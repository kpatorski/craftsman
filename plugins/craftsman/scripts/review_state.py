#!/usr/bin/env python3
"""The one way a review's state changes -- see REVIEW.md.

    review_state.py <review dir> <command> [id] [--by agent|developer]   (the payload, if any, as JSON on stdin)

Commands: init, set, add-finding, update-finding <id>, set-status <id>, mark-sent <id>, add-replies <id>,
add-explanation, update-explanation <id>, use-case-status <id>, answer, handled <message id>, show.

The agent and the review page change review.json at the same time. Every change takes an exclusive lock, reads the
file fresh, checks the change against REVIEW.md's rules, and replaces the file atomically -- so neither side loses
the other's change, and neither can break a rule the other relies on. A refused change exits 1 with the reason on
stderr and leaves the file as it was. `--by` says who asks; it defaults to the agent.
"""
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
TEXT_FIELDS = ("title", "description", "comment")
AGENT_FIELDS = TEXT_FIELDS + ("category", "locations", "directive", "kind", "when")
SETTABLE = ("source", "base", "head", "refreshed", "session", "closed", "language", "scope", "requirements", "tickets",
            "structure", "rules", "map", "checkpoint")
STATUS_BY = {
    "agent": ("maybe-resolved", "merged", "proposed"),
    "developer": ("to-send", "deleted", "proposed"),
}
USE_CASE_STATUS = ("pending", "reviewing", "reviewed")
EXPLANATION_STATUS = ("pending", "ready")


class Refused(Exception):
    pass


def empty_state(source, base, head):
    return {"source": source, "base": base, "head": head, "refreshed": None, "session": None, "closed": None,
            "language": None, "scope": None, "requirements": None, "tickets": [], "structure": None, "rules": [],
            "map": [], "explanations": [], "checkpoint": None, "findings": [], "handled": []}


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


def not_sent(found):
    if found["status"] == "sent":
        raise Refused(f"{found['id']} is sent; a follow-up is a new finding")


def init(review, payload, by):
    if (review / "review.json").exists():
        raise Refused(f"{review.name} is already in progress; it is resumed, never overwritten")
    (review / "diff").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(payload["diff"], review / "diff" / f"{payload['head']}.diff")
    return empty_state(payload["source"], payload["base"], payload["head"]), None


def set_fields(state, payload, by):
    unknown = sorted(set(payload) - set(SETTABLE))
    if unknown:
        raise Refused(f"not settable: {', '.join(unknown)}")
    state.update(payload)
    return state, None


def add_finding(state, payload, by):
    missing = [field for field in ("category", "title", "description", "comment", "locations", "kind")
               if not payload.get(field)]
    if missing:
        raise Refused(f"a finding needs {', '.join(missing)}")
    check_kind(payload)
    found = {"id": next_id(state["findings"], "f"), "directive": None, "when": None, **payload,
             "status": "proposed", "edited": [], "sent": []}
    state["findings"].append(found)
    return state, found["id"]


def update_finding(state, payload, by, finding_id):
    found = by_id(state["findings"], finding_id)
    not_sent(found)
    allowed = TEXT_FIELDS if by == "developer" else AGENT_FIELDS
    unknown = sorted(set(payload) - set(allowed))
    if unknown:
        raise Refused(f"the {by} cannot change {', '.join(unknown)}")
    if by == "agent":
        protected = sorted(set(payload) & set(found["edited"]))
        if protected:
            raise Refused(f"the developer edited {', '.join(protected)} of {finding_id}; propose a new finding instead")
    found.update(payload)
    if by == "developer":
        found["edited"] = [field for field in TEXT_FIELDS if field in set(found["edited"]) | set(payload)]
    check_kind(found)
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
    found["sent"] = [{"replies": [], **entry} for entry in payload["sent"]]
    found["status"] = "sent"
    return state, None


def add_replies(state, payload, by, finding_id):
    found = by_id(state["findings"], finding_id)
    entry = next((sent for sent in found["sent"] if sent["location"] == payload["location"]), None)
    if entry is None:
        raise Refused(f"{finding_id} has no comment sent for location {payload['location']}")
    known = {(reply["author"], reply["at"]) for reply in entry["replies"]}
    entry["replies"] += [reply for reply in payload["replies"] if (reply["author"], reply["at"]) not in known]
    return state, None


def add_explanation(state, payload, by):
    explanation = {"id": next_id(state["explanations"], "e"), "about": payload["about"],
                   "origin": payload.get("origin", "requested"), "body": payload.get("body"),
                   "status": payload.get("status", "pending")}
    state["explanations"].append(explanation)
    return state, explanation["id"]


def update_explanation(state, payload, by, explanation_id):
    explanation = by_id(state["explanations"], explanation_id)
    if payload.get("status", explanation["status"]) not in EXPLANATION_STATUS:
        raise Refused(f"status must be one of {', '.join(EXPLANATION_STATUS)}")
    explanation.update({key: payload[key] for key in ("body", "status") if key in payload})
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


NO_PAYLOAD = ("handled",)
COMMANDS = {"set": set_fields, "add-finding": add_finding, "add-explanation": add_explanation, "answer": answer}
COMMANDS_WITH_ID = {"update-finding": update_finding, "set-status": set_status, "mark-sent": mark_sent,
                    "add-replies": add_replies, "update-explanation": update_explanation,
                    "use-case-status": use_case_status, "handled": handled}


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
    raw = sys.stdin.read() if command not in NO_PAYLOAD and not sys.stdin.isatty() else ""
    try:
        result = change(review, command, json.loads(raw) if raw.strip() else None, by, rest[0] if rest else None)
    except Refused as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 1
    if result:
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
