"""The palettes every craftsman page draws its colours from -- the dashboard, the review page, reports, diffs. A page
puts `theme_css()` into its <style> and uses only the variables it defines; no page defines a colour of its own.

Each palette is a set of base colours; `theme_css` turns one into CSS variables, adding the tints by fixed rules:
a `-dim` tint of an accent for borders, a `-bg` tint for fills, lines and shadows from the palette's `ink` and `shade`.
The meaning of a colour is the same in every palette:

- neon: the accent, for navigation, progress and the one thing to do now; neon-strong is its filled button, with
  on-strong text on it;
- green: added, finished or active work; must: removed work and the worst severity; change: modified or waiting work;
  should: a warning. These keep their hue in every palette, whatever its accent;
- nit: the lowest severity; select: the selected text;
- blue, amber, pink, violet, red: the other colours of the dashboard and the reports;
- inline-code: code inside the text of a Markdown page;
- syn-keyword, syn-string, syn-comment, syn-number, syn-type, syn-annotation: the code of a diff, by its syntax.

The developer picks the palette on the dashboard or the review page; the choice is kept as `theme` in
`<craftsman home>/settings.json`. Graphite is the palette until one is picked."""
DERIVED_ACCENTS = ("blue", "green", "amber", "red", "violet")


def _palette(name, note, **colours):
    """A palette from its own colours; the dashboard's colours not given follow the review page's."""
    colours = {key.replace("_", "-"): value for key, value in colours.items()}
    defaults = {
        "panel": colours["card"], "panel2": colours["card2"], "hover": colours["float"],
        "border": f"rgba({colours['ink']}, .12)", "switch-off": f"rgba({colours['ink']}, .22)", "knob": colours["text"],
        "blue": colours["change"], "green": colours["neon"], "amber": colours["should"], "red": colours["must"],
        "violet": colours["select"], "pink": colours["select"], "shade": "0, 0, 0", "shadow": .7, "scrim": .55,
        "syn-keyword": colours["select"], "syn-string": colours["change"], "syn-comment": colours["muted"],
        "syn-number": colours["should"], "syn-type": colours.get("green", colours["neon"]), "syn-annotation": colours["should"],
        "inline-code": colours.get("green", colours["neon"]),
    }
    return {"name": name, "note": note, **defaults, **colours}


def _grey(name, note, accent, strong, heading, light, annotation, **colours):
    """A palette of the near-black neutral family: greys, one accent and its shades, a muted hue for annotations."""
    family = dict(
        bg="#070707", panel="#070707", card="#0f0f0f", card2="#151515", float="#1a1a1a", code_bg="#0b0b0b",
        text="#e4e4e4", heading="#f7f7f7", muted="#8c8c8c", dim="#595959", nit="#8c8c8c", nit_dot="#6b6b6b",
        must="#d9686a", removed_text="#b8b8b8", change="#6f9fd8", should="#e8a33d", green="#5fae7b",
        ink="255, 255, 255", inline_code="#d0d0d0", syn_string="#b8b8b8", syn_number="#a3a3a3",
        neon=accent, neon_strong=strong, on_strong="#ffffff", blue=heading, select=light, syn_type=accent,
        syn_annotation=annotation)
    return _palette(name, note, **{**family, **colours})


