"""Command-line interface for the Solafune Sentinel-2 change analysis pipeline.

Run ``solafune-change --help`` (or ``python -m solafune_change --help``) for
the full command list. Every command reads the same YAML config schema
(``config/default.yaml`` by default) and any option can be overridden on the
command line.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from . import config as config_mod
from .errors import SolafuneChangeError
from .pipeline import run_pipeline, validate_request
from .types import ProgressEvent

app = typer.Typer(add_completion=False, help="Solafune Sentinel-2 change analysis pipeline.")
console = Console()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False, rich_tracebacks=True)],
    )
    logging.getLogger("fiona").setLevel(logging.WARNING)
    logging.getLogger("rasterio").setLevel(logging.WARNING)


def _load_request(
    config: Path,
    before_folder: Path | None = None,
    after_folder: Path | None = None,
    aoi: Path | None = None,
    output_dir: Path | None = None,
    method: str | None = None,
    threshold_method: str | None = None,
    threshold_value: float | None = None,
    percentile: float | None = None,
    min_area_m2: float | None = None,
    grid_size_m: float | None = None,
    permutations: int | None = None,
    seed: int | None = None,
    ml: bool | None = None,
):
    app_config = config_mod.load_config(config, base_dir=config.resolve().parent.parent)
    request = config_mod.config_to_request(app_config)

    overrides = {}
    if before_folder is not None:
        overrides["before_folder"] = before_folder
    if after_folder is not None:
        overrides["after_folder"] = after_folder
    if aoi is not None:
        overrides["aoi_path"] = aoi
    if output_dir is not None:
        overrides["output_dir"] = output_dir
    if method is not None:
        overrides["method"] = method
    if threshold_method is not None:
        overrides["threshold_method"] = threshold_method
    if threshold_value is not None:
        overrides["manual_threshold"] = threshold_value
    if percentile is not None:
        overrides["percentile"] = percentile
    if min_area_m2 is not None:
        overrides["min_area_m2"] = min_area_m2
    if grid_size_m is not None:
        overrides["spatial_grid_size_m"] = grid_size_m
    if permutations is not None:
        overrides["permutations"] = permutations
    if seed is not None:
        overrides["random_seed"] = seed
    if ml is not None:
        overrides["spatial_ml_enabled"] = ml

    if overrides:
        from dataclasses import replace

        request = replace(request, **overrides)
    return request


CONFIG_OPTION = typer.Option(
    Path("config/default.yaml"), "--config", "-c", help="Path to a YAML configuration file."
)
BEFORE_OPTION = typer.Option(None, "--before", help="Override: before-date Sentinel-2 folder.")
AFTER_OPTION = typer.Option(None, "--after", help="Override: after-date Sentinel-2 folder.")
AOI_OPTION = typer.Option(None, "--aoi", help="Override: AOI vector file.")
OUTPUT_OPTION = typer.Option(None, "--output-dir", help="Override: output directory.")
METHOD_OPTION = typer.Option(None, "--method", help="Override: baseline | cva | both.")
THRESH_METHOD_OPTION = typer.Option(
    None, "--threshold-method", help="Override: otsu | percentile | manual."
)
THRESH_VALUE_OPTION = typer.Option(
    None, "--threshold-value", help="Override: manual threshold value."
)
PERCENTILE_OPTION = typer.Option(
    None, "--percentile", help="Override: percentile threshold value (0-100)."
)
MIN_AREA_OPTION = typer.Option(
    None, "--min-area-m2", help="Override: minimum change-feature area in m^2."
)
GRID_SIZE_OPTION = typer.Option(
    None, "--grid-size-m", help="Override: spatial statistics grid cell size in meters."
)
PERMUTATIONS_OPTION = typer.Option(
    None, "--permutations", help="Override: Monte Carlo permutation count."
)
SEED_OPTION = typer.Option(None, "--seed", help="Override: random seed.")
ML_OPTION = typer.Option(
    None, "--ml/--no-ml", help="Override: enable/disable experimental spatial ML."
)
VERBOSE_OPTION = typer.Option(False, "--verbose", "-v", help="Enable debug logging.")
JSON_PROGRESS_OPTION = typer.Option(
    False,
    "--json-progress",
    help="Emit machine-readable JSON Lines progress on stdout instead of rich console output "
    "(used by the QGIS plugin's external-process execution mode).",
)


def _json_progress_emitter():
    def _emit(evt: ProgressEvent) -> None:
        sys.stdout.write(
            json.dumps(
                {
                    "type": evt.severity,
                    "stage": evt.stage,
                    "percent": evt.percent,
                    "message": evt.message,
                }
            )
            + "\n"
        )
        sys.stdout.flush()

    return _emit


def _rich_progress_emitter():
    def _emit(evt: ProgressEvent) -> None:
        console.print(f"[cyan]\\[{evt.percent:5.1f}%][/cyan] {evt.stage}: {evt.message}")

    return _emit


def _print_validation(report) -> bool:
    table = Table(title=f"Validation: {report.status.upper()}")
    table.add_column("Severity")
    table.add_column("Code")
    table.add_column("Message")
    for issue in report.issues:
        style = {"error": "bold red", "warning": "yellow", "info": "cyan"}[issue.severity]
        table.add_row(f"[{style}]{issue.severity}[/{style}]", issue.code, issue.message)
    if report.issues:
        console.print(table)
    else:
        console.print("[green]No issues found.[/green]")
    return report.is_valid


@app.command()
def validate(
    config: Path = CONFIG_OPTION,
    before_folder: Path | None = BEFORE_OPTION,
    after_folder: Path | None = AFTER_OPTION,
    aoi: Path | None = AOI_OPTION,
    output_dir: Path | None = OUTPUT_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """Validate inputs and configuration without running any analysis (dry-run)."""
    _setup_logging(verbose)
    try:
        request = _load_request(config, before_folder, after_folder, aoi, output_dir)
        report = validate_request(request)
    except SolafuneChangeError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc.user_message}")
        raise typer.Exit(code=1) from exc
    ok = _print_validation(report)
    raise typer.Exit(code=0 if ok else 1)


@app.command()
def run(
    config: Path = CONFIG_OPTION,
    before_folder: Path | None = BEFORE_OPTION,
    after_folder: Path | None = AFTER_OPTION,
    aoi: Path | None = AOI_OPTION,
    output_dir: Path | None = OUTPUT_OPTION,
    method: str | None = METHOD_OPTION,
    threshold_method: str | None = THRESH_METHOD_OPTION,
    threshold_value: float | None = THRESH_VALUE_OPTION,
    percentile: float | None = PERCENTILE_OPTION,
    min_area_m2: float | None = MIN_AREA_OPTION,
    grid_size_m: float | None = GRID_SIZE_OPTION,
    permutations: int | None = PERMUTATIONS_OPTION,
    seed: int | None = SEED_OPTION,
    ml: bool | None = ML_OPTION,
    json_progress: bool = JSON_PROGRESS_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """Run the full pipeline: stacking, change detection, statistics, ML, database, visuals, report."""
    if not json_progress:
        _setup_logging(verbose)
    request = _load_request(
        config,
        before_folder,
        after_folder,
        aoi,
        output_dir,
        method,
        threshold_method,
        threshold_value,
        percentile,
        min_area_m2,
        grid_size_m,
        permutations,
        seed,
        ml,
    )

    val_report = validate_request(request)
    if not val_report.is_valid:
        if json_progress:
            sys.stdout.write(
                json.dumps(
                    {"type": "error", "message": "; ".join(i.message for i in val_report.errors)}
                )
                + "\n"
            )
        else:
            _print_validation(val_report)
            console.print(
                "[bold red]Validation failed; aborting run. Fix the errors above and try again.[/bold red]"
            )
        raise typer.Exit(code=1)
    if val_report.warnings and not json_progress:
        _print_validation(val_report)

    progress_fn = _json_progress_emitter() if json_progress else _rich_progress_emitter()

    try:
        result = run_pipeline(request, progress_callback=progress_fn)
    except SolafuneChangeError as exc:
        if json_progress:
            sys.stdout.write(json.dumps({"type": "error", "message": exc.user_message}) + "\n")
        else:
            console.print(f"[bold red]Run failed:[/bold red] {exc.user_message}")
        raise typer.Exit(code=1) from exc

    if json_progress:
        sys.stdout.write(
            json.dumps(
                {
                    "type": "result",
                    "manifest": str(result.run_manifest_json),
                    "summary": str(result.summary_json),
                }
            )
            + "\n"
        )
        sys.stdout.flush()
        return

    console.print(
        f"\n[bold green]Run complete[/bold green] (run_id={result.run_id}, {result.runtime_seconds:.1f}s)"
    )
    table = Table(title="Summary")
    for k, v in result.summary.items():
        table.add_row(str(k), f"{v:.4f}" if isinstance(v, float) else str(v))
    console.print(table)
    console.print(f"Report: {result.report_md}")
    console.print(f"Database: {result.database}")
    if result.interactive_map_html:
        console.print(f"Interactive map: {result.interactive_map_html}")


@app.command()
def stats(config: Path = CONFIG_OPTION, verbose: bool = VERBOSE_OPTION) -> None:
    """Run the pipeline with spatial statistics forced on (shortcut for `run --ml=false`)."""
    _setup_logging(verbose)
    console.print("[cyan]Running full analysis with spatial statistics enabled...[/cyan]")
    request = _load_request(config)
    from dataclasses import replace

    request = replace(request, spatial_statistics_enabled=True)
    result = run_pipeline(request)
    console.print(
        f"[bold green]Done.[/bold green] Global Moran's I = {result.summary.get('global_moran_i')}"
    )


@app.command()
def visualize(config: Path = CONFIG_OPTION, verbose: bool = VERBOSE_OPTION) -> None:
    """Run the full pipeline (visualization is always produced as part of `run`)."""
    _setup_logging(verbose)
    console.print(
        "[cyan]This CLI always generates figures/interactive map as part of a full run.[/cyan]"
    )
    request = _load_request(config)
    result = run_pipeline(request)
    console.print(f"Figure: {result.static_figure_png}")
    console.print(f"Interactive map: {result.interactive_map_html}")


@app.command()
def report(config: Path = CONFIG_OPTION, verbose: bool = VERBOSE_OPTION) -> None:
    """Run the full pipeline and (re)generate report.md from the resulting summary."""
    _setup_logging(verbose)
    request = _load_request(config)
    result = run_pipeline(request)
    console.print(f"[bold green]report.md written:[/bold green] {result.report_md}")


@app.command()
def all(  # noqa: A001 - deliberate CLI verb matching the assignment naming
    config: Path = CONFIG_OPTION,
    ml: bool | None = ML_OPTION,
    output_dir: Path | None = OUTPUT_OPTION,
    json_progress: bool = JSON_PROGRESS_OPTION,
    verbose: bool = VERBOSE_OPTION,
) -> None:
    """Run validate -> run in sequence (the recommended one-command entry point)."""
    if not json_progress:
        _setup_logging(verbose)
    request = _load_request(config, output_dir=output_dir, ml=ml)
    val_report = validate_request(request)
    if not val_report.is_valid:
        if json_progress:
            sys.stdout.write(
                json.dumps(
                    {"type": "error", "message": "; ".join(i.message for i in val_report.errors)}
                )
                + "\n"
            )
        else:
            _print_validation(val_report)
        raise typer.Exit(code=1)

    progress_fn = _json_progress_emitter() if json_progress else _rich_progress_emitter()

    try:
        result = run_pipeline(request, progress_callback=progress_fn)
    except SolafuneChangeError as exc:
        if json_progress:
            sys.stdout.write(json.dumps({"type": "error", "message": exc.user_message}) + "\n")
        else:
            console.print(f"[bold red]Run failed:[/bold red] {exc.user_message}")
        raise typer.Exit(code=1) from exc

    if json_progress:
        sys.stdout.write(
            json.dumps(
                {
                    "type": "result",
                    "manifest": str(result.run_manifest_json),
                    "summary": str(result.summary_json),
                }
            )
            + "\n"
        )
        sys.stdout.flush()
        return

    console.print(f"\n[bold green]All stages complete[/bold green] (run_id={result.run_id})")
    for key in (
        "feature_count",
        "changed_area_m2",
        "changed_area_percent",
        "global_moran_i",
        "global_moran_p",
        "hotspot_95_count",
    ):
        console.print(f"  {key}: {result.summary.get(key)}")
    console.print(f"Report: {result.report_md}")
    console.print(f"Database: {result.database}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
