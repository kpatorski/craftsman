#!/usr/bin/env python3
"""Renders one compact line for Claude Code's status line: the craftsman session's Call stack, deepest step
first, plus the directives that step's protocol names in `uses:` -- see MANAGEMENT.md, "Status line".

Reads the JSON Claude Code sends on stdin for a status-line command (`cwd`, `workspace.project_dir`, ...),
finds the active `.claude/sessions/*.md` file in that project, and parses its `## Call stack` section per the
exact grammar EXECUTION.md defines (one line per level, indented two spaces per depth, `<id> (<status>[ --
free text])`, an optional `-> hand-off:` prefix). Never raises past `main()` -- a status line that crashes is
worse than one that prints nothing useful, so every failure degrades to a short, honest line instead.

Content root defaults to `~/.claude/craftsman/` (see EXECUTION.md, "Where the content lives"); override with
CRAFTSMAN_CONTENT_ROOT for testing against a scratch tree.
"""
import glob
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _frontmatter import parse_frontmatter, split_frontmatter  # noqa: E402

STATUS_RE = re.compile(r"^`(\w+)`")
LINE_RE = re.compile(r"^(\s*)(?:-> hand-off:\s*)?([A-Za-z0-9-]+)\s*\((\w+)")


def content_root():
    return pathlib.Path(os.environ.get("CRAFTSMAN_CONTENT_ROOT", os.path.expanduser("~/.claude/craftsman")))


def project_dir_from_stdin_json(payload):
    workspace = payload.get("workspace") or {}
    return workspace.get("project_dir") or payload.get("cwd")


def file_status(path):
    """First `` `word` `` after the `## Status` heading, or None if the file has no readable status."""
    text = path.read_text(errors="replace")
    in_status = False
    for line in text.split("\n"):
        if line.strip() == "## Status":
            in_status = True
            continue
        if in_status and line.strip() == "":
            continue
        if in_status:
            m = STATUS_RE.match(line.strip())
            return m.group(1) if m else None
    return None


def pick_session_file(sessions_dir):
    candidates = [pathlib.Path(p) for p in glob.glob(str(sessions_dir / "*.md"))]
    by_status = {}
    for p in candidates:
        try:
            st = file_status(p)
        except OSError:
            continue
        if st:
            by_status.setdefault(st, []).append(p)
    for preferred in ("active", "blocked"):
        if preferred in by_status:
            return max(by_status[preferred], key=lambda p: p.stat().st_mtime), preferred
    return None, None


def call_stack_lines(text):
    """Text between the `## Call stack` heading and the next `##` heading (or EOF)."""
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "## Call stack":
            start = i + 1
            break
    if start is None:
        return []
    out = []
    for line in lines[start:]:
        if line.strip().startswith("## "):
            break
        out.append(line)
    return out


def parse_stack(raw_lines):
    """-> list of (depth, id, status, whole_line) for every parseable line, in file order."""
    parsed = []
    for line in raw_lines:
        if not line.strip():
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        indent, node_id, status = m.groups()
        parsed.append((len(indent), node_id, status, line.strip()))
    return parsed


STATUS_RANK = {"active": 0, "blocked": 1, "pending": 2, "done": 3}


def deepest_node(parsed):
    """The most-indented `active`/`blocked` line -- that is where the run actually is, whether in progress or
    stuck, and a deeper `blocked` line is more informative than a shallower `active` parent still waiting on it.
    Falls back to the deepest line of any status only when nothing is active or blocked (nothing started yet, or
    everything already done)."""
    if not parsed:
        return None
    in_progress = [n for n in parsed if n[2] in ("active", "blocked")]
    pool = in_progress if in_progress else parsed
    max_depth = max(n[0] for n in pool)
    deepest = [n for n in pool if n[0] == max_depth]
    return min(deepest, key=lambda n: STATUS_RANK.get(n[2], 9))


def path_to(parsed, target):
    """Walk back from `target` through preceding lines with strictly shallower depth, root first."""
    idx = parsed.index(target)
    path = [target]
    depth = target[0]
    for node in reversed(parsed[:idx]):
        if node[0] < depth:
            path.append(node)
            depth = node[0]
    path.reverse()
    return path


def find_protocol_file(root, node_id):
    direct = root / "protocols" / node_id / "protocol.md"
    if direct.exists():
        return direct
    for match in root.glob(f"bundles/*/protocols/{node_id}/protocol.md"):
        return match
    return None


def uses_for(root, node_id):
    proto = find_protocol_file(root, node_id)
    if proto is None:
        return []
    fm_text, _ = split_frontmatter(proto.read_text(errors="replace"))
    if fm_text is None:
        return []
    fm = parse_frontmatter(fm_text)
    uses = fm.get("uses")
    return uses if isinstance(uses, list) else []


def render(project_dir, root):
    sessions_dir = pathlib.Path(project_dir) / ".claude" / "sessions"
    if not sessions_dir.is_dir():
        return "craftsman: idle"
    session_file, status = pick_session_file(sessions_dir)
    if session_file is None:
        return "craftsman: idle"
    parsed = parse_stack(call_stack_lines(session_file.read_text(errors="replace")))
    current = deepest_node(parsed)
    if current is None:
        return f"craftsman: {session_file.stem} ({status})"
    path = path_to(parsed, current)
    chain = " > ".join(f"{node_id} ({st})" if node_id == current[1] else node_id for _, node_id, st, _ in path)
    uses = uses_for(root, current[1])
    line = f"craftsman: {chain}"
    if uses:
        line += f"  |  uses: {', '.join(uses)}"
    return line


def main():
    try:
        payload = json.load(sys.stdin)
        project_dir = project_dir_from_stdin_json(payload)
        if not project_dir:
            print("craftsman: (no project dir)")
            return
        print(render(project_dir, content_root()))
    except Exception:
        print("craftsman: (status unavailable)")


if __name__ == "__main__":
    main()
