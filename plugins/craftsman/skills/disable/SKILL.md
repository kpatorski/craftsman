---
name: disable
description: >
  Disables a directive, protocol, or bundle by id — moves it into the Disabled table of its category (or, for a bundle, cascades to its members too). For a protocol with a `checkpoint`, this means "do not stop me here" — see `core.md`. Trigger: "/craftsman:disable", "disable directive", "disable protocol", "disable bundle", "turn off".
argument-hint: "<id>"
allowed-tools: [Read, Edit, Bash]
---

# disable

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — resolving the id, "Enable / disable" (including the bundle
   cascade and `requires` resolution), and the versioning step at the end.
2. Find `$ARGUMENTS`'s row in its Enabled table — the appropriate top-level index, or the bundle's own `bundle.md`
   if it lives inside one. If it is already in Disabled, say so and stop.
3. If `$ARGUMENTS` is a bundle id, follow MANAGEMENT.md's cascade and check whether any other enabled bundle
   requires it. Otherwise, move the single row to the Disabled table.
4. Commit per MANAGEMENT.md.

## Notes

- Disabling an `entry-point` protocol (`analyse`, `domain-design`, `implement`, or a workshop-added one) removes its
  command from use — confirm before doing this, it is not a routine toggle like a stack preference.
- Disabling a bundle that another enabled bundle `requires` needs that other bundle disabled too, or it is left
  enabled but missing something it depends on — MANAGEMENT.md's "Resolving `requires` on disable" covers this.
