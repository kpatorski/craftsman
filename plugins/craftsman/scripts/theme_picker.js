// The palette picker the dashboard and the review page share. Any element with `data-theme-picker` opens it; picking
// a palette asks the server to keep it and swaps the page's `<style id="theme">` in place, without a reload. A page
// that comes back into view takes the palette picked meanwhile in another tab.
(() => {
  const css = document.createElement("style");
  css.textContent = `
    .theme-pop { position: fixed; z-index: 60; width: 340px; max-height: calc(100vh - 32px); overflow-y: auto; padding: 6px;
      background: var(--float); border: 1px solid var(--line2); border-radius: var(--radius); box-shadow: 0 16px 40px var(--shadow);
      font: 300 .8125rem/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--text); }
    .theme-pop .theme-head { padding: 8px 10px 6px; color: var(--muted); font-size: .75rem; }
    .theme-pop button { display: grid; grid-template-columns: 76px minmax(0, 1fr) 14px; gap: 10px; align-items: center; width: 100%;
      padding: 8px 10px; border: 1px solid transparent; border-radius: var(--radius-sm); background: none; color: inherit;
      font: inherit; text-align: left; cursor: pointer; }
    .theme-pop button:hover { background: var(--card2); }
    .theme-pop button.on { border-color: var(--neon-dim); background: var(--neon-bg); }
    .theme-pop .theme-name { color: var(--heading); font-weight: 400; }
    .theme-pop .theme-note { color: var(--muted); font-size: .75rem; }
    .theme-pop .theme-sw { display: flex; height: 22px; border-radius: 6px; overflow: hidden; border: 1px solid var(--line2); }
    .theme-pop .theme-sw i { flex: 1; }
    .theme-pop .theme-tick { color: var(--neon); }`;
  document.head.append(css);

  let pop = null, anchor = null;
  const style = () => document.getElementById("theme");
  const close = () => { if (pop) pop.remove(); pop = anchor = null; };

  async function load() {
    const r = await fetch("/api/theme");
    return r.ok ? r.json() : null;
  }

  function paint(theme) {
    pop.innerHTML = `<div class="theme-head">Colour palette · kept for every craftsman page</div>` + theme.palettes.map(p =>
      `<button data-palette="${p.id}" class="${p.id === theme.current ? "on" : ""}">` +
      `<span class="theme-sw">${p.swatch.map(c => `<i style="background:${c}"></i>`).join("")}</span>` +
      `<span><div class="theme-name">${p.name}</div><div class="theme-note">${p.note}</div></span>` +
      `<span class="theme-tick">${p.id === theme.current ? "✓" : ""}</span></button>`).join("");
  }

  function place() {
    const box = anchor.getBoundingClientRect(), width = 340;
    const left = box.right + 8 + width < innerWidth ? box.right + 8 : Math.max(8, box.right - width);
    pop.style.left = `${left}px`;
    const below = box.right + 8 + width < innerWidth ? box.top : box.bottom + 6;
    pop.style.top = `${Math.max(8, Math.min(below, innerHeight - pop.offsetHeight - 8))}px`;
  }

  async function open(at) {
    const theme = await load();
    if (!theme) return;
    close();
    anchor = at;
    pop = document.createElement("div");
    pop.className = "theme-pop";
    document.body.append(pop);
    paint(theme);
    place();
  }

  async function pick(id) {
    const r = await fetch("/api/theme", { method: "POST", headers: { "Content-Type": "application/json", "X-Craftsman": "1" },
      body: JSON.stringify({ id }) });
    if (!r.ok) return;
    style().textContent = (await r.json()).css;
    const theme = await load();
    if (theme && pop) paint(theme);
  }

  document.addEventListener("click", e => {
    const opener = e.target.closest("[data-theme-picker]"), palette = e.target.closest(".theme-pop [data-palette]");
    if (palette) return pick(palette.dataset.palette);
    if (opener) { e.preventDefault(); return pop && anchor === opener ? close() : open(opener); }
    if (pop && !e.target.closest(".theme-pop")) close();
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState !== "visible") return;
    const theme = await load();
    if (theme && style().textContent !== theme.css) style().textContent = theme.css;
  });
})();
