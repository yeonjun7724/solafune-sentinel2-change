"""UI-facing pipeline result model.

Mirrors the fields of :class:`solafune_change.types.PipelineResult` that the
dock widget and layer loader need, as plain strings/numbers -- kept
dependency-free like :mod:`validation_model` for the same reason, and also
usable to describe a result reconstructed purely from a ``run_manifest.json``
/ ``summary.json`` pair (the external-process execution path, where no live
:class:`PipelineResult` object ever exists in the QGIS process).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UiResult:
    run_id: str = ""
    output_dir: str = ""
    before_date: str = ""
    after_date: str = ""
    paths: dict[str, str | None] = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    runtime_seconds: float = 0.0

    def get_path(self, key: str) -> Path | None:
        value = self.paths.get(key)
        return Path(value) if value else None


def from_core_result(result) -> UiResult:
    return UiResult(
        run_id=result.run_id,
        output_dir=str(result.output_dir),
        before_date=result.before_date,
        after_date=result.after_date,
        paths={
            "before_stack": str(result.before_stack) if result.before_stack else None,
            "after_stack": str(result.after_stack) if result.after_stack else None,
            "baseline_intensity": (
                str(result.baseline_intensity) if result.baseline_intensity else None
            ),
            "baseline_binary": str(result.baseline_binary) if result.baseline_binary else None,
            "cva_intensity": str(result.cva_intensity) if result.cva_intensity else None,
            "cva_binary": str(result.cva_binary) if result.cva_binary else None,
            "database": str(result.database) if result.database else None,
            "spatial_grid_gpkg": (
                str(result.spatial_grid_gpkg) if result.spatial_grid_gpkg else None
            ),
            "report_md": str(result.report_md) if result.report_md else None,
            "interactive_map_html": (
                str(result.interactive_map_html) if result.interactive_map_html else None
            ),
            "static_figure_png": (
                str(result.static_figure_png) if result.static_figure_png else None
            ),
        },
        summary=dict(result.summary),
        warnings=list(result.warnings),
        runtime_seconds=result.runtime_seconds,
    )


def from_manifest_files(manifest_path: str, summary_path: str) -> UiResult:
    """Reconstruct a :class:`UiResult` from the two JSON files an external-process
    run leaves behind -- this is the only source of truth for that execution mode."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    summary = (
        json.loads(Path(summary_path).read_text(encoding="utf-8"))
        if Path(summary_path).exists()
        else {}
    )
    output_paths = manifest.get("output_paths", {})
    output_dir = str(Path(manifest_path).parent)
    return UiResult(
        run_id=manifest.get("run_id", ""),
        output_dir=output_dir,
        before_date=manifest.get("before_date", ""),
        after_date=manifest.get("after_date", ""),
        paths={
            **output_paths,
            "database": output_paths.get("database"),
            "spatial_grid_gpkg": str(Path(output_dir) / "maps" / "spatial_statistics.gpkg"),
            "report_md": str(Path(output_dir) / "report.md"),
        },
        summary=summary,
        warnings=[],
        runtime_seconds=manifest.get("runtime_seconds", 0.0),
    )
