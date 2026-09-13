---
name: enable
description: >
  Enables a directive or protocol by id — moves it into the Enabled table of its category. Trigger: "/craftsman:enable", "enable directive", "enable protocol", "turn on".
argument-hint: "<id>"
allowed-tools: [Read, Edit, Bash]
---

# enable

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — resolving the id, and the versioning step at the end.
2. Find `$ARGUMENTS`'s row in its Disabled table (directives or protocols index, whichever holds it). If it is already
   in Enabled, say so and stop.
3. Move the row to the category's Enabled table, same position rules as any other index edit (see
   `~/.claude/craftsman/directives/index.md` or `protocols/index.md` for the current layout).
4. Commit per MANAGEMENT.md.
