"""Tests for review_state.py: the one way the review's state changes -- see REVIEW.md. The agent and the review page
change the same file at the same time; these tests pin down what each of them may change, and that neither loses
the other's change.

Run: python3 -m unittest discover -s tests
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts" / "review_state.py"

SOURCE = {"kind": "pull-request", "url": "https://github.com/org/booking/pull/123", "repository": "org/booking",
          "number": 123}


def finding(**overrides):
    base = {"category": "naming", "title": "Name says nothing", "description": "The name hides what it does.",
            "comment": "The name `process`...", "locations": [{"path": "A.java", "line": 3, "side": "RIGHT",
                                                                 "commit": "bbb"}],
            "directive": "naming", "kind": "violation"}
    base.update(overrides)
    return base


class ReviewStateTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.review = self.root / "pr-123"
        self.diff = self.root / "change.diff"
        self.diff.write_text("diff --git a/A.java b/A.java\n")

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_state(self, *args, payload=None, by=None, expect_ok=True):
        command = [sys.executable, str(SCRIPT), str(self.review), *args] + (["--by", by] if by else [])
        done = subprocess.run(command, input=None if payload is None else json.dumps(payload),
                              capture_output=True, text=True, timeout=30)
        if expect_ok:
            self.assertEqual(done.returncode, 0, done.stderr)
        else:
            self.assertNotEqual(done.returncode, 0, "expected a refusal, got: " + done.stdout)
        return done

    def state(self):
        return json.loads((self.review / "review.json").read_text())

    def opened(self):
        self.run_state("init", payload={"source": SOURCE, "base": "aaa", "head": "bbb", "diff": str(self.diff)})

    def test_init_creates_the_state_and_keeps_the_diff_under_the_head_commit(self):
        self.opened()

        state = self.state()
        self.assertEqual(state["source"], SOURCE)
        self.assertEqual((state["base"], state["head"]), ("aaa", "bbb"))
        self.assertEqual(state["findings"], [])
        self.assertEqual((self.review / "diff" / "bbb.diff").read_text(), self.diff.read_text())

    def test_a_review_in_progress_is_never_overwritten_by_init(self):
        self.opened()
        self.run_state("add-finding", payload=finding())

        refused = self.run_state("init", payload={"source": SOURCE, "base": "x", "head": "y", "diff": str(self.diff)},
                                 expect_ok=False)

        self.assertIn("already", refused.stderr)
        self.assertEqual(len(self.state()["findings"]), 1)

    def test_findings_get_ids_in_order_and_start_proposed(self):
        self.opened()

        first = self.run_state("add-finding", payload=finding()).stdout.strip()
        second = self.run_state("add-finding", payload=finding(title="Other")).stdout.strip()

        self.assertEqual((first, second), ("f1", "f2"))
        self.assertEqual([f["status"] for f in self.state()["findings"]], ["proposed", "proposed"])

    def test_a_finding_of_an_unknown_kind_is_refused(self):
        self.opened()

        self.run_state("add-finding", payload=finding(kind="opinion"), expect_ok=False)

        self.assertEqual(self.state()["findings"], [])

    def test_an_out_of_scope_finding_must_say_now_or_later(self):
        self.opened()

        self.run_state("add-finding", payload=finding(kind="out-of-scope"), expect_ok=False)
        self.run_state("add-finding", payload=finding(kind="out-of-scope", when="later"))

        self.assertEqual(self.state()["findings"][0]["when"], "later")

    def test_the_developers_edit_is_recorded_and_the_agent_cannot_change_it_back(self):
        self.opened()
        self.run_state("add-finding", payload=finding())

        self.run_state("update-finding", "f1", payload={"comment": "My words."}, by="developer")
        self.run_state("update-finding", "f1", payload={"comment": "Agent words."}, by="agent", expect_ok=False)
        self.run_state("update-finding", "f1", payload={"title": "Agent title"}, by="agent")

        found = self.state()["findings"][0]
        self.assertEqual(found["comment"], "My words.")
        self.assertEqual(found["edited"], ["comment"])
        self.assertEqual(found["title"], "Agent title")

    def test_a_sent_finding_is_final(self):
        self.opened()
        self.run_state("add-finding", payload=finding())
        self.run_state("set-status", "f1", payload={"status": "to-send"}, by="developer")
        self.run_state("mark-sent", "f1", payload={"sent": [{"location": 0, "url": "https://github.com/c/1"}]})

        self.run_state("update-finding", "f1", payload={"title": "Later"}, by="developer", expect_ok=False)
        self.run_state("set-status", "f1", payload={"status": "deleted"}, by="developer", expect_ok=False)

        found = self.state()["findings"][0]
        self.assertEqual(found["status"], "sent")
        self.assertEqual(found["sent"][0]["url"], "https://github.com/c/1")

    def test_only_a_finding_marked_to_send_can_be_sent(self):
        self.opened()
        self.run_state("add-finding", payload=finding())

        self.run_state("mark-sent", "f1", payload={"sent": [{"location": 0, "url": "u"}]}, expect_ok=False)

        self.assertEqual(self.state()["findings"][0]["status"], "proposed")

    def test_replies_to_a_sent_comment_are_recorded_under_it(self):
        self.opened()
        self.run_state("add-finding", payload=finding())
        self.run_state("set-status", "f1", payload={"status": "to-send"}, by="developer")
        self.run_state("mark-sent", "f1", payload={"sent": [{"location": 0, "url": "u"}]})

        self.run_state("add-replies", "f1", payload={"location": 0, "replies": [
            {"author": "anna", "at": "2026-10-30T10:00:00Z", "body": "Fixed."}]})

        self.assertEqual(self.state()["findings"][0]["sent"][0]["replies"][0]["body"], "Fixed.")

    def test_deleting_and_resolving_are_the_developers_and_the_agent_only_suggests(self):
        self.opened()
        self.run_state("add-finding", payload=finding())
        self.run_state("add-finding", payload=finding(title="Second"))

        self.run_state("set-status", "f1", payload={"status": "deleted"}, by="agent", expect_ok=False)
        self.run_state("set-status", "f1", payload={"status": "maybe-resolved"}, by="agent")
        self.run_state("set-status", "f2", payload={"status": "deleted"}, by="developer")

        self.assertEqual([f["status"] for f in self.state()["findings"]], ["maybe-resolved", "deleted"])

    def test_a_merged_finding_names_an_existing_finding_it_went_into(self):
        self.opened()
        self.run_state("add-finding", payload=finding())
        self.run_state("add-finding", payload=finding())

        self.run_state("set-status", "f2", payload={"status": "merged", "merged-into": "f9"}, expect_ok=False)
        self.run_state("set-status", "f2", payload={"status": "merged", "merged-into": "f1"})

        self.assertEqual(self.state()["findings"][1]["merged-into"], "f1")

    def test_the_agent_sets_the_understanding_but_not_an_unknown_field(self):
        self.opened()

        self.run_state("set", payload={"scope": "Cancels a reservation.", "language": "English"})
        self.run_state("set", payload={"findings": []}, expect_ok=False)

        self.assertEqual(self.state()["scope"], "Cancels a reservation.")
        self.assertEqual(self.state()["language"], "English")

    def test_explanations_are_added_pending_and_finished_later(self):
        self.opened()

        explanation = self.run_state("add-explanation", payload={"about": {"kind": "file", "id": "A.java"},
                                                                 "origin": "requested"}).stdout.strip()
        self.run_state("update-explanation", explanation, payload={"body": "It retries.", "status": "ready"})

        self.assertEqual(self.state()["explanations"][0], {"id": "e1", "about": {"kind": "file", "id": "A.java"},
                                                           "origin": "requested", "body": "It retries.",
                                                           "status": "ready"})

    def test_a_handled_inbox_message_is_remembered(self):
        self.opened()

        self.run_state("handled", "m3")

        self.assertEqual(self.state()["handled"], ["m3"])

    def test_a_checkpoint_answer_comes_from_the_developer(self):
        self.opened()
        self.run_state("set", payload={"checkpoint": {"id": "c1", "step": "read-pr-scope", "question": "Scope?",
                                                      "options": ["right", "correct"], "answer": None}})

        self.run_state("answer", payload={"option": "right", "note": None}, by="agent", expect_ok=False)
        self.run_state("answer", payload={"option": "right", "note": None}, by="developer")

        self.assertEqual(self.state()["checkpoint"]["answer"], {"option": "right", "note": None, "by": "developer"})

    def test_two_writers_at_once_lose_nothing(self):
        self.opened()
        command = [sys.executable, str(SCRIPT), str(self.review), "add-finding"]
        writers = [subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True) for _ in range(12)]
        for writer in writers:
            writer.stdin.write(json.dumps(finding()))
            writer.stdin.close()
        for writer in writers:
            with writer:
                errors = writer.stderr.read()
                self.assertEqual(writer.wait(timeout=30), 0, errors)

        ids = [f["id"] for f in self.state()["findings"]]
        self.assertEqual(sorted(ids, key=lambda i: int(i[1:])), [f"f{n}" for n in range(1, 13)])


if __name__ == "__main__":
    unittest.main()
