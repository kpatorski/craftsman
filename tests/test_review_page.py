"""Tests for pieces of the review page's script that work on their own: they are taken out of review_page.html and run
in Node, the way the page runs them; without Node these tests are skipped.

Run: python3 -m unittest discover -s tests
"""
import json
import pathlib
import re
import shutil
import subprocess
import unittest

PAGE = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts" / "review_page.html"
NODE = shutil.which("node")


def function(name):
    """One top-level function of the page's script, from its `function` line to the `}` that closes it."""
    found = re.search(rf"^function {name}\(.*?^}}$", PAGE.read_text(), re.S | re.M)
    if not found:
        raise AssertionError(f"the page has no function {name}")
    return found.group(0)


def run(name, *args):
    program = f"{function(name)}\nconsole.log(JSON.stringify({name}(...{json.dumps(args)})));"
    return json.loads(subprocess.run([NODE, "-e", program], capture_output=True, text=True, check=True).stdout)


@unittest.skipUnless(NODE, "node is not installed")
class FolderLabelsTest(unittest.TestCase):
    def test_a_short_folder_is_named_in_full(self):
        self.assertEqual(run("folderLabels", ["booking/desk/"]), {"booking/desk/": "booking/desk/"})

    def test_a_long_folder_is_named_by_its_first_and_last_two_parts(self):
        self.assertEqual(run("folderLabels", ["booking/desk/find/infrastructure/http/"]),
                         {"booking/desk/find/infrastructure/http/": "booking/…/infrastructure/http/"})

    def test_folders_that_differ_in_the_middle_keep_names_of_their_own(self):
        find, cancel = "booking/desk/find/infrastructure/http/", "booking/reservation/cancel/infrastructure/http/"

        labels = run("folderLabels", [find, cancel])

        self.assertNotEqual(labels[find], labels[cancel])
        self.assertEqual(labels[find], "booking/…/find/infrastructure/http/")
        self.assertEqual(labels[cancel], "booking/…/cancel/infrastructure/http/")

    def test_a_folder_named_in_full_drops_no_part(self):
        one, other = "booking/a/x/http/", "booking/b/x/http/"

        self.assertEqual(run("folderLabels", [one, other]), {one: one, other: other})


APP = "booking/src/main/java/com/example/booking/desk/"
TREE = [APP + "ReserveDesk.java", APP + "Desk.java", "booking/src/test/java/com/example/booking/desk/ReserveDeskTest.java",
        "booking/src/main/resources/db/changelog/001.sql", "pom.xml"]


def rows(paths, closed=()):
    return [(r["type"], r["name"], r["depth"], r.get("root", "")) for r in run("treeRows", paths, list(closed))]


@unittest.skipUnless(NODE, "node is not installed")
class TreeRowsTest(unittest.TestCase):
    def test_folders_come_first_and_a_folder_with_one_folder_and_no_files_shares_its_row(self):
        self.assertEqual(rows(TREE), [
            ("dir", "booking/src", 0, ""),
            ("dir", "main", 1, ""),
            ("dir", "java", 2, "src"),
            ("dir", "com.example.booking.desk", 3, ""),
            ("file", "Desk.java", 4, ""),
            ("file", "ReserveDesk.java", 4, ""),
            ("dir", "resources", 2, "res"),
            ("dir", "db/changelog", 3, ""),
            ("file", "001.sql", 4, ""),
            ("dir", "test", 1, ""),
            ("dir", "java", 2, "test"),
            ("dir", "com.example.booking.desk", 3, ""),
            ("file", "ReserveDeskTest.java", 4, ""),
            ("file", "pom.xml", 0, "")])

    def test_folders_are_sorted_by_name_whatever_order_the_diff_gives(self):
        self.assertEqual(rows(["web/b.ts", "api/a.ts"]), [
            ("dir", "api", 0, ""), ("file", "a.ts", 1, ""), ("dir", "web", 0, ""), ("file", "b.ts", 1, "")])

    def test_a_row_carries_the_path_of_the_deepest_folder_it_names(self):
        found = run("treeRows", TREE, [])

        self.assertEqual(found[3]["path"], APP[:-1])
        self.assertEqual(found[4]["path"], APP + "Desk.java")

    def test_a_closed_folder_hides_what_is_in_it(self):
        self.assertEqual(rows(TREE, ["booking/src/main"])[:3], [
            ("dir", "booking/src", 0, ""), ("dir", "main", 1, ""), ("dir", "test", 1, "")])


