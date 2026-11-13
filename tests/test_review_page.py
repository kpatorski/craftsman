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


def function(name, prefix=""):
    """One top-level function of the page's script, from its `function` line to the `}` that closes it."""
    found = re.search(rf"^{prefix}function {name}\(.*?^}}$", PAGE.read_text(), re.S | re.M)
    if not found:
        raise AssertionError(f"the page has no function {name}")
    return found.group(0)


def constant(name):
    """One top-level one-line `const` of the page's script."""
    found = re.search(rf"^const {name} = .*$", PAGE.read_text(), re.M)
    if not found:
        raise AssertionError(f"the page has no const {name}")
    return found.group(0)


def run(name, *args, uses=()):
    """Runs the page's function `name` on `args`; `uses` names the one-line consts it needs."""
    program = "\n".join([*map(constant, uses), function(name)]) + f"\nconsole.log(JSON.stringify({name}(...{json.dumps(args)})));"
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
            ({"kind": "chapter", "id": "c2"}, {"kind": "chapter", "id": "c2"}, True),
            ({"kind": "chapter", "id": "c2"}, {"kind": "chapter", "id": "c3"}, False),
            ({"kind": "directive", "id": "naming"}, {"kind": "review"}, False)]
        for about, ctx, belongs in cases:
            with self.subTest(about=about, ctx=ctx):
                self.assertEqual(run("aboutContext", about, ctx), belongs)

    def test_the_finding_tab_is_there_only_where_a_finding_can_be_written_or_is_shown(self):
        for ctx, tabs in [({"kind": "review"}, ["ask"]), ({"kind": "folder", "path": "a/"}, ["ask", "finding"]),
                          (self.FILE, ["ask", "finding"]), (self.LINES, ["ask", "finding"]),
                          ({"kind": "finding", "id": "f1"}, ["ask", "finding"]), ({"kind": "github", "id": 1}, ["ask"]),
                          ({"kind": "directive", "id": "naming"}, ["ask"]), ({"kind": "chapter", "id": "c1"}, ["ask"])]:
            with self.subTest(ctx=ctx):
                self.assertEqual(run("panelTabs", ctx), tabs)

    def test_a_draft_is_kept_by_the_file_or_the_folder_it_is_about(self):
        self.assertEqual(run("draftKey", self.FILE), "a/Desk.java")
        self.assertEqual(run("draftKey", self.LINES), "a/Desk.java")
        self.assertEqual(run("draftKey", {"kind": "folder", "path": "a/b/"}), "a/b/")
        self.assertIsNone(run("draftKey", {"kind": "finding", "id": "f1"}))
        self.assertIsNone(run("draftKey", {"kind": "review"}))


@unittest.skipUnless(NODE, "node is not installed")
class StoryTest(unittest.TestCase):
    def test_a_review_opens_on_the_story_and_the_old_addresses_of_overview_and_structure_lead_there(self):
        for given, tab in [(None, "story"), ("", "story"), ("overview", "story"), ("structure", "story"),
                           ("code", "code"), ("findings", "findings"), ("tools", "tools"), ("new", "new")]:
            with self.subTest(given=given):
                self.assertEqual(run("tabOf", given), tab)

    def test_a_diagram_is_its_boxes_in_order_with_an_arrow_between_each_two(self):
        html = run("diagramHtml", {"boxes": ["Cancel button", "Controller", "<CancelReservation>"],
                                   "ends": "Cancelled · NotOwner"}, uses=["esc"])

        boxes = re.findall(r'<span class="dbox">(.*?)</span>', html)
        self.assertEqual(boxes, ["Cancel button", "Controller", "&lt;CancelReservation&gt;"])
        self.assertEqual(html.count('class="darr"'), 2)
        self.assertIn("Cancelled · NotOwner", html)

    def test_a_diagram_without_ends_says_nothing_under_its_boxes(self):
        html = run("diagramHtml", {"boxes": ["A", "B", "C"]}, uses=["esc"])

        self.assertNotIn("dends", html)


STEP_IDS = ["open-review", "read-pr-scope", "map-change-structure", "tell-the-story", "read-test-rules",
            "triage-explanations", "review-use-cases", "deduplicate-findings", "serve-page"]


