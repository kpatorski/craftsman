# Changelog

What a developer with content already installed in `~/.claude/craftsman/` needs to know about each plugin version —
not a full commit log. See `MANAGEMENT.md`, "Plugin version" for how this gets surfaced automatically.

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
