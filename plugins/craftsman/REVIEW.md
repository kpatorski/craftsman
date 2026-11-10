# Review state

What `/craftsman:pr-review` keeps on disk while a review runs: one state the agent writes and the review page reads
and edits. The page shows only what is here. The agent learns about the developer's edits from `review.json`, and
about the developer's requests from the inbox, which the dashboard server passes into the review's Claude session.

## Where it lives

`~/.craftsman/reviews/<review-id>/`, apart from the repository it reviews. `<review-id>` is `<owner>-<repo>-pr-<number>`
for a pull request, or `<checkout folder>-<target>..<source>` (slashes replaced by `-`) for two branches. Nothing is
written into the reviewed repository; `review.json` records the path of its checkout, where the review's session runs.

| File             | Written by                | Holds                                                           |
|------------------|---------------------------|-----------------------------------------------------------------|
| `review.json`    | `scripts/review_state.py` | everything the page shows; the single source of the state       |
| `github.json`    | the dashboard server      | the pull request's conversation, as last read from GitHub       |
| `inbox.jsonl`    | the dashboard server      | messages from the page to the agent, one JSON per line          |
| `session.jsonl`  | the dashboard server      | the review's Claude session as it runs, one stream event a line |
| `session.stderr` | the dashboard server      | what the review's Claude process wrote to stderr                |
| `context.md`     | the dashboard server      | the context given in the wizard, until `init` takes it in       |
| `diff/`          | `scripts/review_state.py` | the diff of every refresh, `<head-sha>.diff`                    |
| `worktree/`      | the agent, the server     | a `git worktree` of the checkout at the reviewed commit         |

### The checkout

A pull request is on github.com or on a GitHub Enterprise host: `https://<host>/<owner>/<repo>/pull/<number>`. The host
is the one the checkout's remote must name, the one a clone is made from, and the one `gh` talks to (`GH_HOST`) when
the comments are sent; `gh` has to be signed in to it (`gh auth login --hostname <host>`).

The review reads the repository from one of two places, chosen in the page's new-review wizard:

