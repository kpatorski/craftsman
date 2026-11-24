"""Tests for the shared visual theme: every craftsman page draws its colours from one palette in _theme.py, so the
dashboard, reports and diffs look the same. The developer picks the palette; the choice lives in the craftsman home.

Run: python3 -m unittest discover -s tests
"""
import colorsys
import json
import os
import pathlib
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "craftsman" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _theme  # noqa: E402

PAGES = ["dashboard_page.html", "review_page.html", "theme_picker.js", "syntax.js", "render_dashboard.py", "render_diff.py", "render_report.py",
         "_markdown.py"]
GREY = ("graphite", "carbon", "mono", "ash", "onyx", "forest", "plum", "bronze", "petrol", "garnet", "citrine")
PIXEL_TEXT = re.compile(r"font-size:\s*[\d.]+px|font:[^;]*?\b[\d.]+px")
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(")


def variables(css):
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", css))


def luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2]


def contrast(a, b):
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + .05) / (dark + .05)


def hue(hex_colour):
    return colorsys.rgb_to_hsv(*(int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)))[0] * 360


class HomeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name) / "home"
        self.real_home = os.environ.get("CRAFTSMAN_HOME")
        os.environ["CRAFTSMAN_HOME"] = str(self.home)

    def tearDown(self):
        if self.real_home is None:
            os.environ.pop("CRAFTSMAN_HOME", None)
        else:
            os.environ["CRAFTSMAN_HOME"] = self.real_home
        self.tmp.cleanup()


