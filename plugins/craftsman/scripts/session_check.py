#!/usr/bin/env python3
"""Hook (PostToolUse on Write|Edit|Bash): after a craftsman session file is written, say what in it no longer has
the shape EXECUTION.md defines -- see MANAGEMENT.md, "Hooks".

The session file is what a run resumes from, what the dashboard and the status line parse, and what the commit gate
reads; a malformed one fails silently in all of them. This checks only what EXECUTION.md states outright (the
sections, State, the Call stack grammar, the Checkpoint log's numbering and labels) and reports each problem with
its line, as additional context for the model to fix. It never blocks and never edits.

A shell command does not say which file it wrote, so after Bash the check covers the session files the command
could have reached -- it must name a `.claude/sessions` path -- that were written in the last two minutes. Where
the path hides behind a variable the command does not set itself, the folders the command runs in are checked.

A file without a `**State:**` label predates the current format; it is left alone rather than reported line by line
-- rewriting an old run's record to satisfy a checker would destroy what it is for.
"""
import json
import pathlib
import re
import sys
import time

SECTIONS = ("Task", "Status", "Call stack", "Directives in effect", "Checkpoint log", "Parked")
STATES = ("active", "blocked", "done")
STEP_STATUSES = ("pending", "active", "blocked", "done")
STEP_RE = re.compile(r"^(\s*)(?:-> hand-off:\s*)?([A-Za-z0-9-]+)\s*\(([A-Za-z-]+)[^)]*\)\s*$")
ENTRY_RE = re.compile(r"^### (\d+)\. `([^`]+)`")
STATE_RE = re.compile(r"\*\*State:\*\*\s*`([^`]*)`")
SESSIONS_RE = re.compile(r"([^\s'\"=;&|()<>]*)\.claude/sessions\b")
CD_RE = re.compile(r"(?:^|[;&|(\n]\s*)cd\s+([^\s;&|]+)")
ASSIGN_RE = re.compile(r"(?:^|[;&|(\n\s])([A-Za-z_]\w*)=(\"[^\"$`]*\"|'[^']*'|[^\s;&|$`\"']+)")
RECENT_SECONDS = 120


def sections(lines):
    """{heading: [(line number, text)]} for every `## ` section."""
    found, current = {}, None
    for number, line in enumerate(lines, 1):
        if line.startswith("## "):
            current = found.setdefault(line[3:].strip(), [])
        elif current is not None:
            current.append((number, line))
    return found


def check_call_stack(body, state):
    problems, base, previous, active = [], None, 0, []
    for number, line in body:
        if not line.strip():
            continue
        step = STEP_RE.match(line)
        if not step:
            problems.append(f"line {number}, Call stack: `{line.strip()}` is not `<id> (<status>[ — note])`")
            continue
        indent, step_id, status = len(step.group(1)), step.group(2), step.group(3)
        if status not in STEP_STATUSES:
            problems.append(f"line {number}, Call stack: `{step_id}` has status `{status}` — use one of "
                            f"{', '.join(STEP_STATUSES)}")
        elif status == "active":
            active.append(step_id)
        base = indent if base is None else base
        depth = (indent - base) / 2
        if depth != int(depth) or depth < 0 or depth > previous + 1:
            problems.append(f"line {number}, Call stack: `{step_id}` is not indented by two spaces per level, at most "
                            f"one level deeper than the line above")
        else:
            previous = int(depth)
    if state == "done" and active:
        problems.append(f"State is `done` but the Call stack still has active steps: {', '.join(active)}")
    return problems


def check_checkpoint_log(body):
    problems, entries = [], []
    for number, line in body:
        entry = ENTRY_RE.match(line)
        if entry:
            entries.append({"line": number, "number": int(entry.group(1)), "step": entry.group(2), "labels": set()})
        elif entries:
            entries[-1]["labels"].update(re.findall(r"\*\*(Asked|Answer|Decision|Actor):\*\*", line))
    for position, entry in enumerate(entries, 1):
        name = f"line {entry['line']}, Checkpoint log: ### {entry['number']}. `{entry['step']}`"
        if entry["number"] != position:
            problems.append(f"{name} is entry {position} — entries are numbered 1, 2, 3 in order, none skipped or "
                            f"reused (the log is append-only: fix the newest entry, never renumber earlier ones)")
        if "Asked" not in entry["labels"]:
            problems.append(f"{name} has no **Asked:** line")
        if "Answer" in entry["labels"] and "Actor" not in entry["labels"]:
            problems.append(f"{name} has an **Answer:** but no **Actor:** line (`human:<name>`)")
    return problems


def problems_in(text):
    lines = text.split("\n")
    found = sections(lines)
    state = STATE_RE.search("\n".join(line for _, line in found.get("Status", [])))
    if not state:
        return []
    problems = [f"section `## {name}` is missing" for name in SECTIONS if name not in found]
    if state.group(1) not in STATES:
        problems.append(f"State is `{state.group(1)}` — use one of {', '.join(STATES)}")
    if "**Next:**" not in text:
        problems.append("there is no **Next:** line — the line a later session resumes from")
    problems += check_call_stack(found.get("Call stack", []), state.group(1))
    problems += check_checkpoint_log(found.get("Checkpoint log", []))
    return problems


def is_session_file(path):
    return path.suffix == ".md" and path.parent.name == "sessions" and path.parent.parent.name == ".claude"


def expanded(command):
    """The command with the shell variables it assigns itself (`NAME=literal`) written out where they are used."""
    for name, value in ASSIGN_RE.findall(command):
        value = value.strip("'\"")
        command = re.sub(r"\$\{" + name + r"\}|\$" + name + r"\b", lambda _: value, command)
    return command


def written_by(command, cwd):
    """Session files a shell command could have written: in a `.claude/sessions` folder it names, changed just now.

    A path that cannot be worked out from the text (a variable set elsewhere, a command substitution) falls back to
    the folders the command runs in.
    """
    command = expanded(command)
    mentions = SESSIONS_RE.findall(command)
    if not mentions:
        return []
    bases = [cwd] + [cwd / pathlib.Path(folder.strip("'\"")).expanduser() for folder in CD_RE.findall(command)]
    folders = {(base / pathlib.Path(prefix).expanduser() / ".claude" / "sessions").resolve()
               for base in bases for prefix in mentions + [""]}
    newest = time.time() - RECENT_SECONDS
    return sorted(path for folder in folders if folder.is_dir() for path in folder.glob("*.md")
                  if path.stat().st_mtime >= newest)


def report(path):
    problems = problems_in(path.read_text(errors="replace"))
    if not problems:
        return None
    return (f"craftsman: {path.name} no longer has the shape EXECUTION.md defines (\"the state file\"). The "
            f"dashboard, the status line, resuming and the commit gate all read this file. Fix these now, "
            f"changing nothing else in it:\n" + "\n".join(f"- {problem}" for problem in problems))


def main():
    try:
        payload = json.load(sys.stdin)
        tool_input = payload.get("tool_input") or {}
        if payload.get("tool_name") == "Bash":
            paths = written_by(tool_input.get("command", ""), pathlib.Path(payload.get("cwd") or "."))
        else:
            paths = [path for path in [pathlib.Path(tool_input.get("file_path", ""))] if is_session_file(path)]
        reports = [found for found in map(report, paths) if found]
        if reports:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                     "additionalContext": "\n\n".join(reports)}}))
    except Exception as error:  # a failed check must never get in the way of the write it follows
        print(f"craftsman session check skipped: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
