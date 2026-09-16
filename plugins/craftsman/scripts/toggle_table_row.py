#!/usr/bin/env python3
"""Mutate a file's **Enabled** / **Disabled** markdown tables — the only supported way to touch these tables (see
MANAGEMENT.md, "Enable / disable"). Hand-editing them with a string-match tool is exactly what this replaces:
every row move changes column widths, so a stale in-context copy of the file makes exact-match edits fail, and
hand-recomputing padding for a whole table is slow and error-prone. This script re-reads the file fresh every
time, so it is immune to that class of problem by construction.

Usage:
    toggle_table_row.py <file> <id> enable|disable
    toggle_table_row.py <file> <id> remove
    toggle_table_row.py <file> add enabled|disabled "<cell2>|<cell3>|...|<cellN>" [--after-heading "<text>"]

`enable`/`disable` moves an existing row between tables. `remove` deletes an existing row outright (for
`uninstall` — see `uninstall_id.py`). `add` inserts a brand-new row (for `install` — see MANAGEMENT.md,
"Installing a bundle" / step 7 of the `install` skill) with an auto-numbered "No" column; supply every other cell,
pipe-separated, in the same order as the table's existing header. `--after-heading` picks which Enabled/Disabled
pair to target when a file has more than one (a directive/protocol index has one pair per `### <category>`
section, a `bundle.md` has one under `## Protocols` and one under `## Directives`); omit it when the file has
exactly one pair (`bundles/index.md`).

For every mode: finds the relevant **Enabled**/**Disabled** table pair, renumbers the "No" column for both tables
in that pair, and rewrites both with padding recomputed per this project's markdown-tables rule (each column
padded to 1 + the longest cell + 1). A table left with zero rows is rendered as the established one-line prose
("Empty — nothing has been switched off yet." / "Empty — nothing in this category is enabled yet."), matching
every existing empty section in this content tree — not a bare header-only table. The reverse also works: adding
or moving a row into a currently-empty (prose) section replaces the prose line with a real table.

Every other line in the file — including unrelated table pairs — is left untouched, to keep the diff minimal.

Exits non-zero with a clear message if: the id is not found anywhere (`enable`/`disable`/`remove`); the id is
already in the requested table (`enable`/`disable` — this one prints a note and exits 0, a no-op not an error);
the id already exists somewhere in the file (`add`); or a `--after-heading` is required (more than one pair in the
file) but not given, or given and not found.
"""
import re
import sys

ROW_RE = re.compile(r"^\|(.*)\|\s*$")
ID_CELL_RE = re.compile(r"^\s*\[([a-z0-9-]+)\]\(")
BARE_ID_RE = re.compile(r"^[a-z0-9-]+$")

EMPTY_TEXT = {
    "Enabled": "Empty — nothing in this category is enabled yet.",
    "Disabled": "Empty — nothing has been switched off yet.",
}


def split_row(line):
    """A pipe-table row -> list of cell strings, stripped. Assumes no literal unescaped `|` inside a cell."""
    inner = ROW_RE.match(line).group(1)
    return [c.strip() for c in inner.split("|")]


def is_delimiter_row(cells):
    return all(re.fullmatch(r":?-+:?", c) for c in cells)


def find_table_pairs(lines):
    """Returns a list of (enabled_marker_idx, disabled_marker_idx) for every **Enabled**/**Disabled** pair,
    in document order, pairing the i-th Enabled with the i-th Disabled."""
    enabled_idxs = [i for i, l in enumerate(lines) if l.strip() == "**Enabled**"]
    disabled_idxs = [i for i, l in enumerate(lines) if l.strip() == "**Disabled**"]
    if len(enabled_idxs) != len(disabled_idxs):
        raise SystemExit(
            f"Mismatched **Enabled**/**Disabled** marker count ({len(enabled_idxs)} vs {len(disabled_idxs)}) "
            "-- file is not in the expected shape, refusing to guess."
        )
    return list(zip(enabled_idxs, disabled_idxs))


def nearest_heading_above(lines, idx):
    """The nearest `#`-heading line at or before `idx` -- used to let `add` disambiguate which pair a
    `--after-heading` argument means, without requiring the caller to know line numbers."""
    for i in range(idx, -1, -1):
        if lines[i].lstrip().startswith("#"):
            return lines[i].strip()
    return None