PALETTES = {
    "graphite": _palette(
        "Graphite", "neutral black, neon green",
        bg="#0b0b0c", panel="#121214", panel2="#1a1a1e", hover="#1f1f24", border="#26262b",
        text="#e4e4e7", heading="#fafafa", muted="#8a8a93",
        blue="#46b35a", green="#5fae7b", amber="#f2a65a", pink="#a8e6b3", violet="#a8e6b3", red="#f47174",
        code_bg="#0f0f11", switch_off="#3a3a40", knob="#d4d4d8",
        neon="#53e36b", neon_strong="#2f9e44", on_strong="#fafafa", removed_text="#f3c4c4", change="#7fb2ff",
        must="#ff6b6b", should="#f5c26b", nit="#9a9a9a", nit_dot="#6b6b6b", select="#a8e6b3",
        card="#141414", card2="#1a1a1a", float="#1d1d1d", dim="#5a5a5a", ink="255, 255, 255",
        syn_type="#53e36b", syn_string="#b8b8b8", syn_number="#a3a3a3", syn_annotation="#c2b48f", inline_code="#d0d0d0"),
    "slate": _palette(
        "Slate", "cool neutral grey, indigo accent",
        bg="#101114", card="#17181d", card2="#1d1f25", float="#22242b", code_bg="#131418",
        text="#e2e4ea", heading="#fafbff", muted="#8b8f9c", dim="#585c68", nit="#8b8f9c", nit_dot="#6c707c",
        neon="#8b93f8", neon_strong="#5058d0", on_strong="#ffffff", must="#f47174", should="#f2b866",
        change="#6cc4e8", select="#d59cf5", removed_text="#f6c8c9", green="#5fd4a0", ink="200, 205, 225"),
    "steel": _palette(
        "Steel", "blue-grey, azure accent",
        bg="#13161b", card="#1a1e25", card2="#20252d", float="#252b34", code_bg="#161a20",
        text="#dce2ea", heading="#f5f8fc", muted="#8d97a6", dim="#58616f", nit="#8d97a6", nit_dot="#6c7584",
        neon="#4fc3f7", neon_strong="#1a78b4", on_strong="#ffffff", must="#ef6f6f", should="#f0bd5e",
        change="#9fb4ff", select="#c7a4ff", removed_text="#f5c6c6", green="#5fd4a0", ink="185, 205, 230"),
    "carbon": _palette(
        "Carbon", "true black, emerald accent, higher contrast",
        bg="#000000", card="#0c0c0c", card2="#131313", float="#181818", code_bg="#060606",
        text="#ececec", heading="#ffffff", muted="#909090", dim="#5c5c5c", nit="#909090", nit_dot="#707070",
        neon="#34d399", neon_strong="#047857", on_strong="#ffffff", must="#ff6b6b", should="#fbbf4f",
        change="#7cb7ff", select="#a7f0d1", removed_text="#f6c5c5", ink="255, 255, 255", green="#5fae7b",
        blue="#2bb583", syn_type="#34d399", syn_string="#b8b8b8", syn_number="#a3a3a3", syn_annotation="#c2b48f",
        inline_code="#d0d0d0"),
    "mono": _palette(
        "Mono", "neutral black, no colour accent: white buttons; colour only for severity",
        bg="#0c0c0d", card="#151517", card2="#1b1b1e", float="#202023", code_bg="#101012",
        text="#e4e4e7", heading="#ffffff", muted="#8b8b93", dim="#57575e", nit="#8b8b93", nit_dot="#6c6c73",
        neon="#e4e4e7", neon_strong="#e4e4e7", on_strong="#0c0c0d", must="#f87171", should="#f5c26b",
        change="#93b4e8", select="#d4d4d8", removed_text="#f5c6c6", green="#5fae7b", knob="#8b8b93",
        ink="255, 255, 255", blue="#d4d4d8", syn_keyword="#ffffff", syn_type="#c8c8cc", syn_string="#b8b8b8",
        syn_number="#a3a3a3", syn_annotation="#9aaab8", inline_code="#d0d0d0"),
    "ash": _grey("Ash", "neutral black and greys, silver accent with grey buttons",
                 "#c8c8cc", "#4a4a4f", "#b0b0b5", "#ececee", "#9aaab8"),
    "onyx": _grey("Onyx", "neutral black and greys, champagne gold accent",
                  "#d9bd82", "#837040", "#c4a86c", "#eddcb4", "#9fb59a", syn_number="#b5a98f"),
    "forest": _grey("Forest", "neutral black and greys, dark green accent",
                    "#5fae7b", "#2f6e47", "#4a9365", "#9ccfad", "#c2b48f"),
    "plum": _grey("Plum", "neutral black and greys, muted violet accent",
                  "#a58bd0", "#6a4fa0", "#9078c5", "#c7b6e6", "#9fb59a"),
    "bronze": _grey("Bronze", "neutral black and greys, copper accent",
                    "#c58a55", "#8a5a2e", "#ad7744", "#ddb48c", "#9aaab8"),
    "petrol": _grey("Petrol", "neutral black and greys, dark teal accent",
                    "#4fa3a5", "#26696b", "#3d9092", "#93cdce", "#c2b48f"),
    "garnet": _grey("Garnet", "neutral black and greys, raspberry red accent",
                    "#e0607e", "#9e2a44", "#d05a75", "#f2b3c2", "#9fb59a"),
    "citrine": _grey("Citrine", "neutral black and greys, lemon yellow accent",
                     "#e2cc52", "#7a6a14", "#c9b23c", "#f0e4a0", "#9aaab8"),
    "paper": _palette(
        "Paper", "light: white cards on a pale grey page, green accent",
        bg="#f6f7f9", card="#ffffff", card2="#f1f3f6", float="#ffffff", hover="#eef0f3", code_bg="#f3f4f7",
        text="#24292f", heading="#0d1117", muted="#57606a", dim="#8c959f", nit="#6e7781", nit_dot="#afb8c1",
        neon="#1a7f37", neon_strong="#1f883d", on_strong="#ffffff", must="#cf222e", should="#9a6700",
        change="#0969da", select="#8250df", removed_text="#82071e", amber="#bc4c00", pink="#bf3989",
        knob="#ffffff", switch_off="#d0d7de", border="#d0d7de", ink="31, 35, 40", shade="31, 35, 40",
        syn_number="#8a5c00", syn_annotation="#953800",
        shadow=.15, scrim=.3),
}


