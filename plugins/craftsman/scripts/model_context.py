#!/usr/bin/env python3
"""Hook: a craftsman run knows each model tier's model from its first step -- see EXECUTION.md, "Choosing a model".

- UserPromptSubmit, a prompt that starts a run (`/craftsman:analyse`, `domain-design`, `implement`, `pr-review`);
- SessionStart, on startup or resume, when a run is open in the working folder or the session is a review's the
  dashboard server started (`CRAFTSMAN_RUN`).

Either adds one line to the context: the tiers and their models (model_tiers.py). After a compaction,
reload_after_compact.py brings it with the run's files. Anything else, and any failure, adds nothing.
"""
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import model_tiers  # noqa: E402
from _session import open_sessions  # noqa: E402

RUN = re.compile(r"^\s*/craftsman:(analyse|domain-design|implement|pr-review)\b")


def line():
    return (f"craftsman: a subagent of this run starts on the model of the tier its work needs -- "
            f"{model_tiers.described()} (EXECUTION.md, \"Choosing a model\").")


def wanted(payload):
    event = payload.get("hook_event_name")
    if event == "UserPromptSubmit":
        return bool(RUN.match(str(payload.get("prompt") or "")))
    if event == "SessionStart" and payload.get("source") in ("startup", "resume"):
        return bool(os.environ.get("CRAFTSMAN_RUN")) or bool(open_sessions([payload.get("cwd") or os.getcwd()]))
    return False


def main():
    try:
        payload = json.load(sys.stdin)
        if wanted(payload):
            print(json.dumps({"hookSpecificOutput": {"hookEventName": payload["hook_event_name"],
                                                     "additionalContext": line()}}))
    except Exception as error:  # a missing reminder must never break the session
        print(f"craftsman model context skipped: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
