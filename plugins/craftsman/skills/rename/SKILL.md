---
name: rename
description: >
  Renames a directive, protocol, or bundle id, updating every reference to it across every collection. Trigger: "/craftsman:rename", "rename directive", "rename protocol", "rename bundle".
argument-hint: "<old-id> <new-id>"
allowed-tools: [Read, Write, Edit, Bash, Grep]
---

# rename

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — the "Renaming" section is the core of this skill; the versioning step
   applies at the end.
2. Refuse if `<new-id>` already exists anywhere (MANAGEMENT.md, same uniqueness rule as `install`).
3. Rename the directory, update the `id` field in its own frontmatter, and update every `composes` / `steps` /
   `uses` / `overrides` / `requires` entry and every body link across `directives/`, `protocols/`, and every
   `bundles/*/` that pointed at the old id.
4. Update the id's row (and any link cell) in every index file it appears in — the top-level indexes, `bundles/index.md`
   if it is a bundle, or the owning bundle's own `bundle.md` if it is a member.
5. Re-run the link/id validation `install` runs, to confirm nothing was missed.
6. Commit per MANAGEMENT.md.
