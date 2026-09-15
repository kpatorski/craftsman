# craftsman — core vocabulary

The single source of truth for every field shared across directives and protocols. A directive or protocol that uses
only fields defined here does not redefine them — its `## Schema` section links back to this file instead of repeating
the definition. Redefine a field locally only when a specific directive or protocol extends it with something this file
does not cover.

## The two kinds

Everything in `directives/` and `protocols/` is one of exactly two kinds. Both nest on any depth — a directive can
compose other directives, a protocol can call other protocols, all the way down.

| Kind        | Answers                                    | Enabling it means            |
|-------------|--------------------------------------------|------------------------------|
| `directive` | What must be true about the code right now | It applies, or it does not   |
| `protocol`  | What order to work in, and where to stop   | It is callable, or it is not |

### The three-question test

Use this when deciding which kind a new entry is, or when a proposed entry feels like it could be either:

1. Can you ask "is this true right now?" and get a yes/no — or only "is this done yet?" Yes/no about the present →
   `directive`. Only "done yet" → `protocol`.
2. Does it have a `checkpoint`, a start and an end? → `protocol`.
3. Removing it — does it change **how the code looks**, or **what happens next**? How it looks → `directive`. What
   happens next → `protocol`.

A directive and a protocol can describe the same concern from two angles without conflicting — e.g. a protocol step that
decides how high to test something, and a directive stating the criteria that decision must satisfy. That split is
normal, not a sign the model is wrong.

## Fields common to both kinds

- **`id`** — unique, kebab-case, stable. Referenced from other files as a relative markdown link
  (`[id](../id/directive.md)`), never as bare text in the frontmatter — frontmatter fields (`composes`, `steps`) hold
  plain id lists only for lookup; the actual references live in the body's numbered lists.
- **`title`** — one short sentence or a few words.
- **`description`** — what this is for and when it matters. Prose, not a restatement of the id.

## Fields specific to `directive`

- **`applies-when`** — the situation this directive is relevant in. Free text; a protocol step consults it to decide
  which enabled directives to load before running.
- **`precedence`** — who wins when this directive and something else (usually an existing project convention) disagree.
  Default posture across the system: **the project's existing convention wins**, unless the directive says otherwise.
- **`enabled-by-default`** — `true` or `false`. Stack-specific preferences (naming a concrete framework or library)
  default to `false`; everything else defaults to `true`. See `choose-stack` for how a protocol weighs enabled
  directives against task requirements — enabled directives break ties, they do not pre-decide the stack.
- **`composes`** *(optional)* — this directive is satisfied only when every directive it lists is satisfied. The list
  lives in the frontmatter for lookup; the actual links live in the body.

## Fields specific to `protocol`

- **`input`** — what this protocol needs before it can run. Prose or a short list.
- **`output`** — what exists once this protocol is done.
- **`steps`** *(optional)* — ordered list of protocol ids this protocol walks through. Present only on a composing
  protocol; a leaf protocol has none. Frontmatter holds ids for lookup, the body holds the numbered list of links, in
  order.
- **`repeat-until`** *(optional)* — this protocol (or its `steps`) repeats one iteration at a time until the stated
  condition holds. Replaces the old `loop` kind — a repeating protocol is still a protocol.
- **`done-when`** *(optional)* — the condition that closes a composing protocol. Only meaningful together with `steps`.
- **`checkpoint`** *(optional)* — present only on a leaf protocol that stops to talk to the developer.
    - `type: ask` — put the `prompt` to the developer and wait for an answer.
    - `type: notify` — inform the developer and continue; does not wait.
    - `blocking: true` — no further step runs, nothing is written, until this is answered.
    - `when: <condition>` *(optional)* — only stop if the condition holds; no condition means always stop.
    - `shows: [...]` *(optional)* — what to render before asking (a diff, a file list, a stub list — whatever the
      protocol names). **A diff of more than 3 lines** (the unified `+`/`-`/context lines, not counting the `---`/
      `+++`/`@@` headers) renders as a self-contained local HTML file (dark theme, no network dependency), via
      `scripts/render_diff.py` (see the `install`/management scripts, same place as `scripts/toggle_table_row.py`)
      — never pasted as raw `+`/`-` text into the conversation past that point. A wall of diff text in a chat
      window is exactly the readability failure this guards against, and it gets worse every class a `tdd-loop`
      touches, not better. Print the script's `file://` link plainly in the chat message — that is the primary,
      portable way to hand it over (clickable or copy-pasteable, works on any OS, doesn't depend on a chat UI's
      file-card rendering, which is not reliable). `--open` is an optional convenience on top of the link, never a
      substitute for printing it — it does nothing useful in a remote or headless environment. 3 lines or fewer can
      stay inline as plain text. This governs every checkpoint that shows a diff alike — `review-design-direction`,
      `refactor-tests`, `refactor-production`, `finish-loop`, `MANAGEMENT.md`'s own conflict presentation — one
      rule, not one per protocol.
    - Disabling a protocol that has a checkpoint means "do not stop me here" — no separate toggle needed.
