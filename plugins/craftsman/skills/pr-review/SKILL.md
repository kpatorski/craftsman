---
name: pr-review
description: >
  Reviews a pull request, or what one branch adds on top of another, in a HUMAN <-> AI loop: what the PR is for, the
  structure of the change, the business rules in its tests, then the code use case by use case — every finding a
  proposed PR comment the developer edits, picks and sends from the review page the dashboard server serves. The
  page is the console: the review's Claude session runs on the dashboard server, so the developer never switches
  between the page and the CLI. Runs from any folder; several reviews can run at once. Not for writing code (that is
  `implement`). Trigger: "/craftsman:pr-review", "review this PR", "review pull request", "review main:feature-x",
  "resume the review".
argument-hint: "[GitHub pull request URL | target:source]"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, Agent, Skill]
---

# pr-review

Two places run this skill, and `$ARGUMENTS` tells them apart.

## Started by the developer (no `--headless`)

The review does not run in this session. It runs in a session the dashboard server starts for it, so that the review
page can talk to it — see `REVIEW.md`. The folder this session runs in plays no part: the developer names the
repository's checkout, or agrees to a clone, on the review page.

1. Run `scripts/dashboard_server.py review`, with `--source <$ARGUMENTS>` when `$ARGUMENTS` is not empty. It starts
   the dashboard server if needed, without adding this folder to the dashboard, and prints the review page's URL: a
   pull request already under review opens there and its session resumes; anything else opens the new-review wizard,
   with the source filled in when one was given.
2. Print the URL on its own line, and say that everything else happens on that page: where the code is read from, the
   questions, the findings, the console. Nothing more happens in this session.

## Started by the dashboard server (`--headless <source> --review <folder> --checkout <path>`)

This session is the review. Nobody reads its terminal: the developer sees it on the review page. It runs in the
repository's checkout; the review's state lives in the folder after `--review`, the `<review dir>` of every
`review_state.py` command.

1. **Load [EXECUTION.md](../../EXECUTION.md)** and **[REVIEW.md](../../REVIEW.md)**.
2. **Resolve the `pr-review` entry-point protocol and execute it** per EXECUTION.md's dispatch rules, with the source
   after `--headless`, the review's folder and the checkout as its input.
3. Every change to the review's state goes through `scripts/review_state.py`, never by editing `review.json`. Its
   payload is one JSON argument in single quotes, an apostrophe inside it written as `\u0027`, never a
   heredoc or a pipe.
   This session runs `git`, `gh` and the plugin's scripts without asking, each named by its full path at the start of
   the command, one command per Bash call. Anything else waits until the developer allows it on the review page — a
   command that starts with a variable (`S=...; python3 $S`) or a `cd`, chains commands (`;`, `&&`, `|`, `2>&1 | head`),
   writes a file with `>`, or runs any other program (`sed`, `cat`) — so use the allowed form wherever there is one, and
   ask only for what the review needs. Git in the worktree runs as `git -C <worktree> …`. Files are read with Read,
   searched with Grep; a diff is read from the review's `diff/` folder or printed by `git diff`, never saved to `/tmp`.
   **A refusal is about that one command, never about Bash as a whole.** When the developer denies a command, read
   the reason they give and go on without it, or the way the reason says; do not stop the review, and do not ask the
   developer to switch Bash on. Only a command already in the allowed form that is refused is worth saying, with the
   command exactly as run.
4. **Checkpoints go through the review page, not `AskUserQuestion`** — that tool has no one to ask here:
    - `ask`: write the question with `review_state.py <review dir> set` as `checkpoint` — `{"id", "step", "question",
      "options", "answer": null}` — say in one line that the question is on the page, and end the turn. The answer
      arrives as a message of type `answer`; the server has recorded it already. Then clear `checkpoint` (set it to
      null) and go on.
    - `notify`: say it in the turn's text; it shows in the console.
5. A message from the review page arrives as a user message naming its id and its JSON. Handle it as `serve-page`
   says, then record it with the command given in the message.
6. Never post anything to GitHub. Sending is the developer's, from the page.

## Notes

- One review per pull request or pair of branches, in `~/.craftsman/reviews/<review-id>/` (see `REVIEW.md`). Starting
  the same one again resumes it.
- `claude --resume <session id>` opens the review's conversation in the CLI; the page's "Continue in CLI" stops the
  server's session first, so two processes never write to one session.
- Nothing here duplicates EXECUTION.md. If this file and EXECUTION.md ever seem to disagree on mechanics, EXECUTION.md
  wins — except for how a checkpoint is asked, which this file settles for the headless session.
