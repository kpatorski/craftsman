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


if __name__ == "__main__":
    unittest.main()
