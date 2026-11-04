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
            "directive": "naming", "kind": "violation", "severity": "should-fix"}
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
        command = [sys.executable, str(SCRIPT), str(self.review), *args] + (
            [] if payload is None else [json.dumps(payload)]) + (["--by", by] if by else [])
        done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
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

    def test_a_diff_written_into_the_review_folder_is_moved_not_left_behind(self):
        self.review.mkdir(parents=True)
        written = self.review / "init.diff"
        written.write_text("diff --git a/B.java b/B.java\n")

        self.run_state("init", payload={"source": SOURCE, "base": "aaa", "head": "bbb", "diff": str(written)})

        self.assertFalse(written.exists())
        self.assertEqual((self.review / "diff" / "bbb.diff").read_text(), "diff --git a/B.java b/B.java\n")

    def test_a_diff_from_elsewhere_is_copied_and_left_alone(self):
        self.opened()

        self.assertTrue(self.diff.exists())

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

    def test_a_sent_finding_keeps_the_link_of_each_comment_and_nothing_more(self):
        self.opened()
        self.run_state("add-finding", payload=finding())
        self.run_state("set-status", "f1", payload={"status": "to-send"}, by="developer")

        self.run_state("mark-sent", "f1", payload={"sent": [{"location": 0, "url": "u"}]})

        self.assertEqual(self.state()["findings"][0]["sent"], [{"location": 0, "url": "u"}])

    def test_the_developer_writes_comments_on_the_whole_pull_request_that_wait_for_send(self):
        self.opened()

        self.assertEqual(self.run_state("add-comment", payload={"body": "Thanks, looks good."}, by="developer")
                         .stdout.strip(), "c1")
        self.run_state("add-comment", payload={"body": "Agreed.", "reply-to": 4711}, by="developer")

        first, second = self.state()["comments"]
        self.assertEqual((first["id"], first["body"], first["status"], first["reply-to"]),
                         ("c1", "Thanks, looks good.", "to-send", None))
        self.assertEqual((second["id"], second["reply-to"]), ("c2", 4711))

    def test_a_comment_needs_text_and_is_the_developers(self):
        self.opened()

        self.run_state("add-comment", payload={"body": "  "}, by="developer", expect_ok=False)
        self.run_state("add-comment", payload={"body": "From the agent."}, expect_ok=False)
        self.run_state("add-comment", payload={"body": "x", "reply-to": "abc"}, by="developer", expect_ok=False)

        self.assertEqual(self.state()["comments"], [])

    def test_the_developer_edits_or_drops_a_comment_until_it_is_sent(self):
        self.opened()
        self.run_state("add-comment", payload={"body": "Draft"}, by="developer")

        self.run_state("update-comment", "c1", payload={"body": "Better"}, by="developer")
        self.run_state("comment-status", "c1", payload={"status": "deleted"}, by="developer")
        self.run_state("comment-status", "c1", payload={"status": "to-send"}, by="developer")
        self.run_state("comment-sent", "c1", payload={"url": "https://github.com/org/booking/pull/123#issuecomment-1"})

        comment = self.state()["comments"][0]
        self.assertEqual((comment["body"], comment["status"], comment["url"]),
                         ("Better", "sent", "https://github.com/org/booking/pull/123#issuecomment-1"))
        self.run_state("update-comment", "c1", payload={"body": "Again"}, by="developer", expect_ok=False)
        self.run_state("comment-status", "c1", payload={"status": "deleted"}, by="developer", expect_ok=False)
        self.run_state("update-comment", "c1", payload={"body": "Agent"}, expect_ok=False)

    def test_only_a_comment_waiting_for_send_is_sent(self):
        self.opened()
        self.run_state("add-comment", payload={"body": "Draft"}, by="developer")
        self.run_state("comment-status", "c1", payload={"status": "deleted"}, by="developer")

        self.run_state("comment-sent", "c1", payload={"url": "u"}, expect_ok=False)

        self.assertEqual(self.state()["comments"][0]["status"], "deleted")

    def test_a_review_started_before_comments_existed_takes_them(self):
        self.opened()
        state = self.state()
        del state["comments"]
        (self.review / "review.json").write_text(json.dumps(state))

        self.run_state("add-comment", payload={"body": "Hi"}, by="developer")

        self.assertEqual([c["id"] for c in self.state()["comments"]], ["c1"])

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

    def test_a_finding_says_how_serious_it_is_and_who_found_it(self):
        self.opened()

        self.run_state("add-finding", payload=finding(severity=None), expect_ok=False)
        self.run_state("add-finding", payload=finding(severity="blocker"), expect_ok=False)
        self.run_state("add-finding", payload=finding(severity="must-fix"))

        found = self.state()["findings"][0]
        self.assertEqual((found["severity"], found["by"]), ("must-fix", "agent"))

    def test_the_developer_adds_a_finding_of_their_own(self):
        self.opened()

        added = self.run_state("add-finding", by="developer", payload={
            "title": "A refusal should be a result", "comment": "Return a result instead of throwing.",
            "locations": [{"path": "A.java", "line": 22, "side": "RIGHT", "commit": "bbb"}],
            "severity": "should-fix"}).stdout.strip()

        found = self.state()["findings"][0]
        self.assertEqual(added, "f1")
        self.assertEqual((found["by"], found["kind"], found["category"], found["status"]),
                         ("developer", "violation", "yours", "proposed"))

    def test_the_developer_changes_how_serious_a_finding_is_and_the_agent_keeps_it(self):
        self.opened()
        self.run_state("add-finding", payload=finding())

        self.run_state("update-finding", "f1", payload={"severity": "nit"}, by="developer")
        self.run_state("update-finding", "f1", payload={"severity": "must-fix"}, by="agent", expect_ok=False)
        self.run_state("update-finding", "f1", payload={"severity": "huge"}, by="developer", expect_ok=False)

        found = self.state()["findings"][0]
        self.assertEqual((found["severity"], found["edited"]), ("nit", ["severity"]))

    def test_the_developer_marks_the_files_they_have_viewed(self):
        self.opened()

        self.run_state("view", payload={"path": "A.java"}, by="developer")
        self.run_state("view", payload={"path": "B.java"}, by="developer")
        self.run_state("view", payload={"path": "A.java"}, by="developer")
        self.run_state("unview", payload={"path": "B.java"}, by="developer")
        self.run_state("view", payload={"path": "C.java"}, expect_ok=False)

        self.assertEqual(self.state()["viewed"], ["A.java"])

    def test_a_thread_starts_with_a_question_and_collects_the_answers(self):
        self.opened()
        self.run_state("add-finding", payload=finding())

        thread = self.run_state("open-thread", by="developer", payload={
            "about": {"kind": "finding", "id": "f1"}, "quote": "straight into the SQL text",
            "text": "Is the id validated anywhere?"}).stdout.strip()
        self.run_state("reply", thread, payload={"text": "No, nothing checks it."})
        self.run_state("resolve", thread, by="agent", expect_ok=False)
        self.run_state("resolve", thread, by="developer")

        opened = self.state()["threads"][0]
        self.assertEqual((opened["id"], opened["status"], opened["quote"]), ("t1", "resolved",
                                                                             "straight into the SQL text"))
        self.assertEqual([(m["by"], m["text"]) for m in opened["messages"]],
                         [("developer", "Is the id validated anywhere?"), ("agent", "No, nothing checks it.")])
        self.assertTrue(all(m["at"] for m in opened["messages"]))

    def test_a_resolved_thread_opens_again_when_the_developer_asks_more(self):
        self.opened()
        self.run_state("open-thread", by="developer", payload={"about": {"kind": "review"}, "text": "Why now?"})
        self.run_state("resolve", "t1", by="developer")

        self.run_state("reply", "t1", by="developer", payload={"text": "One more thing."})

        self.assertEqual(self.state()["threads"][0]["status"], "open")

    def test_a_thread_is_about_something_the_review_knows(self):
        self.opened()

        self.run_state("open-thread", payload={"about": {"kind": "finding", "id": "f9"}, "text": "?"}, expect_ok=False)
        self.run_state("open-thread", payload={"about": {"kind": "file"}, "text": "?"}, expect_ok=False)
        self.run_state("open-thread", payload={"about": {"kind": "weather"}, "text": "?"}, expect_ok=False)
        self.run_state("open-thread", payload={"about": {"kind": "file", "path": "A.java"}}, expect_ok=False)
        self.run_state("open-thread", payload={"about": {"kind": "file", "path": "A.java", "lines": [22, 23]},
                                               "text": "Unasked: this is the only owner check."})

        self.assertEqual(self.state()["threads"][0]["messages"][0]["by"], "agent")

    def test_use_cases_say_what_they_do_and_how_they_run(self):
        self.opened()
        use_case = {"id": "u1", "name": "Cancel a reservation", "says": "The owner cancels their reservation.",
                    "entry": "CancelController.java:22", "files": ["CancelController.java"], "status": "pending",
                    "flow": {"steps": [{"call": "CancelController.cancel()", "path": "CancelController.java",
                                        "line": 22, "change": "added", "crosses": None}],
                             "branches": [{"what": "not the owner → refused", "tested": True}]}}

        self.run_state("set", payload={"structure": {"use-cases": [{**use_case, "says": None}]}}, expect_ok=False)
        self.run_state("set", payload={"structure": {"use-cases": [{**use_case, "flow": {
            "steps": [{**use_case["flow"]["steps"][0], "change": "rewritten"}], "branches": []}}]}}, expect_ok=False)
        self.run_state("set", payload={"structure": {"use-cases": [use_case]}})
        self.run_state("set", payload={"map": []}, expect_ok=False)

        self.assertEqual(self.state()["structure"]["use-cases"][0]["flow"]["branches"][0]["tested"], True)

    def test_a_use_case_says_how_things_were_and_how_they_will_be(self):
        self.opened()
        use_case = {"id": "u1", "name": "Cancel a reservation", "says": "The owner cancels.", "entry": "A.java:1",
                    "files": ["A.java"], "before": "A reservation cannot be cancelled.",
                    "after": "The owner cancels up to an hour before the start; billing refunds in full."}

        self.run_state("set", payload={"structure": {"use-cases": [{**use_case, "before": ["not text"]}]}},
                       expect_ok=False)
        self.run_state("set", payload={"structure": {"use-cases": [use_case]}})

        stored = self.state()["structure"]["use-cases"][0]
        self.assertEqual((stored["before"], stored["after"]), (use_case["before"], use_case["after"]))

    def test_a_flow_step_says_where_it_is_called_from(self):
        self.opened()
        step = {"call": "ReservationRepository.save", "path": "R.java", "line": 11, "change": "unchanged",
                "from": {"path": "S.java", "line": 35}}
        use_case = {"id": "u1", "name": "Cancel", "says": "The owner cancels.", "entry": "S.java:25",
                    "files": ["S.java"], "flow": {"steps": [step], "branches": []}}

        for wrong in ({"path": "S.java"}, {"path": "S.java", "line": "35"}, "S.java:35"):
            self.run_state("set", payload={"structure": {"use-cases": [
                {**use_case, "flow": {"steps": [{**step, "from": wrong}], "branches": []}}]}}, expect_ok=False)
        self.run_state("set", payload={"structure": {"use-cases": [use_case]}})

        self.assertEqual(self.state()["structure"]["use-cases"][0]["flow"]["steps"][0]["from"],
                         {"path": "S.java", "line": 35})

    def test_the_developer_archives_a_review(self):
        self.opened()

        self.run_state("archive", payload={"archived": True}, expect_ok=False)
        self.run_state("archive", payload={"archived": True}, by="developer")

        self.assertTrue(self.state()["archived"])

    def test_a_handled_inbox_message_is_remembered_without_waiting_for_input(self):
        self.opened()

        with subprocess.Popen([sys.executable, str(SCRIPT), str(self.review), "handled", "m3"], text=True,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as caller:
            try:
                self.assertEqual(caller.wait(timeout=10), 0, caller.stderr.read())
            finally:
                caller.kill()

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
        command = [sys.executable, str(SCRIPT), str(self.review), "add-finding", json.dumps(finding())]
        writers = [subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True) for _ in range(12)]
        for writer in writers:
            with writer:
                errors = writer.stderr.read()
                self.assertEqual(writer.wait(timeout=30), 0, errors)

        ids = [f["id"] for f in self.state()["findings"]]
        self.assertEqual(sorted(ids, key=lambda i: int(i[1:])), [f"f{n}" for n in range(1, 13)])


if __name__ == "__main__":
    unittest.main()
