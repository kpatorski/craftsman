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
4. Duplicate detection: check `$ARGUMENTS`' id against `search`'s own lookup (id, title, description across all
   three indexes) — this part stays a judgement call, `validate_content.py` runs later, after writing, and cannot
   see content that isn't on disk yet. Stop and ask if a genuine conflict is found; proceed straight through if
   the id is new or the content is identical to what is already installed.
5. Validate syntax (MANAGEMENT.md) — the directive/protocol contract, or the bundle contract if `$ARGUMENTS` is a
   `bundle.md`. Reject with a clear reason on failure.
6. Check for inline content that should be its own file (MANAGEMENT.md's reverse-merge check). Propose extracting it if
   so; proceed either way per the developer's answer.
7. Write the file(s): under `~/.claude/craftsman/directives/<id>/` or `protocols/<id>/` for a standalone entry, or
   under `bundles/<id>/` (with its own `directives/`/`protocols/` subfolders) for a bundle — see MANAGEMENT.md,
   "Installing a bundle". Add its row with `scripts/toggle_table_row.py <index-file> add enabled|disabled
   "<cells>"` (Enabled if `enabled-by-default: true` for a directive, or always-Enabled for a protocol or bundle;
   pass `--after-heading` when the index has more than one category section — the script says so if needed), and
   add or update the `Sources` table entry by hand (a single-row table, not the Enabled/Disabled shape the script
   handles), including its `Version` (the source's current commit sha, when it is a git repository).
7a. Run `scripts/validate_content.py ~/.claude/craftsman` — the last-mile check that the row just added actually
   matches what's on disk (id uniqueness, links, required fields, index completeness). A failure here means step
   7 was done wrong; fix it before committing, never commit past a failure.
8. If `~/.claude/craftsman/` did not exist before this run, this was a first install — mention that a first run of
   `analyse`/`domain-design`/`implement` will now find real content.
9. Commit per MANAGEMENT.md.

## Notes

- Installing a whole workshop source (a git repository of `directives/` + `protocols/` + `bundles/`) is the same
  flow, run once per file or bundle it contains, plus one `Sources` row for the source itself rather than per file.
- Installing a bundle does not install what it `requires` — say so if a requirement is missing, per MANAGEMENT.md.
