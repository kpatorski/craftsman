"""Tests for setting up the dictation engine and managing its models -- see REVIEW.md, "Dictation". Downloads and
pip are faked: nothing here touches the network.

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

CONTENT = {"config.json": b"{}", "model.bin": b"weights" * 100, "tokenizer.json": b"tok", "vocabulary.txt": b"voc"}
SHA = {name: hashlib.sha256(raw).hexdigest() for name, raw in CONTENT.items()}
CATALOGUE = {model: dict(repo=f"Systran/faster-whisper-{model}", revision="r" * 40, title=model, ram="1 GB",
                         speed="fast", files={name: (len(raw), SHA[name]) for name, raw in CONTENT.items()})
             for model in ("base", "small", "medium")}
PYTHON = ("/usr/bin/python3.12", "3.12")


class FakeNet:
    """Serves the model files; can break after some files, or hand out a corrupted one."""

    def __init__(self):
        self.fetched, self.break_after, self.corrupt = [], None, None

    def __call__(self, url, dest):
        name = url.rsplit("/", 1)[1]
        if self.break_after is not None and len(self.fetched) >= self.break_after:
            raise OSError("connection reset")
        self.fetched.append(name)
        dest.write_bytes(b"garbage" if name == self.corrupt else CONTENT[name])


class FakePip:
    """Makes a venv folder where `python -m venv` would; records every command."""

    def __init__(self):
        self.commands, self.fail = [], False

    def __call__(self, cmd):
        self.commands.append(cmd)
        if self.fail and "pip" in cmd:
            raise dictation.SetupFailed("pip could not install")
        if cmd[1:3] == ["-m", "venv"]:
            (pathlib.Path(cmd[3]) / "bin").mkdir(parents=True, exist_ok=True)


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
                                       free_bytes=lambda path: 10 ** 12)

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
        self.assertEqual(sorted(self.net.fetched), sorted(CONTENT))
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
                                   catalogue=CATALOGUE, free_bytes=lambda path: 10 ** 12)
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
                                 free_bytes=lambda path: 1000)
        with self.assertRaises(dictation.SetupFailed) as refused:
            tight.setup()
        self.assertIn("free", str(refused.exception))
        self.assertEqual(self.pip.commands, [])

    def test_a_download_cut_short_leaves_no_model_and_the_next_add_resumes(self):
        self.engine.setup_venv()
        self.net.break_after = 2
        with self.assertRaises(OSError):
            self.engine.add("base")
        self.assertNotIn("base", self.engine.installed())
        self.assertFalse((dictation.engine_dir() / "models" / "base" / "ready").exists())
        first = list(self.net.fetched)
        self.net.break_after = None
        self.engine.add("base")
        self.assertIn("base", self.engine.installed())
        self.assertEqual(sorted(first + self.net.fetched[2:]), sorted(CONTENT))

    def test_a_file_that_fails_its_checksum_is_thrown_away(self):
        self.engine.setup_venv()
        self.net.corrupt = "model.bin"
        with self.assertRaises(dictation.SetupFailed) as refused:
            self.engine.add("base")
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

    def test_model_files_come_from_the_pinned_revision(self):
        urls = []
        engine = dictation.Engine(fetch=lambda url, dest: (urls.append(url), self.net(url, dest)), run=self.pip,
                                  python=PYTHON, catalogue=CATALOGUE, free_bytes=lambda path: 10 ** 12)
        engine.add("base")
        self.assertIn(f"https://huggingface.co/Systran/faster-whisper-base/resolve/{'r' * 40}/model.bin", urls)

    def test_the_real_catalogue_pins_every_file(self):
        for model, entry in dictation.CATALOGUE.items():
            with self.subTest(model=model):
                self.assertRegex(entry["revision"], r"^[0-9a-f]{40}$")
                self.assertEqual(set(entry["files"]), set(CONTENT))
                for size, sha in entry["files"].values():
                    self.assertRegex(sha, r"^[0-9a-f]{64}$")
                    self.assertGreater(size, 0)
        self.assertIn(dictation.DEFAULT_MODEL, dictation.CATALOGUE)


if __name__ == "__main__":
    unittest.main()
