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
const API_ROOT = (window.API_BASE || "").replace(/\/+$/, "");
const apiUrl = (p) => API_ROOT + (p[0] === "/" ? p : "/" + p);
const fetchJSON = (url) => fetch(apiUrl(url), { credentials: "include" }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });

let WELLS = [];
let ACTIVE = null;
let MAP = null; // live Leaflet map, torn down when leaving the Map view
let MAP_VIEW = null; // remembered {center, zoom} so returning to the map keeps your place

init();

const setStatus = (left, right) => {
  if (left != null) $("#status-left").textContent = left;
  if (right != null) $("#status-right").textContent = right;
};

async function init() {
  try {
    const res = await fetch(apiUrl("/api/me"), { credentials: "include" });
    if (res.status === 401) return showGate();
    if (!res.ok) throw new Error("auth");
    showApp((await res.json()).email);
    await loadWells();
  } catch (e) {
    showGate("Could not reach the server. Try again shortly.");
  }
}

function showGate(note) {
  const si = $("#signin"); if (si) si.href = apiUrl("auth/login");
  $("#gate").hidden = false; $("#app").hidden = true;
  if (note) $("#gate-note").textContent = note;
}
function showApp(email) {
  const lo = $("#logout"); if (lo) lo.href = apiUrl("auth/logout");
  $("#gate").hidden = true; $("#app").hidden = false; $("#user").textContent = email;
}

// ---------- wells rail ----------
async function loadWells() {
  WELLS = await fetchJSON("/api/wells");
  renderRail("");
  setStatus("Ready", `${WELLS.length} wells`);
  $("#filter").addEventListener("input", (e) => renderRail(e.target.value.trim().toLowerCase()));
  $("#mapbtn").addEventListener("click", showMap);
  $("#corpusbtn").addEventListener("click", showCorpus);
  $("#workflowbtn").addEventListener("click", showWorkflow);
}

// Tear down the Leaflet map before switching views (frees its window listeners),
// remembering where you were so returning to the map keeps that pan/zoom.
function clearMap() {
  if (MAP) {
    try { MAP_VIEW = { center: MAP.getCenter(), zoom: MAP.getZoom() }; } catch (e) { /* not ready */ }
    MAP.remove();
    MAP = null;
  }
}

async function showMap() {
  ACTIVE = null;
  clearMap();
  renderRail($("#filter").value.trim().toLowerCase());
  $("#empty").hidden = true;
  const panel = $("#well");
  panel.hidden = false;
  panel.scrollTop = 0;
  panel.replaceChildren(loadingMsg());
  try {
    renderMapPanel(panel, await fetchJSON("/api/map"));
  } catch (e) {
    panel.replaceChildren(errorMsg("Could not load the map."));
  }
}

function renderMapPanel(container, data) {
  container.replaceChildren();
  setStatus("Map", `${data.count} located boreholes`);
  const head = document.createElement("div");
  head.className = "well-head";
  head.innerHTML = `<h2>Borehole map</h2><span class="well-sub">${data.count} located boreholes &middot; orange marks a biostrat report</span>`;
  container.appendChild(head);

  const mapEl = document.createElement("div");
  mapEl.className = "borehole-map";
  container.appendChild(mapEl);

  const map = L.map(mapEl, { preferCanvas: true }).setView([60, 3], 5);
  MAP = map;
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    subdomains: "abcd", maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
  }).addTo(map);

  const bounds = [];
  for (const p of data.points) {
    const bio = p.biostrat;
    const marker = L.circleMarker([p.lat, p.lon], {
      radius: bio ? 5 : 3.5, weight: 1,
      color: bio ? "#a5480a" : "#12305e",
      fillColor: bio ? "#ff8c1a" : "#3a7bd5", fillOpacity: 0.85,
    });
    const field = p.field ? " · " + p.field : "";
    marker.bindTooltip(`${p.borehole_id}${field}`, { direction: "top" });
    marker.on("click", () => selectWell(p.borehole_id));
    marker.addTo(map);
    bounds.push([p.lat, p.lon]);
  }
  // The container was just inserted, so its size is not laid out yet. Recompute
  // the size first, THEN fit the bounds, otherwise fitBounds zooms against a
  // zero-size box and lands on an empty patch with every marker off-screen.
  setTimeout(() => {
    map.invalidateSize();
    if (MAP_VIEW) {
      map.setView(MAP_VIEW.center, MAP_VIEW.zoom); // restore where you were
    } else if (bounds.length) {
      map.fitBounds(bounds, { padding: [24, 24] });
    }
  }, 0);
}

