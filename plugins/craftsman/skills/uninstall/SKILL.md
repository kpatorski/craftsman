---
name: uninstall
description: >
  Removes a directive or protocol by id from `~/.claude/craftsman/`. Trigger: "/craftsman:uninstall", "remove directive", "remove protocol", "uninstall".
argument-hint: "<id>"
allowed-tools: [Read, Edit, Bash, AskUserQuestion]
---

# uninstall

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — resolving the id, and the versioning step at the end.
2. Find `$ARGUMENTS`. Before removing, check whether anything else references it (`composes`, `steps`, `uses`,
   `overrides`, or a body link) — the same scan `merge` uses. If it is referenced, say so and ask whether to proceed
   anyway (leaving a dangling reference for the referrer to fix) or stop.
3. Remove its row from the index (Enabled or Disabled table, whichever holds it) and delete its directory.
4. Commit per MANAGEMENT.md.

## Notes

- Uninstalling an `entry-point` protocol is a bigger deal than a leaf — confirm explicitly, since it removes a whole
  command.
