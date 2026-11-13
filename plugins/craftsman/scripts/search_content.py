#!/usr/bin/env python3
"""The lookup behind `/craftsman:search` -- see MANAGEMENT.md, "Duplicate detection": every installed directive,
protocol and bundle whose id, title or description holds a word of the phrase.

    search_content.py <content root> <phrase>

A word of three letters or more matches anywhere in a field, whatever its case. A match on the id counts most, then
the title, then the description; the best come first, ties in the order of the indexes. It prints a JSON list of
`{"kind", "id", "title", "description", "enabled", "bundle", "path", "matched"}`: `enabled` is whether a review or a
run uses it -- a member of a disabled bundle is not used, whatever its own row says -- and `matched` names the fields
the words were found in. Whether a match is the thing asked about is the reader's call. Exits 1 when nothing is
installed.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render_dashboard import collect_entries  # noqa: E402

WEIGHT = {"id": 3, "title": 2, "description": 1}


def search(content, phrase):
    words = [word.lower() for word in phrase.split() if len(word) >= 3]
    entries = collect_entries(pathlib.Path(content))
    bundles_on = {e["id"]: e["enabled"] for e in entries if e["kind"] == "bundle"}
    found = []
    for order, entry in enumerate(entries):
        matched = [field for field in WEIGHT if any(word in str(entry.get(field) or "").lower() for word in words)]
        if not matched:
            continue
        score = sum(WEIGHT[field] * sum(word in str(entry.get(field) or "").lower() for word in words)
                    for field in matched)
        enabled = entry["enabled"] and bundles_on.get(entry["bundle"], True)
        found.append((-score, order, {"kind": entry["kind"], "id": entry["id"], "title": entry["title"],
                                      "description": entry["description"], "enabled": enabled,
                                      "bundle": entry["bundle"], "path": str(entry["path"]) if entry["path"] else None,
                                      "matched": matched}))
    return [match for _, _, match in sorted(found, key=lambda item: item[:2])]


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__.split("\n\n")[1])
    content = pathlib.Path(argv[0]).expanduser()
    if not content.is_dir():
        sys.exit(f"search_content: nothing is installed at {content}")
    print(json.dumps(search(content, argv[1]), indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
