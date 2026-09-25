---
name: dashboard
description: >
  Starts the live craftsman dashboard -- a local web page, meant to stay open on a second screen, that shows the
  current project's session stacks, artifacts and specs as they change, plus everything installed under
  ~/.claude/craftsman/ with working enable/disable switches and the command list. Refreshes by itself. Trigger:
  "/craftsman:dashboard", "dashboard on", "dashboard off", "open the dashboard", "stop the dashboard", "remove this
  project from the dashboard".
argument-hint: "[on|off|status|remove [<project dir>]]"
allowed-tools: [Bash]
---

# dashboard

Runs `scripts/dashboard_server.py` — see `MANAGEMENT.md`, "Dashboard" for what the server does, what it may write,
and why install/update stay commands for Claude CLI. This skill does not load `MANAGEMENT.md` in full.

## Run this

1. `$ARGUMENTS` is `off` (or `stop`) → run `scripts/dashboard_server.py off` and relay its line. `status` → run
   `scripts/dashboard_server.py status` and relay it. `remove [<dir>]` → run `scripts/dashboard_server.py remove
   --project <dir, or the target project from step 2>` and relay its line. Empty or `on` (or `start`) → continue.
2. Resolve the target project: the git top level of the current directory (`git rev-parse --show-toplevel`), or
   the current directory when it is not a git repository.
3. Run `scripts/dashboard_server.py on --project <target project>`. It starts the server in the background, or —
   when one is already running — adds this project to it; either way it prints the URL.
4. Print the URL exactly as the script printed it, on its own line. Nothing else is needed: the page follows every
   later change on its own, so this skill never has to be run again for the same project.

## Notes

- If `~/.claude/craftsman/` does not exist, the page still starts and shows the project; the Library view is empty.
  Offer `/craftsman:install <workshop URL>` as with any first run.
- The server is detached from this Claude session: closing the session does not stop it. It stops on `off`, or by
  itself after 8 hours with no page open.
- `remove` only makes the dashboard forget a project — nothing in the project is touched. The page has the same
  action: the × next to the project's name.
- While it runs for a project, the per-write report (`EXECUTION.md`, "Report") prints only the `md:` path of each
  file written — the page already shows it.
- On WSL 2 the URL opens as is in a Windows browser — `localhost` is forwarded to WSL.
