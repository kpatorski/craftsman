---
name: enable
description: >
  Enables a directive, protocol, or bundle by id — moves it into the Enabled table of its category (or, for a bundle,
  cascades to its members too). Trigger: "/craftsman:enable", "enable directive", "enable protocol", "enable bundle",
  "turn on".
argument-hint: "<id>"
allowed-tools: [Read, Edit, Bash]
---

# enable

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — resolving the id, "Enable / disable" (including the bundle
   cascade and `requires` resolution), and the versioning step at the end.
2. Find `$ARGUMENTS`'s row in its Disabled table — the appropriate top-level index, or the bundle's own `bundle.md`
   if it lives inside one. If it is already in Enabled, say so and stop.
3. If `$ARGUMENTS` is a bundle id, follow MANAGEMENT.md's cascade and `requires` resolution. Otherwise, move the
   single row to the Enabled table.
4. Commit per MANAGEMENT.md.
