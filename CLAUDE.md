# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Most of the roadmap is built. The repo is a `uv`-managed Python package (`diskos`, src layout). Working and tested: palynology pipeline (parse -> reconcile -> wide CSV), human-in-the-loop name reconciliation + target suggestions, palynology plots, well-log (LAS) tracks, the model layer, a FastAPI web backend with live Google-OAuth/allowlist auth (deployed at johnspace.xyz/diskos-explorer), and local BM25 wiki search. The **LLM wiki over the whole archive is built** (identity resolution via the Sodir/NPD register, borehole grouping + dedup, per-borehole and per-field pages authored by local Ollama models, resumable); see "Borehole identity and the LLM wiki" below. XRF is ported but its PyMca fit path is unverified. Jack's four notebooks are refactored reference under `notebooks/`. Not yet done: OCR for scanned reports, a map view, and qmd/local-search-agent integration. Always use `uv`, never `pip` or bare `python`.

## Commands

```bash
uv sync                                  # install deps + the package
uv run pytest -q                         # run tests (uses tests/data sample, no SSH)
uv run pytest tests/test_stratabugs.py::test_aggregate_sums_counts_regression  # single test
uv run diskos wells                      # print the discovered borehole catalog
uv run diskos stratabugs --all --out out/         # palynology pipeline, all wells
uv run diskos stratabugs --well 7_11-1 --out out/ # one well
uv run diskos taxa suggest --all         # suggest target species from the data
uv run diskos taxa review                # similar names awaiting a same/different call
uv run diskos taxa decide "<target>" "<variant>" same   # record a decision
uv run diskos plot --in out/ --out out/palyno.png       # species-vs-depth figure
uv run diskos logs --well 7_11-1 --out out/logs.png     # gamma/log tracks (LAS)
uv run diskos wiki ingest --in out/ --wiki wiki/         # per-well palynology CSV -> wiki
uv run diskos wiki search "Apectodinium" --wiki wiki/    # local BM25 search
uv run diskos npd fetch                                  # cache the Sodir/NPD wellbore register
uv run diskos boreholes                                  # dirs -> physical boreholes + coverage
uv run diskos wiki build --field 31_2 --wiki wiki/       # LLM wiki over a block (pilot)
uv run diskos wiki build --all --wiki wiki/              # whole-archive sweep (resumable)
uv run diskos wiki build --well 1_3-10 --no-model        # one borehole, deterministic only
DISKOS_WEB_DEV=1 uv run diskos serve     # web API (needs `web` extra)
# Point at a sample tree without editing config:
DISKOS_ROOT=./tests/data/diskos_sample uv run diskos stratabugs --all --out out/
```

Optional dependency groups (kept out of the core install): `plot`, `welllog`,
`llm`, `web`, `xrf`. matplotlib/openpyxl/lasio and the web+test deps are in the
dev group so `uv run pytest` is self-contained.

## Architecture

Layered, lower never imports upper: `io/` (raw parsers) → `palyno`/`welllog`/`xrf` (analysis) → `llm/` (model access) → `wiki/` (knowledge ops) → `web/` (delivery). Two cross-cutting rules:

- **`paths.py` is the only module that knows where DISKOS data lives** (resolves `DISKOS_ROOT` env, then `config.toml` `[paths].prefer`). Every parser takes an explicit path; no `os.chdir`, no hardcoded well paths (unlike the notebooks).
- **`wells.py` models the real DISKOS archive** (confirmed on lambda-scalar): one top-level directory per well (2700+, Norwegian `35_10-8_S` and named Danish `ADDA-1`), each foldered by category (`LOGS`, `WELL_PATH`, `WELL_SEISMIC`, `GEOLOGY`, `DRILLING`, `Reports`...). Well ID = directory name; a file's data type comes from `classify(rel_dir, name)` (category subdir + extension), not a filename regex. Because there are thousands of wells, `list_well_ids` is cheap (top-level only) and `well_files` recurses one well on demand. Buckets: logs, seismic, deviation, geology, images, geochem, core, other.

