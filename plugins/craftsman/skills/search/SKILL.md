---
name: search
description: >
  Answers "do we already have something about X?" — searches `~/.claude/craftsman/directives/index.md`,
  `protocols/index.md` and `bundles/index.md` (plus every bundle's own member tables) by id, title and description, and
  returns candidates with links and enabled/disabled status. Trigger: "/craftsman:search", "do we have a directive
  for...", "is there already a protocol that...", "is there a bundle for...", "check before I write a new one".
argument-hint: "<topic>"
allowed-tools: [Read, Grep]
---

# search

The first step before writing a new directive or protocol, and before `install` accepts one — see `install`'s
duplicate-detection requirement.

## Run this

1. **`Grep`, not `Read`, for the first pass** — the candidate set lives across up to ten files (the three top-level
   indexes plus every `bundles/*/bundle.md`, since bundle membership is positional per `core.md` and only visible by
   opening each one), and reading all of them in full on every search is the slow, expensive way to answer "does
   this exist". One `Grep` call, case-insensitive, for `$ARGUMENTS` (and its individual significant words if it's a
   phrase) across `~/.claude/craftsman/directives/index.md`, `~/.claude/craftsman/protocols/index.md`,
   `~/.claude/craftsman/bundles/index.md`, and `~/.claude/craftsman/bundles/*/bundle.md` gets the same coverage —
   every `Id`, `Title`, and row — for a fraction of the cost. If `~/.claude/craftsman/` does not exist yet, `Grep`
   simply finds nothing there; check for the directory separately to give the right message (see Notes).
2. From the grep hits, collect candidate ids (a hit on a table row's `Id`/`Title` cell is enough to shortlist it).
3. Only `Read` a candidate's own file when the grep hit alone doesn't decide it — a row whose `Id`/`Title` didn't
   match but might be relevant by `description`, or more than one plausible candidate that needs ranking. This is
   the only point where full files get opened, and only the specific candidates, never the whole index or every
   bundle.
4. Report every real match: id, kind (directive/protocol/bundle), title, enabled/disabled, and the link. If nothing
   matches, say so plainly — do not stretch a weak match into a "sort of" answer.

## Notes

- Read-only. Never modifies an index or a content file.
- If `~/.claude/craftsman/` does not exist yet, say so — nothing is installed to search.
