"""Fix prompts -- see REVIEW.md, "Fix prompts".

The findings the developer sends to the author -- marked to send, or sent -- and leaves in the prompts (`in-prompt` is
not false) become one comment on the whole pull request: one prompt per category, each in a fenced block, for the
author to paste into their own AI coding agent. Each prompt asks for its category's fixes and nothing else, made as one
commit, so the author's history gets one atomic commit per kind of problem. The developer's findings with no category
of their own go in one prompt of other fixes. A prompt names no severity, it only lists the worst first: the labels are
the review's, not words for the author's agent.
"""
import re

from review_state import NO_CATEGORY

MARKER = "<!-- craftsman:fix-prompts -->"
SEVERITY = ("must-fix", "should-fix", "nit")
SENT_TO_THE_AUTHOR = ("to-send", "sent")
LIMIT = 65536  # the longest comment GitHub takes, in characters


def in_prompts(found):
    return found.get("status") in SENT_TO_THE_AUTHOR and found.get("in-prompt", True) is not False


def place(location):
    return f"{location['path']}:{location['line']}" if location.get("line") else location["path"]


def rank(found):
    first = (found.get("locations") or [{}])[0]
    return SEVERITY.index(found["severity"]), first.get("path", ""), first.get("line") or 0


def what_is_reviewed(state):
    source = state.get("source") or {}
    pull = source if source.get("kind") == "pull-request" else source.get("pull-request")
    if pull:
        return f"pull request #{pull['number']} of {pull['repository']}"
    return f"branch {source.get('source')}, to be merged into {source.get('target')}"


def prompt(state, category, findings):
    about = "" if category == NO_CATEGORY else f"All of them are about {category}. "
    lines = [f"Fix these review findings in {what_is_reviewed(state)}, reviewed at commit {state['head'][:12]}.",
             f"{about}Make every fix below and nothing else, then make one commit with only these changes. When a "
             "finding says it applies to every place in the change, fixing every such place is part of that fix.", ""]
    for number, found in enumerate(findings, 1):
        locations = found.get("locations") or []
        lines.append(f"{number}. {place(locations[0]) if locations else 'no place'} — {found['title']}")
        lines += ["   " + line if line else "" for line in found["comment"].strip().splitlines()]
        if len(locations) > 1:
            lines.append("   Also at: " + ", ".join(place(location) for location in locations[1:]))
        lines.append("")
    lines.append("Run the tests before the commit, and say what you changed for each finding.")
    return "\n".join(lines)


def fenced(text):
    # a fence longer than any run of backticks in the text, so a code block inside it never ends the prompt
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}\n{text}\n{fence}"


def comments(state, limit=None):
    """The fix prompts as the markdown of comments on the whole pull request: one comment, or, when they are too long
    for one GitHub comment, as few as hold them, each with whole prompts. Empty when no finding goes in."""
    limit = limit or LIMIT
    chosen = [found for found in state.get("findings", []) if in_prompts(found)]
    by_category = {}
    for found in sorted(chosen, key=rank):
        by_category.setdefault(found["category"], []).append(found)
    order = sorted(by_category, key=lambda c: (rank(by_category[c][0])[0], -len(by_category[c]), c))
    sections = []
    for category in order:
        findings = by_category[category]
        heading = "Other fixes" if category == NO_CATEGORY else category
        sections.append(f"#### {heading} · {len(findings)} finding{'s' if len(findings) > 1 else ''}\n\n"
                        + fenced(prompt(state, category, findings)))
    intro = "**Fix prompts** — one per kind of problem. Paste each into your AI coding agent; each one ends in one commit."
    room = limit - len(MARKER) - len(intro) - 40  # the head of a part, "(part n of m)" included
    groups = []
    for section in sections:
        if groups and len("\n\n".join(groups[-1] + [section])) <= room:
            groups[-1].append(section)
        else:
            groups.append([section])
    return [f"{MARKER}\n\n{intro}{f' (part {n} of {len(groups)})' if len(groups) > 1 else ''}\n\n"
            + "\n\n".join(group) + "\n" for n, group in enumerate(groups, 1)]


def is_fix_prompts(body):
    return (body or "").startswith(MARKER)
