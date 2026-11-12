#!/usr/bin/env python3
"""The dictation engine: a local speech-to-text service the dashboard server starts for the review page's
microphone buttons -- see REVIEW.md, "Dictation". It runs in its own virtual environment (faster-whisper and its
decoders), never in the plugin's Python, and only once the developer has set it up.

Usage (the dashboard server runs it; the token comes in the environment, never on the command line):
    CRAFTSMAN_SPEECH_TOKEN=<secret> speech_service.py --models <dir> --active <model id> [--port 0]

It prints one JSON line, {"port": <port>}, once it listens, and logs to stderr.

Contract, the same as OpenAI's `POST /v1/audio/transcriptions`, so an external server can stand in for it:
- 127.0.0.1 only; every route wants `Authorization: Bearer <token>`; a request naming another Host, or sent by a
  browser (any Origin), is refused;
- `POST /v1/audio/transcriptions`, multipart: `file` (Opus in WebM or Ogg, or WAV), `language` (`en` | `pl`), optional `model`
  (an installed model; the active one by default) -> {"text", "language", "duration"};
- `GET /health` -> {"status", "active_model", "installed_models"};
- at most 60 s of audio and 2 MB of upload; one transcription at a time, a second one gets 429 with Retry-After;
- errors are {"error": {"message", "type"}}: 400, 401, 403, 404, 413, 415, 429, 500 -- a 500's details go to the
  log only.
The audio stays in memory: it is never written to disk and never logged.
"""
import argparse
import email.parser
import email.policy
import hmac
import json
import os
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LANGUAGES = ("en", "pl")
MAX_SECONDS = 60
MAX_UPLOAD = 2 * 1024 * 1024
RETRY_AFTER = 2
SAMPLE_RATE = 16000
# what a clip starts with: the decoder is chosen by these bytes, never by the declared type
SIGNATURES = (b"\x1a\x45\xdf\xa3",  # WebM / Matroska (EBML)
              b"OggS",              # Ogg, what Firefox may record Opus in
              b"RIFF")              # WAV


class Refused(Exception):
    def __init__(self, status, message, kind="invalid_request_error"):
        super().__init__(message)
        self.status, self.kind = status, kind


def form_fields(ctype, body):
    """The fields of a multipart/form-data body, name -> bytes."""
    if not ctype.startswith("multipart/form-data"):
        raise Refused(400, "send the audio as multipart/form-data")
    message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        b"Content-Type: " + ctype.encode("latin-1") + b"\r\n\r\n" + body)
    if not message.is_multipart():
        raise Refused(400, "send the audio as multipart/form-data")
    fields = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name:
            fields[name] = part.get_payload(decode=True) or b""
    return fields


