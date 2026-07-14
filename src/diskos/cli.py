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


if __name__ == "__main__":
    app()
