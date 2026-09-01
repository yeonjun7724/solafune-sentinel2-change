"""Framework-independent data contracts shared by the CLI and the QGIS plugin.

Nothing in this module imports QGIS, Qt, or any GUI toolkit. The QGIS plugin
builds a :class:`PipelineRequest` from its dock widget, passes a plain
callback to receive :class:`ProgressEvent` updates, and polls a
:class:`CancellationToken` — the same objects the CLI uses internally.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from .errors import CancelledError

Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class PipelineRequest:
    """All parameters needed to run one end-to-end analysis.

    Immutable by design: build one, tweak it with :func:`dataclasses.replace`
    if needed, and pass it to :func:`solafune_change.pipeline.run_pipeline`.
    """

    before_folder: Path
    after_folder: Path
    aoi_path: Path
    output_dir: Path
    processed_dir: Path | None = None
    run_label: str = "run"

    # --- preprocessing ---
    normalization: str = (
        "robust_median_mad"  # robust_median_mad|percentile_matching|pif_linear|none
    )
    reflectance_scale: float = 10000.0
    nodata_value: float = 0.0

    # --- change detection ---
    method: str = "both"  # baseline|cva|both
    threshold_method: str = "otsu"  # otsu|percentile|manual
    percentile: float = 95.0
    manual_threshold: float | None = None
    morphology_enabled: bool = True
    morphology_operation: str = "opening_then_closing"  # opening|closing|opening_then_closing|none
    morphology_kernel_size: int = 3
    fill_holes: bool = False
    min_area_m2: float = 400.0

    # --- spatial statistics ---
    spatial_statistics_enabled: bool = True
    spatial_grid_size_m: float = 150.0
    spatial_weights: str = "queen"  # queen|rook|knn
    knn_k: int = 8
    row_standardization: bool = True
    permutations: int = 999
    alpha: float = 0.05
    fdr_correction: bool = True

    # --- experimental spatial ML ---
    spatial_ml_enabled: bool = False
    ml_model: str = "isolation_forest"  # isolation_forest|dbscan|hdbscan
    ml_contamination: float = 0.1
    ml_n_estimators: int = 200
    dbscan_eps: float = 1.5
    dbscan_min_samples: int = 5
    ml_use_coordinates: bool = False
    ml_n_bootstrap: int = 20

    # --- outputs ---
    write_stacks: bool = True
    write_intermediate: bool = True
    create_interactive_map: bool = True
    create_qgis_styles: bool = True

    random_seed: int = 42

    def with_output_dir(self, output_dir: Path) -> PipelineRequest:
        return replace(self, output_dir=output_dir)


@dataclass(frozen=True)
class ProgressEvent:
    """One unit of progress, framework-agnostic.

    ``percent`` is monotonically increasing across a single run (0-100).
    """

    stage: str
    message: str
    percent: float
    severity: Severity = "info"


ProgressCallback = Callable[[ProgressEvent], None]


class CancellationToken:
    """Cooperative cancellation flag polled between pipeline stages.

    Deliberately not built on :class:`threading.Event` to keep this module
    free of threading assumptions — the QGIS plugin wires this to
    ``QgsTask.isCanceled()`` and the CLI wires it to a no-op or a
    ``SIGINT`` handler.
    """

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def check(self, stage: str) -> None:
        """Raise :class:`CancelledError` if cancellation has been requested."""
        if self._cancelled:
            raise CancelledError(stage)


@dataclass
class ValidationIssue:
    severity: Severity
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    """Result of :func:`solafune_change.pipeline.validate_request`."""

    issues: list[ValidationIssue] = field(default_factory=list)
    band_metadata: list[dict[str, Any]] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def status(self) -> Literal["valid", "valid_with_warnings", "invalid"]:
        if not self.is_valid:
            return "invalid"
        if self.warnings:
            return "valid_with_warnings"
        return "valid"

    def add(self, severity: Severity, code: str, message: str, **context: Any) -> None:
        self.issues.append(
            ValidationIssue(severity=severity, code=code, message=message, context=context)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "is_valid": self.is_valid,
            "issues": [
                {"severity": i.severity, "code": i.code, "message": i.message, "context": i.context}
                for i in self.issues
            ],
            "band_metadata": self.band_metadata,
        }


@dataclass
class PipelineResult:
    """Everything a caller (CLI or QGIS plugin) needs after a run completes."""

    run_id: str
    output_dir: Path
    before_date: str
    after_date: str
    before_stack: Path | None = None
    after_stack: Path | None = None
    baseline_intensity: Path | None = None
    baseline_binary: Path | None = None
    cva_intensity: Path | None = None
    cva_binary: Path | None = None
    change_features: Path | None = None
    spatial_grid_gpkg: Path | None = None
    global_moran_json: Path | None = None
    spatial_statistics_csv: Path | None = None
    ml_results_csv: Path | None = None
    database: Path | None = None
    summary_json: Path | None = None
    run_manifest_json: Path | None = None
    quality_report_json: Path | None = None
    report_md: Path | None = None
    static_figure_png: Path | None = None
    interactive_map_html: Path | None = None
    qml_styles: dict[str, Path] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    runtime_seconds: float = 0.0
