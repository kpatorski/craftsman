---
name: search
description: >
  Answers "do we already have something about X?" — searches `~/.claude/craftsman/directives/index.md`, `protocols/index.md` and `bundles/index.md` (plus every bundle's own member tables) by id, title and description, and returns candidates with links and enabled/disabled status. Trigger: "/craftsman:search", "do we have a directive for...", "is there already a protocol that...", "is there a bundle for...", "check before I write a new one".
argument-hint: "<topic>"
allowed-tools: [Read, Grep]
---

# search

The first step before writing a new directive or protocol, and before `install` accepts one — see `install`'s
duplicate-detection requirement.

## Run this

1. Read `~/.claude/craftsman/directives/index.md`, `~/.claude/craftsman/protocols/index.md`, and
   `~/.claude/craftsman/bundles/index.md` (both tables in every category — Enabled and Disabled), plus every
   `bundles/*/bundle.md` for the entries that live inside one.
2. Match `$ARGUMENTS` against every row's `Id`, `Title`, and (by opening the linked file when the index columns alone
   don't decide it) `description`.
3. If more than one candidate looks plausible from the index alone, open and read each candidate's full file before
   ranking — the index is for finding candidates, not for the final call.
4. Report every real match: id, kind (directive/protocol/bundle), title, enabled/disabled, and the link. If nothing
   matches, say so plainly — do not stretch a weak match into a "sort of" answer.

## Notes

- Read-only. Never modifies an index or a content file.
- If `~/.claude/craftsman/` does not exist yet, say so — nothing is installed to search.
