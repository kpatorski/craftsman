"""Tests for _draft_preview.py: the developer's draft of a finding, written by a short, separate Claude call as the
finding the review's rules ask for, while the developer is still writing it.

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

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _draft_preview  # noqa: E402
import review_state  # noqa: E402

DIFF = """diff --git a/src/Other.java b/src/Other.java
--- a/src/Other.java
+++ b/src/Other.java
@@ -1,1 +1,1 @@
-class Old {}
+class Other {}
diff --git a/src/Cancel.java b/src/Cancel.java
--- a/src/Cancel.java
+++ b/src/Cancel.java
@@ -1,3 +1,5 @@
 package booking;
-class Cancel {
+public class Cancel {
+    void cancel(String id) {
+    }
 }
"""

ANSWER = {"title": "Class need not be public", "category": "encapsulation", "severity": "nit",
          "description": "Nothing outside the package uses it.", "comment": "Make `Cancel` package-private.",
          "repeats": ""}

FAKE = """import json, os, pathlib, sys, time
prompt = sys.stdin.read()
log = pathlib.Path(os.environ["PREVIEW_LOG"])
log.write_text(log.read_text() + json.dumps({"argv": sys.argv[1:], "prompt": prompt}) + "\\n" if log.exists()
               else json.dumps({"argv": sys.argv[1:], "prompt": prompt}) + "\\n")
if "slow" in prompt:
    time.sleep(5)
if "broken" in prompt:
    sys.stderr.write("model unavailable")
    sys.exit(1)
print(json.dumps([{"type": "system"}, {"type": "result", "is_error": False, "structured_output": %s}]))
""" % json.dumps(ANSWER)


class DraftPreviewTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.review = self.root / "review"
        diff = self.root / "change.diff"
        diff.write_text(DIFF)
        review_state.change(self.review, "init", {"source": {"kind": "pull-request"}, "base": "a", "head": "b",
                                                  "diff": str(diff)})
        review_state.change(self.review, "set", {"language": "Polish"})
        review_state.change(self.review, "add-finding", {
            "category": "naming", "title": "Name says nothing", "description": "d", "comment": "c",
            "locations": [{"path": "src/Cancel.java", "line": 3, "side": "RIGHT", "commit": "b"}],
            "kind": "violation", "severity": "should-fix"})
        review_state.change(self.review, "add-finding", {
            "category": "security", "title": "Elsewhere", "description": "d", "comment": "c",
            "locations": [{"path": "src/Other.java", "line": 1, "side": "RIGHT", "commit": "b"}],
            "kind": "violation", "severity": "must-fix"})
        self.content = self.root / "content"
        directive = self.content / "bundles" / "code-review" / "directives" / "review-comment"
        directive.mkdir(parents=True)
        (directive / "directive.md").write_text("Say what is wrong, why, and what to do.")
        fake = self.root / "fake.py"
        fake.write_text(FAKE)
        self.command = [sys.executable, str(fake)]
        self.log = self.root / "calls.jsonl"
        os.environ["PREVIEW_LOG"] = str(self.log)

    def tearDown(self):
        shutil.rmtree(self.root)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def preview(self, text, lines=(2, 3)):
        return _draft_preview.preview(self.review, "src/Cancel.java", text, list(lines) if lines else None,
                                      content=self.content, command=self.command)

    def test_the_finding_comes_back_as_the_call_wrote_it(self):
        self.assertEqual(self.preview("klasa nie musi byc publiczna"), ANSWER)

    def test_the_call_gets_the_draft_the_code_the_rules_and_the_findings_already_there(self):
        self.preview("klasa nie musi byc publiczna")

        prompt = self.calls()[0]["prompt"]
        for part in ("klasa nie musi byc publiczna", "src/Cancel.java, lines 2–3", "+public class Cancel {",
                     "-class Cancel {", "Say what is wrong, why, and what to do.", "f1", "Name says nothing",
                     "Polish", "naming", "security"):
            with self.subTest(part=part):
                self.assertIn(part, prompt)
        self.assertNotIn("class Other", prompt)
        self.assertNotIn("Elsewhere", prompt)

    def prompt_for(self, **asked):
        _draft_preview.preview(self.review, "src/Cancel.java", "tylko reminder", [2, 3], content=self.content,
                               command=self.command, **asked)
        return self.calls()[-1]["prompt"]

    def test_by_default_the_comment_keeps_the_reviewers_words_in_a_teammates_voice_as_long_as_the_draft(self):
        prompt = self.prompt_for()

        for part in ("Stay close to the reviewer's words", "no softening", "a teammate", "as long as the draft",
                     "the file, the line", "every place in the change, the comment says so",
                     "When the draft has a code block or asks for one, the comment has one",
                     "the style below wins"):
            with self.subTest(part=part):
                self.assertIn(part, prompt)

    def test_every_shape_of_the_comment_is_asked_for_in_words_of_its_own(self):
        for key, value, part in (("fidelity", "close", "Stay close to the reviewer's words"),
                                 ("fidelity", "balanced", "in your own words"),
                                 ("fidelity", "free", "Write it your way"),
                                 ("tone", "casual", "Casual"),
                                 ("tone", "teammate", "a teammate"),
                                 ("tone", "formal", "Formal and neutral"),
                                 ("detail", "brief", "One or two sentences"),
                                 ("detail", "normal", "as long as the draft"),
                                 ("detail", "detailed", "A paragraph or two"),
                                 ("code", True, "End with a short code block"),
                                 ("code", False, "No code block unless the draft has one")):
            with self.subTest(key=key, value=value):
                self.assertIn(part, self.prompt_for(style={key: value}))

    def test_a_shape_it_does_not_know_is_the_default_one(self):
        self.assertEqual(_draft_preview.shape({"tone": "rude", "detail": "detailed", "code": "yes"}),
                         dict(_draft_preview.review_state.COMMENT_STYLE_DEFAULT, detail="detailed"))

    def test_the_severity_the_reviewer_picked_sets_how_firmly_the_comment_says_it(self):
        for severity, part in (("must-fix", "has to change before the merge"), ("should-fix", "a clear recommendation"),
                               ("nit", "minor")):
            with self.subTest(severity=severity):
                prompt = self.prompt_for(severity=severity)
                self.assertIn(f"The reviewer weighs it {severity}", prompt)
                self.assertIn(part, prompt)

    def test_without_a_severity_picked_the_call_weighs_it_and_writes_it_that_firmly(self):
        for severity in (None, "blocker"):
            with self.subTest(severity=severity):
                prompt = self.prompt_for(severity=severity)
                self.assertNotIn("The reviewer weighs it", prompt)
                self.assertIn("with the strength of the severity you choose", prompt)

    def test_only_the_code_around_the_lines_goes_with_a_draft_about_them(self):
        long = "diff --git a/src/Long.java b/src/Long.java\n--- a/src/Long.java\n+++ b/src/Long.java\n@@ -0,0 +1,80 @@\n"
        long += "".join(f"+line number {n}\n" for n in range(1, 81))
        (self.review / "diff" / "b.diff").write_text(long)

        _draft_preview.preview(self.review, "src/Long.java", "here", [60, 61], content=self.content,
                               command=self.command)

        prompt = self.calls()[0]["prompt"]
        self.assertIn("line number 41\n", prompt)
        self.assertIn("line number 80\n", prompt)
        self.assertNotIn("line number 39\n", prompt)

    def test_a_draft_about_the_whole_file_says_so(self):
        self.preview("too big", lines=None)

        self.assertIn("src/Cancel.java, the whole file", self.calls()[0]["prompt"])

    def test_the_call_is_short_and_has_no_tools(self):
        self.preview("klasa nie musi byc publiczna")

        argv = self.calls()[0]["argv"]
        self.assertIn("-p", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertIn("--model", argv)
        self.assertEqual(json.loads(argv[argv.index("--json-schema") + 1])["required"],
                         ["title", "category", "severity", "description", "comment", "repeats"])

    def test_a_newer_draft_of_the_same_file_makes_the_older_preview_stale(self):
        older = {}
        thread = threading.Thread(target=lambda: older.update(answer=self.preview("slow first thought")))
        thread.start()
        deadline = time.time() + 5
        while not self.log.exists() and time.time() < deadline:
            time.sleep(0.02)

        newer = self.preview("second thought")
        thread.join(timeout=10)

        self.assertEqual(newer, ANSWER)
        self.assertIsNone(older["answer"])

    def test_a_failed_call_says_why(self):
        with self.assertRaises(_draft_preview.PreviewFailed) as failed:
            self.preview("broken")

        self.assertIn("model unavailable", str(failed.exception))


if __name__ == "__main__":
    unittest.main()
