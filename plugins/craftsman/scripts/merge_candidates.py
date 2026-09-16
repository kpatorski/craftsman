#!/usr/bin/env python3
"""Find every directive/protocol that lives in its own file but is referenced by exactly one parent — the
deterministic scan behind `/craftsman:merge` (see `MANAGEMENT.md`, "The `merge` candidate check"). Read-only:
reports candidates, never folds anything in itself — that decision, and the actual inlining, stays with the
developer and the agent driving `merge`.

Usage:
    merge_candidates.py <content-root> [--verbose]

Counts references via `composes`, `steps`, and `uses` only — never `requires` (a bundle required by several
others is not a merge candidate; `requires` connects bundles to each other, not an entry to its parent) and never
a bare prose mention (only frontmatter-declared references count — a prose mention is not a structural ownership
claim, per `core.md`'s own frontmatter-is-for-lookup / body-is-for-the-actual-reference split).

Prints three sections:
- Merge candidates: referenced by exactly one parent — the actual purpose of this script.
- Referenced by nobody: zero parents. Not a merge candidate (nothing to fold it into) — a different kind of
  problem, flagged separately per MANAGEMENT.md's own note. Expect this list to be long and mostly uninteresting:
  every entry-point protocol and every directive loaded by `applies-when` matching rather than a `steps`/`uses`
  reference lands here legitimately.
- Shared (2+ parents), only with --verbose: correctly staying standalone, not printed by default.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _frontmatter import parse_frontmatter, split_frontmatter  # noqa: E402

REF_FIELDS = ("composes", "steps", "uses")


def find_content_files(root):
    files = []
    for name in ("directive.md", "protocol.md", "bundle.md"):
        files.extend(p for p in pathlib.Path(root).rglob(name) if ".git" not in p.parts)
    return files


def main():
    if len(sys.argv) < 2:
        raise SystemExit(f"Usage: {sys.argv[0]} <content-root> [--verbose]")
    root = sys.argv[1]
    verbose = "--verbose" in sys.argv[2:]

    all_ids = set()
    parents_of = {}  # id -> list of parent ids referencing it

    for p in find_content_files(root):
        fm_text, _body = split_frontmatter(p.read_text())
        if fm_text is None:
            continue
        try:
            fm = parse_frontmatter(fm_text) or {}
        except ValueError:
            continue  # validate_content.py's job to report a syntax error; this scan just skips it
        my_id = fm.get("id")
        if not my_id:
            continue
        all_ids.add(my_id)
        for field in REF_FIELDS:
            for ref in fm.get(field) or []:
                parents_of.setdefault(ref, []).append(my_id)

    candidates = sorted((rid, parents[0]) for rid, parents in parents_of.items() if len(parents) == 1)
    orphans = sorted(rid for rid in all_ids if rid not in parents_of)
    shared = sorted((rid, parents) for rid, parents in parents_of.items() if len(parents) > 1)

    print(f"Merge candidates (referenced by exactly one parent) -- {len(candidates)}:\n")
    for rid, parent in candidates:
        print(f"  {rid}  ->  {parent}")

    print(f"\nReferenced by nobody (not a merge candidate -- nothing to fold it into) -- {len(orphans)}:\n")
    for rid in orphans:
        print(f"  {rid}")

    if verbose:
        print(f"\nShared, correctly standalone (2+ parents) -- {len(shared)}:\n")
        for rid, parents in shared:
            print(f"  {rid}  <-  {', '.join(parents)}")


if __name__ == "__main__":
    main()
