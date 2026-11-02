"""Tests for _review_session.py: the dashboard server runs each review's Claude session itself, so the page is the
console -- see REVIEW.md. A fake `claude` (fake_claude.py) speaks the same stream-json, records what it was sent, and
records page messages as handled the way the review skill does.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile
import time
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _review_session as sessions  # noqa: E402
import _reviews as reviews  # noqa: E402
import review_state  # noqa: E402

SESSION = "11111111-2222-3333-4444-555555555555"
ID = "org-booking-pr-123"


def eventually(check, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return False


class ReviewSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.checkout = self.tmp / "booking"
        self.checkout.mkdir()
        self.real_home = os.environ.get("CRAFTSMAN_HOME")
        os.environ["CRAFTSMAN_HOME"] = str(self.tmp / "craftsman-home")
        self.review = self.tmp / "craftsman-home" / "reviews" / ID
        self.log = self.tmp / "fake-claude.log"
        os.environ.update(FAKE_CLAUDE_LOG=str(self.log), FAKE_REVIEW_DIR=str(self.review),
                          CRAFTSMAN_SCRIPTS=str(SCRIPTS))
        self.command = [sys.executable, str(TESTS / "fake_claude.py")]
        self.runner = None

    def tearDown(self):
        if self.runner:
            self.runner.stop()
        if self.real_home is None:
            os.environ.pop("CRAFTSMAN_HOME", None)
        else:
            os.environ["CRAFTSMAN_HOME"] = self.real_home
        shutil.rmtree(self.tmp)

    def logged(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def received(self):
        return [entry["received"] for entry in self.logged() if "received" in entry]

    def started(self):
        self.runner = sessions.ReviewSession(ID, self.checkout, command=self.command)
        self.runner.start("https://github.com/org/booking/pull/123")
        self.assertTrue(eventually(lambda: not self.runner.busy()), "the first turn never ended")

    def test_the_review_starts_with_the_command_and_its_source(self):
        self.started()

        self.assertEqual(self.received(), [f"/craftsman:pr-review --headless https://github.com/org/booking/pull/123 "
                                           f"--review {self.review} --checkout {self.checkout}"])

    def test_the_session_runs_in_the_checkout_and_records_it(self):
        self.started()

        self.assertEqual(pathlib.Path(self.logged()[0]["cwd"]).resolve(), self.checkout)
        self.assertEqual(review_state.read(self.review)["checkout"], str(self.checkout))

    def test_the_session_runs_headless_with_a_fixed_tool_list(self):
        self.started()

        argv = self.logged()[0]["argv"]
        for flag in ("-p", "--verbose", "--replay-user-messages", "--permission-mode", "dontAsk", "--allowedTools"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--input-format") + 1], "stream-json")
        self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")

    def test_the_session_may_run_each_craftsman_script_by_its_full_path(self):
        self.started()

        argv = self.logged()[0]["argv"]
        tools = argv[argv.index("--allowedTools") + 1:]
        self.assertIn(f"Bash(python3 {SCRIPTS}/review_state.py:*)", tools)
        self.assertNotIn(f"Bash(python3 {SCRIPTS}/:*)", tools)

    def test_the_session_may_write_only_its_own_session_files_by_absolute_path(self):
        self.started()

        argv = self.logged()[0]["argv"]
        tools = argv[argv.index("--allowedTools") + 1:]
        self.assertIn(f"Write(/{self.checkout}/.claude/sessions/**)", tools)
        self.assertIn(f"Edit(/{self.checkout}/.claude/sessions/**)", tools)

    def test_every_event_is_kept_for_the_console_and_the_session_id_in_the_state(self):
        self.started()

        events = [json.loads(line) for line in (self.review / "session.jsonl").read_text().splitlines()]
        self.assertEqual([e["type"] for e in events], ["system", "assistant", "result"])
        self.assertTrue(eventually(lambda: review_state.read(self.review)["session"] == SESSION))

    def test_page_messages_reach_the_session_one_at_a_time_in_order(self):
        self.started()

        reviews.add_message(ID, {"type": "ask", "thread": "t1"})
        reviews.add_message(ID, {"type": "refresh"})
        self.runner.deliver()

        self.assertTrue(eventually(lambda: len(self.received()) == 3), self.received())
        self.assertIn("m1", self.received()[1])
        self.assertIn("m2", self.received()[2])
        self.assertTrue(eventually(lambda: review_state.read(self.review)["handled"] == ["m1", "m2"]))

    def test_a_resumed_session_continues_the_same_conversation_and_gets_what_it_has_not_handled(self):
        self.started()
        self.runner.stop()
        reviews.add_message(ID, {"type": "refresh"})

        self.runner = sessions.ReviewSession(ID, command=self.command)
        self.runner.resume()

        self.assertTrue(eventually(lambda: any("m1" in text for text in self.received())), self.received())
        resumed = [entry for entry in self.logged() if "argv" in entry][-1]
        self.assertEqual(resumed["argv"][resumed["argv"].index("--resume") + 1], SESSION)
        self.assertEqual(pathlib.Path(resumed["cwd"]).resolve(), self.checkout)

    def test_closing_the_review_ends_its_session(self):
        self.started()

        reviews.add_message(ID, {"type": "close"})
        self.runner.deliver()

        self.assertTrue(eventually(lambda: not self.runner.running()), "the session kept running after close")

    def test_a_stopped_session_is_not_running(self):
        self.started()
        self.assertTrue(self.runner.running())

        self.runner.stop()

        self.assertFalse(self.runner.running())


if __name__ == "__main__":
    unittest.main()