- **`entry-point`** *(optional, `true`)* — this protocol is one of the top-level entries craftsman exposes as a command
  (`/craftsman:analyse`, `/craftsman:domain-design`, `/craftsman:implement`, and any further ones a workshop adds). Only
  composing protocols carry this flag.
- **`uses`** *(optional)* — the directive ids this protocol actively consults, beyond whatever `production-code`
  or another blanket directive already covers by its own `applies-when`. Explicit, not a blind scan of every
  enabled directive on every step — a step names what it needs.
- **`match`** *(optional)* — present on a protocol that is one of several alternatives under a dispatching parent (an
  entry-point, or a composing protocol that picks one path rather than running all of `steps`). Free text describing
  the situation this alternative fits; the dispatcher reads every sibling's `match` and picks the best fit, or asks
  the developer when none fits cleanly.
- **`overrides`** *(optional)* — a map of `entry-id: how this protocol changes it`, where the entry is a step this
  protocol's `steps` list reuses, or a directive one of those steps would otherwise load. Applied for this call
  only, before the affected step runs or the affected directive would otherwise apply — skip it, force its
  outcome, or relax one of its rules. Neither a step nor a directive declares which callers override it; that
  lives only on the overriding protocol, so there is one place to look, not two that can drift apart.

A leaf protocol does not declare who calls it, not even as prose. "Who uses this" is answered by scanning every
composing protocol's `steps` for this id, at the moment someone asks — `search` and `merge` both do exactly this.
Do not write a "Used by" line into a leaf's own file: unlike a live scan, prose written at authoring time goes
stale the first time a new composing protocol starts calling it, and nothing updates that line automatically.

## Bundle

A bundle is not a third kind — the three-question test above still only ever answers `directive` or `protocol`.
A bundle is a grouping and distribution unit: a named folder of directives and/or protocols that installs and
enables together (`enable bundle tdd` turns on everything the TDD loop needs in one move; `disable bundle tdd`
turns it back off).

Membership is positional, not a field: an entry belongs to a bundle by living under `bundles/<bundle-id>/directives/`
or `bundles/<bundle-id>/protocols/`, the same way it belongs to the top level by living directly under
`directives/` or `protocols/`. A bundle's own file never lists its members — `search`, `list`, and `merge` all
discover them by walking the bundle's two folders, exactly as the top-level indexes walk `directives/` and
`protocols/`. Nothing to keep in sync by hand — same reasoning as the removed "Used by" line.

- **`id`** — unique across bundles, same rules as any other id.
- **`title`** — one short sentence.
- **`description`** — what enabling this bundle gives you, and who wants it.
- **`requires`** *(optional)* — bundle ids this bundle depends on. Enabling this bundle enables each of these
  first; if one is not installed, the tool names it and stops — never a silent partial enable.

A directive or protocol does not know which bundle it lives in, not even as prose — same principle as "a leaf
protocol does not declare who calls it" above. Its own file says nothing about bundle membership; the folder it
lives in is the only source of truth.

The same direction-of-reference rule governs `requires` itself: a bundle declares what it needs, never who needs
it. `tdd`'s own file says `requires: [testing]`; `testing`'s file says nothing about `tdd` or any other bundle that
happens to require it, not even as prose ("used by `tdd` and `legacy-code`"). A reverse reference written at
authoring time goes stale the moment a third bundle starts requiring it — the same reasoning that removed the
"Used by" line from leaf protocols applies unchanged here. Whoever wants to know who requires a bundle scans every
other bundle's `requires` for its id, the same way `search` scans `steps` for a protocol's id.

## Golden rule

Do not add a new field to this file unless several directives or protocols would otherwise duplicate it. A field used by
exactly one entry belongs in that entry's own frontmatter, not here.
