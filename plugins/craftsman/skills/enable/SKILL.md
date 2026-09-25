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
2. Run `scripts/set_enabled.py ~/.claude/craftsman enable $ARGUMENTS` — it resolves the id, cascades a bundle to
   its members, resolves `requires`, moves the rows and commits (MANAGEMENT.md, "Enable / disable").
3. Exit 3 means other bundles would change too: put its message to the developer as a question (default yes), and
   on yes re-run with `--yes`. Exit 2 is a stop — an unknown id, or a requirement that is not installed; say so.
4. Relay what it printed, including the note that a bundle toggle overwrites members toggled individually.
