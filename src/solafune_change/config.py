"""YAML configuration loading and conversion to a :class:`PipelineRequest`.

The CLI reads ``config/default.yaml`` (or a user-supplied file) through this
module. The QGIS plugin builds the same :class:`~solafune_change.types.PipelineRequest`
directly from dock-widget values, but can also import/export the identical
YAML schema so settings are portable between the two front ends.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigurationError
from .types import PipelineRequest

logger = logging.getLogger(__name__)


@dataclass
class PathsConfig:
    aoi: Path
    before_folder: Path
    after_folder: Path
    output_dir: Path
    # None when not explicitly set in the YAML: pipeline.run_pipeline() then
    # derives it from the (always-absolute) resolved output_dir itself
    # (output_dir.parent / "data" / "processed") rather than from where this
    # config file happens to live. That distinction matters for a temp config
    # file (e.g. the QGIS plugin's external-execution mode writes one under
    # the OS temp directory) -- resolving a relative default against the temp
    # file's *own* location previously produced nonsensical paths.
    processed_dir: Path | None = None


@dataclass
class PreprocessingConfig:
    normalization: str = "robust_median_mad"
    resampling: str = "bilinear"
    reference_date: str = "before"
    reflectance_scale: float = 10000.0
    nodata_value: float = 0.0


@dataclass
class MorphologyConfig:
    enabled: bool = True
    operation: str = "opening_then_closing"
    structure_size: int = 3
    fill_holes: bool = False


@dataclass
class ChangeDetectionConfig:
    method: str = "both"
    threshold_method: str = "otsu"
    percentile: float = 95.0
    manual_threshold: float | None = None
    morphology: MorphologyConfig = field(default_factory=MorphologyConfig)
    min_area_m2: float = 400.0


@dataclass
class SpatialStatisticsConfig:
    enabled: bool = True
    grid_size_m: float = 150.0
    weights: str = "queen"
    knn_k: int = 8
    permutations: int = 999
    alpha: float = 0.05
    fdr_correction: bool = True
    random_seed: int = 42


@dataclass
class ClusteringConfig:
    algorithm: str = "dbscan"
    eps: float = 1.5
    min_samples: int = 5


@dataclass
class SpatialMLConfig:
    enabled: bool = False
    model: str = "isolation_forest"
    contamination: float = 0.1
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)
    random_seed: int = 42
    use_coordinates: bool = False
    n_bootstrap: int = 20


@dataclass
class OutputConfig:
    write_stacks: bool = True
    write_intermediate: bool = True
    create_interactive_map: bool = True
    create_qgis_styles: bool = True


@dataclass
class AppConfig:
    paths: PathsConfig
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    change_detection: ChangeDetectionConfig = field(default_factory=ChangeDetectionConfig)
    spatial_statistics: SpatialStatisticsConfig = field(default_factory=SpatialStatisticsConfig)
    spatial_ml: SpatialMLConfig = field(default_factory=SpatialMLConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    random_seed: int = 42


def _get(d: dict[str, Any], key: str, default: Any = None) -> Any:
    return d.get(key, default) if d else default


def load_config(config_path: str | Path, base_dir: str | Path | None = None) -> AppConfig:
    """Load a YAML config file into an :class:`AppConfig`.

    Relative paths inside the file are resolved against ``base_dir`` (default:
    the config file's parent directory's parent, i.e. the repository root).
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            f"Could not parse YAML configuration: {config_path}", detail=str(exc)
        ) from exc

    base = Path(base_dir) if base_dir is not None else Path.cwd()

    def resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (base / path)

    paths_raw = _get(raw, "paths", {})
    for required in ("aoi", "before_folder", "after_folder"):
        if not paths_raw.get(required):
            raise ConfigurationError(f"Missing required config field: paths.{required}")

    processed_dir_raw = paths_raw.get("processed_dir")
    paths = PathsConfig(
        aoi=resolve(paths_raw["aoi"]),
        before_folder=resolve(paths_raw["before_folder"]),
        after_folder=resolve(paths_raw["after_folder"]),
        output_dir=resolve(_get(paths_raw, "output_dir", "outputs")),
        processed_dir=resolve(processed_dir_raw) if processed_dir_raw else None,
    )

    prep_raw = _get(raw, "preprocessing", {})
    preprocessing = PreprocessingConfig(
        normalization=_get(prep_raw, "normalization", "robust_median_mad"),
        resampling=_get(prep_raw, "resampling", "bilinear"),
        reference_date=_get(prep_raw, "reference_date", "before"),
        reflectance_scale=float(_get(prep_raw, "reflectance_scale", 10000.0)),
        nodata_value=float(_get(prep_raw, "nodata_value", 0.0)),
    )

    cd_raw = _get(raw, "change_detection", {})
    morph_raw = _get(cd_raw, "morphology", {})
    change_detection = ChangeDetectionConfig(
        method=_get(cd_raw, "method", "both"),
        threshold_method=_get(cd_raw, "threshold_method", "otsu"),
        percentile=float(_get(cd_raw, "percentile", 95.0)),
        manual_threshold=_get(cd_raw, "manual_threshold", None),
        morphology=MorphologyConfig(
            enabled=bool(_get(morph_raw, "enabled", True)),
            operation=_get(morph_raw, "operation", "opening_then_closing"),
            structure_size=int(_get(morph_raw, "structure_size", 3)),
            fill_holes=bool(_get(morph_raw, "fill_holes", False)),
        ),
        min_area_m2=float(_get(cd_raw, "min_area_m2", 400.0)),
    )

    ss_raw = _get(raw, "spatial_statistics", {})
    spatial_statistics = SpatialStatisticsConfig(
        enabled=bool(_get(ss_raw, "enabled", True)),
        grid_size_m=float(_get(ss_raw, "grid_size_m", 150.0)),
        weights=_get(ss_raw, "weights", "queen"),
        knn_k=int(_get(ss_raw, "knn_k", 8)),
        permutations=int(_get(ss_raw, "permutations", 999)),
        alpha=float(_get(ss_raw, "alpha", 0.05)),
        fdr_correction=bool(_get(ss_raw, "fdr_correction", True)),
        random_seed=int(_get(ss_raw, "random_seed", 42)),
    )

    ml_raw = _get(raw, "spatial_ml", {})
    cluster_raw = _get(ml_raw, "clustering", {})
    spatial_ml = SpatialMLConfig(
        enabled=bool(_get(ml_raw, "enabled", False)),
        model=_get(ml_raw, "model", "isolation_forest"),
        contamination=float(_get(ml_raw, "contamination", 0.1)),
        clustering=ClusteringConfig(
            algorithm=_get(cluster_raw, "algorithm", "dbscan"),
            eps=float(_get(cluster_raw, "eps", 1.5)),
            min_samples=int(_get(cluster_raw, "min_samples", 5)),
        ),
        random_seed=int(_get(ml_raw, "random_seed", 42)),
        use_coordinates=bool(_get(ml_raw, "use_coordinates", False)),
        n_bootstrap=int(_get(ml_raw, "n_bootstrap", 20)),
    )

    out_raw = _get(raw, "output", {})
    output = OutputConfig(
        write_stacks=bool(_get(out_raw, "write_stacks", True)),
        write_intermediate=bool(_get(out_raw, "write_intermediate", True)),
        create_interactive_map=bool(_get(out_raw, "create_interactive_map", True)),
        create_qgis_styles=bool(_get(out_raw, "create_qgis_styles", True)),
    )

    run_raw = _get(raw, "run", {})
    random_seed = int(_get(run_raw, "random_seed", 42))

    return AppConfig(
        paths=paths,
        preprocessing=preprocessing,
        change_detection=change_detection,
        spatial_statistics=spatial_statistics,
        spatial_ml=spatial_ml,
        output=output,
        random_seed=random_seed,
    )


