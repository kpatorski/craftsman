#!/usr/bin/env python3
"""The directives a review checks the code against -- see REVIEW.md, "Directives".

    review_directives.py <review dir> [--content <content root>]

Every directive of the workshop, top-level or in a bundle, is listed with whether the workshop enables it -- a bundle
member only while its bundle is enabled -- and whether this review checks it: as the review's own switch says
(`directive-switches` in review.json), else as the developer's default set for every review says (`review-directives`
in the craftsman settings), else as the workshop says. The directives of the `code-review` bundle
are not listed: they say how a finding is kinded and written, not what the code is checked against.

From the command line it prints the directives the review checks, `[{"id", "title", "path"}]`, in the order of the
workshop's indexes. The review's agent checks every use case against all of them; it never picks among them.
"""
import argparse
import json
import pathlib
import sys

import review_state
from render_dashboard import collect_entries

REVIEW_BUNDLE = "code-review"
CONTENT = pathlib.Path.home() / ".claude" / "craftsman"
SCOPE = pathlib.Path("bundles") / REVIEW_BUNDLE / "directive-scope.md"
FILES = ("production", "tests", "all", "none")
REACH = ("file", "flow")
UNSCOPED = {"files": "all", "reach": "flow", "scoped": False}


def scope(content):
    """The review bundle's table of how each directive is checked: `{id: {"files", "reach", "scoped": True}}`. A row
    whose values the review does not know is left out, as if it were missing."""
    table = pathlib.Path(content) / SCOPE
    rows = {}
    for line in table.read_text().splitlines() if table.is_file() else []:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 3 or not cells[0].startswith("`"):
            continue
        entry_id, files, reach = cells[0].strip("`"), cells[1], cells[2]
        if files == "none" or (files in FILES and reach in REACH):
            rows[entry_id] = {"files": files, "reach": reach if files != "none" else None, "scoped": True}
    return rows


def listed(content, state, defaults=None):
    """Every directive the review could check: `id`, `title`, `description`, `bundle`, `path`, `enabled` (by the
    workshop), `default` (for every review: the developer's default set in `defaults`, else the workshop's) and `on`
    (for this review: its own switch, else the default)."""
    entries = collect_entries(pathlib.Path(content)) if pathlib.Path(content).exists() else []
    bundles = {e["id"]: e["enabled"] for e in entries if e["kind"] == "bundle"}
    switches, defaults = state.get("directive-switches") or {}, defaults or {}
    scoped = scope(content)
    out = []
    for e in entries:
        if e["kind"] != "directive" or e["bundle"] == REVIEW_BUNDLE:
            continue
        enabled = e["enabled"] and (e["bundle"] is None or bundles.get(e["bundle"], False))
        default = defaults.get(e["id"], enabled)
        out.append({"id": e["id"], "title": e["title"], "description": e["description"], "bundle": e["bundle"],
                    "path": str(e["path"]) if e["path"] else None, "enabled": enabled, "default": default,
                    "on": switches.get(e["id"], default), **scoped.get(e["id"], UNSCOPED)})
    return out


def to_check(content, state, defaults=None):
    """The directives this review checks: switched on, and not kept out of reviews by the review bundle's table."""
    return [d for d in listed(content, state, defaults) if d["on"] and d["files"] != "none"]


def unscoped(content, state, defaults=None):
    """The ids of the directives this review checks that have no row in the review bundle's table."""
    return [d["id"] for d in to_check(content, state, defaults) if not d["scoped"]]


def protocols(content):
    """The protocols of the `code-review` bundle, in its order, each with whether it is enabled."""
    entries = collect_entries(pathlib.Path(content)) if pathlib.Path(content).exists() else []
    return [{"id": e["id"], "title": e["title"], "enabled": e["enabled"]} for e in entries
            if e["kind"] == "protocol" and e["bundle"] == REVIEW_BUNDLE]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("review")
    parser.add_argument("--content", default=str(CONTENT))
    parser.add_argument("--unscoped", action="store_true", help="print the ids of the checked directives with no row")
    args = parser.parse_args(argv)
    import _settings  # reads the craftsman home, which _reviews names; _reviews imports this module
    state = review_state.read(pathlib.Path(args.review))
    content = pathlib.Path(args.content).expanduser()
    if args.unscoped:
        print(json.dumps(unscoped(content, state, _settings.review_directives())))
        return 0
    print(json.dumps([{key: d[key] for key in ("id", "title", "path", "files", "reach")}
                      for d in to_check(content, state, _settings.review_directives())], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
