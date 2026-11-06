"""The AI Agent's preview of a draft -- see REVIEW.md, "Drafts".

While the developer writes a draft of a finding, a short Claude call of its own, not the review's session, writes it
as the finding the review's rules ask for: the comment for the author, a title, a description, a category and a
severity, and the finding already in the file it repeats, if any. The session handles one message at a time and keeps
its context; a preview every few seconds would wait behind its work and fill that context.

The call gets everything in its prompt -- the draft, the code it is about, the review's directives for comments, the
findings already in the file -- and has no tools, so it answers in seconds. A newer draft of the same file makes the
call still running for it stale: that call is stopped and answers None.
"""
import json
import os
import pathlib
import subprocess
import threading

import review_state

MODEL = os.environ.get("CRAFTSMAN_PREVIEW_MODEL", "haiku")
DIRECTIVES = ("review-comment", "review-posture", "engineer-prose")
AROUND = 20  # lines of code shown before and after the lines a draft is about
LONGEST = 400  # lines of a file's diff shown for a draft about the whole file
FIELDS = ("title", "category", "severity", "description", "comment", "repeats")
SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "category": {"type": "string"},
        "severity": {"type": "string", "enum": list(review_state.SEVERITY)},
        "description": {"type": "string"},
        "comment": {"type": "string"},
        "repeats": {"type": "string"},
    },
    "required": list(FIELDS),
}

_running = {}  # (review, path) -> the call writing that draft's preview now
_lock = threading.Lock()


class PreviewFailed(Exception):
    pass


def claude_command():
    return os.environ.get("CRAFTSMAN_CLAUDE", "claude").split()


def file_diff(text, path):
    """The lines of one file's part of a diff, each as (old number, new number, mark, code)."""
    lines, inside, old, new = [], False, 0, 0
    for line in text.splitlines():
        if line.startswith("diff --git "):
            inside = line.endswith(" b/" + path)
            continue
        if not inside or line.startswith(("---", "+++", "index ")):
            continue
        if line.startswith("@@"):
            numbers = line.split(" ")
            old, new = int(numbers[1][1:].split(",")[0]), int(numbers[2][1:].split(",")[0])
            continue
        mark = line[:1] or " "
        lines.append((old if mark != "+" else None, new if mark != "-" else None, mark, line[1:]))
        old += mark != "+"
        new += mark != "-"
    return lines


def code_excerpt(review, state, path, lines):
    kept = pathlib.Path(review) / "diff" / f"{state['head']}.diff"
    diff = file_diff(kept.read_text() if kept.is_file() else "", path)
    if lines:
        first, last = lines[0] - AROUND, lines[1] + AROUND
        diff = [entry for entry in diff if (entry[1] or entry[0] or 0) >= first and (entry[1] or entry[0] or 0) <= last]
    shown = [f"{new or old or '':>5} {mark}{code}" for old, new, mark, code in diff[:LONGEST]]
    return "\n".join(shown) or "(no change in this file's diff)"


def directives(content):
    texts = []
    for name in DIRECTIVES:
        found = pathlib.Path(content or "") / "bundles" / "code-review" / "directives" / name / "directive.md"
        if found.is_file():
            texts.append(f'<directive id="{name}">\n{found.read_text().strip()}\n</directive>')
    return "\n\n".join(texts) or "(none installed)"


def prompt(review, state, path, text, lines, content):
    place = f"{path}, lines {lines[0]}–{lines[1]}" if lines else f"{path}, the whole file"
    here = [f for f in state.get("findings", []) if f.get("status") not in ("deleted", "merged")
            and any(location["path"] == path for location in f.get("locations", []))]
    findings = "\n".join(
        f"- {f['id']} · line {next(l['line'] for l in f['locations'] if l['path'] == path) or 'whole file'} · "
        f"{f['title']}: {f['comment'][:300]}" for f in here) or "(none)"
    categories = ", ".join(sorted({f["category"] for f in state.get("findings", [])})) or "(none yet)"
    language = state.get("language") or "the language of the draft"
    return f"""You turn a code reviewer's raw thoughts into one finding of a pull-request review: the comment they will
post for the author of the pull request. The reviewer is still writing; you see the draft as it is now.

The reviewer's draft, in their own words, maybe dictated, maybe rough:
<draft>
{text}
</draft>

It is about {place}. The code there, from the pull request's diff (+ added, - removed, the new line number first):
<code>
{code_excerpt(review, state, path, lines)}
</code>

How the review writes its findings, its own directives:
{directives(content)}

Findings already in this file:
{findings}

Categories in this review so far: {categories}.

Write the finding, in {language}, except the category:
- comment: the comment for the author, in GitHub markdown. Keep the reviewer's point and add no other one: say what is
  wrong, why it matters, and what to do. Add a short code suggestion only when it makes the fix clear.
- title: a few words naming the problem.
- description: one or two sentences on why it matters.
- category: a short English kebab-case name; use one of the categories above when it fits.
- severity: must-fix, should-fix or nit, as the directives weigh it.
- repeats: the id of a finding above that is the same problem, or an empty string.
"""


def answer_of(output):
    events = json.loads(output)
    events = events if isinstance(events, list) else [events]
    result = next((e for e in events if e.get("type") == "result"), None)
    if not result or result.get("is_error") or not isinstance(result.get("structured_output"), dict):
        raise PreviewFailed((result or {}).get("result") or "no finding in the answer")
    return {field: result["structured_output"].get(field, "") for field in FIELDS}


def preview(review, path, text, lines=None, side="RIGHT", content=None, command=None, timeout=120):
    """The draft written as a finding, or None when a newer draft of the same file came in meanwhile."""
    state = review_state.read(review)
    argv = (command or claude_command()) + [
        "-p", "--model", MODEL, "--tools", "", "--no-session-persistence", "--strict-mcp-config",
        "--setting-sources", "", "--output-format", "json", "--json-schema", json.dumps(SCHEMA)]
    key = (str(pathlib.Path(review).resolve()), path)
    call = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            cwd=str(review), start_new_session=True)
    with _lock:
        older = _running.get(key)
        _running[key] = call
    if older and older.poll() is None:
        older.kill()
    try:
        out, err = call.communicate(prompt(review, state, path, text, lines, content), timeout=timeout)
    except subprocess.TimeoutExpired:
        call.kill()
        raise PreviewFailed(f"no answer in {timeout} s")
    finally:
        with _lock:
            if _running.get(key) is call:
                del _running[key]
    with _lock:
        stale = _running.get(key) not in (None, call) or call.returncode < 0
    if stale:
        return None
    if call.returncode != 0:
        raise PreviewFailed(err.strip() or out.strip() or f"claude exited {call.returncode}")
    return answer_of(out)
