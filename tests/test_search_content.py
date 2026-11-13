"""Tests for search_content.py, the lookup behind /craftsman:search: every installed directive, protocol and bundle
whose id, title or description has a word of the phrase, best match first -- see MANAGEMENT.md, "Duplicate detection".

Run: python3 -m unittest discover -s tests
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))
import search_content  # noqa: E402
from test_review_directives import workshop  # noqa: E402


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.content = self.root / "content"
        workshop(self.content)

    def search(self, phrase):
        return search_content.search(self.content, phrase)

    def test_a_hit_on_the_id_ranks_above_one_on_the_title_and_one_on_the_description_last(self):
        found = self.search("naming tests")
        self.assertEqual([m["id"] for m in found][:2], ["test-naming", "naming"])
        self.assertEqual(found[0]["matched"], ["id", "title", "description"])

    def test_the_same_word_ranks_an_id_first_a_title_next_and_a_description_last(self):
        content = self.root / "ranked"
        top = content / "directives"
        rows = (("alpha", "Guard clauses", "Keeps methods short."), ("beta", "Short methods", "About guards."),
                ("short-lines", "Lines", "Wraps code."))
        for entry_id, title, description in rows:
            (top / entry_id).mkdir(parents=True)
            (top / entry_id / "directive.md").write_text(
                f"---\nid: {entry_id}\ntitle: {title}\ndescription: {description}\n---\n")
        (top / "index.md").write_text(
            "## Directives\n\n**Enabled**\n\n| No | Id | Title |\n|----|----|-------|\n" + "".join(
                f"| {n} | [{entry_id}]({entry_id}/directive.md) | {title} |\n"
                for n, (entry_id, title, _) in enumerate(rows, 1)))
        self.assertEqual([m["id"] for m in search_content.search(content, "short")],
                         ["short-lines", "beta", "alpha"])
        self.assertEqual([m["id"] for m in search_content.search(content, "guard")], ["alpha", "beta"])

    def test_every_kind_is_searched_bundles_and_their_members_included(self):
        self.assertEqual({(m["kind"], m["id"]) for m in self.search("review")},
                         {("bundle", "code-review"), ("directive", "review-comment"), ("protocol", "open-review"),
                          ("protocol", "review-use-case")})

    def test_a_match_says_whether_it_is_on_and_where_it_lives(self):
        [lombok] = self.search("lombok")
        self.assertEqual((lombok["kind"], lombok["enabled"], lombok["bundle"]), ("directive", False, None))
        self.assertTrue(pathlib.Path(lombok["path"]).is_file())
        [pinned] = self.search("behaviour")
        self.assertEqual((pinned["id"], pinned["bundle"], pinned["enabled"]), ("characterize", "legacy", False),
                         "a member of a disabled bundle is not checked, whatever its own row says")

    def test_case_and_short_words_do_not_matter_and_nothing_found_is_an_empty_list(self):
        self.assertEqual([m["id"] for m in self.search("NAMES a")], ["naming"])
        self.assertEqual(self.search("kubernetes"), [])

    def test_the_command_line_prints_json_and_says_when_nothing_is_installed(self):
        def run(root):
            return subprocess.run([sys.executable, str(SCRIPTS / "search_content.py"), str(root), "lombok"],
                                  capture_output=True, text=True, timeout=30)
        done = run(self.content)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual([m["id"] for m in json.loads(done.stdout)], ["prefer-lombok"])
        missing = run(self.root / "nowhere")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("nothing is installed", missing.stderr)


if __name__ == "__main__":
    unittest.main()
