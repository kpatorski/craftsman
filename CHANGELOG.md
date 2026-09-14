# Changelog

What a developer with content already installed in `~/.claude/craftsman/` needs to know about each plugin version —
not a full commit log. See `MANAGEMENT.md`, "Plugin version" for how this gets surfaced automatically.

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
