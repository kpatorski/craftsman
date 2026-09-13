---
name: install
description: >
  Installs a directive, protocol, or a whole workshop source, from a local path or a URL, into `~/.claude/craftsman/`. Trigger: "/craftsman:install", "install plugin", "install protocol", "add a workshop source".
argument-hint: "<path or URL to a directive.md, protocol.md, or a workshop source>"
allowed-tools: [Read, Write, Edit, Bash, WebFetch, AskUserQuestion]
---

# install

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** in full — duplicate detection, syntax validation, the merge-candidate check, and versioning all apply here.
2. Fetch or read `$ARGUMENTS`.
3. Run duplicate detection (MANAGEMENT.md). Stop and ask if a genuine conflict is found; proceed straight through if the id is new or the content is identical to what is already installed.
4. Validate syntax (MANAGEMENT.md). Reject with a clear reason on failure.
5. Check for inline content that should be its own file (MANAGEMENT.md's reverse-merge check). Propose extracting it if so; proceed either way per the developer's answer.
6. Write the file(s) under `~/.claude/craftsman/directives/<id>/` or `protocols/<id>/`, add its row to the appropriate index (Enabled table if `enabled-by-default: true` for a directive, or always-Enabled for a protocol), and add or update the `Sources` table entry.
7. If `~/.claude/craftsman/` did not exist before this run, this was a first install — mention that a first run of `analyse`/`domain-design`/`implement` will now find real content.
8. Commit per MANAGEMENT.md.

## Notes

- Installing a whole workshop source (a git repository of `directives/` + `protocols/`) is the same flow, run once per file it contains, plus one `Sources` row for the source itself rather than per file.