def parse_section(lines, marker_idx):
    """A section's content starts two lines after its **Enabled**/**Disabled** marker (blank line, then either a
    table's header row, or a single prose line for an empty section). Returns (header_or_None, rows, start_idx,
    end_idx_exclusive) -- header is None when the section is currently prose (empty); rows is always a list
    (empty when prose). start:end is the exact line range to replace when rewriting this section."""
    content_idx = marker_idx + 2
    if content_idx < len(lines) and lines[content_idx].startswith("|"):
        header = split_row(lines[content_idx])
        delim_idx = content_idx + 1
        if not (lines[delim_idx].startswith("|") and is_delimiter_row(split_row(lines[delim_idx]))):
            raise SystemExit(f"Expected a delimiter row at line {delim_idx + 1}.")
        rows = []
        i = delim_idx + 1
        while i < len(lines) and lines[i].startswith("|"):
            rows.append(split_row(lines[i]))
            i += 1
        return header, rows, content_idx, i
    # Prose (empty section) -- exactly one line, no table.
    return None, [], content_idx, content_idx + 1


def render_section(kind, header, rows):
    """kind is 'Enabled' or 'Disabled' -- only used to pick the right empty-state prose."""
    if not rows:
        return [EMPTY_TEXT[kind]]
    all_rows = [header] + rows
    ncols = len(header)
    widths = [max(len(r[c]) for r in all_rows) for c in range(ncols)]

    def fmt(r):
        return "| " + " | ".join(r[c].ljust(widths[c]) for c in range(ncols)) + " |"

    out = [fmt(header), "|" + "|".join("-" * (widths[c] + 2) for c in range(ncols)) + "|"]
    out.extend(fmt(r) for r in rows)
    return out


def renumber(rows, start):
    for i, r in enumerate(rows):
        r[0] = str(start + i)
    return rows


def row_id(row):
    """The id column (column 1) is a markdown link `[id](path)` for a directive/protocol row, or a bare id string
    for a bundle row in bundles/index.md (that file links via its separate Path column instead)."""
    cell = row[1]
    m = ID_CELL_RE.match(cell)
    if m:
        return m.group(1)
    if BARE_ID_RE.fullmatch(cell.strip()):
        return cell.strip()
    return None


def write_back(path, lines):
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def do_enable_disable(path, lines, target_id, direction):
    want_table = "Enabled" if direction == "enable" else "Disabled"

    for enabled_marker, disabled_marker in find_table_pairs(lines):
        e_header, e_rows, e_start, e_end = parse_section(lines, enabled_marker)
        d_header, d_rows, d_start, d_end = parse_section(lines, disabled_marker)

        e_match = next((r for r in e_rows if row_id(r) == target_id), None)
        d_match = next((r for r in d_rows if row_id(r) == target_id), None)
        if e_match is None and d_match is None:
            continue

        current_table = "Enabled" if e_match is not None else "Disabled"
        if current_table == want_table:
            print(f"{target_id} is already {direction}d ({want_table}) in {path} -- no change.")
            return

        header = e_header if e_header is not None else d_header
        first_no = int((e_rows[0] if e_rows else d_rows[0])[0])

        if want_table == "Enabled":
            row = d_match
            d_rows.remove(row)
            e_rows.append(row)
        else:
            row = e_match
            e_rows.remove(row)
            d_rows.append(row)

        renumber(e_rows, first_no)
        renumber(d_rows, first_no + len(e_rows))

        # Disabled comes after Enabled in every observed layout -- replace the later span first so the earlier
        # span's line numbers stay valid.
        lines[d_start:d_end] = render_section("Disabled", header, d_rows)
        lines[e_start:e_end] = render_section("Enabled", header, e_rows)

        write_back(path, lines)
        print(f"Moved {target_id}: {current_table} -> {want_table}, in {path}.")
        return

    raise SystemExit(f"{target_id} not found in any Enabled/Disabled table pair in {path}.")


