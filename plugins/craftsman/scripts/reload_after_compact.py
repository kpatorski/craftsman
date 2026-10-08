#!/usr/bin/env python3
"""Hook (SessionStart, source `compact`): put an open craftsman run back in front of the model after a compaction.

Compaction keeps a summary of the conversation but drops the text of files read earlier -- for a craftsman run,
the directives and protocols it is following. This prints, as additional context, every open run in the working
folder (State `active` or `blocked`): its session file, the step it is on, its Next line, and the full path of
each file to read again before continuing. It names the files; reading them stays the model's job, so the
injected text is short and never stale. See MANAGEMENT.md, "Hooks".
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _session import (current_path, directives_in_effect, find_directive_file, find_protocol_file,  # noqa: E402
                      next_line, open_sessions)
from render_status import content_root  # noqa: E402


def describe(session, root):
    text = session.read_text(errors="replace")
    path = current_path(text)
    lines = [f"- Session file: {session}", f"  Current step: {' > '.join(path) if path else '(no call stack)'}"]
    if next_line(text):
        lines.append(f"  Next: {next_line(text)}")
    lines.append("  Read again before the next step:")
    lines.append(f"  - {session}")
    if path:
        protocol = find_protocol_file(root, path[-1])
        lines.append(f"  - {protocol}" if protocol else f"  - protocol {path[-1]}: not found under {root}")
    for directive_id, certain in directives_in_effect(text):
        found = find_directive_file(root, directive_id)
        if found:
            lines.append(f"  - {found}")
        elif certain:
            lines.append(f"  - directive {directive_id}: not found under {root}")
    return "\n".join(lines)


def main():
    try:
        payload = json.load(sys.stdin)
        sessions = open_sessions([payload.get("cwd") or os.getcwd()])
        if not sessions:
            return
        root = content_root()
        context = ("craftsman: the conversation was just compacted while a run is open. Compaction dropped the text "
                   "of the directives and protocols this run follows; the summary is not a substitute for them. "
                   "Before taking the next step, read every file listed below in full, then continue from the "
                   "current step (EXECUTION.md, \"Resuming\" -- no need to ask again where to resume).\n\n"
                   + "\n\n".join(describe(s, root) for s in sessions))
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))
    except Exception as error:  # a failed reminder must never break the session
        print(f"craftsman reload after compact skipped: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
