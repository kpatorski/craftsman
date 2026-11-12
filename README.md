# craftsman

A HUMAN <-> AI loop for coding, requirements analysis and domain design — never one large generated drop. craftsman
executes **directives** (what must be true about the code right now) and **protocols** (what order to work in, and where
to stop) that a workshop author wrote, stopping at every checkpoint to confirm direction.

## Why a loop, not a drop

A large diff generated in one shot means a wrong direction only surfaces after it's already built — expensive to
unwind, and it teaches nothing about where guidance was actually needed. craftsman stops instead, at every
`checkpoint` a protocol declares, and asks before committing further: one small batch at a time, not the whole task
at once. This is not a side feature — it's the reason craftsman exists instead of a single big prompt. See
[`core.md`](plugins/craftsman/core.md), "Fields specific to `protocol`", for exactly what a `checkpoint` can do
(`ask` and wait, or just `notify` and continue; `blocking` or not).

## Installing

```
/plugin marketplace add kpatorski/craftsman
/plugin install craftsman@craftsman
```

The `@craftsman` names the marketplace explicitly (`<plugin>@<marketplace>`) — this is the form confirmed to work.

(`<this-repo-url-or-path>` works too in place of `kpatorski/craftsman` — a local clone path, or any other git URL,
if you're not installing from GitHub directly.)

Then, on first use of any entry-point command, craftsman notices `~/.claude/craftsman/` doesn't exist yet and offers to
install a starter workshop. Or run `/craftsman:install <workshop-source-url>` yourself, any time.

## Updating

No auto-update, by design — updating a plugin without asking is exactly the kind of thing this project doesn't want
to do to you. craftsman only ever tells you it happened and lets you decide:

- **The plugin itself**: every command checks its own version against `~/.claude/craftsman/`'s own record of it (a
  local, offline comparison — no network call) and says so, once, when they differ, pointing at
  [`CHANGELOG.md`](CHANGELOG.md). To actually update, run these yourself, when you're ready:
  ```
  claude plugin marketplace update craftsman
  claude plugin update craftsman@craftsman
  ```
  The first refreshes Claude Code's cached copy of this marketplace repo; the second installs whatever newer version
  that copy now has. Takes effect in a new session — the one you ran it from keeps the version it already loaded.
  (Claude Code does have an opt-in auto-update for marketplaces — off by default for any marketplace that isn't
  Anthropic's own, including this one — see `/plugin` → Marketplaces if you want to turn it on; craftsman itself
  never turns it on for you.)
- **A workshop source** (e.g. `craftsman-workshop`): re-run `/craftsman:install <same-source-url>` any time. If
  nothing changed upstream, it says so and stops. If something did, it shows what and asks before touching anything
  — see [`MANAGEMENT.md`](plugins/craftsman/MANAGEMENT.md), "Checking a known source for updates". Nothing checks
  this for you in the background either.

  **This never touches your own work.** A directive or protocol you wrote yourself — anything not present in the
  source you're updating from — is never a candidate for deletion. If you hand-edited a file that came from that
  source and upstream hasn't changed it since, your edit is left alone; you're told it was skipped, not silently
  overwritten. A file you edited *and* upstream also changed is shown as a real conflict, with both diffs, so you
  choose — nothing is applied without your say-so. And anything you've deliberately disabled stays disabled through
  an update to its content; only a first install ever decides a fresh entry's starting Enabled/Disabled state.

## The model

Two kinds, nesting on any depth — plus a **bundle**, a grouping and distribution unit for both (not a third kind,
more below):

| Kind        | Answers                                    | Enabling it means            |
|-------------|--------------------------------------------|------------------------------|
| `directive` | What must be true about the code right now | It applies, or it does not   |
| `protocol`  | What order to work in, and where to stop   | It is callable, or it is not |