def do_remove(path, lines, target_id):
    for enabled_marker, disabled_marker in find_table_pairs(lines):
        e_header, e_rows, e_start, e_end = parse_section(lines, enabled_marker)
        d_header, d_rows, d_start, d_end = parse_section(lines, disabled_marker)

        e_match = next((r for r in e_rows if row_id(r) == target_id), None)
        d_match = next((r for r in d_rows if row_id(r) == target_id), None)
        if e_match is None and d_match is None:
            continue

        header = e_header if e_header is not None else d_header
        first_no = int((e_rows[0] if e_rows else d_rows[0])[0])
        source = "Enabled" if e_match is not None else "Disabled"
        (e_rows if e_match is not None else d_rows).remove(e_match or d_match)

        renumber(e_rows, first_no)
        renumber(d_rows, first_no + len(e_rows))

        lines[d_start:d_end] = render_section("Disabled", header, d_rows)
        lines[e_start:e_end] = render_section("Enabled", header, e_rows)

        write_back(path, lines)
        print(f"Removed {target_id} from {source} in {path}.")
        return

    raise SystemExit(f"{target_id} not found in any Enabled/Disabled table pair in {path}.")


def do_add(path, lines, want_table, new_cells, after_heading):
    pairs = find_table_pairs(lines)
    if not pairs:
        raise SystemExit(f"No Enabled/Disabled table pair found in {path}.")

    if after_heading:
        matches = [p for p in pairs if nearest_heading_above(lines, p[0]) == after_heading]
        if not matches:
            raise SystemExit(f"No table pair found under heading {after_heading!r} in {path}.")
        if len(matches) > 1:
            raise SystemExit(f"More than one table pair under heading {after_heading!r} in {path} -- ambiguous.")
        enabled_marker, disabled_marker = matches[0]
    elif len(pairs) == 1:
        enabled_marker, disabled_marker = pairs[0]
    else:
        headings = [nearest_heading_above(lines, p[0]) for p in pairs]
        raise SystemExit(
            f"{path} has {len(pairs)} Enabled/Disabled pairs -- pass --after-heading to pick one. "
            f"Found: {headings}"
        )

    e_header, e_rows, e_start, e_end = parse_section(lines, enabled_marker)
    d_header, d_rows, d_start, d_end = parse_section(lines, disabled_marker)

    existing = next((r for r in e_rows + d_rows if row_id(r) == new_cells[0]), None)
    if existing is not None:
        raise SystemExit(f"{new_cells[0]} already exists in this table pair in {path} -- refusing to duplicate.")

    header = e_header if e_header is not None else d_header
    if header is None:
        raise SystemExit(
            f"Both tables in this pair are empty in {path} -- no header to infer column shape from. "
            "Add the header row by hand for this first-ever entry, then re-run."
        )
    if len(new_cells) != len(header) - 1:
        raise SystemExit(f"Expected {len(header) - 1} cells (header is {header[1:]}), got {len(new_cells)}.")

    first_no = int((e_rows[0] if e_rows else d_rows[0])[0]) if (e_rows or d_rows) else 1
    new_row = ["0"] + new_cells  # "No" placeholder, fixed by renumber() below

    if want_table == "Enabled":
        e_rows.append(new_row)
    else:
        d_rows.append(new_row)

    renumber(e_rows, first_no)
    renumber(d_rows, first_no + len(e_rows))

    lines[d_start:d_end] = render_section("Disabled", header, d_rows)
    lines[e_start:e_end] = render_section("Enabled", header, e_rows)

    write_back(path, lines)
    print(f"Added {new_cells[0]} to {want_table} in {path}.")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--help":
        print(__doc__)
        return

    if len(sys.argv) >= 4 and sys.argv[2] == "add" and sys.argv[3] in ("enabled", "disabled"):
        path, _add, want, cells_arg = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
        after_heading = None
        if "--after-heading" in sys.argv:
            i = sys.argv.index("--after-heading")
            after_heading = sys.argv[i + 1]
        with open(path) as f:
            lines = [l.rstrip("\n") for l in f]
        do_add(path, lines, "Enabled" if want == "enabled" else "Disabled", cells_arg.split("|"), after_heading)
        return

    if len(sys.argv) == 4 and sys.argv[3] in ("enable", "disable"):
        path, target_id, direction = sys.argv[1], sys.argv[2], sys.argv[3]
        with open(path) as f:
            lines = [l.rstrip("\n") for l in f]
        do_enable_disable(path, lines, target_id, direction)
        return

    if len(sys.argv) == 4 and sys.argv[3] == "remove":
        path, target_id, _remove = sys.argv[1], sys.argv[2], sys.argv[3]
        with open(path) as f:
            lines = [l.rstrip("\n") for l in f]
        do_remove(path, lines, target_id)
        return

    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
