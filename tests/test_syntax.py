"""Tests for syntax.js: the review page colours the code of a diff by its language -- keywords, strings, comments,
numbers, types and annotations -- line by line, a block comment or a multi-line string carried from one line to the
next. A file in a language it does not know stays plain text.

The script runs in Node here, the way the page loads it; without Node these tests are skipped.

Run: python3 -m unittest discover -s tests
"""
import html
import json
import pathlib
import re
import shutil
import subprocess
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts" / "syntax.js"
NODE = shutil.which("node")


def run(expression):
    program = f"const Syntax = require({json.dumps(str(SCRIPT))}); console.log(JSON.stringify({expression}));"
    return json.loads(subprocess.run([NODE, "-e", program], capture_output=True, text=True, check=True).stdout)


def lines(language, texts):
    return run(f"Syntax.lines({json.dumps(language)}, {json.dumps(texts)})")


def spans(line_html):
    """The coloured pieces of one line, as (kind, text)."""
    return [(kind, html.unescape(text)) for kind, text in re.findall(r'<span class="sx-(\w)">(.*?)</span>', line_html)]


def text(line_html):
    return html.unescape(re.sub(r"<[^>]+>", "", line_html))


@unittest.skipUnless(NODE, "node is not installed")
class SyntaxTest(unittest.TestCase):
    def test_the_language_comes_from_the_file_name(self):
        paths = ["src/A.java", "app/b.kt", "web/c.tsx", "web/d.js", "tool/e.py", "cmd/f.go", "g.cs", "db/h.sql",
                 "k8s/i.yaml", "j.json", "pom.xml", "run.sh", "README", "notes.txt"]
        self.assertEqual(["java", "kotlin", "typescript", "javascript", "python", "go", "csharp", "sql",
                          "yaml", "json", "xml", "shell", None, None],
                         run(f"{json.dumps(paths)}.map(Syntax.language)"))

    def test_keywords_types_and_a_line_comment(self):
        [line] = lines("java", ["public class Booking extends Base { // the aggregate"])

        self.assertEqual([("k", "public"), ("k", "class"), ("t", "Booking"), ("k", "extends"), ("t", "Base"),
                          ("c", "// the aggregate")], spans(line))

    def test_a_keyword_inside_a_string_is_part_of_the_string(self):
        [line] = lines("java", ['String s = "class \\"new\\" if"; int n = 42;'])

        self.assertEqual([("t", "String"), ("s", '"class \\"new\\" if"'), ("k", "int"), ("n", "42")], spans(line))

    def test_a_block_comment_goes_on_over_the_next_lines(self):
        result = lines("java", ["int a; /* starts", "  goes on", "ends */ return 0x1F;"])

        self.assertEqual([("k", "int"), ("c", "/* starts")], spans(result[0]))
        self.assertEqual([("c", "  goes on")], spans(result[1]))
        self.assertEqual([("c", "ends */"), ("k", "return"), ("n", "0x1F")], spans(result[2]))

    def test_annotations_and_decorators(self):
        self.assertEqual([("a", "@Override"), ("k", "public"), ("k", "void")],
                         spans(lines("java", ["@Override public void run()"])[0]))
        self.assertEqual([("a", "@dataclass")], spans(lines("python", ["@dataclass"])[0]))

    def test_python_comments_and_a_docstring_over_several_lines(self):
        result = lines("python", ['def cancel(self):  # by the owner', '    """Cancel', '    it."""', "    return None"])

        self.assertEqual([("k", "def"), ("k", "self"), ("c", "# by the owner")], spans(result[0]))
        self.assertEqual([("s", '"""Cancel')], spans(result[1]))
        self.assertEqual([("s", '    it."""')], spans(result[2]))
        self.assertEqual([("k", "return"), ("k", "None")], spans(result[3]))

    def test_sql_keywords_in_any_case(self):
        self.assertEqual([("k", "select"), ("k", "FROM"), ("k", "where"), ("s", "'x'")],
                         spans(lines("sql", ["select * FROM desk where id = 'x' -- one"])[0])[:4])

    def test_yaml_keys_and_xml_tags(self):
        self.assertEqual([("t", "name"), ("s", '"api"'), ("c", "# the service")],
                         spans(lines("yaml", ['  name: "api"  # the service'])[0]))
        self.assertEqual([("k", "<dependency"), ("t", "scope"), ("s", '"test"'), ("k", ">")],
                         spans(lines("xml", ['<dependency scope="test">'])[0]))

    def test_the_text_of_every_line_stays_the_same_and_escaped(self):
        samples = {"java": ['if (a < b && c > d) { s = "<x>"; }', "x = y >> 2; /* <b> */"],
                   "typescript": ["const t = `${a} & <b>`;", "let x: Array<string> = []"],
                   "python": ["print('<&>')  # <i>"]}
        for language, texts in samples.items():
            with self.subTest(language=language):
                result = lines(language, texts)
                self.assertEqual(texts, [text(line) for line in result])
                self.assertFalse(any(re.search(r"<(?!/?span)", line) for line in result))

    def test_a_language_it_does_not_know_stays_plain(self):
        self.assertEqual(["a &lt; b // not a comment"], lines(None, ["a < b // not a comment"]))

    def test_each_line_can_carry_its_own_state(self):
        opened, state = run('Syntax.line("java", "/* open", null)')
        closed, after = run(f'Syntax.line("java", "closed */ int", {json.dumps(state)})')

        self.assertEqual(([("c", "/* open")], [("c", "closed */"), ("k", "int")]), (spans(opened), spans(closed)))
        self.assertIsNotNone(state)
        self.assertIsNone(after)

if __name__ == "__main__":
    unittest.main()
