---
name: uninstall
description: >
  Removes a directive, protocol, or bundle by id from `~/.claude/craftsman/`. Trigger: "/craftsman:uninstall", "remove
  directive", "remove protocol", "remove bundle", "uninstall".
argument-hint: "<id>"
allowed-tools: [Read, Bash, AskUserQuestion]
---

# uninstall

## Run this

1. **Load [MANAGEMENT.md](../../MANAGEMENT.md)** — the versioning step at the end applies here.
2. Run `python3 <this plugin's own path>/scripts/uninstall_id.py ~/.claude/craftsman $ARGUMENTS` (no `--yes` yet —
   dry run). It locates the id, reports what would be removed (its directory, member count if it is a bundle, and
   which file holds its table row), and lists every other entry that references it via `composes`/`steps`/`uses`/
   `requires`. If `$ARGUMENTS` doesn't resolve to any id, it says so and stops here.
3. Show the dry-run output to the developer. If anything references the id, ask explicitly whether to proceed
   anyway (leaving a dangling reference for the referrer to fix) or stop.
4. On confirmation, re-run the same command with `--yes` appended — it removes the table row and deletes the
   directory (a bundle's entire `bundles/<id>/` tree, members included, not just the wrapper) in one step.
5. Run `python3 <this plugin's own path>/scripts/validate_content.py ~/.claude/craftsman` afterward — it catches
   any link left dangling by the removal (expected if step 3 was answered "proceed anyway"; surface it as the
   known, accepted consequence, not a new surprise).
6. Commit per MANAGEMENT.md.

## Notes

- Uninstalling an `entry-point` protocol is a bigger deal than a leaf — confirm explicitly, since it removes a
  whole command, even though the script itself treats it the same as any other protocol.
- The script's reference scan does not include a bare prose mention (a body link with no frontmatter
  `composes`/`steps`/`uses`/`requires` entry behind it) — those are caught by `validate_content.py` in step 5
  instead, as a broken link, not reported ahead of time as a referrer.
