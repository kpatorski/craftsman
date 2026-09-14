# craftsman

A HUMAN <-> AI loop for coding, requirements analysis and domain design — never one large generated drop. craftsman
executes **directives** (what must be true about the code right now) and **protocols** (what order to work in, and where
to stop) that a workshop author wrote, stopping at every checkpoint to confirm direction.

## The model

Two kinds, nesting on any depth:

| Kind        | Answers                                    | Enabling it means            |
|-------------|--------------------------------------------|------------------------------|
| `directive` | What must be true about the code right now | It applies, or it does not   |
| `protocol`  | What order to work in, and where to stop   | It is callable, or it is not |

The three-question test that decides which one a new entry is, the full field reference for both kinds, and the golden
rule against adding fields no one needs yet — all in [`plugins/craftsman/core.md`](plugins/craftsman/core.md). Read that
before authoring anything.

A **bundle** is not a third kind — the three-question test above still only ever answers `directive` or `protocol`.
It is a grouping and distribution unit: a named folder of directives and/or protocols that installs and enables
together (`/craftsman:enable event-storming` turns on everything that modelling method needs in one move). A
directive or protocol belongs to a bundle by living inside it on disk, nothing more — no field to keep in sync. See
`core.md`, "Bundle".

## Two repos, on purpose

- **This repo** (`craftsman`) is the code: the plugin, its 12 command skills, the execution and management mechanics.
  Install it once, update it like any other plugin.
- **Content** — directives, protocols, and bundles — lives separately, at `~/.claude/craftsman/` on disk, installed
  via `/craftsman:install` from one or more workshop sources (git repositories of `directives/` + `protocols/` +
  `bundles/`, each collection with its own `index.md`). A plugin update never touches your content; a content update
  never touches the plugin. See [`plugins/craftsman/EXECUTION.md`](plugins/craftsman/EXECUTION.md), "Where the
  content lives".

A reference workshop — this author's own `directives/` + `protocols/` + `bundles/` — lives at
[`kpatorski/craftsman-workshop`](https://github.com/kpatorski/craftsman-workshop). It is a starting point, not a
default everyone must adopt: install it, fork it, or write your own from scratch against `core.md`.

## Commands

| Command                                              | Does                                                                                                                                                  |
|------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| `/craftsman:analyse <input>`                         | Raw requirements → Given/When/Then business rules. No domain modelling.                                                                               |
| `/craftsman:domain-design <input>`                   | Event storming (or whatever the workshop's own method is) → written task specs.                                                                       |
| `/craftsman:implement <task or spec>`                | Drives one task test-first, checkpoint by checkpoint.                                                                                                 |
| `/craftsman:search <topic>`                          | "Do we already have something about X?" — across all three indexes.                                                                                   |
| `/craftsman:list [directives\|protocols\|bundles]`   | What's installed, enabled and disabled.                                                                                                               |
| `/craftsman:enable <id>` / `/craftsman:disable <id>` | Toggle a directive, protocol, or bundle — ids are unique across all three, so the kind resolves by lookup. Toggling a bundle cascades to its members. |
| `/craftsman:install <path or URL>`                   | Add a directive, protocol, bundle, or a whole workshop source.                                                                                        |
| `/craftsman:uninstall <id>`                          | Remove one.                                                                                                                                           |
| `/craftsman:rename <old-id> <new-id>`                | Rename, updating every reference.                                                                                                                     |
| `/craftsman:merge`                                   | Find single-use entries and offer to fold them into their one parent.                                                                                 |
| `/craftsman:help`                                    | This table, from inside a session.                                                                                                                    |

Each entry-point command also triggers from plain conversation ("add a use case", "analyze these requirements", "digest
these requirements") — see each skill's own `description` for its exact trigger phrases.

## Installing

```
/plugin marketplace add kpatorski/craftsman
/plugin install craftsman@craftsman
```

The `@craftsman` names the marketplace explicitly (`<plugin>@<marketplace>`) — this is the form confirmed to work.

(`<this-repo-url-or-path>` works too in place of `kpatorski/craftsman` — a local clone path, or any other git URL,
if you're not installing from GitHub directly.)

Then, on first use of any entry-point command, craftsman notices `~/.claude/craftsman/` doesn't exist yet and offers to
install a starter workshop. Or run `/craftsman:install <workshop-source-url>` yourself, any time.

## For workshop authors

Write directives and protocols against [`core.md`](plugins/craftsman/core.md)'s format — the three-question test, the
field reference, and the golden rule against inventing fields. A **fundament** entry (used by more than one theme,
or a single standalone preference) lives flat at `directives/<id>/directive.md` or `protocols/<id>/protocol.md`. A
new rule that belongs to one identifiable theme a developer would want to switch on or off as a whole goes into a
**bundle** instead: `bundles/<id>/bundle.md` plus its own `directives/` and `protocols/` subfolders, mirroring the
top level. See `core.md`, "Bundle", and
[`craftsman-workshop`'s own `bundles/index.md`](https://github.com/kpatorski/craftsman-workshop/blob/main/bundles/index.md)
for the rule worked through on a real corpus (7 bundles, from a 62-protocol/41-directive workshop) — its own
`## Examples` section walks the fundament-vs-bundle call on concrete entries.

`/craftsman:install` validates syntax and checks for duplicates before accepting anything into `~/.claude/craftsman/` —
see [`MANAGEMENT.md`](plugins/craftsman/MANAGEMENT.md) for exactly what it checks.

## Mechanics, for anyone extending craftsman itself

- [`EXECUTION.md`](plugins/craftsman/EXECUTION.md) — how a protocol actually runs: dispatch, directive loading, the 
  per-task session file, resuming, the checkpoint protocol.
- [`MANAGEMENT.md`](plugins/craftsman/MANAGEMENT.md) — how content gets installed, validated, renamed, merged, and versioned.

## License

[PolyForm Internal Use License 1.0.0](LICENSE.md) — free to use, including commercially, for your own internal
purposes. Redistribution (forking and republishing, mirroring, or otherwise passing this repository or a modified
version of it on to third parties) is not permitted.