class PaletteTest(unittest.TestCase):
    def test_no_page_defines_a_colour_of_its_own(self):
        for name in PAGES:
            with self.subTest(page=name):
                self.assertEqual([], COLOUR.findall((SCRIPTS / name).read_text()))

    def test_every_palette_defines_every_variable_a_page_uses(self):
        used = set()
        for name in PAGES:
            used |= set(re.findall(r"var\((--[a-z0-9-]+)\)", (SCRIPTS / name).read_text()))
        for palette in _theme.PALETTES:
            with self.subTest(palette=palette):
                self.assertEqual(set(), used - set(variables(_theme.theme_css(palette))))

    def test_text_stays_readable_in_every_palette(self):
        for palette, colours in _theme.PALETTES.items():
            with self.subTest(palette=palette):
                self.assertGreaterEqual(contrast(colours["text"], colours["bg"]), 7)
                self.assertGreaterEqual(contrast(colours["muted"], colours["card"]), 4.5)
                self.assertGreaterEqual(contrast(colours["on-strong"], colours["neon-strong"]), 3)

    def test_code_colours_stay_readable_on_cards_and_on_code_in_every_palette(self):
        for palette in _theme.PALETTES:
            css = variables(_theme.theme_css(palette))
            for kind in ("keyword", "string", "comment", "number", "type", "annotation"):
                for ground in ("card", "code-bg"):
                    with self.subTest(palette=palette, kind=kind, ground=ground):
                        self.assertGreaterEqual(contrast(css[f"--syn-{kind}"], css[f"--{ground}"]), 4.5)

    def test_code_colours_tell_keywords_strings_and_comments_apart_in_every_palette(self):
        for palette in _theme.PALETTES:
            css = variables(_theme.theme_css(palette))
            with self.subTest(palette=palette):
                colours = [css[f"--syn-{kind}"] for kind in ("keyword", "string", "comment", "type")]
                self.assertEqual(len(colours), len(set(colours)))
                self.assertNotIn(css["--text"], colours)

    def test_no_page_sizes_its_text_in_pixels(self):
        for name in PAGES:
            with self.subTest(page=name):
                self.assertEqual([], PIXEL_TEXT.findall((SCRIPTS / name).read_text()))

    def test_every_palette_sets_the_one_size_all_text_is_measured_from(self):
        for palette in _theme.PALETTES:
            with self.subTest(palette=palette):
                self.assertIn(f"font-size: {_theme.TEXT_SIZE};", _theme.theme_css(palette))
        self.assertEqual("109%", _theme.TEXT_SIZE)

    def test_the_palettes_are_mostly_greys_with_one_muted_accent_and_a_light_one(self):
        self.assertEqual(["graphite", "slate", "steel", "carbon", "mono", "ash", "onyx", "forest", "plum", "bronze",
                          "petrol", "garnet", "citrine", "paper"], list(_theme.PALETTES))

    def test_grey_palettes_keep_headings_in_a_darker_accent_and_inline_code_grey(self):
        for palette in GREY:
            with self.subTest(palette=palette):
                colours = _theme.PALETTES[palette]
                self.assertLess(luminance(colours["blue"]), luminance(colours["neon"]))
                self.assertGreaterEqual(contrast(colours["blue"], colours["card2"]), 4.5)
                code = colours["inline-code"]
                self.assertEqual(1, len({code[1:3], code[3:5], code[5:7]}))
                self.assertGreaterEqual(contrast(code, colours["code-bg"]), 7)

    def test_grey_palettes_share_one_near_black_neutral_background(self):
        for palette in ("ash", "onyx", "forest", "plum", "bronze", "petrol", "garnet", "citrine"):
            with self.subTest(palette=palette):
                colours = _theme.PALETTES[palette]
                self.assertEqual(("#070707", "#0b0b0b", "#0f0f0f", "#151515", "#1a1a1a"),
                                 (colours["bg"], colours["code-bg"], colours["card"], colours["card2"], colours["float"]))
                self.assertEqual(colours["bg"], colours["panel"])

    def test_inline_code_of_the_other_palettes_keeps_their_green(self):
        for palette in ("slate", "steel", "paper"):
            with self.subTest(palette=palette):
                colours = _theme.PALETTES[palette]
                self.assertEqual(colours["green"], variables(_theme.theme_css(palette))["--inline-code"])

    def test_markdown_inline_code_takes_the_inline_code_colour(self):
        self.assertRegex((SCRIPTS / "_markdown.py").read_text(), r"\.md code \{[^}]*color: var\(--inline-code\)")

    def test_meaningful_colours_keep_their_hue_in_every_palette(self):
        for palette, colours in _theme.PALETTES.items():
            with self.subTest(palette=palette):
                self.assertTrue(120 <= hue(colours["green"]) <= 175, "added is green")
                self.assertTrue(hue(colours["must"]) >= 340 or hue(colours["must"]) <= 10, "removed is red")
                self.assertTrue(185 <= hue(colours["change"]) <= 235, "modified is blue")
                self.assertTrue(30 <= hue(colours["should"]) <= 50, "a warning is amber")

    def test_added_and_removed_lines_are_tinted_by_their_meaning_not_by_the_accent(self):
        for palette, colours in _theme.PALETTES.items():
            with self.subTest(palette=palette):
                css = variables(_theme.theme_css(palette))
                self.assertEqual(_theme._tint(colours["green"], .1), css["--added-bg"])
                self.assertEqual(_theme._tint(colours["must"], .1), css["--removed-bg"])

    def test_marks_of_added_and_finished_work_take_green_on_the_review_page(self):
        page = (SCRIPTS / "review_page.html").read_text()
        for mark in (r"\.kd\.added \{ color: var\(--green\)", r"\.ln\.add \.sg \{ color: var\(--green\)",
                     r"\.sub \.plus \{ color: var\(--green\)", r"\.ck\.clean \{ background: var\(--green\)",
                     r'added: \["--green"', r"M3\.5 8\.5l3 3 6-7\" fill=\"none\" style=\"stroke:var\(--green\)"):
            with self.subTest(mark=mark):
                self.assertRegex(page, mark)

    def test_what_only_decorates_a_page_takes_the_accent_not_green(self):
        for name, mark in (("dashboard_page.html", r"\.brand \{[^}]*color: var\(--neon\)"),
                           ("dashboard_page.html", r"\.switch\.on::after \{[^}]*background: var\(--neon\)"),
                           ("render_dashboard.py", r"h3\.category \{ color: var\(--neon\)"),
                           ("render_report.py", r"\.navlink\.active \{[^}]*border-left-color: var\(--neon\)")):
            with self.subTest(page=name, mark=mark):
                self.assertRegex((SCRIPTS / name).read_text(), mark)

    def test_work_that_waits_shows_as_modified_on_the_dashboard(self):
        self.assertRegex((SCRIPTS / "dashboard_page.html").read_text(), r"\.badge\.pending \{ color: var\(--change\)")

    def test_grey_palettes_give_annotations_a_muted_hue_of_their_own(self):
        for palette in GREY:
            with self.subTest(palette=palette):
                colours = _theme.PALETTES[palette]
                annotation = colours["syn-annotation"]
                saturation = colorsys.rgb_to_hsv(*(int(annotation[i:i + 2], 16) / 255 for i in (1, 3, 5)))[1]
                self.assertTrue(.1 <= saturation <= .35, "a muted hue, neither grey nor loud")
                self.assertNotIn(annotation, (colours["neon"], colours["blue"], colours["select"], colours["syn-type"]))

    def test_grey_palettes_keep_violet_and_teal_out(self):
        for palette in GREY:
            for name in ("blue", "select", "violet", "pink", "syn-keyword", "syn-type", "green"):
                with self.subTest(palette=palette, colour=name):
                    self.assertFalse(250 <= hue(_theme.PALETTES[palette][name]) <= 300 and palette != "plum")
                    self.assertNotEqual("#5fd4a0", _theme.PALETTES[palette][name])

    def test_onyx_is_champagne_with_sage_annotations(self):
        onyx = _theme.PALETTES["onyx"]
        self.assertEqual(("#d9bd82", "#837040", "#c4a86c", "#eddcb4", "#9fb59a", "#b5a98f"),
                         (onyx["neon"], onyx["neon-strong"], onyx["blue"], onyx["select"],
                          onyx["syn-annotation"], onyx["syn-number"]))

    def test_there_are_dark_palettes_and_a_light_one(self):
        light = [p for p, colours in _theme.PALETTES.items() if luminance(colours["bg"]) > .5]
        self.assertEqual(["paper"], light)
        self.assertGreater(len(_theme.PALETTES), 5)


