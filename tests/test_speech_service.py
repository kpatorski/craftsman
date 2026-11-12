"""Tests for the local speech-to-text service's contract -- see REVIEW.md, "Dictation". A fake engine stands in for
the model, so these run without the dictation engine installed.

Run: python3 -m unittest discover -s tests
"""
import http.client
import io
import json
import pathlib
import sys
import threading
import time
import unittest
import wave

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import speech_service  # noqa: E402

TOKEN = "s3cret-token"


def wav(seconds, rate=16000):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x01" * int(seconds * rate))
    return out.getvalue()


WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64


class FakeEngine:
    """Says what it heard; a WAV's length is read from its header, a WebM clip lasts two seconds."""

    def __init__(self):
        self.calls, self.gate, self.fail = [], None, None

    def installed_models(self):
        return ["base", "small"]

    def active_model(self):
        return "small"

    def decode(self, raw):
        if raw.startswith(b"RIFF"):
            with wave.open(io.BytesIO(raw)) as w:
                return "samples", w.getnframes() / w.getframerate()
        return "samples", 2.0

    def transcribe(self, samples, language, model):
        self.calls.append((language, model))
        if self.gate:
            self.gate.wait(5)
        if self.fail:
            raise self.fail
        return "Przezwijmy klasę" if language == "pl" else "Rename the class"


def multipart(fields, boundary="XyZ"):
    body = b""
    for name, value in fields.items():
        if isinstance(value, bytes):
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="clip"\r\n'
                     f"Content-Type: application/octet-stream\r\n\r\n").encode() + value + b"\r\n"
        else:
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    return body + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


class SpeechServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.server = speech_service.make_server(self.engine, TOKEN, port=0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def call(self, method, path, body=None, ctype=None, token=TOKEN, host=None, origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if ctype:
            headers["Content-Type"] = ctype
        if origin:
            headers["Origin"] = origin
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        return resp.status, json.loads(raw or b"{}"), dict(resp.getheaders())

    def transcribe(self, **fields):
        body, ctype = multipart(fields)
        return self.call("POST", "/v1/audio/transcriptions", body, ctype)

    def test_a_clip_comes_back_as_text_in_the_language_asked_for(self):
        status, body, _ = self.transcribe(file=wav(1.5), language="pl")
        self.assertEqual(status, 200, body)
        self.assertEqual(body, {"text": "Przezwijmy klasę", "language": "pl", "duration": 1.5})
        self.assertEqual(self.engine.calls, [("pl", "small")])

    def test_webm_or_ogg_from_the_browser_is_accepted(self):
        for clip in (WEBM, b"OggS" + b"\x00" * 64):
            with self.subTest(clip=clip[:4]):
                status, body, _ = self.transcribe(file=clip, language="en")
                self.assertEqual((status, body["text"]), (200, "Rename the class"))

    def test_an_installed_model_can_be_asked_for_and_an_unknown_one_is_refused(self):
        self.assertEqual(self.transcribe(file=wav(1), language="en", model="base")[0], 200)
        self.assertEqual(self.engine.calls[-1], ("en", "base"))
        status, body, _ = self.transcribe(file=wav(1), language="en", model="medium")
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["type"], "invalid_request_error")

    def test_a_language_other_than_english_or_polish_is_refused(self):
        for fields in (dict(file=wav(1), language="de"), dict(file=wav(1))):
            with self.subTest(fields=list(fields)):
                self.assertEqual(self.transcribe(**fields)[0], 400)

    def test_a_request_without_audio_is_refused(self):
        self.assertEqual(self.transcribe(language="en")[0], 400)
        self.assertEqual(self.call("POST", "/v1/audio/transcriptions", b"{}", "application/json")[0], 400)

    def test_audio_in_an_unknown_format_is_refused(self):
        status, body, _ = self.transcribe(file=b"ID3\x04 an mp3", language="en")
        self.assertEqual(status, 415)
        self.assertEqual(set(body["error"]), {"message", "type"})

    def test_a_clip_longer_than_a_minute_is_refused(self):
        self.assertEqual(self.transcribe(file=wav(59.9, rate=8000), language="en")[0], 200)
        self.assertEqual(self.transcribe(file=wav(60.5, rate=8000), language="en")[0], 413)

    def test_an_upload_over_the_size_limit_is_refused_before_it_is_read(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/v1/audio/transcriptions", skip_host=True)
        for name, value in (("Host", f"127.0.0.1:{self.port}"), ("Authorization", f"Bearer {TOKEN}"),
                            ("Content-Type", "multipart/form-data; boundary=XyZ"),
                            ("Content-Length", str(speech_service.MAX_UPLOAD + 1))):
            conn.putheader(name, value)
        conn.endheaders()  # the body is never sent: the answer comes before it
        resp = conn.getresponse()
        self.assertEqual(resp.status, 413)
        self.assertEqual(json.loads(resp.read())["error"]["type"], "invalid_request_error")
        conn.close()
        self.assertEqual(self.engine.calls, [])

    def test_a_second_clip_while_one_is_being_transcribed_is_told_to_wait(self):
        self.engine.gate = threading.Event()
        first = {}
        worker = threading.Thread(target=lambda: first.update(r=self.transcribe(file=wav(1), language="en")))
        worker.start()
        for _ in range(100):
            if self.engine.calls:
                break
            time.sleep(0.02)
        status, body, headers = self.transcribe(file=wav(1), language="en")
        self.engine.gate.set()
        worker.join(5)
        self.assertEqual(status, 429)
        self.assertIn("Retry-After", headers)
        self.assertEqual(first["r"][0], 200)

    def test_an_engine_failure_is_a_500_that_keeps_its_details_out_of_the_answer(self):
        self.engine.fail = RuntimeError("CUDA out of memory at /secret/path")
        status, body, _ = self.transcribe(file=wav(1), language="en")
        self.assertEqual(status, 500)
        self.assertNotIn("secret", json.dumps(body))

    def test_health_names_the_active_and_the_installed_models(self):
        status, body, _ = self.call("GET", "/health")
        self.assertEqual((status, body), (200, {"status": "ok", "active_model": "small", "installed_models": ["base", "small"]}))

    def test_every_route_wants_the_token(self):
        for method, path in (("GET", "/health"), ("POST", "/v1/audio/transcriptions"), ("GET", "/nowhere")):
            for token in (None, "wrong"):
                with self.subTest(path=path, token=token):
                    status, body, _ = self.call(method, path, b"", token=token)
                    self.assertEqual(status, 401)
                    self.assertEqual(body["error"]["type"], "authentication_error")

    def test_a_browser_or_a_foreign_host_is_refused_even_with_the_token(self):
        self.assertEqual(self.call("GET", "/health", origin="http://craftsman.localhost:4747")[0], 403)
        self.assertEqual(self.call("GET", "/health", host="evil.example.com")[0], 403)
        self.assertEqual(self.call("GET", "/health", host=f"localhost:{self.port}")[0], 200)

    def test_an_unknown_route_is_a_404(self):
        self.assertEqual(self.call("GET", "/v1/models")[0], 404)


if __name__ == "__main__":
    unittest.main()
