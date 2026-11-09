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

# the words that ask for each shape of the comment -- see review_state.COMMENT_STYLE
SHAPES = {
    "fidelity": {
        "close": "Stay close to the reviewer's words: every point of the draft, in its order, as firmly and as "
                 "surely as the draft says it — no softening (\"I'd like\", \"maybe\", \"could we\") of what it "
                 "says plainly, and nothing added: no argument, reason or example the draft does not give. "
                 "Translate, fix grammar and typos, drop filler and repeated words, format it as markdown; nothing "
                 "more.",
        "balanced": "Keep every point of the draft, as firmly as the draft says it, in your own words; add no "
                    "argument the draft does not give.",
        "free": "Write it your way from the draft's point: what is wrong, what to do, and why it matters when the "
                "author would not see it.",
    },
    "tone": {
        "casual": "Casual, the way you'd say it to a teammate over coffee: short words, contractions, no ceremony.",
        "teammate": "The way a teammate would say it at their desk: plain spoken words — \"we\", \"let's\", "
                    "\"I'd\" are fine — no report language and no labels.",
        "formal": "Formal and neutral, as in a written code review: complete sentences, no slang, no \"I'd\".",
    },
    "detail": {
        "brief": "One or two sentences: what to change. Nothing else.",
        "normal": "Make it as long as the draft calls for: a short thought or a reminder stays one or two "
                  "sentences; only a draft that explains something gets a paragraph or two.",
        "detailed": "A paragraph or two: what is wrong, why it matters, and how to fix it.",
    },
    "code": {
        True: "End with a short code block showing the fix, written from the code above: only the lines that "
              "matter.",
        False: "No code block unless the draft has one or asks for one.",
    },
}
FIRMNESS = {
    "must-fix": "it has to change before the merge — say so plainly (\"we need to\", \"this has to\"), never as "
                "a wish or a question",
    "should-fix": "a clear recommendation the author is expected to follow",
    "nit": "minor and optional: mark it as minor, the author may leave it",
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


def shape(style, default=None):
    """The shape asked for, part by part; a part not given, or not known, is the default one."""
    style = style if isinstance(style, dict) else {}
    return {key: style[key] if review_state.known_style(key, style.get(key)) else fallback
            for key, fallback in (default or review_state.COMMENT_STYLE_DEFAULT).items()}


def how_to_write(style, severity):
    asked = shape(style)
    lines = [f"- {SHAPES[key][asked[key]]}" for key in ("fidelity", "tone", "detail", "code")]
    if severity in FIRMNESS:
        lines.append(f"- The reviewer weighs it {severity}: {FIRMNESS[severity]}. Answer severity {severity}.")
    else:
        strengths = "; ".join(f"{name}: {how}" for name, how in FIRMNESS.items())
        lines.append("- Weigh it must-fix, should-fix or nit as the directives weigh it, and write the comment with "
                     f"the strength of the severity you choose: {strengths}.")
    return "\n".join(lines)


def prompt(review, state, path, text, lines, content, style=None, severity=None):
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

How the reviewer wants the comment written; where the style below and the directives differ, the style below wins:
{how_to_write(style, severity)}

Write the finding, in {language}, except the category:
- comment: the comment for the author, in GitHub markdown, in the style above. Keep the reviewer's point. Do not
  repeat what the comment sits on: the file, the line, the names right above it.
  When the draft has a code block or asks for one, the comment has one too: the actual code the reviewer means, written
  from the code above, in place of any placeholder ("proposal here", "TODO", "..."), never dropped.
  When the draft says the point holds for every place in the change, the comment says so in one plain sentence
  ("please remove these everywhere you added them").
- title: a few words naming the problem, the way you would say it in a stand-up.
- description: one short sentence on why it matters, not a repeat of the comment.
- category: a short English kebab-case name; use one of the categories above when it fits.
- severity: must-fix, should-fix or nit, as said above.
- repeats: the id of a finding above that is the same problem, or an empty string.
"""


def answer_of(output):
    events = json.loads(output)
    events = events if isinstance(events, list) else [events]
    result = next((e for e in events if e.get("type") == "result"), None)
    if not result or result.get("is_error") or not isinstance(result.get("structured_output"), dict):
        raise PreviewFailed((result or {}).get("result") or "no finding in the answer")
    return {field: result["structured_output"].get(field, "") for field in FIELDS}


def preview(review, path, text, lines=None, side="RIGHT", content=None, command=None, timeout=120, style=None,
            severity=None):
    """The draft written as a finding, in the shape asked for, or None when a newer draft of the same file came in
    meanwhile. `severity` is the one the reviewer picked, if they did."""
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
        out, err = call.communicate(prompt(review, state, path, text, lines, content, style, severity),
                                    timeout=timeout)
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
