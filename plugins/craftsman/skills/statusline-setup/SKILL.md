---
name: statusline-setup
description: >
  Wires craftsman's command -> batch -> protocol -> directive indicator into Claude Code's status line. Trigger:
  "/craftsman:statusline-setup", "show craftsman's progress in the status line", "always-visible craftsman
  indicator".
allowed-tools: [Read, Edit, Write, Bash, AskUserQuestion]
---

# statusline-setup

Wires `scripts/render_status.py` into Claude Code's native status line (`settings.json`'s `statusLine` key) — see
`MANAGEMENT.md`, "Status line" for what the script does and why this needs a one-time manual step at all (a
plugin cannot register a status line on install). This skill does not load `MANAGEMENT.md` in full — it does not
mutate `~/.claude/craftsman/`, only `settings.json`.

## Run this

1. Ask (blocking, `AskUserQuestion`-style): user-level (`~/.claude/settings.json`, applies in every project) or
   project-level (`.claude/settings.json` in the current project only)?
2. Build the command that always finds the currently-installed plugin version, the same `sort -V` idiom
   `craftsman-workshop/.githooks/pre-commit` already uses:

   ```
   python3 $(ls -d ~/.claude/plugins/cache/craftsman/craftsman/*/scripts 2>/dev/null | sort -V | tail -1)/render_status.py
   ```

3. Read the target `settings.json`. If it doesn't exist, it will be created. If it exists but has no `statusLine`
   key, proceed to step 4. **If it already has a `statusLine` key, stop and show its current value — never
   overwrite silently.** Ask whether to replace it (its previous content is lost from this file, though still
   recoverable from git history if the file is tracked) or leave it alone and stop here.
4. Show the exact JSON that will be added or changed (the whole `statusLine` object, `{"type": "command",
   "command": "<the command from step 2>"}`) as a diff against the current file content — inline if 3 lines or
   fewer of actual change, otherwise via `scripts/render_diff.py` per `core.md`'s `shows` rule.
5. On confirmation, write it. Preserve every other key already in the file untouched.
6. Tell the developer the change takes effect on next status-line refresh (new assistant message, `/compact`, or
   immediately if they restart the session) — no restart is required, but nothing appears mid-turn.

## Notes

- The status line only shows something meaningful while a craftsman session file exists and is `active` or
  `blocked` in the current project (`workspace.project_dir`, or `cwd` if that's absent from what Claude Code
  passes the script) — outside of a craftsman run it prints `craftsman: idle`, not an error.
- This skill never runs `render_status.py` itself to "preview" the result — the script reads live session state
  the skill has no reason to fabricate a stand-in for; the developer will see the real thing once it's wired in.
- Re-running this skill after a `craftsman` plugin update is not required — the `sort -V` command re-resolves the
  current version's scripts directory on every invocation, not just at setup time.
