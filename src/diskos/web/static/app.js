"use strict";

const SERIES = ["--s1","--s2","--s3","--s4","--s5","--s6","--s7","--s8"];
const SVGNS = "http://www.w3.org/2000/svg";
const MAX_SERIES = 8;

const $ = (sel, root = document) => root.querySelector(sel);
const cssvar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const prettySpecies = (col) => col.replace(/_cnt$/, "").replace(/_/g, " ");

let WELLS = [];
let ACTIVE = null;

// ---------- boot ----------
init();

async function init() {
  setupTheme();
  try {
    const res = await fetch("/api/me");
    if (res.status === 401) return showGate();
    if (!res.ok) throw new Error("auth check failed");
    const me = await res.json();
    showApp(me.email);
    await loadWells();
  } catch (err) {
    showGate("Could not reach the server. Try again shortly.");
  }
}

function showGate(note) {
  $("#gate").hidden = false;
  $("#app").hidden = true;
  if (note) $("#gate-note").textContent = note;
}

function showApp(email) {
  $("#gate").hidden = true;
  $("#app").hidden = false;
  $("#user").textContent = email;
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
    if (ACTIVE) selectWell(ACTIVE, true); // re-render chart with new tokens
  });
}

// ---------- wells rail ----------
async function loadWells() {
  const res = await fetch("/api/wells");
  if (!res.ok) return;
  WELLS = await res.json();
  renderRail("");
  $("#filter").addEventListener("input", (e) => renderRail(e.target.value.trim().toLowerCase()));
}

function renderRail(filter) {
  const list = $("#welllist");
  list.replaceChildren();
  const shown = WELLS.filter((w) => w.well_id.toLowerCase().includes(filter));
  for (const w of shown) {
    const item = document.createElement("button");
    item.className = "wellitem" + (w.well_id === ACTIVE ? " active" : "");
    item.setAttribute("role", "option");
    item.innerHTML =
      `<span class="wid">${w.well_id}</span>` +
      `<span class="badges">` +
      badge("paly", w.paly) + badge("logs", w.logs) + badge("xrf", w.xrf) +
      `</span>`;
    item.addEventListener("click", () => selectWell(w.well_id));
    list.appendChild(item);
  }
  if (!shown.length) {
    const p = document.createElement("p");
    p.className = "msg";
    p.textContent = "No wells match.";
    p.style.padding = "8px 10px";
    list.appendChild(p);
  }
}

function badge(kind, n) {
  const on = n > 0 ? " on" : "";
  return `<span class="badge ${kind}${on}" title="${n} ${kind}">${kind}</span>`;
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
    const [detail, paly] = await Promise.all([
      fetch(`/api/wells/${encodeURIComponent(id)}`).then((r) => r.json()),
      fetch(`/api/wells/${encodeURIComponent(id)}/palynology`).then((r) => r.json()),
    ]);
    renderWell(detail, paly);
  } catch (err) {
    panel.replaceChildren(errorMsg("Could not load this well."));
  }
}

function renderWell(detail, paly) {
  const panel = $("#well");
  panel.replaceChildren();

  const head = document.createElement("div");
  head.className = "well-head";
  head.innerHTML =
    `<h2>${detail.well_id}</h2>` +
    `<span class="well-sub">${counts(detail)}</span>`;
  panel.appendChild(head);

  const pills = document.createElement("div");
  pills.className = "filepills";
  for (const kind of ["paly", "logs", "xrf"]) {
    for (const name of detail[kind] || []) {
      const pill = document.createElement("span");
      pill.className = "filepill";
      pill.textContent = name;
      pills.appendChild(pill);
    }
  }
  panel.appendChild(pills);

  const files = (paly.files || []).filter((f) => f.records && f.records.length);
  if (!files.length) {
    panel.appendChild(sectionLabel("Palynology"));
    panel.appendChild(msg("No palynology counts for this well yet."));
    return;
  }

  for (const file of files) {
    panel.appendChild(sectionLabel(`Palynology · ${file.file}`));
    const series = topSeries(file);
    if (series.length) {
      panel.appendChild(buildChartCard(file.records, series));
      if (file.pending_decisions && file.pending_decisions.length) {
        panel.appendChild(buildPending(file.pending_decisions));
      }
      panel.appendChild(buildTable(file.records, series));
    } else {
      panel.appendChild(msg("No species counts in this file."));
    }
  }
}

