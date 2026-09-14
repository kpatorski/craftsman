# craftsman — content management mechanics

Shared by every skill that mutates `~/.claude/craftsman/` (`enable`, `disable`, `install`, `uninstall`, `rename`,
`merge`). Each loads this file first, then does its own specific work.

## Versioning

If `git` is available and `~/.claude/craftsman/` is not already a repository, initialise one (`git init`) before the
first mutation, and say so once. After every mutating command completes, commit the change with a message naming the
command and what changed (e.g. `enable directive prefer-lombok`, `install protocol from <source>`). If `git` is not
available, skip versioning silently — do not block the command on it.

## Plugin version

`~/.claude/craftsman/.craftsman-plugin-version` records which version of this plugin last touched this content tree
— read from this plugin's own `.claude-plugin/plugin.json`, found the same way this file itself was loaded. Every
command compares the two before doing anything else — this is a local, offline comparison of two files already on
disk, cheap enough to run every time, never a network call. On a mismatch: say once, plainly, that the plugin
updated since content was last touched (old version → new version), point to this plugin's own `CHANGELOG.md`, and
write the new version into the marker. This is a fact worth knowing, not a warning to act on — it never triggers or
suggests an automatic update; the plugin itself updates only when the developer runs it themselves (see README.md,
"Updating"). If `~/.claude/craftsman/` does not exist yet, skip this check — a first install writes the marker fresh.
If `~/.claude/craftsman/` exists but the marker file does not (content installed before this file existed), treat it
the same as a mismatch — say so once, using "unknown" as the old version, and write the marker.

## Resolving an id

An id is unique across `directives/`, `protocols/`, and `bundles/` together (validated at every install — see below).
To find which kind an id belongs to and where it lives, check `directives/index.md`, `protocols/index.md`, then
`bundles/index.md`. A directive or protocol may live at the top level or inside a bundle's own `bundle.md` — check
the top-level index first, then every `bundles/*/bundle.md` in turn. If an id appears nowhere, say so — do not guess
a path.

A bare `$ARGUMENTS` id is never prefixed with its kind (no `enable directive <id>` vs `enable bundle <id>`) — ids are
globally unique, so the lookup above always resolves to exactly one kind, one place.

## Checking a known source for updates (`install`)

If `$ARGUMENTS` matches the `Location` of a `Source` already recorded in any index's `Sources` table, this is not a
new install — it is a check. Fetch the source's current state and compare its commit sha to the `Version` already
recorded for that row:

- **Same sha** — nothing changed since the last sync. Say so, stop.
- **Different sha** — say what changed (new, changed, or removed files, from a diff against what's installed) and
  ask whether to apply it. Applying re-runs syntax validation and duplicate detection on every changed file exactly
  as a fresh install would (see below — a changed *id* whose content differs from what's installed is expected here,
  not a conflict to reject), then updates the `Sources` row's `Version` to the new sha. Declining leaves everything
  as it is, including `Version` — the next check shows the same diff again.

This never runs on its own — only when the developer explicitly re-runs `install` with a URI already recorded as a
source. Nothing fetches in the background.

## Duplicate detection (`install`)

Before adding a new directive, protocol, or bundle, run the same search `search` would run: match the incoming id,
title and description against all three indexes (`directives/index.md`, `protocols/index.md`, `bundles/index.md`,
plus every `bundles/*/bundle.md` for members that live inside one). If the *id* already exists:

- **Identical content** (the file bodies match after normalising whitespace) — no conflict, nothing to do, say so.
- **Different content** — never silently overwrite and never rename automatically. Report the conflict (both sources,
  both contents) as a warning and ask the developer how to proceed.

If no id collision exists but a *near-duplicate* is found by title/description (the same kind of match `search`
surfaces), mention it before installing — the developer may prefer to skip the install and use the existing one instead.

## Syntax validation (`install`)

Before a new file is added to `directives/` or `protocols/`, validate it: the mandatory sections are present
(Frontmatter, Schema, the kind-specific body section, i.e. `## Directive` or `## Protocol`), the frontmatter fields
match `core.md`'s contract for its kind, and every relative link it contains resolves to a real file once installed —
except mentions of `core.md` itself, which must be name-only (`` `core.md` ``), never a link: it lives in this
plugin's own code, not in installed content, so no link written into content could stay valid across a plugin
update. See `EXECUTION.md`, "Where the content lives". Reject with a clear reason rather than installing something
broken.

A `bundle.md` validates the same way, against `core.md`'s `bundle` fields (`id`, `title`, `description`, `requires?`
only — reject a `bundle.md` that tries to list its members as a field, that belongs to directory placement, not
frontmatter): Frontmatter, Schema, `## Bundle`, `## Protocols`, `## Directives` (the last two hold this bundle's own
Enabled/Disabled tables — either may say "None" when the bundle has no members of that kind, but the heading stays).
If `requires` names a bundle id that does not resolve, reject with that reason — same as any other dangling
reference.

