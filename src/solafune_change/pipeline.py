"""End-to-end orchestration: the single entry point shared by the CLI and the
QGIS plugin.

``validate_request`` and ``run_pipeline`` are the only two functions a caller
needs. Both take a plain :class:`~solafune_change.types.PipelineRequest` and
accept a framework-independent progress callback / cancellation token —
nothing here imports Qt or QGIS.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np

from . import (
    baseline,
    cva,
    database,
    discovery,
    postprocessing,
    preprocessing,
    reporting,
    spatial_ml,
    thresholding,
    validation,
    vectorization,
    visualization,
)
from . import (
    spatial_statistics as ss,
)
from .errors import ConfigurationError, InputDiscoveryError
from .types import (
    CancellationToken,
    PipelineRequest,
    PipelineResult,
    ProgressCallback,
    ProgressEvent,
    ValidationReport,
)

logger = logging.getLogger(__name__)


def _emit(
    cb: ProgressCallback | None, stage: str, message: str, percent: float, severity: str = "info"
) -> None:
    if severity == "error":
        logger.error("[%5.1f%%] %s: %s", percent, stage, message)
    elif severity == "warning":
        logger.warning("[%5.1f%%] %s: %s", percent, stage, message)
    else:
        logger.info("[%5.1f%%] %s: %s", percent, stage, message)
    if cb is not None:
        cb(ProgressEvent(stage=stage, message=message, percent=percent, severity=severity))


def validate_request(request: PipelineRequest) -> ValidationReport:
    """Run all input/configuration checks without performing any analysis."""
    report = ValidationReport()

    before_folder = Path(request.before_folder)
    after_folder = Path(request.after_folder)
    if before_folder == after_folder:
        report.add("error", "same_folder", "Before and after folders must be different")

    before_bands = after_bands = None
    try:
        before_bands = discovery.discover_bands(before_folder)
    except InputDiscoveryError as exc:
        report.add("error", "before_discovery_failed", exc.user_message)
    try:
        after_bands = discovery.discover_bands(after_folder)
    except InputDiscoveryError as exc:
        report.add("error", "after_discovery_failed", exc.user_message)

    if before_bands and after_bands:
        before_label = discovery.extract_date_label(before_folder)
        after_label = discovery.extract_date_label(after_folder)
        detailed = validation.validate_inputs(
            before_bands, after_bands, Path(request.aoi_path), before_label, after_label
        )
        report.issues.extend(detailed.issues)
        report.band_metadata.extend(detailed.band_metadata)
        if before_label == after_label:
            report.add(
                "warning",
                "same_date_label",
                "Before and after folders resolved to the same date label",
            )

    try:
        Path(request.output_dir).mkdir(parents=True, exist_ok=True)
        probe = Path(request.output_dir) / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        report.add(
            "error",
            "output_dir_not_writable",
            f"Cannot write to output directory: {request.output_dir}",
            detail=str(exc),
        )

    if request.threshold_method == "manual" and request.manual_threshold is None:
        report.add(
            "error",
            "missing_manual_threshold",
            "threshold_method='manual' requires manual_threshold to be set",
        )
    if request.threshold_method == "percentile" and not (0.0 <= request.percentile <= 100.0):
        report.add(
            "error",
            "invalid_percentile",
            f"percentile must be within [0, 100], got {request.percentile}",
        )
    if request.min_area_m2 < 0:
        report.add("error", "invalid_min_area", "min_area_m2 must be >= 0")
    if request.spatial_statistics_enabled and request.spatial_grid_size_m <= 0:
        report.add("error", "invalid_grid_size", "spatial_grid_size_m must be > 0")
    if request.method not in ("baseline", "cva", "both"):
        report.add(
            "error",
            "invalid_method",
            f"method must be one of baseline|cva|both, got {request.method}",
        )

    return report


def run_pipeline(
    request: PipelineRequest,
    progress_callback: ProgressCallback | None = None,
    cancellation_token: CancellationToken | None = None,
) -> PipelineResult:
    """Run the full change-detection pipeline and return all output paths + a summary."""
    token = cancellation_token or CancellationToken()
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    run_id = _build_run_id(request.run_label, started)

    output_dir = Path(request.output_dir)
    processed_dir = (
        Path(request.processed_dir)
        if request.processed_dir
        else output_dir.parent / "data" / "processed"
    )
    figures_dir = output_dir / "figures"
    maps_dir = output_dir / "maps"
    db_dir = output_dir / "database"
    stats_dir = output_dir / "statistics"
    qgis_styles_dir = output_dir / "qgis" / "styles"
    for d in (output_dir, processed_dir, figures_dir, maps_dir, db_dir, stats_dir, qgis_styles_dir):
        d.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    quality_checks: list[dict] = []

    # --- 0-5%: discovery -----------------------------------------------------
    token.check("discovery")
    _emit(progress_callback, "discovery", "Locating B02/B03/B04 band files", 1.0)
    before_folder, after_folder = Path(request.before_folder), Path(request.after_folder)
    before_bands = discovery.discover_bands(before_folder)
    after_bands = discovery.discover_bands(after_folder)
    before_date = discovery.extract_date_label(before_folder)
    after_date = discovery.extract_date_label(after_folder)
    _emit(progress_callback, "discovery", f"Found bands for {before_date} and {after_date}", 5.0)

    # --- 5-12%: validation -----------------------------------------------------
    token.check("validation")
    _emit(progress_callback, "validation", "Validating CRS, dimensions and AOI overlap", 6.0)
    val_report = validation.validate_inputs(
        before_bands, after_bands, Path(request.aoi_path), before_date, after_date
    )
    for issue in val_report.issues:
        quality_checks.append(
            {
                "run_id": run_id,
                "check_name": issue.code,
                "severity": issue.severity,
                "message": issue.message,
                "context_json": issue.context,
            }
        )
        if issue.severity == "warning":
            warnings.append(issue.message)
    if not val_report.is_valid:
        error_msgs = "; ".join(i.message for i in val_report.errors)
        raise ConfigurationError("Input validation failed", detail=error_msgs)
    _emit(
        progress_callback,
        "validation",
        f"Validation passed with {len(val_report.warnings)} warning(s)",
        12.0,
    )

    # --- 12-22%: alignment -----------------------------------------------------
    token.check("alignment")
    _emit(progress_callback, "alignment", "Loading rasters and aligning to a common grid", 13.0)
    aoi_gdf = gpd.read_file(request.aoi_path)
    if not aoi_gdf.is_valid.all():
        aoi_gdf["geometry"] = aoi_gdf.geometry.buffer(0)
    aligned = preprocessing.build_aligned_inputs(
        before_bands,
        after_bands,
        before_date,
        after_date,
        aoi_gdf,
        nodata_value=request.nodata_value,
    )
    if aligned.resampled_after:
        warnings.append(
            f"{after_date} was reprojected/resampled onto the {before_date} reference grid (bilinear)."
        )
    grid = aligned.grid
    _emit(
        progress_callback,
        "alignment",
        f"Grid: {grid.width}x{grid.height} px @ {grid.pixel_size_x:.0f} m, "
        f"{int(aligned.combined_valid_mask.sum())} common valid pixels",
        22.0,
    )

    # --- 22-30%: stack creation -----------------------------------------------------
    token.check("stack")
    before_stack_path = after_stack_path = None
    if request.write_stacks:
        _emit(progress_callback, "stack", "Writing stacked GeoTIFFs (RGB band order)", 24.0)
        before_stack_path = processed_dir / f"sentinel2_{before_date}_stack.tif"
        after_stack_path = processed_dir / f"sentinel2_{after_date}_stack.tif"
        preprocessing.write_stack_geotiff(
            before_stack_path, aligned.before.dn, grid, request.nodata_value, dtype="uint16"
        )
        preprocessing.write_stack_geotiff(
            after_stack_path, aligned.after.dn, grid, request.nodata_value, dtype="uint16"
        )
    _emit(progress_callback, "stack", "Stack creation complete", 30.0)

    # --- 30-42%: radiometric normalization -----------------------------------------------------
    token.check("normalization")
    _emit(
        progress_callback,
        "normalization",
        f"Applying '{request.normalization}' normalization",
        31.0,
    )
    before_refl = preprocessing.to_reflectance(aligned.before.dn, request.reflectance_scale)
    after_refl = preprocessing.to_reflectance(aligned.after.dn, request.reflectance_scale)
    after_norm, norm_meta = preprocessing.apply_normalization(
        request.normalization, before_refl, after_refl, aligned.combined_valid_mask
    )
    _emit(progress_callback, "normalization", "Normalization complete", 42.0)

    # --- 42-55%: baseline -----------------------------------------------------
    token.check("baseline")
    baseline_intensity_path = baseline_binary_path = None
    baseline_result = None
    bl_threshold = None
    if request.method in ("baseline", "both"):
        _emit(
            progress_callback,
            "baseline",
            "Computing baseline change intensity (Euclidean distance)",
            44.0,
        )
        baseline_result = baseline.compute_baseline_change(
            before_refl, after_refl, aligned.combined_valid_mask
        )
        bl_threshold = thresholding.compute_threshold(
            baseline_result.intensity, aligned.combined_valid_mask, method="otsu"
        )
        bl_morphed = postprocessing.apply_morphology(
            bl_threshold.binary,
            request.morphology_operation if request.morphology_enabled else "none",
            request.morphology_kernel_size,
        )
        min_px = postprocessing.min_area_to_pixel_count(request.min_area_m2, grid.pixel_area_m2)
        bl_post = postprocessing.filter_min_area(bl_morphed, min_px, fill_holes=request.fill_holes)

        if request.write_intermediate:
            baseline_intensity_path = processed_dir / "baseline_change_intensity.tif"
            baseline_binary_path = processed_dir / "baseline_change_binary.tif"
            preprocessing.write_single_band_geotiff(
                baseline_intensity_path,
                baseline_result.intensity,
                grid,
                -9999.0,
                "float32",
                aligned.combined_valid_mask,
                description="Baseline change intensity [0,1]",
            )
            preprocessing.write_single_band_geotiff(
                baseline_binary_path,
                bl_post.binary.astype("uint8"),
                grid,
                255,
                "uint8",
                aligned.combined_valid_mask,
                build_overviews=False,
                description="Baseline binary change (1=changed)",
            )
    _emit(progress_callback, "baseline", "Baseline detection complete", 55.0)

    # --- 55-68%: robust CVA -----------------------------------------------------
    token.check("cva")
    cva_intensity_path = cva_binary_path = None
    cva_result = None
    cva_threshold = None
    cva_post = None
    if request.method in ("cva", "both"):
        _emit(progress_callback, "cva", "Computing robust RGB Change Vector Analysis", 57.0)
        cva_result = cva.compute_robust_cva(before_refl, after_norm, aligned.combined_valid_mask)
    _emit(progress_callback, "cva", "Robust CVA complete", 68.0)

    # --- 68-75%: threshold + morphology -----------------------------------------------------
    token.check("threshold")
    primary_intensity = primary_labels = primary_binary = None
    primary_method_name = "cva" if cva_result is not None else "baseline"
    if cva_result is not None:
        _emit(
            progress_callback,
            "threshold",
            f"Thresholding CVA with method='{request.threshold_method}'",
            70.0,
        )
        cva_threshold = thresholding.compute_threshold(
            cva_result.cva,
            aligned.combined_valid_mask,
            method=request.threshold_method,
            percentile=request.percentile,
            manual_value=request.manual_threshold,
        )
        cva_morphed = postprocessing.apply_morphology(
            cva_threshold.binary,
            request.morphology_operation if request.morphology_enabled else "none",
            request.morphology_kernel_size,
        )
        min_px = postprocessing.min_area_to_pixel_count(request.min_area_m2, grid.pixel_area_m2)
        cva_post = postprocessing.filter_min_area(
            cva_morphed, min_px, fill_holes=request.fill_holes
        )

        if request.write_intermediate:
            cva_intensity_path = processed_dir / "cva_change_intensity.tif"
            cva_binary_path = processed_dir / "cva_change_binary.tif"
            preprocessing.write_single_band_geotiff(
                cva_intensity_path,
                cva_result.cva,
                grid,
                -9999.0,
                "float32",
                aligned.combined_valid_mask,
                description="Robust CVA magnitude",
            )
            preprocessing.write_single_band_geotiff(
                cva_binary_path,
                cva_post.binary.astype("uint8"),
                grid,
                255,
                "uint8",
                aligned.combined_valid_mask,
                build_overviews=False,
                description="CVA binary change (1=changed)",
            )

        primary_intensity, primary_labels, primary_binary = (
            cva_result.cva,
            cva_post.labels,
            cva_post.binary,
        )
    elif baseline_result is not None:
        # primary_method_name is already "baseline" here (set above from
        # `"cva" if cva_result is not None else "baseline"`).
        primary_intensity, primary_labels, primary_binary = (
            baseline_result.intensity,
            bl_post.labels,
            bl_post.binary,
        )
    _emit(progress_callback, "threshold", "Threshold and morphology complete", 75.0)

    # --- 75-82%: vectorization -----------------------------------------------------
    token.check("vectorization")
    _emit(progress_callback, "vectorization", "Polygonizing final change raster", 76.0)
    threshold_value = cva_threshold.value if cva_threshold else bl_threshold.value
    threshold_method_used = cva_threshold.method if cva_threshold else bl_threshold.method
    change_features, vec_summary = vectorization.polygonize_change(
        primary_labels,
        primary_intensity,
        grid,
        aoi_gdf,
        before_date,
        after_date,
        primary_method_name,
        threshold_method_used,
        threshold_value,
        request.min_area_m2,
    )
    _emit(
        progress_callback,
        "vectorization",
        f"{len(change_features)} change polygons after filtering",
        82.0,
    )

    # --- 82-90%: spatial statistics -----------------------------------------------------
    token.check("spatial_statistics")
    grid_gdf = None
    global_moran = None
    if request.spatial_statistics_enabled and cva_result is not None:
        _emit(
            progress_callback,
            "spatial_statistics",
            f"Building {request.spatial_grid_size_m:.0f} m analysis grid",
            83.0,
        )
        grid_gdf = ss.build_analysis_grid(
            grid,
            aligned.combined_valid_mask,
            primary_binary,
            cva_result.cva,
            cva_result.band_diff,
            request.spatial_grid_size_m,
        )
        token.check("spatial_statistics")
        _emit(progress_callback, "spatial_statistics", "Computing Global Moran's I", 85.0)
        global_moran = ss.compute_global_moran(
            grid_gdf,
            "mean_cva",
            weights_type=request.spatial_weights,
            knn_k=request.knn_k,
            permutations=request.permutations,
            row_standardize=request.row_standardization,
            seed=request.random_seed,
        )
        _emit(
            progress_callback,
            "spatial_statistics",
            "Computing Local Moran's I and Getis-Ord Gi*",
            87.0,
        )
        grid_gdf = ss.compute_local_statistics(
            grid_gdf,
            "mean_cva",
            weights_type=request.spatial_weights,
            knn_k=request.knn_k,
            permutations=request.permutations,
            alpha=request.alpha,
            fdr_correction=request.fdr_correction,
            seed=request.random_seed,
        )
        change_features = ss.attach_grid_attributes_to_features(change_features, grid_gdf)
    elif request.spatial_statistics_enabled:
        warnings.append(
            "Spatial statistics require the CVA result; skipped because method='baseline' only."
        )
    _emit(progress_callback, "spatial_statistics", "Spatial statistics complete", 90.0)

    # --- 90-94%: experimental spatial ML -----------------------------------------------------
    token.check("spatial_ml")
    ml_result = None
    if request.spatial_ml_enabled:
        if grid_gdf is None:
            warnings.append("Experimental spatial ML requires spatial statistics; skipped.")
        else:
            _emit(
                progress_callback, "spatial_ml", f"Running {request.ml_model} (experimental)", 91.0
            )
            if request.ml_model == "isolation_forest":
                ml_result = spatial_ml.run_isolation_forest(
                    grid_gdf,
                    contamination=request.ml_contamination,
                    n_estimators=request.ml_n_estimators,
                    use_coordinates=request.ml_use_coordinates,
                    random_seed=request.random_seed,
                    n_bootstrap=request.ml_n_bootstrap,
                )
            else:
                changed_cells = grid_gdf[grid_gdf["changed_proportion"] > 0].copy()
                if len(changed_cells) >= 20:
                    ml_result = spatial_ml.run_dbscan_clustering(
                        changed_cells,
                        eps=request.dbscan_eps,
                        min_samples=request.dbscan_min_samples,
                        use_coordinates=True,
                        random_seed=request.random_seed,
                    )
                    merged = grid_gdf.drop(columns=["ml_cluster_id"], errors="ignore").merge(
                        ml_result.grid[
                            [
                                "grid_id",
                                "ml_cluster_id",
                                "ml_anomaly_score",
                                "ml_anomaly_rank",
                                "ml_anomaly_quantile",
                            ]
                        ],
                        on="grid_id",
                        how="left",
                    )
                    ml_result.grid = gpd.GeoDataFrame(merged, geometry="geometry", crs=grid_gdf.crs)
                else:
                    warnings.append(
                        f"Too few changed cells ({len(changed_cells)}) for DBSCAN clustering; skipped."
                    )
            if ml_result is not None:
                grid_gdf = ml_result.grid
                change_features = ss.attach_grid_attributes_to_features(change_features, grid_gdf)
    _emit(progress_callback, "spatial_ml", "Experimental spatial ML complete", 94.0)

    # --- confidence scoring -----------------------------------------------------
    change_features = vectorization.compute_confidence(change_features, threshold_value)

    # --- 94-97%: database and visualization -----------------------------------------------------
    token.check("database")
    _emit(progress_callback, "database", "Writing GeoPackage", 94.5)
    gpkg_path = db_dir / "change_analysis.gpkg"
    run_metadata_row = {
        "run_id": run_id,
        "run_timestamp": started.isoformat(),
        "before_folder": str(before_folder),
        "after_folder": str(after_folder),
        "before_date": before_date,
        "after_date": after_date,
        "aoi_path": str(request.aoi_path),
        "crs": str(grid.crs),
        "pixel_size_m": grid.pixel_size_x,
        "method": primary_method_name,
        "normalization": request.normalization,
        "threshold_method": threshold_method_used,
        "threshold_value": threshold_value,
        "min_area_m2": request.min_area_m2,
        "spatial_statistics_enabled": request.spatial_statistics_enabled,
        "spatial_grid_size_m": request.spatial_grid_size_m,
        "spatial_ml_enabled": request.spatial_ml_enabled,
        "package_version": _package_version(),
        "random_seed": request.random_seed,
        "output_paths_json": {},
    }
    database.write_geopackage(
        gpkg_path, change_features, grid_gdf, run_metadata_row, quality_checks
    )

    interactive_map_path = None
    static_figure_path = None
    qml_paths: dict[str, Path] = {}
    if request.create_qgis_styles and cva_result is not None:
        cva_valid = cva_result.cva[aligned.combined_valid_mask]
        vmax = float(np.percentile(cva_valid, 98)) if cva_valid.size else 1.0
        style_paths = visualization.generate_all_styles(
            qgis_styles_dir, cva_vmin=0.0, cva_vmax=max(vmax, 1e-3)
        )
        qml_paths = style_paths

    _emit(
        progress_callback,
        "database",
        "Rendering static comparison figure and interactive map",
        95.5,
    )
    before_stretch = visualization.compute_rgb_stretch(
        aligned.before.dn, aligned.combined_valid_mask
    )
    before_rgb = visualization.apply_rgb_stretch(
        aligned.before.dn, before_stretch, aligned.combined_valid_mask
    )
    after_rgb = visualization.apply_rgb_stretch(
        aligned.after.dn, before_stretch, aligned.combined_valid_mask
    )

    if cva_result is not None and baseline_result is not None:
        visualization.plot_static_comparison(
            before_rgb,
            after_rgb,
            baseline_result.intensity,
            cva_result.cva,
            change_features,
            grid_gdf,
            aoi_gdf,
            grid.bounds,
            before_date,
            after_date,
            threshold_method_used,
            figures_dir / "change_comparison.png",
        )
        static_figure_path = figures_dir / "change_comparison.png"

    if request.create_interactive_map:
        visualization.create_interactive_map(
            aoi_gdf,
            before_rgb,
            after_rgb,
            str(grid.crs),
            grid.bounds,
            change_features,
            grid_gdf,
            maps_dir / "interactive_map.html",
            before_date,
            after_date,
        )
        interactive_map_path = maps_dir / "interactive_map.html"
    _emit(progress_callback, "database", "Visualization complete", 97.0)

    # --- 97-100%: report and manifest -----------------------------------------------------
    token.check("report")
    _emit(progress_callback, "report", "Writing summary, manifest and report", 98.0)
    runtime_seconds = time.perf_counter() - t0

    valid_area_m2 = int(aligned.combined_valid_mask.sum()) * grid.pixel_area_m2
    summary = _build_summary(
        before_date,
        after_date,
        primary_method_name,
        threshold_method_used,
        threshold_value,
        change_features,
        global_moran,
        request.random_seed,
        runtime_seconds,
        valid_area_m2,
    )
    summary_path = output_dir / "summary.json"
    reporting.write_json(summary_path, summary)

    manifest = reporting.build_run_manifest(
        run_id,
        request,
        before_bands,
        after_bands,
        before_date,
        after_date,
        str(grid.crs),
        grid.pixel_size_x,
        started,
        runtime_seconds,
        output_paths={
            "before_stack": str(before_stack_path) if before_stack_path else None,
            "after_stack": str(after_stack_path) if after_stack_path else None,
            "cva_intensity": str(cva_intensity_path) if cva_intensity_path else None,
            "cva_binary": str(cva_binary_path) if cva_binary_path else None,
            "baseline_intensity": str(baseline_intensity_path) if baseline_intensity_path else None,
            "baseline_binary": str(baseline_binary_path) if baseline_binary_path else None,
            "database": str(gpkg_path),
            "static_figure": str(static_figure_path) if static_figure_path else None,
            "interactive_map": str(interactive_map_path) if interactive_map_path else None,
        },
        package_version=_package_version(),
    )
    manifest_path = output_dir / "run_manifest.json"
    reporting.write_json(manifest_path, manifest)

    quality_report_path = output_dir / "quality_report.json"
    reporting.write_json(
        quality_report_path,
        {
            "run_id": run_id,
            "status": val_report.status,
            "issues": val_report.to_dict()["issues"],
            "warnings": warnings,
        },
    )

    spatial_stats_csv_path = None
    global_moran_json_path = None
    if grid_gdf is not None:
        spatial_stats_csv_path = stats_dir / "spatial_statistics.csv"
        grid_gdf.drop(columns="geometry").to_csv(spatial_stats_csv_path, index=False)
        grid_gdf.to_file(maps_dir / "spatial_statistics.gpkg", layer="spatial_grid", driver="GPKG")
    if global_moran is not None:
        global_moran_json_path = stats_dir / "global_moran.json"
        reporting.write_json(global_moran_json_path, global_moran.to_dict())

    report_context = _build_report_context(
        before_date,
        after_date,
        aoi_gdf,
        request,
        grid,
        aligned,
        threshold_method_used,
        threshold_value,
        norm_meta,
        baseline_result,
        bl_threshold,
        cva_result,
        change_features,
        grid_gdf,
        global_moran,
        ml_result,
        vec_summary,
        val_report,
        run_id,
        runtime_seconds,
    )
    report_md = reporting.render_report_markdown(report_context)
    report_path = output_dir / "report.md"
    reporting.write_text(report_path, report_md)

    _emit(progress_callback, "report", "Run complete", 100.0)

    return PipelineResult(
        run_id=run_id,
        output_dir=output_dir,
        before_date=before_date,
        after_date=after_date,
        before_stack=before_stack_path,
        after_stack=after_stack_path,
        baseline_intensity=baseline_intensity_path,
        baseline_binary=baseline_binary_path,
        cva_intensity=cva_intensity_path,
        cva_binary=cva_binary_path,
        change_features=gpkg_path,
        spatial_grid_gpkg=(maps_dir / "spatial_statistics.gpkg") if grid_gdf is not None else None,
        global_moran_json=global_moran_json_path,
        spatial_statistics_csv=spatial_stats_csv_path,
        database=gpkg_path,
        summary_json=summary_path,
        run_manifest_json=manifest_path,
        quality_report_json=quality_report_path,
        report_md=report_path,
        static_figure_png=static_figure_path,
        interactive_map_html=interactive_map_path,
        qml_styles=qml_paths,
        summary=summary,
        warnings=warnings,
        runtime_seconds=runtime_seconds,
    )


def _build_run_id(run_label: str, started: datetime) -> str:
    """Build a run id, prefixed with a sanitized user-supplied label when one is given.

    ``run_label`` (surfaced in the CLI's ``--config`` YAML and the QGIS
    dock's "Run label" field) is purely cosmetic otherwise, so it is folded
    into the run id here to make layer-group names and GeoPackage
    ``run_metadata`` rows recognizable across multiple runs instead of being
    accepted but silently dropped.
    """
    timestamp = f"{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    label = (run_label or "").strip()
    if not label or label.lower() == "run":
        return timestamp
    safe_label = re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-")[:40]
    return f"{safe_label}-{timestamp}" if safe_label else timestamp


def _package_version() -> str:
    from . import __version__

    return __version__


def _build_summary(
    before_date,
    after_date,
    method,
    threshold_method,
    threshold_value,
    change_features,
    global_moran,
    seed,
    runtime_seconds,
    valid_area_m2,
) -> dict:
    total_area = float(change_features["area_m2"].sum()) if not change_features.empty else 0.0
    return {
        "date_before": before_date,
        "date_after": after_date,
        "method": method,
        "threshold_method": threshold_method,
        "threshold": threshold_value,
        "changed_area_m2": total_area,
        "changed_area_percent": (100.0 * total_area / valid_area_m2) if valid_area_m2 else 0.0,
        "feature_count": int(len(change_features)),
        "global_moran_i": global_moran.moran_i if global_moran else None,
        "global_moran_p": global_moran.p_sim if global_moran else None,
        "hotspot_95_count": (
            int((change_features["hotspot_class"].isin(["hot_95", "hot_99"])).sum())
            if "hotspot_class" in change_features.columns and not change_features.empty
            else 0
        ),
        "largest_change_area_m2": (
            float(change_features["area_m2"].max()) if not change_features.empty else 0.0
        ),
        "runtime_seconds": runtime_seconds,
        "random_seed": seed,
    }


def _build_report_context(
    before_date,
    after_date,
    aoi_gdf,
    request,
    grid,
    aligned,
    threshold_method,
    threshold_value,
    norm_meta,
    baseline_result,
    bl_threshold,
    cva_result,
    change_features,
    grid_gdf,
    global_moran,
    ml_result,
    vec_summary,
    val_report,
    run_id,
    runtime_seconds,
) -> dict:
    aoi_area_km2 = float(aoi_gdf.to_crs(grid.crs).area.sum()) / 1e6
    total_area = float(change_features["area_m2"].sum()) if not change_features.empty else 0.0
    valid_count = int(aligned.combined_valid_mask.sum())
    changed_pct = 100.0 * total_area / (valid_count * grid.pixel_area_m2) if valid_count else 0.0

    if not change_features.empty:
        top5 = change_features.nlargest(5, "area_m2")[
            ["id", "area_m2", "mean_change", "confidence", "hotspot_class"]
        ]
        rows = "\n".join(
            f"| {r.id} | {r.area_m2:,.0f} | {r.mean_change:.3f} | {r.confidence:.2f} | {r.hotspot_class or 'N/A'} |"
            for r in top5.itertuples()
        )
        largest_table = (
            "| ID | Area (m2) | Mean change | Confidence | Gi* class |\n|---|---|---|---|---|\n"
            + rows
        )
    else:
        largest_table = "_No change features were detected above the configured threshold._"

    if global_moran:
        gm = global_moran
        interp = (
            "positive spatial autocorrelation — changed pixels cluster spatially rather than appearing at random locations"
            if gm.moran_i > 0 and gm.p_sim < request.alpha
            else "no statistically significant spatial clustering at the configured alpha level"
        )
    else:
        interp = "spatial statistics were not computed"

    baseline_pct = (
        100.0
        * float(
            (baseline_result.intensity[aligned.combined_valid_mask] > bl_threshold.value).mean()
        )
        if baseline_result is not None and bl_threshold is not None
        else 0.0
    )
    cva_pct = (
        100.0 * float(np.mean(cva_result.cva[aligned.combined_valid_mask] > threshold_value))
        if cva_result is not None
        else 0.0
    )

    lisa_counts = (
        grid_gdf["lisa_cluster"].value_counts().to_dict()
        if grid_gdf is not None and "lisa_cluster" in grid_gdf.columns
        else {}
    )
    hotspot_counts = (
        grid_gdf["hotspot_class"].value_counts().to_dict()
        if grid_gdf is not None and "hotspot_class" in grid_gdf.columns
        else {}
    )

    if ml_result is not None:
        overlap = ml_result.stability.get("mean_top_k_overlap")
        overlap_str = f"{overlap:.2f}" if isinstance(overlap, (int, float)) else "N/A"
        ml_note = (
            f"{ml_result.model} over {len(ml_result.grid)} grid cells; "
            f"top-K anomaly stability: {overlap_str}. "
            "Exploratory ranking only; no ground truth to validate against."
        )
    else:
        ml_note = "not run (spatial_ml_enabled=False or an earlier stage skipped it)"

    return {
        "before_date": before_date,
        "after_date": after_date,
        "aoi_area_km2": aoi_area_km2,
        "threshold_method": threshold_method,
        "threshold_value": threshold_value,
        "changed_area_m2": total_area,
        "changed_area_percent": changed_pct,
        "feature_count": len(change_features),
        "global_moran_i": global_moran.moran_i if global_moran else float("nan"),
        "global_moran_ei": global_moran.expected_i if global_moran else float("nan"),
        "global_moran_z": global_moran.z_score if global_moran else float("nan"),
        "global_moran_p": global_moran.p_sim if global_moran else float("nan"),
        "grid_size_m": request.spatial_grid_size_m,
        "moran_interpretation": interp,
        "hotspot_95_count": (
            int((change_features["hotspot_class"].isin(["hot_95", "hot_99"])).sum())
            if "hotspot_class" in change_features.columns and not change_features.empty
            else 0
        ),
        "crs": str(grid.crs),
        "pixel_size_m": grid.pixel_size_x,
        "width": grid.width,
        "height": grid.height,
        "bounds": tuple(round(v, 1) for v in grid.bounds),
        "nodata": request.nodata_value,
        "nodata_pct": 100.0 * (1 - aligned.before.valid_mask.mean()),
        "quality_summary": f"{len(val_report.warnings)} warning(s), {len(val_report.errors)} error(s) (see quality_report.json)",
        "normalization": request.normalization,
        "morphology_desc": (
            f"{request.morphology_operation} (kernel={request.morphology_kernel_size}px)"
            if request.morphology_enabled
            else "disabled"
        ),
        "min_area_m2": request.min_area_m2,
        "min_area_px": postprocessing.min_area_to_pixel_count(
            request.min_area_m2, grid.pixel_area_m2
        ),
        "n_grid_cells": len(grid_gdf) if grid_gdf is not None else 0,
        "weights_type": request.spatial_weights,
        "permutations": request.permutations,
        "random_seed": request.random_seed,
        "fdr_status": "enabled" if request.fdr_correction else "disabled",
        "ml_status": (
            f"{request.ml_model} enabled"
            if request.spatial_ml_enabled
            else "disabled (opt-in only)"
        ),
        "database_path": "outputs/database/change_analysis.gpkg",
        "baseline_changed_pct": baseline_pct,
        "cva_changed_pct": cva_pct,
        "baseline_vs_cva_note": (
            "CVA's robust per-band standardization generally yields a more spatially coherent result than the "
            "baseline's unnormalized, globally min-max-scaled distance (see Global Moran's I above)."
            if cva_result is not None and baseline_result is not None
            else ""
        ),
        "largest_features_table": largest_table,
        "lisa_counts": lisa_counts,
        "hotspot_counts": hotspot_counts,
        "ml_results_note": ml_note,
        "run_id": run_id,
        "package_version": _package_version(),
    }