The three-question test that decides which one a new entry is, the full field reference for both kinds, and the golden
rule against adding fields no one needs yet — all in [`plugins/craftsman/core.md`](plugins/craftsman/core.md#the-three-question-test). Read 
that before authoring anything.

A **bundle** is not a third kind — the three-question test above still only ever answers `directive` or `protocol`.
It is a grouping and distribution unit: a named folder of directives and/or protocols that installs and enables
together (`/craftsman:enable event-storming` turns on everything that modelling method needs in one move). A
directive or protocol belongs to a bundle by living inside it on disk, nothing more — no field to keep in sync. See
[`core.md`](plugins/craftsman/core.md), "Bundle".

## Two repos, on purpose

- **This repo** (`craftsman`) is the code: the plugin, its 13 command skills, the execution and management mechanics.
  Install it once, update it like any other plugin.
- **Content** — directives, protocols, and bundles — lives separately, at `~/.claude/craftsman/` on disk, installed
  via `/craftsman:install` from one or more workshop sources (git repositories of `directives/` + `protocols/` +
  `bundles/`, each collection with its own `index.md`). A plugin update never touches your content; a content update
  never touches the plugin. See [`plugins/craftsman/EXECUTION.md`](plugins/craftsman/EXECUTION.md), "Where the
  content lives".

A reference workshop — this author's own `directives/` + `protocols/` + `bundles/` — lives at
[`kpatorski/craftsman-workshop`](https://github.com/kpatorski/craftsman-workshop). It is a starting point, not a
default everyone must adopt: install it, fork it, or write your own from scratch against
[`core.md`](plugins/craftsman/core.md).

## Commands

| Command                                              | Does                                                                                                                                                  |
|------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| `/craftsman:analyse <input>`                         | Raw requirements → Given/When/Then business rules. No domain modelling.                                                                               |
| `/craftsman:domain-design <input>`                   | Event storming (or whatever the workshop's own method is) → specs and working code, one use case at a time.                                           |
| `/craftsman:implement <task or spec>`                | Drives one task test-first, checkpoint by checkpoint.                                                                                                 |
| `/craftsman:pr-review [PR URL or target:source]`     | Reviews a pull request on its own page: findings as proposed PR comments the developer edits, picks and sends.                                        |
| `/craftsman:search <topic>`                          | "Do we already have something about X?" — across all three indexes.                                                                                   |
| `/craftsman:list [directives\|protocols\|bundles]`   | What's installed, enabled and disabled.                                                                                                               |
| `/craftsman:enable <id>` / `/craftsman:disable <id>` | Toggle a directive, protocol, or bundle — ids are unique across all three, so the kind resolves by lookup. Toggling a bundle cascades to its members. |
| `/craftsman:install <path or URL>`                   | Add a directive, protocol, bundle, or a whole workshop source.                                                                                        |
| `/craftsman:uninstall <id>`                          | Remove one.                                                                                                                                           |
| `/craftsman:rename <old-id> <new-id>`                | Rename, updating every reference.                                                                                                                     |
| `/craftsman:merge`                                   | Find single-use entries and offer to fold them into their one parent.                                                                                 |
| `/craftsman:statusline-setup`                        | Wire the command → batch → protocol → directive indicator into Claude Code's status line (one-time setup).                                            |
| `/craftsman:dashboard [on\|off\|status\|remove]`     | Live dashboard in the browser, served locally — session stacks, artifacts and specs as they change, installed content with enable/disable switches.   |
| `/craftsman:dictation [setup\|list\|add\|use]`       | Voice dictation in the review page's text boxes, by Whisper on this machine: sets it up and manages its models.                                       |
| `/craftsman:report [project dir]`                    | Analysis artifacts and session(s) of a project as one searchable HTML report. Also generated when a run finishes.                                     |
| `/craftsman:help`                                    | This table, from inside a session.                                                                                                                    |

Each entry-point command also triggers from plain conversation ("add a use case", "model these requirements", "digest
these requirements") — see each skill's own `description` for its exact trigger phrases.

### The live dashboard

`/craftsman:dashboard on` (or just `/craftsman:dashboard`) starts a small local web server and prints its address,
`http://craftsman.localhost:4747` — a `.localhost` name always means this machine, and browsers resolve it without an
entry in `/etc/hosts`; `http://localhost:4747` is the same page. Open it once and keep it on a second screen: it shows
the session's stack collapsed to the step running now, the artifacts and specs as they are written, and everything
installed, with working enable/disable switches — and it refreshes by itself as files change. Run it from another
project and that project joins the same page, and so does every craftsman project found below the folder it was started
from — a repository with one task per sub-folder needs starting only once, from its root. `/craftsman:dashboard remove`
(or the × next to the project's name on the page) takes the current one — or `remove <dir>`, any other — off it again,
without touching its files. `/craftsman:dashboard status` tells whether it runs; `/craftsman:dashboard off` stops it. It
also stops by itself after 8 hours with no page open. ◐ Palette in its top bar picks the colours of every craftsman
page: nine dark palettes and a light one.

Nothing needs installing beyond `python3`, which craftsman's scripts already use. On WSL 2 the address opens as is
in a Windows browser. The server is optional: without it, every file a run writes is still announced with its full
`md:` path and an `html:` link to the static report; with it running, only the `md:` path is printed.

### Dictation

The review page's text boxes take dictation, in English or Polish: a microphone button stands in the corner of the box
being written in, and the spoken text goes in at the caret, for you to read before anything is sent. The speech engine
is Whisper, running on this machine; your recordings never leave it and are never stored. Nothing is installed until
you ask: `/craftsman:dictation setup`, or "Set up…" on the page, downloads the engine and its default model, about
0.7 GB, into `~/.craftsman/dictation/`. `/craftsman:dictation list` shows the models, `add`, `remove` and `use` manage
them. See `REVIEW.md`, "Dictation".

### Guard rails

Some rules are enforced by hooks rather than left to the model, and they switch on with the plugin. During a run, a
`git commit` is refused until you have replied since the last commit and that answer is in the session's checkpoint
log — so no commit happens without your say-so, even when the model forgets to ask. And when a long conversation is
compacted, the run's directives and the current step's protocol are put back in front of the model, so it does not
carry on from a summary of its own rules. A third hook checks each write to a session file and reports what broke
its format. Outside a craftsman run none of them does anything. Details:
[`MANAGEMENT.md`](plugins/craftsman/MANAGEMENT.md), "Hooks".

The check of finished code against the directives is done by separate, read-only reviewers that see only the change
and the rules — never by the session that wrote the code, which tends to overlook the same rules twice. Every finding
comes with a `file:line`; what the run disputes is left for you to decide. Details:
[`EXECUTION.md`](plugins/craftsman/EXECUTION.md), "Independent directive review".

Large read-only work — pulling candidate rules out of a long requirements document, section by section — is split
between read-only helpers that run in parallel and return each item with the words it came from. What they bring
back is only material: every question to you, and every file written, still happens in the run itself.

## For workshop authors

Write directives and protocols against [`core.md`](plugins/craftsman/core.md)'s format — the three-question test, the
field reference, and the golden rule against inventing fields. A **fundament** entry (used by more than one theme, or a
single standalone preference) lives flat at `directives/<id>/directive.md` or `protocols/<id>/protocol.md`. A new rule
that belongs to one identifiable theme a developer would want to switch on or off as a whole goes into a **bundle**
instead: `bundles/<id>/bundle.md` plus its own `directives/` and `protocols/` subfolders, mirroring the top level. See
[`core.md`](plugins/craftsman/core.md), "Bundle", and [`craftsman-workshop`'s own
`bundles/index.md`](https://github.com/kpatorski/craftsman-workshop/blob/main/bundles/index.md) for the rule worked
through on a real corpus (7 bundles, from a 62-protocol/41-directive workshop) — its own `## Examples` section walks the
fundament-vs-bundle call on concrete entries.

`/craftsman:install` validates syntax and checks for duplicates before accepting anything into `~/.claude/craftsman/` —
see [`MANAGEMENT.md`](plugins/craftsman/MANAGEMENT.md) for exactly what it checks.

## Mechanics, for anyone extending craftsman itself

- [`EXECUTION.md`](plugins/craftsman/EXECUTION.md) — how a protocol actually runs: dispatch, directive loading, the 
  per-task session file, resuming, the checkpoint protocol.
- [`MANAGEMENT.md`](plugins/craftsman/MANAGEMENT.md) — how content gets installed, validated, renamed, merged, and
  versioned.

### Reviewing a pull request

`/craftsman:pr-review`, run from any folder, prints the address of the review page and opens nothing in the session
itself. On the page, a wizard asks what is reviewed — a pull request, or what one local branch adds on top of another —
and where its code is read from: your checkout of the repository (typed, or picked with "Browse…"), or, for a pull
request, a clone made for the review in `/tmp`. `/craftsman:pr-review https://github.com/org/repo/pull/123` fills the
wizard in, or opens that PR's review when it is already under way. A pull request on a GitHub Enterprise host works the
same, with `gh` signed in to that host. The review reads the PR's Jira tickets through your Jira MCP server once you
allow it: the page asks the first time the review wants one of its tools, and ⚙ in the rail lists the servers. Whatever
else the review wants beyond its own tools it asks for on the page, and waits: allow it once, in every review, or deny
it with a reason — see `REVIEW.md`, "The review's session". The review reads the PR's description and the tickets it
links, maps the change into use cases, tells the PR's story, reads the business rules in its tests, notes the few places
that are hard to follow, and only then reviews the code, use case by use case from the entry point down, against the
enabled directives — including whether the code could be simpler or left to the standard library, the framework or a
dependency the build already has. Every finding is a proposed PR comment: edit it, delete it, or mark it to send, and
send the marked ones to GitHub whenever you like — nothing is posted before that.

Reviews have their own page, `/review` on the dashboard server, apart from the dashboard. The reviews are tiles in a
rail on the left; the open one has five tabs:

- **Story** — where a review opens: what the PR does, its ticket, what it leaves out, and its findings and viewed
  files in one line; then the PR told as a teammate would, in short chapters, each ending with chips of its files that
  open them in Code, and a diagram where a flow crosses three or more parts. A table of contents beside it; the chapter
  picked is what the AI Agent panel is about. An address with `tab=overview` or `tab=structure` opens the Story.
- **Code** — the changed files as IntelliJ's project tree beside the diff of the open one. Packages share a row
  (`com.example.booking`), source, test and resources roots have coloured folders, and each file shows the kind and
  the visibility of its top-level type (Java, Groovy, Kotlin; the kind for TypeScript), its findings, GitHub's change
  mark and whether you viewed it. What is open, and the tree's width, are kept across reloads; "Unchanged files" adds
  the files the PR leaves as they are, to read and ask about. `↑`/`↓` open the file the cursor lands on, `←`/`→` close
  and open a folder, `Enter` goes into the diff and `Esc` back, `Space` marks the file viewed. The code is coloured by
  its language (Java, Kotlin, TypeScript, JavaScript, Python, Go, C#, SQL, shell, YAML, JSON, XML); findings are dots
  beside the line numbers, opened under the line on a click, or all inline with a switch.
- **Findings** — a table to filter, search and sort; a finding picked opens in the AI Agent panel to edit, ask about,
  drop, or mark to send. A finding's "In fix prompt" switch leaves it out of the fix prompt Send can post.
- **Comments** — the PR's conversation on GitHub as it reads there: everyone's comments, reviews and threads on the
  code, read again after every Send and on request. Write a comment on the whole PR, quote one to answer it, or reply
  in a thread; yours wait for Send. A thread on a line of the diff also shows under that line in the code.
- **Rules** — every directive the review checks the code against, with a switch for this review and what each one
  found in each use case: findings, clean, not applicable, or not checked yet — then "Check now". The review checks
  every directive switched on here; the agent never picks among them. One review's set can become the default for
  every review.

The **AI Agent panel** stands beside every tab, under a header that runs over both. It is about what is picked in the
tab — a folder, a file or lines selected in the diff on Code, a chapter of the Story, a finding, a GitHub comment, a
rule — or the whole PR when nothing is; on Code, 📌 keeps it while you move around the code. "Ask about it" holds the
conversation about that and the box to ask in (`⌘ Enter` on a Mac, `Ctrl Enter` elsewhere), with suggested questions;
the agent's own question, the one the run stopped on, waits there in the PR's conversation. On the whole PR, "Add as
context" keeps what you write as a note for the agent: what it should know that the PR does not say; the new-review
wizard asks for the first one. Lines selected in the diff open "Finding" and stay selected, to copy. The ⧉ next to the
file's path copies the path, to find the file in your IDE. "Finding" is there on a folder, a file or lines: a markdown
editor with the finding as AI Agent writes it, one draft per file or folder that stays while you move around, and "Make
it a finding"; a finding on a folder goes to the PR's conversation. On a finding, "Finding" is the finding itself, with
"Show in code →", which opens the code at its line and keeps the panel on it. A progress strip under the tabs says which
of the review's steps the agent is at and what it does there; the header says whether it is working, idle, or silent for
longer than it should be, with a button to restart its session in the same conversation. The review's Claude session
runs on the dashboard server, so its questions, its progress and your messages to it all stay on the page; once stopped,
`claude --resume` continues the same conversation in the CLI. "Send (N)" opens one dialog listing everything that goes:
every marked finding as an inline comment on its first place, with a pointer from each further place, and every comment
and reply of yours. "Also post a fix prompt" adds a comment for the author: one prompt per category for their AI coding
agent, each fixed as one commit, previewed with its size and a Copy button; whether it starts ticked is set in ⚙. The
dialog sends on a click or `⌘ Enter` (`Ctrl Enter`) only, never on a stray key; a comment the PR already has is never
posted twice.

The page works from the keyboard; `?` lists every key. `1`…`5` open the tabs, `a` and `f` the panel's "Ask about it" and
"Finding", `/` finds a file by the letters of its name in order, as IntelliJ's speed search does (`resd` finds
`ReserveDesk.java`). On Code, `t` and `d` go to the tree and the diff, `[` and `]` to the previous and next file, `v`
marks it viewed, `u` shows the unchanged files, `p` pins the panel and `n`/`N` step through the file's findings; in the
diff `↑`/`↓` move a line cursor and `shift` with them selects lines. On Findings, `↑`/`↓` move, `Enter` opens the
finding in the panel and `x` marks it to send. Single letters work outside text boxes only; what a key changes says so
in a toast with Undo (`⌘ Z`, `Ctrl Z`) for five seconds. A tab opens with the focus where its keys work. Under 1200px
wide the panel is a drawer, opened from a strip on the right edge that shows the AI Agent's waiting questions; under
900px the tree is one too, opened with "☰ Files" or `t`; on a screen lower than 900px the header is compact and the
comment style folds to one line.

Each review keeps its state in `~/.craftsman/reviews/<review-id>/`, outside the repository, and reads the code from its
own `git worktree`, so your checkout is never touched and several reviews can run at once. A clone is deleted when its
review is closed or archived, and made again, with the page saying so, when the review resumes. A review needs the
`code-review` bundle of the workshop and `gh` logged in to the PR's repository; the state it keeps is described in
[`REVIEW.md`](plugins/craftsman/REVIEW.md).

### Releasing a change to this repo

Bump `"version"` in [`plugins/craftsman/.claude-plugin/plugin.json`](plugins/craftsman/.claude-plugin/plugin.json)
on every commit that changes plugin behaviour (not on a pure typo/doc fix), and add an entry to
[`CHANGELOG.md`](CHANGELOG.md). `claude plugin update` compares this field, not raw commits — a content change
without a version bump is invisible to it, and the only way a developer already on an older version can pick it up
is `claude plugin uninstall craftsman@craftsman` + `claude plugin install craftsman@craftsman` (which ignores the
version field and just takes whatever the marketplace currently has). Found live, the hard way, while testing this
mechanism against a real install — see `MANAGEMENT.md`, "Plugin version".

## License

[PolyForm Internal Use License 1.0.0](LICENSE.md) — free to use, including commercially, for your own internal
purposes. Redistribution (forking and republishing, mirroring, or otherwise passing this repository or a modified
version of it on to third parties) is not permitted.
