"""Tests for _markdown.py where it must read a text the way GitHub does: the review page shows comments before they are
sent there.

Run: python3 -m unittest discover -s tests
"""
import pathlib
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from _markdown import render_markdown  # noqa: E402


def rendered(text):
    return render_markdown(text, lambda url: None)


class MarkdownTest(unittest.TestCase):
    def test_a_longer_fence_holds_a_code_block_inside_it(self):
        html = rendered("````\nFix it:\n   ```java\n   var a = 1;\n   ```\nThen commit.\n````\nAfter.")

        self.assertEqual(html.count("<pre>"), 1)
        self.assertIn("Then commit.</code></pre>", html)
        self.assertIn("<p>After.</p>", html)

    def test_a_fence_ends_at_a_line_of_as_many_backticks_or_more(self):
        html = rendered("```\nvar a = 1;\n``````\nAfter.")

        self.assertIn("var a = 1;</code></pre>", html)
        self.assertIn("<p>After.</p>", html)

    def test_a_closing_fence_carries_no_text(self):
        html = rendered("```\nsee ```java here\n```")

        self.assertIn("see ```java here</code></pre>", html)

    def test_an_html_comment_is_not_shown(self):
        html = rendered("<!-- craftsman:fix-prompts -->\n\n**Fix prompts**")

        self.assertNotIn("craftsman:fix-prompts", html)
        self.assertIn("<strong>Fix prompts</strong>", html)


if __name__ == "__main__":
    unittest.main()
