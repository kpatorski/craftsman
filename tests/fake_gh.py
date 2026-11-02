#!/usr/bin/env python3
"""A stand-in for `gh api`, for the sending tests. It records every call in $FAKE_GH_LOG (argv and the JSON sent),
keeps the review and general comments it was given in $FAKE_GH_STATE, and answers the way GitHub's REST API does for the calls
send_review.py makes. FAKE_GH_FAIL=1 makes every call fail.
"""
import json
import os
import pathlib
import sys

LOG = pathlib.Path(os.environ["FAKE_GH_LOG"])
STATE = pathlib.Path(os.environ["FAKE_GH_STATE"])

args = sys.argv[1:]
payload = json.loads(sys.stdin.read() or "null") if "--input" in args else None
with LOG.open("a") as out:
    out.write(json.dumps({"args": args, "payload": payload}) + "\n")
if os.environ.get("FAKE_GH_FAIL"):
    sys.exit("HTTP 422: Unprocessable Entity")

state = json.loads(STATE.read_text()) if STATE.exists() else {"reviews": {}, "issue_comments": []}
endpoint = next(arg for arg in args if arg.startswith("repos/"))
if endpoint.endswith("/reviews") and "POST" in args:
    review_id = str(len(state["reviews"]) + 1)
    state["reviews"][review_id] = [
        dict(comment, html_url=f"https://github.com/org/booking/pull/123#discussion_r{review_id}{n}")
        for n, comment in enumerate(payload["comments"], 1)]
    answer = {"id": int(review_id)}
elif "/reviews/" in endpoint and endpoint.endswith("/comments"):
    # GitHub answers this one with `position` and leaves `line` out (null): only the pull's own list carries `line`
    answer = [dict(comment, line=None, position=comment["line"]) for comment in
              state["reviews"][endpoint.split("/reviews/")[1].split("/")[0]]]
elif endpoint.endswith("/pulls/123/comments"):
    answer = [dict(comment, pull_request_review_id=int(review_id))
              for review_id, comments in state["reviews"].items() for comment in comments]
elif endpoint.endswith("/issues/123/comments") and "POST" in args:
    answer = {"body": payload["body"],
              "html_url": f"https://github.com/org/booking/pull/123#issuecomment-{len(state['issue_comments']) + 1}"}
    state["issue_comments"].append(answer)
elif endpoint.endswith("/issues/123/comments"):
    answer = state["issue_comments"]
else:
    sys.exit(f"fake gh does not know {endpoint}")
STATE.write_text(json.dumps(state))
print(json.dumps(answer))
