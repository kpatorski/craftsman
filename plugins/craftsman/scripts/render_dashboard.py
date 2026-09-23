#!/usr/bin/env python3
"""Renders a single, self-contained, dark-theme local HTML dashboard for the installed craftsman content -- help
text, and every bundle/protocol/directive with its enabled/disabled state, description, and a copy-pasteable
`/craftsman:enable`/`/craftsman:disable` command -- backing the `dashboard` skill (see MANAGEMENT.md, "Dashboard").

Read-only: never writes to the content tree, and the page itself cannot either (a static file has no access to
the filesystem it was generated from). Toggling a row shows the exact command to run, ready to copy -- it does
not flip anything live. See MANAGEMENT.md, "Dashboard" for why: a real write-back would need a background local
server, a new kind of component this project does not otherwise run, for a convenience the copy-paste command
already gets most of the way to.

Every id/title/description shown comes from the entry's own file (frontmatter), never from the index table's Id/
Title cells -- the index is a lookup table, the file is the single source of truth, same principle `core.md`
already applies everywhere else in this content tree.

Usage:
    render_dashboard.py <content-root> --output /path/to/out.html [--open]

`<content-root>` is `~/.claude/craftsman/` (directives/, protocols/, bundles/, each with an index.md). The
`help` skill's own command block is pulled from this script's own plugin install (`../skills/help/SKILL.md`,
relative to this file) -- never re-derived or duplicated, the same file `/craftsman:help` itself prints verbatim.
"""
import argparse
from datetime import datetime
import html
import pathlib
import platform
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _frontmatter import parse_frontmatter, split_frontmatter  # noqa: E402

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent

ROW_RE = re.compile(r"^\|(.*)\|\s*$")
LINK_RE = re.compile(r"^\[([a-z0-9-]+)\]\(([^)]+)\)$")
BARE_ID_RE = re.compile(r"^[a-z0-9-]+$")


def split_row(line):
    return [c.strip() for c in ROW_RE.match(line).group(1).split("|")]


def scan_tables(text):
    """Yield (category, status, rows) for every **Enabled**/**Disabled** block in document order. `category` is
    the nearest preceding `##`/`###` heading, hashes stripped. `rows` is the list of raw data-row lines (header
    and delimiter row consumed, never yielded), or [] for an "Empty -- ..." prose section."""
    lines = text.splitlines()
    category = None
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            category = stripped.lstrip("#").strip()
            i += 1
            continue
        if stripped in ("**Enabled**", "**Disabled**"):
            status = "enabled" if stripped == "**Enabled**" else "disabled"
            i += 1
            while i < n and lines[i].strip() == "":
                i += 1
            if i < n and lines[i].strip().startswith("Empty"):
                yield category, status, []
                i += 1
                continue
            rows = []
            if i < n and lines[i].strip().startswith("|"):
                i += 1  # header row
                if i < n and lines[i].strip().startswith("|"):
                    i += 1  # delimiter row
                while i < n and lines[i].strip().startswith("|"):
                    rows.append(lines[i].strip())
                    i += 1
            yield category, status, rows
            continue
        i += 1


def row_id_and_path(row_line):
    """-> (id, relative_path_or_None). Handles both shapes this tree uses: the Id cell itself as a
    `[id](path)` link (directives/index.md, protocols/index.md, every bundle.md), or a bare Id cell with a
    separate trailing `Path` link column (bundles/index.md, which also carries a `Requires` column)."""
    cells = split_row(row_line)
    id_cell = cells[1] if len(cells) > 1 else ""
    m = LINK_RE.match(id_cell)
    if m:
        return m.group(1), m.group(2)
    if BARE_ID_RE.fullmatch(id_cell):
        last = cells[-1] if cells else ""
        m2 = LINK_RE.match(last)
        return id_cell, (m2.group(2) if m2 else None)
    return None, None


