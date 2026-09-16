---
name: list
description: >
  Lists installed directives, protocols and bundles, enabled and disabled, grouped by category. Trigger:
  "/craftsman:list", "list plugins", "list protocols", "list bundles", "list directives", "what's installed", "what's
  enabled".
argument-hint: "[directives|protocols|bundles]"
allowed-tools: [Bash]
---

# list

## Run this

Run `python3 <this plugin's own path>/scripts/list_content.py ~/.claude/craftsman [directives|protocols|bundles]`
(the kind argument matches `$ARGUMENTS`; omit it to print all three) and show the output as-is. It already handles
a not-yet-installed `~/.claude/craftsman/` (prints one plain line instead of an empty list) and, for `bundles`,
nests each bundle's own Protocols/Directives tables under its row — nothing left to compose or re-derive.

## Notes

- Read-only. The index files are the single source of truth for current enabled/disabled state — see `EXECUTION.md`,
  "Loading directives". The script only reads and prints them verbatim.
