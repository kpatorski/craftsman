---
name: search
description: >
  Answers "do we already have something about X?" — searches `~/.claude/craftsman/directives/index.md`,
  `protocols/index.md` and `bundles/index.md` (plus every bundle's own member tables) by id, title and description,
  and returns candidates with links and enabled/disabled status. Trigger: "/craftsman:search", "do we have a directive
  for...", "is there already a protocol that...", "is there a bundle for...", "check before I write a new one".
argument-hint: "<topic>"
allowed-tools: [Read, Grep, Glob, Bash]
disallowed-tools: [Write, Edit, NotebookEdit]
context: fork
agent: Explore
background: false
---

# search

The first step before writing a new directive or protocol, and before `install` accepts one — see `install`'s
duplicate-detection requirement.

## Run this

1. Run `scripts/search_content.py ~/.claude/craftsman "$ARGUMENTS"`. It looks the words of the phrase up in the id,
   title and description of every installed directive, protocol, bundle and bundle member, and prints the matches
   as JSON, best first, each with its kind, title, description, whether it is enabled, its bundle and its path. When
   it says nothing is installed, say so (see Notes).
2. Weigh the matches: a match on a word of the description alone may be about something else. `Read` a candidate's
   own file only when its description does not decide it — never the whole index or every bundle.
3. Report every real match: id, kind (directive/protocol/bundle), title, enabled/disabled, and the link. If nothing
   matches, say so plainly — do not stretch a weak match into a "sort of" answer.

## Notes

- Read-only. Never modifies an index or a content file. It runs in its own context (`context: fork`), so the script's
  output and the files it opens stay out of the conversation that asked — only the matches come back — and the tools
  that write are taken away there (`disallowed-tools`), not merely left unapproved.
- If `~/.claude/craftsman/` does not exist yet, say so — nothing is installed to search.