@unittest.skipUnless(NODE, "node is not installed")
class FileIconTest(unittest.TestCase):
    def test_a_file_with_a_type_of_its_own_shows_its_kind(self):
        self.assertEqual(run("iconOf", "a/Desk.java", {"kind": "record", "visibility": "public"}), "record")
        self.assertEqual(run("iconOf", "a/desk.ts", {"kind": "class", "visibility": None}), "class")

    def test_any_other_file_shows_what_it_is(self):
        cases = {"Dockerfile": "docker", "docker-compose.ci.yml": "docker", "pom.xml": "maven", "build.gradle.kts": "gradle",
                 "package.json": "npm", "a.ts": "ts", "a.tsx": "tsx", "a.js": "js", "a.yaml": "yaml", "a.yml": "yaml",
                 "a.json": "json", "a.sql": "sql", "a.xml": "xml", "README.md": "markdown", "run.sh": "shell",
                 "Desk.java": "file", "notes.txt": "file"}
        self.assertEqual({path: run("iconOf", "x/" + path, None) for path in cases}, cases)

    def test_a_test_file_is_named_as_the_review_names_one(self):
        tests = ["src/test/java/a/DeskTest.java", "a/DeskTests.kt", "a/DeskSpec.groovy", "web/desk.test.ts",
                 "web/desk.spec.tsx", "scripts/test_desk.py", "web/__tests__/desk.js", "test/Desk.java"]
        production = ["src/main/java/a/Desk.java", "a/Testing.java", "a/latest/Desk.java"]
        self.assertEqual([run("testFile", p) for p in tests], [True] * len(tests))
        self.assertEqual([run("testFile", p) for p in production], [False] * len(production))


@unittest.skipUnless(NODE, "node is not installed")
class PanelContextTest(unittest.TestCase):
    FILE = {"kind": "file", "path": "a/Desk.java"}
    LINES = {"kind": "file", "path": "a/Desk.java", "lines": [3, 5], "side": "RIGHT"}

    def test_a_thread_belongs_to_the_context_it_is_about(self):
        cases = [
            ({"kind": "review"}, {"kind": "review"}, True),
            ({"kind": "folder", "path": "a/"}, {"kind": "folder", "path": "a/"}, True),
            ({"kind": "folder", "path": "a/"}, {"kind": "folder", "path": "b/"}, False),
            ({"kind": "file", "path": "a/Desk.java"}, self.FILE, True),
            ({"kind": "file", "path": "a/Desk.java", "lines": [3, 5]}, self.FILE, False),
            ({"kind": "file", "path": "a/Desk.java", "lines": [3, 5]}, self.LINES, True),
            ({"kind": "file", "path": "a/Desk.java", "lines": [3, 4]}, self.LINES, False),
            ({"kind": "finding", "id": "f2"}, {"kind": "finding", "id": "f2"}, True),
            ({"kind": "finding", "id": "f2"}, {"kind": "finding", "id": "f3"}, False),
            ({"kind": "github", "id": 12}, {"kind": "github", "id": 12}, True),
            ({"kind": "directive", "id": "naming"}, {"kind": "review"}, False)]
        for about, ctx, belongs in cases:
            with self.subTest(about=about, ctx=ctx):
                self.assertEqual(run("aboutContext", about, ctx), belongs)

    def test_the_finding_tab_is_there_only_where_a_finding_can_be_written_or_is_shown(self):
        for ctx, tabs in [({"kind": "review"}, ["ask"]), ({"kind": "folder", "path": "a/"}, ["ask", "finding"]),
                          (self.FILE, ["ask", "finding"]), (self.LINES, ["ask", "finding"]),
                          ({"kind": "finding", "id": "f1"}, ["ask", "finding"]), ({"kind": "github", "id": 1}, ["ask"]),
                          ({"kind": "directive", "id": "naming"}, ["ask"]), ({"kind": "use-case", "id": "u1"}, ["ask"])]:
            with self.subTest(ctx=ctx):
                self.assertEqual(run("panelTabs", ctx), tabs)

    def test_a_draft_is_kept_by_the_file_or_the_folder_it_is_about(self):
        self.assertEqual(run("draftKey", self.FILE), "a/Desk.java")
        self.assertEqual(run("draftKey", self.LINES), "a/Desk.java")
        self.assertEqual(run("draftKey", {"kind": "folder", "path": "a/b/"}), "a/b/")
        self.assertIsNone(run("draftKey", {"kind": "finding", "id": "f1"}))
        self.assertIsNone(run("draftKey", {"kind": "review"}))


if __name__ == "__main__":
    unittest.main()