def config_to_request(config: AppConfig, run_label: str = "run") -> PipelineRequest:
    """Convert a parsed YAML :class:`AppConfig` into a :class:`PipelineRequest`."""
    return PipelineRequest(
        before_folder=config.paths.before_folder,
        after_folder=config.paths.after_folder,
        aoi_path=config.paths.aoi,
        output_dir=config.paths.output_dir,
        processed_dir=config.paths.processed_dir,
        run_label=run_label,
        normalization=config.preprocessing.normalization,
        reflectance_scale=config.preprocessing.reflectance_scale,
        nodata_value=config.preprocessing.nodata_value,
        method=config.change_detection.method,
        threshold_method=config.change_detection.threshold_method,
        percentile=config.change_detection.percentile,
        manual_threshold=config.change_detection.manual_threshold,
        morphology_enabled=config.change_detection.morphology.enabled,
        morphology_operation=config.change_detection.morphology.operation,
        morphology_kernel_size=config.change_detection.morphology.structure_size,
        fill_holes=config.change_detection.morphology.fill_holes,
        min_area_m2=config.change_detection.min_area_m2,
        spatial_statistics_enabled=config.spatial_statistics.enabled,
        spatial_grid_size_m=config.spatial_statistics.grid_size_m,
        spatial_weights=config.spatial_statistics.weights,
        knn_k=config.spatial_statistics.knn_k,
        permutations=config.spatial_statistics.permutations,
        alpha=config.spatial_statistics.alpha,
        fdr_correction=config.spatial_statistics.fdr_correction,
        spatial_ml_enabled=config.spatial_ml.enabled,
        ml_model=config.spatial_ml.model,
        ml_contamination=config.spatial_ml.contamination,
        dbscan_eps=config.spatial_ml.clustering.eps,
        dbscan_min_samples=config.spatial_ml.clustering.min_samples,
        ml_use_coordinates=config.spatial_ml.use_coordinates,
        ml_n_bootstrap=config.spatial_ml.n_bootstrap,
        write_stacks=config.output.write_stacks,
        write_intermediate=config.output.write_intermediate,
        create_interactive_map=config.output.create_interactive_map,
        create_qgis_styles=config.output.create_qgis_styles,
        random_seed=config.random_seed,
    )