def _rgb(hex_colour):
    return ", ".join(str(int(hex_colour[i:i + 2], 16)) for i in (1, 3, 5))


def _alpha(value):
    return f"{value:g}".lstrip("0")


def _tint(hex_colour, alpha):
    return f"rgba({_rgb(hex_colour)}, {_alpha(alpha)})"


TEXT_SIZE = "109%"


def theme_css(palette=None):
    """The `:root` CSS variables of a palette, the chosen one when none is named, and the size every page's text is
    measured from: pages size text in `rem` only."""
    c = PALETTES[palette or chosen()]
    names = ("bg", "panel", "panel2", "hover", "border", "text", "heading", "muted",
             "blue", "green", "inline-code", "amber", "pink", "violet", "red", "code-bg", "switch-off", "knob",
             "neon", "neon-strong", "on-strong", "removed-text", "change", "must", "should", "nit", "nit-dot",
             "select", "card", "card2", "float", "dim",
             "syn-keyword", "syn-string", "syn-comment", "syn-number", "syn-type", "syn-annotation")
    css = {name: c[name] for name in names}
    for accent in DERIVED_ACCENTS:
        css[f"{accent}-dim"], css[f"{accent}-bg"] = _tint(c[accent], .35), _tint(c[accent], .12)
    css.update({
        "neon-dim": _tint(c["neon"], .4), "neon-bg": _tint(c["neon"], .1),
        "added-bg": _tint(c["green"], .1), "removed-bg": _tint(c["must"], .1),
        "change-dim": _tint(c["change"], .35), "change-bg": _tint(c["change"], .1), "must-bg": _tint(c["must"], .1), "should-bg": _tint(c["should"], .1),
        "nit-bg": f"rgba({c['ink']}, .06)", "select-bg": _tint(c["select"], .14),
        "line": f"rgba({c['ink']}, .08)", "line2": f"rgba({c['ink']}, .14)",
        "shadow": f"rgba({c['shade']}, {_alpha(c['shadow'])})", "scrim": f"rgba({c['shade']}, {_alpha(c['scrim'])})",
        "radius": "12px", "radius-sm": "8px", "pill": "999px",
        "mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    })
    return f"\n  :root {{\n    font-size: {TEXT_SIZE};\n" + "".join(f"    --{name}: {value};\n" for name, value in css.items()) + "  }\n"


def palettes():
    """What the palette picker shows: each palette's id, name, note and a few of its colours."""
    return [dict(id=key, name=c["name"], note=c["note"],
                 swatch=[c["bg"], c["card"], c["text"], c["neon"], c["must"], c["should"], c["change"]])
            for key, c in PALETTES.items()]


def chosen():
    """The id of the palette the developer picked; graphite when none is, or the picked one no longer exists."""
    import _settings
    picked = _settings.read().get("theme")
    return picked if picked in PALETTES else "graphite"


def choose(palette):
    """Keep the developer's palette. Raises ValueError for a palette that does not exist."""
    if palette not in PALETTES:
        raise ValueError(f"no such palette: {palette!r}; one of {', '.join(PALETTES)}")
    import _settings
    _settings.update("theme", palette)
