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

const fetchJSON = (url) => fetch(url).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });

function renderWell(detail, paly) {
  const panel = $("#well");
  panel.replaceChildren();

  const head = document.createElement("div");
  head.className = "well-head";
  head.innerHTML = `<h2>${detail.well_id}</h2><span class="well-sub">${counts(detail)}</span>`;
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

  const id = detail.well_id;
  const tabs = [];
  if ((detail.paly || []).length) tabs.push({ label: "Palynology", render: (c) => renderPalyPanel(c, paly) });
  if ((detail.logs || []).length) tabs.push({ label: "Well logs", load: () => fetchJSON(`/api/wells/${encodeURIComponent(id)}/logs`), render: renderLogsPanel });
  if ((detail.xrf || []).length) tabs.push({ label: "XRF", load: () => fetchJSON(`/api/wells/${encodeURIComponent(id)}/xrf`), render: (c, d) => renderXrfPanel(c, d, id) });

  if (!tabs.length) { panel.appendChild(msg("No data files for this well.")); return; }
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
    } else {
      def.render(pc);
    }
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

function renderPalyPanel(container, paly) {
  const files = (paly.files || []).filter((f) => f.records && f.records.length);
  if (!files.length) { container.appendChild(msg("No palynology counts for this well yet.")); return; }
  for (const file of files) {
    container.appendChild(sectionLabel(file.file));
    const series = topSeries(file);
    if (!series.length) { container.appendChild(msg("No species counts in this file.")); continue; }
    container.appendChild(buildChartCard(file.records, series));
    if (file.pending_decisions && file.pending_decisions.length) container.appendChild(buildPending(file.pending_decisions));
    container.appendChild(buildTable(file.records, series));
  }
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

function renderXrfPanel(container, data, wellId) {
  const files = data.files || [];
  if (!files.length) { container.appendChild(msg("No XRF spectra for this well.")); return; }
  for (const file of files) {
    container.appendChild(sectionLabel(file.file));

    const controls = document.createElement("div");
    controls.className = "xrf-controls";
    const depthSel = selectEl("Depth", (file.depths || []).map((d) => [d, `${d} m`]));
    const rangeSel = selectEl("Range", (file.ranges || []).map((r) => [r, r]));
    controls.append(depthSel.wrap, rangeSel.wrap);
    container.appendChild(controls);

    const holder = document.createElement("div");
    container.appendChild(holder);
    const draw = (spectrum) => holder.replaceChildren(spectrum ? buildSpectrumCard(spectrum) : msg("No spectrum for that selection."));
    draw(file.spectrum);
    if (file.spectrum) { depthSel.set(file.spectrum.depth); rangeSel.set(file.spectrum.range); }

    const reload = async () => {
      holder.replaceChildren(loadingMsg());
      try {
        const d = await fetchJSON(`/api/wells/${encodeURIComponent(wellId)}/xrf?depth=${depthSel.value()}&range_type=${encodeURIComponent(rangeSel.value())}`);
        const f = (d.files || []).find((x) => x.file === file.file) || d.files[0];
        draw(f && f.spectrum);
      } catch (e) { holder.replaceChildren(errorMsg("Could not load spectrum.")); }
    };
    depthSel.el.addEventListener("change", reload);
    rangeSel.el.addEventListener("change", reload);
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

// ---------- xrf spectrum (counts vs energy, log counts) ----------
function buildSpectrumCard(spectrum) {
  const E = spectrum.energy || [], C = spectrum.counts || [];
  if (!E.length) return msg("Empty spectrum.");

  const card = document.createElement("div");
  card.className = "chartcard";
  const wrap = document.createElement("div");
  wrap.className = "chart-wrap";
  card.appendChild(wrap);

  const W = 720, H = 340, m = { t: 16, r: 20, b: 44, l: 60 };
  const plotW = W - m.l - m.r, plotH = H - m.t - m.b;
  const emin = Math.min(...E), emax = Math.max(...E);
  const cmax = Math.max(...C, 1);
  const logMax = Math.log10(cmax + 1);
  const xOf = (e) => m.l + (emax === emin ? 0 : ((e - emin) / (emax - emin)) * plotW);
  const yOf = (c) => m.t + plotH - (Math.log10(Math.max(0, c) + 1) / logMax) * plotH;
  const color = cssvar("--s3");

  const svg = el("svg", { class: "depthchart", viewBox: `0 0 ${W} ${H}`, role: "img" });
  const grid = el("g", { class: "grid" });
  const xT = niceTicks(emin, emax, 6);
  for (const e of xT) grid.appendChild(el("line", { x1: xOf(e), x2: xOf(e), y1: m.t, y2: m.t + plotH }));
  const decades = [];
  for (let p = 0; Math.pow(10, p) <= cmax; p++) decades.push(Math.pow(10, p));
  for (const c of decades) grid.appendChild(el("line", { x1: m.l, x2: m.l + plotW, y1: yOf(c), y2: yOf(c) }));
  svg.appendChild(grid);

  const axis = el("g", { class: "axis" });
  for (const c of decades) { const t = el("text", { x: m.l - 8, y: yOf(c) + 3, "text-anchor": "end" }); t.textContent = c; axis.appendChild(t); }
  axis.appendChild(text(m.l - 44, m.t + plotH / 2, "counts (log)", { class: "axis-title", transform: `rotate(-90 ${m.l - 44} ${m.t + plotH / 2})`, "text-anchor": "middle" }));
  for (const e of xT) { const t = el("text", { x: xOf(e), y: m.t + plotH + 16, "text-anchor": "middle" }); t.textContent = trim(e); axis.appendChild(t); }
  axis.appendChild(text(m.l + plotW / 2, H - 6, "energy (keV)", { class: "axis-title", "text-anchor": "middle" }));
  svg.appendChild(axis);

  const dAttr = E.map((e, i) => `${i ? "L" : "M"}${xOf(e).toFixed(1)},${yOf(C[i]).toFixed(1)}`).join(" ");
  svg.appendChild(el("path", { class: "serie-line", d: dAttr, stroke: color, "stroke-width": 1.4 }));

  const cross = el("line", { class: "crosshair", x1: m.l, x2: m.l, y1: m.t, y2: m.t + plotH });
  svg.appendChild(cross);
  const overlay = el("rect", { x: m.l, y: m.t, width: plotW, height: plotH, fill: "transparent" });
  svg.appendChild(overlay);
  wrap.appendChild(svg);

  const tip = document.createElement("div");
  tip.className = "tooltip";
  wrap.appendChild(tip);
  overlay.addEventListener("mousemove", (ev) => {
    const rect = svg.getBoundingClientRect(), scale = W / rect.width;
    const e = emin + ((ev.clientX - rect.left) * scale - m.l) / plotW * (emax - emin);
    let idx = 0, bd = Infinity;
    for (let i = 0; i < E.length; i++) { const d = Math.abs(E[i] - e); if (d < bd) { bd = d; idx = i; } }
    cross.setAttribute("x1", xOf(E[idx])); cross.setAttribute("x2", xOf(E[idx])); cross.style.opacity = 1;
    tip.innerHTML = `<div class="tt-depth">${E[idx].toFixed(2)} keV</div><div class="tt-row"><span class="k">counts</span><span class="v">${Math.round(C[idx])}</span></div>`;
    tip.style.opacity = 1;
    tip.style.left = Math.max(8, Math.min(ev.clientX - rect.left + 14, rect.width - tip.offsetWidth - 8)) + "px";
    tip.style.top = "12px";
  });
  overlay.addEventListener("mouseleave", () => { cross.style.opacity = 0; tip.style.opacity = 0; });
  return card;
}

function selectEl(label, options) {
  const wrap = document.createElement("label");
  wrap.textContent = label + " ";
  const sel = document.createElement("select");
  for (const [val, text] of options) {
    const opt = document.createElement("option");
    opt.value = val; opt.textContent = text;
    sel.appendChild(opt);
  }
  wrap.appendChild(sel);
  return { wrap, el: sel, value: () => sel.value, set: (v) => { sel.value = v; } };
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
