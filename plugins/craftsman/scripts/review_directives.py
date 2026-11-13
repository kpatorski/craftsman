#!/usr/bin/env python3
"""The directives a review checks the code against -- see REVIEW.md, "Directives".

    review_directives.py <review dir> [--content <content root>]
    review_directives.py <review dir> --plan
    review_directives.py <review dir> --record-checks <use case> '<verdicts>' [--directive <id>]

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
import re
import sys

import review_state
from render_dashboard import collect_entries

REVIEW_BUNDLE = "code-review"
CONTENT = pathlib.Path.home() / ".claude" / "craftsman"
SCOPE = pathlib.Path("bundles") / REVIEW_BUNDLE / "directive-scope.md"
FILES = ("production", "tests", "all", "none")
REACH = ("file", "flow")
UNSCOPED = {"files": "all", "reach": "flow", "scoped": False}
GROUP = 6  # directives one reviewer checks
BATCH_LINES = 1500  # changed lines one reviewer of `file` directives reads, unless one file alone has more
TEST_FOLDERS = {"test", "tests", "__tests__"}
KIND = {"production": "production", "tests": "test", "all": "changed"}  # how a note names the files of a `files`
TEST_NAME = re.compile(r"(Tests?|Spec)\.\w+$|\.(test|spec)\.\w+$|^test_\w*\.py$")


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


def is_test(path):
    """Whether a changed file is a test: it lies in a test folder, or its name says it is one."""
    parts = pathlib.PurePosixPath(path).parts
    return any(part in TEST_FOLDERS for part in parts[:-1]) or bool(TEST_NAME.search(parts[-1]))


def kind_of(path):
    return "tests" if is_test(path) else "production"


def plan(content, review, state, defaults=None):
    """Which directive reviewers a review starts, worked out from the diff, the use cases and the scope table:

    - `reviewers` — `{"reach", "use-cases": [{"id", "files"}], "directives": [{"id", "path"}], "files"}`, one per
      reviewer, at most `GROUP` directives each. A `file` directive is checked once over every changed file of its
      kind, the files in batches of about `BATCH_LINES` changed lines, `use-cases` empty. A `flow` directive is checked
      per use case, on the files of its kind that use case is the first to have, the untied files last as the use case
      `untied`; one reviewer takes use cases in order up to about `BATCH_LINES` changed lines, a bigger one alone.
    - `not-applicable` — `{"use-case", "directive", "note"}`, the checks to record as they are: no file of the
      directive's kind in that use case for a reviewer to check.
    - `file-checks` — `{use case: [directive ids]}`, the `file` directives each use case records from its findings.

    A deleted file is not checked: there is no code of it left to judge."""
    import _reviews  # it imports this module
    kept = pathlib.Path(review) / "diff" / f"{state['head']}.diff"
    changed = [f for f in _reviews.changed_files(kept.read_text() if kept.is_file() else "")
               if f["change"] != "deleted"]
    size = {f["path"]: f["added"] + f["removed"] for f in changed}
    use_cases = [(u["id"], [path for path in size if path in u.get("files", [])])
                 for u in (state.get("structure") or {}).get("use-cases", [])]
    tied = {path for _, files in use_cases for path in files}
    untied = [path for path in size if path not in tied]
    use_cases += [(review_state.UNTIED, untied)] if untied else []
    checked = to_check(content, state, defaults)
    reviewers, not_applicable, file_checks = [], [], {}

    def fits(files_value, path):
        return files_value in ("all", kind_of(path))

    def groups(directives):
        return [[{"id": d["id"], "path": d["path"]} for d in directives[first:first + GROUP]]
                for first in range(0, len(directives), GROUP)]

    by_file = [d for d in checked if d["reach"] == "file"]
    for kind in ("production", "tests"):
        files = [path for path in size if kind_of(path) == kind]
        directives = [d for d in by_file if d["files"] in ("all", kind)]
        for group in groups(directives) if files else []:
            for batch in batches(files, size.get):
                reviewers.append({"reach": "file", "use-cases": [], "directives": group, "files": batch})

    seen, own = set(), {}
    for use_case, files in use_cases:
        own[use_case] = [path for path in files if path not in seen]
        seen |= set(own[use_case])
    by_flow = [d for d in checked if d["reach"] == "flow"]
    for files_value in ("production", "tests", "all"):
        directives = [d for d in by_flow if d["files"] == files_value]
        parts = [{"id": use_case, "files": [path for path in own[use_case] if fits(files_value, path)]}
                 for use_case, _ in use_cases]
        for group in groups(directives):
            for pack in batches([part for part in parts if part["files"]],
                                lambda part: sum(size[path] for path in part["files"])):
                reviewers.append({"reach": "flow", "use-cases": pack, "directives": group,
                                  "files": [path for part in pack for path in part["files"]]})
        for (use_case, files), part in zip(use_cases, parts):
            for d in directives if not part["files"] else []:
                note = (f"its {KIND[d['files']]} files are checked with the use case that has them first"
                        if any(fits(d["files"], path) for path in files)
                        else f"no {KIND[d['files']]} files in this use case")
                not_applicable.append({"use-case": use_case, "directive": d["id"], "note": note})
    for use_case, files in use_cases:
        for d in by_file:
            if any(fits(d["files"], path) for path in files):
                file_checks.setdefault(use_case, []).append(d["id"])
            else:
                not_applicable.append({"use-case": use_case, "directive": d["id"],
                                       "note": f"no {KIND[d['files']]} files in this use case"})
    order = {d["id"]: n for n, d in enumerate(checked)}
    not_applicable.sort(key=lambda c: ([u for u, _ in use_cases].index(c["use-case"]), order[c["directive"]]))
    return {"reviewers": reviewers, "not-applicable": not_applicable, "file-checks": file_checks}


VERDICTS = ("clean", "failed")


def record_checks(content, review, use_case, verdicts, defaults=None, directive=None):
    """Record what every directive found in one use case, in one `record-check`; the recorded checks. The agent gives
    only its reviewers' verdicts, `{directive: "clean" | "failed" | {"not-applicable": <reason>}}`, for the `flow`
    directives the plan checks in this use case (a `file` one only when its reviewer failed); the rest is worked out:

    - `findings` -- a finding not deleted names the directive and has a location in the use case's files;
    - a `file` directive of the plan's `file-checks` for the use case -- `clean` unless it has findings or failed;
    - the plan's `not-applicable` checks of the use case, as they are.

    A `flow` directive with no verdict and no finding is a gap, a verdict for a directive the use case does not check
    is a slip, and a `not-applicable` needs its reason: each refuses the whole record. With `directive`, only that
    directive's checks are worked out and recorded -- the developer switched it on after the use case was reviewed.
    Raises Refused."""
    state = review_state.read(pathlib.Path(review))
    planned = plan(content, review, state, defaults)
    use_cases = {u["id"]: u for u in (state.get("structure") or {}).get("use-cases", [])}
    if use_case not in use_cases and use_case != review_state.UNTIED:
        raise review_state.Refused(f"no use case {use_case!r}")
    files = set(use_cases[use_case].get("files", [])) if use_case in use_cases else \
        {path for r in planned["reviewers"] for u in r["use-cases"] if u["id"] == use_case for path in u["files"]}
    flow = [d["id"] for r in planned["reviewers"] if any(u["id"] == use_case for u in r["use-cases"])
            for d in r["directives"]]
    by_file = planned["file-checks"].get(use_case, [])
    planned_out = [c for c in planned["not-applicable"] if c["use-case"] == use_case]
    if directive:
        flow, by_file = [d for d in flow if d == directive], [d for d in by_file if d == directive]
        planned_out = [c for c in planned_out if c["directive"] == directive]
    found = {f["directive"] for f in state["findings"] if f["status"] != "deleted" and f.get("directive")
             and any(loc.get("path") in files for loc in f.get("locations", []))}
    stray = sorted(set(verdicts) - set(flow) - set(by_file))
    if stray:
        raise review_state.Refused(f"{use_case} does not check {', '.join(stray)}")
    checks = []
    for name in flow:
        verdict = verdicts.get(name)
        if name in found:
            checks.append({"result": "findings"})
        elif verdict in VERDICTS:
            checks.append({"result": verdict})
        elif isinstance(verdict, dict) and set(verdict) == {"not-applicable"}:
            if not str(verdict["not-applicable"] or "").strip():
                raise review_state.Refused(f"not-applicable for {name} needs its reason")
            checks.append({"result": "not-applicable", "note": verdict["not-applicable"]})
        elif verdict is None:
            raise review_state.Refused(f"no verdict for {name} in {use_case}: a gap is never clean")
        else:
            raise review_state.Refused(f"{verdict!r} for {name} is not a verdict: clean, failed, "
                                       f'or {{"not-applicable": <reason>}}')
        checks[-1].update({"use-case": use_case, "directive": name})
    for name in by_file:
        if name in flow:
            continue
        result = "findings" if name in found else "failed" if verdicts.get(name) == "failed" else "clean"
        checks.append({"use-case": use_case, "directive": name, "result": result})
    checks += [dict(c, result="not-applicable") for c in planned_out]
    review_state.change(pathlib.Path(review), "record-check", checks)
    return checks


def batches(items, lines):
    """The items in order, cut where the next one would take a batch over `BATCH_LINES` changed lines; `lines` gives
    an item's changed lines."""
    out, total = [[]], 0
    for item in items:
        if out[-1] and total + lines(item) > BATCH_LINES:
            out.append([])
            total = 0
        out[-1].append(item)
        total += lines(item)
    return [batch for batch in out if batch]


