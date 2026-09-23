---
name: dashboard
description: >
  Opens a local, self-contained, dark-theme HTML dashboard of everything installed under ~/.claude/craftsman/ --
  help, and every bundle/protocol/directive with its description and enabled/disabled state, filterable by a
  search box. Read-only: each row shows the exact enable/disable command to copy, it never toggles anything
  itself. Trigger: "/craftsman:dashboard", "show me the dashboard", "browse the bundles", "what's installed,
  visually".
allowed-tools: [Read, Bash]
---

# dashboard

Renders `scripts/render_dashboard.py`'s output and hands it over — see `MANAGEMENT.md`, "Dashboard" for what the
script does and why toggling from the page only ever copies a command instead of writing anything. This skill
does not load `MANAGEMENT.md` in full — it doesn't mutate `~/.claude/craftsman/`, only reads it, the same posture
as `statusline-setup`.

## Run this

1. Resolve the content root per `EXECUTION.md`, "Where the content lives" (`~/.claude/craftsman/`). If it doesn't
   exist yet, say so and offer to install the default starter workshop — the same first-run handling as any other
   entry point.
2. Run `scripts/render_dashboard.py <content-root> --output <output-path>`. Default `<output-path>` is
   `~/.claude/craftsman-dashboard.html` — a stable location sitting next to (not inside) the content tree's own
   git repo, so re-running this skill always refreshes the same file instead of littering a new one per run. Ask
   before writing somewhere else if the developer names a different path.
3. Print the `file://` link the script outputs plainly in the chat — the primary, portable way to hand it over,
   same convention as `render_diff.py` (`core.md`, `shows`). `--open` is an optional convenience on top of it,
   never a substitute for printing the link.

## Notes

- The page is a snapshot of what's on disk at generation time, not a live view. It cannot regenerate itself —
  re-run this skill after installing, enabling, or disabling anything; a browser refresh alone replays the same
  file.
- Every id/title/description on the page comes from that entry's own file, never from the index row — the index
  is a lookup table, the file is the single source of truth, same rule this content tree applies everywhere else.
- The search box is plain client-side JS filtering an already-rendered list — no network call, no re-invocation
  of this skill, works offline.