function showWorkflow() {
  ACTIVE = null;
  clearMap();
  renderRail($("#filter").value.trim().toLowerCase());
  $("#empty").hidden = true;
  const panel = $("#well");
  panel.hidden = false;
  panel.scrollTop = 0;
  renderWorkflow(panel);
}

function renderWorkflow(container) {
  container.replaceChildren();
  setStatus("Workflow", "example from Well_Logs notebook");

  const head = document.createElement("div");
  head.className = "well-head";
  head.innerHTML = `<h2>Workflow</h2><span class="well-sub">connect a data source to a chat, generate output notes</span>`;
  container.appendChild(head);
  container.appendChild(sectionLabel("Example: plot a well log (from Jack's Well_Logs notebook)"));

  const flow = document.createElement("div");
  flow.className = "wf";
  container.appendChild(flow);

  // Source node
  const src = wfNode("Data source", "wf-source");
  const wid = document.createElement("input"); wid.className = "field"; wid.value = "35_9-1";
  const srcRow = document.createElement("div"); srcRow.className = "wf-row";
  srcRow.append(labelWrap("Well", wid), tag("gamma log"));
  src.body.appendChild(srcRow);
  flow.appendChild(src.node);
  flow.appendChild(wfConnector());

  // Chat node
  const chat = wfNode("Chat", "wf-chat");
  const instr = document.createElement("textarea"); instr.className = "ask-box field"; instr.rows = 2; instr.value = "plot the gamma log";
  const runBtn = document.createElement("button"); runBtn.className = "btn"; runBtn.textContent = "Run ▸";
  const runBar = document.createElement("div"); runBar.className = "ask-bar"; runBar.appendChild(runBtn);
  chat.body.append(instr, runBar);
  flow.appendChild(chat.node);
  flow.appendChild(wfConnector());

  // Outputs
  const outputs = document.createElement("div"); outputs.className = "wf-outputs";
  flow.appendChild(outputs);

  const run = async () => {
    runBtn.disabled = true;
    const pending = wfNode("Output · generating…", "wf-output");
    pending.body.appendChild(msg("Rendering the plot…"));
    outputs.appendChild(pending.node);
    try {
      const res = await fetch(apiUrl("/api/workflow/run"), {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ well_id: wid.value.trim(), kind: "log", instruction: instr.value.trim() }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.status);
      const d = await res.json();
      pending.node.remove();
      const out = wfNode("Output · " + d.title, "wf-output");
      const img = document.createElement("img"); img.className = "wf-img"; img.src = d.image; img.alt = d.title;
      out.body.appendChild(img);
      outputs.appendChild(out.node);
    } catch (e) {
      pending.body.replaceChildren(errorMsg("Could not run: " + e.message));
    } finally { runBtn.disabled = false; }
  };
  runBtn.addEventListener("click", run);
  run(); // seed the example output on open

  // ---- Compare wells side by side (#20, any curve #23) ----
  container.appendChild(sectionLabel("Compare wells side by side"));
  const cmp = document.createElement("div"); cmp.className = "wf";
  container.appendChild(cmp);

  const cnode = wfNode("Wells to compare", "wf-source");
  const wellsIn = document.createElement("input"); wellsIn.className = "field";
  wellsIn.placeholder = "well IDs, comma separated"; wellsIn.value = "31_2-1, 31_2-2, 31_2-3";
  const curveIn = document.createElement("input"); curveIn.className = "field";
  curveIn.placeholder = "gamma (default), or GR, DEN, RDEP, DT, NEU...";
  const cRow = document.createElement("div"); cRow.className = "wf-row";
  cRow.append(labelWrap("Wells", wellsIn), labelWrap("Curve", curveIn));
  cnode.body.appendChild(cRow);
  const cBtn = document.createElement("button"); cBtn.className = "btn"; cBtn.textContent = "Compare ▸";
  const cBar = document.createElement("div"); cBar.className = "ask-bar"; cBar.appendChild(cBtn);
  cnode.body.appendChild(cBar);
  cmp.appendChild(cnode.node);
  cmp.appendChild(wfConnector());
  const cOut = document.createElement("div"); cOut.className = "wf-outputs"; cmp.appendChild(cOut);

  const compare = async () => {
    cBtn.disabled = true;
    cOut.replaceChildren();
    const pending = wfNode("Comparing…", "wf-output");
    pending.body.appendChild(msg("Rendering the comparison…"));
    cOut.appendChild(pending.node);
    try {
      const q = new URLSearchParams({ wells: wellsIn.value.trim() });
      if (curveIn.value.trim()) q.set("mnemonic", curveIn.value.trim());
      const d = await fetchJSON("/api/compare?" + q.toString());
      pending.node.remove();
      const out = wfNode("Output · " + d.title, "wf-output");
      const img = document.createElement("img"); img.className = "wf-img"; img.src = d.image; img.alt = d.title;
      out.body.appendChild(img);
      const notes = [];
      if (d.skipped && d.skipped.length) notes.push("no " + d.curve + ": " + d.skipped.join(", "));
      if (d.missing && d.missing.length) notes.push("not found: " + d.missing.join(", "));
      if (notes.length) out.body.appendChild(msg(notes.join(" · ")));
      cOut.appendChild(out.node);
    } catch (e) {
      pending.body.replaceChildren(errorMsg("Could not compare: " + e.message));
    } finally { cBtn.disabled = false; }
  };
  cBtn.addEventListener("click", compare);

  // ---- Analyse a formation across wells (#24) ----
  container.appendChild(sectionLabel("Analyse a formation across wells"));
  const anz = document.createElement("div"); anz.className = "wf";
  container.appendChild(anz);

  const anode = wfNode("Formation analysis", "wf-source");
  const aWells = document.createElement("input"); aWells.className = "field";
  aWells.placeholder = "well IDs, comma separated"; aWells.value = "31_2-1, 31_3-2";
  const aForm = document.createElement("input"); aForm.className = "field";
  aForm.placeholder = "formation, e.g. BRENT GP";
  const aTop = document.createElement("input"); aTop.className = "field"; aTop.placeholder = "top m";
  const aBot = document.createElement("input"); aBot.className = "field"; aBot.placeholder = "bottom m";
  const aRow1 = document.createElement("div"); aRow1.className = "wf-row";
  aRow1.append(labelWrap("Wells", aWells), labelWrap("Formation", aForm));
  const aRow2 = document.createElement("div"); aRow2.className = "wf-row";
  aRow2.append(labelWrap("or depth", aTop), labelWrap("to", aBot));
  anode.body.append(aRow1, aRow2);
  const aBtn = document.createElement("button"); aBtn.className = "btn"; aBtn.textContent = "Analyse ▸";
  const aBar = document.createElement("div"); aBar.className = "ask-bar"; aBar.appendChild(aBtn);
  anode.body.appendChild(aBar);
  anz.appendChild(anode.node);
  anz.appendChild(wfConnector());
  const aOut = document.createElement("div"); aOut.className = "wf-outputs"; anz.appendChild(aOut);

  const analyse = async () => {
    aBtn.disabled = true;
    aOut.replaceChildren();
    const pending = wfNode("Analysing…", "wf-output");
    pending.body.appendChild(msg("Reading the logs and comparing…"));
    aOut.appendChild(pending.node);
    try {
      const q = new URLSearchParams({ wells: aWells.value.trim() });
      if (aForm.value.trim()) q.set("formation", aForm.value.trim());
      if (aTop.value.trim()) q.set("top", aTop.value.trim());
      if (aBot.value.trim()) q.set("bottom", aBot.value.trim());
      const d = await fetchJSON("/api/analyze?" + q.toString());
      pending.node.remove();
      const out = wfNode("Analysis · " + (d.target || "interval"), "wf-output");
      if (d.narrative) { const p = document.createElement("p"); p.className = "analysis-note"; p.textContent = d.narrative; out.body.appendChild(p); }
      out.body.appendChild(analysisTable(d.per_well));
      const notes = [];
      if (d.missing && d.missing.length) notes.push("no data/formation: " + d.missing.join(", "));
      if (d.not_found && d.not_found.length) notes.push("not found: " + d.not_found.join(", "));
      if (notes.length) out.body.appendChild(msg(notes.join(" · ")));
      aOut.appendChild(out.node);
    } catch (e) {
      pending.body.replaceChildren(errorMsg("Could not analyse: " + e.message));
    } finally { aBtn.disabled = false; }
  };
  aBtn.addEventListener("click", analyse);
}

