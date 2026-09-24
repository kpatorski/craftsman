"""Shared markdown -> HTML for craftsman's generated pages (`render_dashboard.py`, `render_report.py`): just enough
markdown for directive/protocol/bundle files and the analysis artifacts (headings, tables, lists, fenced and
indented code, blockquotes, inline code/bold/italic/links, frontmatter shown as a muted block). Not a general
markdown engine, deliberately -- stdlib only, like the other scripts. `MD_CSS` styles what it emits (scope it with
a `.md` class on the container); it expects the pages' shared CSS variables (--panel, --border, --blue, ...)."""
import html
import re

from _frontmatter import split_frontmatter

def render_inline(text, resolve):
    """Inline markdown: code spans, links, bold, italic. `resolve(url)` returns the id of another document shown on
    the same page (or None): such a link becomes a `data-goto` link that switches to that document; any other
    relative link is shown as plain text (a `file://` hop out of the page is exactly what these pages avoid)."""
    spans = []

    def stash(m):
        spans.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)

    def link(m):
        label, url = m.group(1), html.unescape(m.group(2))
        if re.match(r"https?://", url):
            return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{label}</a>'
        target = resolve(url)
        if target:
            return f'<a href="#" data-goto="{html.escape(target)}">{label}</a>'
        return f'<span class="ref">{label}</span>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)


LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def render_list(items, resolve):
    """`items` is [(indent, ordered, text)]; nesting follows indentation."""
    out, stack = [], []  # stack of (indent, tag)
    for indent, ordered, text in items:
        tag = "ol" if ordered else "ul"
        while stack and indent < stack[-1][0]:
            out.append(f"</li></{stack.pop()[1]}>")
        if stack and indent > stack[-1][0]:
            out.append(f"<{tag}>")
            stack.append((indent, tag))
        elif not stack:
            out.append(f"<{tag}>")
            stack.append((indent, tag))
        else:
            out.append("</li>")
        out.append(f"<li>{render_inline(text, resolve)}")
    while stack:
        out.append(f"</li></{stack.pop()[1]}>")
    return "".join(out)


def split_cells(line):
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") else inner
    return [c.strip().replace("\x00", "|") for c in inner.replace("\\|", "\x00").split("|")]


def is_block_start(line):
    st = line.strip()
    return (st.startswith("```") or st.startswith("#") or st.startswith(">") or st.startswith("|")
            or LIST_RE.match(line) is not None or st == "---")


def render_markdown(text, resolve):
    """Markdown -> HTML for the subset craftsman files use; see render_inline for `resolve`."""
    fm_text, body = split_frontmatter(text)
    parts = []
    if fm_text is not None:
        parts.append(f'<pre class="fm">{html.escape(fm_text.strip())}</pre>')
    lines = body.split("\n")
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        st = line.strip()
        if not st:
            i += 1
        elif st.startswith("```"):
            code = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            parts.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
        elif re.match(r"#{1,6}\s", st):
            level = len(st) - len(st.lstrip("#"))
            parts.append(f"<h{level}>{render_inline(st[level:].strip(), resolve)}</h{level}>")
            i += 1
        elif st == "---":
            parts.append("<hr>")
            i += 1
        elif st.startswith("|") and i + 1 < n and re.fullmatch(r"[\s|:\-]+", lines[i + 1].strip()):
            head = split_cells(lines[i])
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_cells(lines[i]))
                i += 1
            th = "".join(f"<th>{render_inline(c, resolve)}</th>" for c in head)
            tr = "".join("<tr>" + "".join(f"<td>{render_inline(c, resolve)}</td>" for c in r) + "</tr>"
                         for r in rows)
            parts.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>")
        elif st.startswith(">"):
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            parts.append(f"<blockquote>{render_inline(' '.join(quote), resolve)}</blockquote>")
        elif LIST_RE.match(line):
            items = []
            while i < n:
                m = LIST_RE.match(lines[i])
                if m:
                    items.append([len(m.group(1)), m.group(2)[0].isdigit(), m.group(3).strip()])
                    i += 1
                elif lines[i].strip() and lines[i].startswith("  ") and items:
                    items[-1][2] += " " + lines[i].strip()  # wrapped continuation of the previous item
                    i += 1
                elif not lines[i].strip() and i + 1 < n and (LIST_RE.match(lines[i + 1])
                                                            or lines[i + 1].startswith("  ")):
                    i += 1
                else:
                    break
            parts.append(render_list([tuple(x) for x in items], resolve))
        elif line.startswith("    "):
            code = []
            while i < n and (lines[i].startswith("    ") or not lines[i].strip()):
                code.append(lines[i][4:])
                i += 1
            parts.append(f"<pre><code>{html.escape(chr(10).join(code).rstrip())}</code></pre>")
        else:
            para = [st]
            i += 1
            while i < n and lines[i].strip() and not is_block_start(lines[i]) and not lines[i].startswith("    "):
                para.append(lines[i].strip())
                i += 1
            parts.append(f"<p>{render_inline(' '.join(para), resolve)}</p>")
    return "\n".join(parts)


MD_CSS = '''
  .md { font-size: .86rem; line-height: 1.6; }
  .md h1, .md h2, .md h3, .md h4 { color: var(--heading); border: 0; margin: 1.3rem 0 .5rem; }
  .md h1 { font-size: 1.25rem; } .md h2 { font-size: 1.05rem; color: var(--blue); } .md h3, .md h4 { font-size: .95rem; }
  .md p { margin: .5rem 0; }
  .md code { background: #1a1a1a; border-radius: 3px; padding: .05rem .3rem; color: var(--green);
    font-family: "SF Mono", Menlo, Consolas, monospace; font-size: .8rem; }
  .md pre { background: #1a1a1a; border: 1px solid var(--border); border-radius: 6px; padding: .7rem .9rem; overflow-x: auto; }
  .md pre code { background: none; padding: 0; color: var(--text); }
  .md pre.fm { color: var(--muted); }
  .md table { border-collapse: collapse; margin: .7rem 0; display: block; overflow-x: auto; }
  .md th, .md td { border: 1px solid var(--border); padding: .3rem .6rem; text-align: left; vertical-align: top; }
  .md th { background: #2a2d2e; color: var(--heading); }
  .md blockquote { border-left: 3px solid var(--blue); margin: .6rem 0; padding: .1rem .9rem; color: var(--muted); }
  .md ul, .md ol { padding-left: 1.4rem; margin: .4rem 0; } .md li { margin: .2rem 0; }
  .md a { color: var(--blue); } .md .ref { color: var(--muted); }
'''
