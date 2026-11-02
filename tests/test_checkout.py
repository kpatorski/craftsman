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


if __name__ == "__main__":
    unittest.main()
