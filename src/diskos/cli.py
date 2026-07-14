"""Command-line entrypoints for diskosAI.

    diskos wells                     -- print the discovered borehole catalog
    diskos stratabugs --all          -- palynology pipeline over every well
    diskos stratabugs --well ID      -- ... over one well
    diskos taxa suggest --well ID    -- suggest target species from the data
    diskos taxa review               -- list similar names awaiting a decision
    diskos taxa decide T V same|different  -- record a same/different call

Every command resolves the DISKOS root from config and discovers wells via the
catalog, so nothing is tied to specific boreholes.
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


def _select_wells(root: Path, well: str | None, all_wells: bool) -> dict[str, wells_mod.Well]:
    catalog = wells_mod.catalog(root)
    if all_wells:
        return catalog
    if well:
        if well not in catalog:
            known = ", ".join(sorted(catalog)) or "(none)"
            typer.echo(f"Well {well!r} not found. Known: {known}", err=True)
            raise typer.Exit(code=1)
        return {well: catalog[well]}
    typer.echo("Specify --well <id> or --all.", err=True)
    raise typer.Exit(code=1)


def _available_taxa(entry: wells_mod.Well) -> list[str]:
    """Union of taxon names across a well's .ASC palynology files."""
    names: set[str] = set()
    for asc_path in entry.paly:
        obs = parse_stratabugs_simple(asc_path)["observations"]
        if not obs.empty:
            names.update(obs["taxon_name"].dropna().tolist())
    return sorted(names)


@app.command()
def wells() -> None:
    """Discover and print the borehole catalog (which data each well has)."""
    root = diskos_root(load_config())
    catalog = wells_mod.catalog(root)
    if not catalog:
        typer.echo(f"No wells discovered under {root}")
        raise typer.Exit(code=0)

    typer.echo(f"{len(catalog)} wells discovered under {root}:\n")
    for well_id in sorted(catalog):
        well = catalog[well_id]
        typer.echo(
            f"  {well_id:<14} paly={len(well.paly)} logs={len(well.logs)} xrf={len(well.xrf)}"
        )


@app.command()
def stratabugs(
    well: str = typer.Option(None, "--well", help="Run one borehole by ID (e.g. 35_10-8)."),
    all_wells: bool = typer.Option(False, "--all", help="Run every discovered borehole."),
    targets: str = typer.Option(
        None, "--targets", help="Comma-separated target taxa (default: the built-in TARGETS)."
    ),
    out: Path = typer.Option(Path("out"), "--out", help="Output directory for per-well CSVs."),
) -> None:
    """Parse .ASC palynology files -> reconcile target taxa -> wide CSV per well.

    Exact genus+species names merge automatically; only similar names that have a
    recorded same/different decision are merged. Undecided similar names are held
    apart and reported (run `diskos taxa review`).
    """
    cfg = load_config()
    root = diskos_root(cfg)
    target_list = [t.strip() for t in targets.split(",")] if targets else TARGETS
    decisions = reconcile.Decisions.load(cfg.decisions_path())

    selected = _select_wells(root, well, all_wells)
    out.mkdir(parents=True, exist_ok=True)

    written = 0
    pending: dict[tuple[str, str], float] = {}
    for well_id in sorted(selected):
        entry = selected[well_id]
        for asc_path in entry.paly:
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
        typer.echo(
            f"{len(pending)} similar name(s) need a same/different decision "
            f"before they can be merged. Run `diskos taxa review`."
        )


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
    selected = _select_wells(root, well, all_wells)

    tracks = {}
    for well_id in sorted(selected):
        entry = selected[well_id]
        if not entry.logs:
            continue
        df = wl_curves.read_las(entry.logs[0])
        name = mnemonic or wl_curves.gamma_column(df)
        series = wl_curves.slice_depth(wl_curves.curve_series(df, name), top, bottom)
        tracks[f"{well_id}:{name}"] = series

    if not tracks:
        typer.echo("No wells with logs in the selection.", err=True)
        raise typer.Exit(code=1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wl_plot.plot_correlation(tracks, out_path=out_path)
    typer.echo(f"Wrote {out_path} ({len(tracks)} track(s))")


@taxa_app.command("suggest")
def taxa_suggest(
    well: str = typer.Option(None, "--well", help="Suggest from one borehole."),
    all_wells: bool = typer.Option(False, "--all", help="Suggest from every borehole."),
    top: int = typer.Option(20, "--top", help="How many suggestions to show."),
) -> None:
    """Suggest target species from what is actually in the selected wells, ranked
    by prevalence, so you can pick rather than maintain a list by hand."""
    import pandas as pd

    cfg = load_config()
    root = diskos_root(cfg)
    selected = _select_wells(root, well, all_wells)

    frames = []
    for entry in selected.values():
        for asc_path in entry.paly:
            obs = parse_stratabugs_simple(asc_path)["observations"]
            if not obs.empty:
                frames.append(obs)
    if not frames:
        typer.echo("No palynology observations found in the selection.")
        raise typer.Exit(code=0)

    suggestions = suggest_targets(pd.concat(frames, ignore_index=True), top_n=top)
    typer.echo(f"Suggested target species (top {len(suggestions)} by prevalence):\n")
    typer.echo(f"  {'depths':>6}  {'count':>7}  species")
    for s in suggestions:
        typer.echo(f"  {s.n_depths:>6}  {s.total_count:>7}  {s.name}")
    typer.echo("\nCopy the ones you want into src/diskos/palyno/targets.py (or --targets).")


@taxa_app.command("review")
def taxa_review(
    well: str = typer.Option(None, "--well", help="Review one borehole."),
    all_wells: bool = typer.Option(True, "--all/--one", help="Review every borehole (default)."),
) -> None:
    """List similar taxon names awaiting a human same/different decision."""
    cfg = load_config()
    root = diskos_root(cfg)
    decisions = reconcile.Decisions.load(cfg.decisions_path())
    selected = _select_wells(root, well, all_wells and not well)

    pending: dict[tuple[str, str], float] = {}
    for entry in selected.values():
        available = _available_taxa(entry)
        result = reconcile.resolve_matches(TARGETS, available, decisions)
        for pair in result.pending:
            pending[(pair.target, pair.variant)] = pair.similarity

    if not pending:
        typer.echo("No similar names pending a decision.")
        raise typer.Exit(code=0)

    typer.echo(f"{len(pending)} similar name(s) awaiting a same/different decision:\n")
    for (target, variant), sim in sorted(pending.items(), key=lambda kv: kv[1], reverse=True):
        typer.echo(f"  sim={sim:.2f}  target={target!r}  variant={variant!r}")
    typer.echo(
        "\nRecord a call with:\n"
        "  diskos taxa decide \"<target>\" \"<variant>\" same|different"
    )


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


if __name__ == "__main__":
    app()