def step_of(state):
    """The step the page shows for `state`, with the session idle on no question."""
    program = "\n".join([f"const STEPS = {json.dumps([[k, k, k] for k in STEP_IDS])};", constant("stepAt"),
                         f"const S = () => ({json.dumps(state)});", "const useCases = () => (S().structure || {})['use-cases'] || [];",
                         "const waiting = () => false;", "const idle = () => false;", function("reviewStep")])
    out = subprocess.run([NODE, "-e", program + "\nconsole.log(JSON.stringify(reviewStep()));"], capture_output=True,
                         text=True, check=True).stdout
    return STEP_IDS[json.loads(out)]


@unittest.skipUnless(NODE, "node is not installed")
class FindingsOnDemandTest(unittest.TestCase):
    UNDERSTOOD = {"scope": "Cancels a reservation.", "story": {"does": "x", "chapters": []}, "checkpoint": None,
                  "rules": [{"id": "r1"}], "threads": [], "findings": [],
                  "structure": {"use-cases": [{"id": "u1", "status": "pending"}]}}

    def test_a_review_whose_search_the_developer_put_off_waits_on_the_page(self):
        self.assertEqual(step_of(dict(self.UNDERSTOOD, **{"findings-search": "skipped"})), "serve-page")

    def test_a_review_still_to_search_or_searching_is_not_waiting_on_the_page(self):
        for search in (None, "requested"):
            with self.subTest(search=search):
                self.assertNotEqual(step_of(dict(self.UNDERSTOOD, **{"findings-search": search})), "serve-page")

    def test_the_findings_tab_offers_the_search_only_when_it_was_put_off(self):
        self.assertIn("data-search-findings", run("searchOffer", {"findings-search": "skipped"}))
        for search in (None, "requested"):
            with self.subTest(search=search):
                self.assertEqual(run("searchOffer", {"findings-search": search}), "")
        self.assertEqual(run("searchOffer", {}), "")


@unittest.skipUnless(NODE, "node is not installed")
class SendTest(unittest.TestCase):
    def test_send_counts_the_findings_the_comments_and_the_fix_prompt_only_when_it_goes(self):
        self.assertEqual(run("sendTotal", 3, 1, 2, True), 6)
        self.assertEqual(run("sendTotal", 3, 1, 2, False), 4)
        self.assertEqual(run("sendTotal", 0, 0, 1, True), 1)

    def test_a_fix_prompt_waiting_from_before_is_not_one_of_the_developers_comments(self):
        self.assertTrue(run("isFixPrompt", "<!-- craftsman:fix-prompts -->\n\n**Fix prompts**"))
        self.assertFalse(run("isFixPrompt", "Nice split. <!-- craftsman:fix-prompts -->"))


@unittest.skipUnless(NODE, "node is not installed")
class KeyboardTest(unittest.TestCase):
    PATHS = ["a/desk/ReserveDesk.java", "a/desk/Desk.java", "a/reservation/Reservation.java", "web/desk.service.ts"]

    def test_tree_search_matches_the_letters_in_order_names_starting_with_them_first(self):
        self.assertEqual(run("searchHits", self.PATHS, "resd"), ["a/desk/ReserveDesk.java"])
        self.assertEqual(run("searchHits", self.PATHS, "desk"),
                         ["a/desk/Desk.java", "web/desk.service.ts", "a/desk/ReserveDesk.java"])
        self.assertEqual(run("searchHits", self.PATHS, "RES"),
                         ["a/desk/ReserveDesk.java", "a/reservation/Reservation.java", "web/desk.service.ts"])
        self.assertEqual(run("searchHits", self.PATHS, ""), [])

    def test_a_name_holding_the_letters_together_comes_before_one_holding_them_apart(self):
        self.assertEqual(run("searchHits", ["x/DxExSxK.java", "y/MyDesk.java"], "desk"), ["y/MyDesk.java", "x/DxExSxK.java"])

    def test_the_folder_is_not_searched_only_the_name(self):
        self.assertEqual(run("searchHits", self.PATHS, "web"), [])

    def test_previous_and_next_file_go_round(self):
        files = ["A.java", "B.java", "C.java"]
        self.assertEqual(run("fileStep", files, "B.java", 1), "C.java")
        self.assertEqual(run("fileStep", files, "C.java", 1), "A.java")
        self.assertEqual(run("fileStep", files, "A.java", -1), "C.java")
        self.assertEqual(run("fileStep", files, "gone.java", 1), "A.java")
        self.assertEqual(run("fileStep", files, "gone.java", -1), "A.java")


if __name__ == "__main__":
    unittest.main()
