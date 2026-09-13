---
name: list
description: >
  Lists installed directives and protocols, enabled and disabled, grouped by category. Trigger: "/craftsman:list", "list plugins", "list protocols", "list directives", "what's installed", "what's enabled".
argument-hint: "[directives|protocols]"
allowed-tools: [Read]
---

# list

## Run this

1. Read `~/.claude/craftsman/directives/index.md` and/or `~/.claude/craftsman/protocols/index.md` per `$ARGUMENTS`
   (both, if no argument is given).
2. Render every category section as it stands in the index — Enabled table, then Disabled table, with the count of each.
3. If `~/.claude/craftsman/` does not exist yet, say so plainly instead of an empty list.

## Notes

- Read-only. The index files are the single source of truth for current enabled/disabled state — see `EXECUTION.md`,
  "Loading directives".
