# Changelog

What a developer with content already installed in `~/.claude/craftsman/` needs to know about each plugin version —
not a full commit log. See `MANAGEMENT.md`, "Plugin version" for how this gets surfaced automatically.

## 0.1.8

- Fix: `shows`'s HTML-diff rendering (0.1.7) is now a real, bundled script (`scripts/render_diff.py`) instead of
  hand-rolled Python each time, and always prints a `file://` link for the result — the primary way to hand it to
  the developer, portable across every OS and environment. `--open` (auto-launch the default browser) is now an
  explicit opt-in convenience, not assumed: it's macOS/Linux/Windows-only and does nothing useful in a remote or
  headless environment, and a chat UI's file-card delivery isn't reliably visible either. Found live, immediately
  after 0.1.7: the developer couldn't see the delivered file, then asked for a portable link instead of relying on
  auto-open once that worked but wasn't universal. See `core.md`, the `checkpoint` field's `shows` entry.

## 0.1.7

- Fix: `shows: [...]` now renders a diff beyond a handful of lines as a self-contained local HTML file (dark
  theme), not raw `+`/`-` text pasted into the conversation — a rule in `core.md` covering every checkpoint that
  shows a diff (`review-design-direction`, `refactor-tests`, `refactor-production`, `finish-loop`,
  `MANAGEMENT.md`'s conflict presentation), generalized from what 0.1.3's decision-12 work already built for
  updates alone. Found live: a raw diff pasted mid-`tdd-loop` was flagged as unreadable, and about to recur on
  every class from then on if left as-is. See `core.md`, the `checkpoint` field's `shows` entry.

## 0.1.6

- Fix: a checkpoint's lead-in and `prompt` now must break onto separate lines when they cover more than one
  distinct point, instead of packing everything into one dense paragraph. Found live, twice in a row in the same
  run — the same class of readability failure the 0.1.2 lead-in fix targeted, just not covered by its wording.
  See `EXECUTION.md`, "Checkpoint protocol".

## 0.1.5

- Fix: `search` now finds candidates with `Grep` across all ten files (three top-level indexes plus every
  `bundles/*/bundle.md`) in one pass, instead of `Read`-ing all ten in full on every call. Same coverage — bundle
  membership is still positional, so every bundle still gets looked at — just not loaded wholesale up front. `Read`
  is now reserved for the few candidates that actually need their own `description` checked or need ranking. Found
  live: a plain topic search took noticeably long, flagged directly as disproportionate for a lookup that should
  focus on a handful of matching rows. See `skills/search/SKILL.md`.

## 0.1.4

- Fix: `enable`/`disable` now moves a table row with a bundled script (`scripts/toggle_table_row.py`) instead of a
  hand-edited string-match diff. Found live, in a separate session, running a plain 4-directive enable: three of
  four table edits failed with "string to replace not found" (column widths shift on every row move), forcing
  repeated re-reads, hand-rolled Python just to compute padding, and several minutes for what should have been a
  trivial operation. The script re-reads the file fresh every call, finds the id's current table itself, moves it,
  renumbers, and repads — including converting an emptied table to this content tree's established prose and back.
  Handles every shape in the tree: category sections, a bundle's own tables, and `bundles/index.md`'s differently
  shaped table. See `MANAGEMENT.md`, "Enable / disable".
- Fix: "Plugin version" now covers the case where the version marker reads *newer* than this session's own loaded
  plugin — happens whenever a different, longer-running or more-recently-started session touches the same shared
  `~/.claude/craftsman/` first. Previously undocumented; an agent hitting it had no defined procedure and guessed
  at 60% confidence. See `MANAGEMENT.md`, "Plugin version".

## 0.1.3

- Fix: re-running `install` on a known source now uses a three-way diff (baseline at the recorded `Version`,
  source now, and what's on disk) instead of a two-way diff — a developer's own new entries are never proposed for
  deletion, a hand-edited installed file is never silently overwritten by an upstream change that didn't touch it,
  and a real conflict (both sides changed) is presented as a concrete three-choice checkpoint (accept upstream /
  keep local / show me the diff — inline, or a local dark-theme HTML file for a long one) instead of one side
  winning by default. Found by asking "what happens to a developer's own protocols on update?" and tracing the old
  two-way diff through it — it had no way to tell who made a given difference; the conflict-presentation part was
  refined again live once the first version ("show both diffs, ask") turned out to be too vague to actually follow.
  See `MANAGEMENT.md`, "Checking a known source for updates" and "Presenting a conflict".
- Fix: updating an existing entry's content no longer moves its row between the Enabled and Disabled tables —
  `enabled-by-default` now only ever governs a first install, never a later content update, closing a direct
  contradiction with the "Enable / disable" section (which already said live state isn't the same as
  `enabled-by-default`, but the update path wasn't honoring that). See `MANAGEMENT.md`, "Enable / disable".

## 0.1.2

- Fix: every checkpoint now states which step (id) it's for, in one line, before the actual question — found live
  while running a real task, when a bare question with no lead-in left a developer reading the transcript unable to
  tell what produced it. See `EXECUTION.md`, "Checkpoint protocol".
- Feature: the call stack now mirrors into Claude Code's own task list (`TaskCreate`/`TaskUpdate`/`TaskList`, or
  legacy `TodoWrite`) when those tools are available in the session — a live view alongside the durable session
  file. Silently skipped where the tools aren't present. See `EXECUTION.md`, "`<type>-session-<slug>.md`".

## 0.1.1

- Fix: syntax validation now explicitly rejects frontmatter that isn't valid YAML at all, instead of only implying
  it. See `MANAGEMENT.md`, "Syntax validation".
- Fix: the plugin-version check now covers the case where `~/.claude/craftsman/` already exists but its version
  marker doesn't (content installed before this check existed) — treated as a mismatch instead of silently doing
  nothing. See `MANAGEMENT.md`, "Plugin version".

## 0.1.0

First versioned release. Includes, relative to the initial bundle-based design:

- The two-repo split (`craftsman` for code, a separate workshop repo for content) and the bundle model — themed
  groups of directives/protocols that install and enable together.
- Fix: a directive/protocol/bundle mentions `core.md` by name only, never as a link — the plugin caches its own
  code under a path that changes on every update, so a link written into installed content could never stay valid.
  If your own workshop content still links to `core.md`, see `EXECUTION.md`, "Where the content lives".
- Fix: enabling or disabling a bundle now always cascades to every member, including one you had toggled
  individually before — the previous promise to preserve an individual override across a later bundle-level toggle
  was unimplementable (the file format has no way to record *why* a member is in its current state) and has been
  dropped. See `MANAGEMENT.md`, "Enable / disable".
