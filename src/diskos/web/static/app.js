"use strict";

const SVGNS = "http://www.w3.org/2000/svg";
const RAIL_CAP = 400; // wells rendered at once; the filter narrows the rest

// Data-type display labels (keys come from wells.py DATA_TYPES).
const TYPE_LABEL = {
  logs: "Well logs", seismic: "Seismic", deviation: "Well path / deviation",
  geology: "Geology & reports", images: "Images", geochem: "Geochemistry",
  core: "Core", other: "Other",
};

const $ = (sel, root = document) => root.querySelector(sel);
const cssvar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fetchJSON = (url) => fetch(url).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });

let WELLS = [];
let ACTIVE = null;

init();

async function init() {
  setupTheme();
  try {
    const res = await fetch("/api/me");
    if (res.status === 401) return showGate();
    if (!res.ok) throw new Error("auth");
    showApp((await res.json()).email);
    await loadWells();
  } catch (e) {
    showGate("Could not reach the server. Try again shortly.");
  }
}

function showGate(note) {
  $("#gate").hidden = false; $("#app").hidden = true;
  if (note) $("#gate-note").textContent = note;
}
function showApp(email) {
  $("#gate").hidden = true; $("#app").hidden = false; $("#user").textContent = email;
}

function setupTheme() {
  const root = document.documentElement;
  const saved = localStorage.getItem("diskos-theme");
  if (saved) root.setAttribute("data-theme", saved);
  $("#theme").addEventListener("click", () => {
    const cur = root.getAttribute("data-theme");
    const isDark = cur === "dark" || (cur === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
    const next = isDark ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("diskos-theme", next);
    if (ACTIVE) selectWell(ACTIVE, true);
  });
}

// ---------- wells rail ----------
async function loadWells() {
  WELLS = await fetchJSON("/api/wells");
  renderRail("");
  $("#filter").addEventListener("input", (e) => renderRail(e.target.value.trim().toLowerCase()));
}

function renderRail(filter) {
  const list = $("#welllist");
  list.replaceChildren();
  const matches = WELLS.filter((w) => w.well_id.toLowerCase().includes(filter));
  for (const w of matches.slice(0, RAIL_CAP)) {
    const item = document.createElement("button");
    item.className = "wellitem" + (w.well_id === ACTIVE ? " active" : "");
    item.setAttribute("role", "option");
    item.innerHTML = `<span class="wid">${w.well_id}</span>`;
    item.addEventListener("click", () => selectWell(w.well_id));
    list.appendChild(item);
  }
  const note = document.createElement("p");
  note.className = "rail-note";
  if (!matches.length) note.textContent = "No wells match.";
  else if (matches.length > RAIL_CAP) note.textContent = `Showing ${RAIL_CAP} of ${matches.length}. Keep typing to narrow.`;
  else note.textContent = `${matches.length} well${matches.length > 1 ? "s" : ""}`;
  list.appendChild(note);
}

// ---------- well detail ----------
async function selectWell(id, keepScroll) {
  ACTIVE = id;
  renderRail($("#filter").value.trim().toLowerCase());
  $("#empty").hidden = true;
  const panel = $("#well");
  panel.hidden = false;
  if (!keepScroll) panel.scrollTop = 0;
  panel.replaceChildren(loadingMsg());
  try {
    renderWell(await fetchJSON(`/api/wells/${encodeURIComponent(id)}`));
  } catch (e) {
    panel.replaceChildren(errorMsg("Could not load this well."));
  }
}

function renderWell(detail) {
  const panel = $("#well");
  panel.replaceChildren();

  const total = Object.values(detail.counts || {}).reduce((a, b) => a + b, 0);
  const summary = Object.entries(detail.counts || {})
    .map(([t, n]) => `${n} ${TYPE_LABEL[t] || t}`).join(" · ") || "no data files";
  const head = document.createElement("div");
  head.className = "well-head";
  head.innerHTML = `<h2>${detail.well_id}</h2><span class="well-sub">${summary}</span>`;
  panel.appendChild(head);

  if (!total) { panel.appendChild(msg("No data files for this well.")); return; }

  const id = detail.well_id;
  const tabs = [];
  if (detail.counts.logs) tabs.push({ label: "Well logs", load: () => fetchJSON(`/api/wells/${encodeURIComponent(id)}/logs`), render: renderLogsPanel });
  tabs.push({ label: "Files", render: (c) => renderFilesPanel(c, detail) });
  buildTabs(panel, tabs);
}

function buildTabs(panel, defs) {
  const bar = document.createElement("div");
  bar.className = "tabs";
  const panels = [];
  const activate = async (def, btn, pc) => {
    bar.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    panels.forEach((p) => (p.hidden = true));
    pc.hidden = false;
    if (def._loaded) return;
    def._loaded = true;
    if (def.load) {
      pc.replaceChildren(loadingMsg());
      try { const data = await def.load(); pc.replaceChildren(); def.render(pc, data); }
      catch (e) { pc.replaceChildren(errorMsg("Could not load this view.")); def._loaded = false; }
    } else def.render(pc);
  };
  defs.forEach((def, i) => {
    const btn = document.createElement("button");
    btn.className = "tab" + (i === 0 ? " active" : "");
    btn.textContent = def.label;
    const pc = document.createElement("div");
    pc.className = "tabpanel";
    pc.hidden = i !== 0;
    btn.addEventListener("click", () => activate(def, btn, pc));
    bar.appendChild(btn);
    panels.push(pc);
    if (i === 0) activate(def, btn, pc);
  });
  panel.appendChild(bar);
  panels.forEach((p) => panel.appendChild(p));
}

function renderFilesPanel(container, detail) {
  const biostrat = new Set(detail.biostrat || []);
  for (const type of Object.keys(TYPE_LABEL)) {
    const files = (detail.files || {})[type];
    if (!files || !files.length) continue;
    const group = document.createElement("div");
    group.className = "filegroup";
    group.innerHTML = `<h3>${TYPE_LABEL[type]} <span class="ct">${files.length}</span></h3>`;
    const ul = document.createElement("ul");
    ul.className = "filelist";
    for (const name of files) {
      const li = document.createElement("li");
      li.textContent = name;
      if (biostrat.has(name)) {
        const b = document.createElement("span");
        b.className = "biostrat-tag";
        b.textContent = "biostrat";
        li.appendChild(b);
      }
      ul.appendChild(li);
    }
    group.appendChild(ul);
    container.appendChild(group);
  }
  const note = document.createElement("p");
  note.className = "msg";
  note.textContent = "File contents are not yet served here. Logs are charted in the Well logs tab; report and image viewing are coming.";
  container.appendChild(note);
}

function renderLogsPanel(container, data) {
  const files = (data.files || []).filter((f) => f.tracks && f.tracks.length);
  if (!files.length) { container.appendChild(msg("No readable log curves for this well.")); return; }
  for (const file of files) {
    const mn = file.tracks.map((t) => t.mnemonic).join(", ");
    container.appendChild(sectionLabel(`${file.file} · ${mn}`));
    for (const track of file.tracks) container.appendChild(buildLogCard(track));
  }
}

// ---------- well-log gamma track ----------
function buildLogCard(track) {
  const pts = (track.points || [])
    .filter((p) => Number.isFinite(p.depth) && Number.isFinite(p.value))
    .sort((a, b) => a.depth - b.depth);
  if (!pts.length) return msg("No curve data.");

  const card = document.createElement("div");
  card.className = "chartcard";
  const wrap = document.createElement("div");
  wrap.className = "chart-wrap";
  card.appendChild(wrap);

  const W = 560, H = 460, m = { t: 16, r: 22, b: 42, l: 64 };
  const plotW = W - m.l - m.r, plotH = H - m.t - m.b;
  const dmin = Math.min(...pts.map((p) => p.depth)), dmax = Math.max(...pts.map((p) => p.depth));
  const vmax = Math.max(...pts.map((p) => p.value)), vmin = Math.min(0, ...pts.map((p) => p.value));
  const yOf = (d) => m.t + (dmax === dmin ? plotH / 2 : ((d - dmin) / (dmax - dmin)) * plotH);
  const xOf = (v) => m.l + ((v - vmin) / ((vmax - vmin) || 1)) * plotW;
  const color = cssvar("--s1");

  const svg = el("svg", { class: "depthchart", viewBox: `0 0 ${W} ${H}`, role: "img" });
  const grid = el("g", { class: "grid" });
  const yT = niceTicks(dmin, dmax, 6), xT = niceTicks(vmin, vmax, 4);
  for (const d of yT) grid.appendChild(el("line", { x1: m.l, x2: m.l + plotW, y1: yOf(d), y2: yOf(d) }));
  for (const v of xT) grid.appendChild(el("line", { x1: xOf(v), x2: xOf(v), y1: m.t, y2: m.t + plotH }));
  svg.appendChild(grid);

  const axis = el("g", { class: "axis" });
  axis.appendChild(el("line", { x1: m.l, x2: m.l, y1: m.t, y2: m.t + plotH, stroke: cssvar("--line") }));
  for (const d of yT) { const t = el("text", { x: m.l - 8, y: yOf(d) + 3, "text-anchor": "end" }); t.textContent = Math.round(d); axis.appendChild(t); }
  axis.appendChild(text(m.l - 46, m.t + plotH / 2, "depth (m)", { class: "axis-title", transform: `rotate(-90 ${m.l - 46} ${m.t + plotH / 2})`, "text-anchor": "middle" }));
  for (const v of xT) { const t = el("text", { x: xOf(v), y: m.t + plotH + 16, "text-anchor": "middle" }); t.textContent = trim(v); axis.appendChild(t); }
  axis.appendChild(text(m.l + plotW / 2, H - 6, track.mnemonic, { class: "axis-title", "text-anchor": "middle" }));
  svg.appendChild(axis);

  const dAttr = pts.map((p, i) => `${i ? "L" : "M"}${xOf(p.value).toFixed(1)},${yOf(p.depth).toFixed(1)}`).join(" ");
  svg.appendChild(el("path", { class: "serie-line", d: dAttr, stroke: color }));

  const cross = el("line", { class: "crosshair", x1: m.l, x2: m.l + plotW, y1: m.t, y2: m.t });
  svg.appendChild(cross);
  const overlay = el("rect", { x: m.l, y: m.t, width: plotW, height: plotH, fill: "transparent" });
  svg.appendChild(overlay);
  wrap.appendChild(svg);

  const tip = document.createElement("div");
  tip.className = "tooltip";
  wrap.appendChild(tip);
  const depths = pts.map((p) => p.depth);
  overlay.addEventListener("mousemove", (e) => {
    const rect = svg.getBoundingClientRect(), scale = H / rect.height;
    const d = nearest(depths, dmin + ((e.clientY - rect.top) * scale - m.t) / plotH * (dmax - dmin));
    const p = pts.find((q) => q.depth === d);
    cross.setAttribute("y1", yOf(d)); cross.setAttribute("y2", yOf(d)); cross.style.opacity = 1;
    tip.innerHTML = `<div class="tt-depth">${Math.round(d)} m</div><div class="tt-row"><span class="k"><span class="tt-sw" style="background:${color}"></span>${track.mnemonic}</span><span class="v">${trim(p.value)}</span></div>`;
    tip.style.opacity = 1;
    tip.style.left = Math.max(8, Math.min(e.clientX - rect.left + 14, rect.width - tip.offsetWidth - 8)) + "px";
    tip.style.top = Math.min(yOf(d) / scale + 8, rect.height - tip.offsetHeight - 8) + "px";
  });
  overlay.addEventListener("mouseleave", () => { cross.style.opacity = 0; tip.style.opacity = 0; });
  return card;
}

// ---------- helpers ----------
function el(name, attrs = {}) {
  const node = document.createElementNS(SVGNS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}
function text(x, y, str, attrs = {}) {
  const t = el("text", { x, y, ...attrs });
  t.textContent = str;
  return t;
}
function niceTicks(min, max, count) {
  if (max === min) return [min];
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const m = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  const step = m * mag;
  const start = Math.ceil(min / step) * step;
  const out = [];
  for (let v = start; v <= max + 1e-9; v += step) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}
function nearest(sorted, v) {
  let best = sorted[0], bd = Infinity;
  for (const s of sorted) { const d = Math.abs(s - v); if (d < bd) { bd = d; best = s; } }
  return best;
}
function trim(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}
const sectionLabel = (s) => { const p = document.createElement("p"); p.className = "section-label"; p.textContent = s; return p; };
const msg = (s) => { const p = document.createElement("p"); p.className = "msg"; p.textContent = s; return p; };
const errorMsg = (s) => { const p = document.createElement("p"); p.className = "msg error"; p.textContent = s; return p; };
const loadingMsg = () => msg("Loading…");
