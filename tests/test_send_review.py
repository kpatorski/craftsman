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
@@ -1,3 +1,5 @@
 class Cancel {
-    // to do
+    void cancel(String id) {
+        if (id == null) return;
+    }
 }
diff --git a/src/Old.java b/src/Old.java
deleted file mode 100644
--- a/src/Old.java
+++ /dev/null
@@ -1,2 +0,0 @@
-class Old {
-}
"""


def at(path, line, side="RIGHT"):
    return {"path": path, "line": line, "side": side, "commit": "bbb"}


class SendReviewTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.review = self.root / "pr-123"
        self.log = self.root / "gh.log"
        os.environ.update(FAKE_GH_LOG=str(self.log), FAKE_GH_STATE=str(self.root / "gh.json"))
        os.environ.pop("FAKE_GH_FAIL", None)
        os.environ.pop("FAKE_GH_NO_FILE", None)
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

    def test_gh_talks_to_the_host_of_the_pull_request(self):
        self.opened(dict(PULL, url="https://github.example.com/org/booking/pull/123"))
        self.finding("Use a value object.", [at("src/Cancel.java", 2)])

        send_review.send(self.review, gh=self.gh)

        self.assertEqual({"github.example.com"}, {call["host"] for call in self.calls()})

    def test_gh_talks_to_github_com_for_a_pull_request_there(self):
        os.environ["GH_HOST"] = "github.example.com"
        self.addCleanup(os.environ.pop, "GH_HOST", None)
        self.opened()
        self.finding("Use a value object.", [at("src/Cancel.java", 2)])

        send_review.send(self.review, gh=self.gh)

        self.assertEqual({"github.com"}, {call["host"] for call in self.calls()})

    def test_a_list_github_gives_in_pages_reads_as_one(self):
        self.assertEqual(send_review.pages('[{"id": 1}, {"id": 2}]\n[{"id": 3}]'), [{"id": 1}, {"id": 2}, {"id": 3}])
        self.assertEqual(send_review.pages('{"id": 7}'), {"id": 7})

    def test_a_line_that_looks_like_a_header_is_still_a_line_of_the_file(self):
        diff = ("diff --git a/db/init.sql b/db/init.sql\n--- a/db/init.sql\n+++ b/db/init.sql\n@@ -1,3 +1,3 @@\n"
                "--- old note\n+++ new note\n select 1;\n-select 2;\n+select 3;\n")

        lines = send_review.changed_lines(diff)

        self.assertEqual((lines[("db/init.sql", "LEFT")], lines[("db/init.sql", "RIGHT")]), ({1, 2, 3}, {1, 2, 3}))

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

    def test_a_finding_about_a_whole_file_in_the_change_goes_on_that_file(self):
        self.opened()
        found = self.finding("Split this class.", [at("src/Cancel.java", None)])

        send_review.send(self.review, gh=self.gh)

        self.assertEqual(self.posted("/pulls/123/comments"), [{"commit_id": "bbb", "path": "src/Cancel.java",
                                                               "subject_type": "file", "body": "Split this class."}])
        self.assertEqual((self.posted_reviews(), self.posted("/issues/123/comments")), ([], []))
        self.assertEqual(self.findings()[found]["status"], "sent")
        self.assertIn("#discussion_r", self.findings()[found]["sent"][0]["url"])

    def test_a_further_place_on_a_whole_file_goes_on_that_file_too(self):
        self.opened()
        found = self.finding("Ids as strings.", [at("src/Cancel.java", 2), at("src/Cancel.java", None)])

        send_review.send(self.review, gh=self.gh)

        url = self.findings()[found]["sent"][0]["url"]
        self.assertEqual(self.posted("/pulls/123/comments"), [{"commit_id": "bbb", "path": "src/Cancel.java",
                                                               "subject_type": "file", "body": f"Same as {url}"}])
        self.assertEqual([entry["location"] for entry in self.findings()[found]["sent"]], [0, 1])

    def test_a_whole_file_github_cannot_comment_on_goes_as_a_general_comment_naming_the_file(self):
        self.opened()
        found = self.finding("Split this class.", [at("src/Cancel.java", None)])
        os.environ["FAKE_GH_NO_FILE"] = "1"

        result = send_review.send(self.review, gh=self.gh)

        general = self.posted("/issues/123/comments")
        self.assertEqual([g["body"] for g in general], ["**`src/Cancel.java`**\n\nSplit this class."])
        self.assertEqual((self.findings()[found]["status"], result["errors"]), ("sent", []))

    def test_a_whole_file_outside_the_change_goes_as_a_general_comment_naming_the_file(self):
        self.opened()
        found = self.finding("Split this class.", [at("src/Desk.java", None)], kind="out-of-scope")

        send_review.send(self.review, gh=self.gh)

        general = self.posted("/issues/123/comments")
        self.assertEqual([g["body"] for g in general], ["**`src/Desk.java`**\n\nSplit this class."])
        self.assertEqual((self.posted_reviews(), self.posted("/pulls/123/comments")), ([], []))
        self.assertEqual(self.findings()[found]["status"], "sent")

    def test_a_finding_on_a_folder_goes_to_the_conversation_naming_the_folder(self):
        self.opened()
        found = self.finding("One aggregate here.", [at("src/desk/", None)])

        send_review.send(self.review, gh=self.gh)

        self.assertEqual([g["body"] for g in self.posted("/issues/123/comments")], ["**`src/desk/`**\n\nOne aggregate here."])
        self.assertEqual((self.posted_reviews(), self.posted("/pulls/123/comments")), ([], []))
        self.assertEqual(self.findings()[found]["status"], "sent")

    def test_a_whole_file_comment_already_on_github_is_not_sent_again(self):
        self.opened()
        found = self.finding("Split this class.", [at("src/Cancel.java", None)])
        earlier = {"comments": [{"id": 77, "path": "src/Cancel.java", "line": None, "subject_type": "file",
                                 "body": "Split this class.",
                                 "html_url": "https://github.com/org/booking/pull/123#discussion_r77"}]}
        (self.root / "gh.json").write_text(json.dumps(earlier))

        send_review.send(self.review, gh=self.gh)

        self.assertEqual(self.posted("/pulls/123/comments"), [])
        self.assertEqual(self.findings()[found]["sent"][0]["url"],
                         "https://github.com/org/booking/pull/123#discussion_r77")

    def test_a_line_of_a_removed_file_goes_on_that_line(self):
        self.opened()
        self.finding("Still used elsewhere.", [at("src/Old.java", 1, "LEFT")])

        send_review.send(self.review, gh=self.gh)

        self.assertEqual(self.posted_reviews()[0]["comments"], [{"path": "src/Old.java", "line": 1, "side": "LEFT",
                                                                 "body": "Still used elsewhere."}])

    def test_a_removed_line_is_judged_by_the_old_side_of_the_diff(self):
        self.opened()
        removed = self.finding("Keep the note.", [at("src/Cancel.java", 2, "LEFT")])
        beyond = self.finding("No such old line.", [at("src/Cancel.java", 4, "LEFT")], kind="out-of-scope")

        send_review.send(self.review, gh=self.gh)

        self.assertEqual(self.posted_reviews()[0]["comments"], [{"path": "src/Cancel.java", "line": 2, "side": "LEFT",
                                                                 "body": "Keep the note."}])
        self.assertEqual(len(self.posted("/issues/123/comments")), 1)
        self.assertIn("src/Cancel.java:4", self.posted("/issues/123/comments")[0]["body"])
        self.assertEqual({self.findings()[f]["status"] for f in (removed, beyond)}, {"sent"})

    def test_a_comment_already_on_github_is_not_sent_again(self):
        self.opened()
        inline = self.finding("Use a value object.", [at("src/Cancel.java", 2)])
        general = self.finding("Exposes a mutable list.", [at("src/DeskRepository.java", 40)], kind="out-of-scope")
        earlier = {"reviews": {"1": [{"path": "src/Cancel.java", "line": 2, "side": "RIGHT", "body": "Use a value object.",
                                      "html_url": "https://github.com/org/booking/pull/123#discussion_r11"}]},
                   "issue_comments": [{"body": "**`src/DeskRepository.java:40`**\n\nExposes a mutable list.",
                                       "html_url": "https://github.com/org/booking/pull/123#issuecomment-1"}]}
        (self.root / "gh.json").write_text(json.dumps(earlier))

        result = send_review.send(self.review, gh=self.gh)

        self.assertEqual((self.posted_reviews(), self.posted("/issues/123/comments")), ([], []))
        self.assertEqual(sorted(result["sent"]), sorted([inline, general]))
        self.assertEqual(self.findings()[inline]["sent"][0]["url"], "https://github.com/org/booking/pull/123#discussion_r11")
        self.assertEqual(self.findings()[general]["sent"][0]["url"], "https://github.com/org/booking/pull/123#issuecomment-1")

    def comment(self, body, reply_to=None):
        return review_state.change(self.review, "add-comment", {"body": body, "reply-to": reply_to}, "developer")

    def comments(self):
        return {c["id"]: c for c in review_state.read(self.review)["comments"]}

    def test_a_comment_on_the_whole_pull_request_goes_to_its_conversation_as_written(self):
        self.opened()
        sent = self.comment("Thanks, the split into use cases reads well.")
        dropped = self.comment("Not this one.")
        review_state.change(self.review, "comment-status", {"status": "deleted"}, "developer", dropped)

        result = send_review.send(self.review, gh=self.gh)

        self.assertEqual(self.posted("/issues/123/comments"), [{"body": "Thanks, the split into use cases reads well."}])
        self.assertEqual(self.posted_reviews(), [])
        self.assertEqual(result["sent"], [sent])
        self.assertEqual(self.comments()[sent]["url"], "https://github.com/org/booking/pull/123#issuecomment-1")
        self.assertEqual(self.comments()[dropped]["status"], "deleted")

    def test_a_reply_goes_into_its_thread_on_github(self):
        self.opened()
        theirs = {"id": 77, "path": "src/Cancel.java", "line": 2, "side": "RIGHT", "body": "Why a string?",
                  "user": {"login": "anna"}, "created_at": "2026-10-30T09:00:00Z",
                  "html_url": "https://github.com/org/booking/pull/123#discussion_r77"}
        (self.root / "gh.json").write_text(json.dumps({"comments": [theirs]}))
        reply = self.comment("Because the id comes from the URL.", reply_to=77)

        send_review.send(self.review, gh=self.gh)

        self.assertEqual(self.posted("/pulls/123/comments/77/replies"), [{"body": "Because the id comes from the URL."}])
        self.assertEqual(self.comments()[reply]["status"], "sent")
        self.assertTrue(self.comments()[reply]["url"].startswith("https://github.com/org/booking/pull/123#discussion_r"))

    def test_a_comment_or_reply_already_on_github_is_not_sent_again(self):
        self.opened()
        earlier = {"issue_comments": [{"id": 501, "body": "Looks good.",
                                       "html_url": "https://github.com/org/booking/pull/123#issuecomment-1"}],
                   "comments": [{"id": 77, "path": "src/Cancel.java", "line": 2, "body": "Why?",
                                 "html_url": "https://github.com/org/booking/pull/123#discussion_r77"},
                                {"id": 78, "in_reply_to_id": 77, "path": "src/Cancel.java", "line": 2, "body": "Because.",
                                 "html_url": "https://github.com/org/booking/pull/123#discussion_r78"}]}
        (self.root / "gh.json").write_text(json.dumps(earlier))
        general, reply = self.comment("Looks good."), self.comment("Because.", reply_to=77)

        send_review.send(self.review, gh=self.gh)

        self.assertEqual((self.posted("/issues/123/comments"), self.posted("/replies")), ([], []))
        self.assertEqual(self.comments()[general]["url"], "https://github.com/org/booking/pull/123#issuecomment-1")
        self.assertEqual(self.comments()[reply]["url"], "https://github.com/org/booking/pull/123#discussion_r78")

    def test_a_failed_comment_waits_for_the_next_send(self):
        self.opened()
        waiting = self.comment("Thanks.")
        os.environ["FAKE_GH_FAIL"] = "1"

        result = send_review.send(self.review, gh=self.gh)

        self.assertEqual(result["sent"], [])
        self.assertEqual(self.comments()[waiting]["status"], "to-send")

    def test_comments_wait_when_what_is_on_github_cannot_be_read(self):
        self.opened()
        waiting = self.comment("Thanks.")
        real = send_review.gh_api

        def unreadable(gh, endpoint, payload=None, host="github.com"):
            if payload is None:
                raise RuntimeError("HTTP 502")
            return real(gh, endpoint, payload, host)
        send_review.gh_api = unreadable
        self.addCleanup(setattr, send_review, "gh_api", real)

        result = send_review.send(self.review, gh=self.gh)

        self.assertEqual(self.posted("/issues/123/comments"), [])
        self.assertEqual(self.comments()[waiting]["status"], "to-send")
        self.assertIn("502", result["errors"][0])

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
