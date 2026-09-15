#!/usr/bin/env python3
"""Move one row between a file's **Enabled** / **Disabled** markdown tables — the only supported way to mutate
these tables (see MANAGEMENT.md, "Enable / disable"). Hand-editing them with a string-match tool is exactly what
this replaces: every row move changes column widths, so a stale in-context copy of the file makes exact-match
edits fail, and hand-recomputing padding for a whole table is slow and error-prone. This script re-reads the file
fresh every time, so it is immune to that class of problem by construction.

Usage:
    toggle_table_row.py <file> <id> <enable|disable>

Finds the **Enabled**/**Disabled** table pair that contains a row for <id> (searches every such pair in the file —
a directive/protocol index has one pair per category, a bundle.md has one pair under "## Protocols" and one under
"## Directives", bundles/index.md has exactly one), moves the row to the requested table if it is not already
there, renumbers the "No" column for both tables in that pair, and rewrites both tables with padding recomputed
per this project's markdown-tables rule (each column padded to 1 + the longest cell + 1). A table left with zero
rows is rendered as the established one-line prose ("Empty — nothing has been switched off yet." /
"Empty — nothing in this category is enabled yet."), matching every existing empty section in this content tree —
not a bare header-only table. The reverse also works: moving a row into a currently-empty (prose) section replaces
the prose line with a real table.

Every other line in the file — including unrelated table pairs — is left untouched, to keep the diff minimal.

Exits non-zero with a clear message if the id is not found anywhere, or if it is already in the requested table
(the latter prints a note and exits 0 — this is a no-op, not an error).
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


def main():
    if len(sys.argv) != 4 or sys.argv[3] not in ("enable", "disable"):
        raise SystemExit(f"Usage: {sys.argv[0]} <file> <id> <enable|disable>")
    path, target_id, direction = sys.argv[1], sys.argv[2], sys.argv[3]
    want_table = "Enabled" if direction == "enable" else "Disabled"

    with open(path) as f:
        lines = [l.rstrip("\n") for l in f]

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

        # A shared header, needed to build a fresh row-list on whichever side is currently prose (empty).
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

        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")

        print(f"Moved {target_id}: {current_table} -> {want_table}, in {path}.")
        return

    raise SystemExit(f"{target_id} not found in any Enabled/Disabled table pair in {path}.")


if __name__ == "__main__":
    main()
