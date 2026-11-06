#!/usr/bin/env python3
"""A stand-in for `claude -p --input-format stream-json --output-format stream-json`, for the review session tests.

It records its arguments and every message it receives in $FAKE_CLAUDE_LOG, answers each message with one assistant
text and one result, and acts like the review skill just enough to be observed: the first message creates the review
state with the checkout it names, and a message from the review page is recorded as handled. A message that says
`needs <tool>` makes it ask for permission to use that tool the way `--permission-prompt-tool stdio` asks, and wait for
the answer, which it records too.
"""
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, os.environ["CRAFTSMAN_SCRIPTS"])
import review_state  # noqa: E402

LOG = pathlib.Path(os.environ["FAKE_CLAUDE_LOG"])
REVIEW = pathlib.Path(os.environ["FAKE_REVIEW_DIR"])
SESSION = "11111111-2222-3333-4444-555555555555"


def emit(event):
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def log(entry):
    with LOG.open("a") as out:
        out.write(json.dumps(entry) + "\n")


def ask(tool):
    """Ask for permission, as Claude does for a tool outside the allowed list, and wait for the answer."""
    command = {"command": "npm test", "description": "Run the tests"}
    request = {"subtype": "can_use_tool", "tool_name": tool, "input": command if tool == "Bash" else {"key": "AB-1"},
               "description": "Run the tests", "decision_reason": "This command requires approval",
               "permission_suggestions": [{"type": "addRules", "behavior": "allow", "destination": "localSettings",
                                           "rules": [{"toolName": tool, "ruleContent": "npm test"} if tool == "Bash"
                                                     else {"toolName": tool}]}]}
    emit({"type": "control_request", "request_id": "req-1", "request": request})
    log({"answered": json.loads(sys.stdin.readline())})


log({"argv": sys.argv[1:], "cwd": os.getcwd()})
if "--json-schema" in sys.argv:
    # a draft's preview: one prompt in, one finding out
    prompt = sys.stdin.read()
    log({"preview": prompt})
    emit([{"type": "result", "is_error": False, "structured_output": {
        "title": "Written up", "category": "naming", "severity": "nit", "description": "Why.",
        "comment": "Rename **it**.", "repeats": ""}}])
    sys.exit(0)
for line in sys.stdin:
    event = json.loads(line)
    if event.get("type") != "user":
        log({"unexpected": event})
        continue
    text = event["message"]["content"]
    log({"received": text})
    emit({"type": "system", "subtype": "init", "session_id": SESSION})
    if text.startswith("/craftsman:pr-review") and not (REVIEW / "review.json").exists():
        diff = REVIEW.parent / "fake.diff"
        diff.parent.mkdir(parents=True, exist_ok=True)
        diff.write_text("diff\n")
        checkout = re.search(r"--checkout (\S+)", text)
        review_state.change(REVIEW, "init", {"source": {"kind": "pull-request"}, "base": "a", "head": "b",
                                             "diff": str(diff), "checkout": checkout and checkout.group(1)})
    if '"type": "close"' in text:
        review_state.change(REVIEW, "set", {"closed": "2026-10-30T12:00:00+00:00"})
    needs = re.search(r"\bneeds (\S+)", text)
    if needs:
        ask(needs.group(1))
    handled = re.search(r"\bhandled (m\d+)", text)
    if handled:
        review_state.change(REVIEW, "handled", item_id=handled.group(1))
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": "got: " + text[:40]}]}})
    background = int(os.environ.get("FAKE_BACKGROUND", "0"))
    emit({"type": "result", "subtype": "success", "session_id": SESSION,
          "subagent_stats": {"spawned": background, "completed": 0, "failed": 0,
                             "killed": {"parent": 0, "user": 0, "system": 0}}})
