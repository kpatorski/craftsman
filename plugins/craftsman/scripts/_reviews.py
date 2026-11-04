"""The review side of the dashboard: listing the reviews in the craftsman home, the changes the page makes as the developer, and
the inbox through which the page's requests reach the review's session -- see REVIEW.md."""
import datetime
import json
import os
import pathlib
import re

import github_conversation
import review_state
from _markdown import render_markdown

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MESSAGE_FIELDS = {"answer": ("checkpoint", "option"), "refresh": (), "ask": ("thread",), "close": ()}
DIFF_HEADER = re.compile(r"^diff --git a/(.*) b/(.*)$")


# github.com or a GitHub Enterprise host
PULL_REQUEST = re.compile(r"^https://(?P<host>[^/\s]+)/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/pull/(?P<number>\d+)/?$")
BRANCHES = re.compile(r"^([^\s:]+):([^\s:]+)$")


def review_id_for(source, checkout=None):
    """Unique across every repository: `<owner>-<repo>-pr-<number>` for a pull request URL; for two branches,
    `<checkout folder>-<target>..<source>` with `/` replaced by `-`."""
    pull = PULL_REQUEST.match(source or "")
    if pull:
        return f"{pull['owner']}-{pull['repo']}-pr-{pull['number']}"
    branches = BRANCHES.match(source or "")
    if branches and checkout:
        return f"{pathlib.Path(checkout).name}-{branches.group(1)}..{branches.group(2)}".replace("/", "-")
    if branches:
        raise review_state.Refused("two branches are reviewed in a local checkout; name it")
    raise review_state.Refused(f"not a pull request URL or <target>:<source>: {source!r}")


def home():
    """The craftsman home, `~/.craftsman`; `CRAFTSMAN_HOME` moves it (the tests do)."""
    return pathlib.Path(os.environ.get("CRAFTSMAN_HOME") or pathlib.Path.home() / ".craftsman")


def reviews_root():
    return home() / "reviews"


def review_dir(review_id):
    review = reviews_root() / (review_id or "")
    if not ID.match(review_id or "") or not (review / "review.json").is_file():
        raise review_state.Refused(f"no review {review_id!r}")
    return review


def list_reviews():
    listed = []
    for state_file in sorted(reviews_root().glob("*/review.json")):
        try:
            state = json.loads(state_file.read_text())
        except (OSError, ValueError):
            continue
        counts = {}
        for found in state.get("findings", []):
            counts[found["status"]] = counts.get(found["status"], 0) + 1
        listed.append({"id": state_file.parent.name, "checkout": state.get("checkout"), "source": state.get("source"),
                       "head": state.get("head"), "closed": state.get("closed"), "findings": counts,
                       "archived": bool(state.get("archived")),
                       "checkpoint": bool(state.get("checkpoint") and not state["checkpoint"].get("answer"))})
    return listed


def read_review(review_id):
    """The state, plus what the server works out from the diff: every changed file with how it changed, which use
    cases it belongs to and whether the developer viewed it, and the files no use case reaches; and the conversation
    last read from the pull request, or None."""
    review = review_dir(review_id)
    state = review_state.read(review)
    use_cases = (state.get("structure") or {}).get("use-cases", [])
    viewed = set(state.get("viewed", []))
    files = [{**changed, "use-cases": [u["id"] for u in use_cases if changed["path"] in u.get("files", [])],
              "viewed": changed["path"] in viewed} for changed in changed_files(diff_text(review_id))]
    conversation = github_conversation.read(review)
    return {"state": state, "pending": len(pending_messages(review)), "html": rendered(state, conversation),
            "github": conversation,
            "console": console_lines(review), "files": files,
            "untied": [changed["path"] for changed in files if not changed["use-cases"]]}


def rendered(state, conversation=None):
    """Every markdown text of the review and of its conversation on GitHub as HTML, keyed the way the page looks it
    up. The renderer escapes HTML, so what others wrote on GitHub shows as text."""
    texts = {"scope": state.get("scope"), "requirements": state.get("requirements")}
    for found in state.get("findings", []):
        for field in ("description", "comment"):
            texts[f"finding:{found['id']}:{field}"] = found.get(field)
    for comment in state.get("comments", []):
        texts[f"comment:{comment['id']}"] = comment.get("body")
    for comment in (conversation or {}).get("comments", []):
        texts[f"github:{comment['id']}"] = comment.get("body")
    for thread in state.get("threads", []):
        for number, said in enumerate(thread["messages"]):
            texts[f"thread:{thread['id']}:{number}"] = said.get("text")
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