def read_meta(path):
    """(title, description) from a directive/protocol/bundle file's own frontmatter -- never from an index row,
    which only exists as a lookup, per this content tree's single-source-of-truth rule."""
    if path is None or not path.exists():
        return "", ""
    fm_text, _ = split_frontmatter(path.read_text(errors="replace"))
    if fm_text is None:
        return "", ""
    fm = parse_frontmatter(fm_text)
    title = str(fm.get("title") or "").strip()
    description = " ".join(str(fm.get("description") or "").split())
    return title, description


def read_requires(path):
    if path is None or not path.exists():
        return []
    fm_text, _ = split_frontmatter(path.read_text(errors="replace"))
    if fm_text is None:
        return []
    fm = parse_frontmatter(fm_text)
    req = fm.get("requires")
    return [str(r) for r in req] if isinstance(req, list) else []


def entries_from_top_index(root, folder, kind):
    """`directives/index.md` or `protocols/index.md` -- the fundament, links resolved relative to `folder`."""
    index_path = root / folder / "index.md"
    if not index_path.exists():
        return []
    out = []
    for category, status, rows in scan_tables(index_path.read_text(errors="replace")):
        for row in rows:
            entry_id, rel_path = row_id_and_path(row)
            if entry_id is None:
                continue
            file_path = (root / folder / rel_path) if rel_path else None
            title, description = read_meta(file_path)
            out.append(dict(kind=kind, id=entry_id, title=title, description=description,
                             enabled=(status == "enabled"), category=category, bundle=None,
                             requires=[], path=file_path))
    return out


def entries_from_bundle(root, bundle_id):
    """A bundle's own `## Protocols` / `## Directives` tables, links resolved relative to the bundle's own dir."""
    bundle_dir = root / "bundles" / bundle_id
    bundle_md = bundle_dir / "bundle.md"
    if not bundle_md.exists():
        return []
    out = []
    for category, status, rows in scan_tables(bundle_md.read_text(errors="replace")):
        if category == "Protocols":
            kind = "protocol"
        elif category == "Directives":
            kind = "directive"
        else:
            continue
        for row in rows:
            entry_id, rel_path = row_id_and_path(row)
            if entry_id is None:
                continue
            file_path = (bundle_dir / rel_path) if rel_path else None
            title, description = read_meta(file_path)
            out.append(dict(kind=kind, id=entry_id, title=title, description=description,
                             enabled=(status == "enabled"), category=None, bundle=bundle_id,
                             requires=[], path=file_path))
    return out


def collect_entries(root):
    entries = entries_from_top_index(root, "directives", "directive")
    entries += entries_from_top_index(root, "protocols", "protocol")

    bundles_index = root / "bundles" / "index.md"
    if bundles_index.exists():
        for category, status, rows in scan_tables(bundles_index.read_text(errors="replace")):
            if category != "Bundles":
                continue
            for row in rows:
                bundle_id, _rel = row_id_and_path(row)
                if bundle_id is None:
                    continue
                bundle_md = root / "bundles" / bundle_id / "bundle.md"
                title, description = read_meta(bundle_md)
                entries.append(dict(kind="bundle", id=bundle_id, title=title, description=description,
                                     enabled=(status == "enabled"), category=None, bundle=None,
                                     requires=read_requires(bundle_md), path=bundle_md))
                entries += entries_from_bundle(root, bundle_id)
    return entries


def help_block(plugin_root):
    path = plugin_root / "skills" / "help" / "SKILL.md"
    if not path.exists():
        return ""
    m = re.search(r"```\n(.*?)```", path.read_text(errors="replace"), re.DOTALL)
    return m.group(1).rstrip("\n") if m else ""


# ---- rendering --------------------------------------------------------------------------------------------


# ---- markdown -> html (just enough for directive/protocol/bundle files) -----------------------------------------

