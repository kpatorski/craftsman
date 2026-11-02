"""Tests for _checkout.py: where a review reads the repository from -- a checkout the developer names (typed, or
picked in the system's folder dialog), or a partial clone the dashboard server makes in /tmp -- see REVIEW.md.

Run: python3 -m unittest discover -s tests
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "plugins" / "craftsman" / "scripts"))
import _checkout as checkout  # noqa: E402
import review_state  # noqa: E402

PULL = "https://github.com/org/booking/pull/123"


def git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class CheckoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.repo = self.tmp / "booking"
        git("init", "-q", "-b", "main", str(self.repo))
        git("remote", "add", "origin", "git@github.com:org/booking.git", cwd=self.repo)
        self.saved = {key: os.environ.get(key) for key in ("CRAFTSMAN_CLONES", "CRAFTSMAN_GITHUB", "CRAFTSMAN_BROWSE")}

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp)

    def test_the_top_folder_of_the_pull_requests_repository_is_accepted(self):
        self.assertEqual(checkout.check(self.repo, PULL), {"checkout": str(self.repo), "warning": None})

    def test_a_folder_inside_a_repository_is_refused_naming_its_top_folder(self):
        (self.repo / "src").mkdir()

        with self.assertRaises(review_state.Refused) as refused:
            checkout.check(self.repo / "src", PULL)

        self.assertIn(str(self.repo), str(refused.exception))

    def test_a_folder_that_is_not_a_repository_is_refused(self):
        with self.assertRaises(review_state.Refused) as refused:
            checkout.check(self.tmp, PULL)

        self.assertIn("not a git repository", str(refused.exception))

    def test_a_checkout_of_another_repository_warns_but_is_accepted(self):
        checked = checkout.check(self.repo, "https://github.com/org/payments/pull/7")

        self.assertEqual(checked["checkout"], str(self.repo))
        self.assertIn("org/payments", checked["warning"])

    def test_two_branches_need_no_remote(self):
        git("remote", "remove", "origin", cwd=self.repo)

        self.assertEqual(checkout.check(self.repo, "main:feature/x")["warning"], None)

    def test_a_pull_request_is_cloned_partially_into_the_clones_folder(self):
        origin = self.tmp / "github" / "org" / "booking.git"
        git("clone", "-q", "--bare", str(self.repo), str(origin))
        os.environ.update(CRAFTSMAN_CLONES=str(self.tmp / "clones"), CRAFTSMAN_GITHUB=f"file://{self.tmp / 'github'}")

        cloned = checkout.clone(PULL)

        self.assertEqual(cloned, self.tmp / "clones" / "org" / "booking")
        self.assertTrue((cloned / ".git").is_dir())
        self.assertEqual(checkout.clone(PULL), cloned)

    def test_two_branches_are_never_cloned(self):
        with self.assertRaises(review_state.Refused):
            checkout.clone("main:feature/x")

    def test_clones_go_to_tmp_unless_moved(self):
        os.environ.pop("CRAFTSMAN_CLONES", None)

        self.assertEqual(checkout.clones_root(), pathlib.Path("/tmp/craftsman/repos"))

    def test_the_folder_dialog_returns_the_chosen_folder(self):
        os.environ["CRAFTSMAN_BROWSE"] = f"echo {self.repo}/"

        self.assertEqual(checkout.browse(), str(self.repo))

    def test_a_cancelled_folder_dialog_returns_nothing(self):
        os.environ["CRAFTSMAN_BROWSE"] = "false"

        self.assertIsNone(checkout.browse())


class ReleaseAndRestoreTest(unittest.TestCase):
    """A review's worktree, and the clone it reads from, are deleted when the review is closed or archived, and made
    again when it resumes: /tmp may be emptied at any restart."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.saved = {key: os.environ.get(key) for key in ("CRAFTSMAN_CLONES", "CRAFTSMAN_GITHUB", "CRAFTSMAN_HOME")}
        os.environ.update(CRAFTSMAN_CLONES=str(self.tmp / "clones"), CRAFTSMAN_GITHUB=f"file://{self.tmp / 'github'}",
                          CRAFTSMAN_HOME=str(self.tmp / "home"))
        work = self.tmp / "work"
        git("init", "-q", "-b", "main", str(work))
        (work / "A.java").write_text("class A {}\n")
        git("add", ".", cwd=work)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "a", cwd=work)
        self.head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, capture_output=True,
                                   text=True).stdout.strip()
        origin = self.tmp / "github" / "org" / "booking.git"
        git("clone", "-q", "--bare", str(work), str(origin))
        git("update-ref", "refs/pull/123/head", self.head, cwd=origin)
        self.diff = self.tmp / "change.diff"
        self.diff.write_text("diff\n")

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp)

    def review(self, review_id, checkout):
        review = self.tmp / "home" / "reviews" / review_id
        review_state.change(review, "init", {"source": {"kind": "pull-request", "url": PULL, "number": 123},
                                             "base": self.head, "head": self.head, "diff": str(self.diff),
                                             "checkout": str(checkout)})
        return review

    def test_a_review_in_a_clone_is_restored_with_its_worktree_at_the_reviewed_commit(self):
        review = self.review("org-booking-pr-123", checkout.clone_dir(PULL))
        self.assertTrue(checkout.needs_restore(review))

        checkout.restore(review)

        self.assertEqual((review / "worktree" / "A.java").read_text(), "class A {}\n")
        self.assertFalse(checkout.needs_restore(review))

    def test_releasing_a_review_deletes_its_worktree_and_its_clone(self):
        review = self.review("org-booking-pr-123", checkout.clone_dir(PULL))
        checkout.restore(review)

        checkout.release(review)

        self.assertFalse((review / "worktree").exists())
        self.assertFalse(checkout.clone_dir(PULL).exists())
        self.assertTrue((review / "review.json").exists())

    def test_a_clone_another_open_review_reads_from_is_kept(self):
        first = self.review("org-booking-pr-123", checkout.clone_dir(PULL))
        second = self.review("org-booking-pr-124", checkout.clone_dir(PULL))
        checkout.restore(first)
        checkout.restore(second)

        checkout.release(first)

        self.assertTrue(checkout.clone_dir(PULL).exists())
        self.assertTrue((second / "worktree" / "A.java").exists())

    def test_releasing_a_review_in_the_developers_checkout_keeps_the_checkout(self):
        mine = self.tmp / "booking"
        git("clone", "-q", str(self.tmp / "github" / "org" / "booking.git"), str(mine))
        git("fetch", "-q", "origin", "refs/pull/123/head", cwd=mine)
        review = self.review("org-booking-pr-123", mine)
        checkout.restore(review)

        checkout.release(review)

        self.assertFalse((review / "worktree").exists())
        self.assertTrue((mine / "A.java").exists())
        listed = subprocess.run(["git", "worktree", "list"], cwd=mine, capture_output=True, text=True).stdout
        self.assertEqual(len(listed.splitlines()), 1)

    def test_a_missing_checkout_of_the_developer_is_not_made_again(self):
        review = self.review("org-booking-pr-123", self.tmp / "gone")

        with self.assertRaises(review_state.Refused) as refused:
            checkout.restore(review)

        self.assertIn("missing", str(refused.exception))


if __name__ == "__main__":
    unittest.main()
