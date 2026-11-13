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
import fix_prompts  # noqa: E402
import review_state  # noqa: E402
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_review_directives import workshop  # noqa: E402

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

    def test_the_review_lists_every_directive_it_could_check_and_the_protocols_it_runs(self):
        workshop(self.tmp / "content")
        reviews.developer_change(ID, "switch-directive", {"directive": "naming", "on": False})

        read = reviews.read_review(ID, self.tmp / "content")

        self.assertEqual({d["id"]: d["on"] for d in read["directives"]},
                         {"naming": False, "no-explanatory-comments": True, "prefer-lombok": False,
                          "test-naming": True, "characterize": False})
        self.assertEqual([p["id"] for p in read["protocols"]], ["open-review", "review-use-case"])

    def test_the_developer_makes_a_reviews_set_of_directives_the_default_for_every_review(self):
        workshop(self.tmp / "content")
        reviews.developer_change(ID, "switch-directive", {"directive": "naming", "on": False})
        reviews.developer_change(ID, "switch-directive", {"directive": "prefer-lombok", "on": True})
        reviews.developer_change(ID, "switch-directive", {"directive": "test-naming", "on": True})

        reviews.developer_change(ID, "default-directives", {}, self.tmp / "content")

        settings = json.loads((self.home / "settings.json").read_text())
        self.assertEqual(settings["review-directives"], {"naming": False, "prefer-lombok": True})
        self.assertEqual(review_state.read(self.review)["directive-switches"], {})
        read = reviews.read_review(ID, self.tmp / "content")
        self.assertEqual({d["id"]: (d["default"], d["on"]) for d in read["directives"]}["naming"], (False, False))

    def test_the_page_asks_the_agent_to_check_one_directive_in_the_use_cases_already_reviewed(self):
        reviews.developer_change(ID, "check-directive", {"directive": "no-explanatory-comments"})

        lines = (self.review / "inbox.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(lines[-1])["type"], "check")
        self.assertEqual(json.loads(lines[-1])["directive"], "no-explanatory-comments")
        with self.assertRaises(review_state.Refused):
            reviews.developer_change(ID, "check-directive", {})

    def test_the_page_asks_the_agent_to_search_for_findings_it_skipped(self):
        review_state.change(self.review, "set", {"findings-search": "skipped"})

        reviews.developer_change(ID, "search-findings", {})

        self.assertEqual(review_state.read(self.review)["findings-search"], "requested")
        self.assertEqual([m["type"] for m in self.inbox()], ["find"])
        with self.assertRaises(review_state.Refused):
            reviews.developer_change(ID, "search-findings", {})
        self.assertEqual(len(self.inbox()), 1)

    def test_the_page_adds_the_developers_own_finding(self):
        reviews.developer_change(ID, "add-finding", {"fields": {
            "title": "Mine", "comment": "Return a result.", "severity": "nit",
            "locations": [{"path": "A.java", "line": 1, "side": "RIGHT", "commit": "bbb"}]}})

        self.assertEqual(review_state.read(self.review)["findings"][1]["by"], "developer")

    def test_the_page_writes_edits_and_drops_the_developers_comments(self):
        reviews.developer_change(ID, "add-comment", {"body": "Thanks."})
        reviews.developer_change(ID, "add-comment", {"body": "Agreed.", "reply-to": 77})
        reviews.developer_change(ID, "edit-comment", {"comment": "c1", "body": "Thanks, **well split**."})
        reviews.developer_change(ID, "comment-status", {"comment": "c2", "status": "deleted"})

        comments = review_state.read(self.review)["comments"]
        self.assertEqual([(c["body"], c["reply-to"], c["status"]) for c in comments],
                         [("Thanks, **well split**.", None, "to-send"), ("Agreed.", 77, "deleted")])
        self.assertIn("<strong>well split</strong>", reviews.read_review(ID)["html"]["comment:c1"])
        self.assertEqual(self.inbox(), [])

    def test_the_conversation_read_from_github_reaches_the_page_with_its_markdown_safe(self):
        (self.review / "github.json").write_text(json.dumps({"fetched": "2026-11-01T10:00:00+00:00", "error": None,
            "comments": [{"id": 501, "kind": "issue", "author": "anna", "at": "2026-10-30T09:00:00Z",
                          "body": "Use `Clock` <script>alert(1)</script>", "url": "https://github.com/x"}]}))

        read = reviews.read_review(ID)

        self.assertEqual(read["github"]["comments"][0]["author"], "anna")
        self.assertIn("<code>Clock</code>", read["html"]["github:501"])
        self.assertNotIn("<script>", read["html"]["github:501"])

    def test_without_a_conversation_read_yet_the_page_gets_none(self):
        self.assertIsNone(reviews.read_review(ID)["github"])

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

    def test_the_story_reaches_the_page_rendered(self):
        review_state.change(self.review, "set", {"story": {"does": "Lets the owner **cancel**.", "left-out": "No `refund`.",
                                                           "chapters": [{"id": "c1", "title": "Cancelling",
                                                                         "text": "One.\n\n`CancelReservation` two."}]}})

        html = reviews.read_review(ID)["html"]

        self.assertIn("<strong>cancel</strong>", html["story:does"])
        self.assertIn("<code>refund</code>", html["story:left-out"])
        self.assertEqual(html["story:c1"].count("<p>"), 2)

    def test_the_diff_of_the_reviewed_head_is_served(self):
        self.assertIn("+class A {}", reviews.diff_text(ID))

    def test_a_review_whose_diff_is_missing_still_opens_and_says_which_diff_it_misses(self):
        (self.review / "diff" / "bbb.diff").unlink()

        read = reviews.read_review(ID)

        self.assertEqual((read["files"], read["missing-diff"]), ([], "bbb"))
        self.assertEqual(reviews.diff_text(ID, "B.java"), "")

    def test_a_review_with_its_diff_misses_none(self):
        self.assertIsNone(reviews.read_review(ID)["missing-diff"])

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

    def test_each_changed_file_names_its_top_level_type_from_the_reviewed_code_or_else_from_the_diff(self):
        worktree = self.review / "worktree"
        worktree.mkdir()
        (worktree / "B.java").write_text("public class B {\n  long x;\n}\n")

        files = {f["path"]: f["declaration"] for f in reviews.read_review(ID)["files"]}

        self.assertEqual(files["B.java"], {"kind": "class", "visibility": "public"})
        self.assertEqual(files["A.java"], {"kind": "class", "visibility": "package"})
        self.assertEqual(files["Old.java"], {"kind": "class", "visibility": "package"})
        self.assertEqual(reviews.changed_files(DIFF)[1]["declaration"], {"kind": "class", "visibility": "package"})

    def test_the_files_the_change_leaves_as_they_are_are_listed_apart(self):
        worktree = self.review / "worktree"
        (worktree / ".git").mkdir(parents=True)
        (worktree / ".git" / "config").write_text("")
        (worktree / "src").mkdir()
        for name in ("A.java", "B.java", "src/K.java"):
            (worktree / name).write_text("public interface K {}\n")
        (worktree / "src" / "notes.txt").write_text("class Z {}\n")

        self.assertEqual(reviews.unchanged_files(ID), [
            {"path": "src/K.java", "declaration": {"kind": "interface", "visibility": "public"}},
            {"path": "src/notes.txt", "declaration": None}])

    def test_a_file_of_the_reviewed_code_is_served_and_nothing_outside_it(self):
        (self.review / "worktree" / "src").mkdir(parents=True)
        (self.review / "worktree" / "src" / "K.java").write_text("class K {}\n")
        (self.review / "worktree" / ".git").write_text("gitdir: elsewhere\n")

        self.assertEqual(reviews.file_text(ID, "src/K.java"), "class K {}\n")
        for path in ("../review.json", "/etc/hosts", ".git", "src"):
            with self.subTest(path=path), self.assertRaises(review_state.Refused):
                reviews.file_text(ID, path)


class ReviewEndpointsTest(ReviewsTest):
    """The same through HTTP, as the page does it."""

    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.checkout)], check=True)
        for args in (["config", "user.email", "dev@example.com"], ["config", "user.name", "dev"],
                     ["commit", "-q", "--allow-empty", "-m", "Start"], ["checkout", "-q", "-b", "feature/x"],
                     ["commit", "-q", "--allow-empty", "-m", "Cancel"], ["checkout", "-q", "main"]):
            subprocess.run(["git", "-C", str(self.checkout), *args], check=True, capture_output=True)
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

    def test_the_page_reads_the_unchanged_files_and_one_of_them(self):
        (self.review / "worktree" / "src").mkdir(parents=True)
        (self.review / "worktree" / "src" / "K.java").write_text("class K {}\n")

        self.assertEqual(self.call(f"/api/review/files?id={ID}"),
                         (200, {"unchanged": [{"path": "src/K.java", "declaration": {"kind": "class", "visibility": "package"}}]}))
        self.assertEqual(self.text(f"/api/review/file?id={ID}&path=src/K.java"), "class K {}\n")
        self.assertEqual(self.call(f"/api/review/file?id={ID}&path=../review.json")[0], 409)

    def test_a_review_still_opening_answers_with_its_session_and_what_it_asks_permission_for(self):
        shutil.rmtree(self.review)
        self.review.mkdir(parents=True)

        status, body = self.call(f"/api/review?id={ID}")

        self.assertEqual((status, body["opening"], body["running"], body["permissions"]), (200, True, False, []))
        self.assertIn("opening.permissions", self.page(f"/review?review={ID}"))

    def test_an_answer_to_a_permission_request_reaches_a_review_still_opening(self):
        shutil.rmtree(self.review)
        self.review.mkdir(parents=True)

        status, body = self.call("/api/review/permission", {"id": ID, "request": "r1", "answer": "allow"})

        self.assertEqual(status, 409)
        self.assertIn("does not wait for 'r1'", body["error"])

    def test_the_page_reads_the_directives_of_the_workshop_the_server_serves(self):
        workshop(self.tmp / "content")

        status, body = self.call(f"/api/review?id={ID}")

        self.assertEqual(status, 200)
        self.assertIn("no-explanatory-comments", [d["id"] for d in body["directives"]])

    def test_the_page_and_the_dashboard_name_the_directives_checked_with_no_row_in_the_scope_table(self):
        workshop(self.tmp / "content")
        (self.tmp / "content" / "bundles" / "code-review" / "directive-scope.md").write_text(
            "| Directive | Files | Reach |\n|---|---|---|\n| `naming` | production | file |\n")

        _, review = self.call(f"/api/review?id={ID}")
        _, dashboard = self.call("/api/data")

        self.assertEqual(review["unscoped"], ["no-explanatory-comments", "test-naming"])
        self.assertEqual(dashboard["manage"]["unscoped"], ["no-explanatory-comments", "test-naming"])
        for served in (self.page(f"/review?review={ID}"), self.page("/")):
            with self.subTest(page=served[:60]):
                self.assertIn("directive-scope.md", served)
                self.assertIn("data-unscoped", served)

    def test_selected_lines_become_the_panels_context_and_selected_words_of_a_finding_open_the_popover(self):
        served = self.page(f"/review?review={ID}")
        for hook in ('setCtx({ kind: "file", path: diff.dataset.diff, lines: [first, last], side }, "finding")', "function popAt(",
                     "popAt(pop, e, about)", "e.clientX", "e.clientY"):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)
        for gone in ('data-pop="comment"', "popAt(pop, e, diff)", "at.right - 200"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, served)

    def test_the_comment_panel_shows_the_finding_as_the_author_reads_it_without_the_reviewers_why(self):
        self.assertNotIn("draft-why", self.page(f"/review?review={ID}"))

    def test_opening_another_file_in_the_code_tab_starts_at_its_top(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("let shownFile", "main.scrollTop = opened ? 0 : y"):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)

    def test_the_rules_tab_says_how_each_directive_is_checked(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("function howChecked", "once over the change", "per use case", "not in reviews"):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)

    def test_the_page_switches_a_directive_of_the_review_it_shows(self):
        status, body = self.call("/api/review/change", {"id": ID, "action": "switch-directive",
                                                         "directive": "naming", "on": False})

        self.assertEqual(status, 200, body)
        self.assertEqual(review_state.read(self.review)["directive-switches"], {"naming": False})

    def test_the_page_gives_the_agent_context_and_tells_it(self):
        status, body = self.call("/api/review/change", {"id": ID, "action": "add-context",
                                                         "text": "Cancelling is free since last week."})
        self.assertEqual(status, 200, body)
        self.assertEqual([n["text"] for n in review_state.read(self.review)["context"]],
                         ["Cancelling is free since last week."])
        self.assertEqual([m["type"] for m in reviews.pending_messages(self.review)][-1:], ["context"])

        status, body = self.call("/api/review/change", {"id": ID, "action": "remove-context", "note": "x1"})

        self.assertEqual(status, 200, body)
        self.assertEqual(self.call(f"/api/review?id={ID}")[1]["state"]["context"], [])
        self.assertEqual([m["type"] for m in reviews.pending_messages(self.review)][-2:], ["context", "context"])

    def fake_gh(self):
        os.environ.update(CRAFTSMAN_GH=f"{sys.executable} {pathlib.Path(__file__).resolve().parent / 'fake_gh.py'}",
                          FAKE_GH_LOG=str(self.tmp / "gh.log"), FAKE_GH_STATE=str(self.tmp / "gh.json"))

    def test_send_posts_the_fix_prompt_too_when_it_is_asked_for(self):
        review_state.change(self.review, "set-status", {"status": "to-send"}, "developer", "f1")
        self.fake_gh()

        status, body = self.call("/api/review/send", {"id": ID, "fix-prompt": True})

        comments = review_state.read(self.review)["comments"]
        self.assertEqual(status, 200, body)
        self.assertEqual([(fix_prompts.is_fix_prompts(c["body"]), c["status"]) for c in comments], [(True, "sent")])
        self.assertIn(comments[0]["id"], body["sent"])

    def test_send_without_the_fix_prompt_posts_none_and_drops_one_still_waiting(self):
        review_state.change(self.review, "set-status", {"status": "to-send"}, "developer", "f1")
        review_state.change(self.review, "add-comment", {"body": fix_prompts.MARKER + "\n\nold prompts"}, "developer")
        review_state.change(self.review, "add-comment", {"body": "Nice split."}, "developer")
        self.fake_gh()

        status, body = self.call("/api/review/send", {"id": ID, "fix-prompt": False})

        self.assertEqual(status, 200, body)
        self.assertEqual([c["status"] for c in review_state.read(self.review)["comments"]], ["deleted", "sent"])

    def test_the_page_previews_the_fix_prompt_before_send(self):
        self.assertEqual(self.call("/api/review/fix-prompt", {"id": ID})[1], {"comments": [], "findings": 0})
        review_state.change(self.review, "set-status", {"status": "to-send"}, "developer", "f1")

        status, body = self.call("/api/review/fix-prompt", {"id": ID})

        self.assertEqual((status, body["findings"], len(body["comments"])), (200, 1, 1))
        self.assertIn("A.java:3", body["comments"][0])

    def test_whether_send_posts_the_fix_prompt_starts_as_the_developer_set_it(self):
        self.assertTrue(self.call(f"/api/review?id={ID}")[1]["send-fix-prompt"])

        status, body = self.call("/api/review/send-fix-prompt", {"id": ID, "on": False})

        self.assertEqual((status, body), (200, {"send-fix-prompt": False}))
        self.assertFalse(self.call(f"/api/review?id={ID}")[1]["send-fix-prompt"])
        self.assertEqual(json.loads((self.home / "settings.json").read_text())["send-fix-prompt"], False)

    def test_the_review_page_sends_through_one_dialog_with_the_fix_prompt_in_it(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("function openSend(", 'id="with-prompt"', "/api/review/fix-prompt", "data-copy-prompt",
                     '"fix-prompt": ', 'role="dialog" aria-modal="true"', "data-in-prompt", 'change("in-prompt"',
                     "/api/review/send-fix-prompt", "Send ("):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)
        for gone in ("data-fix-prompts", 'change("fix-prompts"', "Fix prompts → comment"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, served)

    def test_the_review_page_is_driven_by_the_keyboard(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("function pageKey(", "function diffKey(", "function findingsKey(", "function openKeys(", "function undoable(",
                     'id="tree-search"', 'role="tablist"', 'role="tab"', "aria-selected", ":focus-visible", "data-undo",
                     'tabindex="0" data-finding'):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)

    def test_the_review_page_keeps_its_controls_plain(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("Send (${toSend})", 'data-refresh title="Refresh PR', 'class="plus"', 'class="minus"', "data-tell-story",
                     'setCtx({ kind: "file", path: diff.dataset.diff, lines: [first, last], side }, "finding")'):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)
        for gone in ("Send… (", "<button class=\"btn ghost\" data-refresh>", "<kbd>Esc</kbd> tree", "open conversation\")} about other places",
                     "Ask <kbd>", "The story comes next", "${info.change}${counts"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, served)

    def test_lines_selected_in_the_code_stay_selected_so_they_can_be_copied(self):
        served = self.page(f"/review?review={ID}")
        selecting = served[served.index('setCtx({ kind: "file", path: diff.dataset.diff, lines: [first, last], side }, "finding");'):]
        selecting = selecting[:selecting.index("} else if (about)")]
        self.assertNotIn("removeAllRanges", selecting)
        self.assertIn("renderPanel()", selecting)
        self.assertNotIn("render()", selecting.replace("renderPanel()", ""))

    def test_the_finding_tab_puts_its_main_button_last_on_the_right_like_the_ask_tab(self):
        served = self.page(f"/review?review={ID}")
        row = served[served.index('<div class="row-actions draft-actions">'):]
        row = row[:row.index("</div>")]
        self.assertLess(row.index('<span class="grow"></span>'), row.index("data-draft-discard"))
        self.assertLess(row.index("data-draft-discard"), row.index("data-draft-make"))
        self.assertIn(".draft-actions .grow { flex: 1; }", served)

    def test_the_shown_files_path_can_be_copied(self):
        served = self.page(f"/review?review={ID}")
        self.assertIn('data-copy-path="${esc(path)}"', served)
        self.assertIn("navigator.clipboard.writeText(d.copyPath)", served)
        self.assertIn('"copy-path"', served)

    def test_a_finding_opens_its_place_in_the_code_and_the_panel_stays_on_it(self):
        served = self.page(f"/review?review={ID}")
        self.assertIn('data-goto-finding="${esc(f.id)}"', served)
        jump = served[served.index("if (d.gotoFinding) {"):]
        jump = jump[:jump.index("\n  }\n")]
        self.assertIn('ui.ctxBy.code = { kind: "finding", id: f.id }', jump)
        self.assertIn("showLine(", jump)
        self.assertIn('"goto-finding"', served)

    def test_the_comment_shape_says_why_tone_and_detail_follow_the_draft(self):
        served = self.page(f"/review?review={ID}")
        for hook in ('"Wording"', 'class="style-note ', "Move Wording to balanced to set them",
                     '<button class="btn ghost sm" data-style-reset'):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)
        for gone in ('"Your words"', '<a data-style-reset'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, served)

    def test_the_review_page_fits_smaller_screens_with_drawers(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("@media (max-width: 1599px)", "@media (max-width: 1199px)", "@media (max-width: 899px)",
                     "@media (max-height: 899px)", "panel-open", "tree-open", 'id="edge"', "data-tree-drawer", "function drawer("):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)

    def test_escape_leaves_a_text_box_first_then_closes_the_sessions_log(self):
        served = self.page(f"/review?review={ID}")
        self.assertIn('if (e.key === "Escape") return onEscape(e)', served)
        escape = served[served.index("function onEscape("):]
        escape = escape[:escape.index("\n}\n")]
        self.assertIn("blur()", escape)
        self.assertIn("closePanel()", escape)

    def test_the_page_keeps_a_draft_per_file_and_makes_a_finding_of_it(self):
        status, body = self.call("/api/review/change", {"id": ID, "action": "save-draft", "path": "B.java",
                                                         "text": "Split it.", "lines": [4, 6], "side": "RIGHT"})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.call(f"/api/review?id={ID}")[1]["state"]["drafts"]["B.java"]["text"], "Split it.")

        status, body = self.call("/api/review/change", {"id": ID, "action": "draft-to-finding", "path": "B.java",
                                                         "title": "Too big", "severity": "should-fix"})

        self.assertEqual(status, 200, body)
        state = review_state.read(self.review)
        self.assertEqual((state["findings"][-1]["title"], state["findings"][-1]["locations"][0]["line"]),
                         ("Too big", 6))
        self.assertEqual(state["drafts"], {})

    def test_the_page_gets_the_assistants_finding_of_a_draft_with_its_comment_rendered(self):
        status, body = self.call("/api/review/draft-preview", {"id": ID, "path": "B.java", "text": "zla nazwa",
                                                                "lines": [4, 6]})

        self.assertEqual(status, 200, body)
        self.assertEqual((body["title"], body["category"], body["severity"]), ("Written up", "naming", "nit"))
        self.assertIn("<strong>it</strong>", body["html"])
        self.assertIn("zla nazwa", (self.tmp / "fake.log").read_text())

    def test_the_page_reads_the_default_shape_of_a_comment(self):
        status, body = self.call(f"/api/review?id={ID}")

        self.assertEqual(status, 200, body)
        self.assertEqual(body["comment-style"], review_state.COMMENT_STYLE_DEFAULT)

    def test_a_default_shape_written_by_hand_keeps_what_it_knows(self):
        (self.home / "settings.json").write_text(json.dumps({"comment-style": {"tone": "rude", "detail": "brief"}}))

        status, body = self.call(f"/api/review?id={ID}")

        self.assertEqual(body["comment-style"], dict(review_state.COMMENT_STYLE_DEFAULT, detail="brief"))

    def test_the_page_sets_the_default_shape_of_a_comment_for_every_review(self):
        status, body = self.call("/api/review/comment-style", {"id": ID, "style": {"tone": "formal", "code": True}})

        self.assertEqual(status, 200, body)
        expected = dict(review_state.COMMENT_STYLE_DEFAULT, tone="formal", code=True)
        self.assertEqual(body["comment-style"], expected)
        self.assertEqual(json.loads((self.home / "settings.json").read_text())["comment-style"], expected)
        self.assertNotEqual(self.call("/api/review/comment-style", {"id": ID, "style": {"tone": "rude"}})[0], 200)

    def test_the_assistant_writes_a_draft_in_the_default_shape_with_what_the_draft_asks_on_top(self):
        self.call("/api/review/comment-style", {"id": ID, "style": {"fidelity": "balanced", "tone": "formal",
                                                                    "detail": "detailed"}})

        status, body = self.call("/api/review/draft-preview", {"id": ID, "path": "B.java", "text": "zla nazwa",
                                                                "style": {"detail": "brief"}, "severity": "must-fix"})

        self.assertEqual(status, 200, body)
        prompt = (self.tmp / "fake.log").read_text()
        for part in ("Formal and neutral", "Exactly one or two sentences", "The reviewer weighs it must-fix"):
            with self.subTest(part=part):
                self.assertIn(part, prompt)
        self.assertNotIn("A paragraph or two", prompt)

    def test_the_page_makes_the_assistants_finding_of_a_draft(self):
        self.call("/api/review/change", {"id": ID, "action": "save-draft", "path": "B.java", "text": "zla nazwa"})

        status, body = self.call("/api/review/change", {
            "id": ID, "action": "draft-to-finding", "path": "B.java", "title": "Written up", "severity": "nit",
            "category": "naming", "description": "Why.", "comment": "Rename it."})

        self.assertEqual(status, 200, body)
        made = review_state.read(self.review)["findings"][-1]
        self.assertEqual((made["category"], made["description"], made["comment"]), ("naming", "Why.", "Rename it."))

    def test_the_page_throws_a_draft_away(self):
        self.call("/api/review/change", {"id": ID, "action": "save-draft", "path": "B.java", "text": "Hm."})

        status, body = self.call("/api/review/change", {"id": ID, "action": "discard-draft", "path": "B.java"})

        self.assertEqual(status, 200, body)
        self.assertEqual(review_state.read(self.review)["drafts"], {})

    def test_the_page_previews_markdown_as_the_findings_show_it(self):
        status, body = self.call("/api/review/markdown", {"id": ID, "text": "Use **one** name:\n```\nvar a;\n```"})

        self.assertEqual(status, 200, body)
        self.assertIn("<strong>one</strong>", body["html"])
        self.assertIn("<pre>", body["html"])

    def test_the_ai_agent_panel_stands_beside_every_tab_under_a_header_running_over_both(self):
        served = self.page(f"/review?review={ID}")
        for hook in ('grid-template-areas: "rail head head head" "rail main grip panel"', "#panel { grid-area: panel;",
                     'main.classList.toggle("frames"', 'const REVIEW_TABS = ["story", "code", "findings", "comments", "rules"]',
                     "function askTab(", "data-pin", "Ask about it", "agentAsks(cp)", "data-sugg", 'data-ctx="'):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)
        for gone in ("panelAsk", "panelThread", "panelCheckpoint", "placePanel", 'id="compose"'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, served)

    def test_the_story_takes_the_place_of_overview_and_structure(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("function viewStory(", '["story", "Story", ""]', "data-chapter", "story:does", "diagramHtml(",
                     'data-open-file="', '"tell-the-story"', "data-context-add", 'stepAt("review-use-cases")'):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)
        for gone in ("viewOverview", "viewStructure", '"Overview"', '"Structure"', "ucpanel", "layoutCards", "data-uccard",
                     "showTip", "function fileList", 'data-tab="overview"', 'data-tab="structure"'):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, served)

    def test_the_comment_panel_has_the_ai_agent_assistant(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("data-assistant-switch", "/api/review/draft-preview", "askAssistant", "AI Agent is writing",
                     "repeats"):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)

    def test_the_comment_panel_lets_the_developer_shape_and_correct_the_assistants_comment(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("data-ai-edit", "data-ai-save", "pinned", "Your draft changed since you edited this",
                     "data-ai-again", "makeBlocked", "data-style", "data-style-reset", "/api/review/comment-style",
                     "Comment style", "severity: d.sevChosen ? d.severity : undefined", "FOLLOWS_THE_DRAFT",
                     "the tone and the length follow the draft"):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)
        clickable = served[served.index("const CLICKABLE"):served.index(".map(name => `[data-${name}]`)")]
        for name in ("ai-edit", "ai-save", "ai-cancel", "ai-again", "style-reset"):
            with self.subTest(clickable=name):
                self.assertIn(f'"{name}"', clickable)

    def test_a_discarded_draft_leaves_the_comment_panel_empty(self):
        served = self.page(f"/review?review={ID}")
        discard = served[served.index("if (d.draftDiscard !== undefined)"):served.index("if (d.mdTool)")]

        # the panel draws the draft again from the review's state, so the state is read again first
        self.assertIn("await reload()", discard)

    def test_the_code_tabs_file_tree_scrolls_on_its_own_and_keeps_its_place(self):
        served = self.page(f"/review?review={ID}")
        for hook in ('id="tree"', ".treebox { height: 100%", "keepCursorInView",
                     'const treeY = document.getElementById("tree")?.scrollTop'):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)

    def test_the_code_tab_reads_the_unchanged_files_and_remembers_the_trees_folders_and_width(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("/api/review/files?", '/api/review/${same ? "file" : "diff"}?', "craftsman.review.tree-closed.", "craftsman.review.tree-width",
                     "function treeHtml(", 'role="tree"'):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)

    def test_the_review_page_has_the_comment_panel(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("data-comment-file", "panelComment(c)", 'change("save-draft"', 'change("discard-draft"',
                     'change("draft-to-finding"', "/api/review/markdown", "draft-box", "panelComment", "data-md-tool"):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)
        for gone in ("panelNewFinding", "data-nf-save"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, served)

    def test_a_review_started_with_context_opens_with_it(self):
        status, body = self.call("/api/review/start", {"checkout": str(self.checkout), "source": "main:feature/x",
                                                        "context": "Only the cancel path changed."})
        self.assertEqual(status, 200, body)
        review = self.home / "reviews" / BRANCHES
        deadline = time.time() + 10
        while not (review / "review.json").exists() and time.time() < deadline:
            time.sleep(0.05)

        self.assertEqual([n["text"] for n in review_state.read(review)["context"]], ["Only the cancel path changed."])

    def test_the_context_for_the_agent_is_given_in_the_panel_on_the_whole_pr(self):
        served = self.page(f"/review?review={ID}")
        for hook in ('c.kind === "review" ? contextNotes(S())', "Context you gave the AI Agent", "data-context-add",
                     'change("add-context"', 'change("remove-context"', "data-context-remove", "nr-context"):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)

    def test_the_review_page_lists_the_directives_with_their_switches_and_results(self):
        served = self.page(f"/review?review={ID}")
        for hook in ('["rules", "Rules"', "data-directive-switch", "data-directive-check", "switch-directive",
                     "data-directive-default", "default-directives"):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)

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

    def test_the_server_opens_the_review_before_its_session_starts(self):
        status, body = self.call("/api/review/start", {"checkout": str(self.checkout), "source": "main:feature/x"})
        self.assertEqual(status, 200, body)
        review = self.home / "reviews" / BRANCHES
        state = review_state.read(review)
        head = subprocess.run(["git", "-C", str(self.checkout), "rev-parse", "feature/x"], capture_output=True,
                              text=True).stdout.strip()
        self.assertEqual((state["source"]["kind"], state["head"]), ("branches", head))
        self.assertTrue((review / "worktree").is_dir())

    def test_a_source_that_cannot_be_opened_is_refused_and_no_session_starts(self):
        status, body = self.call("/api/review/start", {"checkout": str(self.checkout), "source": "main:feature/gone"})
        self.assertEqual(status, 409)
        self.assertIn("feature/gone", body["error"])
        self.assertIsNone(dashboard_server.Handler.hub.running_session(reviews.review_id_for(
            "main:feature/gone", self.checkout)))

    def test_the_page_starts_a_review_session_and_stops_it(self):
        fresh = "main:feature/x"
        status, body = self.call("/api/review/start", {"checkout": str(self.checkout), "source": fresh})
        self.assertEqual((status, body["id"]), (200, BRANCHES))
        self.assertTrue(dashboard_server.Handler.hub.session(BRANCHES).running())

        status, _ = self.call("/api/review/stop", {"id": BRANCHES})

        self.assertEqual(status, 200)
        self.assertFalse(dashboard_server.Handler.hub.session(BRANCHES).running())

    def test_a_review_the_page_asked_about_before_it_existed_still_starts(self):
        self.call(f"/api/review?id={BRANCHES}")
        self.call("/api/review/permission", {"id": BRANCHES, "request": "r1", "answer": "allow"})

        status, body = self.call("/api/review/start", {"checkout": str(self.checkout), "source": "main:feature/x"})

        self.assertEqual((status, body.get("id")), (200, BRANCHES), body)
        self.assertTrue(dashboard_server.Handler.hub.session(BRANCHES).running())

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

    def test_the_review_page_colours_code_by_its_language(self):
        self.assertIn('<script src="/syntax.js"></script>', self.page("/review"))
        self.assertIn("Syntax", self.page("/syntax.js"))

    def test_the_review_page_shows_the_conversation_and_writes_comments_and_replies(self):
        served = self.page(f"/review?review={ID}")
        for hook in ("/api/review/github", '["comments", "Comments"', "data-comment-add", "data-gh-reply", "data-gh-thread"):
            with self.subTest(hook=hook):
                self.assertIn(hook, served)

    def test_the_review_page_says_when_the_diff_of_the_head_is_missing(self):
        self.assertIn('R["missing-diff"]', self.page(f"/review?review={ID}"))

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

    def test_the_page_reads_the_conversation_from_github(self):
        os.environ.update(CRAFTSMAN_GH=f"{sys.executable} {pathlib.Path(__file__).resolve().parent / 'fake_gh.py'}",
                          FAKE_GH_LOG=str(self.tmp / "gh.log"), FAKE_GH_STATE=str(self.tmp / "gh.json"))
        (self.tmp / "gh.json").write_text(json.dumps({"issue_comments": [
            {"id": 501, "user": {"login": "anna"}, "created_at": "2026-10-30T09:00:00Z", "body": "Hi",
             "html_url": "https://github.com/org/booking/pull/123#issuecomment-1"}]}))

        status, body = self.call("/api/review/github", {"id": ID})

        self.assertEqual((status, [c["author"] for c in body["comments"]]), (200, ["anna"]))
        self.assertEqual(self.call(f"/api/review?id={ID}")[1]["github"]["comments"][0]["body"], "Hi")

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
        self.assertTrue(eventually(lambda: (self.tmp / "fake.log").exists()))
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
        head = subprocess.run(["git", "-C", str(origin), "rev-parse", "feature/x"], capture_output=True,
                              text=True).stdout.strip()
        subprocess.run(["git", "-C", str(origin), "update-ref", "refs/pull/124/head", head], check=True)
        gh_state = self.tmp / "gh-state.json"
        gh_state.write_text(json.dumps({"pulls": {"124": {
            "number": 124, "title": "Cancel", "html_url": "https://github.com/org/booking/pull/124",
            "base": {"ref": "main"}, "head": {"ref": "feature/x", "sha": head, "label": "org:feature/x"}}}}))
        os.environ.update(CRAFTSMAN_CLONES=str(self.tmp / "clones"), CRAFTSMAN_GITHUB=f"file://{self.tmp / 'github'}",
                          CRAFTSMAN_GH=f"{sys.executable} {pathlib.Path(__file__).resolve().parent / 'fake_gh.py'}",
                          FAKE_GH_STATE=str(gh_state), FAKE_GH_LOG=str(self.tmp / "gh-log.jsonl"))
        self.addCleanup(lambda: [os.environ.pop(key, None) for key in ("CRAFTSMAN_GH", "FAKE_GH_STATE", "FAKE_GH_LOG")])

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
