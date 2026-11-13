#!/usr/bin/env python3
"""The mechanical part of bringing a review up to date with its pull request or branches -- see REVIEW.md,
"Refreshing a review", and the code-review bundle's `refresh-review` protocol, which weighs what this prints.

    refresh_review.py <review dir>

1. fetch the pull request or the branches again, as opening the review did, without touching the developer's
   working tree, and read the pull request's description;
2. read the pull request's conversation again (github_conversation.py); a GitHub that does not answer is named, not
   fatal;
3. when the head has not moved, record the time of the refresh and stop;
4. otherwise move the review's worktree to the new head, write the diff from where the change branched off, move the
   review state to it (`refresh`), and put every use case with a file the new commits changed back to `pending`.

It prints one JSON object: `moved`, `old-head`, `head`, `base`, `commits` (how many are new), `changed-files` (what
the new commits changed), `back-to-pending` (the use cases), `unplaced` (changed files in no use case yet),
`description` (the pull request's, or null), and `github` (`error`, and `new`: the comments dated after the last
refresh). Exits 1, saying why, when the review cannot be refreshed.
"""
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _open_review  # noqa: E402
import github_conversation  # noqa: E402
import review_state  # noqa: E402
from _open_review import git  # noqa: E402
from review_state import Refused  # noqa: E402


def source_text(source):
    if source.get("kind") == "pull-request":
        return source["url"]
    return f"{source['target']}:{source['source']}"


def has_pull_request(source):
    return source.get("kind") == "pull-request" or bool(source.get("pull-request"))


def read_conversation(review, since, gh):
    try:
        conversation = github_conversation.fetch(review, gh=gh)
    except (Refused, RuntimeError) as failure:
        return {"error": str(failure), "new": 0}
    new = [c for c in conversation.get("comments", []) if not since or (c.get("at") or "") > since]
    return {"error": conversation.get("error"), "new": len(new)}


def refresh(review, gh=None):
    review = pathlib.Path(review)
    gh = gh or _open_review.gh_command()
    state = review_state.read(review)
    checkout, old_head = pathlib.Path(state["checkout"]), state["head"]
    since = _iso(state.get("refreshed"))
    _, target, head, description = _open_review.read_source(source_text(state["source"]), checkout, gh)
    github = read_conversation(review, since, gh) if has_pull_request(state["source"]) else None
    report = {"moved": head != old_head, "old-head": old_head, "head": head, "base": state["base"], "commits": 0,
              "changed-files": [], "back-to-pending": [], "unplaced": [], "description": description,
              "github": github}
    if head == old_head:
        review_state.change(review, "set", {"refreshed": _now()})
        return report
    worktree = review / "worktree"
    moved = git("checkout", "-q", "--detach", head, cwd=worktree)
    if moved.returncode != 0:
        raise Refused(f"the review's worktree could not move to {head[:12]}: {moved.stderr.strip()}")
    base = _open_review.merge_base(target, head, checkout, source_text(state["source"]))
    diff = review / "refresh.diff"
    written = git("diff", f"--output={diff}", base, head, cwd=checkout)
    if written.returncode != 0:
        raise Refused(f"the diff {base[:12]}...{head[:12]} could not be written: {written.stderr.strip()}")
    review_state.change(review, "refresh", {"base": base, "head": head, "diff": str(diff)})
    changed = sorted(filter(None, git("diff", "--name-only", old_head, head, cwd=checkout).stdout.splitlines()))
    use_cases = (review_state.read(review).get("structure") or {}).get("use-cases", [])
    touched = [u["id"] for u in use_cases if set(u.get("files", [])) & set(changed)]
    for use_case in touched:
        review_state.change(review, "use-case-status", {"status": "pending"}, item_id=use_case)
    placed = {path for u in use_cases for path in u.get("files", [])}
    count = git("rev-list", "--count", f"{old_head}..{head}", cwd=checkout).stdout.strip()
    report.update(base=base, commits=int(count or 0), **{"changed-files": changed, "back-to-pending": touched,
                                                        "unplaced": [path for path in changed if path not in placed]})
    return report


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _iso(stamp):
    """A refresh time as GitHub writes its own (`2026-11-02T09:00:00Z`), so the two compare as text."""
    if not stamp:
        return None
    return datetime.datetime.fromisoformat(stamp).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv):
    if len(argv) != 1:
        sys.exit(__doc__.split("\n\n")[1])
    try:
        print(json.dumps(refresh(argv[0])))
    except Refused as refused:
        sys.exit(f"refresh_review: {refused}")


if __name__ == "__main__":
    main(sys.argv[1:])
