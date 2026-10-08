#!/usr/bin/env python3
"""Hook: no git commit during a craftsman run until the developer has answered -- see MANAGEMENT.md, "Hooks".

One script, three hook events:

- UserPromptSubmit, and PostToolUse on AskUserQuestion: the developer has just spoken. Record the time for this
  Claude session. The model cannot produce either event itself, which is what makes this a real signal.
- PreToolUse on Bash: when the command makes a commit and a craftsman run is in progress (State `active`; a
  `blocked` run is paused and must not hold up unrelated commits) in the working folder or the commit's folder,
  deny it unless (1) the developer has spoken since the repository's
  last commit, and (2) the run's Checkpoint log ends with an entry that records an **Answer:**. The deny reason says
  which condition failed and what to do, so the agent can correct course instead of retrying.

Anything else, and any failure inside this script, is no objection: a broken gate must not block unrelated work.
"""
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _session import last_checkpoint, open_sessions  # noqa: E402

COMMIT_RE = re.compile(r"(?:^|[;&|(\n]\s*)git((?:\s+-[cC]\s+\S+|\s+--?[\w-]+(?:=\S+)?)*)\s+commit\b")
CD_RE = re.compile(r"(?:^|[;&|(\n]\s*)cd\s+(\S+)\s*&&[^;&|]*git\b[^\n]*\bcommit\b")
KEEP_SECONDS = 14 * 24 * 3600


def state_file():
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser("~/.claude/plugins/data/craftsman")
    return pathlib.Path(base) / "human-turns.json"


def load_turns():
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {}


def record_turn(session_id):
    now = time.time()
    turns = {k: v for k, v in load_turns().items() if now - v < KEEP_SECONDS}
    turns[session_id] = now
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(turns))
    tmp.replace(path)


def commit_folder(command, cwd):
    """The folder the commit runs in, or None if the command makes no commit."""
    m = COMMIT_RE.search(command)
    if not m:
        return None
    folder = pathlib.Path(cwd)
    options = shlex.split(m.group(1)) if m.group(1).strip() else []
    if "-C" in options and options.index("-C") + 1 < len(options):
        return folder / options[options.index("-C") + 1]
    cd = CD_RE.search(command)
    return folder / cd.group(1) if cd else folder


def last_commit(folder):
    """(unix time, short sha) of HEAD, or None in a repository without commits (or no repository)."""
    done = subprocess.run(["git", "-C", str(folder), "log", "-1", "--format=%ct %h"], capture_output=True, text=True)
    if done.returncode != 0 or not done.stdout.strip():
        return None
    stamp, sha = done.stdout.split()
    return int(stamp), sha


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


def gate(payload):
    cwd = payload.get("cwd") or os.getcwd()
    folder = commit_folder((payload.get("tool_input") or {}).get("command", ""), cwd)
    if folder is None:
        return
    sessions = open_sessions([cwd, folder], states=("active",))
    if not sessions:
        return
    session = sessions[0]
    spoke = load_turns().get(payload.get("session_id", ""), 0)
    head = last_commit(folder)
    # git stores commit time in whole seconds: a reply in the same second as the last commit counts as before it,
    # so a tie denies -- one more question is cheaper than one unapproved commit.
    if head is None and not spoke or head is not None and int(spoke) <= head[0]:
        since = f"since the last commit ({head[1]})" if head else "in this run before its first commit"
        deny(f"craftsman run in progress ({session.name}): no answer from the developer {since}. Commits happen only "
             f"after a blocking checkpoint. Ask the developer first and wait for the reply; an explicit request from "
             f"them to commit is such a reply. Then record it in the Checkpoint log and commit.")
        return
    entry = last_checkpoint(session.read_text(errors="replace"))
    if entry is None or not entry[2]:
        where = f"its last entry (### {entry[0]}. `{entry[1]}`)" if entry else "it has no entry yet"
        deny(f"craftsman run in progress ({session.name}): the Checkpoint log does not record the answer that "
             f"approves this commit -- {where} has no **Answer:** line. Record step, question, **Answer:** and "
             f"**Actor:** first (EXECUTION.md, \"Checkpoint protocol\"), then commit.")


def main():
    try:
        payload = json.load(sys.stdin)
        event = payload.get("hook_event_name")
        if event == "UserPromptSubmit" or event == "PostToolUse" and payload.get("tool_name") == "AskUserQuestion":
            record_turn(payload.get("session_id", ""))
        elif event == "PreToolUse" and payload.get("tool_name") == "Bash":
            gate(payload)
    except Exception as error:  # a broken gate must never block unrelated work
        print(f"craftsman commit gate skipped: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
