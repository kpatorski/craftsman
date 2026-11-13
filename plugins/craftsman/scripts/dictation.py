#!/usr/bin/env python3
"""The dictation engine's setup and its models -- see REVIEW.md, "Dictation". Nothing is installed until the
developer asks: `setup` builds the engine's own virtual environment and fetches the default model; the other commands
manage the models.

Usage:
    dictation.py setup [--python <python3.9-3.13>]
    dictation.py list [--json]
    dictation.py add <model> | remove <model> | use <model>
    dictation.py status [--json]

Everything lives in `<craftsman home>/dictation/`: `venv/` (faster-whisper and its decoders, from the hash-locked
`dictation_requirements.txt`) and `models/<id>/`. Each is usable only once its `ready` marker is written, last; the
venv's marker holds a fingerprint of the requirements and the Python version, so a changed pin rebuilds it and an
unchanged run does nothing.

A model comes from OpenAI alone: its checkpoint from OpenAI's download server, which names each file by its SHA-256,
and the tokenizer from the openai/whisper repository at a pinned commit. Both are checked against their pinned size
and SHA-256, then whisper_convert.py, run by the engine's Python, turns them into the model faster-whisper reads, and
every file it writes is checked against its own pin before the model is put in place. The network is needed only
here: pip and the downloads go through the usual proxy (HTTPS_PROXY) and CA (REQUESTS_CA_BUNDLE, SSL_CERT_FILE,
PIP_CERT) settings. The active model is `dictation-model` in the craftsman settings.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _reviews  # noqa: E402
import _settings  # noqa: E402

REQUIREMENTS = HERE / "dictation_requirements.txt"
DEFAULT_MODEL = "small"
VENV_BYTES = 230 * 1024 * 1024  # the installed packages: 219 MB on macOS arm64, Python 3.12
MARGIN = 1.2
PYTHONS = ("python3.12", "python3.11", "python3.13", "python3.10", "python3.9", "python3")
SUPPORTED = ((3, 9), (3, 13))
SETUP = "/craftsman:dictation setup"
CONVERTER = HERE / "whisper_convert.py"
WHISPER_COMMIT = "31243bad24cc746f07d4c8bfdd2d974872cb1803"  # openai/whisper v20250625
TOKENIZER = dict(url=f"https://raw.githubusercontent.com/openai/whisper/{WHISPER_COMMIT}/whisper/assets/"
                     "multilingual.tiktoken",
                 size=816730, sha="b34b360dbb493e781e479794586d661700670d65564001f23024971d1f2fa126")
_CHECKPOINTS = "https://openaipublic.azureedge.net/main/whisper/models"
_TOKENIZER_JSON = (3928877, "c5768e14ad96b1ec30a41def9a77a46686b9f06d2e3a24b0884b2b0d49642d7d")
_VOCABULARY = (1068101, "22f3cb2fc2be1545b9a7db8e993ddd59aeccadfbc7d7b00ca517ca8960864766")


def _model(name, size, sha, heads, config, weights, **shown):
    """A catalogue entry: OpenAI's checkpoint, the alignment heads openai-whisper keeps for it, and the size and
    SHA-256 of every file whisper_convert.py makes of it."""
    return dict(checkpoint=dict(url=f"{_CHECKPOINTS}/{sha}/{name}.pt", size=size, sha=sha), heads=heads,
                files={"config.json": config, "model.bin": weights, "tokenizer.json": _TOKENIZER_JSON,
                       "vocabulary.json": _VOCABULARY}, **shown)


CATALOGUE = {
    "base": _model("base", 145262807, "ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e",
                   "ABzY8KQ!870{>%RzyTQH3`Q^yNP!>##QT-<FaQ7m",
                   (2309, "56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a"),
                   (145217607, "905e5bf8336bcc625ba4e33498d675a4b935504118c594d868c36e91a60c1a57"),
                   title="Whisper base", ram="about 0.5 GB", speed="fastest, less accurate"),
    "small": _model("small", 483617219, "9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794",
                    "ABzY8DmU6=0{>%Rpa?J`kvJ6qF(V^F86#Xh7JUGMK}P<N0000",
                    (2370, "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828"),
                    (483546977, "eef2cbde70d256f29b6e3432c85b92becd26f804650e855cc4ff7e66f12122b0"),
                    title="Whisper small", ram="about 1 GB", speed="a few seconds per sentence; the default"),
    "medium": _model("medium", 1528008539, "345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1",
                     "ABzY8B0Jh+0{>%R7}kK1fFL7w6%<-Pf*t^=N)Qr&0RR9",
                     (2257, "3622a2ddc41ec0e0fd4e68c13c6830f03b90c38d89aaad184de02c8c642cf807"),
                     (1527906453, "ddb3f3149bc5c9682af4cf9cf22e215a8bf047ca7772190ad2a58129bfeeca2d"),
                     title="Whisper medium", ram="about 2.5 GB", speed="slow, most accurate"),
}


class SetupFailed(Exception):
    pass


def engine_dir():
    return _reviews.home() / "dictation"


def venv_python(venv):
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ca_bundle():
    """The CA bundle the environment names, for a TLS-inspecting corporate proxy."""
    for name in ("PIP_CERT", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"):
        if os.environ.get(name):
            return os.environ[name]
    return None


def download(url, dest):
    """Fetch `url` into `dest`, resuming a file a broken run left half-written."""
    have = dest.stat().st_size if dest.exists() else 0
    request = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    context = ssl.create_default_context(cafile=ca_bundle())
    try:
        resp = urllib.request.urlopen(request, timeout=60, context=context)
    except urllib.error.HTTPError as failure:
        if failure.code == 416:  # the file is already whole
            return
        raise
    with resp, dest.open("ab" if resp.status == 206 else "wb") as out:
        shutil.copyfileobj(resp, out, 1024 * 1024)


def run(cmd):
    result = subprocess.run(cmd)
    if result.returncode:
        raise SetupFailed(f"{' '.join(map(str, cmd[:4]))}... failed with exit code {result.returncode}")


def find_python():
    """A Python the engine's packages have wheels for: (path, "3.12")."""
    for name in PYTHONS:
        path = shutil.which(name)
        if not path:
            continue
        try:
            version = subprocess.run([path, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                                     capture_output=True, text=True, timeout=20).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        if version and SUPPORTED[0] <= tuple(map(int, version.split("."))) <= SUPPORTED[1]:
            return path, version
    raise SetupFailed("no Python 3.9-3.13 found; pass --python <path>")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as raw:
        for block in iter(lambda: raw.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Engine:
    def __init__(self, fetch=download, run=run, python=None, catalogue=CATALOGUE, tokenizer=TOKENIZER,
                 free_bytes=None):
        self.fetch, self.run, self._python, self.catalogue, self.tokenizer = fetch, run, python, catalogue, tokenizer
        self.free_bytes = free_bytes or (lambda path: shutil.disk_usage(path).free)

    # ---- where things are ---------------------------------------------------------------------------------------

    @property
    def venv(self):
        return engine_dir() / "venv"

    def model_dir(self, model):
        return engine_dir() / "models" / model

    def python(self):
        if self._python is None:
            self._python = find_python()
        return self._python

    def fingerprint(self):
        return hashlib.sha256(REQUIREMENTS.read_bytes() + b"\0python " + self.python()[1].encode()).hexdigest()

    def venv_ready(self):
        try:
            return (self.venv / "ready").read_text().strip() == self.fingerprint()
        except OSError:
            return False

    def installed(self):
        """The models in place, each made from the checkpoint the catalogue pins: its `ready` marker names it."""
        return sorted(model for model, entry in self.catalogue.items()
                      if self.marker(model) == entry["checkpoint"]["sha"])

    def marker(self, model):
        try:
            return (self.model_dir(model) / "ready").read_text().strip()
        except OSError:
            return None

    def active(self):
        return _settings.read().get("dictation-model")

    # ---- what the page and `list` show ---------------------------------------------------------------------------

    def status(self):
        built, active = (self.venv / "ready").is_file(), self.active()
        problem = None
        offer = self.offer()
        if not built:
            problem = f"Dictation is not set up. Run {SETUP} (it downloads about {offer['download']})."
        elif not self.venv_ready():
            problem = f"The dictation engine is out of date. Run {SETUP}."
        elif not active:
            problem = f"No dictation model is chosen. Run {SETUP}."
        elif active not in self.installed():
            problem = f"The dictation model {active} is not installed. Run /craftsman:dictation add {active}."
        return dict(ready=problem is None, active=active if built else None, problem=problem, offer=offer,
                    python=str(venv_python(self.venv)), models=str(engine_dir() / "models"))

    def offer(self):
        """What `setup` fetches when nothing is set up: the engine and the default model."""
        return dict(model=self.catalogue[DEFAULT_MODEL]["title"],
                    download=gb(VENV_BYTES + self.download_size(DEFAULT_MODEL)))

    def listing(self):
        installed, active = self.installed(), self.active()
        rows = [dict(id=model, title=entry["title"], installed=model in installed, active=model == active,
                     download=entry["checkpoint"]["size"], ram=entry["ram"], speed=entry["speed"])
                for model, entry in self.catalogue.items()]
        where = engine_dir() if engine_dir().exists() else _reviews.home() if _reviews.home().exists() else pathlib.Path.home()
        return dict(models=rows, free=self.free_bytes(where))

    # ---- changes ------------------------------------------------------------------------------------------------

    def need_space(self, needed):
        where = next(p for p in (engine_dir(), *engine_dir().parents) if p.exists())
        free = self.free_bytes(where)
        if free < needed * MARGIN:
            raise SetupFailed(f"not enough free disk space: {needed * MARGIN / 2 ** 30:.1f} GB needed, "
                              f"{free / 2 ** 30:.1f} GB free")

    def setup(self):
        """Build what is missing; return what was done -- nothing when everything is already in place."""
        model = self.active() if self.active() in self.catalogue else DEFAULT_MODEL
        needed = (0 if self.venv_ready() else VENV_BYTES) + \
                 (0 if model in self.installed() else self.space_for(model))
        if needed:
            self.need_space(needed)
        done = []
        if not self.venv_ready():
            self.setup_venv()
            done.append("venv")
        if model not in self.installed():
            self.add(model)
            done.append(model)
        if self.active() != model:
            _settings.update("dictation-model", model)
        return done

    def setup_venv(self):
        python, _ = self.python()
        shutil.rmtree(self.venv, ignore_errors=True)
        engine_dir().mkdir(parents=True, exist_ok=True)
        self.run([python, "-m", "venv", str(self.venv)])
        pip = [str(venv_python(self.venv)), "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
               "--require-hashes", "--only-binary=:all:", "-r", str(REQUIREMENTS)]
        if ca_bundle():
            pip += ["--cert", ca_bundle()]
        self.run(pip)
        (self.venv / "ready").write_text(self.fingerprint() + "\n")

    def download_size(self, model):
        return self.entry(model)["checkpoint"]["size"] + self.tokenizer["size"]

    def space_for(self, model):
        """OpenAI's files and the model made of them are on disk together for a moment."""
        return self.download_size(model) + sum(size for size, _ in self.entry(model)["files"].values())

    def entry(self, model):
        if model not in self.catalogue:
            raise SetupFailed(f"no model {model!r}; the models are {', '.join(self.catalogue)}")
        return self.catalogue[model]

    def add(self, model):
        """Fetch OpenAI's checkpoint and tokenizer into `<id>.partial/`, check each, convert them with the engine's
        Python, check every file made, then move the model in place and mark it ready. A run cut short keeps the
        downloads it checked, so the next one fetches only the rest."""
        entry = self.entry(model)
        if model in self.installed():
            return
        if not self.venv_ready():
            raise SetupFailed(f"the dictation engine is not set up; run {SETUP} first")
        partial = engine_dir() / "models" / f"{model}.partial"
        sources = partial / "openai"
        sources.mkdir(parents=True, exist_ok=True)
        wanted = [(entry["checkpoint"], sources / f"{model}.pt"), (self.tokenizer, sources / "multilingual.tiktoken")]
        missing = sum(source["size"] for source, dest in wanted if not self.whole(dest, source["size"], source["sha"]))
        self.need_space(missing + sum(size for size, _ in entry["files"].values()))
        for source, dest in wanted:
            if self.whole(dest, source["size"], source["sha"]):
                continue
            self.fetch(source["url"], dest)
            if not self.whole(dest, source["size"], source["sha"]):
                dest.unlink(missing_ok=True)
                raise SetupFailed(f"{dest.name} does not match its pinned SHA-256; it was thrown away")
        converted = partial / "model"
        shutil.rmtree(converted, ignore_errors=True)
        self.run([str(venv_python(self.venv)), str(CONVERTER), str(wanted[0][1]), str(wanted[1][1]), entry["heads"],
                  str(converted)])
        for name, (size, sha) in entry["files"].items():
            if not self.whole(converted / name, size, sha):
                shutil.rmtree(converted, ignore_errors=True)
                raise SetupFailed(f"the converted {name} of {model} does not match its pinned SHA-256; nothing was "
                                  f"installed")
        target = self.model_dir(model)
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        converted.rename(target / "model")
        shutil.rmtree(partial)
        (target / "ready").write_text(entry["checkpoint"]["sha"] + "\n")

    @staticmethod
    def whole(path, size, sha):
        return path.is_file() and path.stat().st_size == size and sha256(path) == sha

    def remove(self, model):
        self.entry(model)
        if model not in self.installed():
            raise SetupFailed(f"{model} is not installed")
        if model == self.active():
            raise SetupFailed(f"{model} is the active model; switch to another with /craftsman:dictation use <model> first")
        shutil.rmtree(self.model_dir(model))

    def use(self, model):
        self.entry(model)
        if model not in self.installed():
            raise SetupFailed(f"{model} is not installed; add it with /craftsman:dictation add {model}")
        _settings.update("dictation-model", model)


def gb(n):
    return f"{n / 2 ** 30:.1f} GB" if n >= 2 ** 30 else f"{n / 2 ** 20:.0f} MB"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup")
    setup.add_argument("--python")
    for name in ("list", "status"):
        sub.add_parser(name).add_argument("--json", action="store_true")
    for name in ("add", "remove", "use"):
        sub.add_parser(name).add_argument("model")
    args = parser.parse_args()
    python = None
    if getattr(args, "python", None):
        version = subprocess.run([args.python, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                                 capture_output=True, text=True).stdout.strip()
        python = (args.python, version)
    engine = Engine(python=python)
    try:
        if args.command == "setup":
            done = engine.setup()
            print("dictation is set up" + (f": {', '.join(done)}" if done else "; nothing to do"))
        elif args.command == "status":
            status = engine.status()
            print(json.dumps(status) if args.json else status["problem"] or f"dictation is ready: {status['active']}")
        elif args.command == "list":
            listing = engine.listing()
            if args.json:
                print(json.dumps(listing))
            else:
                for row in listing["models"]:
                    mark = "*" if row["active"] else " "
                    state = "installed" if row["installed"] else "not installed"
                    print(f"{mark} {row['id']:<7} {state:<14} {gb(row['download']):>7}  RAM {row['ram']}; {row['speed']}")
                print(f"free disk: {gb(listing['free'])}")
        else:
            getattr(engine, args.command)(args.model)
            print({"add": f"added {args.model}", "remove": f"removed {args.model}",
                   "use": f"{args.model} is the active model"}[args.command])
    except SetupFailed as failure:
        sys.exit(f"dictation: {failure}")


if __name__ == "__main__":
    main()