// species (count columns) ranked by total, capped at MAX_SERIES
function topSeries(file) {
  const cols = file.columns.filter((c) => c.endsWith("_cnt"));
  const totals = cols.map((c) => ({
    col: c,
    total: file.records.reduce((s, r) => s + (Number(r[c]) || 0), 0),
  }));
  totals.sort((a, b) => b.total - a.total);
  return totals
    .filter((t) => t.total > 0)
    .slice(0, MAX_SERIES)
    .map((t, i) => ({ col: t.col, total: t.total, color: cssvar(SERIES[i]), name: prettySpecies(t.col) }));
}

// ---------- depth-track chart ----------
function buildChartCard(records, series) {
  const card = document.createElement("div");
  card.className = "chartcard";
  const wrap = document.createElement("div");
  wrap.className = "chart-wrap";
  card.appendChild(wrap);

  const W = 720, H = 460;
  const m = { t: 16, r: 116, b: 42, l: 62 };
  const plotW = W - m.l - m.r, plotH = H - m.t - m.b;

  const depths = records.map((r) => Number(r.depth)).filter((d) => Number.isFinite(d));
  const dmin = Math.min(...depths), dmax = Math.max(...depths);
  let xmax = 0;
  for (const s of series) for (const r of records) xmax = Math.max(xmax, Number(r[s.col]) || 0);
  xmax = xmax || 1;

  const yOf = (d) => m.t + (dmax === dmin ? plotH / 2 : ((d - dmin) / (dmax - dmin)) * plotH);
  const xOf = (v) => m.l + (v / xmax) * plotW;

  const svg = el("svg", { class: "depthchart", viewBox: `0 0 ${W} ${H}`, role: "img" });

  // grid + axes
  const grid = el("g", { class: "grid" });
  const yTicks = niceTicks(dmin, dmax, 6);
  for (const d of yTicks) grid.appendChild(el("line", { x1: m.l, x2: m.l + plotW, y1: yOf(d), y2: yOf(d) }));
  const xTicks = niceTicks(0, xmax, 4);
  for (const v of xTicks) grid.appendChild(el("line", { x1: xOf(v), x2: xOf(v), y1: m.t, y2: m.t + plotH }));
  svg.appendChild(grid);

  const axis = el("g", { class: "axis" });
  // depth ruler (left, monospace) — the signature
  axis.appendChild(el("line", { x1: m.l, x2: m.l, y1: m.t, y2: m.t + plotH, stroke: cssvar("--line") }));
  for (const d of yTicks) {
    const t = el("text", { x: m.l - 8, y: yOf(d) + 3, "text-anchor": "end" });
    t.textContent = Math.round(d);
    axis.appendChild(t);
  }
  axis.appendChild(text(m.l - 44, m.t + plotH / 2, "depth (m)", { class: "axis-title", transform: `rotate(-90 ${m.l - 44} ${m.t + plotH / 2})`, "text-anchor": "middle" }));
  // count axis (bottom)
  for (const v of xTicks) {
    const t = el("text", { x: xOf(v), y: m.t + plotH + 16, "text-anchor": "middle" });
    t.textContent = trim(v);
    axis.appendChild(t);
  }
  axis.appendChild(text(m.l + plotW / 2, H - 6, "count", { class: "axis-title", "text-anchor": "middle" }));
  svg.appendChild(axis);

  // series
  for (const s of series) {
    const pts = records
      .map((r) => ({ d: Number(r.depth), v: Number(r[s.col]) }))
      .filter((p) => Number.isFinite(p.d) && Number.isFinite(p.v))
      .sort((a, b) => a.d - b.d);
    if (!pts.length) continue;
    const g = el("g");
    const dAttr = pts.map((p, i) => `${i ? "L" : "M"}${xOf(p.v).toFixed(1)},${yOf(p.d).toFixed(1)}`).join(" ");
    g.appendChild(el("path", { class: "serie-line", d: dAttr, stroke: s.color }));
    for (const p of pts) g.appendChild(el("circle", { class: "serie-dot", cx: xOf(p.v), cy: yOf(p.d), r: 3.5, fill: s.color }));
    svg.appendChild(g);
  }

  // direct labels for the top <=4 series, placed at each series' PEAK (max count)
  // so they spread down the chart instead of colliding at the shallowest depth.
  series.slice(0, 4).forEach((s) => {
    const peak = records
      .map((r) => ({ d: Number(r.depth), v: Number(r[s.col]) }))
      .filter((q) => Number.isFinite(q.d) && Number.isFinite(q.v))
      .reduce((best, q) => (best && best.v >= q.v ? best : q), null);
    if (!peak) return;
    const lx = Math.min(xOf(peak.v) + 8, m.l + plotW - 4);
    const anchor = lx > m.l + plotW - 90 ? "end" : "start";
    const lbl = text(anchor === "end" ? xOf(peak.v) - 8 : lx, yOf(peak.d) - 6, s.name, {
      class: "serie-label", fill: s.color, "text-anchor": anchor,
    });
    svg.appendChild(lbl);
  });

  // crosshair + hover overlay
  const cross = el("line", { class: "crosshair", x1: m.l, x2: m.l + plotW, y1: m.t, y2: m.t });
  svg.appendChild(cross);
  const overlay = el("rect", { x: m.l, y: m.t, width: plotW, height: plotH, fill: "transparent" });
  svg.appendChild(overlay);
  wrap.appendChild(svg);

  const tip = document.createElement("div");
  tip.className = "tooltip";
  wrap.appendChild(tip);

  const uniqDepths = [...new Set(depths)].sort((a, b) => a - b);
  overlay.addEventListener("mousemove", (e) => {
    const rect = svg.getBoundingClientRect();
    const scale = H / rect.height;
    const yPix = (e.clientY - rect.top) * scale;
    const depthAt = dmin + (dmax === dmin ? 0 : ((yPix - m.t) / plotH) * (dmax - dmin));
    const d = nearest(uniqDepths, depthAt);
    cross.setAttribute("y1", yOf(d)); cross.setAttribute("y2", yOf(d)); cross.style.opacity = 1;
    const rec = records.find((r) => Number(r.depth) === d) || {};
    let rows = "";
    for (const s of series) {
      const v = rec[s.col];
      if (v === null || v === undefined || v === "") continue;
      rows += `<div class="tt-row"><span class="k"><span class="tt-sw" style="background:${s.color}"></span>${s.name}</span><span class="v">${trim(v)}</span></div>`;
    }
    tip.innerHTML = `<div class="tt-depth">${Math.round(d)} m</div>${rows || '<div class="tt-row"><span class="k">no counts</span></div>'}`;
    tip.style.opacity = 1;
    const left = Math.min(e.clientX - rect.left + 14, rect.width - tip.offsetWidth - 8);
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = Math.min((yOf(d) / scale) + 8, rect.height - tip.offsetHeight - 8) + "px";
  });
  overlay.addEventListener("mouseleave", () => { cross.style.opacity = 0; tip.style.opacity = 0; });

  // legend (all shown series)
  const legend = document.createElement("div");
  legend.className = "legend";
  for (const s of series) {
    const item = document.createElement("span");
    item.className = "item";
    item.innerHTML = `<span class="sw" style="background:${s.color}"></span>${s.name} <span style="color:var(--text-3)">· ${trim(s.total)}</span>`;
    legend.appendChild(item);
  }
  card.appendChild(legend);
  return card;
}

