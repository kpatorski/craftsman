"""What the live dashboard shows, as one JSON-ready dict: a project's artifacts and session files (raw text plus
pre-rendered HTML -- the page parses the raw text for its structured views and falls back to the HTML), and the
installed content (every bundle/protocol/directive, its state, its own file rendered). `dashboard_server.py` serves
it; `watched_paths` lists what to poll for changes. Stdlib only, like every other script here."""
import json
import pathlib
import re

from _markdown import render_markdown
from render_dashboard import collect_entries, help_block

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTIFACTS = ("business-rules.md", "open-questions.md", "event-model.md")


def split_sections(text):
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]


def count_items(body):
    subsections = len(re.findall(r"^### ", body, flags=re.M))
    return subsections or len(re.findall(r"^(?:\d+\.|-) ", body, flags=re.M))


def kind_of(rel):
    if rel.parts[:2] == (".claude", "sessions"):
        return "session"
    if rel.parts[0] == "specs":
        return "specs-index" if rel.name == "README.md" else "spec"
    return {"business-rules.md": "business-rules", "open-questions.md": "open-questions",
            "event-model.md": "event-model"}.get(rel.name, "markdown")


def project_paths(project):
    paths = [project / n for n in ARTIFACTS]
    paths += sorted((project / "specs").glob("*.md"))
    paths += sorted((project / ".claude" / "sessions").glob("*.md"))
    return [p for p in paths if p.is_file()]


def project_files(project):
    files = []
    for path in project_paths(project):
        rel = path.relative_to(project)
        try:
            text = path.read_text(errors="replace")
            mtime = path.stat().st_mtime
        except OSError:
            continue
        no_links = lambda url: None  # noqa: E731
        sections = [dict(title=t, html=render_markdown(b, no_links), count=count_items(b)) for t, b in split_sections(text)]
        files.append(dict(id="file:" + str(rel), rel=str(rel), kind=kind_of(rel), raw=text,
                          html=render_markdown(text, no_links), sections=sections, mtime=mtime))
    return files


def library(content):
    entries = collect_entries(content) if content.exists() else []
    by_path = {e["path"].resolve(): "lib:" + e["id"] for e in entries if e["path"] is not None}

    def resolver(base):
        def resolve(url):
            target = url.split("#")[0]
            return by_path.get((base / target).resolve()) if target else None
        return resolve

    out, docs = [], {}
    for e in entries:
        doc_id = "lib:" + e["id"]
        if e["path"] is not None and e["path"].exists():
            docs[doc_id] = render_markdown(e["path"].read_text(errors="replace"), resolver(e["path"].parent))
        out.append(dict(kind=e["kind"], id=e["id"], title=e["title"], description=e["description"],
                        enabled=e["enabled"], bundle=e["bundle"], category=e["category"], requires=e["requires"],
                        doc=doc_id if doc_id in docs else None))
    return out, docs


def manage_info(content):
    plugin_json = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    marker = content / ".craftsman-plugin-version"
    sources = ""
    index = content / "directives" / "index.md"
    if index.exists():
        for title, body in split_sections(index.read_text(errors="replace")):
            if title.lower() == "sources":
                sources = render_markdown(body, lambda url: None)
    return dict(plugin=json.loads(plugin_json.read_text()).get("version", "?") if plugin_json.exists() else "?",
                content=marker.read_text().strip() if marker.exists() else "?", sources=sources,
                content_root=str(content))


def build(project, content, projects):
    """`project` may be None (every project was taken off the page): the installed content still shows."""
    lib, docs = library(content)
    return dict(project=dict(name=project.name, path=str(project)) if project else None,
                projects=[str(p) for p in projects], files=project_files(project) if project else [], library=lib, docs=docs, help=help_block(PLUGIN_ROOT),
                manage=manage_info(content))


def watched_paths(projects, content):
    """Every file whose change should refresh the page: each project's artifacts and sessions (plus the folders
    themselves, so a new file shows up), and the content tree's indexes and entries."""
    paths = []
    for project in projects:
        paths += project_paths(project)
        paths += [project, project / "specs", project / ".claude" / "sessions"]
    if content.exists():
        paths += list(content.glob("*/index.md")) + list(content.glob("bundles/*/bundle.md"))
        paths += list(content.glob("*/*/*.md")) + list(content.glob("bundles/*/*/*/*.md"))
    return paths
