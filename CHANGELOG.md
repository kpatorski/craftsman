# Changelog

What a developer with content already installed in `~/.claude/craftsman/` needs to know about each plugin version —
not a full commit log. See `MANAGEMENT.md`, "Plugin version" for how this gets surfaced automatically.

## 0.4.0

- Feature: the report is no longer produced only when a run ends. Every time a step writes or updates an artifact
  file (`business-rules.md`, `open-questions.md`, `event-model.md`, `specs/*.md`, or any deliverable a protocol
  names), the report page is regenerated and two lines are printed: `md:` with the file's full path and `html:` with
  a `file://` link that opens the report on that document. Both are always shown as full paths — never just
  "wrote specs/xyz.md". `scripts/render_report.py` gained `--doc <file>` (repeatable) for this; a file it would not
  otherwise look for appears under "Other". The report stays one page holding every document, so links between
  documents keep working and nothing extra lands in the project's `git status`.

## 0.3.0

- Feature: `/craftsman:report` (new `scripts/render_report.py`) renders a project's results — `business-rules.md`,
  `open-questions.md`, `event-model.md`, `specs/` and the session file(s) — as one self-contained, dark-theme HTML
  page in the dashboard's style: navigation on the left, the chosen document rendered on the right, search across
  all documents, links between documents that switch the view, and the state of each session (`active`, `blocked`,
  `done`) shown in the navigation. The markdown stays the source of truth; the page is regenerated from disk each
  time. Written to `.claude/reports/report.html` next to the sessions, so it does not clutter `git status`.
- Feature: it is also generated automatically when an entry-point run finishes (`EXECUTION.md`, "Report"), with the
  link printed at the end. A failure or an empty result never blocks or changes the run. This lives in the plugin's
  execution mechanics, not in a workshop's protocols — nothing to update on the workshop side.
- The report reads the files by name and does not parse their structure, since their formats belong to the workshop;
  a workshop that writes other files gets them only once they are added to the script's list.
- Internal: the markdown renderer used by the dashboard moved to a shared `scripts/_markdown.py`; the dashboard's
  output is unchanged.

## 0.2.1

- Fix: the command descriptions in `/craftsman:help` (and the dashboard's "Commands" section, which shows the same
  block) started in different columns, so the list looked ragged. They are now aligned to one column, and the wrapped
  second lines line up under the first. Text spacing only; nothing about what the commands do changed.

## 0.2.0

- Feature: the `dashboard` (added in 0.1.15) is reworked into something usable day to day. One collapsible row per
  entry (kind, id, title, status) instead of a wall of cards; a bundle is one row that expands to its members. A
  centred, width-limited page instead of one stretched across the whole screen.
- Feature: a "view" button per entry shows the entry's own file inside the page, in a side panel that appears only
  while a file is open ("view" turns into "hide"), instead of `open file` jumping out to the browser's raw file view.
  The file is rendered (headings, tables, lists, code, frontmatter), and a link to another entry inside it switches
  the panel to that entry. All file contents are embedded, so the page still works offline as a single file.
- Feature: search matches by words, in any order, with hyphens treated as spaces and a trailing plural ignored, so
  "tests coverage" finds `check-coverage` — previously the whole query had to appear as one exact string. Searching
  no longer expands every match; only a bundle is opened, and only to reveal a matching member.
- Docs: the command list section is called "Commands" and sits directly above the search box; the page states when
  it was generated, since it is a snapshot (re-run `/craftsman:dashboard` after installing or toggling anything).
  Entries are read from the indexes, so anything added through `/craftsman:install` shows up on the next run.

## 0.1.15

