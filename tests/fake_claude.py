#!/usr/bin/env python3
"""A stand-in for `claude -p --input-format stream-json --output-format stream-json`, for the review session tests.

It records its arguments and every message it receives in $FAKE_CLAUDE_LOG, answers each message with one assistant
text and one result, and acts like the review skill just enough to be observed: the first message creates the review
state with the checkout it names, and a message from the review page is recorded as handled.
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


log({"argv": sys.argv[1:], "cwd": os.getcwd()})
for line in sys.stdin:
    text = json.loads(line)["message"]["content"]
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
    handled = re.search(r"\bhandled (m\d+)", text)
    if handled:
        review_state.change(REVIEW, "handled", item_id=handled.group(1))
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": "got: " + text[:40]}]}})
    background = int(os.environ.get("FAKE_BACKGROUND", "0"))
    emit({"type": "result", "subtype": "success", "session_id": SESSION,
          "subagent_stats": {"spawned": background, "completed": 0, "failed": 0,
                             "killed": {"parent": 0, "user": 0, "system": 0}}})