Reality check baked into the code: **`.ASC` in the mirror is a Tigress export (well path / checkshot), not StrataBugs palynology**, and palynology exists only as biostrat PDFs. So the StrataBugs pipeline (parse/reconcile/aggregate/plot) is a **curated bring-your-own import** (`diskos stratabugs --in <dir>` over a folder of `.ASC` exports), decoupled from the mirror catalog. Extracting palynology from the biostrat PDFs is a planned wiki/LLM feature.

The palynology pipeline (`io/stratabugs.py` parse → `palyno/reconcile.py` match names → `palyno/aggregate.py` wide depth×species CSV) is the model for later data types: parse raw → reconcile → emit clean, wiki-ingestible artifacts to `out/`, not just figures. Two bugs from the notebook are fixed here and guarded by regression tests: the parenthesis-stripping regex in `normalize_taxon_name_for_columns`, and count aggregation (now summed per depth, was `.first()`).

Name reconciliation is human-in-the-loop by design (Jack's calls): an **exact** genus+species match auto-merges (author/year ignored), but a merely **similar** name (spelling near-miss) is held apart and never silently merged. It goes to a same/different decision persisted in `taxon_decisions.csv` (`reconcile.Decisions`, path from config) and reused everywhere. The `diskos taxa review`/`decide` commands drive this from the CLI now; the web app will drive the same decision store later. Target species are not a fixed list to hand-maintain: `palyno/suggest.py` ranks candidate targets by prevalence in the selected wells (`diskos taxa suggest`) so Jack picks from what is actually there (a richer LLM-based biostrat suggestion can come with the model layer). `palyno/targets.py` holds the current default picks; `palyno/taxa.py` keeps the lower-level `fuzzy_match_taxa` helper.

Model/compute access is config-driven and swappable 3 ways (lambda-scalar Ollama for serving Jack, Modal for burst GPU, a cloud Claude model for wiki authoring) via profiles in `config.toml`; secrets stay in a gitignored `.env` referenced by env-var name. The web front end (Phase 5) will gate everything behind Google OAuth + an email allowlist.

**Borehole identity and the LLM wiki (the actual deliverable #1).** Above `wells.py` sits an identity + location layer that turns the flat directory catalog into physical boreholes. `npd.py` fetches the public Sodir/NPD FactPages wellbore register (cached CSVs, `diskos npd fetch`) and joins by normalizing the wellbore name to the directory form (`34/8-14 A` -> `34_8-14_A`); it supplies authoritative decimal-degree WGS84 lat/lon, field, and the parent-well↔sidetrack mapping. `boreholes.py` uses that (heuristic suffix-strip as fallback) to `group_boreholes`: it collapses sidetracks into one `BoreholeGroup`, resolves its location (NPD, else LAS header via `io/las.read_las_header` + `geo.parse_dms`), and dedupes the archive's byte-identical double-named exports. `wiki/dossier.py::build_dossier` compiles one borehole's model-free facts (identity, location, deduped inventory, log curves + gamma, report presence + studied intervals, palynology, nearest neighbours); `wiki/build.py::build_wiki` renders an IODP-style page per borehole (`wiki/ingest.render_borehole_page`) and a synthesized page per area (NPD field, else block), authored by the `wiki-well` (qwen2.5:32b) and `wiki-field` (llama3.3:70b) local profiles. The deterministic dossier is the unit of work and the page renders without a model, so a better model can re-run over the same dossiers later; per-borehole ingest is resumable via a `dossier_hash` in the page front matter. **Absence is always stated as "not in the mirror," never "does not exist"** (the mirror is a partial, growing Halliburton download). The web app surfaces pages via `/api/wells/{id}/wiki`, `/api/fields/{name}/wiki`, and `/api/wiki/search`, with a Wiki tab in the SPA.

## What this project is

`diskosAI` is a set of tools for working with data pulled from the Norwegian DISKOS petroleum database (mirrored on the UiO geo server `morgoth`). The four intended deliverables, in the owner's priority order:

1. **An LLM Wiki agent** that builds and maintains a persistent, interlinked understanding of the underlying data (see "LLM Wiki pattern" below).
2. **A data explorer app** to view maps of the data, images of microscope/palynological samples, plot variables against each other, and run general investigations.
3. **A local search agent** over all the files.
4. Integration of a local-search tool (reference: https://github.com/wiss84/local-search-agent).

**Delivery surface: a web front end.** The intended way to get these features in front of Jack (a domain user, not a developer) is a web app. It should let him interact with the data directly (maps, plots, imagery, search) and also be the place where the AI products we build (the wiki agent, question-answering over the data, and future tools) are exposed for him to use. Think of the explorer (#2) and search (#3) as views inside this app, and the wiki agent (#1) as an assistant surfaced within it. This is a vision note, not a chosen stack; pick the framework when the first real feature is ready to ship.

## Data access

The DISKOS data is **not in this repo**. It lives on a separate machine:

- Path: `//lambda-scalar/home/mnky9800n/data/DISKOS`
- Access: SSH to `lambda-scalar` first. The data is too large to live in-repo; treat it as an immutable external source of truth.
- Format note: many boreholes have data in **ASCII** files, readable directly from a Jupyter notebook. Jack has an existing notebook for finding files containing species of interest and plotting them; ask for it before rebuilding that from scratch.

## Domain context

The target user correlates boreholes using two main data types. The explorer and wiki should support these specific analysis workflows.

**Palynology (fossils / micro-fossils).** Plot species against depth and look at where a species first occurs, peaks in abundance, or disappears (these events correlate boreholes because species occur in short, specific time windows). Practical caveats: you need a prior idea of which species are important or indicative of what you care about, and results depend on how sampling was done, so trust in the data is not uniform. Watch for and surface these sampling/confidence issues rather than treating counts as ground truth.

**Gamma and downhole geophysics.** Indicate lithology and variation (sand / clay / gravel / lavas). The key workflow: match gamma against **logged drill-core sections**, which are ground truth (you know exactly what is in the core), then use that calibration to link gamma to seismic and up to basin scale. Crucially, **almost all boreholes have gamma but only a handful have drill core**, so confidently linking gamma to core lets gamma be trusted where no core exists. In industry this is done in Petrel alongside seismic; here the user plots in Python.

Borehole-collapse data also exists but is used less. Other data types are not yet catalogued; expect to discover more.

## LLM Wiki pattern

The core deliverable (#1) follows the "LLM Wiki" pattern described in `projectNotes.md`. Key principles when this layer gets built:

- **Three layers**: immutable raw sources (the DISKOS data, never modified); the wiki (a directory of LLM-generated, interlinked markdown that the LLM owns and maintains entirely); and the schema (this CLAUDE.md, encoding conventions and workflows, co-evolved over time).
- **Compound, don't re-derive**: on ingest, read a source, extract key info, and integrate it across existing pages (entity pages, topic summaries, contradiction flags), touching many pages in one pass. Do not treat it as query-time RAG that rediscovers everything each question.
- **index.md** (content catalog, one line per page, updated every ingest) and **log.md** (append-only chronological record; prefix entries like `## [YYYY-MM-DD] ingest | Title` so `grep "^## \[" log.md` works) are the navigation aids.
- **File good answers back into the wiki** as new pages rather than letting analysis disappear into chat history.
- **Lint** periodically: find contradictions, stale claims, orphan pages, missing cross-references, and data gaps.

Read `projectNotes.md` in full before building the wiki layer; it is the source spec. As conventions solidify (directory layout, page formats, ingest/query/lint workflows), document them in this file.

## Writing style

Do not use em dashes in any prose or generated wiki content; use commas, parentheses, colons, or separate sentences instead.
