#!/usr/bin/env python3
"""Rename a directive/protocol/bundle id everywhere it is referenced — the deterministic backbone for
`/craftsman:rename` (see `MANAGEMENT.md`, "Renaming"). Doing this by hand means finding every `composes` /
`steps` / `uses` / `requires` / `overrides` reference, every prose link, every index/bundle table row, and the
entry's own directory and frontmatter `id:` -- exactly the kind of multi-file, easy-to-miss-one-spot change that
caused a real, live bug this project shipped with (see `validate_content.py`'s own docstring). This script finds
every reference by a single, whole-token, boundary-aware text substitution instead of re-deriving the reference
list from prose each time.

Usage:
    rename_id.py <content-root> <old-id> <new-id>

Refuses (exit 1, no files touched) if:
- <old-id> is not found as the `id:` of any directive.md/protocol.md/bundle.md under <content-root>.
- <new-id> already exists anywhere under <content-root> (same uniqueness rule `install` enforces).

Otherwise: renames the entry's own directory (old-id -> new-id), then replaces every whole-token occurrence of
<old-id> with <new-id> across every .md file under <content-root> -- frontmatter fields (`id`, `composes`, `steps`,
`uses`, `requires`, `overrides` keys), link labels, link paths, bare backtick mentions, and table cells alike, all
of which are just text containing the token. "Whole-token" means not immediately preceded or followed by a letter,
digit, or hyphen -- so renaming `event-storming` to `event-storming-loop` does not also touch an unrelated mention
of `event-storming-loop` that already existed, and renaming `tdd` does not touch `tdd-loop`.

Prints every file changed and how many replacements were made in each -- review the diff before committing, same
as any other mutation (see `MANAGEMENT.md`, "Versioning"). Read-only until the checks above pass; then it writes.

**Known limitation, confirmed live by testing this script against a real id that is also an ordinary English
word** (`naming`): a whole-token match cannot tell "the `naming` directive" (a real reference) from "naming
decisions" (plain prose that happens to contain the same word) -- both are the token `naming` with word boundaries
on both sides. Renaming a plain-English id therefore needs the diff read line by line, not just trusted by
replacement count, exactly like reviewing any other diff before commit. This is a real, narrower risk than the
problem this script replaces (a missed reference), not an equivalent one -- a stray false-positive replacement is
visible and reviewable in the diff; a silently missed reference is not.

**Also does not re-pad any markdown table it touches** -- a table row whose id column changed length needs its
column widths recomputed by hand, or by re-running the row through `toggle_table_row.py` (disable then re-enable
it) after this script finishes, before committing.
"""
import re
import sys
import pathlib

ID_LINE_RE = re.compile(r"^id:\s*(\S+)\s*$", re.MULTILINE)


def find_content_files(root):
    files = []
    for name in ("directive.md", "protocol.md", "bundle.md"):
        files.extend(p for p in pathlib.Path(root).rglob(name) if ".git" not in p.parts)
    return files


def find_all_md_files(root):
    """Every `.md` file, not just the three leaf kinds -- the substitution pass must also reach
    `directives/index.md`, `protocols/index.md`, `bundles/index.md`, `README.md`, and any other file that
    mentions the id in a table row or in prose. Only the leaf kinds carry a frontmatter `id:` to discover from,
    but any file can *reference* one."""
    return [p for p in pathlib.Path(root).rglob("*.md") if ".git" not in p.parts]


def id_of(path):
    m = ID_LINE_RE.search(path.read_text())
    return m.group(1) if m else None


def token_re(the_id):
    """Whole-token match: not preceded or followed by a letter, digit, or hyphen. Deliberately not `\\b` --
    hyphen is not a `\\w` character, so `\\bevent-storming\\b` would still match inside `event-storming-loop`."""
    return re.compile(r"(?<![A-Za-z0-9-])" + re.escape(the_id) + r"(?![A-Za-z0-9-])")


def main():
    if len(sys.argv) != 4:
        raise SystemExit(f"Usage: {sys.argv[0]} <content-root> <old-id> <new-id>")
    root, old_id, new_id = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]

    files = find_content_files(root)
    ids = {}
    for p in files:
        fid = id_of(p)
        if fid:
            ids.setdefault(fid, []).append(p)

    if old_id not in ids:
        raise SystemExit(f"`{old_id}` is not the id of any directive/protocol/bundle under {root}.")
    if len(ids[old_id]) > 1:
        raise SystemExit(f"`{old_id}` is not unique -- found in {ids[old_id]}. Fix that first, not with a rename.")
    if new_id in ids:
        raise SystemExit(f"`{new_id}` already exists at {ids[new_id][0]} -- refusing to create a collision.")

    old_path = ids[old_id][0]
    old_dir = old_path.parent
    new_dir = old_dir.parent / new_id
    if new_dir.exists():
        raise SystemExit(f"{new_dir} already exists on disk -- refusing to overwrite.")

    old_dir.rename(new_dir)
    print(f"Renamed directory: {old_dir} -> {new_dir}")

    pattern = token_re(old_id)
    changed = 0
    for p in find_all_md_files(root):
        text = p.read_text()
        new_text, n = pattern.subn(new_id, text)
        if n:
            p.write_text(new_text)
            changed += 1
            print(f"  {p}: {n} replacement(s)")

    print(f"\n`{old_id}` -> `{new_id}`: directory renamed, {changed} file(s) updated with text replacements.")
    print("Review the diff before committing -- this script does not commit.")


if __name__ == "__main__":
    main()
