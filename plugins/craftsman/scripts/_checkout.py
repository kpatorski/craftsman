"""Where a review reads the repository from: a checkout the developer names -- typed, or picked in the system's own
folder dialog -- or, for a pull request, a partial clone the dashboard server makes in /tmp. See REVIEW.md.

Nothing here looks for a repository on the disk by itself: the developer names the checkout, or agrees to the clone.
"""
import os
import pathlib
import platform
import re
import shlex
import shutil
import subprocess

import _reviews as reviews
import review_state
from review_state import Refused

DIALOGS = {
    "Darwin": ["osascript", "-e", 'POSIX path of (choose folder with prompt "The checkout of the reviewed repository")'],
    "Linux": ["zenity", "--file-selection", "--directory", "--title=The checkout of the reviewed repository"],
}


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def pull_request(source):
    """(owner, repo) of a pull request URL, or None for two branches."""
    pull = reviews.PULL_REQUEST.match(source or "")
    return (pull["owner"], pull["repo"]) if pull else None


def clone_url(source):
    """The repository of a pull request on its own host, github.com or a GitHub Enterprise one; `CRAFTSMAN_GITHUB`
    replaces the host (the tests do)."""
    pull = reviews.PULL_REQUEST.match(source or "")
    return f"{os.environ.get('CRAFTSMAN_GITHUB') or 'https://' + pull['host']}/{pull['owner']}/{pull['repo']}.git"


def check(path, source):
    """The checkout as the review uses it: the top folder of a git repository. For a pull request, a checkout whose
    remotes do not name the PR's repository is accepted with a warning. Raises Refused."""
    folder = pathlib.Path(path or "").expanduser().resolve()
    if not folder.is_dir():
        raise Refused(f"no such folder: {folder}")
    top = git("rev-parse", "--show-toplevel", cwd=folder)
    if top.returncode != 0:
        raise Refused(f"not a git repository: {folder}")
    if pathlib.Path(top.stdout.strip()).resolve() != folder:
        raise Refused(f"{folder} is inside a repository; its top folder is {top.stdout.strip()}")
    warning = None
    named = pull_request(source)
    if named:
        remotes = git("remote", "-v", cwd=folder).stdout
        host = reviews.PULL_REQUEST.match(source)["host"]
        wanted = re.compile(rf"{re.escape(host)}[:/]{re.escape(named[0])}/{re.escape(named[1])}(\.git)?(\s|$)", re.I)
        if not wanted.search(remotes):
            warning = f"no remote of {folder} points at {named[0]}/{named[1]}, the pull request's repository"
    return {"checkout": str(folder), "warning": warning}


def clones_root():
    """`/tmp/craftsman/repos`; `CRAFTSMAN_CLONES` moves it (the tests do)."""
    return pathlib.Path(os.environ.get("CRAFTSMAN_CLONES") or "/tmp/craftsman/repos")


def clone_dir(source):
    named = pull_request(source)
    if not named:
        raise Refused("only a pull request is cloned; two branches are reviewed in a local checkout")
    return clones_root() / named[0] / named[1]


def clone(source):
    """A partial clone of the pull request's repository (blobs are fetched when a worktree needs them), made once and
    fetched again when it exists. Returns its folder. Raises Refused."""
    target = clone_dir(source)
    if (target / ".git").is_dir():
        git("fetch", "-q", "origin", cwd=target)
        return target
    owner, repo = pull_request(source)
    url = clone_url(source)
    shutil.rmtree(target, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    # git signs in to the host the way gh does, so a private repository clones and fetches too; the empty helper first
    # drops whatever helpers the global config names
    helper = f"!{shutil.which('gh') or 'gh'} auth git-credential"
    made = git("-c", "credential.helper=", "-c", f"credential.helper={helper}", "clone", "-q", "--filter=blob:none",
               "--no-checkout", url, str(target))
    if made.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        raise Refused(f"cloning {owner}/{repo} failed: {made.stderr.strip()}")
    git("config", "--local", "credential.helper", "", cwd=target)
    git("config", "--local", "--add", "credential.helper", helper, cwd=target)
    return target


def browse():
    """The folder the developer picks in the system's folder dialog, or None when they cancel it. A browser never
    gives a page a folder's full path, so the server opens the dialog. Raises Refused where there is none."""
    command = shlex.split(os.environ["CRAFTSMAN_BROWSE"]) if os.environ.get("CRAFTSMAN_BROWSE") else \
        DIALOGS.get(platform.system())
    if not command or not shutil.which(command[0]):
        raise Refused("this system has no folder dialog the server can open; type the path")
    picked = subprocess.run(command, capture_output=True, text=True)
    chosen = picked.stdout.strip()
    if picked.returncode != 0 or not chosen:
        return None
    return chosen.rstrip("/") or "/"


# ---- a review's worktree and clone: deleted when it is closed or archived, made again when it resumes ------------

def is_clone(path):
    return clones_root() in pathlib.Path(path).parents


def pull_url(source):
    source = source or {}
    if source.get("kind") == "pull-request":
        return source.get("url")
    return (source.get("pull-request") or {}).get("url")


def needs_restore(review):
    """True when the review's checkout or its worktree at the reviewed commit is missing."""
    state = review_state.read(review)
    worktree = pathlib.Path(review) / "worktree"
    at = git("rev-parse", "HEAD", cwd=worktree) if (worktree / ".git").exists() else None
    return not (pathlib.Path(state.get("checkout") or "") / ".git").exists() or not at or \
        at.returncode != 0 or at.stdout.strip() != state["head"]


def restore(review):
    """Make the checkout again when it is a clone, and the worktree at the reviewed commit. Raises Refused."""
    review = pathlib.Path(review)
    state = review_state.read(review)
    folder = pathlib.Path(state.get("checkout") or "")
    if not (folder / ".git").exists():
        url = pull_url(state.get("source"))
        if not is_clone(folder) or not url or clone_dir(url) != folder:
            raise Refused(f"the checkout of {review.name} is missing: {folder}")
        clone(url)
    if not needs_restore(review):
        return
    worktree = review / "worktree"
    shutil.rmtree(worktree, ignore_errors=True)
    git("worktree", "prune", cwd=folder)
    if git("cat-file", "-e", f"{state['head']}^{{commit}}", cwd=folder).returncode != 0:
        source = state.get("source") or {}
        number = source.get("number") or (source.get("pull-request") or {}).get("number")
        wanted = f"refs/pull/{number}/head" if number else source.get("source")
        git("fetch", "-q", "origin", wanted, cwd=folder)
    made = git("worktree", "add", "-q", "--detach", str(worktree), state["head"], cwd=folder)
    if made.returncode != 0:
        raise Refused(f"the worktree of {review.name} at {state['head'][:12]} failed: {made.stderr.strip()}")


def release(review):
    """Delete the review's worktree, and its clone when no other open review reads from it. The state stays."""
    review = pathlib.Path(review)
    folder = pathlib.Path(review_state.read(review).get("checkout") or "")
    worktree = review / "worktree"
    if (folder / ".git").exists():
        git("worktree", "remove", "--force", str(worktree), cwd=folder)
    shutil.rmtree(worktree, ignore_errors=True)
    if (folder / ".git").exists():
        git("worktree", "prune", cwd=folder)
    others = [r for r in reviews.list_reviews() if r["id"] != review.name and r["checkout"] == str(folder)
              and not r["archived"] and not r["closed"]]
    if is_clone(folder) and not others:
        shutil.rmtree(folder, ignore_errors=True)
