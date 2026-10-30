"""The review side of the dashboard: listing a project's reviews, the changes the page makes as the developer, and
the inbox through which the page's requests reach the review's session -- see REVIEW.md."""
import datetime
import json
import pathlib
import re

import review_state
from _markdown import render_markdown

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MESSAGE_FIELDS = {"answer": ("checkpoint", "option"), "explain": ("about",), "refresh": (), "ask": ("text", "about"),
                  "message": ("text",), "close": ()}


PULL_REQUEST = re.compile(r"^https://github\.com/[^/]+/[^/]+/pull/(\d+)/?$")
BRANCHES = re.compile(r"^([^\s:]+):([^\s:]+)$")


def review_id_for(source):
    """`pr-<number>` for a pull request URL, `<target>..<source>` with `/` replaced by `-` for two branches."""
    pull = PULL_REQUEST.match(source or "")
    if pull:
        return f"pr-{pull.group(1)}"
    branches = BRANCHES.match(source or "")
    if branches:
        return f"{branches.group(1)}..{branches.group(2)}".replace("/", "-")
    raise review_state.Refused(f"not a pull request URL or <target>:<source>: {source!r}")


def reviews_root(project):
    return pathlib.Path(project) / ".claude" / "reviews"


def review_dir(project, review_id):
    review = reviews_root(project) / review_id
    if not ID.match(review_id or "") or not (review / "review.json").is_file():
        raise review_state.Refused(f"no review {review_id!r} in {project}")
    return review


def list_reviews(projects):
    listed = []
    for project in projects:
        for state_file in sorted(reviews_root(project).glob("*/review.json")):
            try:
                state = json.loads(state_file.read_text())
            except (OSError, ValueError):
                continue
            counts = {}
            for found in state.get("findings", []):
                counts[found["status"]] = counts.get(found["status"], 0) + 1
            listed.append({"id": state_file.parent.name, "project": str(project), "source": state.get("source"),
                           "head": state.get("head"), "closed": state.get("closed"), "findings": counts,
                           "checkpoint": bool(state.get("checkpoint") and not state["checkpoint"].get("answer"))})
    return listed


def read_review(project, review_id):
    review = review_dir(project, review_id)
    state = review_state.read(review)
    return {"state": state, "pending": len(pending_messages(review)), "html": rendered(state),
            "console": console_lines(review)}


def rendered(state):
    """Every markdown text of the review as HTML, keyed the way the page looks it up."""
    texts = {"scope": state.get("scope"), "requirements": state.get("requirements"),
             "boundaries": (state.get("structure") or {}).get("boundaries")}
    for found in state.get("findings", []):
        for field in ("description", "comment"):
            texts[f"finding:{found['id']}:{field}"] = found.get(field)
    for explanation in state.get("explanations", []):
        texts[f"explanation:{explanation['id']}"] = explanation.get("body")
    for group in state.get("map", []):
        texts[f"group:{group['id']}"] = group.get("summary")
    return {key: render_markdown(text, lambda url: None) for key, text in texts.items() if text}


def console_lines(review, limit=400):
    """The session's stream as the console shows it: what the developer said, what the agent said and did, what was
    refused, and where each turn ended. The last `limit` lines."""
    path = pathlib.Path(review) / "session.jsonl"
    lines = []
    for raw in (path.read_text().splitlines() if path.exists() else []):
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        kind = event.get("type")
        if kind == "user" and isinstance(event.get("message", {}).get("content"), str):
            lines.append({"kind": "you", "text": event["message"]["content"]})
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text", "").strip():
                    lines.append({"kind": "text", "text": block["text"]})
                elif block.get("type") == "tool_use":
                    detail = block.get("input", {})
                    shown = str(detail.get("command") or detail.get("file_path") or detail.get("description") or "")
                    first = shown.strip().split("\n")[0]
                    if first != shown.strip() or len(first) > 160:
                        first = first[:160].rstrip() + " …"
                    lines.append({"kind": "tool", "text": f"{block.get('name')} {first}".strip()})
        elif kind == "system" and event.get("subtype") == "permission_denied":
            lines.append({"kind": "denied", "text": event.get("tool_name", "a tool")})
        elif kind == "result":
            cost = event.get("total_cost_usd")
            lines.append({"kind": "turn", "text": "turn ended" + (f" · ${cost:.4f}" if cost is not None else "")})
    return lines[-limit:]


def diff_text(project, review_id):
    review = review_dir(project, review_id)
    return (review / "diff" / f"{review_state.read(review)['head']}.diff").read_text()


def developer_change(project, review_id, action, body):
    """A change the page makes as the developer: `edit`, `status` or `answer`. Raises Refused."""
    review = review_dir(project, review_id)
    if action == "edit":
        return review_state.change(review, "update-finding", body.get("fields") or {}, "developer", body.get("finding"))
    if action == "status":
        return review_state.change(review, "set-status", {"status": body.get("status")}, "developer",
                                   body.get("finding"))
    if action == "answer":
        checkpoint = review_state.read(review).get("checkpoint") or {}
        review_state.change(review, "answer", {"option": body.get("option"), "note": body.get("note")}, "developer")
        return add_message(project, review_id, {"type": "answer", "checkpoint": checkpoint.get("id"),
                                                "option": body.get("option"), "note": body.get("note")})
    raise review_state.Refused(f"unknown change {action!r}")


def add_message(project, review_id, message):
    """Append one request for the review's session to its inbox; returns the message id. Raises Refused."""
    review = review_dir(project, review_id)
    kind = message.get("type")
    if kind not in MESSAGE_FIELDS:
        raise review_state.Refused(f"unknown message type {kind!r}")
    missing = [field for field in MESSAGE_FIELDS[kind] if not message.get(field)]
    if missing:
        raise review_state.Refused(f"a {kind} message needs {', '.join(missing)}")
    with review_state.locked(review):
        inbox = review / "inbox.jsonl"
        count = len(inbox.read_text().splitlines()) if inbox.exists() else 0
        line = {"id": f"m{count + 1}", "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                **{key: value for key, value in message.items() if key != "id"}}
        with inbox.open("a") as out:
            out.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line["id"]


def pending_messages(review):
    inbox = pathlib.Path(review) / "inbox.jsonl"
    if not inbox.exists():
        return []
    handled = set(review_state.read(review).get("handled", []))
    messages = [json.loads(line) for line in inbox.read_text().splitlines() if line.strip()]
    return [message for message in messages if message["id"] not in handled]


def watched(project):
    """The review files whose change should refresh the page."""
    root = reviews_root(project)
    return [root] + sorted(root.glob("*")) + sorted(root.glob("*/review.json")) + sorted(root.glob("*/session.jsonl"))
