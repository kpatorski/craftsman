"""Dictation as the dashboard server sees it: the page posts a recording to `/api/dictate`, and this forwards it to
the speech engine -- see REVIEW.md, "Dictation".

The engine is either the built-in one, `speech_service.py` in its own venv (set up by `dictation.py`), or an external
server the developer runs, named by `dictation-server` ({"url", "token"}) in the craftsman settings; both take the same
`POST /v1/audio/transcriptions`. The built-in engine is started on the first dictation (or when the page warms it up),
with a secret made for that start: it is passed in the environment, and never reaches the page, a URL or a log. It is
stopped after IDLE_SECONDS with no dictation, when the active model changes, and when the dashboard stops.

Setting the engine up is the developer's explicit act: `/craftsman:dictation setup`, or the page's "Set up" button,
which runs the same command in the background -- never anything on its own.
"""
import json
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

import dictation
import _settings
import speech_service

HERE = os.path.dirname(os.path.abspath(__file__))
IDLE_SECONDS = 600
START_SECONDS = 120
ANSWER_SECONDS = 140  # a 58 s clip of repetitive speech took 80 s on an M1 with `small`
LANGUAGES = speech_service.LANGUAGES
MAX_UPLOAD = speech_service.MAX_UPLOAD


def setup_command():
    return [sys.executable, os.path.join(HERE, "dictation.py"), "setup"]


def built_in_command(status):
    return [status["python"], os.path.join(HERE, "speech_service.py"), "--models", status["models"],
            "--active", status["active"]]


