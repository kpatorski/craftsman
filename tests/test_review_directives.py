"""Tests for review_directives.py: the directives a review checks the code against. The list is worked out the same way
for the review's agent and for the review page, so the agent never picks the directives itself and the developer sees
exactly what is checked.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import review_directives  # noqa: E402
import review_state  # noqa: E402

SOURCE = {"kind": "pull-request", "url": "https://github.com/org/booking/pull/123", "repository": "org/booking",
          "number": 123}


def directive(folder, entry_id, title):
    (folder / entry_id).mkdir(parents=True)
    (folder / entry_id / "directive.md").write_text(
        f"---\nid: {entry_id}\ntitle: {title}\ndescription: >\n  What {entry_id} asks.\n"
        "applies-when: always\nprecedence: none\nenabled-by-default: true\n---\n")


def table(rows):
    if not rows:
        return "Empty — nothing here.\n"
    return "| No | Id | Title |\n|----|----|-------|\n" + "".join(
        f"| {n} | [{entry_id}]({entry_id}/directive.md) | {title} |\n" for n, (entry_id, title) in enumerate(rows, 1))


def bundle(content, bundle_id, enabled, disabled=(), protocols=()):
    folder = content / "bundles" / bundle_id
    for entry_id, title in [*enabled, *disabled]:
        directive(folder / "directives", entry_id, title)
    for entry_id, title in protocols:
        (folder / "protocols" / entry_id).mkdir(parents=True)
        (folder / "protocols" / entry_id / "protocol.md").write_text(
            f"---\nid: {entry_id}\ntitle: {title}\ndescription: >\n  What {entry_id} does.\n---\n")

    def rows(kind, listed):
        return "".join(f"| {n} | [{entry_id}]({kind}s/{entry_id}/{kind}.md) | {title} |\n"
                       for n, (entry_id, title) in enumerate(listed, 1))

    def tables(kind, on, off):
        header = "| No | Id | Title |\n|----|----|-------|\n"
        return (f"**Enabled**\n\n{header + rows(kind, on) if on else 'Empty — none.'}\n\n"
                f"**Disabled**\n\n{header + rows(kind, off) if off else 'Empty — none.'}\n")

    (folder / "bundle.md").write_text(
        f"---\nid: {bundle_id}\ntitle: {bundle_id}\ndescription: >\n  The {bundle_id} bundle.\n---\n\n"
        f"## Protocols\n\n{tables('protocol', protocols, ())}\n## Directives\n\n{tables('directive', enabled, disabled)}")


def workshop(content):
    """A workshop with directives at the top level and in bundles, enabled and disabled, and a code-review bundle."""
    top = content / "directives"
    for entry_id, title in (("naming", "Names say what"), ("no-explanatory-comments", "No comments"),
                            ("prefer-lombok", "Lombok")):
        directive(top, entry_id, title)
    (top / "index.md").write_text(
        "## Directives\n\n### Production code\n\n**Enabled**\n\n"
        + table([("naming", "Names say what"), ("no-explanatory-comments", "No comments")])
        + "\n**Disabled**\n\n" + table([("prefer-lombok", "Lombok")]))
    bundle(content, "testing", [("test-naming", "Tests named by state")])
    bundle(content, "legacy", [("characterize", "Pin behaviour first")])
    bundle(content, "code-review", [("review-comment", "How a comment reads")],
           protocols=[("open-review", "Open a review"), ("review-use-case", "Review one use case")])
    (content / "bundles" / "index.md").write_text(
        "## Bundles\n\n**Enabled**\n\n| No | Id | Title | Path |\n|----|----|-------|------|\n"
        "| 1 | testing | Testing | [testing/bundle.md](testing/bundle.md) |\n"
        "| 2 | code-review | Review | [code-review/bundle.md](code-review/bundle.md) |\n\n"
        "**Disabled**\n\n| No | Id | Title | Path |\n|----|----|-------|------|\n"
        "| 3 | legacy | Legacy | [legacy/bundle.md](legacy/bundle.md) |\n")


class ReviewDirectivesTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.content = self.root / "content"
        workshop(self.content)
        self.review = self.root / "pr-123"
        diff = self.root / "change.diff"
        diff.write_text("diff --git a/A.java b/A.java\n")
        review_state.change(self.review, "init", {"source": SOURCE, "base": "aaa", "head": "bbb", "diff": str(diff)})

    def tearDown(self):
        shutil.rmtree(self.root)

    def listed(self):
        return {d["id"]: d for d in review_directives.listed(self.content, review_state.read(self.review))}

    def test_every_directive_of_the_workshop_is_listed_with_whether_the_workshop_enables_it(self):
        listed = self.listed()

        self.assertEqual({entry_id: d["enabled"] for entry_id, d in listed.items()}, {
            "naming": True, "no-explanatory-comments": True, "prefer-lombok": False, "test-naming": True,
            "characterize": False})
        self.assertEqual((listed["test-naming"]["bundle"], listed["naming"]["bundle"]), ("testing", None))
        self.assertEqual(listed["naming"]["title"], "Names say what")
        self.assertTrue(pathlib.Path(listed["naming"]["path"]).is_file())

    def test_the_review_bundles_own_directives_say_how_findings_are_written_and_are_not_checked(self):
        self.assertNotIn("review-comment", self.listed())

    def test_the_review_checks_what_the_workshop_enables_until_the_developer_switches_it(self):
        self.assertEqual([d["id"] for d in review_directives.to_check(self.content, review_state.read(self.review))],
                         ["naming", "no-explanatory-comments", "test-naming"])

        review_state.change(self.review, "switch-directive", {"id": "naming", "on": False}, "developer")
        review_state.change(self.review, "switch-directive", {"id": "prefer-lombok", "on": True}, "developer")

        listed = self.listed()
        self.assertEqual((listed["naming"]["on"], listed["prefer-lombok"]["on"]), (False, True))
        self.assertEqual([d["id"] for d in review_directives.to_check(self.content, review_state.read(self.review))],
                         ["no-explanatory-comments", "prefer-lombok", "test-naming"])

    def test_the_review_lists_the_protocols_it_runs(self):
        self.assertEqual(review_directives.protocols(self.content),
                         [{"id": "open-review", "title": "Open a review", "enabled": True},
                          {"id": "review-use-case", "title": "Review one use case", "enabled": True}])

    def test_the_developers_default_set_for_reviews_comes_before_the_workshop_and_after_the_review(self):
        defaults = {"naming": False, "prefer-lombok": True}
        review_state.change(self.review, "switch-directive", {"id": "prefer-lombok", "on": False}, "developer")

        listed = {d["id"]: d for d in review_directives.listed(self.content, review_state.read(self.review), defaults)}

        self.assertEqual({entry_id: (d["default"], d["on"]) for entry_id, d in listed.items()}, {
            "naming": (False, False), "no-explanatory-comments": (True, True), "prefer-lombok": (True, False),
            "test-naming": (True, True), "characterize": (False, False)})
        self.assertEqual([d["id"] for d in review_directives.to_check(self.content, review_state.read(self.review),
                                                                      defaults)],
                         ["no-explanatory-comments", "test-naming"])

    def test_the_agent_reads_the_list_from_the_command_line(self):
        home = self.root / "home"
        home.mkdir()
        (home / "settings.json").write_text(json.dumps({"review-directives": {"test-naming": False}}))

        done = subprocess.run([sys.executable, str(SCRIPTS / "review_directives.py"), str(self.review),
                               "--content", str(self.content)], capture_output=True, text=True, timeout=30,
                              env={**os.environ, "CRAFTSMAN_HOME": str(home)})

        self.assertEqual(done.returncode, 0, done.stderr)
        printed = json.loads(done.stdout)
        self.assertEqual([d["id"] for d in printed], ["naming", "no-explanatory-comments"])
        self.assertEqual(set(printed[0]), {"id", "title", "path", "files", "reach"})

    def test_the_directives_with_no_row_are_named_before_any_review_is_open(self):
        self.scope([("naming", "production", "file")])
        home = self.root / "home"
        home.mkdir()
        (home / "settings.json").write_text(json.dumps({"review-directives": {"test-naming": False}}))

        done = subprocess.run([sys.executable, str(SCRIPTS / "review_directives.py"), "--content", str(self.content),
                               "--unscoped"], capture_output=True, text=True, timeout=30,
                              env={**os.environ, "CRAFTSMAN_HOME": str(home)})

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), ["no-explanatory-comments"])

    def scope(self, rows):
        (self.content / "bundles" / "code-review" / "directive-scope.md").write_text(
            "# How a review checks each directive\n\nText.\n\n| Directive | Files | Reach |\n|---|---|---|\n"
            + "".join(f"| `{entry_id}` | {files} | {reach} |\n" for entry_id, files, reach in rows))

    def test_each_directive_is_checked_on_the_files_and_with_the_reach_the_review_bundles_table_gives(self):
        self.scope([("naming", "production", "file"), ("test-naming", "tests", "flow")])

        listed = self.listed()

        self.assertEqual({entry_id: (d["files"], d["reach"], d["scoped"]) for entry_id, d in listed.items()}, {
            "naming": ("production", "file", True), "test-naming": ("tests", "flow", True),
            "no-explanatory-comments": ("all", "flow", False), "prefer-lombok": ("all", "flow", False),
            "characterize": ("all", "flow", False)})

    def test_a_directive_the_table_keeps_out_of_reviews_is_not_checked(self):
        self.scope([("naming", "none", "-")])

        self.assertEqual([d["id"] for d in review_directives.to_check(self.content, review_state.read(self.review))],
                         ["no-explanatory-comments", "test-naming"])

    def test_a_row_the_review_cannot_read_counts_as_no_row(self):
        self.scope([("naming", "everywhere", "file"), ("test-naming", "tests", "far")])

        listed = self.listed()

        self.assertEqual([(d["files"], d["reach"], d["scoped"]) for d in (listed["naming"], listed["test-naming"])],
                         [("all", "flow", False), ("all", "flow", False)])

    def test_the_directives_checked_without_a_row_are_named(self):
        self.scope([("naming", "production", "file"), ("prefer-lombok", "production", "file")])

        self.assertEqual(review_directives.unscoped(self.content, review_state.read(self.review)),
                         ["no-explanatory-comments", "test-naming"])

    def test_the_command_line_names_the_directives_checked_without_a_row(self):
        self.scope([("naming", "production", "file")])

        done = subprocess.run([sys.executable, str(SCRIPTS / "review_directives.py"), str(self.review),
                               "--content", str(self.content), "--unscoped"], capture_output=True, text=True,
                              timeout=30, env={**os.environ, "CRAFTSMAN_HOME": str(self.root / "home")})

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), ["no-explanatory-comments", "test-naming"])


def diff_of(files):
    """A diff of `(path, change, lines)`: `change` is `added`, `modified` or `deleted`."""
    out = ""
    for path, change, lines in files:
        out += f"diff --git a/{path} b/{path}\n"
        if change == "added":
            out += f"new file mode 100644\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{lines} @@\n" + "+x\n" * lines
        elif change == "deleted":
            out += f"deleted file mode 100644\n--- a/{path}\n+++ /dev/null\n@@ -1,{lines} +0,0 @@\n" + "-x\n" * lines
        else:
            out += f"--- a/{path}\n+++ b/{path}\n@@ -1,{lines} +1,{lines} @@\n" + "-x\n+y\n" * lines
    return out


class CheckPlanTest(unittest.TestCase):
    """The plan of a review's directive checks: which reviewers start, each with its directives and files."""

    FILES = [("src/main/Cancel.java", "modified", 3), ("src/main/CancelRequest.java", "added", 2),
             ("src/test/CancelTest.java", "added", 4), ("src/main/Release.java", "modified", 1),
             ("src/main/Old.java", "deleted", 5), ("docker-compose.yml", "modified", 1)]

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.content = self.root / "content"
        workshop(self.content)
        self.review = self.root / "pr-123"
        self.open(self.FILES)
        self.scope([("naming", "production", "file"), ("no-explanatory-comments", "all", "file"),
                    ("test-naming", "tests", "flow")])

    def tearDown(self):
        shutil.rmtree(self.root)

    def open(self, files, use_cases=None):
        diff = self.root / "change.diff"
        diff.write_text(diff_of(files))
        if self.review.exists():
            shutil.rmtree(self.review)
        review_state.change(self.review, "init", {"source": SOURCE, "base": "aaa", "head": "bbb", "diff": str(diff)})
        review_state.change(self.review, "set", {"structure": {"use-cases": use_cases or [
            {"id": "u1", "name": "Cancel", "says": "Cancels.", "entry": "src/main/Cancel.java:1",
             "files": ["src/main/Cancel.java", "src/main/CancelRequest.java", "src/test/CancelTest.java"]},
            {"id": "u2", "name": "Release", "says": "Releases.", "entry": "src/main/Release.java:1",
             "files": ["src/main/Release.java", "src/main/Cancel.java"]}]}})

    def scope(self, rows):
        (self.content / "bundles" / "code-review" / "directive-scope.md").write_text(
            "| Directive | Files | Reach |\n|---|---|---|\n"
            + "".join(f"| `{entry_id}` | {files} | {reach} |\n" for entry_id, files, reach in rows))

    def plan(self):
        return review_directives.plan(self.content, self.review, review_state.read(self.review))

    def reviewers(self):
        return [(r["reach"], [u["id"] for u in r["use-cases"]], [d["id"] for d in r["directives"]], r["files"])
                for r in self.plan()["reviewers"]]

    def test_file_directives_check_every_changed_file_of_their_kind_once_and_flow_ones_each_use_case(self):
        self.assertEqual(self.reviewers(), [
            ("file", [], ["naming", "no-explanatory-comments"],
             ["src/main/Cancel.java", "src/main/CancelRequest.java", "src/main/Release.java", "docker-compose.yml"]),
            ("file", [], ["no-explanatory-comments"], ["src/test/CancelTest.java"]),
            ("flow", ["u1"], ["test-naming"], ["src/test/CancelTest.java"])])

    def test_a_reviewer_is_told_where_each_of_its_directives_is(self):
        directive = self.plan()["reviewers"][0]["directives"][0]

        self.assertEqual(directive["id"], "naming")
        self.assertTrue(pathlib.Path(directive["path"]).is_file())

    def test_a_use_case_with_no_file_of_a_directives_kind_records_it_as_not_applicable(self):
        self.assertEqual([(c["use-case"], c["directive"]) for c in self.plan()["not-applicable"]],
                         [("u2", "test-naming"), ("untied", "test-naming")])
        self.assertTrue(all(c["note"] for c in self.plan()["not-applicable"]))

    def test_a_use_case_whose_files_an_earlier_one_has_says_where_they_are_checked(self):
        use_cases = review_state.read(self.review)["structure"]["use-cases"]
        self.open(self.FILES, use_cases=use_cases + [
            {"id": "u3", "name": "Test", "says": "Tests.", "entry": "src/test/CancelTest.java:1",
             "files": ["src/test/CancelTest.java"]}])

        checks = {(c["use-case"], c["directive"]): c["note"] for c in self.plan()["not-applicable"]}

        self.assertEqual(checks[("u3", "naming")], "no production files in this use case")
        self.assertEqual(checks[("u3", "test-naming")],
                         "its test files are checked with the use case that has them first")
        self.assertEqual(self.plan()["file-checks"]["u3"], ["no-explanatory-comments"])

    def test_each_use_case_is_told_which_file_directives_to_record_from_the_findings(self):
        self.assertEqual(self.plan()["file-checks"], {
            "u1": ["naming", "no-explanatory-comments"], "u2": ["naming", "no-explanatory-comments"],
            "untied": ["naming", "no-explanatory-comments"]})

    def test_a_flow_directive_checks_a_file_with_the_first_use_case_that_has_it_and_untied_files_last(self):
        self.scope([("naming", "production", "flow")])

        flow = [r["use-cases"] for r in self.plan()["reviewers"]
                if r["reach"] == "flow" and "naming" in [d["id"] for d in r["directives"]]]

        self.assertEqual(flow, [[{"id": "u1", "files": ["src/main/Cancel.java", "src/main/CancelRequest.java"]},
                                 {"id": "u2", "files": ["src/main/Release.java"]},
                                 {"id": "untied", "files": ["docker-compose.yml"]}]])

    def test_a_flow_directive_with_no_file_of_its_kind_in_the_change_starts_no_reviewer(self):
        self.open([entry for entry in self.FILES if "test" not in entry[0]])

        self.assertEqual([r[2] for r in self.reviewers() if r[0] == "flow"], [])
        self.assertEqual({c["use-case"] for c in self.plan()["not-applicable"] if c["directive"] == "test-naming"},
                         {"u1", "u2", "untied"})

    def test_one_reviewer_takes_several_use_cases_up_to_a_bounded_change_and_a_big_one_alone(self):
        big = review_directives.BATCH_LINES // 2 + 1
        self.open([("src/main/A.java", "added", big), ("src/main/B.java", "added", big),
                   ("src/main/C.java", "added", 1), ("src/main/D.java", "added", 3 * big)],
                  use_cases=[{"id": f"u{n}", "name": name, "says": ".", "entry": f"src/main/{name}.java:1",
                              "files": [f"src/main/{name}.java"]} for n, name in enumerate("ABCD", 1)])
        self.scope([("naming", "production", "flow")])

        self.assertEqual([r[1] for r in self.reviewers() if r[2] == ["naming"]], [["u1"], ["u2", "u3"], ["u4"]])

    def test_a_directive_with_no_row_checks_every_file_with_each_use_case(self):
        (self.content / "bundles" / "code-review" / "directive-scope.md").unlink()

        reviewers = self.reviewers()

        self.assertEqual([r[:3] for r in reviewers], [
            ("flow", ["u1", "u2", "untied"], ["naming", "no-explanatory-comments", "test-naming"])])
        self.assertEqual(reviewers[0][3], ["src/main/Cancel.java", "src/main/CancelRequest.java",
                                           "src/test/CancelTest.java", "src/main/Release.java", "docker-compose.yml"])

    def test_a_reviewer_gets_at_most_six_directives(self):
        for n in range(8):
            directive(self.content / "directives", f"extra-{n}", f"Extra {n}")
        index = self.content / "directives" / "index.md"
        index.write_text(index.read_text().replace(
            "| 2 | [no-explanatory-comments]", "".join(
                f"| 9{n} | [extra-{n}](extra-{n}/directive.md) | Extra {n} |\n" for n in range(8))
            + "| 2 | [no-explanatory-comments]"))
        self.scope([(f"extra-{n}", "production", "file") for n in range(8)])

        sizes = [len(r[2]) for r in self.reviewers() if r[0] == "file"]

        self.assertEqual(sizes, [6, 2])

    def test_the_files_of_one_reviewer_add_up_to_a_bounded_change(self):
        big = review_directives.BATCH_LINES // 2 + 1
        self.open([("src/main/A.java", "added", big), ("src/main/B.java", "added", big),
                   ("src/main/C.java", "added", 1)],
                  use_cases=[{"id": "u1", "name": "A", "says": "A.", "entry": "src/main/A.java:1",
                              "files": ["src/main/A.java", "src/main/B.java", "src/main/C.java"]}])

        files = [r[3] for r in self.reviewers() if r[0] == "file" and "naming" in r[2]]

        self.assertEqual(files, [["src/main/A.java"], ["src/main/B.java", "src/main/C.java"]])

    def test_a_test_file_is_told_by_its_folder_or_its_name(self):
        for path in ("src/test/java/A.java", "app/tests/a.py", "web/__tests__/a.js", "src/main/ATest.java",
                     "src/main/ATests.java", "src/ASpec.groovy", "web/a.test.ts", "web/a.spec.ts", "test_a.py"):
            with self.subTest(path=path):
                self.assertTrue(review_directives.is_test(path))
        for path in ("src/main/Contest.java", "src/main/Testing.java", "latest/a.py", "docs/testing.md"):
            with self.subTest(path=path):
                self.assertFalse(review_directives.is_test(path))

    def finding(self, directive, path, status=None):
        found = review_state.change(self.review, "add-finding", {
            "category": "naming", "title": "t", "description": "d", "comment": "c", "kind": "violation",
            "severity": "nit", "directive": directive,
            "locations": [{"path": path, "line": 1, "side": "RIGHT", "commit": "bbb"}]})
        if status:
            review_state.change(self.review, "set-status", {"status": status}, by="developer", item_id=found)

    def record(self, use_case, verdicts):
        review_directives.record_checks(self.content, self.review, use_case, verdicts)
        return {(c["use-case"], c["directive"]): (c["result"], c["note"])
                for c in review_state.read(self.review)["checks"]}

    def test_a_use_cases_checks_are_worked_out_from_the_findings_the_plan_and_the_reviewers_verdicts(self):
        self.finding("naming", "src/main/CancelRequest.java")
        self.assertEqual(self.record("u1", {"test-naming": "clean"}), {
            ("u1", "test-naming"): ("clean", None), ("u1", "naming"): ("findings", None),
            ("u1", "no-explanatory-comments"): ("clean", None)})

    def test_a_use_case_with_no_reviewer_of_its_own_records_the_plan(self):
        checks = self.record("u2", {})
        self.assertEqual(checks[("u2", "naming")], ("clean", None))
        self.assertEqual(checks[("u2", "test-naming")], ("not-applicable", "no test files in this use case"))

    def test_a_finding_naming_the_directive_wins_over_the_reviewers_verdict(self):
        self.finding("test-naming", "src/test/CancelTest.java")
        self.assertEqual(self.record("u1", {"test-naming": "clean"})[("u1", "test-naming")], ("findings", None))

    def test_a_finding_in_another_use_cases_files_counts_there_only(self):
        self.finding("naming", "src/main/Release.java")
        self.assertEqual(self.record("u1", {"test-naming": "clean"})[("u1", "naming")], ("clean", None))

    def test_a_directive_checked_on_its_own_leaves_the_plans_other_checks_alone(self):
        review_directives.record_checks(self.content, self.review, "u2", {}, directive="naming")
        self.assertEqual([(c["use-case"], c["directive"]) for c in review_state.read(self.review)["checks"]],
                         [("u2", "naming")])

    def test_a_deleted_finding_counts_for_nothing(self):
        self.finding("naming", "src/main/Cancel.java", status="deleted")
        self.assertEqual(self.record("u1", {"test-naming": "clean"})[("u1", "naming")], ("clean", None))

    def test_the_reviewers_reason_and_failure_are_recorded(self):
        checks = self.record("u1", {"test-naming": {"not-applicable": "no test of a use case"},
                                    "naming": "failed"})
        self.assertEqual(checks[("u1", "test-naming")], ("not-applicable", "no test of a use case"))
        self.assertEqual(checks[("u1", "naming")], ("failed", None))

    def test_a_gap_a_stray_directive_or_a_reasonless_not_applicable_records_nothing(self):
        for verdicts, named in (({}, "test-naming"), ({"test-naming": "clean", "security": "clean"}, "security"),
                                ({"test-naming": {"not-applicable": ""}}, "reason"),
                                ({"test-naming": "fine"}, "fine")):
            with self.subTest(verdicts=verdicts):
                with self.assertRaises(review_state.Refused) as refused:
                    self.record("u1", verdicts)
                self.assertIn(named, str(refused.exception))
                self.assertEqual(review_state.read(self.review)["checks"], [])

    def test_a_directive_checked_on_its_own_records_only_its_own_checks(self):
        self.record("u1", {"test-naming": "clean"})
        review_directives.record_checks(self.content, self.review, "u1", {"test-naming": "failed"},
                                        directive="test-naming")
        checks = {(c["use-case"], c["directive"]): c["result"] for c in review_state.read(self.review)["checks"]}
        self.assertEqual(checks, {("u1", "test-naming"): "failed", ("u1", "naming"): "clean",
                                  ("u1", "no-explanatory-comments"): "clean"})
        review_directives.record_checks(self.content, self.review, "u2", {}, directive="test-naming")
        self.assertEqual(review_state.read(self.review)["checks"][-1]["result"], "not-applicable")

    def test_the_agent_records_a_use_cases_checks_from_the_command_line(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / "review_directives.py"), str(self.review),
                               "--content", str(self.content), "--record-checks", "u1", '{"test-naming": "clean"}'],
                              capture_output=True, text=True, timeout=30,
                              env={**os.environ, "CRAFTSMAN_HOME": str(self.root / "home")})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(json.loads(done.stdout)), 3)
        self.assertEqual(len(review_state.read(self.review)["checks"]), 3)

    def test_the_agent_reads_the_plan_from_the_command_line(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / "review_directives.py"), str(self.review),
                               "--content", str(self.content), "--plan"], capture_output=True, text=True,
                              timeout=30, env={**os.environ, "CRAFTSMAN_HOME": str(self.root / "home")})

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), json.loads(json.dumps(self.plan())))


if __name__ == "__main__":
    unittest.main()
