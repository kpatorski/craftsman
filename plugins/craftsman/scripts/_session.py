"""What the hooks need to know about craftsman session files (`<project>/.claude/sessions/*.md`, format in
EXECUTION.md, "The session file"): which runs are still open, where each one stands, and what it has loaded.
Built on render_status.py's parser so the two never read the same file differently.
"""
import glob
import pathlib
import re

from render_status import call_stack_lines, deepest_node, file_status, find_protocol_file, parse_stack, path_to

OPEN_STATES = ("active", "blocked")
ENTRY_RE = re.compile(r"^### (\d+)\. `([^`]+)`")
DIRECTIVE_ROW_RE = re.compile(r"^\|\s*([a-z0-9-]+)\s*\|")
MENTION_RE = re.compile(r"`([a-z][a-z0-9-]*)`")


def open_sessions(folders, states=OPEN_STATES):
    """Session files whose State is one of `states` (default: active or blocked), in any of `folders`, most
    recently written first."""
    found = {}
    for folder in folders:
        for name in glob.glob(str(pathlib.Path(folder) / ".claude" / "sessions" / "*.md")):
            path = pathlib.Path(name).resolve()
            try:
                if file_status(path) in states:
                    found[path] = path.stat().st_mtime
            except OSError:
                continue
    return sorted(found, key=found.get, reverse=True)


def section(text, heading):
    lines, out, inside = text.split("\n"), [], False
    for line in lines:
        if line.strip().startswith("## "):
            if inside:
                break
            inside = line.strip() == f"## {heading}"
            continue
        if inside:
            out.append(line)
    return out


def last_checkpoint(text):
    """(number, step id, has an **Answer:** line) of the Checkpoint log's last entry, or None if the log is empty."""
    entry = None
    for line in section(text, "Checkpoint log"):
        m = ENTRY_RE.match(line)
        if m:
            entry = [int(m.group(1)), m.group(2), False]
        elif entry and line.lstrip("- ").startswith("**Answer:**"):
            entry[2] = True
    return tuple(entry) if entry else None


def current_path(text):
    """The Call stack path from the entry point down to where the run is, as ids, or [] if there is no stack."""
    parsed = parse_stack(call_stack_lines(text))
    current = deepest_node(parsed)
    return [node_id for _, node_id, _, _ in path_to(parsed, current)] if current else []


def directives_in_effect(text):
    """[(id, certain)] in file order. A row of the table EXECUTION.md defines is certainly a directive id. Older
    session files list them as prose bullets instead (`` `prefer-lombok` -- applied at … ``); every backticked word
    there is only a candidate (`craftsman-workshop`, a step id), for the caller to keep if a directive of that id
    exists."""
    found = {}
    for line in section(text, "Directives in effect"):
        row = DIRECTIVE_ROW_RE.match(line)
        if row:
            if row.group(1) != "id":
                found[row.group(1)] = True
            continue
        for word in MENTION_RE.findall(line):
            found.setdefault(word, False)
    return list(found.items())


def next_line(text):
    """The **Next:** line, or -- in older session files -- the first line under a `## Next` heading."""
    for line in text.split("\n"):
        if "**Next:**" in line:
            return line.split("**Next:**", 1)[1].strip()
    paragraph = []
    for line in section(text, "Next"):
        if line.strip():
            paragraph.append(line.strip())
        elif paragraph:
            break
    return " ".join(paragraph)


def find_directive_file(root, directive_id):
    direct = root / "directives" / directive_id / "directive.md"
    if direct.exists():
        return direct
    for match in root.glob(f"bundles/*/directives/{directive_id}/directive.md"):
        return match
    return None


__all__ = ["open_sessions", "last_checkpoint", "current_path", "directives_in_effect", "next_line",
           "find_directive_file", "find_protocol_file"]
