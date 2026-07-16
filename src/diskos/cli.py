"""Command-line entrypoints for diskosAI.

    diskos wells [--detail]          -- list discovered wells (2700+ in the archive)
    diskos well <id>                 -- one well's files by data type
    diskos logs --well ID | --all    -- plot gamma/log tracks from LAS
    diskos stratabugs --in DIR       -- curated StrataBugs .ASC -> per-well CSV
    diskos taxa suggest --in DIR     -- suggest target species from curated .ASC
    diskos taxa review --in DIR      -- similar names awaiting a same/different call
    diskos taxa decide T V same|different
    diskos wiki ingest|search        -- knowledge-base operations
    diskos serve                     -- run the web API

The DISKOS mirror is one directory per well, classified by data type. Curated
StrataBugs palynology is a separate bring-your-own input (``--in`` a folder of
``.ASC`` exports), since the raw mirror stores palynology only as biostrat PDFs.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import wells as wells_mod
from .config import load_config
from .io.stratabugs import parse_stratabugs_simple
from .palyno import reconcile
from .palyno.aggregate import create_wide_format
from .palyno.suggest import suggest_targets
from .palyno.targets import TARGETS
from .paths import diskos_root

app = typer.Typer(help="Tools for exploring DISKOS petroleum borehole data.", no_args_is_help=True)
taxa_app = typer.Typer(help="Target species: suggest, review similar names, record decisions.", no_args_is_help=True)
app.add_typer(taxa_app, name="taxa")
wiki_app = typer.Typer(help="Wiki: ingest pipeline artifacts into the knowledge base.", no_args_is_help=True)
app.add_typer(wiki_app, name="wiki")
npd_app = typer.Typer(help="NPD/Sodir FactPages: fetch the authoritative wellbore register.", no_args_is_help=True)
app.add_typer(npd_app, name="npd")

CURATED_DEFAULT = Path("data/palynology")


def _curated_ascs(in_dir: Path) -> list[Path]:
    """Curated StrataBugs .ASC exports in a directory."""
    return sorted(p for p in in_dir.glob("*") if p.suffix.lower() == ".asc")


@app.command()
def wells(detail: bool = typer.Option(False, "--detail", help="Recurse each well for data-type counts (slow on the full archive).")) -> None:
    """List discovered wells (well = top-level directory)."""
    root = diskos_root(load_config())
    ids = wells_mod.list_well_ids(root)
    typer.echo(f"{len(ids)} wells discovered under {root}\n")
    if detail:
        for wid in ids:
            counts = wells_mod.well_files(root, wid).counts()
            typer.echo(f"  {wid:<18} " + " ".join(f"{t}={n}" for t, n in counts.items()))
        return
    for wid in ids[:40]:
        typer.echo(f"  {wid}")
    if len(ids) > 40:
        typer.echo(f"  ... and {len(ids) - 40} more (use `diskos well <id>`)")


@app.command()
def well(well_id: str = typer.Argument(..., help="Well ID, e.g. 35_10-8_S.")) -> None:
    """Show one well's files grouped by data type."""
    root = diskos_root(load_config())
    if well_id not in wells_mod.list_well_ids(root):
        typer.echo(f"Well {well_id!r} not found under {root}.", err=True)
        raise typer.Exit(code=1)
    w = wells_mod.well_files(root, well_id)
    typer.echo(f"{well_id}: {w.total()} files")
    for data_type, paths in w.files.items():
        typer.echo(f"  {data_type} ({len(paths)})")
        for p in paths[:8]:
            typer.echo(f"    {p.name}")
        if len(paths) > 8:
            typer.echo(f"    ... {len(paths) - 8} more")


