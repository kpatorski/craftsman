"""Tests for verify_quotes.py: whether what a subagent quotes is where it says -- see EXECUTION.md, "Independent
directive review" and "Delegated read-only preparation". Checking a quote is a lookup, not a judgement.

Run: python3 -m unittest discover -s tests
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import verify_quotes  # noqa: E402

CANCEL = """package booking;

public class CancellationService {
    public void cancel(String reservationId, String userId) {
        if (reservationId == null) return;
        repository.delete(reservationId);
    }
}
"""
RULE = """---
id: value-objects
---

## Rules

- A parameter that carries a domain value is a value object,
  not a primitive.
"""


class QuotesCase(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "src").mkdir()
        (self.root / "src" / "CancellationService.java").write_text(CANCEL)
        self.rule = self.root / "value-objects.md"
        self.rule.write_text(RULE)


class QuoteTest(QuotesCase):
    def check(self, items):
        return verify_quotes.check_quotes(items, self.root)

    def test_a_quote_at_its_line_holds_and_one_elsewhere_says_where_it_is(self):
        held, moved = self.check([
            {"path": "src/CancellationService.java", "line": 4, "quote": "String reservationId, String userId"},
            {"path": "src/CancellationService.java", "line": 1, "quote": "repository.delete(reservationId);"}])
        self.assertEqual((held["found"], held["at"]), (True, [4]))
        self.assertEqual((moved["found"], moved["at"]), (False, [6]))

    def test_a_quote_without_a_line_is_found_anywhere_and_spacing_does_not_matter(self):
        [found] = self.check([{"path": "value-objects.md",
                               "quote": "a domain value is a value object, not a primitive"}])
        self.assertEqual((found["found"], found["at"]), (True, [7]))

    def test_a_quote_copied_with_its_own_line_breaks_is_found(self):
        [found] = self.check([{"path": "value-objects.md", "line": 7,
                               "quote": "a value object,\n    not  a primitive"}])
        self.assertTrue(found["found"])

    def test_a_quote_not_in_the_file_or_a_file_that_is_not_there_does_not_hold(self):
        missing, nowhere = self.check([{"path": "src/CancellationService.java", "quote": "userId.trim()"},
                                       {"path": "src/Gone.java", "line": 3, "quote": "x"}])
        self.assertEqual((missing["found"], missing["at"]), (False, []))
        self.assertEqual(nowhere["found"], False)
        self.assertIn("no such file", nowhere["problem"])

    def test_a_path_outside_the_root_is_not_read(self):
        [outside] = self.check([{"path": "../../etc/passwd", "quote": "root"}])
        self.assertFalse(outside["found"])
        self.assertIn("outside", outside["problem"])


class ReviewerTest(QuotesCase):
    def check(self, text):
        return verify_quotes.check_reviewer(text, self.root, {"value-objects": str(self.rule)})

    def test_a_violation_whose_rule_and_line_are_there_holds(self):
        [line] = self.check('VIOLATION | value-objects | src/CancellationService.java:4 | "A parameter that carries '
                            'a domain value is a value object, not a primitive." | takes two Strings | wrap them\n'
                            "CLEAN | naming | every new name\n")
        self.assertEqual((line["kind"], line["holds"], line["problems"]), ("VIOLATION", True, []))

    def test_a_misquoted_rule_a_line_past_the_end_or_an_unknown_directive_is_named(self):
        lines = self.check(
            'VIOLATION | value-objects | src/CancellationService.java:4 | "Never use a String." | x | y\n'
            'VIOLATION | value-objects | src/CancellationService.java:40 | "not a primitive." | x | y\n'
            'VIOLATION | security | src/CancellationService.java:4 | "Check input." | x | y\n')
        self.assertEqual([line["holds"] for line in lines], [False, False, False])
        self.assertIn("rule", lines[0]["problems"][0])
        self.assertIn("line 40", lines[1]["problems"][0])
        self.assertIn("security", lines[2]["problems"][0])

    def test_a_convention_needs_its_existing_line_too(self):
        [line] = self.check('CONVENTION | value-objects | src/CancellationService.java:4 | "not a primitive." | x | '
                            "src/Other.java:2\n")
        self.assertFalse(line["holds"])
        self.assertIn("src/Other.java", line["problems"][0])


class CommandLineTest(QuotesCase):
    def test_quotes_come_in_on_stdin_and_the_answer_is_json(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / "verify_quotes.py"), "--root", str(self.root)],
                              input=json.dumps([{"path": "value-objects.md", "quote": "not a primitive"}]),
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(json.loads(done.stdout)[0]["found"])

    def test_a_reviewers_answer_comes_in_on_stdin(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / "verify_quotes.py"), "--root", str(self.root),
                               "--reviewer", json.dumps({"value-objects": str(self.rule)})],
                              input='VIOLATION | value-objects | src/CancellationService.java:4 | "not a primitive." '
                                    "| x | y\n", capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(json.loads(done.stdout)[0]["holds"])


if __name__ == "__main__":
    unittest.main()
