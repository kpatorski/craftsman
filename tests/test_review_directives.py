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
        self.assertEqual(set(printed[0]), {"id", "title", "path"})


if __name__ == "__main__":
    unittest.main()
