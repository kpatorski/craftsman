# Changelog

What a developer with content already installed in `~/.claude/craftsman/` needs to know about each plugin version —
not a full commit log. See `MANAGEMENT.md`, "Plugin version" for how this gets surfaced automatically.

## 0.24.0

- One "Send… (N)" button opens a dialog listing everything that goes. "Also post a fix prompt" in it adds the fix
  prompt for the author's AI coding agent, with a preview, its size and Copy; ⚙ AI Agent tools sets whether it starts
  ticked (`send-fix-prompt`, ticked unless set). The Findings tab's "Fix prompts → comment" is gone: after Send nothing
  marked is left to send.
- A fix prompt longer than the 65,536 characters GitHub takes in one comment goes as several, each with whole prompts.
- The dialog sends on a click or `⌘ Enter` (`Ctrl Enter`) only; it opens with the focus on itself, so a stray `Space`
  or `Enter` presses nothing.

## 0.23.0

- The Story tab replaces Overview and Structure, and a review opens on it: what the PR does, its ticket, what it leaves
  out, and its findings and viewed files in one line; then the PR told as a teammate would, in short chapters, each
  with chips of its files that open them in Code, and a diagram where a flow crosses three or more parts. A table of
  contents beside it; the chapter picked is what the AI Agent panel is about. `tab=overview` and `tab=structure` open
  the Story.
- The agent writes the story in a step of its own, `tell-the-story`, after it maps the use cases: update the workshop
  (`/craftsman:install` on its source) for the step and its directive, `pr-story`. Until then a review's Story shows
  the PR's scope.
- Notes of context for the agent are added in the AI Agent panel on the whole PR, with "Add as context".
- Code, Findings and Comments count their items next to their names; Story and Rules do not.

## 0.22.0

- The AI Agent panel stands beside every tab of a review, in place of the "Ask AI" popover, the comment panel and the
  side panels. It is about what is picked in the tab — a folder, a file or lines on Code, a finding, a GitHub comment,
  a rule — or the whole PR when nothing is, and says so at its top. 📌 on the Code tab keeps it while you move around.
- "Ask about it": the conversation about that, kept with the review, with suggested questions; a folder can be asked
  about too. The agent's question the run stopped on waits in the PR's conversation, with its answers.
- "Finding" on a folder, a file or lines: the comment editor and AI Agent's finding, one draft per file or folder. A
  finding on a folder goes to the PR's conversation, naming the folder. On a finding, the finding itself.
- The header runs over the page and the panel; on the Code tab the tree, the diff and the panel are frames that start
  and end on the same lines, and the diff scrolls inside its frame.
- Selected lines stay selected while the panel is about them; `Esc` in the diff lets go of them, then goes back to the
  tree.

## 0.21.0

- The Code tab shows the changed files as IntelliJ's project tree: folders open and close one by one (⊞/⊟ for all),
  packages share a row, and source, test and resources roots have coloured folders. What is open is kept per review.
- Left of a file's name, the kind of its top-level type (class, interface, record, enum, annotation; a test class
  marked) and its visibility, read by the server from Java, Groovy and Kotlin, and the kind from TypeScript; other
  files show what they are (Docker, Maven, Gradle, npm, YAML, SQL, …). Right of it, its findings coloured by the worst
  one, GitHub's change mark, and the viewed mark, which a click toggles.
- "Unchanged files" adds the files the PR leaves as they are, greyed; one opens as the PR's branch has it, to read and
  ask AI Agent about.
- The tree's keys: `↑`/`↓` open the file the cursor lands on with the focus kept in the tree, `←`/`→` close and open a
  folder, `Enter` goes into the diff and `Esc` back to the tree, `Space` marks the file viewed. The Code tab opens with
  the focus on the tree.
- The tree's width is dragged at its right edge and kept.

## 0.20.2

- The Code tab's file list scrolls on its own beside the diff and keeps its place: marking a file viewed or opening
  another one no longer takes you back to the top of the list.
- Files are grouped by their whole folder: two folders that differ only in the middle of their path are two groups, each
  named with as much of its path as tells it apart.

## 0.20.1

