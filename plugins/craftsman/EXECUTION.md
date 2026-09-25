# craftsman — execution mechanics

Shared by all three entry-point skills (`analyse`, `domain-design`, `implement`) and by any further entry point a
workshop adds. Each entry-point skill loads this file first, then runs its own protocol. Nothing here is specific to one
workshop's content — this describes how craftsman executes *any* protocol, whichever workshop it came from.

## Where the content lives

Directives and protocols are not bundled with this plugin — they live at `~/.claude/craftsman/` (`directives/`,
`protocols/`, each with its own `index.md`, plus `bundles/` for content grouped and enabled as a themed unit — see
`core.md`, "Bundle"), installed separately via `craftsman install` and updated independently of plugin updates. See
`core.md` for the format every directive, protocol, and bundle file follows.

If `~/.claude/craftsman/` does not exist yet, this is a first run: say so, and offer to install the default starter
workshop from the source recorded in this plugin's own configuration (see the `install` skill). Do not fabricate
directives or protocols — if there is truly nothing installed, tell the developer and stop.

A directive, protocol, or bundle file mentions `core.md` by name only, never as a link — this plugin caches its own
code under a path that changes on every update, so no link written into installed content could stay valid. `core.md`
always means the one belonging to *this running plugin*: already loaded, the same way this file was.

## Dispatch

0. Run the plugin-version check — `MANAGEMENT.md`, "Plugin version" — before anything else. A local comparison of
   two files already on disk, not a network call; skip it only when step 1 below is about to report that
   `~/.claude/craftsman/` does not exist yet.
1. Find the entry-point protocol matching the invoked skill (`analyse`, `domain-design`, `implement`, or a
   workshop-added one carrying `entry-point: true`) in `~/.claude/craftsman/protocols/index.md`.
2. Read its `## Protocol` section and walk it top to bottom.
3. When a protocol's body offers several alternatives (each with its own `match`, e.g. `implement`'s five scenarios),
   read the task against every alternative's `match` and pick the best fit. If none fits cleanly, say so and ask the
   developer whether to proceed with the closest one or stop — never invent a process none of them describe.
4. A chosen protocol's `steps` are walked in order. A step that is itself a composing protocol is entered recursively —
   nesting goes as deep as the content does.
5. A protocol with `repeat-until` repeats its `steps` as one iteration, re-checking the condition after each pass, until
   it holds.