- **The developer's checkout** — the top folder of a git repository on this machine, typed or picked with "Browse…"
  (the server opens the system's folder dialog). For a pull request, a checkout whose remotes do not name the PR's
  repository is accepted with a warning. Two branches are always reviewed in a checkout.
- **A clone** — for a pull request only: a partial clone (`--filter=blob:none`) the server makes in
  `/tmp/craftsman/repos/<owner>/<repo>/`. Only the files the worktree checks out are downloaded.

Either way the code is read from the review's own `worktree/`, so the checkout's branch and uncommitted changes are
never touched. Closing or archiving a review deletes its worktree, and its clone when no other open review reads from
it. Resuming a review whose clone or worktree is gone — `/tmp` is emptied on restart — makes them again at the reviewed
commit before its session starts; the page says "Restoring the repository…" meanwhile, and why if it fails. A missing
checkout of the developer is never made again: the page says it is missing.

Nobody edits `review.json` by hand, the agent included. Every change goes through `review_state.py`, which takes a
lock, checks the change, and writes the file atomically. The agent and the page change the same file at the same
time; this is what keeps either of them from losing the other's change.

## `review.json`

### Source and revision

- `source` — either `{"kind": "pull-request", "url", "repository", "number", "title", "base-branch", "head-branch"}`
  or `{"kind": "branches", "target", "source", "pull-request": <the same object, or null>}`. `pull-request` is null
  when no PR exists for the source branch; sending is then disabled and the page says why. The page shows the PR's
  title as the review's title.
- `checkout` — the path of the repository's checkout the review reads from and its session runs in.
- `base` and `head` — the commit shas the review was made against. Only `init` and `refresh` set them, each with the
  diff between them, kept as `diff/<head>.diff`: `review_state.py <review dir> refresh '{"base", "head", "diff"}'`,
  run by the agent, moves the review to a new head.
- `refreshed` — when `base`/`head` were last read.
- `closed` — when the developer closed the review, or null while it is open.
- `language` — the language the comments are written in, settled when the review is opened.
- `session` — the id of the Claude session the dashboard server runs for this review. `claude --resume <id>` opens
  the same conversation in the CLI.

### Understanding

What the page shows above the findings. Every text field is GitHub markdown.

- `scope` — what the PR is about, from its description, in three parts: how the system behaves before the change,
  how it behaves after, and what the PR leaves out.
- `requirements` — what the linked Jira ticket asks for; `tickets` lists the keys found in the description. Empty,
  with the reason in `requirements`, when no ticket is linked or Jira cannot be read.
- `context` — what the developer tells the agent that the pull request does not say: why the change is built this
  way, what in the ticket is out of date, what to look at closely. A list of notes, `{"id", "text", "at"}`, written
  only by the developer: sent from the review page's Overview tab (`add-context`), taken back there
  (`remove-context <id>`), or given in the new-review wizard. The agent reads every note before every step and weighs
  them like the description; where they disagree, it asks. The wizard's text waits as `context.md` in the review's
  folder until `init` makes it the first note.
- `structure` — the shape of the change: `use-cases`, each `{"id", "name", "says", "before", "after", "entry",
  "files": [...], "status", "flow"}`:
  - `says` — one sentence on what the use case does, for someone who has not read the code;
  - `before` and `after` — how the system behaves in this use case without the change and with it, one to three
    sentences each;
  - `entry` — the file and line where the use case starts;
  - `files` — every changed file of the use case: reached by its calls, declaring a type its steps use, or else in a
    package where only this use case has files (`map-change-structure`); a file of several use cases is in each;
  - `status` — `pending`, `reviewing` or `reviewed`;
  - `flow` — how the use case runs: `steps`, each `{"call", "path", "line", "change", "crosses", "from"}`, from the
    entry point down through the change, where `path` and `line` are where the called unit is defined, `change` is
    `added`, `modified`, `deleted` or `unchanged`, `crosses` is null or the boundary the call should not cross, and
    `from` is `{"path", "line"}` of the call itself, absent on the entry point; and `branches`, each
    `{"what", "tested"}`, the ways the use case can end and whether a test covers each.
- `rules` — business rules read from the test suites, each `{"id", "rule", "test", "requirement"}`; `test` is
  `path:line`, `requirement` says which requirement it covers, or that none does.

The page lists the use cases as cards. Pointing at a card shows what it says and its files, and marks the use cases
that share a file with it; clicking a card opens its files, its flow and their diff beside the cards.

### What the server adds

The page reads `review.json` together with what the server works out from the diff of `head`, so no changed file can
be missed:

- `files` — every changed file: `path`, `change` (`added`, `modified`, `deleted`, or `renamed` with `from`), the
  lines it adds and removes, the use cases it belongs to, whether the developer viewed it, and `declaration`: the
  kind (`class`, `interface`, `record`, `enum`, `annotation`) and visibility (`public`, `package`, `private`) of its
  top-level type, from `scripts/_declarations.py`, or null. Java, Groovy and Kotlin give both; TypeScript gives the
  kind of its one exported class, interface or enum, with a null visibility. The type is read from the file in
  `worktree/`, or from the diff's lines when the file is deleted or the worktree is missing;
- `untied` — the changed files no use case reaches. The page shows them as one more card, so every changed file is
  in a card;
- `github` — the content of `github.json`, or null before the conversation was first read;
- `directives` — every directive the review could check, from `review_directives.py`: `id`, `title`, `description`,
  `bundle`, `path`, `enabled` (by the workshop) and `on` (for this review) — see "Directives";
- `protocols` — the protocols of the `code-review` bundle, in order, each with `id`, `title` and `enabled`;
- `missing-diff` — `head` when `diff/<head>.diff` is missing, or null. The Code tab then says so instead of a diff,
  and `files` is empty.

For a deleted file, the server also lists where the reviewed code in `worktree/` still names it. On request it lists
the files of `worktree/` the diff leaves as they are (`/api/review/files`), and serves one file of `worktree/` as the
pull request's branch has it (`/api/review/file`); a path outside `worktree/`, or into its `.git`, is refused.

### The developer's reading

- `viewed` — the paths of the changed files the developer marked as viewed. Only the developer marks a file viewed.
  A refresh takes a file off when its change in the new diff differs from the one viewed, or when it is no longer in
  the diff; a change that only moved to other lines on a new base stays viewed.
- `archived` — true once the developer archived the review; the page then leaves it out of the list of reviews, and
  lists it under ⌫, Archived reviews, to bring back. Starting the same pull request or branches again in the wizard
  offers to bring it back, or to start it over: starting over deletes the review's folder, its findings and answers
  with it, and opens it anew.
- `threads` — questions about a part of the review, and notes the agent writes unasked: `{"id", "about", "quote",
  "status", "messages"}`:
  - `about` — `{"kind": "review"}`, `{"kind": "finding", "id"}`, `{"kind": "use-case", "id"}`, or `{"kind": "file",
    "path", "lines": [first, last]}`;
  - `quote` — the text or the lines the developer selected, or null;
  - `status` — `open`, or `resolved` once the developer resolves it; a new message from the developer opens it
    again;
  - `messages` — `{"by", "at", "text"}`, where `by` is `developer` or `agent` and `text` is GitHub markdown.

### Checkpoint

`checkpoint` is the question the run is stopped on, or null. `{"id", "step", "question", "options": [...],
"answer"}`. `answer` is null until the developer answers — on the page or in the CLI — and then `{"option", "note",
"by"}`.

### Findings

`findings` — each one:

- `id` — `f<number>`, never reused.
- `category` — the group on the page, e.g. `naming`, `boundaries`, `security`.
- `by` — `agent`, or `developer` for a finding the developer added; theirs needs only a title, the comment, the
  locations and the severity, and gets the category `yours`.
- `severity` — `must-fix`, `should-fix` or `nit`.
- `title` — a few words.
- `description` — a short introduction to what it is about.
- `comment` — the proposed PR comment: what is wrong, why it matters, the proposed solution.
- `locations` — `{"path", "line", "side", "commit"}`, one or more. The first is where the comment goes; every
  other location gets a short reference to it. `line` is null for a finding about the whole file.
- `directive` — the id of the directive it comes from, or null.
- `kind` — `violation`; `new-convention` (the project does it this way elsewhere, new code need not); `scout` (the
  change leaves nearby code no better than it found it); `out-of-scope` (worth doing, outside this PR).
- `when` — for `out-of-scope` only: `now` or `later`.
- `status` — `proposed`, `to-send`, `sent`, `deleted`, `maybe-resolved`, or `merged`. The AI Agent's finding starts
  `proposed`; the developer's own starts `to-send`.
- `merged-into` — for `merged` only: the id of the finding this one was joined into, as one problem in several
  places. A `merged` finding is never sent; the page shows it folded under that finding.
- `edited` — the fields the developer changed: any of `title`, `description`, `comment`, `severity`.
- `in-prompt` — `false` when the developer leaves the finding out of the fix prompts; missing or `true` otherwise. Set
  with `review_state.py <review dir> in-prompt <id> '{"included": true | false}' --by developer`, also once the
  finding is sent.
- `sent` — `{"location", "url"}` for each comment posted to GitHub. The answers to it are in its thread in
  `github.json`.

### Drafts

`drafts` — the developer's drafts of findings, one per file, by the file's path, written in the comment panel of the
Code tab. Each one:

- `text` — the comment so far, in markdown.
- `lines` — `[first, last]`, the lines it is about, or null for the whole file.
- `side` — `RIGHT` or `LEFT`, the side of the diff the lines are on.
- `style` — the shape asked for this draft's comment where it differs from the default one (see below); missing when
  it does not.
- `at` — when it was last saved.

Only the developer writes them, with `review_state.py <review dir> <command> '<payload>' --by developer`:

- `save-draft` `{"path", "text", "lines", "side", "style"}` — writes the file's draft, replacing the one before; a
  `style` with a key or value not listed below is refused;
- `discard-draft` `{"path"}` — throws it away;
- `draft-to-finding` `{"path", "severity", "title", "comment", "category", "description", "repeats"}` — makes it the
  developer's own finding, on the last of its lines or on the whole file, and removes the draft. A field not given
  comes from the draft: its text is the comment, and the first sentence of the comment's prose is the title, cut to 80
  characters. With `repeats`, the id of a finding not yet sent, no finding is made: the draft's place joins that one.
  An empty draft makes no finding.

With the panel's "AI Agent assistant" switch on, the default, the developer writes or dictates their thoughts in their
own words, and AI Agent writes them up as the finding: a moment after the developer stops, the page asks the server's
`/api/review/draft-preview`. The server runs a short Claude call of its own for it (`scripts/_draft_preview.py`), not
the review's session, with a small model (`haiku`, or `CRAFTSMAN_PREVIEW_MODEL`) and no tools. Its prompt holds the
draft, the code around the draft's lines from the diff, the `code-review` bundle's directives `review-comment`,
`review-posture` and `engineer-prose`, the findings already in the file, the review's categories and its `language`,
the shape of the comment asked for, and the severity when the developer picked one. It answers the title, category,
severity, description and comment, in the review's language whatever the draft's, and the finding of the file it
repeats. A newer draft of the same file stops the call still running for the older one. The panel shows the answer
above the draft, and "Make it a finding" sends it with `draft-to-finding`. "Make it a finding" waits while AI Agent
writes, and while its comment is older than the draft.

The shape of the comment asked for wins where it differs from the directives:

| Key        | Values                                           | Default    | Asks for                                                                                                                                                                                |
|------------|--------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `fidelity` | `verbatim`, `close`, `balanced`, `loose`, `free` | `close`    | the draft's sentences, translated and corrected; its words and strength, nothing added; its points in other words; its points in the order that reads best; a comment of AI Agent's own |
| `tone`     | `casual`, `teammate`, `formal`                   | `teammate` | how it sounds                                                                                                                                                                           |
| `detail`   | `brief`, `normal`, `detailed`                    | `normal`   | one or two sentences; as long as the draft calls for; a paragraph or two                                                                                                                |
| `code`     | `false`, `true`                                  | `false`    | a code sample of the fix at the end; a code block in the draft is kept either way                                                                                                       |

With `verbatim` or `close` the comment keeps the draft's words, so `tone` and `detail` are not asked for: the tone and
the length are the draft's, and the panel greys their sliders. The default shape is `comment-style` in
`~/.craftsman/settings.json`, set on the page's AI Agent tools tab; the panel's sliders and box ask for another shape
for one draft, kept in its `style`. The severity sets how firmly the comment says it: `must-fix` as a change required
before the merge, `should-fix` as a clear recommendation, `nit` as minor and optional. A severity the developer picks
goes to the call; without one, the call picks it and writes the comment that firmly. Picking a severity, or moving a
slider, writes the comment again.

The developer corrects AI Agent's comment and title by hand with "Edit". The correction is pinned: a newer draft does
not write over it, and the panel offers to write it again from the draft instead.

### Fix prompts

The Findings tab's "Fix prompts → comment" writes one comment on the whole pull request for the author's own AI coding
agent, made by `scripts/fix_prompts.py` from the findings marked to send or sent whose `in-prompt` is not `false`. It
holds one prompt per category, each in a fenced block longer than any run of backticks inside it: what is reviewed and
at which commit, every finding of the category — place, title, comment and its other places — and the ask to make these
fixes and nothing else as one commit. The developer's findings with no category of their own go in one prompt headed
"Other fixes". A prompt names no severity; its findings come worst first. The comment goes in word for word, so a
finding whose comment says it holds for every place in the change ("please remove these everywhere you added them") is
fixed everywhere: the prompt says such a fix covers every such place. Categories come worst severity first. The comment
starts with `<!-- craftsman:fix-prompts -->`; while it waits for Send, writing the prompts again rewrites it, and once
it is sent, the next one is a new comment.

### Comments

`comments` — what the developer writes to the pull request apart from the findings: a comment on the whole pull
request, or a reply in a thread on GitHub. Only the developer writes them, on the review page. Each one:

- `id` — `c<number>`, never reused.
- `body` — GitHub markdown, sent as written.
- `reply-to` — the id of the first comment of the GitHub thread it answers, or null for a comment on the whole pull
  request.
- `status` — `to-send` from the start, `deleted` once dropped, `sent` once it is on GitHub.
- `url` — its link on GitHub once sent, else null.
- `at` — when it was written.

### Directives

The review checks the change against every directive it has switched on, never a choice the agent makes.
`scripts/review_directives.py <review dir>` prints them, `[{"id", "title", "path", "files", "reach"}]`: every directive
of the workshop, top-level or in an enabled bundle, that is switched on: by the review's own switch, else by the
developer's default set for every review (`review-directives` in the craftsman settings), else by the workshop. The
directives of the `code-review` bundle are not among them: they say how a finding is kinded and written.

How each directive is checked comes from the `code-review` bundle's `directive-scope.md`, a table with a row per
directive; the directives themselves know nothing of the review:

- `files` — `production`, `tests` or `all`: the changed files it is checked on. A directive whose row says `none`
  (writing specs or commits, or only gathering other directives) is not checked in a review and is not printed.
- `reach` — `file` when one file is enough to judge it, `flow` when it needs the use case.

A directive with no row, or a row with values the script does not know, is checked on `all` files with `flow` reach.
`review_directives.py [<review dir>] --unscoped` prints the ids of the directives checked without a row; without a
review, those the developer's default set checks. The Rules tab, the dashboard's Library and `pr-review`, when the
developer starts it, name them.

`review_directives.py <review dir> --plan` prints the reviewers the review starts, worked out from the diff,
`structure` and the table, so the agent never sorts them itself:

- `reviewers` — `{"reach", "use-cases": [{"id", "files"}], "directives": [{"id", "path"}], "files"}`, at most six
  directives each. The `file` directives are checked once over every changed file of their kind, in batches of about
  1500 changed lines, with `use-cases` empty; the `flow` ones per use case, on the files of their kind it is the first
  to have, and on the untied files last, as the use case `untied`. One `flow` reviewer takes use cases in order up to
  about 1500 changed lines, each as its own flow; a bigger use case has its own. A deleted file is not checked. The
  review starts every reviewer before the first use case, and each use case takes its part of their reports.
- `not-applicable` — `{"use-case", "directive", "note"}`: a use case with no file of the directive's kind, recorded
  as it is.
- `file-checks` — `{<use case>: [<directive id>]}`: the `file` directives a use case records from its findings.

A test file is one in a `test`, `tests` or `__tests__` folder, or named `*Test.*`, `*Tests.*`, `*Spec.*`, `*.test.*`,
`*.spec.*` or `test_*.py`; every other changed file is production code.

- `directive-switches` — `{<directive id>: true | false}`, what the developer switched on or off for this review on
  the Rules tab. A directive not named here follows the default set. Only the developer changes it. "Make this set the
  default for every review" stores the review's set, where it differs from the workshop, as `review-directives`, and
  empties the review's own switches.
- `checks` — what each directive found in each use case: `{"use-case", "directive", "result", "note", "at"}`, where
  `use-case` is a use case's id or `untied` (the changed files no use case reaches), and `result` is `findings`,
  `clean`, `not-applicable` (with the reviewer's reason in `note`) or `failed` (the reviewer did not answer for it). A
  later check of the same directive in the same use case replaces the earlier one. Only the agent records them:
  `review_state.py <review dir> record-check '{"use-case", "directive", "result", "note"}'`, or a list of them in one
  call, recorded all or none.

The Rules tab lists every directive with its switch and a dot per use case for what it found there; a directive
switched on with a reviewed use case it has not checked offers "Check now", which asks the agent to check it there.
The tab also lists the review's protocols; they are switched in the workshop, not per review.

## Rules on changing the state

- **The developer's edits win.** The agent never changes a field listed in a finding's `edited`. To propose a
  different text it adds a new finding. The agent never writes or changes a comment.
- **Nothing is removed.** Deleting sets `deleted`; joining two findings sets `merged` on one of them; neither is
  ever sent. A refresh that no longer sees the problem sets `maybe-resolved`; only the developer decides it is gone.
- **Sent is final.** A `sent` finding or comment is not edited or sent again; a follow-up is a new one.
- **Only `to-send` is sent.** Sending posts every `to-send` finding and comment, and changes it to `sent` only once it
  exists on GitHub. A finding goes as an inline comment, on a removed line too; one about a whole file of the change
  goes on that file. A place outside the diff, or a whole file GitHub takes no comment on, goes to the pull request's
  conversation naming its place. A comment on the whole pull request goes to its conversation, a reply into its
  thread. A comment already on the pull request, at the same place with the same text, is not posted
  again; its link is recorded. When what is on the pull request cannot be read, nothing is posted.

## `github.json`

What everyone wrote on the pull request, read with `gh api` by `scripts/github_conversation.py` when the review page
opens the review, after every Send, and when the developer asks for it again. A review of two branches has none. The
agent reads it again by running `github_conversation.py <review dir>`, which prints where it is kept, how many comments
it holds, and why GitHub did not answer, or null.

- `fetched` — when it was last read.
- `error` — why the last read failed, or null. A failed read keeps the comments read before.
- `comments` — oldest first, each with `id`, `kind`, `author`, `at`, `body` (GitHub markdown) and `url`:
  - `issue` — a comment in the pull request's conversation;
  - `review` — a review with its text, or one that approved or asked for changes; `state` says which;
  - `inline` — a comment on the code, with `path`, `line` (null once the line is no longer in the pull request),
    `original-line`, `side`, and `root`: the id of the thread's first comment, the one a reply answers.

The page shows it under Comments, with the developer's own comments waiting for Send; a thread on a line of the diff
also shows under that line, unless a sent finding started it — then it shows with the finding. The page renders the
markdown with its HTML escaped, so what others wrote is shown as text.

## `inbox.jsonl`

The page appends one line per request: `{"id", "at", "type", ...}`. The server passes every line into the review's
Claude session as a message, in order, once the session has finished its current turn. The agent handles it and
records its `id` in `review.json`'s `handled`. When the server starts the session again, for a review that has lines
not yet in `handled`, it passes those first.

| `type`    | Carries                        | The agent                                                      |
|-----------|--------------------------------|----------------------------------------------------------------|
| `answer`  | `checkpoint`, `option`, `note` | goes on; the server has recorded the answer already            |
| `ask`     | `thread`                       | reads the thread's last message and replies in the same thread |
| `refresh` | —                              | reads the PR or branches again, re-checks the findings         |
| `close`   | —                              | sets `closed` and ends the run                                 |
| `check`   | `directive`                    | checks the use cases already reviewed against that directive   |
| `context` | —                              | reads the notes in `context` and works by them from now on     |

A question from the page opens a thread, or adds to one, before its `ask` line is written.

A note of context is added to or taken out of `review.json` before its `context` line is written.

Edits, deletions, "to send", comments, "viewed", directive switches and archiving on the page do not go through the
inbox: the server applies them to `review.json` through `review_state.py` directly, and the agent sees them the next
time it reads the state.

## The review's session

The dashboard server runs the review's Claude session headless: `claude -p`, in the checkout, with the review folder —
which holds `worktree/` — as a second working directory (`--add-dir`). The tools on a fixed list run without asking:

- reading and searching files, subagents, skills;
- `git` and `gh` commands, each started as `git …` or `gh …` — git in the worktree runs as `git -C <worktree> …`,
  because a `cd` followed by `git` is a command of its own;
- the craftsman scripts, by their full path;
- writing the checkout's `.claude/sessions/` files and the plugin-version marker of the installed content;
- the tools listed as `review-tools` in `~/.craftsman/settings.json`.

For any other tool the session asks the server (`--permission-prompt-tool stdio`) and waits. The page shows the request
at the top of the review — the tool, what it would run or open, and the rule that would allow it — and the developer
answers:

- **Allow once** — that one call runs;
- **Always in reviews** — the rule, edited first if wanted (`Bash(npm test)` widened to `Bash(npm test:*)`), is added
  to `review-tools` and to the running session, so neither this review nor the next one asks for it again;
- **Deny** — the agent is told the developer did not allow it, with the reason typed beside it, and goes on.

For a tool of an MCP server the rule offered is the whole server, `mcp__<server>`.

`review-tools` is also how the session reads Jira, through the MCP server Jira is read through. The page sets it:

- the requests above;
- when the session is refused a tool of an MCP server, a banner names the server and offers **Allow and go on** — the
  server is allowed in every review, and the session restarts and does again what was refused;
- ⚙ in the rail opens **AI Agent tools**: every MCP server the session connected to, and every one allowed, each with
  a switch, and every other rule allowed from a request, with a switch to take it back. A change there applies when
  the session starts next.

Allowing a server allows every tool it has, writing ones too. In `settings.json` a server is `mcp__<server>`, its name
with every character other than a letter, a digit, `_` and `-` made `_`:

```json
{ "review-tools": ["mcp__jira", "Bash(npm test:*)"] }
```

## `session.jsonl`

Every event of the review's Claude session (`--output-format stream-json`), appended by the server as it arrives. The
page shows what the session is doing in its header, and the whole log on request: the agent's text, the tools it
calls, refused tools, and the end of each turn. A subagent's result arrives in a later turn than the one that started
it, so the log never waits for one answer per message.
