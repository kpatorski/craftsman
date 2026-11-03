// Colours the code of a diff by its language, for the review page: keywords, strings, comments, numbers, types and
// annotations, each a `<span class="sx-…">` the page's palette colours. A diff shows lines, not whole files, so a line
// is coloured on its own, with the state of the line before it: whether it starts inside a block comment or a
// multi-line string. A language it does not know stays plain, escaped text.
(root => {
  const words = text => new Set(text.split(" "));
  const C_LIKE = { line: ["//"], blocks: [["/*", "*/", "c"]], quotes: ['"', "'"], at: true };
  const LANGUAGES = {
    java: { ...C_LIKE, blocks: [["/*", "*/", "c"], ['"""', '"""', "s"]], keywords: words("abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public record return sealed permits short static strictfp super switch synchronized this throw throws transient try var void volatile while yield true false null") },
    kotlin: { ...C_LIKE, blocks: [["/*", "*/", "c"], ['"""', '"""', "s"]], keywords: words("abstract annotation as break by catch class companion const constructor continue data do else enum external false final finally for fun get if import in infix init inline inner interface internal is lateinit null object open operator out override package private protected public reified return sealed set super suspend this throw true try typealias val var vararg when where while") },
    typescript: { ...C_LIKE, quotes: ['"', "'", "`"], keywords: words("abstract any as async await boolean break case catch class const constructor continue declare default delete do else enum export extends false finally for from function get if implements import in instanceof interface keyof let module namespace never new null number object of private protected public readonly return set static string super switch this throw true try type typeof undefined unknown var void while yield") },
    javascript: { ...C_LIKE, quotes: ['"', "'", "`"], keywords: words("async await break case catch class const continue debugger default delete do else export extends false finally for from function get if import in instanceof let new null of return set static super switch this throw true try typeof undefined var void while with yield") },
    python: { line: ["#"], blocks: [['"""', '"""', "s"], ["'''", "'''", "s"]], quotes: ['"', "'"], at: true, keywords: words("and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return self True try while with yield") },
    go: { ...C_LIKE, quotes: ['"', "'", "`"], at: false, keywords: words("break case chan const continue default defer else fallthrough for func go goto if import interface map package range return select struct switch type var nil true false bool byte error int int64 string") },
    csharp: { ...C_LIKE, keywords: words("abstract as async await base bool break case catch class const continue decimal default delegate do double else enum event explicit extern false finally fixed float for foreach get if implicit in int interface internal is lock long namespace new null object operator out override params private protected public readonly record ref return sealed set short static string struct switch this throw true try typeof uint using var virtual void volatile while") },
    sql: { line: ["--"], blocks: [["/*", "*/", "c"]], quotes: ["'"], nocase: true, notypes: true, keywords: words("add all alter and as asc begin between by case check column commit constraint create default delete desc distinct drop else end exists foreign from group having in index inner insert into is join key left like limit not null on or order outer primary references right rollback select set table then union unique update values view when where with") },
    shell: { line: ["#"], blocks: [], quotes: ['"', "'"], notypes: true, keywords: words("if then else elif fi for while do done case esac in function return local export set unset echo exit") },
    yaml: { line: ["#"], blocks: [], quotes: ['"', "'"], notypes: true, keys: /^(\s*-?\s*)([\w.\-/]+)(?=\s*:)/, keywords: words("true false null yes no on off") },
    json: { line: [], blocks: [], quotes: ['"'], notypes: true, keys: /^(\s*)("(?:[^"\\]|\\.)*")(?=\s*:)/, keywords: words("true false null") },
    xml: { markup: true },
  };
  const EXTENSIONS = { java: "java", kt: "kotlin", kts: "kotlin", ts: "typescript", tsx: "typescript", mts: "typescript",
    js: "javascript", jsx: "javascript", mjs: "javascript", cjs: "javascript", py: "python", go: "go", cs: "csharp",
    sql: "sql", sh: "shell", bash: "shell", zsh: "shell", yaml: "yaml", yml: "yaml", json: "json", xml: "xml",
    xsd: "xml", html: "xml", htm: "xml", svg: "xml", gradle: "java", groovy: "java", scala: "java" };

  const esc = s => s.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const span = (kind, s) => s ? `<span class="sx-${kind}">${esc(s)}</span>` : "";

  function language(path) {
    const name = String(path || "").split("/").pop(), dot = name.lastIndexOf(".");
    return dot > 0 ? EXTENSIONS[name.slice(dot + 1).toLowerCase()] || null : null;
  }

  // XML and HTML: tags, attribute names and values, comments; the state is an open `<!--`.
  function markup(text, state) {
    let out = "", i = 0;
    if (state) {
      const end = text.indexOf("-->");
      if (end < 0) return [span("c", text), state];
      out += span("c", text.slice(0, end + 3)); i = end + 3;
    }
    let inTag = false;
    while (i < text.length) {
      const rest = text.slice(i);
      if (!inTag && rest.startsWith("<!--")) {
        const end = rest.indexOf("-->", 4);
        if (end < 0) return [out + span("c", rest), "comment"];
        out += span("c", rest.slice(0, end + 3)); i += end + 3; continue;
      }
      const open = !inTag && rest.match(/^<\/?[\w:.\-?!]+/);
      if (open) { out += span("k", open[0]); i += open[0].length; inTag = true; continue; }
      const close = inTag && rest.match(/^\/?\??>/);
      if (close) { out += span("k", close[0]); i += close[0].length; inTag = false; continue; }
      const attr = inTag && rest.match(/^[\w:.\-]+(?=\s*=)/);
      if (attr) { out += span("t", attr[0]); i += attr[0].length; continue; }
      const value = inTag && rest.match(/^("[^"]*"?|'[^']*'?)/);
      if (value) { out += span("s", value[0]); i += value[0].length; continue; }
      out += esc(text[i]); i++;
    }
    return [out, null];
  }

  // One line: its HTML, and the state the next line starts in -- the index of the open block, or null.
  function line(lang, text, state = null) {
    const L = LANGUAGES[lang];
    if (!L) return [esc(text), null];
    if (L.markup) return markup(text, state);
    let out = "", i = 0;
    if (state !== null && state !== undefined) {
      const [, close, kind] = L.blocks[state], end = text.indexOf(close);
      if (end < 0) return [span(kind, text), state];
      out += span(kind, text.slice(0, end + close.length)); i = end + close.length;
    }
    if (i === 0 && L.keys) {
      const key = text.match(L.keys);
      if (key) { out += esc(key[1]) + span("t", key[2]); i = key[0].length; }
    }
    while (i < text.length) {
      const rest = text.slice(i), before = i ? text[i - 1] : "";
      if (L.line.some(m => rest.startsWith(m))) { out += span("c", rest); break; }
      const block = L.blocks.findIndex(([open]) => rest.startsWith(open));
      if (block >= 0) {
        const [open, close, kind] = L.blocks[block], end = rest.indexOf(close, open.length);
        if (end < 0) return [out + span(kind, rest), block];
        out += span(kind, rest.slice(0, end + close.length)); i += end + close.length; continue;
      }
      const quote = L.quotes.find(q => rest[0] === q);
      if (quote) {
        let j = 1;
        while (j < rest.length && rest[j] !== quote) j += rest[j] === "\\" ? 2 : 1;
        const s = rest.slice(0, Math.min(j + 1, rest.length));
        out += span("s", s); i += s.length; continue;
      }
      const at = L.at && rest.match(/^@[A-Za-z_][\w.]*/);
      if (at && !/\w/.test(before)) { out += span("a", at[0]); i += at[0].length; continue; }
      const number = !/[\w$]/.test(before) && rest.match(/^(0[xX][\da-fA-F_]+|\d[\d_]*(\.\d+)?([eE][+-]?\d+)?[lLfFdDmMuU]*)/);
      if (number) { out += span("n", number[0]); i += number[0].length; continue; }
      const word = rest.match(/^[A-Za-z_$][\w$]*/);
      if (word && !/[\w$]/.test(before)) {
        const w = word[0], keyword = L.keywords.has(L.nocase ? w.toLowerCase() : w);
        out += keyword ? span("k", w) : !L.notypes && /^[A-Z]/.test(w) && /[a-z]/.test(w) ? span("t", w) : esc(w);
        i += w.length; continue;
      }
      out += esc(text[i]); i++;
    }
    return [out, null];
  }

  // Lines that follow one another, each starting in the state the one before it left.
  function lines(lang, texts) {
    let state = null;
    return texts.map(text => { const [html, next] = line(lang, text, state); state = next; return html; });
  }

  const Syntax = { language, line, lines };
  if (typeof module !== "undefined" && module.exports) module.exports = Syntax;
  else root.Syntax = Syntax;
})(typeof window !== "undefined" ? window : globalThis);
