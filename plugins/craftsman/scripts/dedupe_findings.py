#!/usr/bin/env python3
"""The mechanical part of making one finding of each problem across use cases -- see REVIEW.md, "Findings", and the
code-review bundle's `deduplicate-findings`, which decides what is one problem.

    dedupe_findings.py <review dir> candidates
    dedupe_findings.py <review dir> join '[["<finding id>", ...], ...]'

`candidates` prints the findings that may be one problem: of the same directive and the same kind, in different use
cases, neither deleted nor merged -- `[{"directive", "kind", "findings": [{"id", "use-case", "title", "comment",
"locations", "developer"}]}]`, in the order of the walk (the use cases' order, the untied files last). `developer`
says the developer wrote, edited, marked or sent it.

`join` takes the groups the agent judged to be one problem each and joins them: the finding the others go into is the
developer's, if one is, else the earliest in the walk; its locations come first, the others' after them in walk order;
every other copy is `merged` into it. A group with two findings of the developer is left apart -- a text the developer
wrote is not replaced by another -- and reported as `kept-apart`. A group that is not one of the candidates' (another
directive or kind, a finding gone or unknown, one finding alone, a finding in two groups) refuses the whole join,
before anything changes. It prints `{"joined": [{"into", "merged"}], "kept-apart": [[ids]]}`.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import review_state  # noqa: E402
from review_state import Refused  # noqa: E402

LIVE = ("proposed", "to-send", "maybe-resolved")


def walk(state):
    """Each finding's place in the walk: (use case index, use case id), by its first location."""
    use_cases = (state.get("structure") or {}).get("use-cases", [])

    def place(finding):
        path = (finding.get("locations") or [{}])[0].get("path")
        for index, use_case in enumerate(use_cases):
            if path in use_case.get("files", []):
                return index, use_case["id"]
        return len(use_cases), review_state.UNTIED

    return place


def developers(finding):
    return finding.get("by") == "developer" or bool(finding.get("edited")) or finding["status"] == "to-send" or \
        bool(finding.get("sent"))


def candidates(state):
    place = walk(state)
    live = [f for f in state["findings"] if f["status"] in LIVE and f.get("directive")]
    order = {f["id"]: n for n, f in enumerate(state["findings"])}
    groups = {}
    for finding in live:
        groups.setdefault((finding["directive"], finding.get("kind")), []).append(finding)
    out = []
    for (directive, kind), found in groups.items():
        if len({place(f)[1] for f in found}) < 2:
            continue
        found.sort(key=lambda f: (place(f)[0], order[f["id"]]))
        out.append({"directive": directive, "kind": kind, "findings": [
            {"id": f["id"], "use-case": place(f)[1], "title": f["title"], "comment": f["comment"],
             "locations": f["locations"], "developer": developers(f)} for f in found]})
    out.sort(key=lambda g: min(place(f)[0] for f in state["findings"] if f["id"] == g["findings"][0]["id"]))
    return out


def join(review, groups):
    review = pathlib.Path(review)
    state = review_state.read(review)
    by_id = {f["id"]: f for f in state["findings"]}
    place = walk(state)
    order = {f["id"]: n for n, f in enumerate(state["findings"])}
    seen, plans, kept_apart = set(), [], []
    for group in groups:
        if not isinstance(group, list) or len(group) < 2:
            raise Refused(f"a join needs two findings or more: {group}")
        for finding_id in group:
            if finding_id not in by_id or by_id[finding_id]["status"] not in LIVE:
                raise Refused(f"{finding_id} is no finding to join")
            if finding_id in seen:
                raise Refused(f"{finding_id} is in two groups twice over")
            seen.add(finding_id)
        found = sorted((by_id[i] for i in group), key=lambda f: (place(f)[0], order[f["id"]]))
        if len({f.get("directive") for f in found}) > 1:
            raise Refused(f"{', '.join(group)} name another directive each")
        if len({f.get("kind") for f in found}) > 1:
            raise Refused(f"{', '.join(group)} are of another kind each")
        mine = [f for f in found if developers(f)]
        if len(mine) > 1:
            kept_apart.append([f["id"] for f in found])
            continue
        into = mine[0] if mine else found[0]
        plans.append((into, [f for f in found if f is not into]))
    joined = []
    for into, copies in plans:
        if not into.get("sent"):
            locations = list(into["locations"])
            for copy in copies:
                locations += [loc for loc in copy["locations"] if loc not in locations]
            review_state.change(review, "update-finding", {"locations": locations}, item_id=into["id"])
        for copy in copies:
            review_state.change(review, "set-status", {"status": "merged", "merged-into": into["id"]},
                                item_id=copy["id"])
        joined.append({"into": into["id"], "merged": [copy["id"] for copy in copies]})
    return {"joined": joined, "kept-apart": kept_apart}


def main(argv):
    if len(argv) < 2 or argv[1] not in ("candidates", "join") or (argv[1] == "join") != (len(argv) == 3):
        sys.exit(__doc__.split("\n\n")[1])
    try:
        if argv[1] == "candidates":
            print(json.dumps(candidates(review_state.read(pathlib.Path(argv[0]))), indent=2))
        else:
            print(json.dumps(join(argv[0], json.loads(argv[2]))))
    except (Refused, ValueError) as refused:
        sys.exit(f"dedupe_findings: {refused}")


if __name__ == "__main__":
    main(sys.argv[1:])
