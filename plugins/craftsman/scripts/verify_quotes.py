#!/usr/bin/env python3
"""Whether what a subagent quotes is where it says -- see EXECUTION.md, "Independent directive review" and "Delegated
read-only preparation". Looking a quote up is not a judgement, so the run does not do it by reading.

    verify_quotes.py --root <folder> < quotes.json
    verify_quotes.py --root <folder> --reviewer '{"<directive id>": "<directive path>", ...}' < answer.txt

Quotes: a JSON list on stdin, `[{"path", "line" (optional), "quote"}]`, each path relative to `--root`. A quote is
found when its words are in the file, however the lines and spaces fall; with a line, it holds only within two lines
of it. Each comes back with `found`, `at` (the lines where it starts) and `problem` (why it could not be looked up).

Reviewer: a directive reviewer's answer on stdin (the plugin's `craftsman:directive-reviewer`). Every `VIOLATION` and
`CONVENTION` line comes back with `kind`, `directive`, `location`, `holds` and `problems`: the rule it quotes must be
in the directive's file, its `file:line` must exist under `--root`, and a `CONVENTION`'s existing line too. Whether the
line breaks the rule is still the run's to judge.
"""
import argparse
import json
import pathlib
import re
import sys

NEAR = 2  # lines a quote may start before or end after the line it is given with
LOCATION = re.compile(r"^(?P<path>[^:]+):(?P<line>\d+)$")


def normalized(text):
    """The text with every run of whitespace made one space, and the line each of its characters is on."""
    chars, lines, line, space = [], [], 1, False
    for char in text:
        if char.isspace():
            if not space and chars:
                chars.append(" ")
                lines.append(line)
            space = True
        else:
            chars.append(char)
            lines.append(line)
            space = False
        if char == "\n":
            line += 1
    return "".join(chars), lines


def occurrences(text, quote):
    """(first line, last line) of every place the quote's words are in the text."""
    flat, lines = normalized(text)
    wanted = " ".join(quote.split())
    found, start = [], flat.find(wanted) if wanted else -1
    while start >= 0:
        found.append((lines[start], lines[start + len(wanted) - 1]))
        start = flat.find(wanted, start + 1)
    return found


def read(root, path):
    """(text, problem) of a file under `root`."""
    root = pathlib.Path(root).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        return None, f"{path} is outside {root}"
    if not target.is_file():
        return None, f"no such file: {path}"
    return target.read_text(errors="replace"), None


def check_quotes(items, root):
    out = []
    for item in items:
        text, problem = read(root, item.get("path", ""))
        if problem:
            out.append({**item, "found": False, "at": [], "problem": problem})
            continue
        places = occurrences(text, str(item.get("quote", "")))
        line = item.get("line")
        held = any(first - NEAR <= line <= last + NEAR for first, last in places) if line else bool(places)
        out.append({**item, "found": held, "at": [first for first, _ in places], "problem": None})
    return out


def line_exists(root, location):
    found = LOCATION.match(location.strip())
    if not found:
        return f"{location} is not <file>:<line>"
    text, problem = read(root, found["path"])
    if problem:
        return problem
    if not 1 <= int(found["line"]) <= len(text.splitlines()):
        return f"{found['path']} has no line {found['line']}"
    return None


def check_reviewer(answer, root, directives):
    out = []
    for raw in answer.splitlines():
        fields = [field.strip() for field in raw.split(" | ")]
        if fields[0] not in ("VIOLATION", "CONVENTION"):
            continue
        kind, directive, location = (fields + ["", "", ""])[:3]
        quote = fields[3].strip('"“”') if len(fields) > 3 else ""
        problems = []
        if directive not in directives:
            problems.append(f"{directive} is not one of the directives the reviewer was given")
        else:
            rule = pathlib.Path(directives[directive])
            if not rule.is_file() or not occurrences(rule.read_text(errors="replace"), quote):
                problems.append(f"the rule quoted is not in {directive}'s directive: \"{quote}\"")
        problem = line_exists(root, location)
        if problem:
            problems.append(problem)
        if kind == "CONVENTION":
            problem = line_exists(root, fields[-1]) if len(fields) > 5 else "a CONVENTION names no existing line"
            if problem:
                problems.append(f"the existing line {fields[-1]}: {problem}")
        out.append({"kind": kind, "directive": directive, "location": location, "holds": not problems,
                    "problems": problems})
    return out


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True, help="the folder the paths are relative to")
    parser.add_argument("--reviewer", help="check a directive reviewer's answer: {directive id: directive path}")
    args = parser.parse_args(argv)
    try:
        if args.reviewer:
            print(json.dumps(check_reviewer(sys.stdin.read(), args.root, json.loads(args.reviewer)), indent=2))
        else:
            print(json.dumps(check_quotes(json.loads(sys.stdin.read()), args.root), indent=2))
    except ValueError as error:
        sys.exit(f"verify_quotes: {error}")


if __name__ == "__main__":
    main(sys.argv[1:])
