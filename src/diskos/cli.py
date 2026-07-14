"""Command-line entrypoints for diskosAI.

    diskos wells                 -- print the discovered borehole catalog
    diskos stratabugs --all      -- run the palynology pipeline over every well
    diskos stratabugs --well ID  -- ... over one well

Every command resolves the DISKOS root from config and discovers wells via the
catalog, so nothing is tied to specific boreholes.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import wells as wells_mod
from .config import load_config
from .io.stratabugs import parse_stratabugs_simple
from .palyno.aggregate import create_wide_format_with_target_matching
from .palyno.targets import TARGETS
from .paths import diskos_root

app = typer.Typer(help="Tools for exploring DISKOS petroleum borehole data.", no_args_is_help=True)


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


@app.command()
def stratabugs(
    well: str = typer.Option(None, "--well", help="Run one borehole by ID (e.g. 35_10-8)."),
    all_wells: bool = typer.Option(False, "--all", help="Run every discovered borehole."),
    targets: str = typer.Option(
        None, "--targets", help="Comma-separated target taxa (default: the built-in TARGETS)."
    ),
    threshold: float = typer.Option(0.9, "--threshold", help="Fuzzy-match similarity threshold."),
    out: Path = typer.Option(Path("out"), "--out", help="Output directory for per-well CSVs."),
) -> None:
    """Parse .ASC palynology files -> match target taxa -> wide CSV per well."""
    root = diskos_root(load_config())
    target_list = [t.strip() for t in targets.split(",")] if targets else TARGETS

    selected = _select_wells(root, well, all_wells)
    out.mkdir(parents=True, exist_ok=True)

    written = 0
    for well_id in sorted(selected):
        entry = selected[well_id]
        if not entry.paly:
            continue
        for asc_path in entry.paly:
            parsed = parse_stratabugs_simple(asc_path)
            obs = parsed["observations"]
            if obs.empty:
                typer.echo(f"  {asc_path.name}: no observations, skipped")
                continue
            wide = create_wide_format_with_target_matching(obs, target_list, threshold)
            if wide.empty or wide.shape[1] == 0:
                typer.echo(f"  {asc_path.name}: no target matches, skipped")
                continue
            out_path = out / f"{asc_path.stem}.csv"
            wide.to_csv(out_path, index=True)
            typer.echo(f"  {asc_path.name} -> {out_path} ({wide.shape[0]} depths, {wide.shape[1]} cols)")
            written += 1

    typer.echo(f"\nWrote {written} CSV file(s) to {out}")


if __name__ == "__main__":
    app()