After every mutating command that touches the population of `directives/`, `protocols/`, or any `bundles/*/` folder,
re-run the id-set check: every id physically on disk appears in exactly one Enabled/Disabled table (its own index if
fundament, its bundle's `bundle.md` if not), and every id in a table exists on disk. A table silently holding the
wrong-but-still-valid content for its position (a copy-paste into the wrong section) passes every link check and
every duplicate check, and is caught only by this count.

## Installing a bundle

A bundle installs as a unit: materialize `bundles/<id>/bundle.md` plus its `directives/` and `protocols/`
subfolders, run duplicate detection and syntax validation on every file it contains (the bundle itself and each
member), add one row to `bundles/index.md`, and one `Sources` entry for the bundle as a whole rather than one per
member file. If any `requires` it declares is not already installed, say so before finishing — installing a bundle
does not install what it requires; that is a separate, explicit step, same as enabling one (see "Resolving
`requires`" below).

## The `merge` candidate check

`merge` scans every directive and protocol — top-level and inside every bundle — for one that lives in its own file
but is referenced (via `composes`, `steps`, or `uses`) by **exactly one** parent, and by nothing else. Each such
candidate is proposed to the developer as a merge into that one parent — never merged automatically. Declining leaves
it exactly as it is. This is unrelated to `requires`: a bundle required by several others is not a merge candidate,
`requires` is not a reference this check counts.

`install` runs a version of the same check in reverse: if the content being installed already contains, inline,
something that duplicates an existing standalone directive or protocol — or something substantial enough that it would
itself be a good candidate for its own file — propose extracting it and linking to it instead of installing it inline.

## Renaming

`rename <old-id> <new-id>` updates: the id in the entry's own frontmatter, its directory name, every `composes` /
`steps` / `uses` / `overrides` reference to it across every collection (top-level and every bundle), and every link
in prose bodies. Refuse if `<new-id>` already exists anywhere (unless it is this same entry) — this is the same
uniqueness rule `install` enforces, applied to the target name.

Renaming a directive or protocol never moves it between the top level and a bundle, or between bundles — only its
id and directory name change, in place. Renaming a bundle itself additionally updates every other bundle's
`requires` list that names the old id.

## Enable / disable

Moves the entry's row between the Enabled and Disabled tables of its category, in the appropriate index
(`directives/index.md` or `protocols/index.md` for a fundament entry; the bundle's own `bundle.md` — its `##
Protocols` / `## Directives` tables — for an entry that lives inside one). Nothing in the entry's own file
changes — `enabled-by-default` is what a fresh install starts from, not the live state. See `EXECUTION.md`,
"Loading directives".

**Enabling or disabling a bundle** moves its row in `bundles/index.md`, and cascades: every member id moves to the
same table too, in the same command — including one the developer had toggled individually before this bundle-level
command ran. A bundle's own `bundle.md` records only current table position, nothing about how a member got there,
so there is nothing to preserve selectively: an individual toggle inside an enabled bundle is a statement about
*right now*, not a standing exception the next bundle-level command must remember. Say plainly that the cascade
overwrites any individual state, so the developer can re-toggle after if they still want the exception.

**Resolving `requires` on enable:** before enabling a bundle, check every id in its `requires`. Installed and
enabled — proceed. Installed but disabled — ask whether to enable it too (default yes) before continuing. Not
installed at all — name it, explain that the bundle depends on it, and stop; do not partially enable.

**Resolving `requires` on disable:** before disabling a bundle, check whether any other **enabled** bundle names it
in `requires`. If so, name that bundle and ask whether to disable it too (a bundle can't stay enabled without
something it requires) or stop and leave both as they are. Never leave an enabled bundle silently missing a
requirement.
