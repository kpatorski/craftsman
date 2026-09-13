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
      protocol names).
    - Disabling a protocol that has a checkpoint means "do not stop me here" — no separate toggle needed.
- **`entry-point`** *(optional, `true`)* — this protocol is one of the top-level entries craftsman exposes as a command
  (`/craftsman:analyse`, `/craftsman:domain-design`, `/craftsman:implement`, and any further ones a workshop adds). Only
  composing protocols carry this flag.
- **`match`** *(optional)* — present on a protocol that is one of several alternatives under a dispatching parent (an
  entry-point, or a composing protocol that picks one path rather than running all of `steps`). Free text describing
  the situation this alternative fits; the dispatcher reads every sibling's `match` and picks the best fit, or asks
  the developer when none fits cleanly.
- **`overrides`** *(optional)* — a map of `step-id: how this protocol changes it`, for a step this protocol's own
  `steps` list reuses from elsewhere. Applied before that shared step runs, for this call only — skip it, force its
  outcome, or relax one of its rules. A step never declares which parents override it; that lives only on the
  overriding protocol, so there is one place to look, not two that can drift apart.

A leaf protocol does not declare who calls it. "Used by X, Y" is derived by scanning every composing protocol's
`steps` for this id — worth noting in a leaf's own `## Protocol` prose for a human reader, but never a formal field,
so there is nothing to keep in sync by hand.

## Golden rule

Do not add a new field to this file unless several directives or protocols would otherwise duplicate it. A field used by
exactly one entry belongs in that entry's own frontmatter, not here.