function buildPending(pending) {
  const box = document.createElement("div");
  box.className = "pending";
  const items = pending
    .map((p) => `<li>${p.variant} ~ ${p.target} (sim ${Number(p.similarity).toFixed(2)})</li>`)
    .join("");
  box.innerHTML =
    `<h3>${pending.length} similar name${pending.length > 1 ? "s" : ""} awaiting a decision</h3>` +
    `<p>These names look like a target species but were not merged automatically. A same/different call is needed before their counts fold in.</p>` +
    `<ul>${items}</ul>`;
  return box;
}

function buildTable(records, series) {
  const wrap = document.createElement("div");
  wrap.className = "tablewrap";
  const table = document.createElement("table");
  table.className = "data";
  const cols = series.map((s) => s.col);
  const head = "<tr><th>depth</th>" + series.map((s) => `<th title="${s.name}">${s.name}</th>`).join("") + "</tr>";
  const rows = records
    .slice()
    .sort((a, b) => Number(a.depth) - Number(b.depth))
    .map((r) => {
      const cells = cols.map((c) => `<td>${r[c] == null ? "" : trim(r[c])}</td>`).join("");
      return `<tr><td>${trim(r.depth)}</td>${cells}</tr>`;
    })
    .join("");
  table.innerHTML = `<thead>${head}</thead><tbody>${rows}</tbody>`;
  wrap.appendChild(table);
  return wrap;
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
function counts(detail) {
  const parts = [];
  for (const k of ["paly", "logs", "xrf"]) { const n = (detail[k] || []).length; if (n) parts.push(`${n} ${k}`); }
  return parts.join(" · ") || "no data files";
}
const sectionLabel = (s) => { const p = document.createElement("p"); p.className = "section-label"; p.textContent = s; return p; };
const msg = (s) => { const p = document.createElement("p"); p.className = "msg"; p.textContent = s; return p; };
const errorMsg = (s) => { const p = document.createElement("p"); p.className = "msg error"; p.textContent = s; return p; };
const loadingMsg = () => msg("Loading…");