def protocols(content):
    """The protocols of the `code-review` bundle, in its order, each with whether it is enabled."""
    entries = collect_entries(pathlib.Path(content)) if pathlib.Path(content).exists() else []
    return [{"id": e["id"], "title": e["title"], "enabled": e["enabled"]} for e in entries
            if e["kind"] == "protocol" and e["bundle"] == REVIEW_BUNDLE]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("review", nargs="?", help="the review's folder; without it, the developer's default set")
    parser.add_argument("--content", default=str(CONTENT))
    parser.add_argument("--unscoped", action="store_true", help="print the ids of the checked directives with no row")
    parser.add_argument("--plan", action="store_true", help="print the reviewers the review starts")
    parser.add_argument("--record-checks", nargs=2, metavar=("USE_CASE", "VERDICTS"),
                        help="record what every directive found in a use case, from its reviewers' verdicts (JSON)")
    parser.add_argument("--directive", help="with --record-checks: record only this directive's checks")
    args = parser.parse_args(argv)
    import _settings  # reads the craftsman home, which _reviews names; _reviews imports this module
    if not args.review and not args.unscoped:
        parser.error("the review's folder is needed, except with --unscoped")
    state = review_state.read(pathlib.Path(args.review)) if args.review else {}
    content = pathlib.Path(args.content).expanduser()
    if args.record_checks:
        use_case, verdicts = args.record_checks
        try:
            print(json.dumps(record_checks(content, args.review, use_case, json.loads(verdicts),
                                           _settings.review_directives(), directive=args.directive), indent=2))
        except (review_state.Refused, ValueError) as refused:
            sys.exit(f"review_directives: {refused}")
        return 0
    if args.plan:
        print(json.dumps(plan(content, args.review, state, _settings.review_directives()), indent=2))
        return 0
    if args.unscoped:
        print(json.dumps(unscoped(content, state, _settings.review_directives())))
        return 0
    print(json.dumps([{key: d[key] for key in ("id", "title", "path", "files", "reach")}
                      for d in to_check(content, state, _settings.review_directives())], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
