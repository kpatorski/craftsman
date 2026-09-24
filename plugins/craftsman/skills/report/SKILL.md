---
name: report
description: >
  Renders a project's craftsman results -- business rules, open questions, the event model, specs and the session
  file(s) -- as one self-contained, dark-theme HTML page with navigation and search, in the dashboard's style. The
  markdown files stay the source of truth; this is a reading view over them. Trigger: "/craftsman:report",
  "show me the report", "render the analysis as html", "browse the results".
argument-hint: "[project dir]"
allowed-tools: [Read, Bash, Edit]
---

# report

Runs `scripts/render_report.py` — see `EXECUTION.md`, "Report" for what it looks for and why it is generic. This
skill does not load `MANAGEMENT.md`: it does not touch `~/.claude/craftsman/`, only reads the project.

## Run this

1. Resolve the project directory: `$ARGUMENTS` if given, otherwise the current directory.
2. Check whether `.claude/reports/` is covered by the project's `.gitignore`. If not, say so and offer to add the
   line — the same courtesy as for `.claude/sessions/`. Never add it without asking.
3. Run `scripts/render_report.py <project-dir>`. It writes `<project-dir>/.claude/reports/report.html`
   (override with `--output` only if the developer names a path). Exit code 2 means the project has none of the
   files it looks for — say so, name what it looks for, and stop; do not invent content.
4. Print the `file://` link it outputs plainly in the chat, the same handoff as `render_diff.py` and the
   dashboard. `--open` is an optional convenience on top of the link, never a substitute.

## Notes

- The page is a snapshot of what is on disk right now. Analysis files are written incrementally during a run, so
  this works mid-run too — re-run it to refresh.
- Also regenerated automatically every time a step writes an artifact file, with `--doc <file>`, printing the full
  `md:` path and the `html:` link to that document (`EXECUTION.md`, "Report").
- Nothing here parses the structure of the files: their formats belong to the installed workshop.
