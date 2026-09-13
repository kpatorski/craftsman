# craftsman

A HUMAN <-> AI loop for coding, requirements analysis and domain design — never one large generated drop. craftsman
executes **directives** (what must be true about the code right now) and **protocols** (what order to work in, and where
to stop) that a workshop author wrote, stopping at every checkpoint to confirm direction. Formerly three separate
skills — `developer`, `analyst`, `digester` — unified under one tool with a shared, extensible content format.

## The model

Two kinds, nesting on any depth:

| Kind        | Answers                                    | Enabling it means            |
|-------------|--------------------------------------------|------------------------------|
| `directive` | What must be true about the code right now | It applies, or it does not   |
| `protocol`  | What order to work in, and where to stop   | It is callable, or it is not |

The three-question test that decides which one a new entry is, the full field reference for both kinds, and the golden
rule against adding fields no one needs yet — all in [`plugins/craftsman/core.md`](plugins/craftsman/core.md). Read that
before authoring anything.

## Two repos, on purpose

- **This repo** (`craftsman`) is the code: the plugin, its 12 command skills, the execution and management mechanics.
  Install it once, update it like any other plugin.
- **Content** — directives and protocols — lives separately, at `~/.claude/craftsman/` on disk, installed via
  `/craftsman:install` from one or more workshop sources (git repositories of `directives/` + `protocols/`, each with
  its own `index.md`). A plugin update never touches your content; a content update never touches the plugin. See [
  `plugins/craftsman/EXECUTION.md`](plugins/craftsman/EXECUTION.md), "Where the content lives".

A reference workshop — this author's own `directives/` + `protocols/` — lives at `craftsman-workshop` (a sibling 
repo). It is a starting point, not a default everyone must adopt: install it, fork it, or write your own from 
scratch against `core.md`.

## Commands

| Command                                              | Does                                                                            |
|------------------------------------------------------|---------------------------------------------------------------------------------|
| `/craftsman:analyse <input>`                         | Raw requirements → Given/When/Then business rules. No domain modelling.         |
| `/craftsman:domain-design <input>`                   | Event storming (or whatever the workshop's own method is) → written task specs. |
| `/craftsman:implement <task or spec>`                | Drives one task test-first, checkpoint by checkpoint.                           |
| `/craftsman:search <topic>`                          | "Do we already have something about X?" — across both indexes.                  |
| `/craftsman:list [directives\|protocols]`            | What's installed, enabled and disabled.                                         |
| `/craftsman:enable <id>` / `/craftsman:disable <id>` | Toggle a directive or protocol.                                                 |
| `/craftsman:install <path or URL>`                   | Add a directive, protocol, or a whole workshop source.                          |
| `/craftsman:uninstall <id>`                          | Remove one.                                                                     |
| `/craftsman:rename <old-id> <new-id>`                | Rename, updating every reference.                                               |
| `/craftsman:merge`                                   | Find single-use entries and offer to fold them into their one parent.           |
| `/craftsman:help`                                    | This table, from inside a session.                                              |

Each entry-point command also triggers from plain conversation ("add a use case", "analyze these requirements", "digest
these requirements") — see each skill's own `description` for its exact trigger phrases.

## Installing

```
/plugin marketplace add <this-repo-url-or-path>
/plugin install craftsman
```

Then, on first use of any entry-point command, craftsman notices `~/.claude/craftsman/` doesn't exist yet and offers to
install a starter workshop. Or run `/craftsman:install <workshop-source-url>` yourself, any time.

## For workshop authors

Write directives and protocols against [`core.md`](plugins/craftsman/core.md)'s format — the three-question test, the
field reference, and the golden rule against inventing fields. Every directive lives at `directives/<id>/directive.md`,
every protocol at `protocols/<id>/protocol.md`, flat, with an `index.md` at the top of each collection categorising
what's there. See `craftsman-workshop`'s own `directives/index.md` and `protocols/index.md` for a worked example at real
scale (103 entries).

`/craftsman:install` validates syntax and checks for duplicates before accepting anything into `~/.claude/craftsman/` —
see [`MANAGEMENT.md`](plugins/craftsman/MANAGEMENT.md) for exactly what it checks.

## Mechanics, for anyone extending craftsman itself

- [`EXECUTION.md`](plugins/craftsman/EXECUTION.md) — how a protocol actually runs: dispatch, directive loading, the 
  per-task session file, resuming, the checkpoint protocol.
- [`MANAGEMENT.md`](plugins/craftsman/MANAGEMENT.md) — how content gets installed, validated, renamed, merged, and versioned.
