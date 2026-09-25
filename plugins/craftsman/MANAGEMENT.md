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

**The marker can also read *newer* than this running session's own plugin.** `~/.claude/craftsman/` is one shared
path on disk — if another session (or the developer, from a terminal) updated the plugin and touched this content
tree first, that session already wrote the newer version into the marker, while this session loaded its own
plugin.json at its own start and has not changed since. This is not a broken state and does not need "unknown"
handling: say plainly, once, that a *different* session updated the plugin to a newer version than this one has
loaded (old = this session's version, new = the marker's), and that a fresh session picks it up (see README.md,
"Updating" — a running session keeps the version it started with). Never overwrite the marker with this session's
own, older version in this direction — that would erase the newer session's record for no reason.

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
new install — it is a check. Fetch the source's current state (full clone with history — never `--depth 1` here;
the next paragraph explains why) and compare its commit sha to the `Version` already recorded for that row:

- **Same sha** — nothing changed since the last sync. Say so, stop.
- **Different sha** — classify every file, then act per file. See below.

This never runs on its own — only when the developer explicitly re-runs `install` with a URI already recorded as a
source. Nothing fetches in the background.

### Three-way classification, not a two-way diff

A plain diff between "source now" and "what's on disk" cannot tell whether a difference came from upstream or from
the developer's own hand — and a developer who has added their own directives or protocols, or hand-edited an
installed one, is not a hypothetical, it's the normal way this tool gets used. The fix needs a third point of
reference: the **baseline**, i.e. the source's content at the sha already recorded in `Version` — `git show
<Version>:<path>` against the fetched clone, since the clone now holds full history. Classify each file by
comparing all three (baseline, source-now, on-disk):

| On-disk vs. baseline | Source-now vs. baseline | Meaning              | Action                                                             |
|-----------------------|--------------------------|-----------------------|----------------------------------------------------------------------|
| same                  | changed                  | clean upstream update | show it, apply after agreement — as before                          |
| changed               | same                     | developer's own edit  | leave it untouched; say it was skipped and why                      |
| changed               | changed                  | real conflict         | see "Presenting a conflict" below — never resolved silently          |
| n/a — not in baseline or source | n/a              | developer's own new file | never a deletion candidate — it didn't come from this source       |
| n/a — not in source anymore | same as baseline      | removed upstream       | propose deleting it                                                  |
| n/a — not in source anymore | changed locally         | removed vs. local work | keep it; say plainly upstream deleted it, then ask what to do        |

Applying a change still re-runs syntax validation and duplicate detection on every touched file exactly as a fresh
install would (a changed *id* whose content now differs from what's installed is expected here, not a conflict to
reject) — but never touches which table (Enabled/Disabled) an existing entry's row sits in; see "Enable / disable"
below.

### Presenting a conflict

A vague "show both diffs" is not an instruction anyone could follow the same way twice. For each conflicted id:

1. State plainly that this id has two different versions since the last sync — yours and upstream's. Name the id.
2. Offer exactly three choices, always in this order, and wait for one:
   - **Accept upstream** — overwrite the local copy with the source's current version.
   - **Keep local** — leave the file exactly as it is; upstream's change is not applied to this file.
   - **Show me the diff** — before deciding, see the actual change.
3. On "show me the diff": render it per `core.md`'s `shows` rule — baseline → local and baseline → upstream, one
   section per conflicted id if several are being reviewed together. Loop back to step 2 for a real decision;
   "show me the diff" is never itself the final answer for a file.
4. Whatever gets chosen — accept upstream or keep local — is that file's decision for "Moving `Version` forward"
   below. A merge-by-hand is just "keep local" followed by the developer editing the file themselves afterward;
   this protocol does not attempt to auto-merge content.

**No baseline available** (source isn't a git repository, `Version` is empty, or the recorded sha is gone from
history) — there is nothing to classify against. Fall back to the old two-way behavior, but safer: every
difference is shown and asked about individually, and a file present on disk but absent from the source is never
proposed for deletion.

### Moving `Version` forward

Declining the check entirely leaves `Version` untouched — the next check shows the same diff again, as before.
Once every file in the diff has an explicit decision (applied / accepted upstream / kept local), `Version` moves to
the new sha — **including for files where the developer chose "keep local".** This is not data loss: the baseline
means "the last state of the source this tool has seen," not "the state currently on disk." Without moving it, a
file with a kept-local decision would show up as the same conflict forever. The rule is all-or-nothing on the
decision, not on the outcome: never move `Version` if any file in the diff was left without an explicit decision —
otherwise a skipped upstream change silently drops off the radar for good.

## Duplicate detection (`install`)

**Run `scripts/validate_content.py <content-root>` for id uniqueness, link validity, required fields/sections, and
`requires` resolution — every deterministic check in this section and the next, in one pass, instead of an agent
re-deriving them from prose each time.** Found live: a real id collision (`event-storming`, used by both a bundle
and its own entry protocol) sat unnoticed in the content tree because every session had re-implemented this
checking ad hoc — including this plugin's own author, more than once, in scratch scripts nobody kept. Treat a
non-zero exit as a rejection reason to report to the developer. The prose in this section and "Syntax validation"
below is the specification the script encodes — read it to understand or extend a check, never to re-implement one
by hand. `search`'s own near-duplicate matching (title/description, not id) is the one part of this section the
script does not cover — that stays a judgement call.

Before adding a new directive, protocol, or bundle, run the same search `search` would run: match the incoming id,
title and description against all three indexes (`directives/index.md`, `protocols/index.md`, `bundles/index.md`,
plus every `bundles/*/bundle.md` for members that live inside one). If the *id* already exists:

- **Identical content** (the file bodies match after normalising whitespace) — no conflict, nothing to do, say so.
- **Different content** — never silently overwrite and never rename automatically. Report the conflict (both sources,
  both contents) as a warning and ask the developer how to proceed.

If no id collision exists but a *near-duplicate* is found by title/description (the same kind of match `search`
surfaces), mention it before installing — the developer may prefer to skip the install and use the existing one.

## Syntax validation (`install`)

Covered by `scripts/validate_content.py`, same as "Duplicate detection" above — this section is what it checks,
not a separate manual step.

Before a new file is added to `directives/` or `protocols/`, validate it: the frontmatter parses as YAML at all
(reject with the parser's own error if it doesn't — malformed YAML never reaches the checks below), the mandatory
sections are present (Frontmatter, Schema, the kind-specific body section, i.e. `## Directive` or `## Protocol`),
the frontmatter fields match `core.md`'s contract for its kind, and every relative link it contains resolves to a
real file once installed — except mentions of `core.md` itself, which must be name-only (`` `core.md` ``), never a
link: it lives in this plugin's own code, not in installed content, so no link written into content could stay
valid across a plugin update. See `EXECUTION.md`, "Where the content lives". Reject with a clear reason rather than
installing something broken.

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
every duplicate check, and is caught only by this count. `scripts/validate_content.py` re-runs this too — it is the
"run the whole script again" step, not a separate manual re-check.

## Installing a bundle

A bundle installs as a unit: materialize `bundles/<id>/bundle.md` plus its `directives/` and `protocols/`
subfolders, run duplicate detection and syntax validation on every file it contains (the bundle itself and each
member), add one row to `bundles/index.md` (`scripts/toggle_table_row.py bundles/index.md add enabled "<cells>"`),
one row per member to the bundle's own `bundle.md` tables (same script, `--after-heading "## Protocols"` or
`"## Directives"`), and one `Sources` entry for the bundle as a whole rather than one per member file. If any
`requires` it declares is not already installed, say so before finishing — installing a bundle does not install
what it requires; that is a separate, explicit step, same as enabling one (see "Resolving `requires`" below). Run
`scripts/validate_content.py` once at the end, after every row is in place, not once per member.

## The `merge` candidate check

**Run `scripts/merge_candidates.py <content-root>`** for the scan itself — it walks every directive and protocol,
top-level and inside every bundle, and reports every one that lives in its own file but is referenced (via
`composes`, `steps`, or `uses`) by **exactly one** parent, and by nothing else. This is unrelated to `requires`: a
bundle required by several others is not a merge candidate, `requires` is not a reference this check counts. An
earlier hand-rolled version of this scan used a single-line regex on these fields and silently missed every
reference inside a multi-line flow list (`composes: [a, b,` wrapped across lines) — the script parses the whole
frontmatter properly instead (see `scripts/_frontmatter.py`) and does not have that failure mode.

Each candidate the script reports is proposed to the developer as a merge into that one parent — never merged
automatically. Declining leaves it exactly as it is. The script only scans and reports; the actual inlining (step
4 below) is not automated — a merge changes prose structure, which needs judgment, not just reference-counting.

`install` runs a version of the same check in reverse: if the content being installed already contains, inline,
something that duplicates an existing standalone directive or protocol — or something substantial enough that it would
itself be a good candidate for its own file — propose extracting it and linking to it instead of installing it inline.

## Renaming

**Run `scripts/rename_id.py <content-root> <old-id> <new-id>`** — it renames the entry's directory and replaces
every whole-token occurrence of the id across every `.md` file under the root in one pass (frontmatter `id`,
`composes` / `steps` / `uses` / `requires` / `overrides`, prose links, backtick mentions, index and `bundle.md`
table rows) — instead of an agent hand-finding each reference, which is exactly how a real, live id collision
(`event-storming`, see `validate_content.py`'s docstring) went unnoticed for a while: one missed spot in a
multi-file change is invisible until something else breaks. Refuses outright (no files touched) if `<new-id>`
already exists anywhere — the same uniqueness rule `install` enforces, applied to the target name.

**Read the printed diff, not just the replacement count, before committing** — confirmed live against a real
case (renaming `naming`): a whole-token match cannot distinguish "the `naming` directive" from ordinary prose
that happens to contain the same word ("naming decisions"), so a false-positive replacement is possible when the
id is also an English word. This is a narrower, more visible risk than the missed-reference problem the script
replaces — review it the same way any other mutation's diff gets reviewed before commit (see "Versioning"). The
script also does not re-pad a table whose id column changed width; re-run the affected row through
`scripts/toggle_table_row.py` (disable then re-enable it) if the column looks wrong, before committing. Run
`scripts/validate_content.py` afterward either way — it catches an id left un-renamed in one table but not
another, the last-mile check this script does not replace.

Renaming a directive or protocol never moves it between the top level and a bundle, or between bundles — only its
id and directory name change, in place. Renaming a bundle itself additionally updates every other bundle's
`requires` list that names the old id — `rename_id.py` finds these the same way it finds any other reference.

## Enable / disable

Moves the entry's row between the Enabled and Disabled tables of its category, in the appropriate index
(`directives/index.md` or `protocols/index.md` for a fundament entry; the bundle's own `bundle.md` — its `##
Protocols` / `## Directives` tables — for an entry that lives inside one). Nothing in the entry's own file
changes — `enabled-by-default` is what a fresh install starts from, not the live state. See `EXECUTION.md`,
"Loading directives". Updating an entry that already exists (see "Checking a known source for updates" above)
never moves its row either — `enabled-by-default` governs only the first install of a given id, never a later
content update to it.

**Always toggle with `scripts/set_enabled.py <content-root> enable|disable <id>`** — the whole of this section as one
script, called by the `enable`/`disable` skills and by the dashboard's switches alike, so the two cannot disagree. It
resolves the id, applies the bundle cascade and `requires` resolution below, moves every row, and commits (see
"Versioning"). When the toggle would also change other bundles it changes nothing and exits 3 with the question to
put to the developer; re-run with `--yes` on agreement. An unknown id, or a requirement that is not installed at
all, exits 2.

Rows themselves move through `scripts/toggle_table_row.py <file> <id> <enable|disable>`, never by hand-editing the
table with a string-match tool. Every row move changes the column widths of a correctly-padded table, so a hand-edit
needs to reproduce the whole table's padding on every change — slow, and it fails outright the moment the file has
drifted from whatever copy is still in context. The script re-reads the file fresh every time, moves the row,
renumbers, and repads both tables, including converting a table that becomes empty into this content tree's
one-line prose ("Empty — nothing has been switched off yet.") and back. A moved row is always appended at the end of
its destination table: round-tripping a row restores its membership, not its position in the list.

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

## Status line

`scripts/render_status.py` renders one line — the current session's Call stack (see `EXECUTION.md`, "Call
stack"), deepest step first, plus that step's protocol's `uses:` directives — for Claude Code's native status
line feature. It reads the JSON Claude Code passes a `statusLine` command on stdin, locates
`<project>/.claude/sessions/*.md` (preferring an `active` file over a `blocked` one, most recently modified
first), and never raises: any failure prints a short, honest fallback line instead of breaking the status line.

Claude Code has no mechanism for a plugin to register a status line on install — it is always a one-time,
explicit edit to `settings.json` (user- or project-level). The `statusline-setup` skill does this edit; see its
own file for the exact steps. It never overwrites an existing `statusLine` entry without asking, and always shows
the change as a diff before writing — the same discipline as any other change to a developer's own configuration.

## Dashboard

`scripts/dashboard_server.py` is a small local web server (stdlib only), started by the `dashboard` skill, serving
one page meant to stay open in a browser on a second screen. It shows the projects it was started from — their
session stacks (the Call stack of every session file, collapsed to the current step), artifacts, specs and session
logs — and the installed content with its enabled/disabled state, the command list, and the plugin's and sources'
versions. It polls the files it shows once a second and pushes a change to the page, which re-reads only then: no
re-running a script, no reload.

**What the page may write: enable/disable, and nothing else.** A switch calls `set_enabled.py` (see "Enable /
disable"), so a click does exactly what `/craftsman:enable` / `/craftsman:disable` would, including the commit and
the question when other bundles would change too. Install, update, uninstall, rename and merge need the agent's
judgement — duplicate detection, three-way update conflicts, reverse-merge proposals — which a server cannot give,
so the page offers them as commands to copy into Claude CLI.

It binds `127.0.0.1` only and refuses a write that does not come from its own page (Host check plus a custom
header, which another site cannot send without a CORS preflight the server never answers). One server serves every
project it was started from; starting it from another project adds that project. A server left running by an
older plugin version is replaced on the next start. It exits by itself after 8 hours with no page open. State:
`~/.claude/craftsman-dashboard.json`; log: `~/.claude/craftsman-dashboard.log`.

`scripts/render_dashboard.py` still renders the old static, read-only snapshot of the installed content to a
single HTML file — kept for a machine where a local server is not wanted; the skill no longer uses it.
