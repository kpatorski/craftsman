---
name: list
description: >
  Lists installed directives, protocols and bundles, enabled and disabled, grouped by category. Trigger: "/craftsman:list", "list plugins", "list protocols", "list bundles", "list directives", "what's installed", "what's enabled".
argument-hint: "[directives|protocols|bundles]"
allowed-tools: [Read]
---

# list

## Run this

1. Read `~/.claude/craftsman/directives/index.md`, `~/.claude/craftsman/protocols/index.md`, and/or
   `~/.claude/craftsman/bundles/index.md` per `$ARGUMENTS` (all three, if no argument is given).
2. Render every category section as it stands in the index — Enabled table, then Disabled table, with the count of
   each. For `bundles`, also read each bundle's own `bundle.md` and render its Enabled/Disabled member tables nested
   under the bundle's row.
3. If `~/.claude/craftsman/` does not exist yet, say so plainly instead of an empty list.

## Notes

- Read-only. The index files are the single source of truth for current enabled/disabled state — see `EXECUTION.md`,
  "Loading directives".
