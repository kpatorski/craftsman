#!/usr/bin/env python3
"""What everyone wrote on a review's pull request -- see REVIEW.md, "`github.json`".

    github_conversation.py <review dir>

The dashboard server reads it with `gh api` when the review page asks, and the agent from the command line when it
refreshes the review. It is kept in `<review>/github.json`, beside `review.json`: it is GitHub's state, not the
review's, so only this module writes it. From the command line it prints where it is kept, how many comments it holds
and why GitHub did not answer, or null; it exits 1 when GitHub did not answer or the review has no pull request. It holds `fetched` (when it was
last read), `error` (why the last read failed, or null) and `comments`, oldest first, each one of:

- `issue` -- a comment in the pull request's conversation;
- `review` -- a review with its text, or one that approved or asked for changes; `state` says which;
- `inline` -- a comment on the code, with `path`, `line` (null once the line is gone from the pull request),
  `original-line`, `side`, and `root`: the id of its thread's first comment, the one a reply answers.

Each also has `id`, `author`, `at`, `body` and `url`. A failed read keeps the comments read before.
"""
import datetime
import json
import pathlib
import sys

import review_state

DECIDED = ("APPROVED", "CHANGES_REQUESTED")


def read(review):
    path = pathlib.Path(review) / "github.json"
    return json.loads(path.read_text()) if path.is_file() else None


def said(kind, comment, at):
    return {"id": comment["id"], "kind": kind, "author": (comment.get("user") or {}).get("login"),
            "at": comment.get(at), "body": comment.get("body") or "", "url": comment.get("html_url")}


def fetch(review, gh=None):
    """Read the pull request's conversation from GitHub and keep it; the conversation. Raises Refused without one."""
    from send_review import gh_api, gh_command, pull_request  # send_review needs _reviews, which reads this module
    review = pathlib.Path(review)
    repository, number, host = pull_request(review_state.read(review))
    gh = gh or gh_command()
    kept = read(review) or {"fetched": None, "error": None, "comments": []}
    try:
        issue = gh_api(gh, f"repos/{repository}/issues/{number}/comments", host=host)
        reviews = gh_api(gh, f"repos/{repository}/pulls/{number}/reviews", host=host)
        inline = gh_api(gh, f"repos/{repository}/pulls/{number}/comments", host=host)
    except RuntimeError as failure:
        conversation = {**kept, "error": str(failure)}
    else:
        comments = [said("issue", c, "created_at") for c in issue]
        comments += [{**said("review", r, "submitted_at"), "state": r.get("state")} for r in reviews
                     if (r.get("body") or "").strip() or r.get("state") in DECIDED]
        comments += [{**said("inline", c, "created_at"), "path": c.get("path"), "line": c.get("line"),
                      "original-line": c.get("original_line"), "side": c.get("side") or "RIGHT",
                      "root": c.get("in_reply_to_id") or c["id"]} for c in inline]
        comments.sort(key=lambda c: c["at"] or "")
        conversation = {"fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                        "error": None, "comments": comments}
    (review / "github.json").write_text(json.dumps(conversation, indent=2, ensure_ascii=False))
    return conversation


def main(argv):
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    review = pathlib.Path(argv[0])
    try:
        conversation = fetch(review)
    except review_state.Refused as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 1
    print(json.dumps({"file": str(review / "github.json"), "comments": len(conversation["comments"]),
                      "error": conversation["error"]}))
    return 0 if conversation["error"] is None else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
