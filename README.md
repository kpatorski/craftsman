# craftsman

A HUMAN <-> AI loop for coding, requirements analysis and domain design — never one large generated drop. craftsman
executes **directives** (what must be true about the code right now) and **protocols** (what order to work in, and where
to stop) that a workshop author wrote, stopping at every checkpoint to confirm direction.

## Why a loop, not a drop

A large diff generated in one shot means a wrong direction only surfaces after it's already built — expensive to
unwind, and it teaches nothing about where guidance was actually needed. craftsman stops instead, at every
`checkpoint` a protocol declares, and asks before committing further: one small batch at a time, not the whole task
at once. This is not a side feature — it's the reason craftsman exists instead of a single big prompt. See
[`core.md`](plugins/craftsman/core.md), "Fields specific to `protocol`", for exactly what a `checkpoint` can do
(`ask` and wait, or just `notify` and continue; `blocking` or not).

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

## Updating

No auto-update, by design — updating a plugin without asking is exactly the kind of thing this project doesn't want
to do to you. craftsman only ever tells you it happened and lets you decide:

- **The plugin itself**: every command checks its own version against `~/.claude/craftsman/`'s own record of it (a
  local, offline comparison — no network call) and says so, once, when they differ, pointing at
  [`CHANGELOG.md`](CHANGELOG.md). To actually update, run these yourself, when you're ready:
  ```
  claude plugin marketplace update craftsman
  claude plugin update craftsman@craftsman
  ```
  The first refreshes Claude Code's cached copy of this marketplace repo; the second installs whatever newer version
  that copy now has. Takes effect in a new session — the one you ran it from keeps the version it already loaded.
  (Claude Code does have an opt-in auto-update for marketplaces — off by default for any marketplace that isn't
  Anthropic's own, including this one — see `/plugin` → Marketplaces if you want to turn it on; craftsman itself
  never turns it on for you.)
- **A workshop source** (e.g. `craftsman-workshop`): re-run `/craftsman:install <same-source-url>` any time. If
  nothing changed upstream, it says so and stops. If something did, it shows what and asks before touching anything
  — see [`MANAGEMENT.md`](plugins/craftsman/MANAGEMENT.md), "Checking a known source for updates". Nothing checks
  this for you in the background either.

  **This never touches your own work.** A directive or protocol you wrote yourself — anything not present in the
  source you're updating from — is never a candidate for deletion. If you hand-edited a file that came from that
  source and upstream hasn't changed it since, your edit is left alone; you're told it was skipped, not silently
  overwritten. A file you edited *and* upstream also changed is shown as a real conflict, with both diffs, so you
  choose — nothing is applied without your say-so. And anything you've deliberately disabled stays disabled through
  an update to its content; only a first install ever decides a fresh entry's starting Enabled/Disabled state.

## The model

Two kinds, nesting on any depth — plus a **bundle**, a grouping and distribution unit for both (not a third kind,
more below):

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
[`core.md`](plugins/craftsman/core.md), "Bundle".

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
default everyone must adopt: install it, fork it, or write your own from scratch against
[`core.md`](plugins/craftsman/core.md).

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

## For workshop authors

Write directives and protocols against [`core.md`](plugins/craftsman/core.md)'s format — the three-question test, the
field reference, and the golden rule against inventing fields. A **fundament** entry (used by more than one theme, or a
single standalone preference) lives flat at `directives/<id>/directive.md` or `protocols/<id>/protocol.md`. A new rule
that belongs to one identifiable theme a developer would want to switch on or off as a whole goes into a **bundle**
instead: `bundles/<id>/bundle.md` plus its own `directives/` and `protocols/` subfolders, mirroring the top level. See
[`core.md`](plugins/craftsman/core.md), "Bundle", and [`craftsman-workshop`'s own
`bundles/index.md`](https://github.com/kpatorski/craftsman-workshop/blob/main/bundles/index.md) for the rule worked
through on a real corpus (7 bundles, from a 62-protocol/41-directive workshop) — its own `## Examples` section walks the
fundament-vs-bundle call on concrete entries.

`/craftsman:install` validates syntax and checks for duplicates before accepting anything into `~/.claude/craftsman/` —
see [`MANAGEMENT.md`](plugins/craftsman/MANAGEMENT.md) for exactly what it checks.

## Mechanics, for anyone extending craftsman itself

- [`EXECUTION.md`](plugins/craftsman/EXECUTION.md) — how a protocol actually runs: dispatch, directive loading, the 
  per-task session file, resuming, the checkpoint protocol.
- [`MANAGEMENT.md`](plugins/craftsman/MANAGEMENT.md) — how content gets installed, validated, renamed, merged, and
  versioned.

### Releasing a change to this repo

Bump `"version"` in [`plugins/craftsman/.claude-plugin/plugin.json`](plugins/craftsman/.claude-plugin/plugin.json)
on every commit that changes plugin behaviour (not on a pure typo/doc fix), and add an entry to
[`CHANGELOG.md`](CHANGELOG.md). `claude plugin update` compares this field, not raw commits — a content change
without a version bump is invisible to it, and the only way a developer already on an older version can pick it up
is `claude plugin uninstall craftsman@craftsman` + `claude plugin install craftsman@craftsman` (which ignores the
version field and just takes whatever the marketplace currently has). Found live, the hard way, while testing this
mechanism against a real install — see `MANAGEMENT.md`, "Plugin version".

## License

[PolyForm Internal Use License 1.0.0](LICENSE.md) — free to use, including commercially, for your own internal
purposes. Redistribution (forking and republishing, mirroring, or otherwise passing this repository or a modified
version of it on to third parties) is not permitted.
