#!/usr/bin/env python3
"""Send the findings the developer marked to send, and the developer's own comments, to the pull request -- see
REVIEW.md.

    send_review.py <review dir>

Run by the dashboard server when the developer presses Send, never by the agent. Every finding marked `to-send` is
sent; nothing else is. Its first location gets the comment, in one GitHub review on the reviewed commit; every
further location gets a short reference to that first comment, in a second review once the first comment's link
exists. A line of the diff, added, kept or removed, gets an inline comment; a whole file of the change gets a comment
on that file. A line outside the diff, a file outside the change, or a whole file a GitHub cannot comment on (one
that knows no `subject_type`) gets a general comment on the pull request that names the place. A finding becomes
`sent` only once its first comment exists on GitHub; a failure leaves it `to-send`, with the reason in the result. A
comment already on the pull request -- the same place and text -- is not sent again: its link is recorded instead.

Every comment of the developer's waiting for Send goes too: a comment on the whole pull request to its conversation, a
reply to its thread on GitHub. Each becomes `sent` once it exists there; one already there, with the same text in the
same place, is recorded instead of sent again. Prints the result as JSON.
"""
import json
import os
import pathlib
import re
import subprocess
import sys

import review_state
from _reviews import PULL_REQUEST


def gh_api(gh, endpoint, payload=None, host="github.com"):
    """`gh api` against `host`, github.com or a GitHub Enterprise one."""
    args = list(gh) + ["api", endpoint] + (["-X", "POST", "--input", "-"] if payload is not None else ["--paginate"])
    done = subprocess.run(args, input=json.dumps(payload) if payload is not None else None, capture_output=True,
                          text=True, timeout=60, env={**os.environ, "GH_HOST": host})
    if done.returncode != 0:
        raise RuntimeError((done.stderr or done.stdout).strip() or f"gh api {endpoint} failed")
    return pages(done.stdout)


def pages(text):
    """`gh api --paginate` prints one JSON array per page, back to back; a list is joined into one, an object kept."""
    decoder, text, at, found = json.JSONDecoder(), text.strip(), 0, []
    while at < len(text):
        value, at = decoder.raw_decode(text, at)
        found.append(value)
        while at < len(text) and text[at].isspace():
            at += 1
    return [item for page in found for item in page] if all(isinstance(page, list) for page in found) else found[0]


def changed_lines(diff_text):
    """{(path, side): set of line numbers} that a review can comment on inline: RIGHT counts the new file's lines,
    LEFT the old one's. Every file of the diff has an entry for both sides, maybe empty."""
    lines, path, old, new = {}, None, None, None
    for line in diff_text.splitlines():
        if line.startswith("diff "):
            path, old, new = None, None, None
            continue
        if new is None and line.startswith("--- "):
            path = line[6:] if line.startswith("--- a/") else None
            continue
        if new is None and line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else path
            for side in ("LEFT", "RIGHT"):
                lines.setdefault((path, side), set())
            continue
        hunk = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk:
            old, new = int(hunk.group(1)), int(hunk.group(2))
            continue
        if path is None or new is None or line.startswith("\\"):
            continue
        if not line.startswith("+"):
            lines[(path, "LEFT")].add(old)
            old += 1
        if not line.startswith("-"):
            lines[(path, "RIGHT")].add(new)
            new += 1
    return lines


def pull_request(state):
    source = state["source"]
    pull = source if source.get("kind") == "pull-request" else source.get("pull-request")
    if not pull:
        raise review_state.Refused("this review has no pull request to send to")
    url = PULL_REQUEST.match(pull.get("url") or "")
    return pull["repository"], pull["number"], url["host"] if url else "github.com"


def gh_command():
    return os.environ.get("CRAFTSMAN_GH", "gh").split()


