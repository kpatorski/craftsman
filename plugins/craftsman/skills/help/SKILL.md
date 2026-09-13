---
name: help
description: >
  Explains what craftsman is and lists its commands. Trigger: "/craftsman:help", "what can craftsman do", "craftsman commands".
allowed-tools: [Read]
---

# help

## Run this

Present, in the developer's language:

1. One paragraph: craftsman drives coding, requirements-to-rules extraction, and domain design in a HUMAN <-> AI loop, executing directives (what must be true) and protocols (what order to work in) that a workshop author wrote — never a large unconfirmed drop.
2. The entry-point commands, each with its one-line trigger purpose:
   - `/craftsman:analyse <input>` — raw requirements to Given/When/Then business rules.
   - `/craftsman:domain-design <input>` — event storming to written task specs.
   - `/craftsman:implement <task or spec>` — drive one task test-first, checkpoint by checkpoint.
3. The management commands: `/craftsman:search <topic>`, `/craftsman:list [directives|protocols]`, `/craftsman:enable <id>`, `/craftsman:disable <id>`, `/craftsman:install <path or URL>`, `/craftsman:uninstall <id>`, `/craftsman:rename <old-id> <new-id>`, `/craftsman:merge`.
4. If `~/.claude/craftsman/` does not exist yet, mention `install` is the way to get a starter workshop in place.
5. Point to `~/.claude/craftsman/directives/index.md` and `protocols/index.md` for what is actually installed right now — this file explains commands, those explain content.
