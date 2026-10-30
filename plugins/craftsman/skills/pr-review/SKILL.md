---
name: pr-review
description: >
  Reviews a pull request, or what one branch adds on top of another, in a HUMAN <-> AI loop: what the PR is for, the
  structure of the change, the business rules in its tests, then the code use case by use case — every finding a
  proposed PR comment the developer edits, picks and sends from the review page the dashboard server serves. The
  page is the console: the review's Claude session runs on the dashboard server, so the developer never switches
  between the page and the CLI. Several reviews can run at once. Not for writing code (that is `implement`). Trigger:
  "/craftsman:pr-review", "review this PR", "review pull request", "review main:feature-x", "resume the review".
argument-hint: "<GitHub pull request URL | target:source>"
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, Agent, Skill]
---

# pr-review

Two places run this skill, and `$ARGUMENTS` tells them apart.

## Started by the developer (no `--headless`)

The review does not run in this session. It runs in a session the dashboard server starts for it, so that the review
page can talk to it — see `REVIEW.md`.

1. The repository is the top level of the current directory's git checkout: `git rev-parse --show-toplevel`. Not a git
   checkout → stop and say the review runs from inside the repository it reviews.
2. Run `scripts/dashboard_server.py review --project <repository> --source <$ARGUMENTS>`. It starts the dashboard
   if needed, then starts the review — or resumes it, when that pull request or those branches are already under
   review — and prints the review's URL.
3. Print the URL on its own line, and say that everything else happens on that page: the questions, the findings, the
   console. Nothing more happens in this session.

## Started by the dashboard server (`--headless <source>`)

This session is the review. Nobody reads its terminal: the developer sees it on the review page.

1. **Load [EXECUTION.md](../../EXECUTION.md)** and **[REVIEW.md](../../REVIEW.md)**.
2. **Resolve the `pr-review` entry-point protocol and execute it** per EXECUTION.md's dispatch rules, with the source
   after `--headless` as its input.
3. Every change to the review's state goes through `scripts/review_state.py`, never by editing `review.json`.
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

- One review per pull request or pair of branches, in `.claude/reviews/<review-id>/` of the repository. Starting the
  same one again resumes it.
- `claude --resume <session id>` opens the review's conversation in the CLI; the page's "Continue in CLI" stops the
  server's session first, so two processes never write to one session.
- Nothing here duplicates EXECUTION.md. If this file and EXECUTION.md ever seem to disagree on mechanics, EXECUTION.md
  wins — except for how a checkpoint is asked, which this file settles for the headless session.
