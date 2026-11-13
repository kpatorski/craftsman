#!/usr/bin/env python3
"""Hook: during a craftsman run, every subagent starts on the model of a tier the run chose -- see EXECUTION.md,
"Choosing a model".

PreToolUse on Agent (or Task, its older name): when a craftsman run is in progress -- a session file `active` or
`blocked` in the working folder, or the review's session the dashboard server starts (`CRAFTSMAN_RUN` in its
environment) -- a call that names no `model`, or a model no tier is mapped to (model_tiers.py), is denied. The deny
reason gives the tiers and their models, so the run picks one and starts the subagent again.

Anything else, and any failure inside this script, is no objection: a broken gate must not block unrelated work.
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import model_tiers  # noqa: E402
from _session import open_sessions  # noqa: E402


def in_a_run(cwd):
    return bool(os.environ.get("CRAFTSMAN_RUN")) or bool(open_sessions([cwd]))


def refusal(tool_input):
    """Why this call may not start, or None."""
    name = tool_input.get("model")
    if name and model_tiers.tier_of(name):
        return None
    subagent = tool_input.get("subagent_type") or "general-purpose"
    problem = (f"`{name}` is no tier's model" if name
               else f"the call starting `{subagent}` names no model")
    return (f"craftsman run in progress: {problem}. Pick the tier the work needs, per EXECUTION.md, \"Choosing a "
            f"model\" -- fast for mechanical work, balanced for steps already laid out, deep for analysis nobody has "
            f"done yet -- and start it again with `model` set to that tier's model: {model_tiers.described()}.")


def gate(payload):
    tool_input = payload.get("tool_input") or {}
    if not in_a_run(payload.get("cwd") or os.getcwd()):
        return
    reason = refusal(tool_input)
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))


def main():
    try:
        payload = json.load(sys.stdin)
        if payload.get("hook_event_name") == "PreToolUse" and payload.get("tool_name") in ("Agent", "Task"):
            gate(payload)
    except Exception as error:  # a broken gate must never block unrelated work
        print(f"craftsman model gate skipped: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
