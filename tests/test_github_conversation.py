"""Tests for github_conversation.py: reading what everyone wrote on the pull request -- its conversation, the reviews
and the threads on the code -- so the review page shows it beside the developer's own comments. A fake `gh`
(fake_gh.py) answers like GitHub's REST API.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import github_conversation  # noqa: E402
import review_state  # noqa: E402

PULL = {"kind": "pull-request", "url": "https://github.com/org/booking/pull/123", "repository": "org/booking",
        "number": 123}
ON_GITHUB = {
    "issue_comments": [{"id": 501, "user": {"login": "anna"}, "created_at": "2026-10-30T09:00:00Z",
                        "body": "Please add the ticket.", "html_url": "https://github.com/org/booking/pull/123#issuecomment-1"}],
    "review_list": [
        {"id": 31, "user": {"login": "olek"}, "submitted_at": "2026-10-30T11:00:00Z", "state": "CHANGES_REQUESTED",
         "body": "Two things before it goes in.", "html_url": "https://github.com/org/booking/pull/123#pullrequestreview-31"},
        {"id": 32, "user": {"login": "olek"}, "submitted_at": "2026-10-30T11:05:00Z", "state": "COMMENTED", "body": "",
         "html_url": "https://github.com/org/booking/pull/123#pullrequestreview-32"}],
    "comments": [
        {"id": 77, "user": {"login": "olek"}, "created_at": "2026-10-30T10:00:00Z", "path": "src/Cancel.java", "line": 2,
         "side": "RIGHT", "body": "Why a string?", "html_url": "https://github.com/org/booking/pull/123#discussion_r77"},
        {"id": 78, "in_reply_to_id": 77, "user": {"login": "anna"}, "created_at": "2026-10-30T10:30:00Z",
         "path": "src/Cancel.java", "line": 2, "side": "RIGHT", "body": "It comes from the URL.",
         "html_url": "https://github.com/org/booking/pull/123#discussion_r78"},
        {"id": 79, "user": {"login": "olek"}, "created_at": "2026-10-30T10:40:00Z", "path": "src/Old.java", "line": None,
         "original_line": 9, "side": "RIGHT", "body": "Outdated now.",
         "html_url": "https://github.com/org/booking/pull/123#discussion_r79"}],
}


class ConversationTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.review = self.root / "pr-123"
        os.environ.update(FAKE_GH_LOG=str(self.root / "gh.log"), FAKE_GH_STATE=str(self.root / "gh.json"))
        os.environ.pop("FAKE_GH_FAIL", None)
        self.gh = [sys.executable, str(TESTS / "fake_gh.py")]
        (self.root / "gh.json").write_text(json.dumps(ON_GITHUB))

    def tearDown(self):
        os.environ.pop("FAKE_GH_FAIL", None)
        shutil.rmtree(self.root)

    def opened(self, source=PULL):
        diff = self.root / "change.diff"
        diff.write_text("diff --git a/src/Cancel.java b/src/Cancel.java\n")
        review_state.change(self.review, "init", {"source": source, "base": "aaa", "head": "bbb", "diff": str(diff)})

    def test_everything_said_on_the_pull_request_is_read_in_the_order_it_was_said(self):
        self.opened()

        conversation = github_conversation.fetch(self.review, gh=self.gh)

        self.assertEqual([(c["kind"], c["id"]) for c in conversation["comments"]],
                         [("issue", 501), ("inline", 77), ("inline", 78), ("inline", 79), ("review", 31)])
        self.assertIsNone(conversation["error"])
        self.assertTrue(conversation["fetched"])

    def test_each_comment_says_who_wrote_it_when_and_where_it_is_on_github(self):
        self.opened()

        issue = github_conversation.fetch(self.review, gh=self.gh)["comments"][0]

        self.assertEqual(issue, {"id": 501, "kind": "issue", "author": "anna", "at": "2026-10-30T09:00:00Z",
                                 "body": "Please add the ticket.",
                                 "url": "https://github.com/org/booking/pull/123#issuecomment-1"})

    def test_a_comment_on_the_code_names_its_line_and_the_thread_it_belongs_to(self):
        self.opened()

        comments = {c["id"]: c for c in github_conversation.fetch(self.review, gh=self.gh)["comments"]}

        self.assertEqual({key: comments[78][key] for key in ("path", "line", "side", "root")},
                         {"path": "src/Cancel.java", "line": 2, "side": "RIGHT", "root": 77})
        self.assertEqual(comments[77]["root"], 77)
        self.assertEqual((comments[79]["line"], comments[79]["original-line"]), (None, 9))

    def test_a_review_shows_with_what_it_decided_and_an_empty_one_only_when_it_decided_something(self):
        self.opened()

        reviews = [c for c in github_conversation.fetch(self.review, gh=self.gh)["comments"] if c["kind"] == "review"]

        self.assertEqual([(r["id"], r["state"], r["author"]) for r in reviews], [(31, "CHANGES_REQUESTED", "olek")])

    def test_the_conversation_is_kept_beside_the_review_and_read_back(self):
        self.opened()
        fetched = github_conversation.fetch(self.review, gh=self.gh)

        self.assertEqual(github_conversation.read(self.review), fetched)
        self.assertTrue((self.review / "github.json").is_file())

    def test_a_failure_keeps_what_was_read_before_and_says_why(self):
        self.opened()
        before = github_conversation.fetch(self.review, gh=self.gh)
        os.environ["FAKE_GH_FAIL"] = "1"

        after = github_conversation.fetch(self.review, gh=self.gh)

        self.assertEqual((after["comments"], after["fetched"]), (before["comments"], before["fetched"]))
        self.assertIn("422", after["error"])

    def test_a_review_of_two_branches_has_no_conversation(self):
        self.opened({"kind": "branches", "target": "main", "source": "feature/x", "pull-request": None})

        with self.assertRaises(review_state.Refused):
            github_conversation.fetch(self.review, gh=self.gh)
        self.assertIsNone(github_conversation.read(self.review))

    def run_script(self):
        return subprocess.run([sys.executable, str(SCRIPTS / "github_conversation.py"), str(self.review)],
                              capture_output=True, text=True, timeout=30,
                              env={**os.environ, "CRAFTSMAN_GH": " ".join(self.gh)})

    def test_the_agent_reads_the_conversation_again_from_the_command_line(self):
        self.opened()

        done = self.run_script()

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), {"file": str(self.review / "github.json"), "comments": 5,
                                                   "error": None})
        self.assertEqual(len(github_conversation.read(self.review)["comments"]), 5)

    def test_the_command_line_says_when_github_did_not_answer(self):
        self.opened()
        os.environ["FAKE_GH_FAIL"] = "1"

        done = self.run_script()

        self.assertEqual(done.returncode, 1)
        self.assertIn("422", json.loads(done.stdout)["error"])

    def test_the_command_line_refuses_a_review_without_a_pull_request(self):
        self.opened({"kind": "branches", "target": "main", "source": "feature/x", "pull-request": None})

        done = self.run_script()

        self.assertEqual(done.returncode, 1)
        self.assertIn("refused", done.stderr)


if __name__ == "__main__":
    unittest.main()