- Fix: `EXECUTION.md`'s session-file contract gives `Checkpoint log`, `Directives in effect`, `Task`, `Status`, and
  `Next` an actual labeled shape instead of free-running prose. Found live, reading a real session file on a
  second machine: only `Call stack` had ever been given a parseable grammar (0.1.13); everything else was a
  numbered list of dense paragraphs with bold words as the only structure — unfindable by grep, unusable as a data
  source for anything beyond a human re-reading the whole log. `Checkpoint log` entries are now `### N.
  \`step-id\`` headings with **Asked:**/**Answer:**/**Decision:**/**Actor:** lines; `Directives in effect` is a
  table; `Task`/`Status`/`Next` get the same labeled-line treatment. `scripts/render_status.py`'s `## Status`
  parser updated to match (now searches for the backtick-quoted word anywhere on the line, not only at its
  start). See `EXECUTION.md`, "`<type>-session-<slug>.md`".
- Feature: a local HTML dashboard (`scripts/render_dashboard.py`, new `dashboard` skill) — dark theme, browses
  every installed bundle/protocol/directive with its own file's description and enabled/disabled state, plus the
  `help` command block, all client-side searchable. Read-only by construction: a static file has no way to write
  back to the disk it was generated from, so each row shows the exact `/craftsman:enable`/`disable` command to
  copy instead of toggling anything live. See `MANAGEMENT.md`, "Dashboard".

## 0.1.14

- Docs: `domain-design`'s command description, `help` text and README now say what the starter workshop's
  `domain-design` does since the workshop moved to slices: every event first, then one use case at a time from its
  rules to a reviewed spec to implemented, committed code, with a direction check after each. Nothing in the plugin's
  code changed — this is the workshop's protocols (`slice-loop`, `confirm-direction`) and the text describing them.
  Update the workshop source with `/craftsman:install <same-source-url>`; a `domain-design` session already in
  progress has a Call stack in the old shape and needs re-deriving on resume.

## 0.1.13

- Feature: a Claude Code status line showing the current command -> batch -> protocol -> directive, always
  visible instead of only readable from the session file or the task list. `scripts/render_status.py` (new)
  parses the session's Call stack and prints one compact line; the new `statusline-setup` skill wires it into
  `settings.json` (a plugin cannot register a status line on install — this is always a one-time manual step).
  See `MANAGEMENT.md`, "Status line".
- Fix: `EXECUTION.md`'s own example of the Call stack format was stale — it showed a flat, single-line `a > b >
  c (active)` shape, but real session files already write an indented, one-line-per-level tree with free-text
  status annotations (`(active — batch 2 of 4)`, `(blocked — waiting on X)`) and an undocumented `-> hand-off:`
  variant. The example now matches actual practice; this is what makes it parseable by a script at all.

## 0.1.12

- Fix: `analyse`/`domain-design`/`implement` resolve their entry-point protocol by role (`entry-point: true` in
  the installed workshop's `protocols/index.md`), not by a hardcoded content path. The hardcoded path was already
  dead per EXECUTION.md's own dispatch rules, silently broke if the entry point lived inside a bundle, and left
  `rename` able to orphan a command. This was actually shipped in the previous commit, without the version bump
  its own behaviour-change rule requires — caught and corrected here rather than left unbumped.
- Feature: the session file's checkpoint log now records who answered a `type: ask` checkpoint (`human:<git
  user.name or user.email>`, never left blank), and resuming a session says plainly when the actor resuming
  differs from the log's most recent entries — the same "say what differs, never assume" treatment
  `EXECUTION.md` already gives to directive-version drift, extended to identity. See `EXECUTION.md`, "Checkpoint
  log" and "Resuming".

## 0.1.11

- Fix: every remaining mutating command now has a deterministic script backing its mechanics, closing out the
  same class of fix as 0.1.10's `validate_content.py`/`rename_id.py`. `scripts/merge_candidates.py` (the `merge`
  scan), `scripts/list_content.py` (`list`, prints tables verbatim instead of re-composing them), and
  `scripts/uninstall_id.py` (dry-run reference check + `--yes` removal) are new; `scripts/toggle_table_row.py`
  gained `add`/`remove` modes for `install`/`uninstall`'s table-row mechanics, on top of its existing
  `enable`/`disable`. See `MANAGEMENT.md` and each command's own `SKILL.md`.
- Fix: a real bug found while building the above — an early version of `merge_candidates.py` used a single-line
  regex to read `composes`/`steps`/`uses` and silently missed every reference inside a multi-line flow list
  (`production-code`'s own `composes:` wraps across 3 lines), undercounting references and misclassifying shared
  directives as merge candidates. Fixed by extracting `validate_content.py`'s already-correct frontmatter parser
  into a shared `scripts/_frontmatter.py` both scripts import, instead of a second, weaker parser existing at all.

## 0.1.10

- Fix: `scripts/validate_content.py` replaces prose-only duplicate/id/link/syntax validation in `MANAGEMENT.md`
  with one deterministic, repeatable script. Found live: a real id collision (`event-storming`, used by both a
  bundle and its own entry protocol) sat unnoticed in a workshop source because every session re-derived these
  checks from prose instead of running a shared implementation. See `MANAGEMENT.md`, "Duplicate detection" and
  "Syntax validation".
- Fix: `scripts/rename_id.py` replaces prose-only reference-finding for `rename` with a deterministic,
  whole-token substitution across every file, directory, and table row referencing an id — the same class of risk
  as the bug above (a multi-file change with an easy-to-miss spot), applied to the one remaining mutating command
  with no script backing it. See `MANAGEMENT.md`, "Renaming".
- Fix: `help` now prints a fixed, pre-written block instead of a set of talking points the agent re-composed (and
  re-read a file for) on every invocation — the same class of fix as `search`'s 0.1.5 change, applied to a command
  that never needed any live interpretation at all. See `skills/help/SKILL.md`.

## 0.1.9

- Fix: the "diff beyond a handful of lines" threshold for `shows`'s HTML rendering is now a precise 3 lines, not
  a vague "handful" — the developer asked for a concrete number after confirming the mechanism itself works. See
  `core.md`, the `checkpoint` field's `shows` entry.

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
