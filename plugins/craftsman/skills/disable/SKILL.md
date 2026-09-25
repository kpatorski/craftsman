---
name: disable
description: >
  Disables a directive, protocol, or bundle by id — moves it into the Disabled table of its category (or, for a bundle,
  cascades to its members too). For a protocol with a `checkpoint`, this means "do not stop me here" — see `core.md`.
  Trigger: "/craftsman:disable", "disable directive", "disable protocol", "disable bundle", "turn off".
argument-hint: "<id>"
allowed-tools: [Read, Edit, Bash]
---

# disable

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — resolving the id, "Enable / disable" (including the bundle
   cascade and `requires` resolution), and the versioning step at the end.
2. If `$ARGUMENTS` is an `entry-point` protocol, confirm first (see Notes).
3. Run `scripts/set_enabled.py ~/.claude/craftsman disable $ARGUMENTS` — it resolves the id, cascades a bundle to
   its members, checks which enabled bundles require it, moves the rows and commits (MANAGEMENT.md, "Enable /
   disable").
4. Exit 3 means other bundles require this one: put its message to the developer as a question, and on yes re-run
   with `--yes`; on no, nothing was changed. Exit 2 is an unknown id — say so. Otherwise relay what it printed.

## Notes

- Disabling an `entry-point` protocol (`analyse`, `domain-design`, `implement`, or a workshop-added one) removes its
  command from use — confirm before doing this, it is not a routine toggle like a stack preference.
- Disabling a bundle that another enabled bundle `requires` needs that other bundle disabled too, or it is left
  enabled but missing something it depends on — `set_enabled.py` stops and asks (exit 3) rather than doing either.
