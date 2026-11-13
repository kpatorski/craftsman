"""Tests for refresh_review.py, the mechanical part of bringing a review up to date with its pull request -- see
REVIEW.md, "Refreshing a review". It fetches, moves the worktree and the review state to the new head, puts the use
cases the new commits touched back to pending, reads the conversation again, and prints what the agent weighs next.
Real git repositories, a fake `gh`.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_open_review import GH, PR, RepositoryCase, git  # noqa: E402

import _open_review  # noqa: E402
import refresh_review  # noqa: E402
import review_state  # noqa: E402

STRUCTURE = {"use-cases": [
    {"id": "u1", "name": "Cancel a reservation", "says": "An employee cancels.", "entry": "Cancel.java:1",
     "files": ["Cancel.java"], "status": "reviewed"},
    {"id": "u2", "name": "Book a desk", "says": "An employee books.", "entry": "Booking.java:1",
     "files": ["Booking.java"], "status": "reviewed"},
]}


class RefreshReviewTest(RepositoryCase):
    """The repository and pull request of test_open_review; the review is opened, then the author pushes."""

    def setUp(self):
        super().setUp()
        _open_review.open_review(self.review, PR, self.checkout, gh=GH)
        review_state.change(self.review, "set", {"structure": STRUCTURE, "refreshed": "2026-11-01T10:00:00+00:00"})

    def push(self, files):
        """The author pushes one commit onto the pull request."""
        work = self.tmp / "author"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(work)], check=True, capture_output=True)
        git(work, "config", "user.email", "author@example.com")
        git(work, "config", "user.name", "author")
        git(work, "fetch", "-q", "origin", "refs/pull/123/head")
        git(work, "checkout", "-q", "FETCH_HEAD")
        for name, text in files.items():
            (work / name).write_text(text)
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", "Address the review")
        new_head = git(work, "rev-parse", "HEAD")
        git(work, "push", "-q", "origin", "HEAD:refs/pull/123/head")
        state = json.loads(self.state.read_text())
        state["pulls"]["123"]["head"]["sha"] = new_head
        state["pulls"]["123"]["body"] = "Lets an employee cancel, and says why."
        self.state.write_text(json.dumps(state))
        return new_head

    def refresh(self):
        return refresh_review.refresh(self.review, gh=GH)

    def test_the_review_moves_to_the_new_head_and_the_touched_use_cases_go_back_to_pending(self):
        new_head = self.push({"Cancel.java": "class Cancel { void cancel() {} }\n", "Audit.java": "class Audit {}\n"})
        report = self.refresh()
        state = review_state.read(self.review)
        self.assertEqual((state["head"], state["base"]), (new_head, self.base))
        self.assertEqual(git(self.review / "worktree", "rev-parse", "HEAD"), new_head)
        self.assertIn("Audit.java", (self.review / "diff" / f"{new_head}.diff").read_text())
        statuses = {u["id"]: u["status"] for u in state["structure"]["use-cases"]}
        self.assertEqual(statuses, {"u1": "pending", "u2": "reviewed"})
        self.assertEqual((report["moved"], report["old-head"], report["head"], report["commits"]),
                         (True, self.head, new_head, 1))
        self.assertEqual(report["changed-files"], ["Audit.java", "Cancel.java"])
        self.assertEqual((report["back-to-pending"], report["unplaced"]), (["u1"], ["Audit.java"]))
        self.assertEqual(report["description"], "Lets an employee cancel, and says why.")

    def test_without_new_commits_only_the_time_of_the_refresh_is_recorded(self):
        report = self.refresh()
        state = review_state.read(self.review)
        self.assertFalse(report["moved"])
        self.assertEqual(state["head"], self.head)
        self.assertNotEqual(state["refreshed"], "2026-11-01T10:00:00+00:00")
        self.assertEqual({u["id"]: u["status"] for u in state["structure"]["use-cases"]},
                         {"u1": "reviewed", "u2": "reviewed"})

    def test_the_conversation_is_read_again_and_only_what_came_since_the_last_refresh_is_new(self):
        state = json.loads(self.state.read_text())
        state["issue_comments"] = [{"id": 0, "body": "Looks big.", "user": {"login": "lead"},
                                    "created_at": "2026-10-30T09:00:00Z", "html_url": f"{PR}#issuecomment-0"},
                                   {"id": 1, "body": "Rebased.", "user": {"login": "author"},
                                    "created_at": "2026-11-02T09:00:00Z", "html_url": f"{PR}#issuecomment-1"}]
        self.state.write_text(json.dumps(state))
        report = self.refresh()
        self.assertEqual(report["github"], {"error": None, "new": 1})
        self.assertTrue((self.review / "github.json").is_file())

    def test_the_command_line_prints_the_report_as_json(self):
        done = subprocess.run([sys.executable, str(refresh_review.__file__), str(self.review)], capture_output=True,
                              text=True, env=dict(os.environ, CRAFTSMAN_GH=" ".join(GH)))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(json.loads(done.stdout)["moved"])


if __name__ == "__main__":
    unittest.main()