**A step that lives inside a bundle only runs if that bundle is enabled.** A fundament protocol's `steps` can name a
step that lives inside a bundle (see `core.md`'s "Bundle" — this is normal, not an exception). Before entering such a
step, check `bundles/index.md`: bundle enabled → proceed as any other step; bundle installed but disabled, or not
installed at all → stop at that point, name the bundle and what it would take to proceed (`enable bundle <id>`, or
`install` first if it is missing), and ask rather than silently skipping the step or inventing a substitute.

## Loading directives

A step loads only the directives its own `uses` field names, plus any directive named in an ancestor protocol's
`overrides` that targets this step or a directive it would otherwise load. This is deliberately not a blind scan of
every enabled directive on every step — see `core.md`, "Fields specific to `protocol`".

A directive named in `uses` that is itself composing (has `composes`) pulls in every directive it composes, recursively,
unless an ancestor's `overrides` says otherwise for this call.

Only **enabled** directives apply. A directive's current enabled/disabled state is its table membership — in
`~/.claude/craftsman/directives/index.md` for a fundament directive, or in its bundle's own `bundle.md` for one that
lives inside a bundle (and that bundle must itself be enabled in `bundles/index.md`, or the directive does not apply
regardless of its own table) — **not** its own `enabled-by-default` frontmatter field, which only decided which
table it landed in in the first place, at install time. `craftsman enable` / `craftsman disable` move a row between
the two tables; nothing in the directive's own file changes.

## Applying an `overrides` map

Before a step that appears as a key in the chosen protocol's `overrides` runs — or before a directive named as a key
would otherwise be loaded by that step — apply the stated change for this call only: skip the step, force its outcome,
or relax the named rule. Neither the step nor the directive itself is touched; the override is scoped to this one run of
the overriding protocol.

## `<type>-session-<slug>.md` — the state file

One file per task, under `.claude/sessions/` in the project (`.claude/sessions/<entry>-session-<slug>.md`, e.g.
`implement-session-cancel-reservation.md`), not the project root — so a task in progress never clutters `git status`.
`<entry>` is the invoked skill's name (`analyse`, `domain-design`, `implement`). The filename slug is a short kebab-case
reduction of the task statement. `session=<path>` on the invocation overrides the location entirely.

**First use in a project:** check whether `.claude/sessions/` and `.claude/reports/` (see "Report", below) are covered
by `.gitignore`. If not, say so and offer to add the missing lines.

Written in English regardless of conversation language. Holds:

- **Task** — three labeled lines: **Statement:** (the task itself — prose, can run several sentences),
  **Entry point:** (the resolved entry-point protocol chain, e.g. `` `domain-design` → `ingest`,
  `requirements-analysis` ``), and **Related sessions:** (another session file in this project that references or
  is referenced by this one — omit the line entirely when there is none; never write it empty).
- **Status** — two labeled lines: **State:** (`` `active` `` / `` `blocked` `` / `` `done` ``, backtick-quoted) and
  **Last updated:** (the timestamp). Two fields, not one sentence combining them, so either is greppable without
  parsing the other; `scripts/render_status.py` reads **State:**'s backtick-quoted word.
- **Call stack** — the full planned tree from the entry-point protocol down, **one line per level, indented two
  spaces per depth**, each line `<id> (<status>[ — free text])` where `<status>` is `pending` / `active` /
  `blocked` / `done` and the free text is optional context (what a batch covers, why a step is blocked):

      implement (active)
        scenario-new-use-case (active)
          tdd-loop (active)
            cover-cycle (active)
              cover-batch (active — batch 2 of an estimated 4)
      domain-design (active)
        ingest (done)
        requirements-analysis (active)
          event-storming (active)
            collect-events (done)
            attach-event-rules (active — batch 3, full pass)
            identify-aggregates (pending — full)

  A step not yet reached but already known (a sibling still to come, a planned hand-off) is listed as `pending` at
  its real depth — the block is the whole planned tree as currently known, not only the path walked so far. A
  hand-off to another session's entry point is written `-> hand-off: <id> (pending)` at the depth it will resume
  from. This exact shape — literal indentation, not prose describing the same thing — is what
  `scripts/render_status.py` parses to drive an optional status line; see `MANAGEMENT.md`, "Status line". A step
  reused across several parents (its id appears in more than one composing protocol's `steps`) takes its parent
  from the walk it is on for this call.

  **Mirror this in Claude Code's own task list** (`TaskCreate` / `TaskUpdate` / `TaskList`, or the legacy `TodoWrite`
  if that is what the session has instead) whenever those tools are available — one entry per step in the current
  call stack, status kept in lockstep with the stack above. This is only available on some models and
  configurations; if none of these tools exist in the current session, skip this silently — the session file above
  remains the durable, resumable record regardless, and is never optional the way this display is.
- **Directives in effect** — a table, one row per directive actually loaded so far this run:

      | Id           | Source                                       | Version   |
      |--------------|-----------------------------------------------|-----------|
      | `test-style` | `craftsman-workshop` (see Sources in the index) | `b0a7994` |

  ("Source" is the workshop source from `directives/index.md`'s Sources table; "Version" is that source's version —
  a commit sha, when it is a git repository.) Empty at the start of a run — write `None loaded yet.` as prose
  instead of a header-only table, the same empty-table convention `toggle_table_row.py` already uses for index
  files. On resume, compare this table against the currently-installed versions and say plainly what differs —
  never silently assume they still match. This is what lets a task be picked up faithfully by a different developer
  on a different machine.
- **Checkpoint log** — one entry per checkpoint reached, each its own `### N. \`step-id\`` heading — carrying the
  same batch/context suffix the Call stack line for that step has, e.g.
  `` ### 3. `attach-event-rules` (batch 1: Block created, Block edited) `` — followed by labeled lines:
  - **Asked:** — what was put to the developer (or stated, for a `notify` checkpoint).
  - **Answer:** — their answer, verbatim or a faithful restatement. Omit this line for a `type: notify`
    checkpoint — it did not wait for one.
  - **Decision:** — what this settles, when it is more than a restatement of the answer. Omit if there is
    nothing beyond the answer itself.
  - **Actor:** — `human:<git user.name or user.email>` when the target project is a git repository with one
    configured, `human:developer` otherwise — never left blank. Omit for a `type: notify` checkpoint.

  Append-only — never edit or renumber an earlier entry. This labeled shape, not one dense paragraph per entry, is
  what lets a specific field be found or extracted without re-reading the whole log, and is what makes "picked up
  faithfully by a different developer" (see Directives in effect, above) something the next session can actually
  check with a grep on **Actor:**, not just assume.
- **Parked** — items deferred per `defer-discovered-gaps` (or an equivalent workshop directive), each to become
  its own later task.
- **Next** — one labeled line: **Next:** followed by the line a future session resumes from.

Keep it current in the same turn as the event: a step starts or finishes, a checkpoint is answered, something is parked.
It must never lag the conversation.

## Report

Results should be pleasant to read as they appear, not only when a run ends. **Every time a step writes or updates
an artifact file** — `business-rules.md`, `open-questions.md`, `event-model.md`, a `specs/*.md`, or any other
deliverable a protocol tells you to write — run `scripts/render_report.py <target project> --doc <file>` (one
`--doc` per file written in that step). It regenerates the project's report page,
`<target project>/.claude/reports/report.html`, which holds every artifact and the session file(s) as one
self-contained, searchable page, and prints two lines per file:

    md:   /full/path/to/specs/001-book-a-desk.md
    html: file:///full/path/to/.claude/reports/report.html#specs-001-book-a-desk-md

**Always show both, always as full paths, exactly as the script prints them** — never "wrote specs/xyz.md" alone,
never a relative or shortened path. The `html:` link opens the report on that very document. Do the same once more
when the entry-point protocol finishes (the session file's **State:** becomes `done`), for the files the run
produced. The session file itself is part of the report but is not announced on every update — it changes on almost
every turn.

**When the live dashboard runs for this project** (`/craftsman:dashboard on` — see `MANAGEMENT.md`, "Dashboard"),
the script sees it, skips the page and prints only the `md:` line per file: the dashboard already shows every write,
so an `html:` link would only add noise. Show the `md:` lines exactly as printed, same as above.

The markdown files remain the source of truth; the page is regenerated from them each time and is a snapshot.
`/craftsman:report` runs the same script on demand, without `--doc`, and prints just the report's link.

This is a courtesy, never part of a step's result: if the script fails, say so in one line — still giving the `md:`
path — and carry on. Never block, retry, or treat the step as not done because of it. It lives here, not in a
workshop's protocols, because the script is the plugin's and a workshop's content cannot name a path inside the
plugin (see "Where the content lives").

## Resuming

On invocation:

- Look in `.claude/sessions/` for `<entry>-session-*.md`. If `session=` is given, or exactly one unfinished file
  matching this entry exists, read it in full, state in one or two lines where things stand (task, current step, what is
  parked), re-state the Directives in effect comparison from above, and ask whether to resume from the current step or
  somewhere else. If the actor resuming now differs from the checkpoint log's most recent **Actor:** fields, say so
  plainly, the same way a version drift is said plainly — never silently assume it's the same developer picking
  this back up.
- If several unfinished session files exist for this entry and none is named, list them (slug, task, current step,
  `Next`) and ask which to resume.
- Do not restart a protocol from the top unless asked.

## Checkpoint protocol

A `checkpoint` is where execution stops and talks to the developer — full field reference in `core.md`.

- `type: ask` — put the `prompt` to the developer and wait for an answer.
- `type: notify` — state the `prompt` and continue; do not wait.
- `when: <condition>` — only stop if the condition holds; otherwise the step is internal and execution continues. No
  condition means always stop.
- `blocking: true` — take no further step, write nothing, without an answer. Every checkpoint before a large or
  hard-to-reverse move (including any git commit) is blocking.
- `shows: [...]` — render these before asking: whatever the protocol names (a diff, a file list, a stub list).
- After the answer: record step + question + who answered + answer + resulting decision in the session's
  checkpoint log, then act on it. "Adjust" means redo the current step in the new direction, not carry on.

Before the `prompt`, say in one short line, in plain language, what is happening right now — a developer reading
the transcript, possibly having lost track of where things stand, should never hit a bare question with no idea
what produced it. Naming the step's id is fine as a trailing aside for someone tracing the run, but the line itself
must read like something you'd say to a colleague, not a list of directive/protocol ids strung together — "citing
your own machinery instead of saying what's happening" is the same failure as a bare question with no lead-in,
just dressed up as an answer to it.

Fill the `prompt`'s own placeholders with the real thing, not a compressed tag list standing in for it. When a
prompt template asks for content "as drafted" (`draft-spec`) or a full list (`collect-events`, `attach-rules-batch`,
...), that means the actual text — criteria written out, the real phrases — not single words abbreviating them
("confirmed/rejected-busy/rejected-blocked" is not acceptance criteria, it's a filing label for them). A developer
who has to ask "what does that abbreviation mean" is reading a checkpoint that failed at its one job.

Then ask in the developer's language: a short, direct question; a numbered list of concrete options when the
choice is between discrete alternatives; free-form when it is open. Do not stack the next step's work "just in
case" while waiting.

When the lead-in or the `prompt` covers more than one distinct point — several facts, several decisions bundled
into one ask, a status update touching more than one thing — put each point on its own line, not packed into one
dense paragraph. This failed live, twice in a row in the same run, in the exact same way as the two failures
above: a checkpoint that is technically correct but unreadable because every point runs together. The fix is the
same discipline as the lead-in and content rules just above it — this is not a separate, optional nicety.

## Language

- Converse with the developer in their language; match and switch with them.
- Directive files, protocol files, session files, and all artefacts a protocol produces stay in English unless the
  protocol says otherwise.
- Code identifiers, comments, and commit messages follow the target repository's convention.

## Notes

- If the task matches no entry-point alternative and the developer does not want the closest one, stop cleanly — do not
  invent a process the installed content does not describe.
- craftsman's defaults are a posture, not a cage: if the developer explicitly asks to skip a checkpoint for one move,
  that is their call — note it, and who authorized it, in the checkpoint log and continue.
- One task, one session file. A genuinely separate task — including a parked follow-up picked up later — is a new run
  with its own session file.
