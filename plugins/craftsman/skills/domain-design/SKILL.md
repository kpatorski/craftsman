---
name: domain-design
description: >
  Turns a requirements input into reviewed, written task specs — event storming (or whatever the installed workshop's own analysis method is) run in a HUMAN <-> AI loop, one confirmed building block at a time, instead of a guessed backlog. Executes the `domain-design` entry-point protocol. Progress is persisted to a per-task `domain-design-session-<slug>.md` under `.claude/sessions/` in the project. Trigger: "/craftsman:domain-design", "analyze these requirements", "run event storming on this", "turn this into specs", "resume the domain design session".
argument-hint: "<input file, URL, or inline text> [session=<path to session file>]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, WebFetch, AskUserQuestion]
---

# domain-design

Turns a raw requirements input into `specs/NNN-slug.md` files a human then hands to `implement`. Formerly the `analyst`
skill; see the `craftsman` plan, decision 7.

## Run this

1. **Load [EXECUTION.md](../../EXECUTION.md)** — the mechanics shared by every craftsman entry point.
2. **Read `~/.claude/craftsman/protocols/domain-design/protocol.md`** and execute it per EXECUTION.md's dispatch rules —
   `$ARGUMENTS` is the input (file path, URL, or inline text).
3. If `~/.claude/craftsman/protocols/` does not exist, this is a first run — see EXECUTION.md, "Where the content
   lives".

## Notes

- Optionally consumes a `business-rules.md` produced by `analyse` (or written by hand) — authoritative when present, but
  `domain-design` runs standalone on raw input alone. It never assumes `analyse` is installed.
- A spec's `shape` field (from the `classify-task-shape` directive) is a tool-agnostic hint, not another workshop's
  scenario id — `domain-design` never hardcodes `implement`'s internal ids. Handing a spec to `implement` is a loose,
  manual handoff.
- Nothing here duplicates EXECUTION.md. If this file and EXECUTION.md ever seem to disagree, EXECUTION.md wins.
