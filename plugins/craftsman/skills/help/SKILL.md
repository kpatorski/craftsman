---
name: help
description: >
  Explains what craftsman is and lists its commands. Trigger: "/craftsman:help", "what can craftsman do", "craftsman
  commands".
allowed-tools: []
---

# help

## Run this

Print the block below verbatim, translated into the developer's language if their session is not in English — do
not re-derive, re-summarize, or re-compose it. This is finished, ready-to-print text, not a set of talking points;
the only reason to touch a tool at all is a translation pass, never a file read.

```
craftsman drives coding, requirements-to-rules extraction, and domain design in a HUMAN <-> AI loop, executing
directives (what must be true about the code) and protocols (what order to work in) that a workshop author wrote —
never a large, unconfirmed drop of generated work.

Entry points:
  /craftsman:analyse <input>          raw requirements -> Given/When/Then business rules
  /craftsman:domain-design <input>    event storming -> specs and working code, one use case at a time
  /craftsman:implement <task/spec>    drive one task test-first, checkpoint by checkpoint

Management commands:
  /craftsman:search <topic>                    is there already something about this?
  /craftsman:list [directives|protocols|bundles]
  /craftsman:enable <id>                        (directive, protocol, or bundle -- ids are unique across all three)
  /craftsman:disable <id>
  /craftsman:install <path or URL>              install a directive, protocol, bundle, or a whole workshop source
  /craftsman:uninstall <id>
  /craftsman:rename <old-id> <new-id>
  /craftsman:merge                              find single-use entries worth folding into their one caller
  /craftsman:statusline-setup                   wire the command -> batch -> protocol -> directive indicator
                                                 into Claude Code's status line (one-time setup)

No installed content yet? `/craftsman:install <workshop URL>` gets a starter set in place.

What's actually installed and enabled right now lives in `~/.claude/craftsman/directives/index.md`,
`protocols/index.md`, and `bundles/index.md` -- this command explains the commands, those explain the content.
```
