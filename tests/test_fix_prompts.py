"""Tests for fix_prompts.py: the findings the developer sends, turned into one prompt per category for the author's own
AI coding agent, so each category is fixed as one atomic commit.

Run: python3 -m unittest discover -s tests
"""
import pathlib
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import fix_prompts  # noqa: E402

SOURCE = {"kind": "pull-request", "url": "https://github.example.com/org/booking/pull/7", "repository": "org/booking",
          "number": 7, "title": "Cancel a reservation"}


def finding(finding_id, category, severity, status="to-send", path="src/A.java", line=10, comment="Fix it.", **more):
    return {"id": finding_id, "category": category, "severity": severity, "status": status, "title": f"Title {finding_id}",
            "comment": comment, "locations": [{"path": path, "line": line, "side": "RIGHT", "commit": "bbb"}], **more}


def state(*findings):
    return {"source": SOURCE, "head": "bbbbbbbbbbbb", "findings": list(findings)}


def closes(line, fence):
    """As GitHub reads it: a run of at least as many backticks, indented by at most three spaces, ends the block."""
    bare = line.strip()
    return len(line) - len(line.lstrip(" ")) <= 3 and bare and set(bare) == {"`"} and len(bare) >= len(fence)


def blocks(body):
    """The prompts of a comment: the text inside each fenced block, in order."""
    out, inside, fence = [], None, None
    for line in body.splitlines():
        if inside is None and line.startswith("```"):
            inside, fence = [], line
        elif inside is not None and closes(line, fence):
            out.append("\n".join(inside))
            inside = None
        elif inside is not None:
            inside.append(line)
    return out


class FixPromptsTest(unittest.TestCase):
    def test_every_category_gets_one_prompt_of_its_own(self):
        body = fix_prompts.comment(state(finding("f1", "naming", "nit"), finding("f2", "security", "must-fix"),
                                         finding("f3", "naming", "should-fix", path="src/B.java", line=3)))

        prompts = blocks(body)
        self.assertEqual(len(prompts), 2)
        self.assertIn("security", prompts[0])
        self.assertIn("Title f2", prompts[0])
        self.assertIn("naming", prompts[1])
        self.assertLess(prompts[1].index("Title f3"), prompts[1].index("Title f1"))
        self.assertIn("src/B.java:3", prompts[1])
        self.assertIn("org/booking", prompts[1])
        self.assertIn("one commit", prompts[1])

    def test_only_what_is_sent_to_the_author_and_left_in_the_prompts_goes_in(self):
        body = fix_prompts.comment(state(
            finding("f1", "naming", "nit"), finding("f2", "naming", "nit", status="sent"),
            finding("f3", "naming", "nit", status="proposed"), finding("f4", "naming", "nit", status="deleted"),
            finding("f5", "naming", "nit", **{"in-prompt": False})))

        self.assertEqual([t for t in ("Title f1", "Title f2", "Title f3", "Title f4", "Title f5") if t in body],
                         ["Title f1", "Title f2"])

    def test_nothing_to_fix_makes_no_comment(self):
        self.assertIsNone(fix_prompts.comment(state(finding("f1", "naming", "nit", status="proposed"))))

    def test_a_comment_with_a_code_block_does_not_end_the_prompt(self):
        body = fix_prompts.comment(state(finding("f1", "naming", "nit", comment="Use:\n```java\nvar a = 1;\n```")))

        self.assertEqual(len(blocks(body)), 1)
        self.assertIn("var a = 1;", blocks(body)[0])
        self.assertIn("Run the tests", blocks(body)[0])

    def test_every_other_place_of_a_finding_is_named_too(self):
        two = finding("f1", "naming", "nit")
        two["locations"].append({"path": "src/C.java", "line": 44, "side": "RIGHT", "commit": "bbb"})

        self.assertIn("src/C.java:44", blocks(fix_prompts.comment(state(two)))[0])

    def test_the_comment_is_known_again_by_its_marker(self):
        body = fix_prompts.comment(state(finding("f1", "naming", "nit")))

        self.assertTrue(fix_prompts.is_fix_prompts(body))
        self.assertFalse(fix_prompts.is_fix_prompts("Thanks, looks good."))


if __name__ == "__main__":
    unittest.main()
