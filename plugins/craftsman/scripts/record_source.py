#!/usr/bin/env python3
"""The `Sources` table of each index -- where installed content came from, and at which version -- see MANAGEMENT.md,
"Checking a known source for updates". `install` reads and writes it through here, never by hand.

    record_source.py record <index file> <name> <location> <kind> <version>
    record_source.py find <content root> <location>

`record` adds the source as a row, or -- when a row has its location -- gives that row the new name, kind and version.
It pads the table again, so every row lines up, leaves the rest of the file as it was, and prints `added`, `updated`
or `unchanged`. An index with no `## Sources` table is refused.

`find` prints, as JSON, every index whose table records the location -- `[{"index", "name", "kind", "version"}]` --
empty when the source is new. Locations compare without a trailing `/` or `.git`.
"""
import json
import pathlib
import sys

HEADING = "## Sources"
COLUMNS = ("Name", "Location", "Kind", "Version")
INDEXES = ("directives", "protocols", "bundles")


def same_place(a, b):
    def bare(location):
        location = location.strip().rstrip("/")
        return location[:-4] if location.endswith(".git") else location
    return bare(a) == bare(b)


def table(lines):
    """(first line, line after the last) of the Sources table, or None."""
    if HEADING not in lines:
        return None
    start = next((n for n in range(lines.index(HEADING), len(lines)) if lines[n].startswith("|")), None)
    if start is None:
        return None
    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    return start, end


def cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def rows_of(lines):
    found = table(lines)
    if not found:
        return None
    start, end = found
    return [dict(zip(COLUMNS, cells(line))) for line in lines[start + 2:end]]


def render(rows):
    widths = [max(len(column), *(len(row[column]) for row in rows)) for column in COLUMNS]
    line = lambda values: "| " + " | ".join(v.ljust(w) for v, w in zip(values, widths)) + " |"  # noqa: E731
    return [line(COLUMNS), "|" + "|".join("-" * (w + 2) for w in widths) + "|"] + \
        [line([row[column] for column in COLUMNS]) for row in rows]


def record(index, name, location, kind, version):
    index = pathlib.Path(index)
    lines = index.read_text().split("\n")
    rows = rows_of(lines)
    if rows is None:
        raise ValueError(f"{index} has no {HEADING} table")
    wanted = {"Name": name, "Location": location, "Kind": kind, "Version": version}
    known = next((row for row in rows if same_place(row.get("Location", ""), location)), None)
    if known == wanted:
        return "unchanged"
    if known:
        known.update(wanted)
    else:
        rows.append(wanted)
    start, end = table(lines)
    lines[start:end] = render(rows)
    index.write_text("\n".join(lines))
    return "updated" if known else "added"


def find(content, location):
    found = []
    for kind in INDEXES:
        path = pathlib.Path(content) / kind / "index.md"
        rows = rows_of(path.read_text().split("\n")) if path.is_file() else None
        for row in rows or []:
            if same_place(row.get("Location", ""), location):
                found.append({"index": kind, "name": row.get("Name"), "kind": row.get("Kind"),
                              "version": row.get("Version")})
    return found


def main(argv):
    if argv[:1] == ["record"] and len(argv) == 6:
        try:
            print(record(*argv[1:]))
        except (OSError, ValueError) as refused:
            sys.exit(f"record_source: {refused}")
    elif argv[:1] == ["find"] and len(argv) == 3:
        print(json.dumps(find(argv[1], argv[2])))
    else:
        sys.exit(__doc__.split("\n\n")[1])


if __name__ == "__main__":
    main(sys.argv[1:])