const CURVE_ORDER = ["gamma", "density", "neutron", "sonic", "resistivity_deep", "resistivity_med"];
const CURVE_SHORT = { gamma: "gamma", density: "density", neutron: "neutron", sonic: "sonic", resistivity_deep: "res deep", resistivity_med: "res med" };

function analysisTable(perWell) {
  const table = document.createElement("table"); table.className = "wiki-table";
  const head = document.createElement("tr");
  ["well", "interval", ...CURVE_ORDER.map((c) => CURVE_SHORT[c])].forEach((h) => {
    const th = document.createElement("th"); th.textContent = h; head.appendChild(th);
  });
  table.appendChild(head);
  for (const w of perWell || []) {
    const tr = document.createElement("tr");
    const cells = [w.well_id, `${w.interval[0].toFixed(0)}-${w.interval[1].toFixed(0)} m`];
    CURVE_ORDER.forEach((c) => {
      const s = w.curves[c];
      cells.push(s ? `${s.mean} (${s.mnemonic})` : "-");
    });
    cells.forEach((v, i) => { const td = document.createElement(i ? "td" : "th"); td.textContent = v; tr.appendChild(td); });
    table.appendChild(tr);
  }
  return table;
}

function wfNode(title, cls) {
  const node = document.createElement("div");
  node.className = "wf-node " + cls;
  const head = document.createElement("div"); head.className = "wf-node-title"; head.textContent = title;
  const body = document.createElement("div"); body.className = "wf-node-body";
  node.append(head, body);
  return { node, body };
}
function wfConnector() { const c = document.createElement("div"); c.className = "wf-connector"; c.textContent = "▼"; return c; }
function labelWrap(text, input) { const l = document.createElement("label"); l.className = "wf-field"; l.append(text + " ", input); return l; }
function tag(t) { const s = document.createElement("span"); s.className = "wf-tag"; s.textContent = t; return s; }

