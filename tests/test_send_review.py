"""Tests for send_review.py: sending the findings the developer marked to send as comments on the pull request --
see REVIEW.md, "Rules on changing the state". A fake `gh` (fake_gh.py) answers like GitHub's REST API.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import review_state  # noqa: E402
import send_review  # noqa: E402

PULL = {"kind": "pull-request", "url": "https://github.com/org/booking/pull/123", "repository": "org/booking",
        "number": 123}
DIFF = """diff --git a/src/Cancel.java b/src/Cancel.java
--- a/src/Cancel.java
+++ b/src/Cancel.java
@@ -1,3 +1,6 @@
 class Cancel {
+    void cancel(String id) {
+        if (id == null) return;
+    }
 }
"""


def at(path, line):
    return {"path": path, "line": line, "side": "RIGHT", "commit": "bbb"}


class SendReviewTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.review = self.root / "pr-123"
        self.log = self.root / "gh.log"
        os.environ.update(FAKE_GH_LOG=str(self.log), FAKE_GH_STATE=str(self.root / "gh.json"))
        os.environ.pop("FAKE_GH_FAIL", None)
        self.gh = [sys.executable, str(TESTS / "fake_gh.py")]

    def tearDown(self):
        shutil.rmtree(self.root)

    def opened(self, source=PULL):
        diff = self.root / "change.diff"
        diff.write_text(DIFF)
        review_state.change(self.review, "init", {"source": source, "base": "aaa", "head": "bbb", "diff": str(diff)})

    def finding(self, comment, locations, to_send=True, kind="violation"):
        found = review_state.change(self.review, "add-finding", {
            "category": "c", "title": "t", "description": "d", "comment": comment, "locations": locations,
            "kind": kind, "severity": "should-fix", **({"when": "later"} if kind == "out-of-scope" else {})})
        if to_send:
            review_state.change(self.review, "set-status", {"status": "to-send"}, "developer", found)
        return found

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def posted(self, ending):
        return [call["payload"] for call in self.calls() if "POST" in call["args"]
                and next(a for a in call["args"] if a.startswith("repos/")).endswith(ending)]

    def posted_reviews(self):
        return self.posted("/reviews")

    def findings(self):
        return {f["id"]: f for f in review_state.read(self.review)["findings"]}

    def test_a_list_github_gives_in_pages_reads_as_one(self):
        self.assertEqual(send_review.pages('[{"id": 1}, {"id": 2}]\n[{"id": 3}]'), [{"id": 1}, {"id": 2}, {"id": 3}])
        self.assertEqual(send_review.pages('{"id": 7}'), {"id": 7})

    def test_only_findings_marked_to_send_go_as_one_review_on_the_reviewed_commit(self):
        self.opened()
        sent = self.finding("Use a value object.", [at("src/Cancel.java", 2)])
        self.finding("Not chosen.", [at("src/Cancel.java", 3)], to_send=False)

        result = send_review.send(self.review, gh=self.gh)

        reviews = self.posted_reviews()
        self.assertEqual(len(reviews), 1)
        self.assertEqual((reviews[0]["commit_id"], reviews[0]["event"]), ("bbb", "COMMENT"))
        self.assertEqual(reviews[0]["comments"], [{"path": "src/Cancel.java", "line": 2, "side": "RIGHT",
                                                   "body": "Use a value object."}])
        self.assertEqual(result["sent"], [sent])
        self.assertEqual(self.findings()[sent]["status"], "sent")
        self.assertTrue(self.findings()[sent]["sent"][0]["url"].startswith("https://github.com/"))
        self.assertEqual(self.findings()["f2"]["status"], "proposed")

    def test_every_further_place_points_back_to_the_first_comment(self):
        self.opened()
        found = self.finding("Ids as strings.", [at("src/Cancel.java", 2), at("src/Cancel.java", 3)])

        send_review.send(self.review, gh=self.gh)

        first, second = self.posted_reviews()
        url = self.findings()[found]["sent"][0]["url"]
        self.assertEqual(second["comments"][0]["line"], 3)
        self.assertIn(url, second["comments"][0]["body"])
        self.assertEqual([entry["location"] for entry in self.findings()[found]["sent"]], [0, 1])

    def test_a_place_outside_the_diff_goes_as_a_general_comment_naming_the_place(self):
        self.opened()
        found = self.finding("Exposes a mutable list.", [at("src/DeskRepository.java", 40)], kind="out-of-scope")

        send_review.send(self.review, gh=self.gh)

        general = self.posted("/issues/123/comments")
        self.assertEqual(len(general), 1)
        self.assertIn("src/DeskRepository.java:40", general[0]["body"])
        self.assertIn("Exposes a mutable list.", general[0]["body"])
        self.assertEqual(self.findings()[found]["status"], "sent")

    def test_without_a_pull_request_nothing_is_sent(self):
        self.opened({"kind": "branches", "target": "main", "source": "feature/x", "pull-request": None})
        found = self.finding("x", [at("src/Cancel.java", 2)])

        with self.assertRaises(review_state.Refused):
            send_review.send(self.review, gh=self.gh)

        self.assertEqual(self.calls(), [])
        self.assertEqual(self.findings()[found]["status"], "to-send")

    def test_a_failure_on_github_leaves_the_findings_to_send(self):
        self.opened()
        found = self.finding("x", [at("src/Cancel.java", 2)])
        os.environ["FAKE_GH_FAIL"] = "1"

        result = send_review.send(self.review, gh=self.gh)

        self.assertEqual(result["sent"], [])
        self.assertIn("422", result["errors"][0])
        self.assertEqual(self.findings()[found]["status"], "to-send")


if __name__ == "__main__":
    unittest.main()
