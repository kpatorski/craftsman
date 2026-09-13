# craftsman — content management mechanics

Shared by every skill that mutates `~/.claude/craftsman/` (`enable`, `disable`, `install`, `uninstall`, `rename`,
`merge`). Each loads this file first, then does its own specific work.

## Versioning

If `git` is available and `~/.claude/craftsman/` is not already a repository, initialise one (`git init`) before the
first mutation, and say so once. After every mutating command completes, commit the change with a message naming the
command and what changed (e.g. `enable directive prefer-lombok`, `install protocol from <source>`). If `git` is not
available, skip versioning silently — do not block the command on it.

## Resolving an id

An id is unique across both `directives/` and `protocols/` (validated at every install — see below). To find which kind
an id belongs to and where it lives, check `directives/index.md` first, then `protocols/index.md`. If an id appears in
neither, say so — do not guess a path.

## Duplicate detection (`install`)

Before adding a new directive or protocol, run the same search `search` would run: match the incoming id, title and
description against both indexes. If the *id* already exists:

- **Identical content** (the file bodies match after normalising whitespace) — no conflict, nothing to do, say so.
- **Different content** — never silently overwrite and never rename automatically. Report the conflict (both sources,
  both contents) as a warning and ask the developer how to proceed.

If no id collision exists but a *near-duplicate* is found by title/description (the same kind of match `search`
surfaces), mention it before installing — the developer may prefer to skip the install and use the existing one instead.

## Syntax validation (`install`)

Before a new file is added to `directives/` or `protocols/`, validate it: the mandatory sections are present
(Frontmatter, Schema, the kind-specific body section, i.e. `## Directive` or `## Protocol`), the frontmatter fields
match `core.md`'s contract for its kind, and every relative link it contains resolves to a real file once installed.
Reject with a clear reason rather than installing something broken.

## The `merge` candidate check

`merge` scans both indexes for a directive or protocol that lives in its own file but is referenced (via `composes`,
`steps`, or `uses`) by **exactly one** parent, and by nothing else. Each such candidate is proposed to the developer as
a merge into that one parent — never merged automatically. Declining leaves it exactly as it is.

`install` runs a version of the same check in reverse: if the content being installed already contains, inline,
something that duplicates an existing standalone directive or protocol — or something substantial enough that it would
itself be a good candidate for its own file — propose extracting it and linking to it instead of installing it inline.

## Renaming

`rename <old-id> <new-id>` updates: the id in the entry's own frontmatter, its directory name, every `composes` /
`steps` / `uses` / `overrides` reference to it across both collections, and every link in prose bodies. Refuse if
`<new-id>` already exists (unless it is this same entry) — this is the same uniqueness rule `install` enforces, applied
to the target name.

## Enable / disable

Moves the entry's row between the Enabled and Disabled tables of its category, in the appropriate index
(`directives/index.md` or `protocols/index.md`). Nothing in the entry's own file changes — `enabled-by-default` is what
a fresh install starts from, not the live state. See `EXECUTION.md`, "Loading directives".
