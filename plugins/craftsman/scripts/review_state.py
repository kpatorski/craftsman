#!/usr/bin/env python3
"""The one way a review's state changes -- see REVIEW.md.

    review_state.py <review dir> <command> [id] ['<payload JSON>'] [--by agent|developer]

The payload is one argument, in single quotes; an apostrophe inside it is written as \\u0027.

Commands: init, refresh, set, add-finding, update-finding <id>, set-status <id>, mark-sent <id>, add-comment,
update-comment <id>, comment-status <id>, comment-sent <id>, use-case-status <id>, open-thread,
reply <thread id>, resolve <thread id>, view, unview, archive, answer, handled <message id>,
switch-directive, clear-directive-switches, record-check, add-context, remove-context <id>,
in-prompt <id>, save-draft,
discard-draft, draft-to-finding, show.

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
import re
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
SETTABLE = ("source", "checkout", "refreshed", "session", "closed", "language", "scope",
            "requirements", "tickets", "structure", "rules", "checkpoint")
STATUS_BY = {
    "agent": ("maybe-resolved", "merged", "proposed"),
    "developer": ("to-send", "deleted", "proposed"),
}
USE_CASE_STATUS = ("pending", "reviewing", "reviewed")
CHECK_RESULT = ("findings", "clean", "not-applicable", "failed")
UNTIED = "untied"  # the changed files no use case reaches, reviewed together as a use case of their own
CHANGES = ("added", "modified", "deleted", "unchanged")
ABOUT = ("review", "finding", "file", "use-case")
COMMENT_STATUS = ("to-send", "deleted")


class Refused(Exception):
    pass


def empty_state(source, base, head, checkout=None):
    return {"source": source, "checkout": checkout, "base": base, "head": head, "refreshed": None, "session": None, "closed": None,
            "language": None, "scope": None, "requirements": None, "tickets": [], "structure": None, "rules": [],
            "checkpoint": None, "findings": [], "comments": [], "threads": [], "viewed": [], "archived": False, "handled": [],
            "directive-switches": {}, "checks": [], "context": [], "drafts": {}}


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
    state = empty_state(payload["source"], payload["base"], payload["head"], payload.get("checkout"))
    given = review / "context.md"  # what the developer gave when starting the review, before review.json existed
    if given.is_file():
        text = given.read_text().strip()
        state["context"] = [{"id": "x1", "text": text, "at": now()}] if text else []
        given.unlink()
    return state, None


def file_changes(text):
    """Each file of a diff and its change, by the file's path; the line numbers of hunks and the blob ids left out, so
    a change that only moved on a new base stays the same change."""
    changes, path = {}, None
    for line in text.splitlines():
        if line.startswith("diff --git "):
            path = line.rsplit(" b/", 1)[-1]
            changes[path] = []
        elif path is not None and not line.startswith("index "):
            changes[path].append("@@" if line.startswith("@@") else line)
    return changes


def refresh(review, payload, by):
    """The review moves to a new base and head with the diff between them; a file whose change differs from the one
    the developer viewed is not viewed any more."""
    if by != "agent":
        raise Refused("a review is refreshed by the agent")
    state = read(review)
    diff = pathlib.Path(payload["diff"]).resolve()
    if not diff.is_file():
        raise Refused(f"no diff at {diff}")
    before = file_changes((review / "diff" / f"{state['head']}.diff").read_text())
    after = file_changes(diff.read_text())
    kept = review / "diff" / f"{payload['head']}.diff"
    if pathlib.Path(review).resolve() in diff.parents:
        shutil.move(diff, kept)
    else:
        shutil.copyfile(diff, kept)
    state.update(base=payload["base"], head=payload["head"], refreshed=now())
    state["viewed"] = [path for path in state.get("viewed", []) if path in after and after[path] == before.get(path)]
    return state, None


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


def in_prompt(state, payload, by, finding_id):
    """The developer leaves a finding in the fix prompts, or out of them; it can change after the finding is sent."""
    if by != "developer":
        raise Refused("what goes in the fix prompts is the developer's choice")
    if not isinstance(payload.get("included"), bool):
        raise Refused("in-prompt says `included`, true or false")
    by_id(state["findings"], finding_id)["in-prompt"] = payload["included"]
    return state, None


def drafts_of(state, payload, by):
    """The developer's drafts of findings, one per file; a draft is about the selected lines, or the whole file."""
    if by != "developer":
        raise Refused("a draft of a finding is the developer's")
    if not payload.get("path"):
        raise Refused("a draft names the file it is about")
    return state.setdefault("drafts", {})


def save_draft(state, payload, by):
    drafts = drafts_of(state, payload, by)
    lines = payload.get("lines")
    if lines is not None and not (isinstance(lines, list) and len(lines) == 2 and all(isinstance(n, int) for n in lines)):
        raise Refused("a draft's lines are [first, last]")
    drafts[payload["path"]] = {"text": payload.get("text") or "", "lines": lines,
                               "side": payload.get("side") or "RIGHT", "at": now()}
    return state, None


def discard_draft(state, payload, by):
    drafts_of(state, payload, by).pop(payload["path"], None)
    return state, None