class ChoiceTest(HomeTest):
    def test_graphite_is_the_palette_until_the_developer_picks_one(self):
        self.assertEqual("graphite", _theme.chosen())
        self.assertEqual(_theme.theme_css("graphite"), _theme.theme_css())

    def test_the_choice_is_kept_in_the_craftsman_home_beside_other_settings(self):
        self.home.mkdir(parents=True)
        (self.home / "settings.json").write_text(json.dumps({"other": 1}))
        _theme.choose("forest")
        self.assertEqual("forest", _theme.chosen())
        self.assertEqual({"other": 1, "theme": "forest"}, json.loads((self.home / "settings.json").read_text()))
        self.assertEqual(_theme.theme_css("forest"), _theme.theme_css())

    def test_an_unknown_palette_is_refused_and_a_stale_choice_falls_back_to_graphite(self):
        with self.assertRaises(ValueError):
            _theme.choose("neon-pink")
        self.home.mkdir(parents=True)
        (self.home / "settings.json").write_text(json.dumps({"theme": "gone"}))
        self.assertEqual("graphite", _theme.chosen())


class ThemeEndpointsTest(HomeTest):
    """The dashboard page and the review page switch the palette through the server."""

    def setUp(self):
        super().setUp()
        import dashboard_server
        self.server = dashboard_server.ThreadingHTTPServer(("127.0.0.1", 0), dashboard_server.Handler)
        self.port = self.server.server_address[1]
        dashboard_server.Handler.hub = dashboard_server.Hub(self.home / "content", [], self.port)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, path, body=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=None if body is None else json.dumps(body).encode(),
            method="GET" if body is None else "POST",
            headers={"Host": f"127.0.0.1:{self.port}", "X-Craftsman": "1", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                text = response.read().decode()
                return response.status, (json.loads(text) if path.startswith("/api/") else text)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_the_page_lists_the_palettes_and_names_the_chosen_one(self):
        status, answer = self.call("/api/theme")
        self.assertEqual(200, status)
        self.assertEqual("graphite", answer["current"])
        self.assertEqual(list(_theme.PALETTES), [p["id"] for p in answer["palettes"]])
        self.assertTrue(all(p["name"] and p["swatch"] for p in answer["palettes"]))

    def test_picking_a_palette_answers_its_css_and_every_page_is_served_in_it(self):
        status, answer = self.call("/api/theme", {"id": "paper"})
        self.assertEqual((200, _theme.theme_css("paper")), (status, answer["css"]))
        for page in ("/", "/review"):
            with self.subTest(page=page):
                self.assertIn(_theme.theme_css("paper"), self.call(page)[1])

    def test_both_pages_offer_the_palette_picker(self):
        script = self.call("/theme_picker.js")[1]
        self.assertIn("/api/theme", script)
        for page in ("/", "/review"):
            with self.subTest(page=page):
                served = self.call(page)[1]
                self.assertIn('<script src="/theme_picker.js"></script>', served)
                self.assertIn("data-theme-picker", served)

    def test_an_unknown_palette_is_refused(self):
        status, answer = self.call("/api/theme", {"id": "neon-pink"})
        self.assertEqual(400, status)
        self.assertEqual("graphite", _theme.chosen())


if __name__ == "__main__":
    unittest.main()