def render_inline(text, known_ids):
    """Inline markdown: code spans, links, bold, italic. A relative link to another entry's file becomes a
    `data-goto` link that switches the panel to that entry; any other relative link is shown as plain text (a
    `file://` hop out of the page is exactly what the panel exists to avoid)."""
    spans = []

    def stash(m):
        spans.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)

    def link(m):
        label, url = m.group(1), html.unescape(m.group(2))
        if re.match(r"https?://", url):
            return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{label}</a>'
        target = re.search(r"([a-z0-9-]+)/(?:directive|protocol|bundle)\.md$", url)
        if target and target.group(1) in known_ids:
            return f'<a href="#" data-goto="{target.group(1)}">{label}</a>'
        return f'<span class="ref">{label}</span>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)


LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def render_list(items, known_ids):
    """`items` is [(indent, ordered, text)]; nesting follows indentation."""
    out, stack = [], []  # stack of (indent, tag)
    for indent, ordered, text in items:
        tag = "ol" if ordered else "ul"
        while stack and indent < stack[-1][0]:
            out.append(f"</li></{stack.pop()[1]}>")
        if stack and indent > stack[-1][0]:
            out.append(f"<{tag}>")
            stack.append((indent, tag))
        elif not stack:
            out.append(f"<{tag}>")
            stack.append((indent, tag))
        else:
            out.append("</li>")
        out.append(f"<li>{render_inline(text, known_ids)}")
    while stack:
        out.append(f"</li></{stack.pop()[1]}>")
    return "".join(out)


def split_cells(line):
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") else inner
    return [c.strip().replace("\x00", "|") for c in inner.replace("\\|", "\x00").split("|")]


def is_block_start(line):
    st = line.strip()
    return (st.startswith("```") or st.startswith("#") or st.startswith(">") or st.startswith("|")
            or LIST_RE.match(line) is not None or st == "---")


def render_markdown(text, known_ids):
    fm_text, body = split_frontmatter(text)
    parts = []
    if fm_text is not None:
        parts.append(f'<pre class="fm">{html.escape(fm_text.strip())}</pre>')
    lines = body.split("\n")
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        st = line.strip()
        if not st:
            i += 1
        elif st.startswith("```"):
            code = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            parts.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
        elif re.match(r"#{1,6}\s", st):
            level = len(st) - len(st.lstrip("#"))
            parts.append(f"<h{level}>{render_inline(st[level:].strip(), known_ids)}</h{level}>")
            i += 1
        elif st == "---":
            parts.append("<hr>")
            i += 1
        elif st.startswith("|") and i + 1 < n and re.fullmatch(r"[\s|:\-]+", lines[i + 1].strip()):
            head = split_cells(lines[i])
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_cells(lines[i]))
                i += 1
            th = "".join(f"<th>{render_inline(c, known_ids)}</th>" for c in head)
            tr = "".join("<tr>" + "".join(f"<td>{render_inline(c, known_ids)}</td>" for c in r) + "</tr>"
                         for r in rows)
            parts.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>")
        elif st.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            parts.append(f"<blockquote>{render_inline(' '.join(quote), known_ids)}</blockquote>")
        elif LIST_RE.match(line):
            items = []
            while i < n:
                m = LIST_RE.match(lines[i])
                if m:
                    items.append([len(m.group(1)), m.group(2)[0].isdigit(), m.group(3).strip()])
                    i += 1
                elif lines[i].strip() and lines[i].startswith("  ") and items:
                    items[-1][2] += " " + lines[i].strip()  # wrapped continuation of the previous item
                    i += 1
                elif not lines[i].strip() and i + 1 < n and (LIST_RE.match(lines[i + 1])
                                                            or lines[i + 1].startswith("  ")):
                    i += 1
                else:
                    break
            parts.append(render_list([tuple(x) for x in items], known_ids))
        elif line.startswith("    "):
            code = []
            while i < n and (lines[i].startswith("    ") or not lines[i].strip()):
                code.append(lines[i][4:])
                i += 1
            parts.append(f"<pre><code>{html.escape(chr(10).join(code).rstrip())}</code></pre>")
        else:
            para = [st]
            i += 1
            while i < n and lines[i].strip() and not is_block_start(lines[i]) and not lines[i].startswith("    "):
                para.append(lines[i].strip())
                i += 1
            parts.append(f"<p>{render_inline(' '.join(para), known_ids)}</p>")
    return "\n".join(parts)


