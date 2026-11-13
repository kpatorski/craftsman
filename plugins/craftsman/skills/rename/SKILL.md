---
name: rename
description: >
  Renames a directive, protocol, or bundle id, updating every reference to it across every collection. Trigger:
  "/craftsman:rename", "rename directive", "rename protocol", "rename bundle".
argument-hint: "<old-id> <new-id>"
allowed-tools: [Read, Write, Edit, Bash, Grep]
---

# rename

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — the "Renaming" section is the core of this skill; the versioning step
   applies at the end.
2. Run `scripts/rename_id.py ~/.claude/craftsman <old-id> <new-id>`. It refuses, touching nothing, when `<old-id>` is
   not installed or `<new-id>` already exists; otherwise it renames the entry's directory and every reference to the
   id in one pass, and prints each file it changed. Relay a refusal as-is and stop.
3. Read the diff line by line (`git -C ~/.claude/craftsman diff`): an id that is also an ordinary word can be replaced
   in plain prose too (MANAGEMENT.md, "Renaming"). Undo such a line, and re-pad a table whose id column changed width
   with `scripts/toggle_table_row.py`.
4. Run `scripts/validate_content.py ~/.claude/craftsman`; a problem it reports is fixed before committing.
5. Commit per MANAGEMENT.md.
