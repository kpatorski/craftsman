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
from review_state import Refused

DIALOGS = {
    "Darwin": ["osascript", "-e", 'POSIX path of (choose folder with prompt "The checkout of the reviewed repository")'],
    "Linux": ["zenity", "--file-selection", "--directory", "--title=The checkout of the reviewed repository"],
}


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def pull_request(source):
    """(owner, repo) of a pull request URL, or None for two branches."""
    pull = reviews.PULL_REQUEST.match(source or "")
    return (pull.group(1), pull.group(2)) if pull else None


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
        wanted = re.compile(rf"github\.com[:/]{re.escape(named[0])}/{re.escape(named[1])}(\.git)?(\s|$)", re.I)
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
    url = f"{os.environ.get('CRAFTSMAN_GITHUB') or 'https://github.com'}/{owner}/{repo}.git"
    shutil.rmtree(target, ignore_errors=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    made = git("clone", "-q", "--filter=blob:none", "--no-checkout", url, str(target))
    if made.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        raise Refused(f"cloning {owner}/{repo} failed: {made.stderr.strip()}")
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
