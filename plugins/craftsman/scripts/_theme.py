"""The one palette every craftsman page draws its colours from -- the dashboard, reports, diffs. A page puts
`THEME_CSS` into its <style> and uses only the variables below; no page defines a colour of its own.

Almost-black background, slightly lighter cards with a thin border and rounded corners; accents in indigo (--blue),
mint (--green), orange (--amber), pink and violet; red for what failed. Each accent has a `-dim` tint for borders
and a `-bg` tint for fills.

The review page adds a neon green (--neon) for progress and the one thing to do now, a light blue (--change) for a
modified file, softer severity colours (--must, --should, --nit), lines between areas (--line, --line2) and a shadow
for what floats above the page."""

THEME_CSS = '''
  :root {
    --bg: #0b0b0c; --panel: #121214; --panel2: #1a1a1e; --hover: #1f1f24; --border: #26262b;
    --text: #e4e4e7; --heading: #fafafa; --muted: #8a8a93;
    --blue: #8b93f8; --green: #5fd4a0; --amber: #f2a65a; --pink: #ec7ab8; --violet: #a78bfa; --red: #f47174;
    --blue-dim: rgba(139, 147, 248, .35); --blue-bg: rgba(139, 147, 248, .12);
    --green-dim: rgba(95, 212, 160, .35); --green-bg: rgba(95, 212, 160, .12);
    --amber-dim: rgba(242, 166, 90, .35); --amber-bg: rgba(242, 166, 90, .12);
    --red-dim: rgba(244, 113, 116, .35); --red-bg: rgba(244, 113, 116, .12);
    --violet-dim: rgba(167, 139, 250, .35); --violet-bg: rgba(167, 139, 250, .12);
    --code-bg: #0f0f11; --switch-off: #3a3a40; --knob: #d4d4d8;
    --neon: #53e36b; --neon-strong: #2f9e44; --neon-dim: rgba(83, 227, 107, .4); --neon-bg: rgba(83, 227, 107, .1);
    --added-bg: rgba(83, 227, 107, .06); --removed-bg: rgba(255, 107, 107, .08); --removed-text: #f3c4c4;
    --change: #7fb2ff; --change-bg: rgba(127, 178, 255, .1);
    --must: #ff6b6b; --must-bg: rgba(255, 107, 107, .1); --should: #f5c26b; --should-bg: rgba(245, 194, 107, .1);
    --nit: #9a9a9a; --nit-dot: #6b6b6b; --nit-bg: rgba(255, 255, 255, .06);
    --select: #b69cff; --select-bg: rgba(182, 156, 255, .14);
    --card: #141414; --card2: #1a1a1a; --float: #1d1d1d; --dim: #5a5a5a;
    --line: rgba(255, 255, 255, .08); --line2: rgba(255, 255, 255, .14); --shadow: rgba(0, 0, 0, .7); --scrim: rgba(0, 0, 0, .55);
    --radius: 12px; --radius-sm: 8px; --pill: 999px;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
'''
