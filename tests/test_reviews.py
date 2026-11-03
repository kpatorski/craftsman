"""Tests for the review side of the dashboard: what the page may read and change in a review, and how its requests
reach the review's session -- see REVIEW.md.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import subprocess
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


def eventually(check, seconds=10):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return False


ID = "org-booking-pr-123"
BRANCHES = "booking-main..feature-x"


class ReviewsTest(unittest.TestCase):
    """A review lives in the craftsman home, apart from the repository it reviews: `self.home` stands in for
    `~/.craftsman`, `self.checkout` for the developer's checkout of the repository."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.home, self.checkout = self.tmp / "craftsman-home", self.tmp / "booking"
        self.checkout.mkdir()
        self.real_home = os.environ.get("CRAFTSMAN_HOME")
        os.environ["CRAFTSMAN_HOME"] = str(self.home)
        self.review = self.home / "reviews" / ID
        diff = self.tmp / "change.diff"
        diff.write_text(DIFF)
        review_state.change(self.review, "init", {"source": SOURCE, "base": "aaa", "head": "bbb", "diff": str(diff),
                                                  "checkout": str(self.checkout)})
        review_state.change(self.review, "set", {"scope": "Cancels a reservation."})
        review_state.change(self.review, "add-finding", FINDING)

    def tearDown(self):
        if self.real_home is None:
            os.environ.pop("CRAFTSMAN_HOME", None)
        else:
            os.environ["CRAFTSMAN_HOME"] = self.real_home
        shutil.rmtree(self.tmp)

    def inbox(self):
        path = self.review / "inbox.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_reviews_live_in_the_craftsman_home(self):
        os.environ.pop("CRAFTSMAN_HOME")

        self.assertEqual(reviews.reviews_root(), pathlib.Path.home() / ".craftsman" / "reviews")

    def test_a_review_leaves_nothing_in_the_repository_it_reviews(self):
        self.assertFalse((self.checkout / ".claude").exists())

    def test_every_review_is_listed_with_its_checkout_and_counts(self):
        listed = reviews.list_reviews()

        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], ID)
        self.assertEqual(listed[0]["checkout"], str(self.checkout))
        self.assertEqual(listed[0]["source"], SOURCE)
        self.assertEqual(listed[0]["findings"], {"proposed": 1})

    def test_the_page_edits_a_finding_as_the_developer(self):
        reviews.developer_change(ID, "edit", {"finding": "f1", "fields": {"comment": "Mine."}})

        found = review_state.read(self.review)["findings"][0]
        self.assertEqual((found["comment"], found["edited"]), ("Mine.", ["comment"]))

    def test_the_page_cannot_mark_a_finding_sent(self):
        with self.assertRaises(review_state.Refused):
            reviews.developer_change(ID, "status", {"finding": "f1", "status": "sent"})

    def test_a_checkpoint_answer_is_recorded_and_wakes_the_session(self):
        review_state.change(self.review, "set", {"checkpoint": {"id": "c1", "step": "read-pr-scope",
                                                                "question": "Scope?", "options": ["right"],
                                                                "answer": None}})

        reviews.developer_change(ID, "answer", {"option": "right", "note": "ok"})

        self.assertEqual(review_state.read(self.review)["checkpoint"]["answer"]["option"], "right")
        self.assertEqual([(m["id"], m["type"], m["checkpoint"]) for m in self.inbox()], [("m1", "answer", "c1")])

    def test_messages_get_ids_in_order_and_wait_until_handled(self):
        reviews.add_message(ID, {"type": "refresh"})
        reviews.add_message(ID, {"type": "ask", "thread": "t1"})
        review_state.change(self.review, "handled", item_id="m1")

        self.assertEqual([m["id"] for m in reviews.pending_messages(self.review)], ["m2"])

    def test_a_message_of_an_unknown_type_or_without_its_fields_is_refused(self):
        with self.assertRaises(review_state.Refused):
            reviews.add_message(ID, {"type": "delete-everything"})
        with self.assertRaises(review_state.Refused):
            reviews.add_message(ID, {"type": "ask"})

        self.assertEqual(self.inbox(), [])

    def test_the_page_adds_the_developers_own_finding(self):
        reviews.developer_change(ID, "add-finding", {"fields": {
            "title": "Mine", "comment": "Return a result.", "severity": "nit",
            "locations": [{"path": "A.java", "line": 1, "side": "RIGHT", "commit": "bbb"}]}})

        self.assertEqual(review_state.read(self.review)["findings"][1]["by"], "developer")

    def test_a_question_on_the_page_opens_a_thread_and_wakes_the_session(self):
        reviews.developer_change(ID, "ask", {
            "about": {"kind": "file", "path": "A.java", "lines": [1, 2]}, "quote": "class A {}", "text": "Why?"})
        reviews.developer_change(ID, "reply", {"thread": "t1", "text": "And?"})
        reviews.developer_change(ID, "resolve", {"thread": "t1"})

        thread = review_state.read(self.review)["threads"][0]
        self.assertEqual(([m["text"] for m in thread["messages"]], thread["status"]), (["Why?", "And?"], "resolved"))
        self.assertEqual([(m["type"], m["thread"]) for m in self.inbox()], [("ask", "t1"), ("ask", "t1")])

    def test_the_page_marks_files_viewed_and_archives_the_review(self):
        reviews.developer_change(ID, "view", {"path": "A.java"})
        reviews.developer_change(ID, "unview", {"path": "A.java"})
        reviews.developer_change(ID, "view", {"path": "B.java"})
        reviews.developer_change(ID, "archive", {"archived": True})

        self.assertEqual(review_state.read(self.review)["viewed"], ["B.java"])
        self.assertTrue(reviews.list_reviews()[0]["archived"])

    def test_a_review_id_never_reaches_outside_the_reviews_folder(self):
        with self.assertRaises(review_state.Refused):
            reviews.review_dir("../../etc")
        with self.assertRaises(review_state.Refused):
            reviews.review_dir("org-booking-pr-999")

    def test_a_review_is_named_after_its_pull_request_or_its_repository_and_branches(self):
        self.assertEqual(reviews.review_id_for("https://github.com/org/booking/pull/130"), "org-booking-pr-130")
        self.assertEqual(reviews.review_id_for("https://github.example.com/org/booking/pull/131"), "org-booking-pr-131")
        self.assertEqual(reviews.review_id_for("main:feature/cancel-reservation", self.checkout),
                         "booking-main..feature-cancel-reservation")
        with self.assertRaises(review_state.Refused):
            reviews.review_id_for("main:feature/cancel-reservation")
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

        html = reviews.read_review(ID)["html"]

        self.assertIn("<code>ReservationId</code>", html["finding:f1:comment"])
        self.assertIn("Cancels a reservation.", html["scope"])

    def test_the_diff_of_the_reviewed_head_is_served(self):
        self.assertIn("+class A {}", reviews.diff_text(ID))

    def test_the_diff_of_one_file_is_served_alone(self):
        one = reviews.diff_text(ID, "B.java")

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

        read = reviews.read_review(ID)

        files = {f["path"]: f for f in read["files"]}
        self.assertEqual(files["B.java"]["use-cases"], ["u1", "u2"])
        self.assertTrue(files["B.java"]["viewed"])
        self.assertEqual(read["untied"], ["Old.java", "D.java"])

    def test_what_still_refers_to_a_deleted_file_is_found_in_the_reviewed_code(self):
        worktree = self.review / "worktree"
        (worktree / "src").mkdir(parents=True)
        (worktree / "src" / "Uses.java").write_text("class Uses {\n  Old old;\n  OldStyle style;\n}\n")
        (worktree / "src" / "Clean.java").write_text("class Clean {}\n")

        self.assertEqual(reviews.references(ID, "Old.java"), ["src/Uses.java:2"])