def diff_text(review_id, path=None):
    """The diff of the reviewed head; with `path`, only that file's part of it."""
    review = review_dir(review_id)
    text = (review / "diff" / f"{review_state.read(review)['head']}.diff").read_text()
    if path is None:
        return text
    return "".join("".join(part) for header, part in file_parts(text) if path in header)


def file_parts(text):
    """The diff cut into one part per file: ((old path, new path), the part's lines)."""
    parts = []
    for line in text.splitlines(keepends=True):
        header = DIFF_HEADER.match(line.rstrip("\n"))
        if header:
            parts.append((header.groups(), []))
        if parts:
            parts[-1][1].append(line)
    return parts


def changed_files(text):
    """Every file the diff changes: its path, `added`, `modified`, `deleted` or `renamed` (with `from`), and how many
    lines it adds and removes."""
    files = []
    for (old, new), lines in file_parts(text):
        heading = "".join(line for line in lines if not line.startswith(("+", "-", " ", "@@")))
        change = ("added" if "new file mode" in heading else "deleted" if "deleted file mode" in heading
                  else "renamed" if "rename from" in heading else "modified")
        body = [line for line in lines if not line.startswith(("+++", "---"))]
        changed = {"path": old if change == "deleted" else new, "change": change,
                   "added": sum(line.startswith("+") for line in body),
                   "removed": sum(line.startswith("-") for line in body)}
        if change == "renamed":
            changed["from"] = old
        files.append(changed)
    return files


def references(review_id, path, limit=50):
    """Where the reviewed code still names a deleted file's class or module: `path:line` in the review's worktree."""
    review = review_dir(review_id)
    worktree = review / "worktree"
    name = re.compile(r"\b" + re.escape(pathlib.PurePath(path).stem) + r"\b")
    found = []
    for candidate in sorted(worktree.rglob("*")) if worktree.is_dir() else []:
        if not candidate.is_file() or ".git" in candidate.relative_to(worktree).parts:
            continue
        try:
            lines = candidate.read_text().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        found += [f"{candidate.relative_to(worktree)}:{number}" for number, line in enumerate(lines, 1)
                  if name.search(line)]
        if len(found) >= limit:
            break
    return found[:limit]


def developer_change(review_id, action, body):
    """A change the page makes as the developer. A question or a reply in a thread also goes to the inbox, so the
    review's session answers it. Raises Refused."""
    review = review_dir(review_id)
    if action == "add-finding":
        return review_state.change(review, "add-finding", body.get("fields") or {}, "developer")
    if action == "ask":
        thread = review_state.change(review, "open-thread", {key: body.get(key) for key in ("about", "quote", "text")},
                                     "developer")
        add_message(review_id, {"type": "ask", "thread": thread})
        return thread
    if action == "reply":
        review_state.change(review, "reply", {"text": body.get("text")}, "developer", body.get("thread"))
        return add_message(review_id, {"type": "ask", "thread": body.get("thread")})
    if action == "resolve":
        return review_state.change(review, "resolve", {}, "developer", body.get("thread"))
    if action in ("view", "unview"):
        return review_state.change(review, action, {"path": body.get("path")}, "developer")
    if action == "archive":
        return review_state.change(review, "archive", {"archived": body.get("archived")}, "developer")
    if action == "edit":
        return review_state.change(review, "update-finding", body.get("fields") or {}, "developer", body.get("finding"))
    if action == "status":
        return review_state.change(review, "set-status", {"status": body.get("status")}, "developer",
                                   body.get("finding"))
    if action == "add-comment":
        return review_state.change(review, "add-comment", {"body": body.get("body"), "reply-to": body.get("reply-to")},
                                   "developer")
    if action == "edit-comment":
        return review_state.change(review, "update-comment", {"body": body.get("body")}, "developer",
                                   body.get("comment"))
    if action == "comment-status":
        return review_state.change(review, "comment-status", {"status": body.get("status")}, "developer",
                                   body.get("comment"))
    if action == "answer":
        checkpoint = review_state.read(review).get("checkpoint") or {}
        review_state.change(review, "answer", {"option": body.get("option"), "note": body.get("note")}, "developer")
        return add_message(review_id, {"type": "answer", "checkpoint": checkpoint.get("id"),
                                                "option": body.get("option"), "note": body.get("note")})
    raise review_state.Refused(f"unknown change {action!r}")


def add_message(review_id, message):
    """Append one request for the review's session to its inbox; returns the message id. Raises Refused."""
    review = review_dir(review_id)
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


def watched():
    """The review files whose change should refresh the page."""
    root = reviews_root()
    return [root] + sorted(root.glob("*")) + sorted(root.glob("*/review.json")) + sorted(root.glob("*/session.jsonl"))
