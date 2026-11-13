"""Tests for record_source.py: the `Sources` table of each index, where `install` records where content came from and
at which version -- see MANAGEMENT.md, "Checking a known source for updates".

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
import record_source  # noqa: E402

WORKSHOP = "https://github.example.com/team/workshop"
INDEX = """## Sources

Where installed directives came from.

| Name     | Location                              | Kind | Version |
|----------|---------------------------------------|------|---------|
| workshop | https://github.example.com/team/workshop | git  | 3dc95a9 |

## Directives

Empty — nothing here.
"""


class RecordSourceTest(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        for kind in ("directives", "protocols", "bundles"):
            (self.root / kind).mkdir()
            (self.root / kind / "index.md").write_text(INDEX.replace("Directives", kind.title()))
        self.index = self.root / "directives" / "index.md"

    def table(self):
        lines = self.index.read_text().splitlines()
        start = lines.index("## Sources")
        return [line for line in lines[start:] if line.startswith("|")]

    def test_a_known_source_gets_its_new_version_and_the_table_stays_aligned(self):
        self.assertEqual(record_source.record(self.index, "workshop", WORKSHOP, "git", "698cfdf"), "updated")
        rows = self.table()
        self.assertEqual(len(rows), 3)
        self.assertIn("| 698cfdf |", rows[2])
        self.assertEqual(len({len(row) for row in rows}), 1, rows)
        self.assertEqual({row.count("|") for row in rows}, {5})

    def test_a_new_source_is_added_below_the_others(self):
        self.assertEqual(record_source.record(self.index, "local", "/srv/rules", "folder", "-"), "added")
        rows = self.table()
        self.assertEqual([row.split("|")[1].strip() for row in rows[2:]], ["workshop", "local"])
        self.assertEqual(len({len(row) for row in rows}), 1, rows)

    def test_the_same_version_again_changes_nothing(self):
        before = self.index.read_text()
        record_source.record(self.index, "workshop", WORKSHOP, "git", "698cfdf")
        once = self.index.read_text()
        self.assertEqual(record_source.record(self.index, "workshop", WORKSHOP, "git", "698cfdf"), "unchanged")
        self.assertEqual(self.index.read_text(), once)
        self.assertNotEqual(before, once)
        self.assertIn("## Directives\n\nEmpty — nothing here.\n", once, "the rest of the file is left as it was")

    def test_a_source_is_found_by_its_location_in_every_index(self):
        record_source.record(self.index, "workshop", WORKSHOP, "git", "698cfdf")
        self.assertEqual(len(record_source.find(self.root, WORKSHOP + ".git")), 3)
        found = record_source.find(self.root, WORKSHOP + "/")
        self.assertEqual(sorted((f["index"], f["version"]) for f in found),
                         [("bundles", "3dc95a9"), ("directives", "698cfdf"), ("protocols", "3dc95a9")])
        self.assertEqual(record_source.find(self.root, "https://github.example.com/other/rules"), [])

    def test_an_index_without_a_sources_table_is_refused(self):
        self.index.write_text("## Directives\n\nEmpty.\n")
        with self.assertRaises(ValueError):
            record_source.record(self.index, "workshop", WORKSHOP, "git", "698cfdf")

    def test_the_command_line_records_and_finds(self):
        def run(*args):
            return subprocess.run([sys.executable, str(SCRIPTS / "record_source.py"), *args], capture_output=True,
                                  text=True, timeout=30)
        done = run("record", str(self.index), "workshop", WORKSHOP, "git", "698cfdf")
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "updated"), done.stderr)
        found = run("find", str(self.root), WORKSHOP)
        self.assertEqual(len(json.loads(found.stdout)), 3)


if __name__ == "__main__":
    unittest.main()
