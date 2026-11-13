"""Tests for opening a review on the dashboard server -- see REVIEW.md, "Opening a review". The server reads the pull
request or the two branches, fetches what is reviewed, makes the review's worktree and diff, and writes the review
state, before the review's session starts; none of it needs the model. Real git repositories, a fake `gh`.

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
import _open_review  # noqa: E402
import review_state  # noqa: E402
from review_state import Refused  # noqa: E402

GH = [sys.executable, str(TESTS / "fake_gh.py")]
PR = "https://github.com/org/booking/pull/123"


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


class RepositoryCase(unittest.TestCase):
    """The developer's checkout of org/booking: `main` moved on after `feature/x` branched off; pull request 123 has
    `feature/x` as its head, kept on origin as `refs/pull/123/head` only."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        work = self.tmp / "work"
        work.mkdir()
        git(work, "init", "-q", "-b", "main")
        git(work, "config", "user.email", "dev@example.com")
        git(work, "config", "user.name", "dev")
        (work / "Booking.java").write_text("class Booking {}\n")
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", "Book a desk")
        self.base = git(work, "rev-parse", "HEAD")
        git(work, "checkout", "-q", "-b", "feature/x")
        (work / "Cancel.java").write_text("class Cancel {}\n")
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", "Cancel a reservation")
        self.head = git(work, "rev-parse", "HEAD")
        git(work, "checkout", "-q", "main")
        (work / "Later.java").write_text("class Later {}\n")
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", "Main moves on")
        self.origin = self.tmp / "github" / "org" / "booking.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(work), str(self.origin)], check=True, capture_output=True)
        git(self.origin, "update-ref", "refs/pull/123/head", self.head)
        git(self.origin, "branch", "-D", "feature/x")  # the PR's branch lives on in its pull ref only
        self.checkout = self.tmp / "booking"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.checkout)], check=True, capture_output=True)
        git(self.checkout, "remote", "set-url", "origin", "https://github.com/org/booking.git")
        git(self.checkout, "config", f"url.file://{self.tmp / 'github'}/.insteadOf", "https://github.com/")
        self.review = self.tmp / "home" / "reviews" / "org-booking-pr-123"
        self.state = self.tmp / "gh-state.json"
        self.log = self.tmp / "gh-log.jsonl"
        self.state.write_text(json.dumps({"pulls": {"123": {
            "number": 123, "title": "Cancel a reservation", "body": "Lets an employee cancel.", "state": "open",
            "html_url": PR, "base": {"ref": "main"}, "head": {"ref": "feature/x", "sha": self.head,
                                                                 "label": "org:feature/x"}}}}))
        self.saved = {key: os.environ.get(key) for key in ("FAKE_GH_STATE", "FAKE_GH_LOG", "FAKE_GH_FAIL")}
        os.environ.update(FAKE_GH_STATE=str(self.state), FAKE_GH_LOG=str(self.log))
        os.environ.pop("FAKE_GH_FAIL", None)
        self.addCleanup(self.restore_env)

    def restore_env(self):
        for key, value in self.saved.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)



class OpenReviewTest(RepositoryCase):
    def open(self, source=PR, checkout=None):
        return _open_review.open_review(self.review, source, checkout or self.checkout, gh=GH)

    def test_a_pull_request_is_opened_at_its_head_against_where_it_branched(self):
        self.open()
        state = review_state.read(self.review)
        self.assertEqual(state["source"], {"kind": "pull-request", "url": PR, "repository": "org/booking",
                                           "number": 123, "title": "Cancel a reservation", "base-branch": "main",
                                           "head-branch": "feature/x"})
        self.assertEqual((state["base"], state["head"], state["checkout"]), (self.base, self.head, str(self.checkout)))
        diff = (self.review / "diff" / f"{self.head}.diff").read_text()
        self.assertIn("Cancel.java", diff)
        self.assertNotIn("Later.java", diff, "the diff is what the PR adds, not what main did since")
        self.assertEqual(git(self.review / "worktree", "rev-parse", "HEAD"), self.head)

    def test_the_developers_own_checkout_is_left_as_it_was(self):
        (self.checkout / "wip.txt").write_text("half done")
        before = (git(self.checkout, "rev-parse", "--abbrev-ref", "HEAD"), git(self.checkout, "status", "--short"))
        self.open()
        self.assertEqual((git(self.checkout, "rev-parse", "--abbrev-ref", "HEAD"),
                          git(self.checkout, "status", "--short")), before)

    def test_two_branches_are_opened_and_attached_to_the_open_pull_request_of_the_source(self):
        git(self.checkout, "branch", "feature/x", self.head)
        self.open("main:feature/x")
        state = review_state.read(self.review)
        self.assertEqual(state["source"]["kind"], "branches")
        self.assertEqual((state["source"]["target"], state["source"]["source"]), ("main", "feature/x"))
        self.assertEqual(state["source"]["pull-request"]["number"], 123)
        self.assertEqual((state["base"], state["head"]), (self.base, self.head))

    def test_the_branch_the_developer_has_wins_over_the_one_on_origin(self):
        git(self.origin, "branch", "feature/y", self.head)
        git(self.checkout, "fetch", "-q", "origin")
        git(self.checkout, "checkout", "-q", "-b", "feature/y", "origin/feature/y")
        (self.checkout / "Local.java").write_text("class Local {}\n")
        git(self.checkout, "add", ".")
        git(self.checkout, "-c", "user.email=dev@example.com", "-c", "user.name=dev", "commit", "-q", "-m",
            "Not pushed")
        local = git(self.checkout, "rev-parse", "HEAD")
        git(self.checkout, "checkout", "-q", "main")
        self.open("main:feature/y")
        self.assertEqual(review_state.read(self.review)["head"], local)

    def test_two_branches_without_a_pull_request_are_reviewed_without_one(self):
        self.state.write_text(json.dumps({"pulls": {}}))
        git(self.checkout, "branch", "feature/x", self.head)
        self.open("main:feature/x")
        self.assertIsNone(review_state.read(self.review)["source"]["pull-request"])

    def test_a_branch_that_does_not_exist_is_refused_by_name(self):
        with self.assertRaises(Refused) as refused:
            self.open("main:feature/nowhere")
        self.assertIn("feature/nowhere", str(refused.exception))
        self.assertFalse((self.review / "review.json").exists())

    def test_a_pull_request_github_does_not_know_is_refused_with_githubs_answer(self):
        with self.assertRaises(Refused) as refused:
            self.open("https://github.com/org/booking/pull/999")
        self.assertIn("404", str(refused.exception))
        self.assertFalse((self.review / "worktree").exists())

    def test_a_review_already_opened_is_left_as_it_is(self):
        self.open()
        review_state.change(self.review, "set", {"scope": "Cancels a reservation."})
        calls = len(self.log.read_text().splitlines())
        self.open()
        self.assertEqual(review_state.read(self.review)["scope"], "Cancels a reservation.")
        self.assertEqual(len(self.log.read_text().splitlines()), calls, "nothing is read again")

    def test_github_is_asked_on_the_pull_requests_own_host(self):
        self.open()
        self.assertEqual({json.loads(line)["host"] for line in self.log.read_text().splitlines()}, {"github.com"})


if __name__ == "__main__":
    unittest.main()
