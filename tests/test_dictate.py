"""Tests for dictation through the dashboard server: the page posts a recording to `/api/dictate`, the server starts
the engine when needed, forwards the recording with a secret the page never sees, and stops the engine when it has
been idle -- see REVIEW.md, "Dictation". The engine is tests/fake_speech.py.

Run: python3 -m unittest discover -s tests
"""
import http.client
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import wave

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _settings  # noqa: E402
import _speech  # noqa: E402
import dashboard_server  # noqa: E402
import speech_service  # noqa: E402


def wav(seconds=1.0):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x01" * int(seconds * 16000))
    return out.getvalue()


class DictateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.saved = {key: os.environ.get(key) for key in ("CRAFTSMAN_HOME", "FAKE_SPEECH_SLOW")}
        os.environ["CRAFTSMAN_HOME"] = str(self.tmp / "home")
        os.environ.pop("FAKE_SPEECH_SLOW", None)
        self.engine = dict(ready=True, active="small", problem=None, python=sys.executable, models=str(self.tmp))
        self.speech = _speech.Speech(engine_status=lambda: dict(self.engine),
                                     command=lambda status: [sys.executable, str(HERE / "fake_speech.py"),
                                                             "--active", status["active"]], idle=60,
                                     setup_command=lambda: [sys.executable, "-c", self.setup_script])
        self.setup_script = "import time; time.sleep(0.5)"
        self.real_state = dashboard_server.STATE
        dashboard_server.STATE = self.tmp / "dashboard-state.json"
        self.server = dashboard_server.ThreadingHTTPServer(("127.0.0.1", 0), dashboard_server.Handler)
        self.port = self.server.server_address[1]
        hub = dashboard_server.Hub(self.tmp / "content", [], self.port)
        hub.speech = self.speech
        dashboard_server.Handler.hub = hub
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.speech.stop()
        self.server.shutdown()
        self.server.server_close()
        dashboard_server.STATE = self.real_state
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def request(self, path, body=None, ctype="audio/wav", headers=None):
        sent = {"Host": f"127.0.0.1:{self.port}", "X-Craftsman": "1", "Content-Type": ctype, **(headers or {})}
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=body, headers=sent,
                                         method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            raw, status = error.read(), error.code
        self.seen = getattr(self, "seen", b"") + raw
        return status, json.loads(raw)

    def dictate(self, language="en", audio=None):
        return self.request(f"/api/dictate?language={language}", wav() if audio is None else audio)

    def test_a_recording_comes_back_as_text_from_an_engine_started_for_it(self):
        self.assertIsNone(self.speech.proc)
        status, body = self.dictate("pl")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["text"].startswith("[small/pl] heard"))
        first = self.speech.proc.pid
        self.dictate("en")
        self.assertEqual(self.speech.proc.pid, first, "the engine stays up between recordings")

    def test_the_secret_never_reaches_the_page(self):
        self.dictate()
        self.request("/api/dictate")
        self.request("/api/dictate/start", b"{}", "application/json")
        self.assertTrue(self.speech.token)
        self.assertNotIn(self.speech.token.encode(), self.seen)
        self.assertNotIn(self.speech.token, " ".join(self.speech.proc.args))

    def test_the_status_says_whether_the_engine_runs(self):
        self.assertEqual(self.request("/api/dictate")[1]["state"], "off")
        self.dictate()
        self.assertEqual(self.request("/api/dictate")[1]["state"], "ready")

    def test_start_warms_the_engine_up_without_waiting_for_it(self):
        status, body = self.request("/api/dictate/start", b"{}", "application/json")
        self.assertEqual(status, 200)
        self.assertIn(body["state"], ("starting", "ready"))
        for _ in range(100):
            if self.request("/api/dictate")[1]["state"] == "ready":
                break
            time.sleep(0.05)
        self.assertEqual(self.request("/api/dictate")[1]["state"], "ready")

    def test_without_the_engine_set_up_the_page_is_told_how_to_set_it_up(self):
        self.engine.update(ready=False, problem="Dictation is not set up. Run /craftsman:dictation setup.")
        status, body = self.request("/api/dictate")
        self.assertEqual((status, body["state"]), (200, "unavailable"))
        self.assertIn("/craftsman:dictation setup", body["problem"])
        status, body = self.dictate()
        self.assertEqual((status, body["kind"]), (409, "not-set-up"))
        self.assertIsNone(self.speech.proc)

    def test_an_idle_engine_is_stopped_and_starts_again_when_needed(self):
        self.dictate()
        proc = self.speech.proc
        self.speech.idle = 0
        self.speech.reap()
        self.assertIsNone(self.speech.proc)
        self.assertIsNotNone(proc.poll(), "the process has exited")
        self.assertEqual(self.dictate()[0], 200)
        self.assertNotEqual(self.speech.proc.pid, proc.pid)

    def test_a_used_engine_is_not_stopped(self):
        self.dictate()
        self.speech.reap()
        self.assertIsNotNone(self.speech.proc)

    def test_a_new_active_model_restarts_the_engine(self):
        self.dictate()
        self.engine["active"] = "base"
        status, body = self.dictate()
        self.assertTrue(body["text"].startswith("[base/en]"), body)

    def test_a_dead_engine_is_started_again(self):
        self.dictate()
        self.speech.proc.kill()
        self.speech.proc.wait()
        self.assertEqual(self.dictate()[0], 200)

    def test_a_busy_engine_is_reported_as_busy(self):
        os.environ["FAKE_SPEECH_SLOW"] = "1.5"
        self.speech.ensure()
        first = threading.Thread(target=self.dictate)
        first.start()
        time.sleep(0.4)
        status, body = self.dictate()
        first.join()
        self.assertEqual((status, body["kind"]), (429, "busy"))

    def test_a_bad_language_or_an_empty_recording_is_refused_without_starting_the_engine(self):
        self.assertEqual(self.dictate("de")[0], 400)
        self.assertEqual(self.dictate("en", b"")[0], 400)
        self.assertIsNone(self.speech.proc)

    def test_an_engine_refusal_comes_back_with_its_message(self):
        status, body = self.dictate("en", b"ID3 not audio we read")
        self.assertEqual((status, body["kind"]), (415, "unsupported_media_type"))
        self.assertIn("WebM", body["error"])

    def test_a_recording_over_the_limit_is_refused_before_it_is_read(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/api/dictate?language=en", skip_host=True)
        for name, value in (("Host", f"127.0.0.1:{self.port}"), ("X-Craftsman", "1"), ("Content-Type", "audio/webm"),
                            ("Content-Length", str(speech_service.MAX_UPLOAD + 1))):
            conn.putheader(name, value)
        conn.endheaders()  # the body is never sent: the answer comes before it
        resp = conn.getresponse()
        self.assertEqual(resp.status, 413)
        conn.close()
        self.assertIsNone(self.speech.proc)

    def test_only_the_page_may_dictate(self):
        for headers in ({"X-Craftsman": ""}, {"Host": "evil.example.com"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("/api/dictate?language=en", wav(), headers=headers)[0], 403)
        self.assertIsNone(self.speech.proc)

    def wait_for(self, state, seconds=5):
        for _ in range(int(seconds / 0.05)):
            body = self.request("/api/dictate")[1]
            if body["state"] == state:
                return body
            time.sleep(0.05)
        self.fail(f"the state never became {state}: {body}")

    def test_set_up_from_the_page_runs_the_setup_once_and_the_engine_is_then_ready(self):
        self.engine.update(ready=False, problem="Dictation is not set up. Run /craftsman:dictation setup.")
        status, body = self.request("/api/dictate/setup", b"{}", "application/json")
        self.assertEqual((status, body["state"]), (200, "installing"))
        first = self.speech.installer
        self.assertEqual(self.request("/api/dictate/setup", b"{}", "application/json")[1]["state"], "installing")
        self.assertIs(self.speech.installer, first, "a second click does not start a second setup")
        self.engine.update(ready=True, problem=None)
        self.wait_for("off")

    def test_a_failed_setup_from_the_page_says_where_to_look(self):
        self.engine.update(ready=False, problem="Dictation is not set up. Run /craftsman:dictation setup.")
        self.setup_script = "import sys; sys.exit('no network')"
        self.request("/api/dictate/setup", b"{}", "application/json")
        body = self.wait_for("unavailable")
        self.assertIn("setup failed", body["problem"])
        self.assertIn("setup.log", body["problem"])

    def test_set_up_is_refused_when_the_engine_is_already_set_up(self):
        status, body = self.request("/api/dictate/setup", b"{}", "application/json")
        self.assertEqual(status, 409)
        self.assertIsNone(self.speech.installer)

    def test_the_engine_stops_with_the_dashboard(self):
        self.dictate()
        proc = self.speech.proc
        dashboard_server.Handler.hub.stop_sessions()  # what the server runs as it stops
        self.assertIsNotNone(proc.wait(5))
        self.assertIsNone(self.speech.proc)


class ExternalServerTest(DictateTest.__base__):
    """With `dictation-server` set, the dashboard talks to that server the same way, and starts nothing."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        saved = os.environ.get("CRAFTSMAN_HOME")
        os.environ["CRAFTSMAN_HOME"] = str(self.tmp / "home")
        self.addCleanup(lambda: os.environ.__setitem__("CRAFTSMAN_HOME", saved) if saved
                        else os.environ.pop("CRAFTSMAN_HOME", None))
        sys.path.insert(0, str(HERE))
        from test_speech_service import FakeEngine
        self.external = speech_service.make_server(FakeEngine(), "external-token", port=0)
        threading.Thread(target=self.external.serve_forever, daemon=True).start()
        self.addCleanup(self.external.server_close)
        self.addCleanup(self.external.shutdown)
        _settings.update("dictation-server", {"url": f"http://localhost:{self.external.server_address[1]}",
                                              "token": "external-token"})
        self.speech = _speech.Speech(engine_status=lambda: self.fail("the built-in engine is not asked"),
                                     command=lambda status: self.fail("nothing is started"))

    def test_a_recording_goes_to_the_external_server(self):
        status, body = self.speech.transcribe(wav(), "pl")
        self.assertEqual((status, body), (200, {"text": "Przezwijmy klasę"}))
        self.assertIsNone(self.speech.proc)

    def test_the_status_has_no_model_management_and_no_token(self):
        status = self.speech.status()
        self.assertEqual((status["state"], status["external"]), ("ready", True))
        self.assertNotIn("external-token", json.dumps(status))

    def test_a_wrong_token_is_reported(self):
        _settings.update("dictation-server", {"url": f"http://localhost:{self.external.server_address[1]}",
                                              "token": "wrong"})
        status, body = self.speech.transcribe(wav(), "en")
        self.assertEqual((status, body["kind"]), (401, "authentication_error"))

    def test_an_unreachable_server_is_reported(self):
        _settings.update("dictation-server", {"url": "http://127.0.0.1:9", "token": "t"})
        status, body = self.speech.transcribe(wav(), "en")
        self.assertEqual((status, body["kind"]), (502, "unreachable"))


if __name__ == "__main__":
    unittest.main()
