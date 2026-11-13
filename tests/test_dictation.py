"""Tests for setting up the dictation engine and managing its models -- see REVIEW.md, "Dictation". Downloads, pip
and the conversion of OpenAI's checkpoint are faked: nothing here touches the network.

Run: python3 -m unittest discover -s tests
"""
import hashlib
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _settings  # noqa: E402
import dictation  # noqa: E402

CONTENT = {"config.json": b"{}", "model.bin": b"weights" * 100, "tokenizer.json": b"tok", "vocabulary.json": b"voc"}
SOURCES = {"base.pt": b"base checkpoint", "small.pt": b"small checkpoint" * 50, "medium.pt": b"medium checkpoint",
           "multilingual.tiktoken": b"tiktoken ranks"}


def pinned(raw):
    return len(raw), hashlib.sha256(raw).hexdigest()


def checkpoint(model):
    size, sha = pinned(SOURCES[f"{model}.pt"])
    return dict(url=f"https://openai.example.com/models/{sha}/{model}.pt", size=size, sha=sha)


TOKENIZER = dict(url="https://openai.example.com/assets/multilingual.tiktoken",
                 **dict(zip(("size", "sha"), pinned(SOURCES["multilingual.tiktoken"]))))
CATALOGUE = {model: dict(title=f"Whisper {model}", ram="1 GB", speed="fast", checkpoint=checkpoint(model),
                         heads=f"heads-of-{model}", files={name: pinned(raw) for name, raw in CONTENT.items()})
             for model in ("base", "small", "medium")}
PYTHON = ("/usr/bin/python3.12", "3.12")


class FakeNet:
    """Serves OpenAI's files; can break after some files, or hand out a corrupted one."""

    def __init__(self):
        self.fetched, self.urls, self.break_after, self.corrupt = [], [], None, None

    def __call__(self, url, dest):
        name = url.rsplit("/", 1)[1]
        if self.break_after is not None and len(self.fetched) >= self.break_after:
            raise OSError("connection reset")
        self.fetched.append(name)
        self.urls.append(url)
        dest.write_bytes(b"garbage" if name == self.corrupt else SOURCES[name])


class FakePip:
    """Makes a venv folder where `python -m venv` would, and the converted model where whisper_convert.py would;
    records every command."""

    def __init__(self):
        self.commands, self.fail, self.miswrite = [], False, None

    def __call__(self, cmd):
        self.commands.append(cmd)
        if self.fail and "pip" in cmd:
            raise dictation.SetupFailed("pip could not install")
        if cmd[1:3] == ["-m", "venv"]:
            (pathlib.Path(cmd[3]) / "bin").mkdir(parents=True, exist_ok=True)
        if cmd[1].endswith("whisper_convert.py"):
            self.converted_from = (pathlib.Path(cmd[2]).read_bytes(), pathlib.Path(cmd[3]).read_bytes())
            out = pathlib.Path(cmd[5])
            out.mkdir(parents=True, exist_ok=True)
            for name, raw in CONTENT.items():
                (out / name).write_bytes(b"different" if name == self.miswrite else raw)

    def conversions(self):
        return [cmd for cmd in self.commands if cmd[1].endswith("whisper_convert.py")]


class DictationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        saved = os.environ.get("CRAFTSMAN_HOME")
        os.environ["CRAFTSMAN_HOME"] = str(self.tmp / "home")
        self.addCleanup(lambda: os.environ.__setitem__("CRAFTSMAN_HOME", saved) if saved
                        else os.environ.pop("CRAFTSMAN_HOME", None))
        self.net, self.pip = FakeNet(), FakePip()
        self.engine = dictation.Engine(fetch=self.net, run=self.pip, python=PYTHON, catalogue=CATALOGUE,
                                       tokenizer=TOKENIZER, free_bytes=lambda path: 10 ** 12)

    def test_nothing_is_set_up_until_asked(self):
        status = self.engine.status()
        self.assertEqual((status["ready"], status["active"]), (False, None))
        self.assertIn("/craftsman:dictation setup", status["problem"])
        self.assertFalse((self.tmp / "home" / "dictation").exists())

    def test_setup_builds_the_venv_from_the_locked_requirements_and_installs_the_default_model(self):
        self.engine.setup()
        pip = next(cmd for cmd in self.pip.commands if "pip" in cmd)
        self.assertIn("--require-hashes", pip)
        self.assertIn("--only-binary=:all:", pip)
        self.assertEqual(pip[pip.index("-r") + 1], str(SCRIPTS / "dictation_requirements.txt"))
        self.assertEqual(sorted(self.net.fetched), ["multilingual.tiktoken", "small.pt"])
        status = self.engine.status()
        self.assertEqual((status["ready"], status["active"], status["problem"]), (True, "small", None))
        self.assertEqual(_settings.read()["dictation-model"], "small")

    def test_setup_run_again_does_nothing(self):
        self.engine.setup()
        commands, fetched = len(self.pip.commands), len(self.net.fetched)
        done = self.engine.setup()
        self.assertEqual((len(self.pip.commands), len(self.net.fetched)), (commands, fetched))
        self.assertEqual(done, [])

    def test_a_changed_pin_or_python_rebuilds_the_venv(self):
        self.engine.setup()
        (dictation.engine_dir() / "venv" / "stale").write_text("from the old build")
        rebuilt = dictation.Engine(fetch=self.net, run=self.pip, python=("/usr/bin/python3.11", "3.11"),
                                   catalogue=CATALOGUE, tokenizer=TOKENIZER, free_bytes=lambda path: 10 ** 12)
        self.assertNotEqual(rebuilt.fingerprint(), self.engine.fingerprint())
        rebuilt.setup()
        self.assertFalse((dictation.engine_dir() / "venv" / "stale").exists())
        self.assertTrue(rebuilt.status()["ready"])

    def test_a_failed_pip_install_leaves_no_ready_marker(self):
        self.pip.fail = True
        with self.assertRaises(dictation.SetupFailed):
            self.engine.setup()
        self.assertFalse((dictation.engine_dir() / "venv" / "ready").exists())
        self.assertFalse(self.engine.status()["ready"])

    def test_setup_refuses_when_the_disk_is_too_full(self):
        tight = dictation.Engine(fetch=self.net, run=self.pip, python=PYTHON, catalogue=CATALOGUE,
                                 tokenizer=TOKENIZER, free_bytes=lambda path: 1000)
        with self.assertRaises(dictation.SetupFailed) as refused:
            tight.setup()
        self.assertIn("free", str(refused.exception))
        self.assertEqual(self.pip.commands, [])

    def test_a_model_is_converted_from_openais_checkpoint_and_tokenizer_by_the_engines_python(self):
        self.engine.setup()
        self.assertEqual(self.net.urls, [CATALOGUE["small"]["checkpoint"]["url"], TOKENIZER["url"]])
        [convert] = self.pip.conversions()
        self.assertEqual(convert[0], str(dictation.venv_python(dictation.engine_dir() / "venv")))
        self.assertEqual(self.pip.converted_from, (SOURCES["small.pt"], SOURCES["multilingual.tiktoken"]))
        self.assertEqual(convert[4], "heads-of-small")
        model = dictation.engine_dir() / "models" / "small"
        self.assertEqual({p.name: p.read_bytes() for p in (model / "model").iterdir()}, CONTENT)
        self.assertEqual(sorted(p.name for p in (dictation.engine_dir() / "models").iterdir()), ["small"],
                         "OpenAI's files are gone once the model is in place")

    def test_a_model_from_another_source_counts_as_not_installed_and_setup_replaces_it(self):
        self.engine.setup()
        (dictation.engine_dir() / "models" / "small" / "ready").write_text("ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66\n")
        self.assertEqual(self.engine.installed(), [])
        self.assertIn("/craftsman:dictation add small", self.engine.status()["problem"])
        self.assertEqual(self.engine.setup(), ["small"])
        self.assertEqual(self.engine.installed(), ["small"])

    def test_a_model_cannot_be_added_before_the_engine_is_set_up(self):
        with self.assertRaises(dictation.SetupFailed) as refused:
            self.engine.add("base")
        self.assertIn("/craftsman:dictation setup", str(refused.exception))
        self.assertEqual(self.net.fetched, [])

    def test_a_download_cut_short_leaves_no_model_and_the_next_add_resumes(self):
        self.engine.setup_venv()
        self.net.break_after = 1
        with self.assertRaises(OSError):
            self.engine.add("base")
        self.assertNotIn("base", self.engine.installed())
        self.assertFalse((dictation.engine_dir() / "models" / "base" / "ready").exists())
        self.net.break_after = None
        self.engine.add("base")
        self.assertIn("base", self.engine.installed())
        self.assertEqual(self.net.fetched, ["base.pt", "multilingual.tiktoken"], "base.pt is not fetched twice")

    def test_a_download_that_fails_its_checksum_is_thrown_away(self):
        self.engine.setup_venv()
        self.net.corrupt = "base.pt"
        with self.assertRaises(dictation.SetupFailed) as refused:
            self.engine.add("base")
        self.assertIn("SHA-256", str(refused.exception))
        self.assertNotIn("base", self.engine.installed())
        self.assertEqual(self.pip.conversions(), [])

    def test_a_converted_file_that_fails_its_checksum_installs_nothing(self):
        self.engine.setup_venv()
        self.pip.miswrite = "model.bin"
        with self.assertRaises(dictation.SetupFailed) as refused:
            self.engine.add("base")
        self.assertIn("model.bin", str(refused.exception))
        self.assertIn("SHA-256", str(refused.exception))
        self.assertNotIn("base", self.engine.installed())

    def test_models_are_added_listed_switched_and_removed(self):
        self.engine.setup()
        self.engine.add("base")
        listed = {row["id"]: row for row in self.engine.listing()["models"]}
        self.assertEqual((listed["base"]["installed"], listed["small"]["active"], listed["medium"]["installed"]),
                         (True, True, False))
        self.engine.use("base")
        self.assertEqual(self.engine.status()["active"], "base")
        self.engine.remove("small")
        self.assertEqual(self.engine.installed(), ["base"])

    def test_the_active_model_cannot_be_removed(self):
        self.engine.setup()
        with self.assertRaises(dictation.SetupFailed):
            self.engine.remove("small")
        self.assertIn("small", self.engine.installed())

    def test_an_unknown_or_missing_model_cannot_be_added_or_used(self):
        self.engine.setup()
        for action in (lambda: self.engine.add("huge"), lambda: self.engine.use("medium"),
                       lambda: self.engine.remove("medium")):
            with self.assertRaises(dictation.SetupFailed):
                action()

    def test_a_missing_active_model_is_reported_with_the_command_that_fixes_it(self):
        self.engine.setup()
        shutil.rmtree(dictation.engine_dir() / "models" / "small")
        status = self.engine.status()
        self.assertFalse(status["ready"])
        self.assertIn("/craftsman:dictation add small", status["problem"])

    def test_pip_gets_the_corporate_ca_bundle_from_the_environment(self):
        os.environ["REQUESTS_CA_BUNDLE"] = "/etc/corp-ca.pem"
        self.addCleanup(os.environ.pop, "REQUESTS_CA_BUNDLE", None)
        self.engine.setup_venv()
        pip = next(cmd for cmd in self.pip.commands if "pip" in cmd)
        self.assertEqual(pip[pip.index("--cert") + 1], "/etc/corp-ca.pem")

    def test_the_setup_says_how_much_it_downloads_from_the_catalogue(self):
        problem = self.engine.status()["problem"]
        size = dictation.VENV_BYTES + CATALOGUE["small"]["checkpoint"]["size"] + TOKENIZER["size"]
        self.assertIn(f"about {dictation.gb(size)}", problem)
        self.assertEqual(self.engine.status()["offer"], dict(model="Whisper small", download=dictation.gb(size)))

    def test_the_real_catalogue_takes_everything_from_openai_and_pins_every_file(self):
        self.assertRegex(dictation.TOKENIZER["url"],
                         r"^https://raw\.githubusercontent\.com/openai/whisper/[0-9a-f]{40}/whisper/assets/multilingual\.tiktoken$")
        for model, entry in dictation.CATALOGUE.items():
            with self.subTest(model=model):
                source = entry["checkpoint"]
                self.assertEqual(source["url"], f"https://openaipublic.azureedge.net/main/whisper/models/"
                                                f"{source['sha']}/{model}.pt", "OpenAI names each file by its SHA-256")
                self.assertGreater(source["size"], 0)
                self.assertEqual(set(entry["files"]), set(CONTENT))
                for size, sha in entry["files"].values():
                    self.assertRegex(sha, r"^[0-9a-f]{64}$")
                    self.assertGreater(size, 0)
        self.assertIn(dictation.DEFAULT_MODEL, dictation.CATALOGUE)


if __name__ == "__main__":
    unittest.main()
