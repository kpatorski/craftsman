#!/usr/bin/env python3
"""The one way a review's state changes -- see REVIEW.md.

    review_state.py <review dir> <command> [id] ['<payload JSON>'] [--by agent|developer]

The payload is one argument, in single quotes; an apostrophe inside it is written as \\u0027.

Commands: init, set, add-finding, update-finding <id>, set-status <id>, mark-sent <id>, add-comment,
update-comment <id>, comment-status <id>, comment-sent <id>, use-case-status <id>, open-thread,
reply <thread id>, resolve <thread id>, view, unview, archive, answer, handled <message id>, show.

The agent and the review page change review.json at the same time. Every change takes an exclusive lock, reads the
file fresh, checks the change against REVIEW.md's rules, and replaces the file atomically -- so neither side loses
the other's change, and neither can break a rule the other relies on. A refused change exits 1 with the reason on
stderr and leaves the file as it was. `--by` says who asks; it defaults to the agent.
"""
import datetime
import fcntl
import json
import os
import pathlib
import shutil
import sys
import tempfile
from contextlib import contextmanager

KINDS = ("violation", "new-convention", "scout", "out-of-scope")
WHEN = ("now", "later")
SEVERITY = ("must-fix", "should-fix", "nit")
TEXT_FIELDS = ("title", "description", "comment")
DEVELOPER_FIELDS = TEXT_FIELDS + ("severity",)
AGENT_FIELDS = DEVELOPER_FIELDS + ("category", "locations", "directive", "kind", "when")
SETTABLE = ("source", "checkout", "base", "head", "refreshed", "session", "closed", "language", "scope",
            "requirements", "tickets", "structure", "rules", "checkpoint")
STATUS_BY = {
    "agent": ("maybe-resolved", "merged", "proposed"),
    "developer": ("to-send", "deleted", "proposed"),
}
USE_CASE_STATUS = ("pending", "reviewing", "reviewed")
CHANGES = ("added", "modified", "deleted", "unchanged")
ABOUT = ("review", "finding", "file", "use-case")
COMMENT_STATUS = ("to-send", "deleted")


class Refused(Exception):
    pass


def empty_state(source, base, head, checkout=None):
    return {"source": source, "checkout": checkout, "base": base, "head": head, "refreshed": None, "session": None, "closed": None,
            "language": None, "scope": None, "requirements": None, "tickets": [], "structure": None, "rules": [],
            "checkpoint": None, "findings": [], "comments": [], "threads": [], "viewed": [], "archived": False, "handled": []}


