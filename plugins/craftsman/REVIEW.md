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

- `source` — either `{"kind": "pull-request", "url", "repository", "number"}` or `{"kind": "branches", "target",
  "source", "pull-request": <the same object, or null>}`. `pull-request` is null when no PR exists for the source
  branch; sending is then disabled and the page says why.
- `base` and `head` — the commit shas the review was made against.
- `refreshed` — when `base`/`head` were last read.
- `closed` — when the developer closed the review, or null while it is open.
- `language` — the language the comments are written in, settled when the review is opened.
- `session` — the id of the Claude session the dashboard server runs for this review. `claude --resume <id>` opens
  the same conversation in the CLI.

### Understanding

What the page shows above the findings. Every text field is GitHub markdown.

- `scope` — what the PR is about, from its description.
- `requirements` — what the linked Jira ticket asks for; `tickets` lists the keys found in the description. Empty,
  with the reason in `requirements`, when no ticket is linked or Jira cannot be read.
- `structure` — the shape of the change:
  - `use-cases` — `{"id", "name", "entry", "files": [...], "status"}`; `entry` is the file and line where the use
    case starts; `status` is `pending`, `reviewing` or `reviewed`;
  - `contexts` — `{"id", "name", "files": [...]}`;
  - `boundaries` — one markdown text on how the parts talk to each other and where they should not;
  - `links` — `{"from", "to", "how", "doubt"}` per pair of contexts that talk in this change; `how` is `call`,
    `event`, `http` or `table`; `doubt` is null, or one sentence on why the direction looks wrong.

The page draws `structure` as one small graph: use cases on the left, each joined to the contexts its files are in,
and the contexts joined by `links`, a doubtful link marked. Never a node per class or file. With more than 12 use
cases and contexts together, the graph shows only the contexts and their links, and a context opens to its use cases
on a click. The graph is a way into the rest of the page:

- pointing at a node lights up everything joined to it;
- clicking a use case or a context narrows the PR map, the explanations and the findings to its files, until the
  filter is cleared;
- clicking a link shows how the two contexts talk and, for a doubtful one, why.
- `rules` — business rules read from the test suites, each `{"id", "rule", "test", "requirement"}`; `test` is
  `path:line`, `requirement` says which requirement it covers, or that none does.

### Context for the reviewer

- `map` — the PR map: `{"id", "name", "summary", "files": [...]}` per group of files belonging to one use case or
  component. Every changed file is in exactly one group.
- `explanations` — `{"id", "about", "origin", "body", "status"}`:
  - `about` — `{"kind": "group" | "file" | "finding", "id"}`, where a file's `id` is its path;
  - `origin` — `triage` (written unasked, for a non-obvious place) or `requested` (the developer asked);
  - `status` — `pending` while the agent writes it, then `ready`.

### Checkpoint

`checkpoint` is the question the run is stopped on, or null. `{"id", "step", "question", "options": [...],
"answer"}`. `answer` is null until the developer answers — on the page or in the CLI — and then `{"option", "note",
"by"}`.

### Findings

`findings` — each one:

- `id` — `f<number>`, never reused.
- `category` — the group on the page, e.g. `naming`, `boundaries`, `security`.
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
- `edited` — the fields the developer changed: any of `title`, `description`, `comment`.
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

| `type`    | Carries                        | The agent                                              |
|-----------|--------------------------------|--------------------------------------------------------|
| `answer`  | `checkpoint`, `option`, `note` | goes on; the server has recorded the answer already    |
| `explain` | `about`                        | adds a `requested` explanation and writes it           |
| `refresh` | —                              | reads the PR or branches again, re-checks the findings |
| `ask`     | `text`, `about`                | answers in a new explanation about the same thing      |
| `message` | `text`                         | answers in the console, like a message typed in a CLI  |
| `close`   | —                              | sets `closed` and ends the run                         |

Edits, deletions and "to send" on the page do not go through the inbox: the server applies them to `review.json`
through `review_state.py` directly, and the agent sees them the next time it reads the state.

## `session.jsonl`

Every event of the review's Claude session (`--output-format stream-json`), appended by the server as it arrives. The
page's console panel shows it: the agent's text, the tools it calls, refused tools, and the end of each turn. A
subagent's result arrives in a later turn than the one that started it, so the console never waits for one answer
per message.
