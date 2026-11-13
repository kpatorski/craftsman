"""Tests for dedupe_findings.py, the mechanical part of making one finding of each problem across use cases -- see
REVIEW.md, "Findings", and the code-review bundle's `deduplicate-findings`. The script lists the candidates and carries
out a join; whether two findings are one problem is the agent's call.

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
import dedupe_findings  # noqa: E402
import review_state  # noqa: E402
from review_state import Refused  # noqa: E402

DIFF = "diff --git a/src/Cancel.java b/src/Cancel.java\n"


class DedupeCase(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.review = self.root / "review"
        diff = self.root / "change.diff"
        diff.write_text(DIFF)
        review_state.change(self.review, "init", {"source": {"kind": "pull-request"}, "base": "a", "head": "b",
                                                  "diff": str(diff)})
        review_state.change(self.review, "set", {"structure": {"use-cases": [
            {"id": "u1", "name": "Cancel", "says": ".", "entry": "src/Cancel.java:1", "files": ["src/Cancel.java"]},
            {"id": "u2", "name": "Book", "says": ".", "entry": "src/Book.java:1", "files": ["src/Book.java"]},
            {"id": "u3", "name": "Release", "says": ".", "entry": "src/Release.java:1", "files": ["src/Release.java"]},
        ]}})

    def finding(self, path, line=3, directive="value-objects", kind="violation", by="agent"):
        payload = {"title": f"String id in {path}", "comment": "Make it a value object.",
                   "locations": [{"path": path, "line": line, "side": "RIGHT", "commit": "b"}], "severity": "nit"}
        if by == "agent":
            payload.update(category="design", description="d", kind=kind, directive=directive)
        return review_state.change(self.review, "add-finding", payload, by=by)

    def findings(self):
        return {f["id"]: f for f in review_state.read(self.review)["findings"]}


class CandidatesTest(DedupeCase):
    def test_findings_of_one_directive_and_kind_in_different_use_cases_are_candidates_in_walk_order(self):
        release = self.finding("src/Release.java")
        cancel = self.finding("src/Cancel.java")
        self.finding("src/Book.java", kind="scout")
        self.finding("src/Book.java", directive="naming")
        groups = dedupe_findings.candidates(review_state.read(self.review))
        self.assertEqual([[f["id"] for f in g["findings"]] for g in groups], [[cancel, release]])
        self.assertEqual((groups[0]["directive"], groups[0]["kind"]), ("value-objects", "violation"))
        self.assertEqual([f["use-case"] for f in groups[0]["findings"]], ["u1", "u3"])

    def test_findings_in_one_use_case_or_set_aside_are_no_candidates(self):
        self.finding("src/Cancel.java", line=3)
        self.finding("src/Cancel.java", line=9)
        gone = self.finding("src/Book.java")
        review_state.change(self.review, "set-status", {"status": "deleted"}, by="developer", item_id=gone)
        self.assertEqual(dedupe_findings.candidates(review_state.read(self.review)), [])


class JoinTest(DedupeCase):
    def test_the_copies_go_into_the_earliest_finding_with_every_place_in_walk_order(self):
        release, cancel, book = (self.finding("src/Release.java"), self.finding("src/Cancel.java"),
                                 self.finding("src/Book.java"))
        report = dedupe_findings.join(self.review, [[release, book, cancel]])
        found = self.findings()
        self.assertEqual([loc["path"] for loc in found[cancel]["locations"]],
                         ["src/Cancel.java", "src/Book.java", "src/Release.java"])
        self.assertEqual({(found[f]["status"], found[f].get("merged-into")) for f in (release, book)},
                         {("merged", cancel)})
        self.assertEqual(report, {"joined": [{"into": cancel, "merged": [book, release]}], "kept-apart": []})

    def test_the_developers_finding_is_the_one_the_others_go_into(self):
        cancel = self.finding("src/Cancel.java")
        book = self.finding("src/Book.java")
        review_state.change(self.review, "update-finding", {"comment": "Wrap the id."}, by="developer", item_id=book)
        dedupe_findings.join(self.review, [[cancel, book]])
        found = self.findings()
        self.assertEqual((found[cancel]["merged-into"], found[book]["comment"]), (book, "Wrap the id."))
        self.assertEqual([loc["path"] for loc in found[book]["locations"]], ["src/Book.java", "src/Cancel.java"])

    def test_two_findings_the_developer_wrote_are_kept_apart(self):
        cancel = self.finding("src/Cancel.java")
        book = self.finding("src/Book.java")
        for found in (cancel, book):
            review_state.change(self.review, "update-finding", {"comment": f"Mine {found}."}, by="developer",
                                item_id=found)
        report = dedupe_findings.join(self.review, [[cancel, book]])
        self.assertEqual(report, {"joined": [], "kept-apart": [[cancel, book]]})
        self.assertEqual({f["status"] for f in self.findings().values()}, {"proposed"})

    def test_a_join_that_is_no_candidate_group_changes_nothing(self):
        cancel = self.finding("src/Cancel.java")
        book = self.finding("src/Book.java")
        scout = self.finding("src/Release.java", kind="scout")
        other = self.finding("src/Release.java", directive="naming")
        for groups, named in (([[cancel, scout]], "kind"), ([[cancel, other]], "directive"), ([[cancel]], "two"),
                              ([[cancel, "f99"]], "f99"), ([[cancel, book], [book, scout]], "twice")):
            with self.subTest(groups=groups):
                with self.assertRaises(Refused) as refused:
                    dedupe_findings.join(self.review, groups)
                self.assertIn(named, str(refused.exception))
                self.assertEqual({f["status"] for f in self.findings().values()}, {"proposed"})

    def test_the_command_line_lists_candidates_and_joins_them(self):
        cancel = self.finding("src/Cancel.java")
        book = self.finding("src/Book.java")
        run = lambda *args: subprocess.run([sys.executable, str(SCRIPTS / "dedupe_findings.py"), str(self.review),
                                            *args], capture_output=True, text=True, timeout=30)  # noqa: E731
        listed = run("candidates")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(len(json.loads(listed.stdout)), 1)
        joined = run("join", json.dumps([[cancel, book]]))
        self.assertEqual(joined.returncode, 0, joined.stderr)
        self.assertEqual(json.loads(joined.stdout)["joined"], [{"into": cancel, "merged": [book]}])


if __name__ == "__main__":
    unittest.main()
