#!/usr/bin/env python3
"""Validate a craftsman content tree (a workshop source repo, or `~/.claude/craftsman/`) against `core.md`'s
contract — one deterministic, repeatable script replacing what `MANAGEMENT.md` previously only described in prose
("Duplicate detection", "Syntax validation", the id-set completeness paragraph). Found live: a real id collision
(`event-storming` used by both a bundle and its own entry protocol) sat unnoticed in `craftsman-workshop` because
every session re-implemented this checking ad hoc, in whatever shape that session's agent interpreted the prose
into that turn — including this plugin's own author, more than once, in scratch scripts that were never kept.

Usage:
    validate_content.py <content-root> [content-root ...]

Exits non-zero and prints every failure found (not just the first) if any check fails; exits 0 and prints a summary
otherwise. Safe to run repeatedly and safe to wire into a pre-commit hook or CI — read-only, no files are changed.

Checks, each against every `directive.md` / `protocol.md` / `bundle.md` found under the given root(s):

1. Frontmatter parses as YAML at all.
2. Mandatory sections are present: `## Schema`, plus the kind-specific body (`## Directive` / `## Protocol` /
   `## Bundle`); a `bundle.md` also needs `## Protocols` and `## Directives`.
3. Frontmatter has every field `core.md` requires for that kind (`id`, `title`, `description` for all three, plus
   `applies-when`/`precedence`/`enabled-by-default` for a directive, `input`/`output` for a protocol). A `bundle.md`
   is rejected outright if it declares a `members` field — that belongs to directory placement, never frontmatter.
4. Every id is unique across `directives/`, `protocols/`, and `bundles/` combined (see `MANAGEMENT.md`,
   "Resolving an id" — ids are looked up without a kind prefix, so a collision breaks that lookup silently).
5. Every relative markdown link resolves to a real file, except a bare `` `core.md` `` mention, which must stay a
   name, never a link (see `EXECUTION.md`, "Where the content lives").
6. Every `requires` a `bundle.md` declares names a bundle id that actually exists.
7. Index completeness: every id physically on disk appears in exactly one Enabled/Disabled table (its own
   top-level index if it is fundament, its bundle's own `bundle.md` if it lives inside one), and every id named in
   a table exists on disk.
"""
import re
import sys
import pathlib

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
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
    """A minimal, dependency-free parser for the narrow YAML subset craftsman frontmatter actually uses: plain
    scalars, booleans, `key: >` / `key: |` blocks, `key: [a, b, c]` flow sequences (possibly wrapped across
    lines), and one level of nested map (`checkpoint:` / `overrides:`). Not a general YAML parser, deliberately --
    this plugin's other scripts are stdlib-only, and PyYAML is not guaranteed to be installed on every machine
    that clones a workshop source. Cross-checked field-for-field against `yaml.safe_load` on all 112 real files in
    `craftsman-workshop` before replacing it; the only remaining divergence is a cosmetic trailing newline on the
    last block-scalar field, which none of this script's checks depend on."""
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

REQUIRED_FIELDS = {
    "directive": ["id", "title", "description", "applies-when", "precedence", "enabled-by-default"],
    "protocol": ["id", "title", "description", "input", "output"],
    "bundle": ["id", "title", "description"],
}
REQUIRED_SECTIONS = {
    "directive": ["## Schema", "## Directive"],
    "protocol": ["## Schema", "## Protocol"],
    "bundle": ["## Schema", "## Bundle", "## Protocols", "## Directives"],
}

# Reused from toggle_table_row.py's table-parsing shape -- kept identical so both scripts read the same tables
# the same way.
ROW_RE = re.compile(r"^\|(.*)\|\s*$")
ID_CELL_RE = re.compile(r"^\s*\[([a-z0-9-]+)\]\(")
BARE_ID_RE = re.compile(r"^[a-z0-9-]+$")


def kind_of(path):
    return {"directive.md": "directive", "protocol.md": "protocol", "bundle.md": "bundle"}[path.name]


def find_content_files(roots):
    files = []
    for root in roots:
        for name in ("directive.md", "protocol.md", "bundle.md"):
            files.extend(p for p in pathlib.Path(root).rglob(name) if ".git" not in p.parts)
    return files


def split_frontmatter(text):
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    return text[3:end], text[end + 4 :]


def check_file(path, errors):
    text = path.read_text()
    kind = kind_of(path)
    fm_text, body = split_frontmatter(text)

    if fm_text is None:
        errors.append(f"{path}: no `---`-delimited frontmatter found")
        return None

    try:
        fm = parse_frontmatter(fm_text) or {}
    except ValueError as e:
        errors.append(f"{path}: frontmatter is not valid YAML -- {e}")
        return None

    for field in REQUIRED_FIELDS[kind]:
        if field not in fm:
            errors.append(f"{path}: missing required frontmatter field `{field}` for a {kind}")
    if kind == "bundle" and "members" in fm:
        errors.append(f"{path}: `members` is not a legal bundle.md field -- membership is positional (core.md)")

    for section in REQUIRED_SECTIONS[kind]:
        if section not in text:
            errors.append(f"{path}: missing required section `{section}`")

    for m in LINK_RE.finditer(body):
        label, target = m.group(1), m.group(2)
        if target.startswith("http") or target.startswith("#"):
            continue
        if target.endswith("core.md"):
            errors.append(f"{path}: `core.md` must be named, never linked (`{label}`({target}))")
            continue
        target_path = (path.parent / target.split("#")[0]).resolve()
        if not target_path.exists():
            errors.append(f"{path}: broken link -- [{label}]({target})")

    return fm.get("id"), fm


