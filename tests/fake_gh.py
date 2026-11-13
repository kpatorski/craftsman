#!/usr/bin/env python3
"""A stand-in for `gh api`, for the sending and conversation tests. It records every call in $FAKE_GH_LOG (argv and
the JSON sent), keeps what is on the pull request in $FAKE_GH_STATE, and answers the way GitHub's REST API does for the
calls send_review.py and github_conversation.py make. FAKE_GH_FAIL=1 makes every call fail; FAKE_GH_NO_FILE=1 makes
a comment on a whole file fail, as a GitHub that does not know `subject_type` answers.

The state: `reviews` -- the inline comments of each review sent, by review id; `comments` -- further inline comments,
written by others or posted as replies; `issue_comments` -- the general comments; `review_list` -- the reviews as
GitHub lists them; `pulls` -- the pull requests by number, as GitHub's REST API gives one. A test may seed any of them.
"""
import json
import os
import pathlib
import re
import sys
import urllib.parse

LOG = pathlib.Path(os.environ["FAKE_GH_LOG"])
STATE = pathlib.Path(os.environ["FAKE_GH_STATE"])
ME = {"login": "me"}
AT = "2026-11-01T10:00:00Z"

args = sys.argv[1:]
payload = json.loads(sys.stdin.read() or "null") if "--input" in args else None
with LOG.open("a") as out:
    out.write(json.dumps({"args": args, "payload": payload, "host": os.environ.get("GH_HOST")}) + "\n")
if os.environ.get("FAKE_GH_FAIL"):
    sys.exit("HTTP 422: Unprocessable Entity")

state = json.loads(STATE.read_text()) if STATE.exists() else {}
for key, empty in (("reviews", {}), ("comments", []), ("issue_comments", []), ("review_list", [])):
    state.setdefault(key, empty)
endpoint = next(arg for arg in args if arg.startswith("repos/"))


def pull_comments():
    return [dict(comment, pull_request_review_id=int(review_id))
            for review_id, comments in state["reviews"].items() for comment in comments] + state["comments"]


if endpoint.endswith("/reviews") and "POST" in args:
    review_id = str(len(state["reviews"]) + 1)
    state["reviews"][review_id] = [
        dict(comment, id=int(f"{review_id}{n}"), user=ME, created_at=AT,
             html_url=f"https://github.com/org/booking/pull/123#discussion_r{review_id}{n}")
        for n, comment in enumerate(payload["comments"], 1)]
    answer = {"id": int(review_id)}
elif endpoint.endswith("/reviews"):
    answer = state["review_list"]
elif "/reviews/" in endpoint and endpoint.endswith("/comments"):
    # GitHub answers this one with `position` and leaves `line` out (null): only the pull's own list carries `line`
    answer = [dict(comment, line=None, position=comment["line"]) for comment in
              state["reviews"][endpoint.split("/reviews/")[1].split("/")[0]]]
elif endpoint.endswith("/replies") and "POST" in args:
    root = int(endpoint.split("/comments/")[1].split("/")[0])
    parent = next(c for c in pull_comments() if c["id"] == root)
    reply_id = 9000 + len(state["comments"])
    answer = {"id": reply_id, "in_reply_to_id": root, "body": payload["body"], "user": ME, "created_at": AT,
              "path": parent["path"], "line": parent["line"], "side": parent.get("side", "RIGHT"),
              "html_url": f"https://github.com/org/booking/pull/123#discussion_r{reply_id}"}
    state["comments"].append(answer)
elif endpoint.endswith("/pulls/123/comments") and "POST" in args:
    if os.environ.get("FAKE_GH_NO_FILE"):
        sys.exit("HTTP 422: Unprocessable Entity")
    comment_id = 9000 + len(state["comments"])
    answer = dict(payload, id=comment_id, line=None, user=ME, created_at=AT,
                  html_url=f"https://github.com/org/booking/pull/123#discussion_r{comment_id}")
    state["comments"].append(answer)
elif endpoint.endswith("/pulls/123/comments"):
    answer = pull_comments()
elif endpoint.endswith("/issues/123/comments") and "POST" in args:
    number = len(state["issue_comments"]) + 1
    answer = {"id": 500 + number, "body": payload["body"], "user": ME, "created_at": AT,
              "html_url": f"https://github.com/org/booking/pull/123#issuecomment-{number}"}
    state["issue_comments"].append(answer)
elif endpoint.endswith("/issues/123/comments"):
    answer = state["issue_comments"]
elif re.fullmatch(r"repos/[^/]+/[^/]+/pulls/\d+", endpoint):
    pull = state.get("pulls", {}).get(endpoint.rsplit("/", 1)[1])
    if not pull:
        sys.exit("HTTP 404: Not Found")
    answer = pull
elif re.fullmatch(r"repos/[^/]+/[^/]+/pulls\?.*", endpoint):
    query = urllib.parse.parse_qs(endpoint.split("?", 1)[1])
    answer = [pull for pull in state.get("pulls", {}).values()
              if pull["head"]["label"] == query["head"][0] and pull.get("state", "open") == query.get("state", ["open"])[0]]
else:
    sys.exit(f"fake gh does not know {endpoint}")
STATE.write_text(json.dumps(state))
print(json.dumps(answer))
