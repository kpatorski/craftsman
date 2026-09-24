#!/usr/bin/env python3
"""Renders a project's craftsman results -- the analysis artifacts and the session file(s) -- as one self-contained,
dark-theme local HTML page, in the same style as the dashboard. The markdown files stay the source of truth; this
is a reading view over them, regenerated from disk each time it runs (a snapshot, not a live view).

Deliberately generic: the formats of these files are defined by the installed workshop, not by this plugin, so
nothing here parses their structure. It looks for the known files, renders each one as markdown, and puts them
behind a navigation list with a search box. A workshop that writes different files is unaffected -- it just
won't show those until they are added to the list below.

Looks for, in the project directory:
    business-rules.md, open-questions.md, event-model.md      (analysis artifacts, project root)
    specs/README.md, specs/*.md                                (specs)
    .claude/sessions/*.md                                      (session files, newest first)

Usage:
    render_report.py [<project-dir>] [--output /path/to/report.html] [--doc <file.md> ...] [--open]

`--doc` (repeatable) names a file that was just written. The page is regenerated and, for each such file, two lines
are printed -- the full path of the markdown file and a `file://` link straight to that document inside the page --
so a step can always show both. A file the script would not otherwise look for is added under "Other".

`<project-dir>` defaults to the current directory. `--output` defaults to `<project-dir>/.claude/reports/report.html`
(next to the sessions, so it never clutters `git status`). Prints a `file://` link on success; exits 2 and writes
nothing when the project has none of the files above.
"""
import argparse
import html
import pathlib
import platform
import re
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _markdown import MD_CSS, render_markdown  # noqa: E402

ANALYSIS_FILES = ["business-rules.md", "open-questions.md", "event-model.md"]
STATE_RE = re.compile(r"\*\*State:\*\*\s*`(\w+)`")
LEGACY_STATE_RE = re.compile(r"^## Status\s*\n+\s*`(\w+)`", re.MULTILINE)


def slug(rel):
    return re.sub(r"[^a-z0-9]+", "-", str(rel).lower()).strip("-")


def doc_title(text, path):
    for line in text.splitlines():
        if line.startswith("# "):
            return re.sub(r"[`*_]", "", line[2:]).strip()  # nav shows plain text, not inline markdown
    return path.stem


def session_state(text):
    m = STATE_RE.search(text) or LEGACY_STATE_RE.search(text)
    return m.group(1) if m else None


def discover(project, extra=()):
    """-> list of dicts (group, path, rel, id, title, text, state), in the order they appear in the navigation."""
    found = []
    for name in ANALYSIS_FILES:
        p = project / name
        if p.is_file():
            found.append(("Analysis", p))
    specs = project / "specs"
    if specs.is_dir():
        readme = specs / "README.md"
        if readme.is_file():
            found.append(("Specs", readme))
        for p in sorted(specs.glob("*.md")):
            if p.name != "README.md":
                found.append(("Specs", p))
    sessions = project / ".claude" / "sessions"
    if sessions.is_dir():
        for p in sorted(sessions.glob("*.md"), key=lambda q: q.stat().st_mtime, reverse=True):
            found.append(("Sessions", p))
    listed = {p.resolve() for _, p in found}
    for p in extra:
        if p.resolve() not in listed:
            found.append(("Other", p))
            listed.add(p.resolve())
    docs = []
    for group, p in found:
        text = p.read_text(errors="replace")
        try:
            rel = p.resolve().relative_to(project)
        except ValueError:
            rel = pathlib.Path(p.name)  # outside the project: shown by name only
        docs.append(dict(group=group, path=p.resolve(), rel=rel, id=slug(rel), title=doc_title(text, p),
                         text=text, state=session_state(text) if group == "Sessions" else None))
    return docs