def doc_templates(entries, root):
    """One inert `<template>` per entry holding its rendered file; the panel copies from it on demand."""
    known = {e["id"] for e in entries}
    out = []
    for e in entries:
        path = e["path"]
        if path is None or not path.exists():
            continue
        try:
            rel = path.resolve().relative_to(root.resolve())
        except ValueError:
            rel = path
        body = render_markdown(path.read_text(errors="replace"), known)
        out.append(f'<template id="doc-{html.escape(e["id"])}" data-path="{html.escape(str(rel))}">{body}</template>')
    return "\n".join(out)


BADGE = {True: '<span class="badge on">ENABLED</span>', False: '<span class="badge off">DISABLED</span>'}


def file_link(entry_id, path):
    """A button, not a `file://` link: the panel shows the file inside the page instead of hopping out to the
    browser's raw file view."""
    if path is None or not path.exists():
        return ""
    return f'<button class="view" type="button" data-view="{html.escape(entry_id)}">view</button>'


def toggle_row(entry_id, enabled):
    cmd = f"/craftsman:{'disable' if enabled else 'enable'} {entry_id}"
    esc = html.escape(cmd)
    return (
        f'<input class="cmd" type="text" readonly value="{esc}" '
        f'onclick="this.select(); tryCopy(this)" title="click to select, then copy">'
    )


def entry_card(e, members_html=""):
    """One collapsible row: kind, id, title and status on the summary line; description, requires, the copyable
    command and the file link inside. A bundle's own members nest inside its body (`members_html`)."""
    search_key = html.escape(" ".join([e["id"], e["title"], e["description"], e["category"] or "",
                                        e["bundle"] or "", e["kind"]]).lower())
    requires = f'<div class="requires">requires: {html.escape(", ".join(e["requires"]))}</div>' if e["requires"] else ""
    desc = html.escape(e["description"]) if e["description"] else '<span class="muted">(no description)</span>'
    title = html.escape(e["title"]) if e["title"] else ""
    members = f'<div class="members">{members_html}</div>' if members_html else ""

    count = f'<span class="count">{members_html.count("<details")} items</span>' if members_html else ""
    return f"""
<details class="entry {'enabled' if e['enabled'] else 'disabled'} {e['kind']}" data-search="{search_key}">
  <summary>
    <span class="kind">{e['kind']}</span>
    <code class="id">{html.escape(e['id'])}</code>
    <span class="title">{title}</span>
    {count}
    {BADGE[e['enabled']]}
  </summary>
  <div class="body">
    <p class="desc">{desc}</p>
    {requires}
    <div class="row">
      {toggle_row(e['id'], e['enabled'])}
      {file_link(e['id'], e['path'])}
    </div>
    {members}
  </div>
</details>"""


def section_html(title, entries, group_by_category):
    if not entries:
        return f'<section><h2>{html.escape(title)}</h2><p class="muted">Empty.</p></section>'
    body = []
    if group_by_category:
        seen = []
        for e in entries:
            if e["category"] not in seen:
                seen.append(e["category"])
        for cat in seen:
            label = html.escape(cat) if cat else "Uncategorized"
            body.append(f'<h3 class="category">{label}</h3>')
            body.append('<div class="list">' + "".join(entry_card(e) for e in entries if e["category"] == cat) + "</div>")
    else:
        body.append('<div class="list">' + "".join(entry_card(e) for e in entries) + "</div>")
    return f'<section><h2>{html.escape(title)}</h2>{"".join(body)}</section>'


def bundle_section_html(bundles, members):
    if not bundles:
        return '<section><h2>Bundles</h2><p class="muted">Empty.</p></section>'
    cards = "".join(entry_card(b, "".join(entry_card(m) for m in members.get(b["id"], []))) for b in bundles)
    return f'<section><h2>Bundles</h2><div class="list">{cards}</div></section>'