class ReviewEndpointsTest(ReviewsTest):
    """The same through HTTP, as the page does it."""

    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", str(self.checkout)], check=True)
        self.saved_env = {key: os.environ.get(key) for key in ("CRAFTSMAN_CLONES", "CRAFTSMAN_GITHUB",
                                                                "CRAFTSMAN_BROWSE")}
        self.real_state = dashboard_server.STATE
        dashboard_server.STATE = self.tmp / "dashboard-state.json"
        fake = pathlib.Path(__file__).resolve().parent / "fake_claude.py"
        os.environ["CRAFTSMAN_CLAUDE"] = f"{sys.executable} {fake}"
        os.environ.update(FAKE_CLAUDE_LOG=str(self.tmp / "fake.log"), CRAFTSMAN_SCRIPTS=str(SCRIPTS),
                          FAKE_REVIEW_DIR=str(self.home / "reviews" / BRANCHES))
        self.server = dashboard_server.ThreadingHTTPServer(("127.0.0.1", 0), dashboard_server.Handler)
        self.port = self.server.server_address[1]
        dashboard_server.Handler.hub = dashboard_server.Hub(self.tmp / "content", [], self.port)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        dashboard_server.Handler.hub.stop_sessions()
        self.server.shutdown()
        self.server.server_close()
        dashboard_server.STATE = self.real_state
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
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
        dashboard_server.Handler.hub.add_project(self.tmp)

        self.assertTrue((self.tmp / "dashboard-state.json").exists())

    def test_the_list_says_which_reviews_have_their_session_running(self):
        self.call("/api/review/start", {"checkout": str(self.checkout), "source": "main:feature/x"})

        deadline, running = time.time() + 10, {}
        while len(running) < 2 and time.time() < deadline:
            status, body = self.call("/api/reviews")
            running = {review["id"]: review["running"] for review in body["reviews"]}

        self.assertEqual((status, running), (200, {BRANCHES: True, ID: False}))

    def test_the_page_reads_a_review(self):
        status, body = self.call(f"/api/review?id={ID}")

        self.assertEqual(status, 200)
        self.assertEqual(body["state"]["scope"], "Cancels a reservation.")

    def test_the_page_sees_whether_the_agent_is_in_a_turn_and_how_long_it_has_been_quiet(self):
        status, body = self.call(f"/api/review?id={ID}")
        self.assertEqual((status, body["working"], body["quiet"]), (200, False, None))

        self.call("/api/review/start", {"checkout": str(self.checkout), "source": "main:feature/x"})
        deadline, body = time.time() + 10, {}
        while time.time() < deadline and not (body.get("running") and not body.get("working")
                                              and body.get("quiet") is not None):
            _, body = self.call(f"/api/review?id={BRANCHES}")

        self.assertEqual((body["running"], body["working"]), (True, False))
        self.assertGreaterEqual(body["quiet"], 0)

    def test_the_agent_still_works_while_its_reviewers_run_in_the_background(self):
        os.environ["FAKE_BACKGROUND"] = "2"
        self.addCleanup(os.environ.pop, "FAKE_BACKGROUND")
        self.call("/api/review/start", {"checkout": str(self.checkout), "source": "main:feature/x"})
        deadline, body = time.time() + 10, {}
        while time.time() < deadline and body.get("background") != 2:
            _, body = self.call(f"/api/review?id={BRANCHES}")

        self.assertEqual((body["background"], body["working"]), (2, True))

    def test_the_page_changes_a_finding_and_sends_a_message(self):
        status, _ = self.call("/api/review/change", {"id": ID, "action": "status",
                                                      "finding": "f1", "status": "to-send"})
        self.assertEqual(status, 200)
        status, body = self.call("/api/review/message", {"id": ID,
                                                         "type": "refresh"})
        self.assertEqual((status, body["id"]), (200, "m1"))

        self.assertEqual(review_state.read(self.review)["findings"][0]["status"], "to-send")

    def test_the_page_reads_one_files_diff_and_what_refers_to_a_deleted_file(self):
        (self.review / "worktree").mkdir()
        (self.review / "worktree" / "Uses.java").write_text("Old old;\n")

        diff = self.text(f"/api/review/diff?id={ID}&path=B.java")
        status, body = self.call(f"/api/review/references?id={ID}&path=Old.java")

        self.assertTrue(diff.startswith("diff --git a/B.java"))
        self.assertEqual((status, body["references"]), (200, ["Uses.java:1"]))

    def test_a_refused_change_says_why(self):
        status, body = self.call("/api/review/change", {"id": ID,
                                                         "action": "status", "finding": "f1", "status": "sent"})

        self.assertEqual(status, 409)
        self.assertIn("cannot set sent", body["error"])

    def test_the_page_starts_a_review_session_and_stops_it(self):
        fresh = "main:feature/x"
        status, body = self.call("/api/review/start", {"checkout": str(self.checkout), "source": fresh})
        self.assertEqual((status, body["id"]), (200, BRANCHES))
        self.assertTrue(dashboard_server.Handler.hub.session(BRANCHES).running())

        status, _ = self.call("/api/review/stop", {"id": BRANCHES})

        self.assertEqual(status, 200)
        self.assertFalse(dashboard_server.Handler.hub.session(BRANCHES).running())

    def test_the_page_allows_an_mcp_server_in_reviews_and_takes_it_back(self):
        status, body = self.call("/api/review/tools", {"id": ID, "rule": "mcp__jira", "allow": True})
        self.assertEqual(200, status)
        self.assertIn({"name": "jira", "rule": "mcp__jira", "status": "not connected", "allowed": True, "refused": False},
                      body["tools"])
        self.assertEqual(["mcp__jira"], json.loads((self.home / "settings.json").read_text())["review-tools"])
        self.assertEqual(body["tools"], self.call(f"/api/review?id={ID}")[1]["tools"])

        status, body = self.call("/api/review/tools", {"id": ID, "rule": "mcp__jira", "allow": False})
        self.assertEqual((200, []), (status, body["tools"]))

    def test_only_an_mcp_server_can_be_allowed_from_the_tools_panel(self):
        for rule in ("Bash", "mcp__jira__getIssue(x)", "mcp__", "Write(//etc/**)"):
            with self.subTest(rule=rule):
                self.assertEqual(409, self.call("/api/review/tools", {"id": ID, "rule": rule, "allow": True})[0])

    def test_the_page_shows_what_the_session_asks_to_use_and_answers_it(self):
        fresh = {"checkout": str(self.checkout), "source": "main:feature/x"}
        self.call("/api/review/start", fresh)
        runner = dashboard_server.Handler.hub.session(BRANCHES)
        self.assertTrue(eventually(lambda: not runner.busy()))
        runner.send("go on; needs Bash")
        self.assertTrue(eventually(lambda: self.call(f"/api/review?id={BRANCHES}")[1]["permissions"]))
        request = self.call(f"/api/review?id={BRANCHES}")[1]["permissions"][0]
        self.assertEqual(("req-1", "Bash(npm test)"), (request["id"], request["rule"]))

        status, body = self.call("/api/review/permission", {"id": BRANCHES, "request": "req-1", "answer": "always",
                                                            "rule": "Bash(npm test:*)"})

        self.assertEqual((200, []), (status, body["permissions"]))
        self.assertEqual(["Bash(npm test:*)"], json.loads((self.home / "settings.json").read_text())["review-tools"])

    def test_an_answer_the_session_does_not_wait_for_is_refused(self):
        status, body = self.call("/api/review/permission", {"id": ID, "request": "req-1", "answer": "allow"})

        self.assertEqual(409, status)
        self.assertIn("does not wait", body["error"])

    def test_a_rule_allowed_in_reviews_is_listed_and_can_be_taken_back(self):
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "settings.json").write_text(json.dumps({"review-tools": ["Bash(npm test:*)"]}))
        listed = {"name": "Bash(npm test:*)", "rule": "Bash(npm test:*)", "status": "rule", "allowed": True,
                  "refused": False}
        self.assertIn(listed, self.call(f"/api/review?id={ID}")[1]["tools"])

        status, body = self.call("/api/review/tools", {"id": ID, "rule": "Bash(npm test:*)", "allow": False})

        self.assertEqual((200, []), (status, body["tools"]))

    def test_a_review_starts_only_inside_a_git_repository(self):
        shutil.rmtree(self.checkout / ".git")

        status, body = self.call("/api/review/start", {"checkout": str(self.checkout), "source": "main:feature/x"})

        self.assertEqual(status, 409)
        self.assertIn("not a git repository", body["error"])

    def test_a_review_already_in_progress_is_not_started_again(self):
        status, body = self.call("/api/review/start", {"checkout": str(self.checkout),
                                                       "source": "https://github.com/org/booking/pull/123"})

        self.assertEqual(status, 409)
        self.assertIn("in progress", body["error"])
        self.assertEqual({"id": ID, "archived": False, "closed": False}, body["existing"])

    def test_starting_an_archived_review_again_names_it_as_archived(self):
        self.call("/api/review/change", {"id": ID, "action": "archive", "archived": True})

        status, body = self.call("/api/review/start", {"checkout": str(self.checkout),
                                                       "source": "https://github.com/org/booking/pull/123"})

        self.assertEqual((409, True), (status, body["existing"]["archived"]))
        self.assertIn("archived", body["error"])

    def test_a_review_started_over_loses_its_old_state_and_runs_again(self):
        fresh = {"checkout": str(self.checkout), "source": "main:feature/x"}
        self.call("/api/review/start", fresh)
        self.assertTrue(eventually(lambda: (self.home / "reviews" / BRANCHES / "review.json").exists()))
        review_state.change(self.home / "reviews" / BRANCHES, "add-finding", FINDING)
        self.call("/api/review/change", {"id": BRANCHES, "action": "archive", "archived": True})

        status, body = self.call("/api/review/start", dict(fresh, replace=True))

        self.assertEqual((200, BRANCHES), (status, body["id"]))
        self.assertTrue(dashboard_server.Handler.hub.session(BRANCHES).running())
        self.assertTrue(eventually(lambda: (self.home / "reviews" / BRANCHES / "review.json").exists()))
        state = review_state.read(self.home / "reviews" / BRANCHES)
        self.assertEqual([], state["findings"])
        self.assertFalse(state.get("archived"))

    def test_the_page_sends_what_is_marked_to_send(self):
        review_state.change(self.review, "set-status", {"status": "to-send"}, "developer", "f1")
        os.environ.update(CRAFTSMAN_GH=f"{sys.executable} {pathlib.Path(__file__).resolve().parent / 'fake_gh.py'}",
                          FAKE_GH_LOG=str(self.tmp / "gh.log"), FAKE_GH_STATE=str(self.tmp / "gh.json"))

        status, body = self.call("/api/review/send", {"id": ID})

        self.assertEqual((status, body["sent"]), (200, ["f1"]))
        self.assertEqual(review_state.read(self.review)["findings"][0]["status"], "sent")

    def test_the_page_is_served_under_craftsman_localhost_and_localhost(self):
        for host in (f"craftsman.localhost:{self.port}", f"localhost:{self.port}", f"127.0.0.1:{self.port}"):
            request = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/reviews", headers={"Host": host})
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200, host)

    def test_a_request_naming_another_host_is_refused(self):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/reviews",
                                         headers={"Host": f"evil.example:{self.port}"})
        with self.assertRaises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(request, timeout=5)

        self.assertEqual(refused.exception.code, 403)

    def test_the_skill_opens_the_wizard_when_nothing_is_given(self):
        self.assertEqual(dashboard_server.review_url(self.port, None), f"http://craftsman.localhost:{self.port}/review?new=")

    def test_the_skill_opens_the_wizard_with_a_new_source_filled_in(self):
        self.assertEqual(dashboard_server.review_url(self.port, "https://github.com/org/booking/pull/130"),
                         f"http://craftsman.localhost:{self.port}/review?new=https%3A//github.com/org/booking/pull/130")
        self.assertEqual(dashboard_server.review_url(self.port, "main:feature/x"),
                         f"http://craftsman.localhost:{self.port}/review?new=main%3Afeature/x")

    def test_the_skill_opens_and_resumes_a_pull_request_already_under_review(self):
        printed = dashboard_server.review_url(self.port, "https://github.com/org/booking/pull/123")

        self.assertEqual(printed, f"http://craftsman.localhost:{self.port}/review?review={ID}")
        runner = dashboard_server.Handler.hub.session(ID)
        deadline = time.time() + 10
        while not runner.running() and time.time() < deadline:
            time.sleep(0.05)
        self.assertTrue(runner.running())

    def test_a_started_review_records_the_checkout_it_runs_in(self):
        self.call("/api/review/start", {"checkout": str(self.checkout), "source": "main:feature/x"})
        deadline, listed = time.time() + 10, {}
        while BRANCHES not in listed and time.time() < deadline:
            listed = {review["id"]: review for review in self.call("/api/reviews")[1]["reviews"]}

        self.assertEqual(listed[BRANCHES]["checkout"], str(self.checkout))
        cwd = [json.loads(line) for line in (self.tmp / "fake.log").read_text().splitlines()][0]["cwd"]
        self.assertEqual(pathlib.Path(cwd).resolve(), self.checkout)

    def test_the_page_checks_a_checkout_before_starting(self):
        status, body = self.call("/api/checkout/check", {"path": str(self.checkout),
                                                         "source": "https://github.com/org/booking/pull/7"})
        self.assertEqual(status, 200)
        self.assertEqual(body["checkout"], str(self.checkout))
        self.assertIn("org/booking", body["warning"])

        status, body = self.call("/api/checkout/check", {"path": str(self.tmp), "source": "main:feature/x"})
        self.assertEqual(status, 409)
        self.assertIn("not a git repository", body["error"])

    def test_the_page_asks_the_server_to_open_the_folder_dialog(self):
        os.environ["CRAFTSMAN_BROWSE"] = f"echo {self.checkout}"
        self.assertEqual(self.call("/api/checkout/browse", {}), (200, {"path": str(self.checkout)}))

        os.environ["CRAFTSMAN_BROWSE"] = "false"
        self.assertEqual(self.call("/api/checkout/browse", {}), (200, {"path": None}))

    def test_a_pull_request_review_may_run_in_a_clone_the_server_makes(self):
        origin = self.tmp / "github" / "org" / "booking.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(self.checkout), str(origin)], check=True,
                       capture_output=True)
        os.environ.update(CRAFTSMAN_CLONES=str(self.tmp / "clones"), CRAFTSMAN_GITHUB=f"file://{self.tmp / 'github'}")

        status, body = self.call("/api/review/start", {"clone": True,
                                                       "source": "https://github.com/org/booking/pull/124"})

        self.assertEqual((status, body["id"]), (200, "org-booking-pr-124"))
        self.assertEqual(dashboard_server.Handler.hub.session("org-booking-pr-124").checkout,
                         self.tmp / "clones" / "org" / "booking")

    def test_archiving_a_review_stops_its_session_and_deletes_its_worktree(self):
        (self.review / "worktree").mkdir()

        status, _ = self.call("/api/review/change", {"id": ID, "action": "archive", "archived": True})

        self.assertEqual(status, 200)
        self.assertFalse((self.review / "worktree").exists())
        self.assertFalse(dashboard_server.Handler.hub.session(ID).running())

    def test_the_page_sees_a_review_being_restored(self):
        status, body = self.call(f"/api/review?id={ID}")

        self.assertEqual((status, body["restoring"], body["problem"]), (200, False, None))

    def test_an_unknown_review_is_not_found(self):
        status, body = self.call("/api/review/message", {"id": "org-booking-pr-999", "type": "refresh"})

        self.assertEqual(status, 409)
        self.assertIn("no review", body["error"])


if __name__ == "__main__":
    unittest.main()
