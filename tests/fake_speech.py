"""A stand-in for the dictation engine's process: the real speech service, with an engine that hears nothing and
says which model and language it was asked for. FAKE_SPEECH_SLOW makes each transcription take that many seconds."""
import argparse
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"))
import speech_service  # noqa: E402


class Engine:
    def __init__(self, active):
        self.active = active

    def installed_models(self):
        return [self.active]

    def active_model(self):
        return self.active

    def decode(self, raw):
        return raw, 1.0

    def transcribe(self, samples, language, model):
        time.sleep(float(os.environ.get("FAKE_SPEECH_SLOW") or 0))
        return f"[{model}/{language}] heard {len(samples)} bytes"


parser = argparse.ArgumentParser()
parser.add_argument("--models")
parser.add_argument("--active")
args = parser.parse_args()
token = os.environ.pop("CRAFTSMAN_SPEECH_TOKEN")
print("fake speech service: starting", file=sys.stderr, flush=True)
server = speech_service.make_server(Engine(args.active), token)
print('{"port": %d}' % server.server_address[1], flush=True)
server.serve_forever()
