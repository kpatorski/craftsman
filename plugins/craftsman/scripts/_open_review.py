"""Opening a review, done by the dashboard server before the review's session starts -- see REVIEW.md, "Opening a
review". Every step is mechanical, so none of it is left to the model:

1. read the source: a pull request from GitHub (`gh api`), or two branches -- each must exist in the checkout or on
   `origin` -- and the open pull request of the source branch, if there is one;
2. leave a review already opened as it is: it is resumed, never overwritten;
3. fetch what is reviewed from `origin`, without touching the developer's working tree;
4. make the review's worktree at the reviewed commit;
5. write the diff from where the change branched off, and the review state with it.

What needs judgement -- the language of the comments, and everything after -- is the session's.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import review_state
from review_state import Refused
from _reviews import PULL_REQUEST

REMOTE = re.compile(r"(?:^[^@/]+@(?P<ssh_host>[^:]+):|^[a-z+]+://(?:[^@/]+@)?(?P<host>[^/:]+)(?::\d+)?/)"
                    r"(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")


def gh_command():
    return os.environ.get("CRAFTSMAN_GH", "gh").split()


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def gh_api(gh, endpoint, host):
    done = subprocess.run(list(gh) + ["api", endpoint], capture_output=True, text=True, timeout=60,
                          env={**os.environ, "GH_HOST": host})
    if done.returncode != 0:
        raise Refused(f"GitHub did not answer for {endpoint}: {(done.stderr or done.stdout).strip()}")
    return json.loads(done.stdout)


def as_source(pull, repository):
    return {"kind": "pull-request", "url": pull["html_url"], "repository": repository, "number": pull["number"],
            "title": pull["title"], "base-branch": pull["base"]["ref"], "head-branch": pull["head"]["ref"]}


def commit(checkout, *names):
    """The commit of the first name that is one in the checkout, or None."""
    for name in names:
        found = git("rev-parse", "--verify", "--quiet", f"{name}^{{commit}}", cwd=checkout)
        if found.returncode == 0:
            return found.stdout.strip()
    return None


def origin_repository(checkout):
    """(host, "owner/repo") of the checkout's `origin`, or None."""
    url = git("config", "--get", "remote.origin.url", cwd=checkout)  # as written, before any insteadOf
    found = REMOTE.match(url.stdout.strip()) if url.returncode == 0 else None
    if not found:
        return None
    return found["host"] or found["ssh_host"], f"{found['owner']}/{found['repo']}"


def read_pull_request(source, checkout, gh):
    """(source object, target commit, head commit, description) of a pull request URL, its commits fetched."""
    url = PULL_REQUEST.match(source)
    repository = f"{url['owner']}/{url['repo']}"
    pull = gh_api(gh, f"repos/{repository}/pulls/{url['number']}", url["host"])
    fetched = [git("fetch", "-q", "origin", ref, cwd=checkout)
               for ref in (pull["base"]["ref"], f"refs/pull/{pull['number']}/head")]
    head = commit(checkout, pull["head"]["sha"])
    if not head:
        problem = next((done.stderr.strip() for done in fetched if done.returncode), "")
        raise Refused(f"the head of pull request {pull['number']}, {pull['head']['sha'][:12]}, could not be "
                      f"fetched from origin{': ' + problem if problem else ''}")
    target = commit(checkout, f"origin/{pull['base']['ref']}", pull["base"]["ref"])
    return as_source(pull, repository), target, head, pull.get("body") or ""


def read_branches(source, checkout, gh):
    """(source object, target commit, head commit, description of its pull request or None) of `<target>:<source>`.
    A branch in the checkout wins over the one on `origin`: the developer names the branch they have."""
    target_branch, _, source_branch = source.partition(":")
    if not target_branch or not source_branch:
        raise Refused(f"not a pull request URL nor <target>:<source>: {source}")
    for branch in (target_branch, source_branch):
        git("fetch", "-q", "origin", branch, cwd=checkout)  # a branch that is only local is fine
    found = {branch: commit(checkout, branch, f"origin/{branch}") for branch in (target_branch, source_branch)}
    missing = [branch for branch, sha in found.items() if not sha]
    if missing:
        raise Refused(f"no branch {', '.join(missing)} in {checkout} or on origin")
    pull, pulls = None, []
    repository = origin_repository(checkout)
    if repository:
        host, name = repository
        owner = name.split("/")[0]
        try:
            pulls = gh_api(gh, f"repos/{name}/pulls?head={owner}:{source_branch}&state=open", host)
        except Refused:
            pulls = []  # without GitHub the review runs, and the page says sending is unavailable
        pull = as_source(pulls[0], name) if pulls else None
    return {"kind": "branches", "target": target_branch, "source": source_branch, "pull-request": pull}, \
        found[target_branch], found[source_branch], (pulls[0].get("body") or "") if pulls else None


def read_source(source, checkout, gh):
    """(source object, target commit, head commit, description) of a pull request URL or `<target>:<source>`."""
    return (read_pull_request if PULL_REQUEST.match(source) else read_branches)(source, checkout, gh)


def merge_base(target, head, checkout, source):
    """Where the change branched off: the diff of a review runs from here to its head."""
    found = git("merge-base", target, head, cwd=checkout)
    if found.returncode != 0:
        raise Refused(f"{source}: the two sides share no history")
    return found.stdout.strip()


def open_review(review, source, checkout, gh=None):
    """Open the review in `review` (its folder) from `source`, read in `checkout`. Raises Refused, leaving no worktree
    and no state behind."""
    review, checkout = pathlib.Path(review), pathlib.Path(checkout)
    if (review / "review.json").exists():
        return
    gh = gh or gh_command()
    described, target, head, _ = read_source(source or "", checkout, gh)
    base = merge_base(target, head, checkout, source)
    review.mkdir(parents=True, exist_ok=True)
    worktree = review / "worktree"
    made = git("worktree", "add", "-q", "--detach", str(worktree), head, cwd=checkout)
    if made.returncode != 0:
        raise Refused(f"the review's worktree at {head[:12]} could not be made: {made.stderr.strip()}")
    try:
        diff = review / "init.diff"
        written = git("diff", f"--output={diff}", base, head, cwd=checkout)
        if written.returncode != 0:
            raise Refused(f"the diff {base[:12]}...{head[:12]} could not be written: {written.stderr.strip()}")
        review_state.change(review, "init", {"source": described, "checkout": str(checkout), "base": base,
                                             "head": head, "diff": str(diff)})
    except Exception:
        git("worktree", "remove", "--force", str(worktree), cwd=checkout)
        shutil.rmtree(worktree, ignore_errors=True)
        raise
