---
name: uninstall
description: >
  Removes a directive, protocol, or bundle by id from `~/.claude/craftsman/`. Trigger: "/craftsman:uninstall", "remove
  directive", "remove protocol", "remove bundle", "uninstall".
argument-hint: "<id>"
allowed-tools: [Read, Edit, Bash, AskUserQuestion]
---

# uninstall

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — resolving the id, and the versioning step at the end.
2. Find `$ARGUMENTS`. Before removing, check whether anything else references it (`composes`, `steps`, `uses`,
   `overrides`, `requires`, or a body link) — the same scan `merge` uses. If it is referenced, say so and ask
   whether to proceed anyway (leaving a dangling reference for the referrer to fix) or stop.
3. Remove its row from the index (Enabled or Disabled table, whichever holds it — the top-level index for a
   standalone entry, the bundle's own `bundle.md` for one inside a bundle) and delete its directory. Uninstalling a
   bundle removes its entire `bundles/<id>/` tree and its row in `bundles/index.md` — this deletes its members too,
   not just the bundle wrapper; make that explicit before proceeding.
4. Commit per MANAGEMENT.md.

## Notes

- Uninstalling an `entry-point` protocol is a bigger deal than a leaf — confirm explicitly, since it removes a whole
  command.
- Uninstalling a bundle that another installed bundle `requires` leaves that bundle broken if it stays enabled —
  surface this the same way step 2's reference check does, before removing.
