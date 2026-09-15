#!/usr/bin/env python3
"""Render one or more unified diffs as a single, self-contained, dark-theme local HTML file — the mechanism
`core.md`'s `shows` field requires for any diff beyond a handful of lines (see "Fields specific to `protocol`").
Replaces pasting raw `+`/`-` text into the conversation, which does not scale past the first class a `tdd-loop`
touches, and replaces hand-rolling this HTML from scratch each time a checkpoint needs it.

Usage:
    render_diff.py --title "TITLE" --output /path/to/out.html \
        --section "Label one:/path/to/one.diff" \
        [--section "Label two:/path/to/two.diff" ...] \
        [--note "one-line context shown under the title"] \
        [--open]

Each `--section` is `Label:path-to-a-unified-diff-file` (a real file, e.g. from `git diff ... > path`) — one
section per diff, in the order given; a single-diff checkpoint (review-design-direction, refactor-tests,
refactor-production, finish-loop) passes exactly one, a multi-file conflict presentation
(MANAGEMENT.md, "Presenting a conflict") passes one per file times up to two (baseline->local, baseline->upstream).

Always prints a `file://` URL for the result — the primary, portable way to hand it to the developer: clickable or
copy-pasteable in any terminal, on any OS, in any environment (remote session, sandboxed shell, no browser
installed locally at all). Do not rely on a chat UI's file card alone; it does not always render visibly.

--open additionally runs the platform's "open with default app" command (`open` on macOS, `xdg-open` on Linux,
`start` on Windows) as a convenience on top of the link — best-effort, not the primary mechanism, since it does
nothing useful on a platform without a local default-browser command (e.g. many remote/server environments).
"""
import argparse
import html
import pathlib
import platform
import subprocess
import sys


def render_diff_lines(diff_text):
    out = []
    for line in diff_text.splitlines():
        esc = html.escape(line)
        cls = ""
        if line.startswith("+++") or line.startswith("---"):
            cls = "hdr"
        elif line.startswith("@@"):
            cls = "hunk"
        elif line.startswith("+"):
            cls = "add"
        elif line.startswith("-"):
            cls = "del"
        out.append(f'<span class="{cls}">{esc}</span>')
    return "\n".join(out)


def build_page(title, note, sections):
    section_html = []
    for label, diff_text in sections:
        section_html.append(f"<h2>{html.escape(label)}</h2>\n<pre>{render_diff_lines(diff_text)}</pre>")
    note_html = f'<p class="note">{html.escape(note)}</p>' if note else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  body {{ background: #1e1e1e; color: #d4d4d4; font-family: -apple-system, "Segoe UI", sans-serif; margin: 2rem; }}
  h1 {{ color: #f0f0f0; font-size: 1.3rem; }}
  h2 {{ color: #9cdcfe; font-size: 1.05rem; margin-top: 2rem; border-bottom: 1px solid #333; padding-bottom: .3rem; }}
  pre {{ background: #252526; border: 1px solid #333; border-radius: 6px; padding: 1rem; overflow-x: auto;
         font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 0.85rem; line-height: 1.5; }}
  .hdr {{ color: #808080; display: block; }}
  .hunk {{ color: #c586c0; display: block; }}
  .add {{ color: #4ec9b0; display: block; background: #14301f; }}
  .del {{ color: #f48771; display: block; background: #3a1d1d; }}
  .note {{ color: #808080; font-size: 0.85rem; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
{note_html}
{"".join(section_html)}
</body>
</html>
"""


def open_in_browser(path):
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", path], check=False)
    elif system == "Linux":
        subprocess.run(["xdg-open", path], check=False)
    elif system == "Windows":
        subprocess.run(["start", "", path], shell=True, check=False)
    else:
        print(f"Don't know how to auto-open on {system} -- open {path} manually.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--title", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--section", action="append", required=True, help="Label:path-to-diff-file, repeatable")
    parser.add_argument("--note", default="")
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    sections = []
    for raw in args.section:
        if ":" not in raw:
            raise SystemExit(f"--section must be Label:path, got: {raw!r}")
        label, path = raw.split(":", 1)
        with open(path) as f:
            sections.append((label, f.read()))

    page = build_page(args.title, args.note, sections)
    with open(args.output, "w") as f:
        f.write(page)

    file_url = pathlib.Path(args.output).resolve().as_uri()
    print(file_url)

    if args.open:
        open_in_browser(args.output)


if __name__ == "__main__":
    main()
