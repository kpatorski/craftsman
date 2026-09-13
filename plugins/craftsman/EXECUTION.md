# craftsman — execution mechanics

Shared by all three entry-point skills (`analyse`, `domain-design`, `implement`) and by any further entry point a workshop adds. Each entry-point skill loads this file first, then runs its own protocol. Nothing here is specific to one workshop's content — this describes how craftsman executes *any* protocol, whichever workshop it came from.

## Where the content lives

Directives and protocols are not bundled with this plugin — they live at `~/.claude/craftsman/` (`directives/`, `protocols/`, each with its own `index.md`), installed separately via `craftsman install` and updated independently of plugin updates. See `core.md` for the format every directive and protocol file follows.

If `~/.claude/craftsman/` does not exist yet, this is a first run: say so, and offer to install the default starter workshop from the source recorded in this plugin's own configuration (see the `install` skill). Do not fabricate directives or protocols — if there is truly nothing installed, tell the developer and stop.

## Dispatch

1. Find the entry-point protocol matching the invoked skill (`analyse`, `domain-design`, `implement`, or a workshop-added one carrying `entry-point: true`) in `~/.claude/craftsman/protocols/index.md`.
2. Read its `## Protocol` section and walk it top to bottom.
3. When a protocol's body offers several alternatives (each with its own `match`, e.g. `implement`'s five scenarios), read the task against every alternative's `match` and pick the best fit. If none fits cleanly, say so and ask the developer whether to proceed with the closest one or stop — never invent a process none of them describe.
4. A chosen protocol's `steps` are walked in order. A step that is itself a composing protocol is entered recursively — nesting goes as deep as the content does.
5. A protocol with `repeat-until` repeats its `steps` as one iteration, re-checking the condition after each pass, until it holds.

## Loading directives

A step loads only the directives its own `uses` field names, plus any directive named in an ancestor protocol's `overrides` that targets this step or a directive it would otherwise load. This is deliberately not a blind scan of every enabled directive on every step — see `core.md`, "Fields specific to `protocol`".

A directive named in `uses` that is itself composing (has `composes`) pulls in every directive it composes, recursively, unless an ancestor's `overrides` says otherwise for this call.

Only **enabled** directives apply. A directive's current enabled/disabled state is its table membership in `~/.claude/craftsman/directives/index.md` — **not** its own `enabled-by-default` frontmatter field, which only decided which table it landed in in the first place, at install time. `craftsman enable` / `craftsman disable` move a row between the two tables; nothing in the directive's own file changes.

## Applying an `overrides` map

Before a step that appears as a key in the chosen protocol's `overrides` runs — or before a directive named as a key would otherwise be loaded by that step — apply the stated change for this call only: skip the step, force its outcome, or relax the named rule. Neither the step nor the directive itself is touched; the override is scoped to this one run of the overriding protocol.

## `<type>-session-<slug>.md` — the state file

One file per task, under `.claude/sessions/` in the project (`.claude/sessions/<entry>-session-<slug>.md`, e.g. `implement-session-cancel-reservation.md`), not the project root — so a task in progress never clutters `git status`. `<entry>` is the invoked skill's name (`analyse`, `domain-design`, `implement`). The filename slug is a short kebab-case reduction of the task statement. `session=<path>` on the invocation overrides the location entirely.

**First use in a project:** check whether `.claude/sessions/` is covered by `.gitignore`. If not, say so and offer to add a `.claude/sessions/` line.

Written in English regardless of conversation language. Holds:

- **Task** — the task statement and the resolved entry-point protocol. Human-readable "what is this file" line, kept at the top.
- **Status** — `active` / `blocked` / `done`, and the timestamp of the last update.
- **Call stack** — the path from the entry-point protocol down to the current step, indented like a stack trace, each level marked `pending` / `active` / `done`:

      implement > scenario-new-use-case > tdd-loop > cover-cycle > cover-batch (active)

  A step reused across several parents (its id appears in more than one composing protocol's `steps`) takes its parent from the walk it is on for this call.
- **Directives in effect** — every directive actually loaded so far this run: its id, the workshop source it came from (`directives/index.md`'s Sources table), and that source's version (a commit sha, when the source is a git repository). On resume, compare this list against the currently-installed versions and say plainly what differs — never silently assume they still match. This is what lets a task be picked up faithfully by a different developer on a different machine.
- **Checkpoint log** — one entry per checkpoint reached: which step, what was asked, what the developer answered, the resulting decision. Append-only.
- **Parked** — items deferred per `defer-discovered-gaps` (or an equivalent workshop directive), each to become its own later task.
- **Next** — the one line a future session resumes from.

Keep it current in the same turn as the event: a step starts or finishes, a checkpoint is answered, something is parked. It must never lag the conversation.

## Resuming

On invocation:

- Look in `.claude/sessions/` for `<entry>-session-*.md`. If `session=` is given, or exactly one unfinished file matching this entry exists, read it in full, state in one or two lines where things stand (task, current step, what is parked), re-state the Directives in effect comparison from above, and ask whether to resume from the current step or somewhere else.
- If several unfinished session files exist for this entry and none is named, list them (slug, task, current step, `Next`) and ask which to resume.
- Do not restart a protocol from the top unless asked.

## Checkpoint protocol

A `checkpoint` is where execution stops and talks to the developer — full field reference in `core.md`.

- `type: ask` — put the `prompt` to the developer and wait for an answer.
- `type: notify` — state the `prompt` and continue; do not wait.
- `when: <condition>` — only stop if the condition holds; otherwise the step is internal and execution continues. No condition means always stop.
- `blocking: true` — take no further step, write nothing, without an answer. Every checkpoint before a large or hard-to-reverse move (including any git commit) is blocking.
- `shows: [...]` — render these before asking: whatever the protocol names (a diff, a file list, a stub list).
- After the answer: record step + question + answer + resulting decision in the session's checkpoint log, then act on it. "Adjust" means redo the current step in the new direction, not carry on.

Ask in the developer's language. A short, direct question; a numbered list of concrete options when the choice is between discrete alternatives; free-form when it is open. Do not stack the next step's work "just in case" while waiting.

## Language

- Converse with the developer in their language; match and switch with them.
- Directive files, protocol files, session files, and all artefacts a protocol produces stay in English unless the protocol says otherwise.
- Code identifiers, comments, and commit messages follow the target repository's convention.

## Notes

- If the task matches no entry-point alternative and the developer does not want the closest one, stop cleanly — do not invent a process the installed content does not describe.
- craftsman's defaults are a posture, not a cage: if the developer explicitly asks to skip a checkpoint for one move, that is their call — note it in the checkpoint log and continue.
- One task, one session file. A genuinely separate task — including a parked follow-up picked up later — is a new run with its own session file.
