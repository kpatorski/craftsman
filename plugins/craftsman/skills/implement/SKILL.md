---
name: implement
description: >
  Drives a coding task the way the developer works, in a HUMAN <-> AI loop instead of one large generated drop. Executes
  the `implement` entry-point protocol from the installed workshop, matching the task to a scenario and walking it step
  by step — stopping at every checkpoint to confirm direction with the developer. Progress is persisted to a per-task
  `implement-session-<slug>.md` under `.claude/sessions/` in the project, so one task can span many Claude sessions.
  Trigger: "/craftsman:implement", "work in my style", "add a use case", "let's TDD this", "drive this change with my
  coding style", "resume the coding session", "continue the implement loop".
argument-hint: "<task description, or a spec file path> [session=<path to session file>]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion]
---

# implement

An orchestrator. It does not write a solution end to end and then report. It advances a coding task in small,
checkpoint-gated moves, following the `implement` protocol installed at
`~/.claude/craftsman/protocols/implement/protocol.md` and whatever it calls. The developer stays in the loop at every
decision point.

## Why this exists

Left to its defaults, an AI takes a coding task and produces a large block of code to review after the fact. By then the
direction is set and correcting it is expensive. This skill inverts that: the *process* is data — directives and
protocols the developer (or a workshop they installed) authored — the tool executes it, and it stops, visibly and on
purpose, wherever that content says to check in.

## Run this

1. **Load [EXECUTION.md](../../EXECUTION.md)** — the mechanics shared by every craftsman entry point: dispatch,
   directive loading, the session file, resuming, the checkpoint protocol. Everything below is specific to `implement`;
   everything about *how* to run it is there.
2. **Read `~/.claude/craftsman/protocols/implement/protocol.md`** and execute it per EXECUTION.md's dispatch rules —
   `$ARGUMENTS` is the task description or spec file path.
3. If `~/.claude/craftsman/protocols/` does not exist, this is a first run — EXECUTION.md's "Where the content lives"
   section covers it; do not proceed with an invented process.

## Notes

- A spec file (from `domain-design`) is a valid `$ARGUMENTS` — its Acceptance criteria become the source `implement`'s
  scenarios enumerate as test cases. `implement` does not require one; a plain task description works too.
- Nothing here duplicates EXECUTION.md. If this file and EXECUTION.md ever seem to disagree, EXECUTION.md wins — it is
  the single source for mechanics.