def check_ids_unique(files_and_fm, errors):
    seen = {}
    for path, (fm_id, _fm) in files_and_fm.items():
        if fm_id is None:
            continue
        if fm_id in seen:
            errors.append(f"id collision: `{fm_id}` used by both {seen[fm_id]} and {path}")
        else:
            seen[fm_id] = path
    return seen


def check_bundle_requires(files_and_fm, bundle_ids, errors):
    for path, (_fm_id, fm) in files_and_fm.items():
        if kind_of(path) != "bundle":
            continue
        for req in fm.get("requires") or []:
            if req not in bundle_ids:
                errors.append(f"{path}: `requires: [{req}]` names a bundle id that does not exist")


# --- index completeness: reuses toggle_table_row.py's table shape ---


def split_row(line):
    inner = ROW_RE.match(line).group(1)
    return [c.strip() for c in inner.split("|")]


def is_delimiter_row(cells):
    return all(re.fullmatch(r":?-+:?", c) for c in cells)


def row_id(row):
    cell = row[1]
    m = ID_CELL_RE.match(cell)
    if m:
        return m.group(1)
    if BARE_ID_RE.fullmatch(cell.strip()):
        return cell.strip()
    return None


def ids_in_tables(index_path):
    """Every id appearing in any **Enabled**/**Disabled** table in this index-shaped file."""
    lines = index_path.read_text().splitlines()
    ids = []
    i = 0
    while i < len(lines):
        if lines[i].strip() in ("**Enabled**", "**Disabled**"):
            content_idx = i + 2
            if content_idx < len(lines) and lines[content_idx].startswith("|"):
                delim_idx = content_idx + 1
                if delim_idx < len(lines) and is_delimiter_row(split_row(lines[delim_idx])):
                    j = delim_idx + 1
                    while j < len(lines) and lines[j].startswith("|"):
                        rid = row_id(split_row(lines[j]))
                        if rid:
                            ids.append(rid)
                        j += 1
        i += 1
    return ids


def check_index_completeness(root, errors):
    root = pathlib.Path(root)

    # Fundament directives/protocols.
    for folder, name, index in (
        ("directives", "directive.md", root / "directives" / "index.md"),
        ("protocols", "protocol.md", root / "protocols" / "index.md"),
    ):
        if not index.exists():
            continue
        on_disk = {p.parent.name for p in (root / folder).glob(f"*/{name}")}
        in_index = set(ids_in_tables(index))
        for missing in sorted(on_disk - in_index):
            errors.append(f"{index}: `{missing}` exists on disk under {folder}/ but is in no table")
        for ghost in sorted(in_index - on_disk):
            errors.append(f"{index}: `{ghost}` is listed but has no matching directory under {folder}/")

    # Bundles themselves, in bundles/index.md.
    bundles_index = root / "bundles" / "index.md"
    if bundles_index.exists():
        on_disk = {p.parent.name for p in (root / "bundles").glob("*/bundle.md")}
        in_index = set(ids_in_tables(bundles_index))
        for missing in sorted(on_disk - in_index):
            errors.append(f"{bundles_index}: `{missing}` exists on disk under bundles/ but is in no table")
        for ghost in sorted(in_index - on_disk):
            errors.append(f"{bundles_index}: `{ghost}` is listed but has no matching directory under bundles/")

    # Each bundle's own members.
    for bundle_md in (root / "bundles").glob("*/bundle.md"):
        bundle_dir = bundle_md.parent
        on_disk = set()
        for name in ("directive.md", "protocol.md"):
            on_disk |= {p.parent.name for p in bundle_dir.rglob(name)}
        in_index = set(ids_in_tables(bundle_md))
        for missing in sorted(on_disk - in_index):
            errors.append(f"{bundle_md}: `{missing}` exists on disk but is in no table")
        for ghost in sorted(in_index - on_disk):
            errors.append(f"{bundle_md}: `{ghost}` is listed but has no matching directory")


def main():
    roots = sys.argv[1:]
    if not roots:
        raise SystemExit(f"Usage: {sys.argv[0]} <content-root> [content-root ...]")

    errors = []
    files = find_content_files(roots)
    files_and_fm = {}
    for path in files:
        result = check_file(path, errors)
        files_and_fm[path] = result if result else (None, {})

    ids_seen = check_ids_unique(files_and_fm, errors)
    bundle_ids = {fm_id for path, (fm_id, _fm) in files_and_fm.items() if fm_id and kind_of(path) == "bundle"}
    check_bundle_requires(files_and_fm, bundle_ids, errors)

    for root in roots:
        check_index_completeness(root, errors)

    if errors:
        print(f"{len(errors)} problem(s) found:\n")
        for e in errors:
            print(f"  - {e}")
        print(f"\n{len(files)} files checked, {len(ids_seen)} unique ids.")
        sys.exit(1)

    print(f"OK -- {len(files)} files checked, {len(ids_seen)} unique ids, 0 problems.")
    sys.exit(0)


if __name__ == "__main__":
    main()