def send(review, gh=None):
    review = pathlib.Path(review)
    gh = gh or gh_command()
    state = review_state.read(review)
    repository, number, host = pull_request(state)

    def api(endpoint, payload=None):
        return gh_api(gh, endpoint, payload, host)

    findings = [f for f in state["findings"] if f["status"] == "to-send"]
    inline = changed_lines((review / "diff" / f"{state['head']}.diff").read_text())
    on_diff = lambda loc: loc.get("line") in inline.get((loc["path"], loc.get("side", "RIGHT")), set())  # noqa: E731
    # a whole file of the change takes a comment of its own, on the file
    on_file = lambda loc: loc.get("line") is None and (loc["path"], "RIGHT") in inline  # noqa: E731
    pulls = f"repos/{repository}/pulls/{number}"
    sent, errors, urls = [], [], {}
    # what is on the pull request already: a comment sent before, but never recorded as sent, is not sent again
    on_github = {"inline": {}, "general": {}, "replies": {}}

    def look_on_github():
        inline_comments = api(f"{pulls}/comments")
        on_github["inline"] = {(c.get("path"), c.get("line"), c.get("body")): c["html_url"] for c in inline_comments}
        on_github["replies"] = {(c.get("in_reply_to_id"), c.get("body")): c["html_url"] for c in inline_comments
                                if c.get("in_reply_to_id")}
        on_github["general"] = {c.get("body"): c["html_url"]
                                for c in api(f"repos/{repository}/issues/{number}/comments")}
        on_github["read"] = True

    def review_with(comments):
        made = api(f"{pulls}/reviews", {"commit_id": state["head"], "event": "COMMENT", "body": "",
                                               "comments": comments})
        # the review's own comment list has no `line`; the pull's list has it, and says which review a comment is in
        return [c for c in api(f"{pulls}/comments") if c.get("pull_request_review_id") == made["id"]]

    def general(found, index, body):
        location = found["locations"][index]
        place = f"{location['path']}:{location['line']}" if location.get("line") else location["path"]
        text = f"**`{place}`**\n\n{body}"
        if text in on_github["general"]:
            urls[(found["id"], index)] = on_github["general"][text]
            return
        made = api(f"repos/{repository}/issues/{number}/comments", {"body": text})
        urls[(found["id"], index)] = made["html_url"]

    def whole_file(found, index, body):
        path = found["locations"][index]["path"]
        earlier = on_github["inline"].get((path, None, body))
        if earlier:
            urls[(found["id"], index)] = earlier
            return
        try:
            made = api(f"{pulls}/comments", {"commit_id": state["head"], "path": path, "subject_type": "file",
                                             "body": body})
        except RuntimeError:
            # a GitHub that knows no comment on a whole file: the conversation gets it, naming the file
            general(found, index, body)
            return
        urls[(found["id"], index)] = made["html_url"]

    def elsewhere(found, index, body):
        (whole_file if on_file(found["locations"][index]) else general)(found, index, body)

    def inline_round(pairs):
        for found, index, body in pairs:
            location = found["locations"][index]
            earlier = on_github["inline"].get((location["path"], location["line"], body))
            if earlier:
                urls[(found["id"], index)] = earlier
        pairs = [(f, i, body) for f, i, body in pairs if (f["id"], i) not in urls]
        comments = [{"path": f["locations"][i]["path"], "line": f["locations"][i]["line"],
                     "side": f["locations"][i].get("side", "RIGHT"), "body": body} for f, i, body in pairs]
        if not comments:
            return
        posted = review_with(comments)
        for (found, index, body), comment in zip(pairs, comments):
            match = next((p for p in posted if (p.get("path"), p.get("line"), p.get("body"))
                          == (comment["path"], comment["line"], body)), None)
            if match:
                urls[(found["id"], index)] = match["html_url"]

    try:
        look_on_github()
        inline_round([(f, 0, f["comment"]) for f in findings if on_diff(f["locations"][0])])
        for found in findings:
            if not on_diff(found["locations"][0]):
                elsewhere(found, 0, found["comment"])
    except RuntimeError as failure:
        errors.append(str(failure))
    further = []
    for found in findings:
        first = urls.get((found["id"], 0))
        for index in range(1, len(found["locations"]) if first else 0):
            further.append((found, index, f"Same as {first}"))
    try:
        inline_round([pair for pair in further if on_diff(pair[0]["locations"][pair[1]])])
        for found, index, body in further:
            if not on_diff(found["locations"][index]):
                elsewhere(found, index, body)
    except RuntimeError as failure:
        errors.append(str(failure))
    for found in findings:
        entries = [{"location": index, "url": urls[(found["id"], index)]}
                   for index in range(len(found["locations"])) if (found["id"], index) in urls]
        if entries and entries[0]["location"] == 0:
            review_state.change(review, "mark-sent", {"sent": entries}, item_id=found["id"])
            sent.append(found["id"])
            missing = len(found["locations"]) - len(entries)
            if missing:
                errors.append(f"{found['id']}: {missing} further place(s) got no reference")
    # a comment is sent only once what is on GitHub is known, so a failed read never sends one twice
    for comment in state.get("comments", []) if on_github.get("read") else []:
        if comment["status"] != "to-send":
            continue
        try:
            url = send_comment(api, comment, repository, number, on_github)
        except RuntimeError as failure:
            errors.append(f"{comment['id']}: {failure}")
            continue
        review_state.change(review, "comment-sent", {"url": url}, item_id=comment["id"])
        sent.append(comment["id"])
    return {"sent": sent, "errors": errors}


def send_comment(api, comment, repository, number, on_github):
    """One comment of the developer's on GitHub; its link. A reply goes into the thread it answers."""
    body, root = comment["body"], comment.get("reply-to")
    if root is None:
        earlier = on_github["general"].get(body)
        return earlier or api(f"repos/{repository}/issues/{number}/comments", {"body": body})["html_url"]
    earlier = on_github["replies"].get((root, body))
    return earlier or api(f"repos/{repository}/pulls/{number}/comments/{root}/replies", {"body": body})["html_url"]


def main(argv):
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        result = send(pathlib.Path(argv[0]))
    except review_state.Refused as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