def handler(engine, token):
    busy = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def answer(self, status, body, headers=()):
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(raw)

        def refuse(self, status, message, kind="invalid_request_error", headers=()):
            self.close_connection = True
            self.answer(status, {"error": {"message": message, "type": kind}}, headers)

        def admitted(self):
            port = self.server.server_address[1]
            if self.headers.get("Origin") is not None or \
                    self.headers.get("Host", "") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                self.refuse(403, "only the craftsman dashboard may call this service", "permission_error")
                return False
            given = self.headers.get("Authorization", "")
            if not (given.startswith("Bearer ") and hmac.compare_digest(given[7:].encode(), token.encode())):
                self.refuse(401, "a valid bearer token is required", "authentication_error")
                return False
            return True

        def do_GET(self):
            if not self.admitted():
                return
            if self.path != "/health":
                return self.refuse(404, "not found", "not_found_error")
            self.answer(200, {"status": "ok", "active_model": engine.active_model(),
                              "installed_models": engine.installed_models()})

        def do_POST(self):
            if not self.admitted():
                return
            if self.path != "/v1/audio/transcriptions":
                return self.refuse(404, "not found", "not_found_error")
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self.refuse(400, "a Content-Length is required")
            if length > MAX_UPLOAD:
                return self.refuse(413, f"at most {MAX_UPLOAD // (1024 * 1024)} MB of audio")
            body = self.rfile.read(length)
            if not busy.acquire(blocking=False):
                return self.refuse(429, "one transcription at a time", "rate_limit_error",
                                   [("Retry-After", str(RETRY_AFTER))])
            try:
                self.answer(200, self.transcribe(body))
            except Refused as refusal:
                self.refuse(refusal.status, str(refusal), refusal.kind)
            except Exception as failure:  # the details stay in the log
                print(f"speech_service: transcription failed: {failure!r}", file=sys.stderr, flush=True)
                self.refuse(500, "the transcription failed; see the dictation engine's log", "server_error")
            finally:
                busy.release()

        def transcribe(self, body):
            fields = form_fields(self.headers.get("Content-Type", ""), body)
            raw = fields.get("file")
            if not raw:
                raise Refused(400, "no audio in the `file` field")
            language = fields.get("language", b"").decode("utf-8", "replace").strip()
            if language not in LANGUAGES:
                raise Refused(400, f"language must be one of {', '.join(LANGUAGES)}")
            model = fields.get("model", b"").decode("utf-8", "replace").strip() or engine.active_model()
            if model not in engine.installed_models():
                raise Refused(400, f"model {model!r} is not installed")
            if not raw.startswith(SIGNATURES):
                raise Refused(415, "the audio must be WebM or Ogg (Opus), or WAV", "unsupported_media_type")
            samples, duration = engine.decode(raw)
            if duration > MAX_SECONDS:
                raise Refused(413, f"at most {MAX_SECONDS} s of audio")
            text = engine.transcribe(samples, language, model)
            return {"text": text, "language": language, "duration": round(duration, 2)}

    return Handler


def make_server(engine, token, port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), handler(engine, token))
    server.daemon_threads = True
    return server


class WhisperEngine:
    """faster-whisper on the CPU, int8, one model loaded at a time from `<models>/<id>/`; a model is installed when
    its folder holds the `ready` marker."""

    def __init__(self, models, active):
        self.models, self.active, self.loaded, self.lock = pathlib.Path(models), active, {}, threading.Lock()

    def installed_models(self):
        return sorted(p.name for p in self.models.iterdir() if (p / "ready").is_file()) if self.models.is_dir() else []

    def active_model(self):
        return self.active

    def model(self, model_id):
        with self.lock:
            if model_id not in self.loaded:
                from faster_whisper import WhisperModel
                self.loaded = {model_id: WhisperModel(str(self.models / model_id / "model"), device="cpu",
                                                      compute_type="int8", local_files_only=True)}
            return self.loaded[model_id]

    def decode(self, raw):
        """16 kHz mono float samples of the clip and its length in seconds, decoded in memory by PyAV."""
        import io

        import av
        import numpy
        chunks = []
        with av.open(io.BytesIO(raw)) as container:
            resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
            for frame in container.decode(audio=0):
                for out in resampler.resample(frame):
                    chunks.append(out.to_ndarray().reshape(-1))
            for out in resampler.resample(None):
                chunks.append(out.to_ndarray().reshape(-1))
        samples = (numpy.concatenate(chunks) if chunks else numpy.zeros(0, numpy.int16)).astype(numpy.float32) / 32768
        return samples, len(samples) / SAMPLE_RATE

    def transcribe(self, samples, language, model):
        segments, _ = self.model(model).transcribe(samples, language=language, beam_size=5, vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", required=True)
    parser.add_argument("--active", required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    token = os.environ.pop("CRAFTSMAN_SPEECH_TOKEN", "")
    if not token:
        sys.exit("speech_service: CRAFTSMAN_SPEECH_TOKEN is not set")
    # offline: the model loads from its folder and nothing opens a network connection
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    engine = WhisperEngine(args.models, args.active)
    if args.active not in engine.installed_models():
        sys.exit(f"speech_service: model {args.active!r} is not installed in {args.models}")
    engine.model(args.active)
    server = make_server(engine, token, args.port)
    print(json.dumps({"port": server.server_address[1]}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
