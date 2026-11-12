"""Tests against the real dictation engine: the speech service in its own venv, with the active model, transcribing
speech that macOS's `say` speaks -- once with no network at all. Skipped until `/craftsman:dictation setup` has run.

Run: python3 -m unittest discover -s tests
"""
import http.client
import json
import os
import pathlib
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import dictation  # noqa: E402

STATUS = dictation.Engine().status() if (dictation.engine_dir() / "venv" / "ready").is_file() else {"ready": False}
# no network but loopback: a sandbox profile on macOS, a fresh network namespace on Linux
NO_NETWORK = {"darwin": ["sandbox-exec", "-p", '(version 1)(allow default)(deny network-outbound)'
                         '(allow network-outbound (remote ip "localhost:*"))(allow network-outbound (remote unix-socket))'],
              "linux": ["unshare", "-rn", "sh", "-c", "ip link set lo up && exec \"$0\" \"$@\""]}.get(sys.platform)


@unittest.skipUnless(STATUS["ready"], "the dictation engine is not set up (/craftsman:dictation setup)")
@unittest.skipUnless(shutil.which("say"), "needs macOS's `say` to speak the test sentence")
class SpeechEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.clip = cls.tmp / "clip.wav"
        subprocess.run(["say", "-o", str(cls.clip), "--data-format=LEI16@16000", "Please rename the reservation class."],
                       check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def start(self, prefix=()):
        token = secrets.token_urlsafe(24)
        proc = subprocess.Popen([*prefix, STATUS["python"], str(SCRIPTS / "speech_service.py"), "--models", STATUS["models"],
                                 "--active", STATUS["active"]], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=dict(os.environ, CRAFTSMAN_SPEECH_TOKEN=token), text=True)
        self.addCleanup(proc.kill)
        line = proc.stdout.readline()
        self.assertTrue(line, proc.stderr.read() if proc.poll() is not None else "no port line")
        return json.loads(line)["port"], token

    def transcribe(self, port, token):
        boundary = uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\nen\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="clip.wav"\r\n'
                f"Content-Type: audio/wav\r\n\r\n").encode() + self.clip.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
        conn.request("POST", "/v1/audio/transcriptions", body, {
            "Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}"})
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read())

    def test_spoken_english_comes_back_as_text(self):
        status, body = self.transcribe(*self.start())
        self.assertEqual(status, 200, body)
        self.assertIn("rename", body["text"].lower())
        self.assertIn("reservation", body["text"].lower())

    @unittest.skipUnless(NO_NETWORK and shutil.which(NO_NETWORK[0]), "no way to cut the network on this system")
    def test_the_engine_works_with_no_network_at_all(self):
        status, body = self.transcribe(*self.start(NO_NETWORK))
        self.assertEqual(status, 200, body)
        self.assertIn("rename", body["text"].lower())


if __name__ == "__main__":
    unittest.main()
