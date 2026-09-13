---
name: analyse
description: >
  Turns raw requirements (a file, a URL, or pasted text) into Given/When/Then business rules — nothing more. No domain modelling; that is `domain-design`'s job. Executes the `analyse` entry-point protocol, section by section, each batch confirmed before the next. Progress is persisted to a per-task `analyse-session-<slug>.md` under `.claude/sessions/` in the project. Trigger: "/craftsman:analyse", "digest these requirements", "extract business rules", "resume the analyse session".
argument-hint: "<input file, URL, or inline text> [session=<path to session file>]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, WebFetch, AskUserQuestion]
---

# analyse

Turns a requirements input into `business-rules.md` — plain, structured Given/When/Then data any downstream reader (a human, `domain-design`, or anything else) can consume without `analyse` knowing that reader exists. Formerly the `digester` skill; see the `craftsman` plan, decision 7.

## Run this

1. **Load [EXECUTION.md](../../EXECUTION.md)** — the mechanics shared by every craftsman entry point.
2. **Read `~/.claude/craftsman/protocols/analyse/protocol.md`** and execute it per EXECUTION.md's dispatch rules — `$ARGUMENTS` is the input (file path, URL, or inline text).
3. If `~/.claude/craftsman/protocols/` does not exist, this is a first run — see EXECUTION.md, "Where the content lives".

## Notes

- Never references an id from any other workshop content — `analyse` installs and runs entirely on its own.
- Nothing here duplicates EXECUTION.md. If this file and EXECUTION.md ever seem to disagree, EXECUTION.md wins.
