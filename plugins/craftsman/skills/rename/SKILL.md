---
name: rename
description: >
  Renames a directive or protocol id, updating every reference to it across both collections. Trigger: "/craftsman:rename", "rename directive", "rename protocol".
argument-hint: "<old-id> <new-id>"
allowed-tools: [Read, Write, Edit, Bash, Grep]
---

# rename

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — the "Renaming" section is the core of this skill; the versioning step applies at the end.
2. Refuse if `<new-id>` already exists elsewhere (MANAGEMENT.md, same uniqueness rule as `install`).
3. Rename the directory, update the `id` field in its own frontmatter, and update every `composes` / `steps` / `uses` / `overrides` entry and every body link across both `directives/` and `protocols/` that pointed at the old id.
4. Update the id's row (and any link cell) in both index files if it appears there.
5. Re-run the link/id validation `install` runs, to confirm nothing was missed.
6. Commit per MANAGEMENT.md.