@app.command()
def logs(
    well: str = typer.Option(None, "--well", help="Plot one borehole by ID."),
    all_wells: bool = typer.Option(False, "--all", help="Plot every borehole with logs."),
    mnemonic: str = typer.Option(None, "--mnemonic", help="Curve mnemonic (default: gamma)."),
    top: float = typer.Option(None, "--top", help="Top depth (m)."),
    bottom: float = typer.Option(None, "--bottom", help="Bottom depth (m)."),
    out_path: Path = typer.Option(Path("out/logs.png"), "--out", help="Output figure path."),
) -> None:
    """Plot gamma (or a chosen curve) as depth-aligned color tracks for correlation."""
    from .welllog import curves as wl_curves
    from .welllog import plot as wl_plot

    root = diskos_root(load_config())
    if well:
        well_ids = [well]
    elif all_wells:
        well_ids = wells_mod.list_well_ids(root)
    else:
        typer.echo("Specify --well <id> or --all.", err=True)
        raise typer.Exit(code=1)

    tracks = {}
    for well_id in well_ids:
        try:
            w = wells_mod.well_files(root, well_id)
        except KeyError:
            continue
        las_files = w.files.get("logs", [])
        if not las_files:
            continue
        df = wl_curves.read_las(las_files[0])
        try:
            name = mnemonic or wl_curves.gamma_column(df)
        except KeyError:
            continue
        tracks[f"{well_id}:{name}"] = wl_curves.slice_depth(wl_curves.curve_series(df, name), top, bottom)

    if not tracks:
        typer.echo("No wells with logs in the selection.", err=True)
        raise typer.Exit(code=1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wl_plot.plot_correlation(tracks, out_path=out_path)
    typer.echo(f"Wrote {out_path} ({len(tracks)} track(s))")


@app.command()
def stratabugs(
    in_dir: Path = typer.Option(CURATED_DEFAULT, "--in", help="Directory of curated StrataBugs .ASC exports."),
    targets: str = typer.Option(None, "--targets", help="Comma-separated target taxa (default: built-in TARGETS)."),
    out: Path = typer.Option(Path("out"), "--out", help="Output directory for per-well CSVs."),
) -> None:
    """Curated StrataBugs .ASC -> reconcile target taxa -> wide CSV per file.

    Exact genus+species names merge automatically; only similar names with a
    recorded same/different decision are merged (run `diskos taxa review`).
    """
    cfg = load_config()
    target_list = [t.strip() for t in targets.split(",")] if targets else TARGETS
    decisions = reconcile.Decisions.load(cfg.decisions_path())

    ascs = _curated_ascs(in_dir)
    if not ascs:
        typer.echo(f"No .ASC files in {in_dir}.", err=True)
        raise typer.Exit(code=1)
    out.mkdir(parents=True, exist_ok=True)

    written = 0
    pending: dict[tuple[str, str], float] = {}
    for asc_path in ascs:
        obs = parse_stratabugs_simple(asc_path)["observations"]
        if obs.empty:
            typer.echo(f"  {asc_path.name}: no observations, skipped")
            continue
        available = sorted(obs["taxon_name"].dropna().unique().tolist())
        result = reconcile.resolve_matches(target_list, available, decisions)
        for pair in result.pending:
            pending[(pair.target, pair.variant)] = pair.similarity
        wide = create_wide_format(obs, result.mapping)
        if wide.empty or wide.shape[1] == 0:
            typer.echo(f"  {asc_path.name}: no target matches, skipped")
            continue
        out_path = out / f"{asc_path.stem}.csv"
        wide.to_csv(out_path, index=True)
        typer.echo(f"  {asc_path.name} -> {out_path} ({wide.shape[0]} depths, {wide.shape[1]} cols)")
        written += 1

    typer.echo(f"\nWrote {written} CSV file(s) to {out}")
    if pending:
        typer.echo(f"{len(pending)} similar name(s) need a same/different decision. Run `diskos taxa review`.")


@app.command()
def plot(
    in_dir: Path = typer.Option(Path("out"), "--in", help="Directory of per-well CSVs (from stratabugs)."),
    out_path: Path = typer.Option(Path("out/palyno.png"), "--out", help="Output figure path."),
    tops: Path = typer.Option(None, "--tops", help="Optional formation-tops .xlsx for shading."),
) -> None:
    """Plot species-vs-depth for every per-well CSV in a directory (one figure)."""
    import pandas as pd

    from .palyno import plot as palyno_plot

    csvs = sorted(in_dir.glob("*.csv"))
    if not csvs:
        typer.echo(f"No CSVs found in {in_dir}. Run `diskos stratabugs` first.", err=True)
        raise typer.Exit(code=1)

    frames = {p.name: pd.read_csv(p) for p in csvs}
    tops_df = palyno_plot.load_formation_tops(tops) if tops else None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    palyno_plot.plot_wells(frames, tops=tops_df, out_path=out_path)
    typer.echo(f"Wrote {out_path} ({len(frames)} well(s))")


@taxa_app.command("suggest")
def taxa_suggest(
    in_dir: Path = typer.Option(CURATED_DEFAULT, "--in", help="Directory of curated .ASC exports."),
    top: int = typer.Option(20, "--top", help="How many suggestions to show."),
) -> None:
    """Suggest target species from the curated .ASC files, ranked by prevalence."""
    import pandas as pd

    frames = []
    for asc_path in _curated_ascs(in_dir):
        obs = parse_stratabugs_simple(asc_path)["observations"]
        if not obs.empty:
            frames.append(obs)
    if not frames:
        typer.echo(f"No palynology observations in {in_dir}.")
        raise typer.Exit(code=0)

    suggestions = suggest_targets(pd.concat(frames, ignore_index=True), top_n=top)
    typer.echo(f"Suggested target species (top {len(suggestions)} by prevalence):\n")
    typer.echo(f"  {'depths':>6}  {'count':>7}  species")
    for s in suggestions:
        typer.echo(f"  {s.n_depths:>6}  {s.total_count:>7}  {s.name}")


@taxa_app.command("review")
def taxa_review(
    in_dir: Path = typer.Option(CURATED_DEFAULT, "--in", help="Directory of curated .ASC exports."),
) -> None:
    """List similar taxon names awaiting a human same/different decision."""
    cfg = load_config()
    decisions = reconcile.Decisions.load(cfg.decisions_path())

    names: set[str] = set()
    for asc_path in _curated_ascs(in_dir):
        obs = parse_stratabugs_simple(asc_path)["observations"]
        if not obs.empty:
            names.update(obs["taxon_name"].dropna().tolist())

    result = reconcile.resolve_matches(TARGETS, sorted(names), decisions)
    if not result.pending:
        typer.echo("No similar names pending a decision.")
        raise typer.Exit(code=0)

    pending = {(p.target, p.variant): p.similarity for p in result.pending}
    typer.echo(f"{len(pending)} similar name(s) awaiting a same/different decision:\n")
    for (target, variant), sim in sorted(pending.items(), key=lambda kv: kv[1], reverse=True):
        typer.echo(f"  sim={sim:.2f}  target={target!r}  variant={variant!r}")
    typer.echo('\nRecord: diskos taxa decide "<target>" "<variant>" same|different')


@taxa_app.command("decide")
def taxa_decide(
    target: str = typer.Argument(..., help="The canonical target species."),
    variant: str = typer.Argument(..., help="The similar name in the data."),
    decision: str = typer.Argument(..., help="'same' or 'different'."),
) -> None:
    """Record that a similar name is the same as, or different from, a target."""
    if decision not in (reconcile.SAME, reconcile.DIFFERENT):
        typer.echo(f"decision must be 'same' or 'different', got {decision!r}", err=True)
        raise typer.Exit(code=1)
    cfg = load_config()
    decisions = reconcile.Decisions.load(cfg.decisions_path())
    decisions.set(target, variant, decision)
    decisions.save()
    typer.echo(f"Recorded: {variant!r} is {decision} as {target!r} -> {cfg.decisions_path()}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    """Run the web API (reuses the pipeline modules). Requires the `web` extra."""
    import uvicorn

    uvicorn.run("diskos.web.api:app", host=host, port=port, reload=False)


@wiki_app.command("ingest")
def wiki_ingest(
    in_dir: Path = typer.Option(Path("out"), "--in", help="Directory of per-well CSVs (from stratabugs)."),
    wiki_dir: Path = typer.Option(Path("wiki"), "--wiki", help="Wiki directory to update."),
) -> None:
    """Ingest every per-well CSV in a directory into the wiki (entity pages + index + log)."""
    from .wiki.ingest import ingest_well_csv

    csvs = sorted(in_dir.glob("*.csv"))
    if not csvs:
        typer.echo(f"No CSVs found in {in_dir}. Run `diskos stratabugs` first.", err=True)
        raise typer.Exit(code=1)

    for csv_path in csvs:
        page = ingest_well_csv(csv_path, wiki_dir)
        typer.echo(f"  {csv_path.name} -> {page}")
    typer.echo(f"\nIngested {len(csvs)} well(s) into {wiki_dir}")


@wiki_app.command("search")
def wiki_search(
    query: str = typer.Argument(..., help="Search terms."),
    wiki_dir: Path = typer.Option(Path("wiki"), "--wiki", help="Wiki directory to search."),
    top: int = typer.Option(5, "--top", help="How many results."),
) -> None:
    """Rank wiki pages against a query (local BM25 over page bodies)."""
    from .wiki.search import search as wiki_search_fn

    results = wiki_search_fn(wiki_dir, query, top_k=top)
    if not results:
        typer.echo("No matches.")
        raise typer.Exit(code=0)
    for r in results:
        typer.echo(f"  {r['score']:>7}  {r['path']}")
        if r["snippet"]:
            typer.echo(f"           {r['snippet']}")


@npd_app.command("fetch")
def npd_fetch() -> None:
    """Download the Sodir/NPD FactPages wellbore CSVs into the cached npd dir."""
    from . import npd as npd_mod

    cfg = load_config()
    dest = cfg.npd_path()
    typer.echo(f"Fetching Sodir FactPages wellbore tables into {dest} ...")
    written = npd_mod.fetch_factpages(dest)
    if not written:
        typer.echo("No tables downloaded (network or endpoint issue).", err=True)
        raise typer.Exit(code=1)
    records = npd_mod.load_factpages(dest)
    for path in written:
        typer.echo(f"  {path.name}")
    typer.echo(f"\n{len(records)} wellbore records available from {len(written)} table(s).")


@app.command()
def boreholes(
    limit: int = typer.Option(40, "--limit", help="How many groups to print."),
) -> None:
    """Resolve directories into physical boreholes and report coverage."""
    from . import npd as npd_mod
    from .boreholes import borehole_id, quadrant_block

    cfg = load_config()
    root = diskos_root(cfg)
    records = npd_mod.load_factpages(cfg.npd_path())
    ids = wells_mod.list_well_ids(root)

    groups: dict[str, list[str]] = {}
    for wid in ids:
        groups.setdefault(borehole_id(wid, records), []).append(wid)

    n = len(groups)
    with_coords = sum(1 for b in groups if (m := npd_mod.match(records, b)) and m.lat is not None)
    with_field = sum(1 for b in groups if (m := npd_mod.match(records, b)) and m.field)
    multi = sum(1 for v in groups.values() if len(v) > 1)
    pct = lambda x: f"{100 * x // n}%" if n else "0%"

    typer.echo(f"{len(ids)} directories -> {n} boreholes ({multi} with sidetracks)")
    typer.echo(f"NPD register loaded: {len(records)} wellbores")
    typer.echo(f"  with coordinates: {with_coords} ({pct(with_coords)})")
    typer.echo(f"  with field:       {with_field} ({pct(with_field)})\n")
    for bid, members in sorted(groups.items())[:limit]:
        extra = f"  <- {members}" if len(members) > 1 else ""
        typer.echo(f"  {bid}{extra}")


@wiki_app.command("build")
def wiki_build(
    field: str = typer.Option(None, "--field", help="Build one field or block, e.g. 31_2."),
    well: str = typer.Option(None, "--well", help="Build one borehole by ID."),
    all_wells: bool = typer.Option(False, "--all", help="Build the whole archive."),
    wiki_dir: Path = typer.Option(Path("wiki"), "--wiki", help="Wiki directory to write."),
    out_dir: Path = typer.Option(Path("out"), "--out", help="Per-well palynology CSVs, if any."),
    no_model: bool = typer.Option(False, "--no-model", help="Deterministic pages only (no LLM)."),
    force: bool = typer.Option(False, "--force", help="Rewrite pages even if unchanged."),
) -> None:
    """Build borehole + field wiki pages from the archive (NPD-located, deduped)."""
    from .llm.client import LLMClient
    from .wiki.build import build_wiki

    cfg = load_config()
    root = diskos_root(cfg)

    if well:
        scope: tuple[str, str] | str = ("well", well)
    elif field:
        scope = ("field", field)
    elif all_wells:
        scope = "all"
    else:
        typer.echo("Specify --field <block/field>, --well <id>, or --all.", err=True)
        raise typer.Exit(code=1)

    well_client = field_client = None
    if not no_model:
        well_client = LLMClient.from_profile("wiki-well", cfg)
        field_client = LLMClient.from_profile("wiki-field", cfg)

    typer.echo(f"Building wiki (scope={scope}) into {wiki_dir} ...")
    summary = build_wiki(
        root, wiki_dir, scope,
        well_client=well_client, field_client=field_client,
        out_dir=out_dir if out_dir.is_dir() else None,
        npd_dir=cfg.npd_path(), ocr_dir=cfg.ocr_path(), force=force,
    )
    typer.echo(
        f"\n{summary['boreholes']} boreholes: {summary['pages_written']} written, "
        f"{summary['pages_skipped']} unchanged; {summary['areas']} field pages."
    )


@app.command()
def ocr(
    biostrat: bool = typer.Option(False, "--biostrat", help="Only biostratigraphy reports."),
    field: str = typer.Option(None, "--field", help="Limit to one field/block, e.g. 31_2."),
    limit: int = typer.Option(0, "--limit", help="Cap how many PDFs to OCR (0 = no cap)."),
    max_pages: int = typer.Option(12, "--max-pages", help="Pages to OCR per report."),
    force: bool = typer.Option(False, "--force", help="Re-OCR even if cached."),
) -> None:
    """OCR scanned report PDFs with the local vision model, caching transcripts.

    Skips reports that already have a text layer or a cached transcript. Then
    re-run `diskos wiki build` so the pages that gained text regenerate.
    """
    from . import npd as npd_mod
    from . import wells as wells_mod
    from .boreholes import group_boreholes, quadrant_block
    from .io.ocr import ocr_reports
    from .llm.client import LLMClient

    cfg = load_config()
    root = diskos_root(cfg)
    records = npd_mod.load_factpages(cfg.npd_path())

    well_ids = wells_mod.list_well_ids(root)
    if field:
        well_ids = [w for w in well_ids if quadrant_block(w)[1] == field]
    catalog = {w: wells_mod.well_files(root, w) for w in well_ids}
    groups = group_boreholes(catalog, records)

    pdfs: list[Path] = []
    for group in groups.values():
        for p in group.files.get("geology", []):
            if p.suffix.lower() != ".pdf":
                continue
            if biostrat and not wells_mod.is_biostrat(p):
                continue
            pdfs.append(p)
    if limit:
        pdfs = pdfs[:limit]

    client = LLMClient.from_profile("vision", cfg)
    typer.echo(f"OCR over {len(pdfs)} report PDF(s) with the vision model ...")
    done = {"ocr": 0, "cached": 0, "has-text": 0, "empty": 0}

    def report(status: dict) -> None:
        done[status["state"]] = done.get(status["state"], 0) + 1
        if status["state"] == "ocr":
            typer.echo(f"  {status['file']}  ({status['chars']} chars)")

    ocr_reports(pdfs, client, cfg.ocr_path(), max_pages=max_pages, force=force, on_each=report)
    typer.echo(
        f"\nOCR done: {done['ocr']} transcribed, {done['cached']} cached, "
        f"{done['has-text']} already had text, {done['empty']} empty. "
        f"Now run `diskos wiki build --all` to enrich pages."
    )


if __name__ == "__main__":
    app()