async function showCorpus() {
  ACTIVE = null;
  clearMap();
  renderRail($("#filter").value.trim().toLowerCase());
  $("#empty").hidden = true;
  const panel = $("#well");
  panel.hidden = false;
  panel.scrollTop = 0;
  panel.replaceChildren(loadingMsg());
  try {
    renderCorpusPanel(panel, await fetchJSON("/api/corpus"));
  } catch (e) {
    panel.replaceChildren(errorMsg("Could not load the corpus overview."));
  }
}

function renderCorpusPanel(container, stats) {
  container.replaceChildren();
  setStatus("Corpus overview", `${stats.n_wells} wells`);

  const head = document.createElement("div");
  head.className = "well-head";
  head.innerHTML = `<h2>DISKOS corpus</h2><span class="well-sub">${stats.n_wells} wells</span>`;
  container.appendChild(head);

  container.appendChild(sectionLabel("Data coverage (wells with each type)"));
  const tiles = document.createElement("div");
  tiles.className = "tiles";
  const cov = { ...stats.coverage, biostrat: stats.biostrat, core: stats.core };
  for (const [t, n] of Object.entries(cov)) {
    if (!n) continue;
    const tile = document.createElement("div");
    tile.className = "tile";
    tile.innerHTML = `<div class="tile-n">${n}</div><div class="tile-t">${TYPE_LABEL[t] || t}</div><div class="tile-pct">${Math.round((n / stats.n_wells) * 100)}%</div>`;
    tiles.appendChild(tile);
  }
  container.appendChild(tiles);

  // Finder
  container.appendChild(sectionLabel("Find wells"));
  const finder = document.createElement("div");
  finder.className = "finder";
  const typeSel = document.createElement("select");
  typeSel.className = "field";
  typeSel.innerHTML = `<option value="">any type</option>` + Object.keys(stats.coverage).map((t) => `<option value="${t}">${TYPE_LABEL[t] || t}</option>`).join("");
  const quad = document.createElement("input");
  quad.className = "field finder-q";
  quad.placeholder = "quadrant (e.g. 35)";
  const bioLbl = document.createElement("label"); const bio = document.createElement("input"); bio.type = "checkbox"; bioLbl.append(bio, document.createTextNode(" biostrat"));
  const coreLbl = document.createElement("label"); const core = document.createElement("input"); core.type = "checkbox"; coreLbl.append(core, document.createTextNode(" core"));
  const findBtn = document.createElement("button"); findBtn.className = "btn"; findBtn.textContent = "Find";
  finder.append(typeSel, quad, bioLbl, coreLbl, findBtn);
  container.appendChild(finder);
  const results = document.createElement("div"); results.className = "finder-results"; container.appendChild(results);

  const doFind = async () => {
    const params = new URLSearchParams();
    if (typeSel.value) params.set("type", typeSel.value);
    if (quad.value.trim()) params.set("quadrant", quad.value.trim());
    if (bio.checked) params.set("biostrat", "true");
    if (core.checked) params.set("core", "true");
    results.replaceChildren(loadingMsg());
    try {
      const d = await fetchJSON("/api/corpus/find?" + params.toString());
      results.replaceChildren(sectionLabel(`${d.count} well${d.count === 1 ? "" : "s"}`));
      const ul = document.createElement("ul"); ul.className = "filelist";
      for (const w of d.wells) {
        const li = document.createElement("li");
        const a = document.createElement("a"); a.className = "filelink"; a.href = "#"; a.textContent = w.well_id;
        a.addEventListener("click", (e) => { e.preventDefault(); selectWell(w.well_id); });
        const meta = document.createElement("span"); meta.className = "finder-meta";
        meta.textContent = w.types.join(", ") + (w.biostrat ? " · biostrat" : "") + (w.core ? " · core" : "");
        li.append(a, meta);
        ul.appendChild(li);
      }
      results.appendChild(ul);
    } catch (e) { results.replaceChildren(errorMsg("Find failed.")); }
  };
  findBtn.addEventListener("click", doFind);

  // Cross-well ask
  container.appendChild(sectionLabel("Ask across the corpus"));
  const box = document.createElement("textarea");
  box.className = "ask-box field"; box.rows = 2;
  box.placeholder = "e.g. how much of the archive has biostratigraphy reports?";
  container.appendChild(box);
  const abar = document.createElement("div"); abar.className = "ask-bar";
  const abtn = document.createElement("button"); abtn.className = "btn"; abtn.textContent = "Ask";
  abar.appendChild(abtn); container.appendChild(abar);
  const aout = document.createElement("div"); aout.className = "answer"; container.appendChild(aout);
  const ask = async () => {
    const q = box.value.trim(); if (!q) return;
    aout.replaceChildren(msg("Thinking…")); abtn.disabled = true;
    try {
      const res = await fetch(apiUrl("/api/corpus/ask"), { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.status);
      const d = await res.json();
      const t = document.createElement("div"); t.className = "answer-text"; t.textContent = d.answer;
      aout.replaceChildren(t);
    } catch (e) { aout.replaceChildren(errorMsg("Assistant unavailable: " + e.message)); }
    finally { abtn.disabled = false; }
  };
  abtn.addEventListener("click", ask);
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
  clearMap();
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
  setStatus(`Well: ${detail.well_id}`, `${total} file${total === 1 ? "" : "s"}`);

  if (!total) { panel.appendChild(msg("No data files for this well.")); return; }

  const id = detail.well_id;
  const tabs = [];
  tabs.push({ label: "Wiki", load: () => fetchJSON(`/api/wells/${encodeURIComponent(id)}/wiki`), render: renderWikiPanel });
  tabs.push({ label: "Assistant", render: (c) => renderAssistantPanel(c, detail) });
  if (detail.counts.logs) tabs.push({ label: "Well logs", render: (c) => renderLogsPanel(c, id) });
  if (detail.counts.geology) tabs.push({ label: "Graph", load: () => fetchJSON(`/api/wells/${encodeURIComponent(id)}/graph`), render: renderGraphPanel });
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

function renderWikiPanel(container, data) {
  if (!data.exists) {
    container.appendChild(msg(data.detail || "No wiki page yet for this borehole."));
    return;
  }
  const wrap = document.createElement("div");
  wrap.className = "wiki";
  renderMarkdown(wrap, data.markdown);
  container.appendChild(wrap);
}

// Minimal, dependency-free markdown -> DOM for the known wiki page shape.
function renderMarkdown(root, md) {
  const lines = md.split("\n");
  let i = 0;
  // Skip YAML front matter.
  if (lines[0] === "---") { i = 1; while (i < lines.length && lines[i] !== "---") i++; i++; }
  let list = null, table = null;
  const flush = () => { list = null; table = null; };
  for (; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("## ")) { flush(); const h = document.createElement("h4"); h.textContent = line.slice(3); root.appendChild(h); continue; }
    if (line.startsWith("# ")) { flush(); const h = document.createElement("h3"); h.textContent = line.slice(2); root.appendChild(h); continue; }
    if (line.startsWith("|")) {
      const cells = line.split("|").slice(1, -1).map((c) => c.trim());
      if (cells.every((c) => /^-+$/.test(c))) continue; // separator row
      if (!table) { table = document.createElement("table"); table.className = "wiki-table"; root.appendChild(table); }
      const tr = document.createElement("tr");
      cells.forEach((c) => { const td = document.createElement(table.rows.length ? "td" : "th"); inlineInto(td, c); tr.appendChild(td); });
      table.appendChild(tr);
      continue;
    }
    if (line.startsWith("- ")) {
      if (!list) { list = document.createElement("ul"); list.className = "wiki-list"; root.appendChild(list); }
      const li = document.createElement("li"); inlineInto(li, line.slice(2)); list.appendChild(li);
      continue;
    }
    if (line.trim() === "") { flush(); continue; }
    flush();
    const p = document.createElement("p"); inlineInto(p, line); root.appendChild(p);
  }
}

// Inline: **bold**, `code`, and [[wikilinks]] (well_/field_ links are clickable).
function inlineInto(el, text) {
  const re = /\[\[([^\]]+)\]\]|\*\*([^*]+)\*\*|`([^`]+)`/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) el.appendChild(document.createTextNode(text.slice(last, m.index)));
    if (m[1] != null) {
      const target = m[1];
      const wellMatch = target.match(/^well_(.+)$/);
      if (wellMatch) {
        const a = document.createElement("a"); a.href = "#"; a.className = "wikilink"; a.textContent = wellMatch[1];
        a.addEventListener("click", (e) => { e.preventDefault(); selectWell(wellMatch[1]); });
        el.appendChild(a);
      } else {
        const s = document.createElement("span"); s.className = "wikilink"; s.textContent = target.replace(/^field_/, ""); el.appendChild(s);
      }
    } else if (m[2] != null) { const b = document.createElement("strong"); b.textContent = m[2]; el.appendChild(b); }
    else { const c = document.createElement("code"); c.textContent = m[3]; el.appendChild(c); }
    last = re.lastIndex;
  }
  if (last < text.length) el.appendChild(document.createTextNode(text.slice(last)));
}

function suggestionsFor(counts) {
  const s = [];
  if (counts.geology) s.push("Summarize the biostratigraphy of this well.", "What ages or biozones are identified, and at what depths?");
  if (counts.logs) s.push("Describe the gamma log character with depth.", "What log curves are available and over what depth range?");
  if (counts.seismic) s.push("What seismic or checkshot data does this well have?");
  s.push("What data does this well have?");
  return s.slice(0, 4);
}

function renderAssistantPanel(container, detail) {
  const id = detail.well_id;
  const counts = detail.counts || {};

  const intro = document.createElement("p");
  intro.className = "assistant-intro";
  intro.textContent =
    "Ask about this well. The local model answers from this well's own context: "
    + "its file inventory, log curves, and (where present) geology/biostratigraphy reports.";
  container.appendChild(intro);

  const chips = document.createElement("div");
  chips.className = "chips";
  for (const s of suggestionsFor(counts)) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = s;
    chip.addEventListener("click", () => { box.value = s; run(); });
    chips.appendChild(chip);
  }
  container.appendChild(chips);

  const box = document.createElement("textarea");
  box.className = "ask-box field";
  box.rows = 3;
  box.placeholder = "Ask a question about " + id + "...";
  container.appendChild(box);

  const bar = document.createElement("div");
  bar.className = "ask-bar";
  const btn = document.createElement("button");
  btn.className = "btn";
  btn.textContent = "Ask";
  bar.appendChild(btn);
  container.appendChild(bar);

  const out = document.createElement("div");
  out.className = "answer";
  container.appendChild(out);

  const run = async () => {
    const q = box.value.trim();
    if (!q) return;
    out.className = "answer";
    out.replaceChildren(msg("Thinking… (the local model can take a moment)"));
    btn.disabled = true;
    try {
      const res = await fetch(apiUrl(`/api/wells/${encodeURIComponent(id)}/ask`), {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.status);
      const data = await res.json();
      out.replaceChildren();
      const ans = document.createElement("div");
      ans.className = "answer-text";
      ans.textContent = data.answer;
      out.appendChild(ans);
      if (data.sources && data.sources.length) {
        const src = document.createElement("p");
        src.className = "answer-sources";
        src.textContent = "Sources: " + data.sources.join(", ");
        out.appendChild(src);
      }
    } catch (e) {
      out.replaceChildren(errorMsg("Assistant unavailable: " + e.message));
    } finally {
      btn.disabled = false;
    }
  };
  btn.addEventListener("click", run);
  box.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run(); });
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
    for (const f of files) {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.className = "filelink";
      a.href = apiUrl(`/api/wells/${encodeURIComponent(detail.well_id)}/file?path=${encodeURIComponent(f.rel)}`);
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = f.name;
      li.appendChild(a);
      if (biostrat.has(f.name)) {
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
  note.textContent = "Click a file to open it (PDFs and images view in a new tab). Logs are charted in the Well logs tab.";
  container.appendChild(note);
}

function renderGraphPanel(container, data) {
  const reports = data.nodes.filter((n) => n.kind === "report");
  const dataNodes = data.nodes.filter((n) => n.kind !== "report");
  if (!reports.length) { container.appendChild(msg("No reports to graph for this well.")); return; }

  container.appendChild(sectionLabel("Report ↔ data connections (click a node to focus its links)"));
  const wrap = document.createElement("div");
  wrap.className = "graph-wrap";
  container.appendChild(wrap);

  const W = 760, colL = 24, colR = 470, boxW = 286, boxH = 30, vgap = 12, top = 16;
  const rows = Math.max(reports.length, dataNodes.length);
  const H = top * 2 + rows * (boxH + vgap);
  const svg = el("svg", { class: "graph", viewBox: `0 0 ${W} ${H}` });
  const edgeG = el("g", {});
  svg.appendChild(edgeG);

  const yOf = (i, n) => top + i * (boxH + vgap) + ((rows - n) * (boxH + vgap)) / 2;
  const pos = {};
  reports.forEach((n, i) => { const y = yOf(i, reports.length); pos[n.id] = { y }; svg.appendChild(graphNode(n, colL, y, boxW, boxH, "report")); });
  dataNodes.forEach((n, i) => { const y = yOf(i, dataNodes.length); pos[n.id] = { y }; svg.appendChild(graphNode(n, colR, y, boxW, boxH, n.kind)); });

  const adj = {};
  for (const e of data.edges) {
    const a = pos[e.source], b = pos[e.target];
    if (!a || !b) continue;
    const line = el("line", { class: "gedge", x1: colL + boxW, y1: a.y + boxH / 2, x2: colR, y2: b.y + boxH / 2, "data-s": e.source, "data-t": e.target });
    const t = el("title", {}); t.textContent = e.reason; line.appendChild(t);
    edgeG.appendChild(line);
    (adj[e.source] = adj[e.source] || new Set()).add(e.target);
    (adj[e.target] = adj[e.target] || new Set()).add(e.source);
  }
  wrap.appendChild(svg);

  const focus = (id) => {
    const keep = new Set([id, ...(adj[id] || [])]);
    svg.querySelectorAll(".gnode").forEach((g) => { g.classList.toggle("dim", !keep.has(g.getAttribute("data-id"))); g.classList.toggle("on", g.getAttribute("data-id") === id); });
    edgeG.querySelectorAll(".gedge").forEach((l) => { const hit = l.getAttribute("data-s") === id || l.getAttribute("data-t") === id; l.classList.toggle("on", hit); l.classList.toggle("dim", !hit); });
  };
  const reset = () => svg.querySelectorAll(".gnode,.gedge").forEach((x) => x.classList.remove("dim", "on"));
  svg.addEventListener("click", (e) => { const g = e.target.closest(".gnode"); if (g) focus(g.getAttribute("data-id")); else reset(); });

  const linked = reports.filter((r) => adj[r.id]).length;
  const note = document.createElement("p");
  note.className = "msg";
  note.textContent = `${reports.length} report(s), ${dataNodes.length} data file(s), ${data.edges.length} connection(s). `
    + `${linked}/${reports.length} reports linked by depth/sample; unlinked reports are scanned or name no interval.`;
  container.appendChild(note);
}

function graphNode(n, x, y, w, h, kind) {
  const g = el("g", { class: `gnode gnode-${kind}` + (n.biostrat ? " gnode-biostrat" : "") });
  g.setAttribute("data-id", n.id);
  g.appendChild(el("rect", { x, y, width: w, height: h }));
  const label = n.label.length > 38 ? n.label.slice(0, 36) + "…" : n.label;
  g.appendChild(text(x + 8, y + h / 2 + 4, label, { class: "gnode-label" }));
  const tt = el("title", {});
  tt.textContent = n.label + (n.interval ? ` (${n.interval[0]}-${n.interval[1]} m)` : "") + (n.range ? ` (${Math.round(n.range[0])}-${Math.round(n.range[1])} m)` : "");
  g.appendChild(tt);
  return g;
}

async function renderLogsPanel(container, wellId) {
  container.replaceChildren(loadingMsg());
  let data;
  try {
    data = await fetchJSON(`/api/wells/${encodeURIComponent(wellId)}/logs`);
  } catch (e) {
    container.replaceChildren(errorMsg("Could not load this well's logs."));
    return;
  }
  container.replaceChildren();

  // Curve picker: any mnemonic present in the well, defaulting to gamma (#23).
  const mnems = [...new Set((data.files || []).flatMap((f) => f.mnemonics || []))];
  const gamma = (data.files || []).map((f) => f.gamma).find(Boolean);
  const bar = document.createElement("div"); bar.className = "ask-bar";
  const sel = document.createElement("select"); sel.className = "field";
  for (const mn of mnems) {
    const o = document.createElement("option"); o.value = mn; o.textContent = mn;
    if (mn === gamma) o.selected = true;
    sel.appendChild(o);
  }
  bar.appendChild(labelWrap("Curve", sel));
  container.appendChild(bar);

  const plots = document.createElement("div");
  container.appendChild(plots);

  const draw = (d) => {
    const files = (d.files || []).filter((f) => f.tracks && f.tracks.length);
    if (!files.length) { plots.replaceChildren(msg("No readable data for this curve.")); return; }
    plots.replaceChildren();
    for (const file of files) {
      const mn = file.tracks.map((t) => t.mnemonic).join(", ");
      plots.appendChild(sectionLabel(`${file.file} · ${mn}`));
      for (const track of file.tracks) plots.appendChild(buildLogCard(track));
    }
  };
  draw(data);

  sel.addEventListener("change", async () => {
    plots.replaceChildren(loadingMsg());
    try {
      draw(await fetchJSON(`/api/wells/${encodeURIComponent(wellId)}/logs?mnemonic=${encodeURIComponent(sel.value)}`));
    } catch (e) {
      plots.replaceChildren(errorMsg("Could not load that curve."));
    }
  });
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