def title_of(text, longest=80):
    """A finding's title from its comment: the first sentence of its first line of prose, without markdown marks."""
    prose, fenced = "", False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and line.strip():
            prose = line.strip()
            break
    plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", prose)
    plain = re.sub(r"[*_`#>]+", "", plain).lstrip("-+ ").strip()
    sentence = re.split(r"(?<=[.!?])\s", plain, maxsplit=1)[0].rstrip(".!?:; ")
    return sentence if len(sentence) <= longest else sentence[:longest - 1].rsplit(" ", 1)[0] + "…"


def draft_to_finding(state, payload, by):
    """The draft becomes the developer's finding, on the last line it is about, or on the whole file, and is gone."""
    drafts = drafts_of(state, payload, by)
    draft = drafts.get(payload["path"])
    if not draft or not draft["text"].strip():
        raise Refused(f"no draft about {payload['path']} to make a finding of")
    lines = draft.get("lines")
    location = {"path": payload["path"], "line": lines[1] if lines else None, "side": draft.get("side") or "RIGHT",
                "commit": state["head"]}
    if payload.get("repeats"):
        # the same problem as a finding already there: this place joins it
        found = by_id(state["findings"], payload["repeats"])
        not_sent(found)
        place = lambda l: (l["path"], l.get("line"), l.get("side", "RIGHT"))  # noqa: E731
        if place(location) not in map(place, found["locations"]):
            found["locations"].append(location)
        del drafts[payload["path"]]
        return state, found["id"]
    fields = {key: payload[key] for key in ("title", "severity", "comment", "category", "description")
              if payload.get(key)}
    fields.setdefault("title", title_of(fields.get("comment") or draft["text"])
                      or f"About {payload['path'].rsplit('/', 1)[-1]}")
    state, made = add_finding(state, {"comment": draft["text"].strip(), **fields, "locations": [location]}, by)
    del drafts[payload["path"]]
    return state, made


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


def switch_directive(state, payload, by):
    """The developer switches a directive on or off for this review; the workshop's switch stays as it is."""
    if by != "developer":
        raise Refused("a directive is switched for a review by the developer")
    if not payload.get("id") or not isinstance(payload.get("on"), bool):
        raise Refused("a switch names a directive `id` and says `on`, true or false")
    state.setdefault("directive-switches", {})[payload["id"]] = payload["on"]
    return state, None


def clear_directive_switches(state, payload, by):
    """The review's own switches go once the developer made its set the default for every review."""
    if by != "developer":
        raise Refused("a directive is switched for a review by the developer")
    state["directive-switches"] = {}
    return state, None


def record_check(state, payload, by):
    """What one directive found in one use case, or a list of such checks, all recorded or none; a later check of
    the same pair replaces it."""
    if by != "agent":
        raise Refused("a check is recorded by the agent")
    use_cases = [u["id"] for u in (state.get("structure") or {}).get("use-cases", [])] + [UNTIED]
    for check in payload if isinstance(payload, list) else [payload]:
        if check.get("use-case") not in use_cases:
            raise Refused(f"no use case {check.get('use-case')!r}")
        if not check.get("directive"):
            raise Refused("a check names its directive")
        if check.get("result") not in CHECK_RESULT:
            raise Refused(f"result must be one of {', '.join(CHECK_RESULT)}")
        pair = (check["use-case"], check["directive"])
        state["checks"] = [c for c in state.get("checks", []) if (c["use-case"], c["directive"]) != pair] + [
            {"use-case": pair[0], "directive": pair[1], "result": check["result"], "note": check.get("note"),
             "at": now()}]
    return state, None


def context_notes(state):
    """The developer's notes of context; a review that kept one text as its context has it as its first note."""
    kept = state.get("context")
    if isinstance(kept, str):
        return [{"id": "x1", "text": kept, "at": None}]
    return list(kept or [])


def add_context(state, payload, by):
    """A note on what the pull request does not say, from the developer to the agent; prints its id."""
    if by != "developer":
        raise Refused("the context of a review is the developer's")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise Refused("a note of context has text")
    notes = context_notes(state)
    note = {"id": next_id(notes, "x"), "text": text, "at": now()}
    state["context"] = notes + [note]
    return state, note["id"]


def remove_context(state, payload, by, note_id):
    if by != "developer":
        raise Refused("the context of a review is the developer's")
    notes = context_notes(state)
    if note_id not in [n["id"] for n in notes]:
        raise Refused(f"no note of context {note_id!r}")
    state["context"] = [n for n in notes if n["id"] != note_id]
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
            "view": view, "unview": unview, "archive": archive, "answer": answer,
            "switch-directive": switch_directive, "clear-directive-switches": clear_directive_switches,
            "record-check": record_check, "add-context": add_context, "save-draft": save_draft,
            "discard-draft": discard_draft, "draft-to-finding": draft_to_finding}
COMMANDS_WITH_ID = {"update-finding": update_finding, "set-status": set_status, "mark-sent": mark_sent,
                    "update-comment": update_comment, "comment-status": comment_status,
                    "comment-sent": comment_sent, "use-case-status": use_case_status, "reply": reply,
                    "resolve": resolve, "handled": handled, "remove-context": remove_context,
                    "in-prompt": in_prompt}


def change(review, command, payload=None, by="agent", item_id=None):
    """Apply one command under the lock; returns what the command prints (a new id), or None. Raises Refused."""
    review = pathlib.Path(review)
    with locked(review):
        if command == "init":
            state, result = init(review, payload, by)
        elif command == "refresh":
            state, result = refresh(review, payload or {}, by)
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
    payload = rest.pop() if rest and rest[-1].lstrip().startswith(("{", "[")) else None
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