PAGE_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #1e1e1e; --panel: #252526; --border: #333; --text: #d4d4d4; --heading: #f0f0f0;
    --green: #4ec9b0; --blue: #9cdcfe; --muted: #808080;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--bg); color: var(--text); margin: 0; padding: 2rem 2rem 4rem;
    font-family: -apple-system, "Segoe UI", sans-serif;
  }
  h1 { color: var(--heading); font-size: 1.5rem; margin: 0 0 .2rem; }
  .subtitle { color: var(--muted); font-size: .85rem; margin: 0 0 1.5rem; }
  #search {
    width: 100%; max-width: 32rem; padding: .6rem .8rem; margin: 2rem 0 0;
    background: var(--panel); color: var(--text); border: 1px solid var(--border); border-radius: 6px;
    font-size: .95rem;
  }
  #search:focus { outline: none; border-color: var(--blue); }
  h2 {
    color: var(--blue); font-size: 1.1rem; border-bottom: 1px solid var(--border); padding-bottom: .4rem;
    margin-top: 2.5rem;
  }
  h3.category { color: var(--green); font-size: .9rem; text-transform: uppercase; letter-spacing: .04em;
    margin: 1.5rem 0 .6rem; }
  .list { display: flex; flex-direction: column; gap: .35rem; }
  details.entry { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; }
  details.entry.enabled { border-left: 3px solid var(--green); }
  details.entry.disabled { border-left: 3px solid var(--muted); }
  details.entry.hidden { display: none; }
  summary { display: flex; align-items: baseline; gap: .6rem; padding: .5rem .8rem; cursor: pointer; list-style: none; }
  summary::-webkit-details-marker { display: none; }
  summary::before { content: "\\25B8"; color: var(--muted); font-size: .75rem; }
  details[open] > summary::before { content: "\\25BE"; }
  summary:hover { background: #2a2d2e; }
  .kind { font-size: .68rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); width: 4.6rem; flex: none; }
  .id { color: var(--blue); font-family: "SF Mono", Menlo, Consolas, monospace; font-size: .85rem; flex: none; }
  .title { color: var(--text); font-size: .88rem; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .count { color: var(--muted); font-size: .75rem; flex: none; }
  .badge { font-size: .62rem; padding: .1rem .5rem; border-radius: 999px; letter-spacing: .03em; flex: none; }
  .badge.on { color: var(--green); border: 1px solid var(--green); background: rgba(78,201,176,.12); }
  .badge.off { color: var(--muted); border: 1px solid #555; background: rgba(128,128,128,.1); }
  .body { padding: .2rem .9rem .8rem 1.9rem; border-top: 1px solid var(--border); }
  .desc { font-size: .85rem; line-height: 1.5; margin: .7rem 0 .5rem; }
  .requires { font-size: .75rem; color: var(--muted); margin-bottom: .5rem; }
  .row { display: flex; align-items: center; gap: .8rem; }
  .cmd {
    flex: 1; min-width: 0; background: #1a1a1a; color: var(--green); border: 1px solid var(--border); border-radius: 4px;
    padding: .3rem .5rem; font-family: "SF Mono", Menlo, Consolas, monospace; font-size: .78rem;
  }
  .members { display: flex; flex-direction: column; gap: .3rem; margin-top: .8rem; }
  .muted { color: var(--muted); }
  pre.help { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 1rem;
    overflow-x: auto; font-family: "SF Mono", Menlo, Consolas, monospace; font-size: .82rem; line-height: 1.5; }
  .wrap { max-width: 1700px; margin: 0 auto; }
  .layout { max-width: 1100px; margin: 0 auto; }
  .layout.with-panel {
    max-width: none; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1.8rem;
    align-items: start;
  }
  #panel { display: none; }
  .with-panel #panel {
    display: block; position: sticky; top: 1rem; height: calc(100vh - 2rem); overflow: auto; background: var(--panel);
    border: 1px solid var(--border); border-radius: 8px; padding: 0 1.3rem 1.5rem;
  }
  .panel-head {
    position: sticky; top: 0; background: var(--panel); padding: .9rem 0 .6rem; border-bottom: 1px solid var(--border);
    display: flex; align-items: baseline; gap: .7rem; margin-bottom: .8rem;
  }
  .panel-head code { color: var(--blue); }
  #panel-path { color: var(--muted); font-size: .75rem; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  #panel-close { background: none; border: 0; color: var(--muted); font-size: 1.2rem; cursor: pointer; }
  #panel-close:hover { color: var(--heading); }
  button.view {
    background: none; border: 1px solid var(--border); color: var(--blue); border-radius: 4px; padding: .25rem .6rem;
    font-size: .78rem; cursor: pointer; white-space: nowrap;
  }
  button.view:hover { border-color: var(--blue); }
  .md { font-size: .86rem; line-height: 1.6; }
  .md h1, .md h2, .md h3, .md h4 { color: var(--heading); border: 0; margin: 1.3rem 0 .5rem; }
  .md h1 { font-size: 1.25rem; } .md h2 { font-size: 1.05rem; color: var(--blue); } .md h3, .md h4 { font-size: .95rem; }
  .md p { margin: .5rem 0; }
  .md code { background: #1a1a1a; border-radius: 3px; padding: .05rem .3rem; color: var(--green);
    font-family: "SF Mono", Menlo, Consolas, monospace; font-size: .8rem; }
  .md pre { background: #1a1a1a; border: 1px solid var(--border); border-radius: 6px; padding: .7rem .9rem; overflow-x: auto; }
  .md pre code { background: none; padding: 0; color: var(--text); }
  .md pre.fm { color: var(--muted); }
  .md table { border-collapse: collapse; margin: .7rem 0; display: block; overflow-x: auto; }
  .md th, .md td { border: 1px solid var(--border); padding: .3rem .6rem; text-align: left; vertical-align: top; }
  .md th { background: #2a2d2e; color: var(--heading); }
  .md blockquote { border-left: 3px solid var(--blue); margin: .6rem 0; padding: .1rem .9rem; color: var(--muted); }
  .md ul, .md ol { padding-left: 1.4rem; margin: .4rem 0; } .md li { margin: .2rem 0; }
  .md a { color: var(--blue); } .md .ref { color: var(--muted); }
  @media (max-width: 1000px) {
    .layout.with-panel { grid-template-columns: 1fr; }
    .with-panel #panel { position: static; height: auto; max-height: 75vh; }
  }
</style>
</head>
<body>
<div class="wrap"><div class="layout"><main>
<h1>__TITLE__</h1>
<p class="subtitle">__SUBTITLE__</p>
<section><h2>Commands</h2><pre class="help">__HELP__</pre></section>
<input id="search" type="text" placeholder="Filter bundles, protocols and directives by id, title, description...">
__BODY__
</main>
<aside id="panel">
  <div class="panel-head"><code id="panel-id"></code><span id="panel-path"></span>
    <button id="panel-close" type="button" title="clear">&times;</button></div>
  <div id="panel-body" class="md"></div>
</aside>
</div></div>
__DOCS__
<script>
function tryCopy(el) {
  try { document.execCommand('copy'); } catch (e) { /* select-and-manual-copy still works */ }
}
var currentDoc = null;
function syncViewButtons() {
  document.querySelectorAll('button.view').forEach(function (b) {
    b.textContent = (b.getAttribute('data-view') === currentDoc) ? 'hide' : 'view';
  });
}
function showDoc(id) {
  var t = document.getElementById('doc-' + id);
  if (!t) { return; }
  currentDoc = id;
  document.querySelector('.layout').classList.add('with-panel');
  document.getElementById('panel-id').textContent = id;
  document.getElementById('panel-path').textContent = t.getAttribute('data-path');
  document.getElementById('panel-body').innerHTML = t.innerHTML;
  document.getElementById('panel').scrollTop = 0;
  syncViewButtons();
}
function hidePanel() {
  currentDoc = null;
  document.querySelector('.layout').classList.remove('with-panel');
  syncViewButtons();
}
document.addEventListener('click', function (ev) {
  var view = ev.target.closest('[data-view]');
  if (view) {
    var id = view.getAttribute('data-view');
    if (id === currentDoc) { hidePanel(); } else { showDoc(id); }
    return;
  }
  var go = ev.target.closest('[data-goto]');
  if (go) { ev.preventDefault(); showDoc(go.getAttribute('data-goto')); return; }
  if (ev.target.id === 'panel-close') { hidePanel(); }
});
// Word-based matching: every word of the query must appear somewhere in an entry (any order), hyphens and other
// punctuation count as spaces (so "test coverage" finds `check-coverage`), and a trailing plural "s" is ignored.
function norm(t) { return t.toLowerCase().replace(/[^a-z0-9]+/g, ' '); }
function stem(w) { return (w.length > 3 && /s$/.test(w) && !/ss$/.test(w)) ? w.slice(0, -1) : w; }
document.getElementById('search').addEventListener('input', function () {
  var words = norm(this.value).split(' ').filter(Boolean).map(stem);
  var q = words.length > 0;
  var all = Array.prototype.slice.call(document.querySelectorAll('details.entry'));
  // undo whatever the previous keystroke opened, so refining or clearing the query restores the collapsed view
  all.forEach(function (el) {
    if (el.hasAttribute('data-auto')) { el.open = false; el.removeAttribute('data-auto'); }
  });
  all.reverse().forEach(function (el) {  // children first
    if (el._hay === undefined) { el._hay = ' ' + norm(el.getAttribute('data-search')) + ' '; }
    var own = !q || words.every(function (w) { return el._hay.indexOf(w) !== -1; });
    var childShown = el.querySelector('details.entry:not(.hidden)') !== null;
    el.classList.toggle('hidden', !(own || childShown));
    // only a container is opened, and only to reveal a matching descendant -- a plain match stays collapsed
    if (q && childShown && !el.open) { el.open = true; el.setAttribute('data-auto', '1'); }
  });
});
</script>
</body>
</html>
"""


def build_page(root):
    entries = collect_entries(root)
    # Fundament sections show only entries with no owning bundle -- a bundle's own protocols/directives are
    # rendered once, nested under that bundle's card, never duplicated into the flat top-level list too.
    directives = [e for e in entries if e["kind"] == "directive" and e["bundle"] is None]
    protocols = [e for e in entries if e["kind"] == "protocol" and e["bundle"] is None]
    bundles = [e for e in entries if e["kind"] == "bundle"]
    members = {}
    for e in entries:
        if e["bundle"]:
            members.setdefault(e["bundle"], []).append(e)

    body = (
        bundle_section_html(bundles, members)
        + section_html("Protocols", protocols, group_by_category=True)
        + section_html("Directives", directives, group_by_category=True)
    )

    page = PAGE_SHELL
    page = page.replace("__TITLE__", "craftsman dashboard")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    page = page.replace("__SUBTITLE__", html.escape(f"content root: {root}  \u00b7  generated {stamp} (a snapshot -- re-run /craftsman:dashboard to refresh)"))
    page = page.replace("__HELP__", html.escape(help_block(PLUGIN_ROOT)))
    page = page.replace("__BODY__", body)
    page = page.replace("__DOCS__", doc_templates(entries, root))
    return page


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
    parser.add_argument("content_root")
    parser.add_argument("--output", required=True)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    root = pathlib.Path(args.content_root).expanduser()
    page = build_page(root)
    with open(args.output, "w") as f:
        f.write(page)

    file_url = pathlib.Path(args.output).resolve().as_uri()
    print(file_url)

    if args.open:
        open_in_browser(args.output)


if __name__ == "__main__":
    main()