def nav_html(docs):
    out = []
    for group in ("Analysis", "Specs", "Sessions", "Other"):
        members = [d for d in docs if d["group"] == group]
        if not members:
            continue
        out.append(f'<div class="navgroup" data-group="{group}"><h3>{group}</h3>')
        for d in members:
            badge = f'<span class="state {html.escape(d["state"])}">{html.escape(d["state"])}</span>' if d["state"] else ""
            out.append(
                f'<a class="navlink" href="#{d["id"]}" data-doc="{d["id"]}">'
                f'{badge}<span class="navtitle">{html.escape(d["title"])}</span>'
                f'<span class="navpath">{html.escape(str(d["rel"]))}</span></a>')
        out.append("</div>")
    return "\n".join(out)


def articles_html(docs):
    by_path = {d["path"]: d["id"] for d in docs}
    out = []
    for d in docs:
        base = d["path"].parent

        def resolve(url, base=base):
            if re.match(r"[a-z]+:", url) or url.startswith("#"):
                return None
            target = url.split("#", 1)[0]
            return by_path.get((base / target).resolve()) if target else None

        body = render_markdown(d["text"], resolve)
        out.append(f'<article class="doc md" id="{d["id"]}" hidden>'
                   f'<div class="docpath">{html.escape(str(d["rel"]))}</div>{body}</article>')
    return "\n".join(out)


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
  body { background: var(--bg); color: var(--text); margin: 0; font-family: -apple-system, "Segoe UI", sans-serif; }
  .layout { display: grid; grid-template-columns: 320px minmax(0, 1fr); min-height: 100vh; }
  nav {
    position: sticky; top: 0; height: 100vh; overflow-y: auto; background: var(--panel);
    border-right: 1px solid var(--border); padding: 1.3rem 1rem 2rem;
  }
  nav h1 { color: var(--heading); font-size: 1.15rem; margin: 0; }
  .subtitle { color: var(--muted); font-size: .75rem; margin: .2rem 0 1rem; line-height: 1.4; }
  #search {
    width: 100%; padding: .5rem .7rem; margin-bottom: .4rem; background: var(--bg); color: var(--text);
    border: 1px solid var(--border); border-radius: 6px; font-size: .88rem;
  }
  #search:focus { outline: none; border-color: var(--blue); }
  #count { color: var(--muted); font-size: .72rem; min-height: 1rem; margin-bottom: .6rem; }
  .navgroup h3 {
    color: var(--green); font-size: .7rem; text-transform: uppercase; letter-spacing: .05em; margin: 1.1rem 0 .3rem;
  }
  .navlink {
    display: block; padding: .4rem .6rem; border-radius: 5px; border-left: 3px solid transparent; text-decoration: none;
    color: var(--text); margin-bottom: 2px;
  }
  .navlink:hover { background: #2a2d2e; }
  .navlink.active { background: #2f3336; border-left-color: var(--green); }
  .navlink.hidden, .navgroup.hidden { display: none; }
  .navtitle { display: block; font-size: .86rem; }
  .navpath { display: block; color: var(--muted); font-size: .68rem; font-family: "SF Mono", Menlo, Consolas, monospace; }
  .state { float: right; font-size: .62rem; padding: .05rem .45rem; border-radius: 999px; border: 1px solid var(--muted); color: var(--muted); }
  .state.active { color: var(--green); border-color: var(--green); }
  .state.blocked { color: #d7ba7d; border-color: #d7ba7d; }
  main { padding: 2rem 2.5rem 5rem; min-width: 0; }
  article.doc { max-width: 900px; margin: 0 auto; font-size: .92rem; }
  .docpath { color: var(--muted); font-size: .75rem; font-family: "SF Mono", Menlo, Consolas, monospace; margin-bottom: 1rem; }
  .empty { color: var(--muted); max-width: 900px; margin: 0 auto; }
  @media (max-width: 900px) {
    .layout { grid-template-columns: 1fr; }
    nav { position: static; height: auto; max-height: 45vh; border-right: 0; border-bottom: 1px solid var(--border); }
  }
</style>
</head>
<body>
<div class="layout">
<nav>
  <h1>__PROJECT__</h1>
  <p class="subtitle">craftsman report &middot; generated __STAMP__<br>a snapshot &mdash; re-run /craftsman:report to refresh</p>
  <input id="search" type="text" placeholder="Search all documents...">
  <div id="count"></div>
__NAV__
</nav>
<main>
__ARTICLES__
<p class="empty" id="none" hidden>No document matches.</p>
</main>
</div>
<script>
// Word-based search: every word must occur somewhere in a document (any order); hyphens count as spaces and a
// trailing plural "s" is ignored -- the same matching the dashboard uses.
function norm(t) { return t.toLowerCase().replace(/[^a-z0-9]+/g, ' '); }
function stem(w) { return (w.length > 3 && /s$/.test(w) && !/ss$/.test(w)) ? w.slice(0, -1) : w; }
var links = Array.prototype.slice.call(document.querySelectorAll('.navlink'));
var docs = Array.prototype.slice.call(document.querySelectorAll('article.doc'));
function show(id) {
  var found = false;
  docs.forEach(function (d) { var on = d.id === id; d.hidden = !on; found = found || on; });
  links.forEach(function (l) { l.classList.toggle('active', l.getAttribute('data-doc') === id); });
  if (found) { window.scrollTo(0, 0); }
  return found;
}
function route() {
  var id = decodeURIComponent(location.hash.slice(1));
  if (!show(id) && docs.length) { show(docs[0].id); }
}
window.addEventListener('hashchange', route);
document.addEventListener('click', function (ev) {
  var go = ev.target.closest('[data-goto]');
  if (go) { ev.preventDefault(); location.hash = go.getAttribute('data-goto'); }
});
document.getElementById('search').addEventListener('input', function () {
  var words = norm(this.value).split(' ').filter(Boolean).map(stem);
  var shown = 0;
  links.forEach(function (l) {
    var d = document.getElementById(l.getAttribute('data-doc'));
    if (d._hay === undefined) { d._hay = ' ' + norm(d.textContent) + ' '; }
    var ok = words.every(function (w) { return d._hay.indexOf(w) !== -1; });
    l.classList.toggle('hidden', !ok);
    if (ok) { shown += 1; }
  });
  document.querySelectorAll('.navgroup').forEach(function (g) {
    g.classList.toggle('hidden', g.querySelectorAll('.navlink:not(.hidden)').length === 0);
  });
  document.getElementById('count').textContent = words.length ? shown + ' of ' + links.length + ' documents' : '';
  document.getElementById('none').hidden = shown !== 0;
});
route();
</script>
</body>
</html>
"""


def build_page(project, docs):
    page = PAGE_SHELL.replace("</style>", MD_CSS + "</style>", 1)
    page = page.replace("__TITLE__", html.escape(f"{project.name} — craftsman report"))
    page = page.replace("__PROJECT__", html.escape(project.name))
    page = page.replace("__STAMP__", datetime.now().strftime("%Y-%m-%d %H:%M"))
    page = page.replace("__NAV__", nav_html(docs))
    page = page.replace("__ARTICLES__", articles_html(docs))
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
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--output")
    parser.add_argument("--doc", action="append", default=[])
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    project = pathlib.Path(args.project_dir).expanduser().resolve()
    extra = [pathlib.Path(d).expanduser().resolve() for d in args.doc]
    missing = [str(d) for d in extra if not d.is_file()]
    if missing:
        print(f"Not a file: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)
    docs = discover(project, extra)
    if not docs:
        print(f"No craftsman artifacts found in {project} (looked for {', '.join(ANALYSIS_FILES)}, specs/, "
              f".claude/sessions/).", file=sys.stderr)
        sys.exit(2)

    output = pathlib.Path(args.output).expanduser() if args.output else project / ".claude" / "reports" / "report.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_page(project, docs))
    url = output.resolve().as_uri()
    by_path = {d["path"]: d["id"] for d in docs}
    if extra:
        for d in extra:
            print(f"md:   {d}")
            print(f"html: {url}#{by_path[d]}")
    else:
        print(url)
    if args.open:
        open_in_browser(str(output))


if __name__ == "__main__":
    main()
