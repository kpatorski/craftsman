#!/usr/bin/env python3
"""Remove a directive/protocol/bundle by id — the deterministic backbone for `/craftsman:uninstall` (see
`MANAGEMENT.md`'s id-resolution rules and the `uninstall` skill). Two-phase, like every other mutating command in
this family: a dry run reports what would happen and who references the id, and only `--yes` actually deletes
anything — the reference check is exactly the kind of thing that must reach the developer before a file
disappears, not something this script decides alone.

Usage:
    uninstall_id.py <content-root> <id>          -- dry run: report only, no changes
    uninstall_id.py <content-root> <id> --yes     -- actually remove

Finds the id's own directory (and, for a bundle, everything under it — this is a bundle's members too, not just
the wrapper) and the table row that names it (its own top-level index if it is fundament, its bundle's own
`bundle.md` if it lives inside one, `bundles/index.md` if the id is itself a bundle). Reports every other entry
that references it via `composes` / `steps` / `uses` / `requires` (the same scan `merge_candidates.py` runs, plus
`requires` — a bundle another installed bundle depends on is exactly the case that check does not need to cover
but this one does) before removing anything, since uninstalling a referenced id leaves a dangling reference for
its referrer to fix.
"""
import shutil
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _frontmatter import parse_frontmatter, split_frontmatter  # noqa: E402
import toggle_table_row as ttr  # noqa: E402

REF_FIELDS = ("composes", "steps", "uses", "requires")


def find_content_files(root):
    files = []
    for name in ("directive.md", "protocol.md", "bundle.md"):
        files.extend(p for p in pathlib.Path(root).rglob(name) if ".git" not in p.parts)
    return files


def locate(root, target_id):
    """Returns (path, kind, fm) for the file whose id is target_id, or None."""
    for p in find_content_files(root):
        fm_text, _body = split_frontmatter(p.read_text())
        if fm_text is None:
            continue
        try:
            fm = parse_frontmatter(fm_text) or {}
        except ValueError:
            continue
        if fm.get("id") == target_id:
            kind = {"directive.md": "directive", "protocol.md": "protocol", "bundle.md": "bundle"}[p.name]
            return p, kind, fm
    return None


def find_referrers(root, target_id):
    referrers = []
    for p in find_content_files(root):
        fm_text, _body = split_frontmatter(p.read_text())
        if fm_text is None:
            continue
        try:
            fm = parse_frontmatter(fm_text) or {}
        except ValueError:
            continue
        my_id = fm.get("id")
        for field in REF_FIELDS:
            if target_id in (fm.get(field) or []):
                referrers.append((my_id, field))
    return referrers


def index_file_for(root, path, kind):
    """Which file holds this entry's table row."""
    root = pathlib.Path(root)
    if kind == "bundle":
        return root / "bundles" / "index.md"
    # Inside a bundle if the path has a `bundles/<id>/` ancestor before the entry's own dir.
    parts = path.relative_to(root).parts
    if parts[0] == "bundles":
        bundle_id = parts[1]
        return root / "bundles" / bundle_id / "bundle.md"
    folder = "directives" if kind == "directive" else "protocols"
    return root / folder / "index.md"


def main():
    if len(sys.argv) < 3:
        raise SystemExit(f"Usage: {sys.argv[0]} <content-root> <id> [--yes]")
    root, target_id = sys.argv[1], sys.argv[2]
    execute = "--yes" in sys.argv[3:]

    found = locate(root, target_id)
    if found is None:
        raise SystemExit(f"`{target_id}` is not the id of any directive/protocol/bundle under {root}.")
    path, kind, _fm = found
    entry_dir = path.parent
    index_file = index_file_for(root, path, kind)

    referrers = find_referrers(root, target_id)

    print(f"`{target_id}` is a {kind} at {entry_dir}")
    print(f"Its row lives in: {index_file}")
    if kind == "bundle":
        member_count = sum(1 for _ in entry_dir.rglob("directive.md")) + sum(1 for _ in entry_dir.rglob("protocol.md"))
        print(f"Removing it deletes {member_count} member file(s) under {entry_dir} too, not just the wrapper.")

    if referrers:
        print(f"\nReferenced by {len(referrers)} other entr{'y' if len(referrers) == 1 else 'ies'}:")
        for referrer_id, field in referrers:
            print(f"  {referrer_id} (via `{field}`)")
        print("\nRemoving anyway leaves these as dangling references -- confirm with the developer before --yes.")
    else:
        print("\nNot referenced by anything else.")

    if not execute:
        print("\nDry run only -- no changes made. Re-run with --yes to actually remove.")
        return

    with open(index_file) as f:
        lines = [l.rstrip("\n") for l in f]
    ttr.do_remove(str(index_file), lines, target_id)

    shutil.rmtree(entry_dir)
    print(f"\nRemoved {entry_dir} and its row in {index_file}.")


if __name__ == "__main__":
    main()