@contextmanager
def locked(review):
    review.mkdir(parents=True, exist_ok=True)
    with open(review / "review.json.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def read(review):
    return json.loads((review / "review.json").read_text())


def write(review, state):
    handle, temp = tempfile.mkstemp(dir=review, prefix=".review.json.")
    with os.fdopen(handle, "w") as out:
        json.dump(state, out, indent=2, ensure_ascii=False)
    os.replace(temp, review / "review.json")


def next_id(items, prefix):
    return prefix + str(1 + max((int(item["id"][len(prefix):]) for item in items), default=0))


def by_id(items, item_id):
    for item in items:
        if item["id"] == item_id:
            return item
    raise Refused(f"no {item_id} in this review")


def check_kind(found):
    if found.get("kind") not in KINDS:
        raise Refused(f"kind must be one of {', '.join(KINDS)}")
    if found["kind"] == "out-of-scope" and found.get("when") not in WHEN:
        raise Refused("an out-of-scope finding needs `when`: now or later")


def check_severity(found):
    if found.get("severity") not in SEVERITY:
        raise Refused(f"severity must be one of {', '.join(SEVERITY)}")


def check_structure(structure):
    """Every use case says what it does, and may say how it worked before the change and how it works after; its flow,
    when given, is calls through the change, each with where it is called from, and the branches they take."""
    for use_case in (structure or {}).get("use-cases", []):
        missing = [field for field in ("id", "name", "says", "entry") if not use_case.get(field)]
        if missing or not isinstance(use_case.get("files"), list):
            raise Refused(f"a use case needs {', '.join(missing or ['files'])}")
        if any(not isinstance(use_case.get(field, ""), str) for field in ("before", "after")):
            raise Refused("a use case's before and after are text")
        if use_case.get("status", "pending") not in USE_CASE_STATUS:
            raise Refused(f"a use case's status must be one of {', '.join(USE_CASE_STATUS)}")
        flow = use_case.get("flow") or {"steps": [], "branches": []}
        for step in flow.get("steps", []):
            if not step.get("call") or not step.get("path") or step.get("change") not in CHANGES:
                raise Refused(f"a flow step needs call, path, and change: one of {', '.join(CHANGES)}")
            called_from = step.get("from", {"path": "-", "line": 1})
            if not isinstance(called_from, dict) or not called_from.get("path") or \
                    not isinstance(called_from.get("line"), int):
                raise Refused("a flow step's from is the path and line of the call")
        for branch in flow.get("branches", []):
            if not branch.get("what") or not isinstance(branch.get("tested"), bool):
                raise Refused("a branch needs what, and tested: true or false")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def not_sent(found):
    if found["status"] == "sent":
        raise Refused(f"{found['id']} is sent; a follow-up is a new finding")


def init(review, payload, by):
    if (review / "review.json").exists():
        raise Refused(f"{review.name} is already in progress; it is resumed, never overwritten")
    (review / "diff").mkdir(parents=True, exist_ok=True)
    diff = pathlib.Path(payload["diff"]).resolve()
    kept = review / "diff" / f"{payload['head']}.diff"
    if pathlib.Path(review).resolve() in diff.parents:
        shutil.move(diff, kept)  # written into the review folder for this: nothing is left behind
    else:
        shutil.copyfile(diff, kept)
    return empty_state(payload["source"], payload["base"], payload["head"], payload.get("checkout")), None


def set_fields(state, payload, by):
    unknown = sorted(set(payload) - set(SETTABLE))
    if unknown:
        raise Refused(f"not settable: {', '.join(unknown)}")
    if "structure" in payload:
        check_structure(payload["structure"])
    state.update(payload)
    return state, None


def add_finding(state, payload, by):
    """The agent's finding names its category and kind; the developer's own needs only what a PR comment needs."""
    required = ("category", "title", "description", "comment", "locations", "kind", "severity") if by == "agent" \
        else ("title", "comment", "locations", "severity")
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise Refused(f"a finding needs {', '.join(missing)}")
    defaults = {"category": "yours", "description": "", "kind": "violation"} if by == "developer" else {}
    found = {"id": next_id(state["findings"], "f"), "directive": None, "when": None, **defaults, **payload, "by": by,
             "status": "proposed", "edited": [], "sent": []}
    check_kind(found)
    check_severity(found)
    state["findings"].append(found)
    return state, found["id"]


def update_finding(state, payload, by, finding_id):
    found = by_id(state["findings"], finding_id)
    not_sent(found)
    allowed = DEVELOPER_FIELDS if by == "developer" else AGENT_FIELDS
    unknown = sorted(set(payload) - set(allowed))
    if unknown:
        raise Refused(f"the {by} cannot change {', '.join(unknown)}")
    if by == "agent":
        protected = sorted(set(payload) & set(found["edited"]))
        if protected:
            raise Refused(f"the developer edited {', '.join(protected)} of {finding_id}; propose a new finding instead")
    found.update(payload)
    if by == "developer":
        found["edited"] = [field for field in DEVELOPER_FIELDS if field in set(found["edited"]) | set(payload)]
    check_kind(found)
    check_severity(found)
    return state, None


def set_status(state, payload, by, finding_id):
    found = by_id(state["findings"], finding_id)
    not_sent(found)
    status = payload.get("status")
    if status not in STATUS_BY[by]:
        raise Refused(f"the {by} cannot set {status}")
    if status == "merged":
        target = payload.get("merged-into")
        if target == finding_id or target not in {other["id"] for other in state["findings"]}:
            raise Refused("a merged finding names the existing finding it went into")
        found["merged-into"] = target
    found["status"] = status
    return state, None


def mark_sent(state, payload, by, finding_id):
    found = by_id(state["findings"], finding_id)
    if found["status"] != "to-send":
        raise Refused(f"only a finding marked to send is sent; {finding_id} is {found['status']}")
    found["sent"] = [{"location": entry["location"], "url": entry["url"]} for entry in payload["sent"]]
    found["status"] = "sent"
    return state, None


def developers_comment(by):
    if by != "developer":
        raise Refused("a comment on the pull request is the developer's")


def comment_text(payload):
    body = (payload.get("body") or "").strip()
    if not body:
        raise Refused("a comment needs text")
    return body


def add_comment(state, payload, by):
    """A comment on the whole pull request, or a reply in a thread on GitHub: `reply-to` is the id of the thread's
    first comment. It waits for Send."""
    developers_comment(by)
    reply_to = payload.get("reply-to")
    if reply_to is not None and (not isinstance(reply_to, int) or isinstance(reply_to, bool)):
        raise Refused("reply-to is the id of a comment on GitHub")
    comments = state.setdefault("comments", [])
    comment = {"id": next_id(comments, "c"), "body": comment_text(payload), "reply-to": reply_to,
               "status": "to-send", "url": None, "at": now()}
    comments.append(comment)
    return state, comment["id"]


def unsent_comment(state, comment_id):
    comment = by_id(state.setdefault("comments", []), comment_id)
    if comment["status"] == "sent":
        raise Refused(f"{comment_id} is sent; a follow-up is a new comment")
    return comment


def update_comment(state, payload, by, comment_id):
    developers_comment(by)
    unsent_comment(state, comment_id)["body"] = comment_text(payload)
    return state, None


def comment_status(state, payload, by, comment_id):
    developers_comment(by)
    if payload.get("status") not in COMMENT_STATUS:
        raise Refused(f"a comment's status is one of {', '.join(COMMENT_STATUS)}")
    unsent_comment(state, comment_id)["status"] = payload["status"]
    return state, None


def comment_sent(state, payload, by, comment_id):
    comment = by_id(state.setdefault("comments", []), comment_id)
    if comment["status"] != "to-send":
        raise Refused(f"only a comment waiting for Send is sent; {comment_id} is {comment['status']}")
    comment.update(status="sent", url=payload["url"])
    return state, None


def check_about(state, about):
    kind = (about or {}).get("kind")
    if kind not in ABOUT:
        raise Refused(f"a thread is about one of {', '.join(ABOUT)}")
    if kind == "finding":
        by_id(state["findings"], about.get("id"))
    if kind == "use-case":
        by_id((state.get("structure") or {}).get("use-cases", []), about.get("id"))
    if kind == "file" and not about.get("path"):
        raise Refused("a thread about a file names its path")


def message(payload, by):
    if not payload.get("text"):
        raise Refused("a message needs text")
    return {"by": by, "at": now(), "text": payload["text"]}


def open_thread(state, payload, by):
    """A question the developer asks about a part of the review, or a note the agent writes unasked."""
    check_about(state, payload.get("about"))
    threads = state.setdefault("threads", [])
    thread = {"id": next_id(threads, "t"), "about": payload["about"], "quote": payload.get("quote"),
              "status": "open", "messages": [message(payload, by)]}
    threads.append(thread)
    return state, thread["id"]


def reply(state, payload, by, thread_id):
    thread = by_id(state.setdefault("threads", []), thread_id)
    thread["messages"].append(message(payload, by))
    if by == "developer":
        thread["status"] = "open"
    return state, None


def resolve(state, payload, by, thread_id):
    if by != "developer":
        raise Refused("a thread is resolved by the developer")
    by_id(state.setdefault("threads", []), thread_id)["status"] = "resolved"
    return state, None


def view(state, payload, by):
    if by != "developer":
        raise Refused("files are marked viewed by the developer")
    viewed = state.setdefault("viewed", [])
    if payload.get("path") and payload["path"] not in viewed:
        viewed.append(payload["path"])
    return state, None


def unview(state, payload, by):
    if by != "developer":
        raise Refused("files are marked viewed by the developer")
    state["viewed"] = [path for path in state.get("viewed", []) if path != payload.get("path")]
    return state, None


def archive(state, payload, by):
    if by != "developer":
        raise Refused("a review is archived by the developer")
    state["archived"] = bool(payload.get("archived"))
    return state, None


def use_case_status(state, payload, by, use_case_id):
    if payload.get("status") not in USE_CASE_STATUS:
        raise Refused(f"status must be one of {', '.join(USE_CASE_STATUS)}")
    by_id((state.get("structure") or {}).get("use-cases", []), use_case_id)["status"] = payload["status"]
    return state, None


def answer(state, payload, by):
    if by != "developer":
        raise Refused("a checkpoint is answered by the developer")
    if not state.get("checkpoint"):
        raise Refused("no checkpoint is open")
    state["checkpoint"]["answer"] = {"option": payload["option"], "note": payload.get("note"), "by": by}
    return state, None


def handled(state, payload, by, message_id):
    if message_id not in state["handled"]:
        state["handled"].append(message_id)
    return state, None


COMMANDS = {"set": set_fields, "add-finding": add_finding, "add-comment": add_comment, "open-thread": open_thread,
            "view": view, "unview": unview, "archive": archive, "answer": answer}
COMMANDS_WITH_ID = {"update-finding": update_finding, "set-status": set_status, "mark-sent": mark_sent,
                    "update-comment": update_comment, "comment-status": comment_status,
                    "comment-sent": comment_sent, "use-case-status": use_case_status, "reply": reply,
                    "resolve": resolve, "handled": handled}


def change(review, command, payload=None, by="agent", item_id=None):
    """Apply one command under the lock; returns what the command prints (a new id), or None. Raises Refused."""
    review = pathlib.Path(review)
    with locked(review):
        if command == "init":
            state, result = init(review, payload, by)
        else:
            if command in COMMANDS_WITH_ID:
                if item_id is None:
                    raise Refused(f"{command} needs an id")
                state, result = COMMANDS_WITH_ID[command](read(review), payload or {}, by, item_id)
            elif command in COMMANDS:
                state, result = COMMANDS[command](read(review), payload or {}, by)
            else:
                raise Refused(f"unknown command {command}")
        write(review, state)
        return result


def main(argv):
    args = list(argv)
    by = "agent"
    if "--by" in args:
        at = args.index("--by")
        by = args[at + 1]
        del args[at:at + 2]
    if len(args) < 2 or by not in STATUS_BY:
        print(__doc__, file=sys.stderr)
        return 2
    review, command, rest = pathlib.Path(args[0]), args[1], args[2:]
    if command == "show":
        print(json.dumps(read(review), indent=2, ensure_ascii=False))
        return 0
    payload = rest.pop() if rest and rest[-1].lstrip().startswith("{") else None
    try:
        result = change(review, command, json.loads(payload) if payload else None, by, rest[0] if rest else None)
    except Refused as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 1
    if result:
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
