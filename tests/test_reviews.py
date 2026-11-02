"""Tests for the review side of the dashboard: what the page may read and change in a review, and how its requests
reach the review's session -- see REVIEW.md.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile
import threading
import time
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
           "locations": [{"path": "A.java", "line": 3, "side": "RIGHT", "commit": "bbb"}], "kind": "violation",
           "severity": "should-fix"}
DIFF = """diff --git a/A.java b/A.java
new file mode 100644
--- /dev/null
+++ b/A.java
@@ -0,0 +1,2 @@
+class A {}
+// two
diff --git a/B.java b/B.java
index 111..222 100644
--- a/B.java
+++ b/B.java
@@ -1,3 +1,3 @@
 class B {
-  int x;
+  long x;
 }
diff --git a/Old.java b/Old.java
deleted file mode 100644
--- a/Old.java
+++ /dev/null
@@ -1,2 +0,0 @@
-class Old {}
-// gone
diff --git a/C.java b/D.java
similarity index 90%
rename from C.java
rename to D.java
--- a/C.java
+++ b/D.java
@@ -1 +1 @@
-class C {}
+class D {}
"""


class ReviewsTest(unittest.TestCase):
    def setUp(self):
        self.project = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.review = self.project / ".claude" / "reviews" / "pr-123"
        diff = self.project / "change.diff"
        diff.write_text(DIFF)
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
        reviews.add_message(self.project, "pr-123", {"type": "refresh"})
        reviews.add_message(self.project, "pr-123", {"type": "ask", "thread": "t1"})
        review_state.change(self.review, "handled", item_id="m1")

        self.assertEqual([m["id"] for m in reviews.pending_messages(self.review)], ["m2"])

    def test_a_message_of_an_unknown_type_or_without_its_fields_is_refused(self):
        with self.assertRaises(review_state.Refused):
            reviews.add_message(self.project, "pr-123", {"type": "delete-everything"})
        with self.assertRaises(review_state.Refused):
            reviews.add_message(self.project, "pr-123", {"type": "ask"})

        self.assertEqual(self.inbox(), [])

    def test_the_page_adds_the_developers_own_finding(self):
        reviews.developer_change(self.project, "pr-123", "add-finding", {"fields": {
            "title": "Mine", "comment": "Return a result.", "severity": "nit",
            "locations": [{"path": "A.java", "line": 1, "side": "RIGHT", "commit": "bbb"}]}})

        self.assertEqual(review_state.read(self.review)["findings"][1]["by"], "developer")

    def test_a_question_on_the_page_opens_a_thread_and_wakes_the_session(self):
        reviews.developer_change(self.project, "pr-123", "ask", {
            "about": {"kind": "file", "path": "A.java", "lines": [1, 2]}, "quote": "class A {}", "text": "Why?"})
        reviews.developer_change(self.project, "pr-123", "reply", {"thread": "t1", "text": "And?"})
        reviews.developer_change(self.project, "pr-123", "resolve", {"thread": "t1"})

        thread = review_state.read(self.review)["threads"][0]
        self.assertEqual(([m["text"] for m in thread["messages"]], thread["status"]), (["Why?", "And?"], "resolved"))
        self.assertEqual([(m["type"], m["thread"]) for m in self.inbox()], [("ask", "t1"), ("ask", "t1")])

    def test_the_page_marks_files_viewed_and_archives_the_review(self):
        reviews.developer_change(self.project, "pr-123", "view", {"path": "A.java"})
        reviews.developer_change(self.project, "pr-123", "unview", {"path": "A.java"})
        reviews.developer_change(self.project, "pr-123", "view", {"path": "B.java"})
        reviews.developer_change(self.project, "pr-123", "archive", {"archived": True})

        self.assertEqual(review_state.read(self.review)["viewed"], ["B.java"])
        self.assertTrue(reviews.list_reviews([self.project])[0]["archived"])

    def test_a_review_id_never_reaches_outside_the_reviews_folder(self):
        with self.assertRaises(review_state.Refused):
            reviews.review_dir(self.project, "../../etc")
        with self.assertRaises(review_state.Refused):
            reviews.review_dir(self.project, "pr-999")

    def test_a_review_is_named_after_its_pull_request_or_its_branches(self):
        self.assertEqual(reviews.review_id_for("https://github.com/org/booking/pull/130"), "pr-130")
        self.assertEqual(reviews.review_id_for("main:feature/cancel-reservation"), "main..feature-cancel-reservation")
        with self.assertRaises(review_state.Refused):
            reviews.review_id_for("not a source")

    def test_the_console_shows_what_was_said_done_and_refused(self):
        events = [{"type": "system", "subtype": "init", "session_id": "s"},
                  {"type": "user", "message": {"role": "user", "content": "Why the retry?"}},
                  {"type": "assistant", "message": {"content": [
                      {"type": "text", "text": "Because the provider..."},
                      {"type": "tool_use", "name": "Bash", "input": {"command": "git log -1"}}]}},
                  {"type": "user", "message": {"content": [{"type": "tool_result", "content": "abc"}]}},
                  {"type": "system", "subtype": "permission_denied", "tool_name": "Write"},
                  {"type": "result", "subtype": "success", "total_cost_usd": 0.0123}]
        (self.review / "session.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events) + "not json\n")

        lines = reviews.console_lines(self.review)

        self.assertEqual([(line["kind"], line["text"]) for line in lines], [
            ("you", "Why the retry?"), ("text", "Because the provider..."), ("tool", "Bash git log -1"),
            ("denied", "Write"), ("turn", "turn ended · $0.0123")])

    def test_a_long_tool_call_shows_as_its_first_line_shortened(self):
        command = "python3 review_state.py pr-1 set <<'EOF'\n" + "{" + "x" * 400 + "}\nEOF"
        event = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash",
                                                                "input": {"command": command}}]}}
        (self.review / "session.jsonl").write_text(json.dumps(event) + "\n")

        line = reviews.console_lines(self.review)[0]["text"]

        self.assertEqual(line, "Bash python3 review_state.py pr-1 set <<'EOF' …")

    def test_markdown_in_the_review_reaches_the_page_rendered(self):
        review_state.change(self.review, "update-finding", {"comment": "Use `ReservationId`."}, item_id="f1")

        html = reviews.read_review(self.project, "pr-123")["html"]

        self.assertIn("<code>ReservationId</code>", html["finding:f1:comment"])
        self.assertIn("Cancels a reservation.", html["scope"])

    def test_the_diff_of_the_reviewed_head_is_served(self):
        self.assertIn("+class A {}", reviews.diff_text(self.project, "pr-123"))

    def test_the_diff_of_one_file_is_served_alone(self):
        one = reviews.diff_text(self.project, "pr-123", "B.java")

        self.assertTrue(one.startswith("diff --git a/B.java b/B.java"))
        self.assertIn("+  long x;", one)
        self.assertNotIn("class A", one)

    def test_the_changed_files_say_how_each_one_changed(self):
        files = reviews.changed_files(DIFF)

        self.assertEqual([(f["path"], f["change"], f["added"], f["removed"]) for f in files], [
            ("A.java", "added", 2, 0), ("B.java", "modified", 1, 1), ("Old.java", "deleted", 0, 2),
            ("D.java", "renamed", 1, 1)])
        self.assertEqual(files[3]["from"], "C.java")

    def test_every_changed_file_is_in_a_use_case_or_listed_apart_so_none_is_lost(self):
        review_state.change(self.review, "set", {"structure": {"use-cases": [
            {"id": "u1", "name": "Cancel", "says": "Cancels.", "entry": "A.java:1", "files": ["A.java", "B.java"]},
            {"id": "u2", "name": "Release", "says": "Releases.", "entry": "B.java:1", "files": ["B.java"]}]}})
        review_state.change(self.review, "view", {"path": "B.java"}, "developer")

        read = reviews.read_review(self.project, "pr-123")

        files = {f["path"]: f for f in read["files"]}
        self.assertEqual(files["B.java"]["use-cases"], ["u1", "u2"])
        self.assertTrue(files["B.java"]["viewed"])
        self.assertEqual(read["untied"], ["Old.java", "D.java"])

    def test_what_still_refers_to_a_deleted_file_is_found_in_the_reviewed_code(self):
        worktree = self.review / "worktree"
        (worktree / "src").mkdir(parents=True)
        (worktree / "src" / "Uses.java").write_text("class Uses {\n  Old old;\n  OldStyle style;\n}\n")
        (worktree / "src" / "Clean.java").write_text("class Clean {}\n")

        self.assertEqual(reviews.references(self.project, "pr-123", "Old.java"), ["src/Uses.java:2"])


class ReviewEndpointsTest(ReviewsTest):
    """The same through HTTP, as the page does it -- only for projects on the dashboard."""

    def setUp(self):
        super().setUp()
        (self.project / ".git").mkdir()
        self.real_state = dashboard_server.STATE
        dashboard_server.STATE = self.project / "dashboard-state.json"
        fake = pathlib.Path(__file__).resolve().parent / "fake_claude.py"
        os.environ["CRAFTSMAN_CLAUDE"] = f"{sys.executable} {fake}"
        os.environ.update(FAKE_CLAUDE_LOG=str(self.project / "fake.log"), CRAFTSMAN_SCRIPTS=str(SCRIPTS),
                          FAKE_REVIEW_DIR=str(self.project / ".claude" / "reviews" / "main..feature-x"))
        self.server = dashboard_server.ThreadingHTTPServer(("127.0.0.1", 0), dashboard_server.Handler)
        self.port = self.server.server_address[1]
        dashboard_server.Handler.hub = dashboard_server.Hub(pathlib.Path(tempfile.mkdtemp()), [self.project],
                                                            self.port)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        dashboard_server.Handler.hub.stop_sessions()
        self.server.shutdown()
        self.server.server_close()
        dashboard_server.STATE = self.real_state
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

    def text(self, path):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                         headers={"Host": f"127.0.0.1:{self.port}", "X-Craftsman": "1"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.read().decode()

    def page(self, path):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                         headers={"Host": f"127.0.0.1:{self.port}"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.read().decode()

    def test_reviews_have_their_own_page_apart_from_the_dashboard(self):
        review_page, dashboard_page = self.page("/review"), self.page("/")

        self.assertIn("<title>craftsman review</title>", review_page)
        self.assertIn("/api/review", review_page)
        self.assertNotIn("/api/review", dashboard_page)

    def test_the_tests_never_touch_the_real_dashboard_state(self):
        dashboard_server.Handler.hub.add_project(self.project)

        self.assertTrue((self.project / "dashboard-state.json").exists())

    def test_the_list_says_which_reviews_have_their_session_running(self):
        self.call("/api/review/start", {"project": str(self.project), "source": "main:feature/x"})

        deadline, running = time.time() + 10, {}
        while len(running) < 2 and time.time() < deadline:
            status, body = self.call("/api/reviews")
            running = {review["id"]: review["running"] for review in body["reviews"]}

        self.assertEqual((status, running), (200, {"main..feature-x": True, "pr-123": False}))

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

    def test_the_page_reads_one_files_diff_and_what_refers_to_a_deleted_file(self):
        (self.review / "worktree").mkdir()
        (self.review / "worktree" / "Uses.java").write_text("Old old;\n")

        diff = self.text(f"/api/review/diff?project={self.project}&id=pr-123&path=B.java")
        status, body = self.call(f"/api/review/references?project={self.project}&id=pr-123&path=Old.java")

        self.assertTrue(diff.startswith("diff --git a/B.java"))
        self.assertEqual((status, body["references"]), (200, ["Uses.java:1"]))

    def test_a_refused_change_says_why(self):
        status, body = self.call("/api/review/change", {"project": str(self.project), "id": "pr-123",
                                                         "action": "status", "finding": "f1", "status": "sent"})

        self.assertEqual(status, 409)
        self.assertIn("cannot set sent", body["error"])

    def test_the_page_starts_a_review_session_and_stops_it(self):
        fresh = "main:feature/x"
        status, body = self.call("/api/review/start", {"project": str(self.project), "source": fresh})
        self.assertEqual((status, body["id"]), (200, "main..feature-x"))
        self.assertTrue(dashboard_server.Handler.hub.session(self.project, "main..feature-x").running())

        status, _ = self.call("/api/review/stop", {"project": str(self.project), "id": "main..feature-x"})

        self.assertEqual(status, 200)
        self.assertFalse(dashboard_server.Handler.hub.session(self.project, "main..feature-x").running())

    def test_a_review_starts_only_inside_a_git_repository(self):
        shutil.rmtree(self.project / ".git")

        status, body = self.call("/api/review/start", {"project": str(self.project), "source": "main:feature/x"})

        self.assertEqual(status, 409)
        self.assertIn("not a git repository", body["error"])

    def test_a_review_already_in_progress_is_not_started_again(self):
        status, body = self.call("/api/review/start", {"project": str(self.project),
                                                       "source": "https://github.com/org/booking/pull/123"})

        self.assertEqual(status, 409)
        self.assertIn("in progress", body["error"])

    def test_the_page_sends_what_is_marked_to_send(self):
        review_state.change(self.review, "set-status", {"status": "to-send"}, "developer", "f1")
        os.environ.update(CRAFTSMAN_GH=f"{sys.executable} {pathlib.Path(__file__).resolve().parent / 'fake_gh.py'}",
                          FAKE_GH_LOG=str(self.project / "gh.log"), FAKE_GH_STATE=str(self.project / "gh.json"))

        status, body = self.call("/api/review/send", {"project": str(self.project), "id": "pr-123"})

        self.assertEqual((status, body["sent"]), (200, ["f1"]))
        self.assertEqual(review_state.read(self.review)["findings"][0]["status"], "sent")

    def test_the_cli_starts_a_review_and_prints_where_to_watch_it(self):
        printed = dashboard_server.start_review(self.port, self.project, "main:feature/x")

        self.assertEqual(printed, f"http://localhost:{self.port}/review?project={self.project}&review=main..feature-x")
        self.assertTrue(dashboard_server.Handler.hub.session(self.project, "main..feature-x").running())

    def test_the_cli_resumes_a_review_already_in_progress(self):
        printed = dashboard_server.start_review(self.port, self.project, "https://github.com/org/booking/pull/123")

        self.assertTrue(printed.endswith("&review=pr-123"))
        self.assertTrue(dashboard_server.Handler.hub.session(self.project, "pr-123").running())

    def test_a_project_registered_through_a_symlink_is_found(self):
        link = pathlib.Path(tempfile.mkdtemp()) / "link"
        link.symlink_to(self.project)
        hub = dashboard_server.Handler.hub
        hub.add_project(link)
        hub.remove_project(self.project)
        self.assertEqual(hub.project_list(), [link])

        status, _ = self.call(f"/api/review?project={link}&id=pr-123")

        self.assertEqual(status, 200)
        shutil.rmtree(link.parent)

    def test_a_project_not_on_the_dashboard_is_refused(self):
        elsewhere = tempfile.mkdtemp()
        status, _ = self.call("/api/review/message", {"project": elsewhere, "id": "pr-123", "type": "refresh"})

        self.assertEqual(status, 404)
        shutil.rmtree(elsewhere)


if __name__ == "__main__":
    unittest.main()
