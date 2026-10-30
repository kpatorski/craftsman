"""Tests for the shared visual theme: every craftsman page draws its colours from one palette in _theme.py, so the
dashboard, reports and diffs look the same and a theme change is an edit in one place.

Run: python3 -m unittest discover -s tests
"""
import pathlib
import re
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))

PAGES = ["dashboard_page.html", "render_dashboard.py", "render_diff.py", "render_report.py", "_markdown.py"]
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(")


class ThemeTest(unittest.TestCase):
    def test_no_page_defines_a_colour_of_its_own(self):
        for name in PAGES:
            with self.subTest(page=name):
                self.assertEqual([], COLOUR.findall((SCRIPTS / name).read_text()))

    def test_the_palette_defines_every_variable_a_page_uses(self):
        import _theme
        defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", _theme.THEME_CSS))
        for name in PAGES:
            used = set(re.findall(r"var\((--[a-z0-9-]+)\)", (SCRIPTS / name).read_text()))
            with self.subTest(page=name):
                self.assertEqual(set(), used - defined)


if __name__ == "__main__":
    unittest.main()
