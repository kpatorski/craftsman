"""Shared, dependency-free frontmatter parser for craftsman's content-management scripts — used by
`validate_content.py`, `merge_candidates.py`, and anything else that needs a real parse of a directive/protocol/
bundle's frontmatter rather than a hand-rolled regex per script.

A minimal parser for the narrow YAML subset craftsman frontmatter actually uses: plain scalars, booleans,
`key: >` / `key: |` blocks, `key: [a, b, c]` flow sequences (possibly wrapped across several lines), and one
level of nested map (`checkpoint:` / `overrides:`). Not a general YAML parser, deliberately -- this plugin's other
scripts are stdlib-only, and PyYAML is not guaranteed to be installed on every machine that clones a workshop
source. Cross-checked field-for-field against `yaml.safe_load` on all 112 real files in `craftsman-workshop`
before this replaced it; the only remaining divergence is a cosmetic trailing newline on the last block-scalar
field, which none of these scripts' checks depend on.

**Do not re-implement a single-line-only regex for `composes`/`steps`/`uses` in a new script.** That was tried
once, in an early version of `merge_candidates.py`, and it silently missed every reference in a multi-line flow
list (`production-code`'s own `composes:` line-wraps across 3 lines) -- exactly the same class of bug this whole
family of scripts exists to prevent. Parse the whole frontmatter with `parse_frontmatter` and read the field from
the result instead.
"""
import re

KV_RE = re.compile(r"^(\s*)([\w-]+):\s*(.*)$")


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def _coerce_scalar(s):
    s = s.strip()
    if s == "true":
        return True
    if s == "false":
        return False
    return _unquote(s)


def _parse_flow_list(first_value, lines, i):
    """`first_value` starts with '[' -- consume continuation lines until the matching ']'."""
    buf = first_value
    while "]" not in buf and i < len(lines):
        buf += " " + lines[i].strip()
        i += 1
    inner = buf[buf.index("[") + 1 : buf.rindex("]")]
    items = [x.strip() for x in inner.split(",") if x.strip()]
    return items, i


def parse_frontmatter(fm_text):
    lines = fm_text.split("\n")
    result = {}
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.strip() == "":
            i += 1
            continue
        m = KV_RE.match(line)
        if not m:
            raise ValueError(f"line {i + 1} is not a `key: value` line and not blank: {line!r}")
        indent, key, value = m.groups()
        if indent != "":
            raise ValueError(f"line {i + 1} has unexpected top-level indent: {line!r}")
        i += 1
        if value in (">", "|"):
            block = []
            while i < n and (lines[i].strip() == "" or lines[i].startswith("  ")):
                if lines[i].strip() != "":
                    block.append(lines[i].strip())
                i += 1
            result[key] = " ".join(block) if value == ">" else "\n".join(block)
        elif value.startswith("["):
            items, i = _parse_flow_list(value, lines, i)
            result[key] = items
        elif value == "":
            nested = {}
            while i < n and lines[i].startswith("  ") and KV_RE.match(lines[i]):
                nm = KV_RE.match(lines[i])
                _nindent, nkey, nvalue = nm.groups()
                i += 1
                if nvalue in (">", "|"):
                    block = []
                    while i < n and (lines[i].strip() == "" or lines[i].startswith("    ")):
                        if lines[i].strip() != "":
                            block.append(lines[i].strip())
                        i += 1
                    nested[nkey] = " ".join(block) if nvalue == ">" else "\n".join(block)
                elif nvalue.startswith("["):
                    items, i = _parse_flow_list(nvalue, lines, i)
                    nested[nkey] = items
                else:
                    nested[nkey] = _coerce_scalar(nvalue)
            result[key] = nested if nested else None
        else:
            result[key] = _coerce_scalar(value)
    return result


def split_frontmatter(text):
    """A file's full text -> (frontmatter_text, body_text), or (None, text) if there's no `---`-delimited
    frontmatter at all."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    return text[3:end], text[end + 4 :]
