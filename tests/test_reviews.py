"""Tests for the review side of the dashboard: what the page may read and change in a review, and how its requests
reach the review's session -- see REVIEW.md.

Run: python3 -m unittest discover -s tests
"""
import json
import pathlib
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _reviews as reviews  # noqa: E402
import dashboard_server  # noqa: E402
import review_state  # noqa: E402

SOURCE = {"kind": "pull-request", "url": "https://github.com/org/booking/pull/123", "repository": "org/booking",
          "number": 123}
FINDING = {"category": "naming", "title": "Name says nothing", "description": "d", "comment": "c",
           "locations": [{"path": "A.java", "line": 3, "side": "RIGHT", "commit": "bbb"}], "kind": "violation"}


class ReviewsTest(unittest.TestCase):
    def setUp(self):
        self.project = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.review = self.project / ".claude" / "reviews" / "pr-123"
        diff = self.project / "change.diff"
        diff.write_text("diff --git a/A.java b/A.java\n+class A {}\n")
        review_state.change(self.review, "init", {"source": SOURCE, "base": "aaa", "head": "bbb", "diff": str(diff)})
        review_state.change(self.review, "set", {"scope": "Cancels a reservation."})
        review_state.change(self.review, "add-finding", FINDING)

    def tearDown(self):
        shutil.rmtree(self.project)

    def inbox(self):
        path = self.review / "inbox.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_a_project_with_reviews_is_a_craftsman_project(self):
        self.assertEqual(dashboard_server.data.discover_projects(self.project), [self.project])

    def test_the_reviews_of_a_project_are_listed_with_their_counts(self):
        listed = reviews.list_reviews([self.project])

        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], "pr-123")
        self.assertEqual(listed[0]["project"], str(self.project))
        self.assertEqual(listed[0]["source"], SOURCE)
        self.assertEqual(listed[0]["findings"], {"proposed": 1})

    def test_the_page_edits_a_finding_as_the_developer(self):
        reviews.developer_change(self.project, "pr-123", "edit", {"finding": "f1", "fields": {"comment": "Mine."}})

        found = review_state.read(self.review)["findings"][0]
        self.assertEqual((found["comment"], found["edited"]), ("Mine.", ["comment"]))

    def test_the_page_cannot_mark_a_finding_sent(self):
        with self.assertRaises(review_state.Refused):
            reviews.developer_change(self.project, "pr-123", "status", {"finding": "f1", "status": "sent"})

    def test_a_checkpoint_answer_is_recorded_and_wakes_the_session(self):
        review_state.change(self.review, "set", {"checkpoint": {"id": "c1", "step": "read-pr-scope",
                                                                "question": "Scope?", "options": ["right"],
                                                                "answer": None}})

        reviews.developer_change(self.project, "pr-123", "answer", {"option": "right", "note": "ok"})

        self.assertEqual(review_state.read(self.review)["checkpoint"]["answer"]["option"], "right")
        self.assertEqual([(m["id"], m["type"], m["checkpoint"]) for m in self.inbox()], [("m1", "answer", "c1")])

    def test_messages_get_ids_in_order_and_wait_until_handled(self):
        reviews.add_message(self.project, "pr-123", {"type": "explain", "about": {"kind": "file", "id": "A.java"}})
        reviews.add_message(self.project, "pr-123", {"type": "message", "text": "Why the retry?"})
        review_state.change(self.review, "handled", item_id="m1")

        self.assertEqual([m["id"] for m in reviews.pending_messages(self.review)], ["m2"])

    def test_a_message_of_an_unknown_type_or_without_its_fields_is_refused(self):
        with self.assertRaises(review_state.Refused):
            reviews.add_message(self.project, "pr-123", {"type": "delete-everything"})
        with self.assertRaises(review_state.Refused):
            reviews.add_message(self.project, "pr-123", {"type": "message"})

        self.assertEqual(self.inbox(), [])

    def test_a_review_id_never_reaches_outside_the_reviews_folder(self):
        with self.assertRaises(review_state.Refused):
            reviews.review_dir(self.project, "../../etc")
        with self.assertRaises(review_state.Refused):
            reviews.review_dir(self.project, "pr-999")

    def test_the_diff_of_the_reviewed_head_is_served(self):
        self.assertIn("+class A {}", reviews.diff_text(self.project, "pr-123"))


class ReviewEndpointsTest(ReviewsTest):
    """The same through HTTP, as the page does it -- only for projects on the dashboard."""

    def setUp(self):
        super().setUp()
        self.server = dashboard_server.ThreadingHTTPServer(("127.0.0.1", 0), dashboard_server.Handler)
        self.port = self.server.server_address[1]
        dashboard_server.Handler.hub = dashboard_server.Hub(pathlib.Path(tempfile.mkdtemp()), [self.project],
                                                            self.port)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, path, body=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=None if body is None else json.dumps(body).encode(),
            method="GET" if body is None else "POST",
            headers={"Host": f"127.0.0.1:{self.port}", "X-Craftsman": "1", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_the_page_reads_a_review(self):
        status, body = self.call(f"/api/review?project={self.project}&id=pr-123")

        self.assertEqual(status, 200)
        self.assertEqual(body["state"]["scope"], "Cancels a reservation.")

    def test_the_page_changes_a_finding_and_sends_a_message(self):
        status, _ = self.call("/api/review/change", {"project": str(self.project), "id": "pr-123", "action": "status",
                                                      "finding": "f1", "status": "to-send"})
        self.assertEqual(status, 200)
        status, body = self.call("/api/review/message", {"project": str(self.project), "id": "pr-123",
                                                         "type": "refresh"})
        self.assertEqual((status, body["id"]), (200, "m1"))

        self.assertEqual(review_state.read(self.review)["findings"][0]["status"], "to-send")

    def test_a_refused_change_says_why(self):
        status, body = self.call("/api/review/change", {"project": str(self.project), "id": "pr-123",
                                                         "action": "status", "finding": "f1", "status": "sent"})

        self.assertEqual(status, 409)
        self.assertIn("cannot set sent", body["error"])

    def test_a_project_not_on_the_dashboard_is_refused(self):
        elsewhere = tempfile.mkdtemp()
        status, _ = self.call("/api/review/message", {"project": elsewhere, "id": "pr-123", "type": "refresh"})

        self.assertEqual(status, 404)
        shutil.rmtree(elsewhere)


if __name__ == "__main__":
    unittest.main()