def request_to_yaml_dict(request: PipelineRequest) -> dict[str, Any]:
    """Serialize a :class:`PipelineRequest` back into the ``default.yaml`` schema.

    Note: the QGIS plugin's actual "Export configuration YAML" action uses its
    own independent implementation (``settings.export_yaml``), not this
    function -- this one is exercised by ``tests/test_config.py`` as a
    round-trip check for the CLI's config schema.
    """
    paths: dict[str, Any] = {
        "aoi": str(request.aoi_path),
        "before_folder": str(request.before_folder),
        "after_folder": str(request.after_folder),
        "output_dir": str(request.output_dir),
    }
    if request.processed_dir:
        # Omitted (not defaulted to a relative string) when unset, so a
        # reloaded config keeps deriving it from output_dir at run time
        # instead of resolving a relative default against wherever this
        # YAML file happens to be saved.
        paths["processed_dir"] = str(request.processed_dir)
    return {
        "paths": paths,
        "preprocessing": {
            "normalization": request.normalization,
            "resampling": "bilinear",
            "reference_date": "before",
            "reflectance_scale": request.reflectance_scale,
            "nodata_value": request.nodata_value,
        },
        "change_detection": {
            "method": request.method,
            "threshold_method": request.threshold_method,
            "percentile": request.percentile,
            "manual_threshold": request.manual_threshold,
            "morphology": {
                "enabled": request.morphology_enabled,
                "operation": request.morphology_operation,
                "structure_size": request.morphology_kernel_size,
                "fill_holes": request.fill_holes,
            },
            "min_area_m2": request.min_area_m2,
        },
        "spatial_statistics": {
            "enabled": request.spatial_statistics_enabled,
            "grid_size_m": request.spatial_grid_size_m,
            "weights": request.spatial_weights,
            "knn_k": request.knn_k,
            "permutations": request.permutations,
            "alpha": request.alpha,
            "fdr_correction": request.fdr_correction,
            "random_seed": request.random_seed,
        },
        "spatial_ml": {
            "enabled": request.spatial_ml_enabled,
            "model": request.ml_model,
            "contamination": request.ml_contamination,
            "clustering": {
                "algorithm": "dbscan",
                "eps": request.dbscan_eps,
                "min_samples": request.dbscan_min_samples,
            },
            "random_seed": request.random_seed,
            "use_coordinates": request.ml_use_coordinates,
            "n_bootstrap": request.ml_n_bootstrap,
        },
        "output": {
            "write_stacks": request.write_stacks,
            "write_intermediate": request.write_intermediate,
            "create_interactive_map": request.create_interactive_map,
            "create_qgis_styles": request.create_qgis_styles,
        },
        "run": {"random_seed": request.random_seed},
    }
