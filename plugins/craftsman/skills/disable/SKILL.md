---
name: disable
description: >
  Disables a directive or protocol by id — moves it into the Disabled table of its category. For a protocol with a `checkpoint`, this means "do not stop me here" — see `core.md`. Trigger: "/craftsman:disable", "disable directive", "disable protocol", "turn off".
argument-hint: "<id>"
allowed-tools: [Read, Edit, Bash]
---

# disable

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — resolving the id, and the versioning step at the end.
2. Find `$ARGUMENTS`'s row in its Enabled table. If it is already in Disabled, say so and stop.
3. Move the row to the category's Disabled table.
4. Commit per MANAGEMENT.md.

## Notes

- Disabling an `entry-point` protocol (`analyse`, `domain-design`, `implement`, or a workshop-added one) removes its command from use — confirm before doing this, it is not a routine toggle like a stack preference.