- "Your words" has five steps: verbatim (the draft's sentences, translated and corrected), close, balanced, loose and
  free. With verbatim or close, the tone and the length follow the draft and their sliders are greyed.
- "Brief" asks for exactly one or two sentences.
- "Discard" empties the comment panel; the thrown-away draft no longer comes back into it.

## 0.20.0

- The comment panel's AI Agent keeps to the developer's words by default: their points and how firmly they say them,
  nothing added. Sliders shape the comment — how close to the draft's words, the tone, how long — and a box asks for a
  code sample of the fix. The default shape is set on the AI Agent tools tab, kept as `comment-style` in
  `~/.craftsman/settings.json`; each draft may ask for another.
- The severity picked in the panel sets how firmly the comment says it: must-fix as required before the merge, nit as
  minor.
- "Edit" corrects AI Agent's comment by hand; the correction is pinned, and a newer draft does not write over it.
- "Make it a finding" waits while AI Agent writes the comment, so a half-written one is never made a finding.

## 0.19.4

- The Findings table's "To the author" column fits "maybe resolved".

## 0.19.3

- Fix prompts name no severity, only list the worst first, and the developer's findings with no category go in one
  prompt headed "Other fixes" instead of "yours".
- A finding about a whole file goes on that file in the pull request, not into its conversation; a GitHub that takes no
  comment on a whole file still gets it in the conversation. A finding on a removed line goes on that line.

## 0.19.2

- A finding the developer adds on the review page, or turns a draft into, is marked to send from the start; the AI
  Agent's findings still wait to be picked.

## 0.19.1

- The comment panel's AI Agent writes the code the developer asks for: a code block in the draft, a placeholder like
  "proposal here" included, comes back as the actual code, never dropped. `review-comment` asks for a snippet for a new
  type or a changed signature, or whenever the developer wants one.

## 0.19.0

- `map-change-structure` gives a use case the changed files declaring the types its steps use, and a changed file in
  no use case the use case whose package it shares, when only one does.
- The `code-review` bundle's `directive-scope.md` says, per directive, which changed files a review checks it on
  (`production`, `tests`, `all`, or `none`: not in a review) and whether one file is enough to judge it (`file`) or it
  needs the use case (`flow`). `review_directives.py` prints `files` and `reach`, leaves out `none`, and names the
  directives with no row with `--unscoped`; those are checked on every file, per use case. Re-run `install` on the
  workshop source to get the table: a bundle installs every file in its folder.
- A review checks the directives by that table: `review_directives.py --plan` lists the reviewers to start. A `file`
  directive is checked once over the whole change, not again in every use case; a `flow` one per use case, only on
  the files of its kind; a use case with no such file records it as not applicable. The review's directive reviewers
  run on Sonnet. `record-check` takes a list, so a use case records all its checks in one call.
- The directives a review checks with no row in `directive-scope.md` are named: on the Rules tab, in the dashboard's
  Library, and by `pr-review` when the developer starts it (`review_directives.py --unscoped`, no review needed). The
  Rules tab says how each directive is checked: on which files, and once over the change or per use case.
- One `flow` reviewer takes several small use cases, up to about 1500 changed lines, each as its own flow, and the
  review starts every reviewer before the first use case. `visibility`, `interfaces`, `abstraction-timing`,
  `error-handling` and `type-contracts` are `file` directives: their reviewer looks up the callers in the code.
- `review-comment` asks for a comment the way a teammate would say it: as long as the point needs (a reminder stays a
  sentence or two), what is wrong and what to do, why only when it is not obvious, no report language, and nothing
  the comment already sits on. The comment panel's AI Agent writes to the same measure, keeping the size of the draft,
  and the panel shows the finding's title and comment, as the author reads it.
- A comment can hold for every place in the change, the way it would be said on a call: "please remove these
  everywhere you added them". The comment panel's AI Agent keeps that sentence, and the fix prompts tell the author's
  agent that such a fix covers every such place.
- Opening another file in the Code tab shows it from its top; a refresh of the same file keeps the place.
- The selection popover ("Ask AI Agent", "Comment") opens by the pointer where the selection ended, inside the diff or
  text it was made in, never under the side panel.

## 0.18.0

- The Code tab has a comment panel: "✎ Comment" over selected lines, or "✎ Comment on file" in a file's header, opens
  a markdown editor with a toolbar, the finding rendered above it as the author will read it, a severity, and "Make it
  a finding" (⌘ Enter); the finding's title is the comment's first sentence. Each file keeps one draft, saved as you
  type, so moving between files moves between their drafts. Drafts are `drafts` in
  `review.json` (`review_state.py save-draft`, `discard-draft`, `draft-to-finding`, the developer's); see REVIEW.md,
  "Drafts". It replaces the "Add finding" panel.
- The comment panel's "AI Agent assistant", on by default: write your thoughts in your own words, in any language,
  and a moment after you stop AI Agent writes them up above the draft as the finding — title, category, severity, why,
  and the comment, in the review's language, by the `code-review` bundle's directives — and says when a finding of
  the file already is the same problem; "Make it a finding" then adds the place to it. A short Claude call of its own
  writes it (`/api/review/draft-preview`, `_draft_preview.py`, model `haiku` or `CRAFTSMAN_PREVIEW_MODEL`), not the
  review's session.
- A finding can be about a whole file: its location's `line` is null, the Code tab shows it above the file's diff,
  and Send posts it to the pull request's conversation, naming the file.
- The review page's side panel is a rounded card beside the content, level with it, instead of a strip along the
  window's edge; over an open use case it still floats on top.
- Esc steps back one layer on the review page: out of a text box, then the selection popover, the side panel, and the
  open use case.

## 0.17.0

- The developer can tell the review's agent what the pull request does not say: "Context for the AI Agent" under "What
  the PR is for" on the Overview tab, where each text sent (⌘ Enter) becomes a note that can be taken back, and an
  optional third step in the new-review wizard. The notes are `context` in `review.json` (`review_state.py add-context`
  and `remove-context`, the developer's); each change also sends a `context` message to the agent. See REVIEW.md,
  "Understanding". Update the `code-review` bundle of the workshop together with this version — its `read-pr-scope`,
  `review-use-case` and `serve-page` read and handle it.
- "Fix prompts → comment" on the Findings tab writes the findings marked to send as a comment on the whole PR: one
  prompt per category, in a fenced block, for the author's AI coding agent to fix as one commit (`fix_prompts.py`).
  Each finding has an "In fix prompt" switch, on by default (`in-prompt`, `review_state.py in-prompt <id>`). See
  REVIEW.md, "Fix prompts".
- Markdown on the review page and in the reports is read as GitHub reads it in two more places: a fenced block ends
  only at a line of as many backticks or more, so a longer fence holds a code block, and a line that is an HTML
  comment is not shown.

## 0.16.0

- The review page has a **Rules** tab: every directive the review checks the code against, with a switch for this
  review and a dot per use case for what it found there — findings, clean, not applicable, or not checked — and
  "Check now" for a directive switched on after use cases were reviewed. One review's set can become the default for
  every review (`review-directives` in the craftsman settings). It also lists the review's protocols.
- `review_directives.py <review dir>` prints the directives a review checks: every directive the workshop enables,
  unless the developer switched it for the review. `review.json` gains `directive-switches` and `checks`;
  `review_state.py` gains `switch-directive` (the developer's) and `record-check` (the agent's). See REVIEW.md,
  "Directives". Update the `code-review` bundle of the workshop together with this version — its `review-use-case`
  checks every use case against all of them and records each result.
- The directive reviewer reads a directive's `applies-when` as the code the rule is about: a change that contains such
  code is checked against it.
- A review that is still opening shows the permission prompts of its session on the review page, and they can be
  answered there.
- A review whose opening stopped before `review.json` was written starts again from the review page.

## 0.15.4

- The root text size is 109% (`_theme.TEXT_SIZE`).

## 0.15.3

- The root text size is 112% (`_theme.TEXT_SIZE`).

## 0.15.2

- Text on the dashboard, the review page and the reports is larger. Every page sizes its text in `rem`, from one root
  size the shared theme sets (`_theme.TEXT_SIZE`, 115%).
- The use-case cards on the review page's Structure tab take the height of their text, in rows and beside the panel.

## 0.15.1

- `review_state.py refresh '{"base", "head", "diff"}'` moves a review to a new head: it keeps the diff as
  `diff/<head>.diff` and sets `base`, `head` and `refreshed` in one change. `set` no longer takes `base` or `head`.
  A file whose change differs in the new diff is no longer marked viewed. Update the `code-review` bundle of the
  workshop together with this version — its `refresh-review` runs `refresh`.
- A review whose diff is missing still opens; its Code tab says which diff is missing.

## 0.15.0

- The review page has a **Comments** tab: the pull request's conversation on GitHub — everyone's comments, reviews and
  threads on the code — read when the review opens, after every Send, and on request. Write a comment on the whole
  pull request, quote one to answer it, or reply in a thread; they wait for Send beside the marked findings. A thread
  on a line of the diff shows under that line too, and a sent finding shows the answers to it. See REVIEW.md,
  "Comments" and "`github.json`".
- A sent finding's `sent` entries hold `location` and `url` only; the answers to it come from its thread on GitHub.
  `review_state.py add-replies` is gone: the review's agent reads the conversation with `github_conversation.py
  <review dir>`. Update the `code-review` bundle of the workshop together with this version — its `refresh-review`
  reads the conversation that way.

## 0.14.1

- The review page colours the code of a diff by its language — keywords, strings, comments, numbers, types and
  annotations — in every palette, for Java, Kotlin, TypeScript, JavaScript, Python, Go, C#, SQL, shell, YAML, JSON and
  XML; other files stay plain.
- A folder shortened in the file list shows its full path on hover.

## 0.14.0

- The review's session asks before it uses a tool outside its list, instead of being refused: the review page shows the
  request — the tool, what it would run, the rule that would allow it — and waits for **Allow once**, **Always in
  reviews** or **Deny** with a reason the AI Agent reads. **Always in reviews** keeps the rule, editable first, in
  `review-tools`; ⚙ AI Agent tools lists it with a switch to take it back. See REVIEW.md, "The review's session".

## 0.13.3

- ⌫ Archived reviews and ⚙ AI Agent tools open when no review is open too, rather than leaving the new-review wizard
  on the page.
- Starting a review that exists already — archived, or still in progress — no longer stops at an error: the wizard
  offers to bring it back or open it, or to start it over, deleting its findings and answers.
- The review's session runs one command per Bash call, scripts by their full path, and takes a refused command for
  what it is — that one command — rewriting it in the allowed form instead of stopping the review.

## 0.13.2

- A review reads Jira through your Jira MCP server once you allow it. The first time the review's session is refused
  one of the server's tools, the page says so and offers **Allow and go on**; ⚙ in the rail, **AI Agent tools**, lists
  the session's MCP servers with a switch each. The choice applies to every review and is kept as `review-tools` in
  `~/.craftsman/settings.json`; see REVIEW.md, "The review's session".
- The review's session runs git in the worktree as `git -C <worktree>` and may record the plugin version it ran with,
  so neither is refused any more. Update the workshop too: its `code-review` protocols say `git -C`.

## 0.13.1

- `/craftsman:pr-review` takes a pull request on a GitHub Enterprise host, not only on github.com: the checkout's
  remote is checked against that host, a clone is made from it and the comments are sent to it. `gh` has to be signed
  in to the host (`gh auth login --hostname <host>`). The new-review wizard says when the URL is not a pull request's.

## 0.13.0

- A colour palette to pick: ◐ Palette on the dashboard, or ◐ in the review page's rail. Nine dark palettes —
  Graphite, Midnight, Arctic, Slate, Steel, Dim, Ink, Carbon, Mono — and a light one, Paper. The choice applies to
  every craftsman page, the report and rendered diffs included, and is kept in `~/.craftsman/settings.json`.
  Graphite, the palette so far, stays the default.

## 0.12.1

- The dashboard and the review page open at `http://craftsman.localhost:4747`. A `.localhost` name always means this
  machine and browsers resolve it with no entry in `/etc/hosts`; `http://localhost:4747` still works.
- The rail of the review page: reviews are dragged into your own order, and the card beside a tile stays long enough to
  reach Open and Archive.

## 0.12.0

- New: `/craftsman:pr-review [PR URL | target:source]` reviews a pull request on its own page, `/review` on the
  dashboard server. The page has four tabs — Overview, Structure, Code, Findings — and the review's Claude session runs
  on the server, so its questions and progress show on the page. Findings are proposed PR comments to edit, drop or mark
  to send; only the marked ones go to GitHub, when you press Send, and a comment the PR already has is not posted again.
  Each review has its own state and `git worktree`, so several can run at once. Needs the workshop's `code-review`
  bundle and `gh`. The review state is described in `REVIEW.md`; the README's "Reviewing a pull request" describes the
  page.
- `/craftsman:pr-review` runs from any folder. A wizard on the page asks what is reviewed and where its code is read
  from: a checkout, typed or picked with "Browse…", or for a pull request a partial clone in `/tmp/craftsman/repos/`,
  deleted when the review is closed or archived and made again when it resumes.
- Reviews live in `~/.craftsman/reviews/`, apart from the repositories they review; one dashboard server lists them
  all. A review's id names its repository: `<owner>-<repo>-pr-<number>`, or `<checkout folder>-<target>..<source>`.
- The dashboard finds a project registered through a symlink.
- The dashboard server loads its code once, when it starts: after updating the plugin, stop it
  (`/craftsman:dashboard off`) and start it again.

## 0.11.2

- Every craftsman page — the dashboard, reports, diffs and the library page — takes its colours from one shared
  palette: an almost-black background, slightly lighter rounded cards, and indigo, mint, orange, pink and violet
  accents. Nothing changes in what the pages show.

## 0.11.1

- Fixed: `/craftsman:search` no longer takes `Bash` away from itself. Where Claude Code searches through the shell
  rather than a `Grep` tool, that left the skill reading all ten index files in full. Writing is still impossible:
  `Write` and `Edit` stay removed, and the skill runs in the read-only `Explore` agent.

## 0.11.0

- `/craftsman:search` runs in its own context (`context: fork`, read-only `Explore` agent, result in the same turn):
  the grep hits and the files it opens no longer land in the conversation that asked, only the matches do. Its
  tool list is now a restriction (`disallowed-tools`), not just pre-approval. Needs Claude Code 2.1.218 or later.
- The three entry-point commands say when not to use them, each naming the command to use instead. The trigger
  "analyze these requirements" on `domain-design` collided with `analyse` and is now "model these requirements".

## 0.10.1

- Fixed: the session file check after a `Bash` command also finds the file when its path sits in a shell variable.
  A variable the command assigns itself is followed; any other path that cannot be read from the command's text
  falls back to the `.claude/sessions` folder of the directories the command runs in.

## 0.10.0

Independent directive review, after its first real run (`EXECUTION.md`, same name):

- New verdict `CONVENTION`: the change breaks a rule the same way the project's existing code does, and the
  directive yields to the project's convention. The reviewer points to the existing line; the run neither fixes
  nor drops such a finding, it puts it to the developer as its own group at the checkpoint.
- A finding the developer already decided at an earlier checkpoint of the run is listed as already settled, not
  raised again. The run sorts these out from the Checkpoint log; the reviewer is still told nothing.
- Fixes made after a review are reviewed once: one more reviewer, on the files the fixes touched. Whatever that
  round's own fixes change is named at the checkpoint as not reviewed.
- With workshop content from the same date, the TDD loop reviews once, in `finish-loop`, over the whole diff;
  `refactor-production` no longer runs its own review of the same production code.

## 0.9.1

- Fixed: a checkpoint that puts one proposal up to confirm or change ("Right place?", "Move on?") is asked as plain
  text. `AskUserQuestion` needs at least two real alternatives and the rule forbids adding "adjust" as one, so such
  a checkpoint had no valid form; `EXECUTION.md`, "Checkpoint protocol" now says so.
- Fixed: the session file check also runs after a `Bash` command that names a `.claude/sessions` path. A session
  file rewritten by a script or `sed` used to skip the check, which only followed `Write` and `Edit`.

## 0.9.0

- New: delegated read-only preparation (`EXECUTION.md`, same name). Reading that splits into independent parts —
  the sections of a large input, a project's build and configuration files — may go to read-only helpers running
  in parallel: the new plugin agent `craftsman:researcher` (Read, Grep, Glob). Every item comes back with its source
  and the exact words it rests on, the run checks the quotes and the coverage, and each step's checkpoint and
  writes stay in the run. Nothing that waits for the developer is ever delegated.
- New: resuming says what changed. `scripts/changed_since.py` lists commits and files changed, added or deleted since
  the session file was last written, committed or not, with craftsman artifacts called out; a resumed run reads the
  changed files again instead of continuing from what it remembers.

## 0.8.0

- New: a checkpoint that offers discrete alternatives asks through `AskUserQuestion`; open questions stay plain
  text. A picked answer is logged exactly as chosen, and what the developer judges (draft, list, diff) is shown in
  the message before the question, never inside an option.
- New hook: after a session file is written, anything that broke the shape `EXECUTION.md` defines is reported back
  with its line number — a Call stack line without a status, a skipped level, checkpoint entries out of order, an
  answer without an actor, a missing section. Session files in the older format are left alone.

## 0.7.0

- New: independent directive review (`EXECUTION.md`, "Independent directive review"). A protocol that checks a
  change against the directives no longer does it in the session that wrote the change. It hands the diff and the
  directive files to fresh read-only reviewers: the new plugin agent `craftsman:directive-reviewer`, limited to
  Read, Grep and Glob. Groups of up to six directives run in parallel. Every finding cites `file:line` and the rule
  it breaks; the run verifies each one, fixes what holds, and shows fixed, disputed and unchecked findings at the
  checkpoint.
- Used by `finish-loop` and `refactor-production` in `craftsman-workshop` from `bundles/tdd` onwards. With an older
  plugin, or without the `Agent` tool, the run does the check itself and says so.

## 0.6.0

- New: the plugin ships hooks, loaded automatically with it (`hooks/hooks.json`). Outside an open craftsman run they
  do nothing.
  - Commit gate: during a run, `git commit` is denied until the developer has replied since the last commit and the
    Checkpoint log records that answer. Until now this was only an instruction the model could skip.
  - Reload after compaction: when the conversation is compacted during a run, the session file, the current step's
    protocol and every directive in effect are listed with full paths to be read again before the next step.
    Compaction used to drop them silently.
- See `MANAGEMENT.md`, "Hooks". The first tests in the repository cover both: `python3 -m unittest discover -s tests`.

## 0.5.6

- Fix: a session's Parked list only ever grew — items stayed there after they were taken up or settled, because
  nothing said when an item leaves it. Parked now holds only open items. An item leaves it as soon as it becomes an
  ordinary step of the run, its own task (the new session says where it came from), a question in
  `open-questions.md`, or irrelevant (one line in the checkpoint log says why). A decision a later step of the same
  run will take is no longer parked. Before a run ends, every remaining item is reviewed, and the final checkpoint
  says what is still parked.

## 0.5.5

- Docs: `/craftsman:help` and the README's command table now list `remove` in the dashboard's arguments, and help
  says the dashboard covers the current folder and every craftsman project below it.

## 0.5.4

- Fix: the dashboard showed nothing for a repository whose craftsman work lives in sub-folders (`tasks/0017-…/`,
  each with its own `.claude/sessions/`), because it looked only in the folder it was started from — the
  repository's root. It now finds every craftsman project below that folder (up to five levels, hidden and build
  folders skipped), lists them in the project switcher, picks up new ones within about ten seconds, and opens on
  the one with the most recent session activity. `status` lists what was found under each root. The per-write
  `md:`-only announcement applies to those projects too.
- Fix: `/craftsman:dashboard` took the git repository's top level as the project, even when Claude was started in
  a task folder below it. It now takes the current directory — the same folder a craftsman run writes its sessions
  and artifacts to.

## 0.5.3

- Fix: taking the last project off the dashboard left its name and × on the page, and a periodic redraw brought the
  old project's view back. A dashboard with no project is now a real state: the menu says "no project", the centre
  shows how to add one (`/craftsman:dashboard on` from inside it), and Library, Commands and Manage keep working.

## 0.5.2

- Feature: a project can be taken off the dashboard — `/craftsman:dashboard remove` for the current project,
  `remove <dir>` for any other, or the × next to the project's name on the page (it asks first). Only the dashboard
  forgets it; the project's files are untouched. Before this, the only way was `off` and `on` again.

## 0.5.1

- Fix: the dashboard's project switcher named each project by its last folder only, so two projects that both end
  in `workspace` looked identical. It now shows the shortest trailing part of the path that tells them apart
  (`gym/workspace`, `Projects/workspace`), with the full path on hover.

## 0.5.0

- Feature: `/craftsman:dashboard` is now live. It starts a small local web server (`scripts/dashboard_server.py`,
  stdlib only) and prints `http://localhost:4747` — a page to keep open on a second screen. Left: a menu of the
  project's artifacts, specs and sessions, plus the installed content, the commands and versions. Centre: the chosen
  file, in a view built for its shape (slice progress for `event-model.md`, one line per rule, a checklist per spec,
  decisions newest first per session). Right: every session's stack, collapsed to the step running now, unfolding
  level by level, with its parked gaps. The page follows every change on disk by itself; nothing needs re-running.
  Starting it from another project adds that project to the same server (a switcher appears). `on` (default),
  `off` and `status` as arguments. On WSL 2 the URL opens as is in a Windows browser.
- While the dashboard runs for a project, a run's per-write announcement prints only the `md:` path of each file —
  no `html:` link, the page already shows it. Without the server nothing changes: `md:` and `html:` as before.
- Feature: the enable/disable switches on the page really write. `scripts/set_enabled.py` now carries the whole of
  "Enable / disable" — id resolution, bundle cascade, `requires` in both directions, the commit — and both the page
  and `/craftsman:enable` / `/craftsman:disable` call it. A toggle that would change other bundles asks first.
  Install, update, uninstall, rename and merge stay commands for Claude CLI: they need the agent's judgement.
- The static `render_dashboard.py` page is no longer what the skill opens; the script stays for machines where a
  local server is not wanted.

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
