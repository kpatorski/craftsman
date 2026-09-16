---
name: install
description: >
  Installs a directive, protocol, bundle, or a whole workshop source, from a local path or a URL, into
  `~/.claude/craftsman/`. Trigger: "/craftsman:install", "install plugin", "install protocol", "install bundle", "add a
  workshop source".
argument-hint: "<path or URL to a directive.md, protocol.md, bundle.md, or a workshop source>"
allowed-tools: [Read, Write, Edit, Bash, WebFetch, AskUserQuestion]
---

# install

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** in full — duplicate detection, syntax validation, installing a
   bundle, the merge-candidate check, and versioning all apply here.
2. If `$ARGUMENTS` matches a `Location` already recorded in some index's `Sources` table, this is a check for
   updates, not a new install — follow MANAGEMENT.md, "Checking a known source for updates" instead of the rest of
   this list.
3. Otherwise, fetch or read `$ARGUMENTS`.
4. Run duplicate detection (MANAGEMENT.md). Stop and ask if a genuine conflict is found; proceed straight through if the
   id is new or the content is identical to what is already installed.
5. Validate syntax (MANAGEMENT.md) — the directive/protocol contract, or the bundle contract if `$ARGUMENTS` is a
   `bundle.md`. Reject with a clear reason on failure.
6. Check for inline content that should be its own file (MANAGEMENT.md's reverse-merge check). Propose extracting it if
   so; proceed either way per the developer's answer.
7. Write the file(s): under `~/.claude/craftsman/directives/<id>/` or `protocols/<id>/` for a standalone entry, or
   under `bundles/<id>/` (with its own `directives/`/`protocols/` subfolders) for a bundle — see MANAGEMENT.md,
   "Installing a bundle". Add its row to the appropriate index (Enabled table if `enabled-by-default: true` for a
   directive, or always-Enabled for a protocol or bundle), and add or update the `Sources` table entry, including its
   `Version` (the source's current commit sha, when it is a git repository).
8. If `~/.claude/craftsman/` did not exist before this run, this was a first install — mention that a first run of
   `analyse`/`domain-design`/`implement` will now find real content.
9. Commit per MANAGEMENT.md.

## Notes

- Installing a whole workshop source (a git repository of `directives/` + `protocols/` + `bundles/`) is the same
  flow, run once per file or bundle it contains, plus one `Sources` row for the source itself rather than per file.
- Installing a bundle does not install what it `requires` — say so if a requirement is missing, per MANAGEMENT.md.
