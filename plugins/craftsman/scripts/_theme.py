"""The palettes every craftsman page draws its colours from -- the dashboard, the review page, reports, diffs. A page
puts `theme_css()` into its <style> and uses only the variables it defines; no page defines a colour of its own.

Each palette is a set of base colours; `theme_css` turns one into CSS variables, adding the tints by fixed rules:
a `-dim` tint of an accent for borders, a `-bg` tint for fills, lines and shadows from the palette's `ink` and `shade`.
The meaning of a colour is the same in every palette:

- neon: progress and the one thing to do now; neon-strong is its filled button, with on-strong text on it;
- must, should, nit: the severity of a finding; change: a modified file; select: the selected text;
- blue, green, amber, pink, violet, red: the accents of the dashboard and the reports;
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
    }
    return {"name": name, "note": note, **defaults, **colours}


PALETTES = {
    "graphite": _palette(
        "Graphite", "neutral black, neon green",
        bg="#0b0b0c", panel="#121214", panel2="#1a1a1e", hover="#1f1f24", border="#26262b",
        text="#e4e4e7", heading="#fafafa", muted="#8a8a93",
        blue="#8b93f8", green="#5fd4a0", amber="#f2a65a", pink="#ec7ab8", violet="#a78bfa", red="#f47174",
        code_bg="#0f0f11", switch_off="#3a3a40", knob="#d4d4d8",
        neon="#53e36b", neon_strong="#2f9e44", on_strong="#fafafa", removed_text="#f3c4c4", change="#7fb2ff",
        must="#ff6b6b", should="#f5c26b", nit="#9a9a9a", nit_dot="#6b6b6b", select="#b69cff",
        card="#141414", card2="#1a1a1a", float="#1d1d1d", dim="#5a5a5a", ink="255, 255, 255"),
    "midnight": _palette(
        "Midnight", "navy blue, sky-blue accent",
        bg="#0d1117", card="#151b24", card2="#1b2330", float="#1d2633", code_bg="#10151d",
        text="#d5dde9", heading="#f2f6fc", muted="#8792a4", dim="#556072", nit="#8792a4", nit_dot="#6a7486",
        neon="#58a6ff", neon_strong="#1f6feb", on_strong="#ffffff", must="#ff7b72", should="#e3b341",
        change="#a5b4fc", select="#d2a8ff", removed_text="#ffc9c4", green="#56d364", ink="160, 190, 240"),
    "arctic": _palette(
        "Arctic", "lighter slate grey, frost-cyan accent, muted colours",
        bg="#1b1f27", card="#232832", card2="#2a303b", float="#2e3440", code_bg="#1f242c",
        text="#d8dee9", heading="#eceff4", muted="#a0a8b6", dim="#646d7d", nit="#a0a8b6", nit_dot="#7a8292",
        neon="#88d0dc", neon_strong="#2f7f94", on_strong="#ffffff", must="#e0727c", should="#e5c07b",
        change="#8fb0d8", select="#c09bc4", removed_text="#f2c9cd", green="#a3d39c", ink="200, 215, 235"),
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
    "dim": _palette(
        "Dim", "the softest dark: mid grey-blue, calm blue accent",
        bg="#22272e", card="#2a3038", card2="#313842", float="#363e49", code_bg="#262c34",
        text="#cdd9e5", heading="#e6edf3", muted="#a0acb9", dim="#636e7b", nit="#a0acb9", nit_dot="#768390",
        neon="#6cb6ff", neon_strong="#316dca", on_strong="#ffffff", must="#f47067", should="#daaa3f",
        change="#96d0ff", select="#dcbdfb", removed_text="#ffc6c0", green="#57ab5a", ink="205, 217, 229"),
    "ink": _palette(
        "Ink", "deep indigo-navy, periwinkle accent",
        bg="#0b0d18", card="#121526", card2="#181c30", float="#1d2238", code_bg="#0e101d",
        text="#dadff5", heading="#f4f6ff", muted="#8a90b0", dim="#535878", nit="#8a90b0", nit_dot="#686e8f",
        neon="#8ea2ff", neon_strong="#4d63e0", on_strong="#ffffff", must="#ff7a85", should="#f5c46e",
        change="#6fd3f0", select="#e2a4ff", removed_text="#ffcbd0", green="#5fd4a0", ink="170, 180, 255"),
    "carbon": _palette(
        "Carbon", "true black, emerald accent, higher contrast",
        bg="#000000", card="#0c0c0c", card2="#131313", float="#181818", code_bg="#060606",
        text="#ececec", heading="#ffffff", muted="#909090", dim="#5c5c5c", nit="#909090", nit_dot="#707070",
        neon="#34d399", neon_strong="#047857", on_strong="#ffffff", must="#ff6b6b", should="#fbbf4f",
        change="#7cb7ff", select="#b9a0ff", removed_text="#f6c5c5", ink="255, 255, 255"),
    "mono": _palette(
        "Mono", "neutral black, no colour accent: white buttons; colour only for severity",
        bg="#0c0c0d", card="#151517", card2="#1b1b1e", float="#202023", code_bg="#101012",
        text="#e4e4e7", heading="#ffffff", muted="#8b8b93", dim="#57575e", nit="#8b8b93", nit_dot="#6c6c73",
        neon="#e4e4e7", neon_strong="#e4e4e7", on_strong="#0c0c0d", must="#f87171", should="#f5c26b",
        change="#93b4e8", select="#a1a1aa", removed_text="#f5c6c6", green="#5fd4a0", knob="#8b8b93",
        ink="255, 255, 255"),
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


def theme_css(palette=None):
    """The `:root` CSS variables of a palette; the chosen one when none is named."""
    c = PALETTES[palette or chosen()]
    names = ("bg", "panel", "panel2", "hover", "border", "text", "heading", "muted",
             "blue", "green", "amber", "pink", "violet", "red", "code-bg", "switch-off", "knob",
             "neon", "neon-strong", "on-strong", "removed-text", "change", "must", "should", "nit", "nit-dot",
             "select", "card", "card2", "float", "dim",
             "syn-keyword", "syn-string", "syn-comment", "syn-number", "syn-type", "syn-annotation")
    css = {name: c[name] for name in names}
    for accent in DERIVED_ACCENTS:
        css[f"{accent}-dim"], css[f"{accent}-bg"] = _tint(c[accent], .35), _tint(c[accent], .12)
    css.update({
        "neon-dim": _tint(c["neon"], .4), "neon-bg": _tint(c["neon"], .1),
        "added-bg": _tint(c["neon"], .06), "removed-bg": _tint(c["must"], .08),
        "change-bg": _tint(c["change"], .1), "must-bg": _tint(c["must"], .1), "should-bg": _tint(c["should"], .1),
        "nit-bg": f"rgba({c['ink']}, .06)", "select-bg": _tint(c["select"], .14),
        "line": f"rgba({c['ink']}, .08)", "line2": f"rgba({c['ink']}, .14)",
        "shadow": f"rgba({c['shade']}, {_alpha(c['shadow'])})", "scrim": f"rgba({c['shade']}, {_alpha(c['scrim'])})",
        "radius": "12px", "radius-sm": "8px", "pill": "999px",
        "mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    })
    return "\n  :root {\n" + "".join(f"    --{name}: {value};\n" for name, value in css.items()) + "  }\n"


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
