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
- `base` and `head` — the commit shas the review was made against.
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
- `structure` — the shape of the change: `use-cases`, each `{"id", "name", "says", "before", "after", "entry",
  "files": [...], "status", "flow"}`:
  - `says` — one sentence on what the use case does, for someone who has not read the code;
  - `before` and `after` — how the system behaves in this use case without the change and with it, one to three
    sentences each;
  - `entry` — the file and line where the use case starts;
  - `files` — every changed file the use case reaches; a file reached by several use cases is in each of them;
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
  lines it adds and removes, the use cases it belongs to, and whether the developer viewed it;
- `untied` — the changed files no use case reaches. The page shows them as one more card, so every changed file is
  in a card;
- `github` — the content of `github.json`, or null before the conversation was first read.

For a deleted file, the server also lists where the reviewed code in `worktree/` still names it.

### The developer's reading

- `viewed` — the paths of the changed files the developer marked as viewed. Only the developer changes it.
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
  other location gets a short reference to it.
- `directive` — the id of the directive it comes from, or null.
- `kind` — `violation`; `new-convention` (the project does it this way elsewhere, new code need not); `scout` (the
  change leaves nearby code no better than it found it); `out-of-scope` (worth doing, outside this PR).
- `when` — for `out-of-scope` only: `now` or `later`.
- `status` — `proposed`, `to-send`, `sent`, `deleted`, `maybe-resolved`, or `merged`.
- `merged-into` — for `merged` only: the id of the finding this one was joined into, as one problem in several
  places. A `merged` finding is never sent; the page shows it folded under that finding.
- `edited` — the fields the developer changed: any of `title`, `description`, `comment`, `severity`.
- `sent` — `{"location", "url"}` for each comment posted to GitHub. The answers to it are in its thread in
  `github.json`.

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

## Rules on changing the state

- **The developer's edits win.** The agent never changes a field listed in a finding's `edited`. To propose a
  different text it adds a new finding. The agent never writes or changes a comment.
- **Nothing is removed.** Deleting sets `deleted`; joining two findings sets `merged` on one of them; neither is
  ever sent. A refresh that no longer sees the problem sets `maybe-resolved`; only the developer decides it is gone.
- **Sent is final.** A `sent` finding or comment is not edited or sent again; a follow-up is a new one.
- **Only `to-send` is sent.** Sending posts every `to-send` finding and comment, and changes it to `sent` only once it
  exists on GitHub. A finding goes as an inline comment, a comment on the whole pull request to its conversation, a
  reply into its thread. A comment already on the pull request, at the same place with the same text, is not posted
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

A question from the page opens a thread, or adds to one, before its `ask` line is written.

Edits, deletions, "to send", comments, "viewed" and archiving on the page do not go through the inbox: the server
applies them to `review.json` through `review_state.py` directly, and the agent sees them the next time it reads the
state.

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
