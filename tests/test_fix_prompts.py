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


def one(state_):
    """The fix prompts of a review small enough for one comment."""
    bodies = fix_prompts.comments(state_)
    assert len(bodies) == 1, bodies
    return bodies[0]


class FixPromptsTest(unittest.TestCase):
    def test_every_category_gets_one_prompt_of_its_own(self):
        body = one(state(finding("f1", "naming", "nit"), finding("f2", "security", "must-fix"),
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

    def test_a_prompt_names_no_severity_but_keeps_the_worst_first(self):
        body = one(state(finding("f1", "naming", "nit"), finding("f2", "naming", "must-fix", line=3),
                                         finding("f3", "naming", "should-fix", line=5)))

        prompt = blocks(body)[0]
        for severity in fix_prompts.SEVERITY:
            with self.subTest(severity=severity):
                self.assertNotIn(severity, body)
        self.assertLess(prompt.index("Title f2"), prompt.index("Title f3"))
        self.assertLess(prompt.index("Title f3"), prompt.index("Title f1"))
        self.assertIn("1. src/A.java:3 — Title f2", prompt)

    def test_the_developers_findings_without_a_category_go_in_as_other_fixes(self):
        body = one(state(finding("f1", "yours", "nit", by="developer"),
                                         finding("f2", "yours", "should-fix", by="developer"),
                                         finding("f3", "naming", "nit")))

        self.assertNotIn("yours", body)
        self.assertIn("#### Other fixes · 2 findings", body)
        other = next(p for p in blocks(body) if "Title f1" in p)
        self.assertNotIn("All of them are about", other)
        self.assertIn("Make every fix below and nothing else", other)
        self.assertIn("All of them are about naming", next(p for p in blocks(body) if "Title f3" in p))

    def test_only_what_is_sent_to_the_author_and_left_in_the_prompts_goes_in(self):
        body = one(state(
            finding("f1", "naming", "nit"), finding("f2", "naming", "nit", status="sent"),
            finding("f3", "naming", "nit", status="proposed"), finding("f4", "naming", "nit", status="deleted"),
            finding("f5", "naming", "nit", **{"in-prompt": False})))

        self.assertEqual([t for t in ("Title f1", "Title f2", "Title f3", "Title f4", "Title f5") if t in body],
                         ["Title f1", "Title f2"])

    def test_nothing_to_fix_makes_no_comment(self):
        self.assertEqual(fix_prompts.comments(state(finding("f1", "naming", "nit", status="proposed"))), [])

    def test_a_comment_with_a_code_block_does_not_end_the_prompt(self):
        body = one(state(finding("f1", "naming", "nit", comment="Use:\n```java\nvar a = 1;\n```")))

        self.assertEqual(len(blocks(body)), 1)
        self.assertIn("var a = 1;", blocks(body)[0])
        self.assertIn("Run the tests", blocks(body)[0])

    def test_every_other_place_of_a_finding_is_named_too(self):
        two = finding("f1", "naming", "nit")
        two["locations"].append({"path": "src/C.java", "line": 44, "side": "RIGHT", "commit": "bbb"})

        self.assertIn("src/C.java:44", blocks(one(state(two)))[0])

    def test_a_finding_that_says_it_applies_everywhere_is_fixed_everywhere_and_its_words_go_in_as_they_are(self):
        said = "Let's not put implementation details in the OpenAPI docs. Please remove them everywhere you added them."

        prompt = blocks(one(state(finding("f1", "api-docs", "should-fix", comment=said))))[0]

        self.assertIn(said, " ".join(line.strip() for line in prompt.splitlines()))
        self.assertIn("applies to every place in the change, fixing every such place is part of that fix", prompt)

    def test_the_comment_is_known_again_by_its_marker(self):
        body = one(state(finding("f1", "naming", "nit")))

        self.assertTrue(fix_prompts.is_fix_prompts(body))
        self.assertFalse(fix_prompts.is_fix_prompts("Thanks, looks good."))

    def test_prompts_too_long_for_one_github_comment_go_in_several_each_with_whole_prompts(self):
        findings = [finding(f"f{n}", category, "nit", line=n, comment="Rename it. " * 30)
                    for n, category in enumerate(["naming", "naming", "security", "tests", "tests"], 1)]

        bodies = fix_prompts.comments(state(*findings), limit=1500)

        self.assertGreater(len(bodies), 1)
        for number, body in enumerate(bodies, 1):
            with self.subTest(part=number):
                self.assertLessEqual(len(body), 1500)
                self.assertTrue(fix_prompts.is_fix_prompts(body))
                self.assertIn(f"part {number} of {len(bodies)}", body)
        prompts = [prompt for body in bodies for prompt in blocks(body)]
        self.assertEqual([p.split("All of them are about ")[1].split(".")[0] for p in prompts], ["naming", "tests", "security"])

    def test_no_part_is_longer_than_github_takes_whatever_the_limit(self):
        findings = [finding(f"f{n}", category, "nit", line=n, comment="Rename it. " * 30)
                    for n, category in enumerate(["naming", "naming", "security", "tests", "tests"], 1)]

        for limit in range(1500, 4000, 11):
            with self.subTest(limit=limit):
                self.assertLessEqual(max(map(len, fix_prompts.comments(state(*findings), limit=limit))), limit)

    def test_one_comment_holds_every_prompt_when_they_fit(self):
        body = one(state(finding("f1", "naming", "nit"), finding("f2", "security", "nit")))

        self.assertEqual(len(blocks(body)), 2)
        self.assertNotIn("part 1", body)

    def test_github_takes_a_comment_of_at_most_65536_characters(self):
        self.assertEqual(fix_prompts.LIMIT, 65536)


if __name__ == "__main__":
    unittest.main()
