#!/usr/bin/env python3
"""What changed in a project since a craftsman session file was last written -- see EXECUTION.md, "Resuming".

    changed_since.py <project dir> <session file>

A resumed run knows the project as it was when it last wrote its session file. Anything changed after that -- by the
developer, a teammate's commits, another run -- is invisible to it unless it is told. This prints the commits made
since, and every file that differs: committed changes, uncommitted edits, new and deleted files, with the craftsman
artifacts among them called out. The reference point is the session file's own modification time, so nothing has to
be recorded in advance and uncommitted work is seen too.

Without git, files are compared by modification time alone (deletions cannot be seen). Always exits 0.
"""
import datetime
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _dashboard_data import ARTIFACTS, SKIP_DIRS  # noqa: E402

STATE = {"M": "modified", "A": "new", "D": "deleted", "R": "renamed", "C": "new", "T": "modified"}
ORDER = ("new", "modified", "renamed", "changed", "deleted")


def git(project, *args):
    done = subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else None


def touched_after(project, relative, since):
    try:
        return (project / relative).stat().st_mtime > since
    except OSError:
        return False


def with_git(project, since):
    """(commits, {path: state}) -- committed since `since`, plus working-tree files written after it."""
    stamp = f"@{int(since)}"
    commits = (git(project, "log", f"--since={stamp}", "--format=%h %s") or "").splitlines()
    files = {}
    for line in reversed((git(project, "log", f"--since={stamp}", "--name-status", "--format=") or "").splitlines()):
        parts = line.split("\t")
        if len(parts) >= 2:
            files[parts[-1]] = STATE.get(parts[0][0], "changed")
    for path in (git(project, "ls-files", "--others", "--exclude-standard") or "").splitlines():
        if touched_after(project, path, since):
            files[path] = "new"
    for path in (git(project, "diff", "HEAD", "--name-only") or git(project, "ls-files", "-m") or "").splitlines():
        if not (project / path).exists():
            files[path] = "deleted"
        elif touched_after(project, path, since):
            files.setdefault(path, "modified")
    return commits, files


def without_git(project, since):
    files = {}
    for folder, folders, names in os.walk(project):
        folders[:] = [d for d in folders if not d.startswith(".") and d not in SKIP_DIRS]
        for name in names:
            relative = (pathlib.Path(folder) / name).relative_to(project).as_posix()
            if not name.startswith(".") and touched_after(project, relative, since):
                files[relative] = "changed"
    return [], files


def is_artifact(path):
    return path in ARTIFACTS or path.startswith("specs/") and path.endswith(".md")


def report(project, session):
    since = session.stat().st_mtime
    inside_git = git(project, "rev-parse", "--is-inside-work-tree") is not None
    commits, files = with_git(project, since) if inside_git else without_git(project, since)
    files = {path: state for path, state in files.items() if not path.startswith(".claude/")}
    when = datetime.datetime.fromtimestamp(since).strftime("%Y-%m-%d %H:%M")
    if not commits and not files:
        return f"Nothing changed in {project} since {session.name} was last written ({when})."
    lines = [f"Changed in {project} since {session.name} was last written ({when}):"]
    if commits:
        lines += ["", f"commits ({len(commits)}):"] + [f"  {commit}" for commit in commits]
    lines += ["", f"files ({len(files)}):"]
    for state in ORDER:
        lines += [f"  {state:<9}{path}" for path in sorted(files) if files[path] == state]
    artifacts = sorted(path for path in files if is_artifact(path))
    if artifacts:
        lines += ["", "craftsman artifacts among them -- what the run built on has moved:"]
        lines += [f"  {files[path]:<9}{path}" for path in artifacts]
    if not inside_git:
        lines += ["", "(no git repository: compared by file time only; deleted files cannot be seen)"]
    return "\n".join(lines)


def main():
    if len(sys.argv) != 3:
        print(__doc__.strip().split("\n")[2].strip(), file=sys.stderr)
        return
    project, session = pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2]).resolve()
    try:
        print(report(project, session))
    except OSError as error:
        print(f"Could not compare {project} with {session.name}: {error}")


if __name__ == "__main__":
    main()
