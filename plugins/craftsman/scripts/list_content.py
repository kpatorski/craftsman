#!/usr/bin/env python3
"""Print what's installed and enabled/disabled — the deterministic backbone for `/craftsman:list`. Reads the
index files and prints their tables verbatim; the index files are the single source of truth for current state
(see `EXECUTION.md`, "Loading directives"), so there is nothing to compose or re-derive, only to read and print.

Usage:
    list_content.py <content-root> [directives|protocols|bundles]

No second argument prints all three. For `bundles`, each bundle's own `bundle.md` Protocols/Directives tables are
printed nested under its row, matching how a developer actually wants to read "what's inside this bundle" without
a second command.
"""
import re
import sys
import pathlib

SECTION_HEADING = {"directives": "## Directives", "protocols": "## Protocols", "bundles": "## Bundles"}
INDEX_FILE = {"directives": "index.md", "protocols": "index.md", "bundles": "index.md"}

BUNDLE_ROW_RE = re.compile(r"^\|\s*\d+\s*\|(.+)$")
LINKED_ID_RE = re.compile(r"^\s*\[([a-z0-9-]+)\]\(")
BARE_ID_RE = re.compile(r"^[a-z0-9-]+$")


def bundle_row_ids(section_text):
    """`bundles/index.md`'s own table uses a bare id cell (its separate `Path` column carries the link) --
    unlike `directives/index.md`/`protocols/index.md`, whose id cell is itself a markdown link. Handle both."""
    ids = []
    for line in section_text.splitlines():
        m = BUNDLE_ROW_RE.match(line)
        if not m:
            continue
        first_cell = m.group(1).split("|", 1)[0].strip()
        linked = LINKED_ID_RE.match(first_cell)
        if linked:
            ids.append(linked.group(1))
        elif BARE_ID_RE.fullmatch(first_cell):
            ids.append(first_cell)
    return ids


def section_from(text, heading):
    """Everything from `heading` (a `## ` line) to the next `## ` line at the same level, or EOF."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == heading), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).rstrip()


def print_kind(root, kind):
    if kind == "bundles":
        index_path = pathlib.Path(root) / "bundles" / "index.md"
        if not index_path.exists():
            print(f"(no bundles/index.md under {root})")
            return
        section = section_from(index_path.read_text(), "## Bundles")
        print(section or "(no ## Bundles section found)")
        for bundle_id in (bundle_row_ids(section) if section else []):
            bundle_md = pathlib.Path(root) / "bundles" / bundle_id / "bundle.md"
            if not bundle_md.exists():
                print(f"\n  -- {bundle_id}: bundle.md not found at {bundle_md}")
                continue
            text = bundle_md.read_text()
            print(f"\n--- {bundle_id} ---")
            for sub in ("## Protocols", "## Directives"):
                sub_section = section_from(text, sub)
                if sub_section:
                    print(sub_section)
        return

    folder = kind  # "directives" or "protocols"
    index_path = pathlib.Path(root) / folder / "index.md"
    if not index_path.exists():
        print(f"(no {folder}/index.md under {root})")
        return
    section = section_from(index_path.read_text(), SECTION_HEADING[kind])
    print(section or f"(no {SECTION_HEADING[kind]} section found)")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(f"Usage: {sys.argv[0]} <content-root> [directives|protocols|bundles]")
    root = pathlib.Path(sys.argv[1])
    kind = sys.argv[2] if len(sys.argv) > 2 else None

    if not root.exists():
        print(f"{root} does not exist yet -- nothing installed. See MANAGEMENT.md / README.md, \"Installing\".")
        return

    kinds = [kind] if kind else ["directives", "protocols", "bundles"]
    for k in kinds:
        if k not in ("directives", "protocols", "bundles"):
            raise SystemExit(f"Unknown kind {k!r} -- expected directives, protocols, or bundles.")
        print(f"=== {k} ===\n")
        print_kind(root, k)
        print()


if __name__ == "__main__":
    main()
