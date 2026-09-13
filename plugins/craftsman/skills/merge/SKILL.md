---
name: merge
description: >
  Finds directives or protocols that live in their own file but are used by exactly one parent, and proposes folding each into that parent. Trigger: "/craftsman:merge", "clean up single-use entries", "merge candidates".
allowed-tools: [Read, Write, Edit, Bash]
---

# merge

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — the "The `merge` candidate check" section is the core of this skill;
   the versioning step applies at the end.
2. Scan every directive and protocol — top-level and inside every bundle: for each, count how many other entries
   reference it (via `composes`, `steps`, or `uses`). Collect every entry referenced by exactly one parent and
   nothing else. A bundle named in another bundle's `requires` is never a candidate — `requires` is not counted here.
3. Present the full candidate list — each with its one parent — and ask which, if any, to fold in. Never merge without
   asking, and never merge more than one candidate per confirmation if the developer wants to review them individually.
4. For each accepted candidate: inline its `## Directive` / `## Protocol` content into the parent's own body at the
   point the parent's link pointed to, remove the standalone file and its index row, and update the parent's
   `composes` / `steps` / `uses` frontmatter to drop the now-inlined id.
5. Commit per MANAGEMENT.md.

## Notes

- A candidate referenced by nothing at all (zero parents, not one) is not this skill's job — that is a dangling entry,
  worth flagging separately, but merging has nothing to fold it into.
