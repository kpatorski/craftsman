# Review state

What `/craftsman:pr-review` keeps on disk while a review runs: one state the agent writes and the review page reads
and edits. The page shows only what is here. The agent learns about the developer's edits from `review.json`, and
about the developer's requests from the inbox, which the dashboard server passes into the review's Claude session.

## Where it lives

`<project>/.claude/reviews/<review-id>/`, where `<project>` is the checked-out repository and `<review-id>` is
`pr-<number>` for a pull request, or `<target>..<source>` (slashes replaced by `-`) for two branches.

| File             | Written by                | Holds                                                           |
|------------------|---------------------------|-----------------------------------------------------------------|
| `review.json`    | `scripts/review_state.py` | everything the page shows; the single source of the state       |
| `inbox.jsonl`    | the dashboard server      | messages from the page to the agent, one JSON per line          |
| `session.jsonl`  | the dashboard server      | the review's Claude session as it runs, one stream event a line |
| `session.stderr` | the dashboard server      | what the review's Claude process wrote to stderr                |
| `diff/`          | `scripts/review_state.py` | the diff of every refresh, `<head-sha>.diff`                    |

Nobody edits `review.json` by hand, the agent included. Every change goes through `review_state.py`, which takes a
lock, checks the change, and writes the file atomically. The agent and the page change the same file at the same
time; this is what keeps either of them from losing the other's change.

## `review.json`

### Source and revision

- `source` — either `{"kind": "pull-request", "url", "repository", "number", "title", "base-branch", "head-branch"}`
  or `{"kind": "branches", "target", "source", "pull-request": <the same object, or null>}`. `pull-request` is null
  when no PR exists for the source branch; sending is then disabled and the page says why. The page shows the PR's
  title as the review's title.
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
  in a card.

For a deleted file, the server also lists where the reviewed code in `worktree/` still names it.

### The developer's reading

- `viewed` — the paths of the changed files the developer marked as viewed. Only the developer changes it.
- `archived` — true once the developer archived the review; the page then leaves it out of the list of reviews.
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
- `sent` — `{"location", "url", "replies"}` for each comment posted to GitHub; `replies` are
  `{"author", "at", "body"}`, read from GitHub on every refresh and only shown, never answered by the agent.

## Rules on changing the state

- **The developer's edits win.** The agent never changes a field listed in a finding's `edited`. To propose a
  different text it adds a new finding.
- **Nothing is removed.** Deleting sets `deleted`; joining two findings sets `merged` on one of them; neither is
  ever sent. A refresh that no longer sees the problem sets `maybe-resolved`; only the developer decides it is gone.
- **Sent is final.** A `sent` finding is not edited or sent again; a follow-up is a new finding.
- **Only `to-send` is sent.** Sending posts every `to-send` finding and changes it to `sent` only once its comment
  exists on GitHub.

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

Edits, deletions, "to send", "viewed" and archiving on the page do not go through the inbox: the server applies them
to `review.json` through `review_state.py` directly, and the agent sees them the next time it reads the state.

## `session.jsonl`

Every event of the review's Claude session (`--output-format stream-json`), appended by the server as it arrives. The
page shows what the session is doing in its header, and the whole log on request: the agent's text, the tools it
calls, refused tools, and the end of each turn. A subagent's result arrives in a later turn than the one that started
it, so the log never waits for one answer per message.