class Speech:
    def __init__(self, engine_status=None, command=built_in_command, idle=IDLE_SECONDS, setup_command=setup_command):
        self.engine_status = engine_status or (lambda: dictation.Engine().status())
        self.command, self.idle, self.setup_command = command, idle, setup_command
        self.installer, self.setup_failed = None, None
        self.proc = self.port = self.token = self.model = None
        self.starting, self.last_used = False, 0.0
        self.lock = threading.RLock()

    # ---- which engine --------------------------------------------------------------------------------------------

    @staticmethod
    def external():
        server = _settings.read().get("dictation-server")
        return server if isinstance(server, dict) and server.get("url") else None

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def status(self):
        """What the page shows: `unavailable` (with the problem and its fix), `off`, `starting` or `ready`."""
        if self.external():
            return dict(state="ready", external=True, problem=None, languages=list(LANGUAGES))
        if self.installer is not None and self.installer.poll() is None:
            return dict(state="installing", external=False, problem=None, languages=list(LANGUAGES))
        engine = self.engine_status()
        if not engine["ready"]:
            return dict(state="unavailable", external=False, problem=self.setup_failed or engine["problem"],
                        languages=list(LANGUAGES), setup=engine.get("offer") or True)
        state = "starting" if self.starting else "ready" if self.alive() else "off"
        return dict(state=state, external=False, problem=None, languages=list(LANGUAGES), model=engine["active"])

    def setup(self):
        """Run the engine's setup in the background, once; (HTTP status, status)."""
        with self.lock:
            if self.installer is not None and self.installer.poll() is None:
                return 200, self.status()
            if self.external() or self.engine_status()["ready"]:
                return 409, dict(self.status(), error="the dictation engine is already set up")
            log = dictation.engine_dir() / "setup.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            self.setup_failed = None
            with log.open("ab") as out:
                self.installer = subprocess.Popen(self.setup_command(), stdin=subprocess.DEVNULL, stdout=out,
                                                  stderr=subprocess.STDOUT)
            threading.Thread(target=self.await_setup, args=(self.installer, log), daemon=True).start()
            return 200, self.status()

    def await_setup(self, installer, log):
        if installer.wait():
            self.setup_failed = f"The dictation setup failed; see {log}, or run /craftsman:dictation setup."

    # ---- the built-in engine's process ---------------------------------------------------------------------------

    def warm(self):
        """Start the built-in engine in the background, so it is up by the time the recording ends."""
        if not self.external() and not self.alive() and not self.starting and self.engine_status()["ready"]:
            self.starting = True
            threading.Thread(target=self.quietly_ensure, daemon=True).start()
        return self.status()

    def quietly_ensure(self):
        try:
            self.ensure()
        except Unavailable:
            pass

    def ensure(self):
        """The running engine for the active model: (port, token), started or restarted as needed."""
        with self.lock:
            engine = self.engine_status()
            if not engine["ready"]:
                raise Unavailable(409, engine["problem"], "not-set-up")
            if self.alive() and self.model == engine["active"]:
                return self.port, self.token
            self.stop()
            self.starting = True
            try:
                return self.start(engine)
            finally:
                self.starting = False

    def start(self, engine):
        token = secrets.token_urlsafe(32)
        log = dictation.engine_dir() / "service.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("ab") as errors:
            # the engine reads its model from disk only: faster-whisper never reaches for a model hub
            proc = subprocess.Popen(self.command(engine), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=errors, env=dict(os.environ, CRAFTSMAN_SPEECH_TOKEN=token,
                                                            HF_HUB_OFFLINE="1"))
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(proc.stdout.readline()), daemon=True).start()
        try:
            port = json.loads(lines.get(timeout=START_SECONDS))["port"]
        except (queue.Empty, ValueError, KeyError, TypeError):
            proc.kill()
            raise Unavailable(503, f"the speech engine did not start; see {log}", "engine-failed")
        self.proc, self.port, self.token, self.model = proc, port, token, engine["active"]
        self.last_used = time.time()
        return port, token

    def reap(self):
        """Stop the built-in engine once it has been idle long enough; the dashboard's watcher calls this."""
        with self.lock:
            if self.alive() and time.time() - self.last_used >= self.idle:
                self.stop()

    def stop(self):
        with self.lock:
            proc, self.proc, self.port, self.token, self.model = self.proc, None, None, None, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    # ---- a recording -----------------------------------------------------------------------------------------------

    def transcribe(self, audio, language):
        """(HTTP status, body) for the page: {"text"} or {"error", "kind"}."""
        if language not in LANGUAGES:
            return 400, dict(error=f"language must be one of {', '.join(LANGUAGES)}", kind="bad-language")
        if not audio:
            return 400, dict(error="the recording is empty", kind="empty")
        external = self.external()
        try:
            if external:
                url, token, opener = external["url"].rstrip("/"), str(external.get("token") or ""), urllib.request.build_opener()
            else:
                port, token = self.ensure()
                # loopback only: never through a proxy the environment names
                url, opener = f"http://127.0.0.1:{port}", urllib.request.build_opener(urllib.request.ProxyHandler({}))
        except Unavailable as unavailable:
            return unavailable.status, dict(error=str(unavailable), kind=unavailable.kind)
        boundary = uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\n{language}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="dictation"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n").encode() + audio + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(f"{url}/v1/audio/transcriptions", data=body, method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with opener.open(request, timeout=ANSWER_SECONDS) as response:
                answer = json.loads(response.read())
            return 200, dict(text=str(answer.get("text", "")).strip())
        except urllib.error.HTTPError as refusal:
            try:
                error = json.loads(refusal.read())["error"]
                message, kind = str(error["message"]), str(error["type"])
            except (ValueError, KeyError, TypeError):
                message, kind = f"the speech engine answered {refusal.code}", "engine-failed"
            if refusal.code == 429:
                return 429, dict(error="the speech engine is busy with another recording", kind="busy")
            return (refusal.code if refusal.code < 500 else 502), dict(error=message, kind=kind)
        except (OSError, ValueError) as failure:
            print(f"dictation: the speech engine is unreachable: {failure!r}", file=sys.stderr, flush=True)
            if not external:
                self.stop()
            return 502, dict(error="the speech engine could not be reached", kind="unreachable")
        finally:
            self.last_used = time.time()


class Unavailable(Exception):
    def __init__(self, status, message, kind):
        super().__init__(message)
        self.status, self.kind = status, kind
