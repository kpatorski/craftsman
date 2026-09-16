---
name: merge
description: >
  Finds directives or protocols that live in their own file but are used by exactly one parent, and proposes folding
  each into that parent. Trigger: "/craftsman:merge", "clean up single-use entries", "merge candidates".
allowed-tools: [Read, Write, Edit, Bash]
---

# merge

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — the "The `merge` candidate check" section is the core of this skill;
   the versioning step applies at the end.
2. Run `python3 <this plugin's own path>/scripts/merge_candidates.py ~/.claude/craftsman` — it prints the full
   candidate list (referenced by exactly one parent), plus the "referenced by nobody" list (a different problem,
   see Notes) and, with `--verbose`, everything correctly staying standalone. Use its output as-is; don't re-derive
   the same scan by hand.
3. Present the candidate list — each with its one parent — and ask which, if any, to fold in. Never merge without
   asking, and never merge more than one candidate per confirmation if the developer wants to review them individually.
4. For each accepted candidate: inline its `## Directive` / `## Protocol` content into the parent's own body at the
   point the parent's link pointed to, remove the standalone file
   (`scripts/uninstall_id.py ~/.claude/craftsman <id> --yes`, after the dry run confirms the only referrer is the
   parent being merged into), and update the parent's `composes` / `steps` / `uses` frontmatter to drop the
   now-inlined id.
5. Run `scripts/validate_content.py ~/.claude/craftsman` before committing.
6. Commit per MANAGEMENT.md.

## Notes

- A candidate referenced by nothing at all (zero parents, not one) is not this skill's job — that is a dangling entry,
  worth flagging separately, but merging has nothing to fold it into.
