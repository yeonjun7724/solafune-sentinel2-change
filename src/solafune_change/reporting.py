"""Run manifest, quality report, summary.json, and report.md generation.

Every number that ends up in ``report.md`` is read back from the
``summary`` dict produced during the actual pipeline run (or, for the
standalone ``solafune-change report`` command, from a previously written
``summary.json``) — nothing here is invented independently of a completed run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .atomic import atomic_output

logger = logging.getLogger(__name__)


def file_checksum(path: Path, algorithm: str = "sha256", chunk_size: int = 1 << 20) -> str:
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def package_versions() -> dict[str, str]:
    versions = {}
    for mod_name in (
        "numpy",
        "pandas",
        "rasterio",
        "geopandas",
        "shapely",
        "pyproj",
        "scipy",
        "skimage",
        "sklearn",
        "libpysal",
        "esda",
        "folium",
        "yaml",
    ):
        try:
            mod = __import__(mod_name)
            versions[mod_name] = getattr(mod, "__version__", "unknown")
        except ImportError:
            versions[mod_name] = "not installed"
    return versions


def write_json(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    with atomic_output(path) as tmp_path:
        tmp_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote %s", path)


def write_text(path: Path, content: str) -> None:
    path = Path(path)
    with atomic_output(path) as tmp_path:
        tmp_path.write_text(content, encoding="utf-8")
    logger.info("Wrote %s", path)


def build_run_manifest(
    run_id: str,
    request: Any,
    before_paths: dict[str, Path],
    after_paths: dict[str, Path],
    before_date: str,
    after_date: str,
    crs: str,
    pixel_size_m: float,
    started_at: datetime,
    runtime_seconds: float,
    output_paths: dict[str, str],
    package_version: str,
) -> dict[str, Any]:
    input_checksums = {f"before_{k}": file_checksum(v) for k, v in before_paths.items()}
    input_checksums.update({f"after_{k}": file_checksum(v) for k, v in after_paths.items()})

    return {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "runtime_seconds": runtime_seconds,
        "before_date": before_date,
        "after_date": after_date,
        "inputs": {
            "before_folder": str(request.before_folder),
            "after_folder": str(request.after_folder),
            "aoi_path": str(request.aoi_path),
            "checksums": input_checksums,
        },
        "grid": {"crs": crs, "pixel_size_m": pixel_size_m},
        "parameters": {
            "method": request.method,
            "normalization": request.normalization,
            "reflectance_scale": request.reflectance_scale,
            "threshold_method": request.threshold_method,
            "percentile": request.percentile,
            "manual_threshold": request.manual_threshold,
            "morphology_enabled": request.morphology_enabled,
            "morphology_operation": request.morphology_operation,
            "morphology_kernel_size": request.morphology_kernel_size,
            "min_area_m2": request.min_area_m2,
            "spatial_statistics_enabled": request.spatial_statistics_enabled,
            "spatial_grid_size_m": request.spatial_grid_size_m,
            "spatial_weights": request.spatial_weights,
            "permutations": request.permutations,
            "alpha": request.alpha,
            "fdr_correction": request.fdr_correction,
            "spatial_ml_enabled": request.spatial_ml_enabled,
            "ml_model": request.ml_model,
            "random_seed": request.random_seed,
        },
        "environment": {
            "python_version": sys.version,
            "platform": platform.platform(),
            "package_versions": package_versions(),
        },
        "package_version": package_version,
        "output_paths": output_paths,
    }


REPORT_TEMPLATE = """# Sentinel-2 Change Analysis Report

## 1. Executive Summary

- **Dates compared:** {before_date} vs {after_date}
- **AOI:** open-pit mining site, Zambia (`inputs/aoi.geojson`), area ~{aoi_area_km2:.2f} km^2
- **Primary method:** Robust RGB Change Vector Analysis (CVA) over B04/B03/B02, threshold = {threshold_method} ({threshold_value:.4f})
- **Total detected change area:** {changed_area_m2:,.0f} m^2 ({changed_area_percent:.2f}% of the valid AOI)
- **Change features (polygons):** {feature_count}
- **Key spatial pattern:** Global Moran's I = {global_moran_i:.3f} (permutation p = {global_moran_p:.4f}) on mean CVA per {grid_size_m:.0f} m analysis cell —
  {moran_interpretation}
- **95%+ Gi\\* hotspot cells:** {hotspot_95_count}
- **Important limitation:** no ground truth exists for this AOI; all figures below are descriptive/exploratory, not validated accuracy.

## 2. Data

- **Bands used:** B02 (Blue), B03 (Green), B04 (Red) — 10 m Sentinel-2, already clipped to the AOI.
- **CRS:** {crs} ({pixel_size_m:.0f} m pixel size); grid: {width} x {height} pixels.
- **Extent (working CRS):** {bounds}
- **NoData:** {nodata} ({nodata_pct:.2f}% of the raster footprint outside the AOI polygon).
- **Quality checks:** {quality_summary}

## 3. Method

1. **Baseline** — an independent reimplementation of the idea in `inputs/example_change_detection.py`: per-pixel multi-band Euclidean distance, min-max normalized to [0, 1] over the AOI/valid mask. No radiometric normalization is applied (mirrors the example's implicit assumption).
2. **Radiometric normalization** — `{normalization}` applied to the "after" date before CVA, using only pixels valid in both dates and inside the AOI to estimate the transform. See README "Radiometric Normalization" for the full rationale and limitations.
3. **Robust RGB CVA** — per-band differences standardized with median/MAD (MAD-near-zero pixels fall back to standard deviation; see `cva.py`), combined as `sqrt(sum(z_b^2))`.
4. **Threshold** — `{threshold_method}` on the CVA raster (value = {threshold_value:.4f}), computed over valid pixels only.
5. **Morphology / cleanup** — {morphology_desc}; minimum change area = {min_area_m2:.0f} m^2 ({min_area_px} px).
6. **Vectorization** — 8-connectivity polygonization, clipped to the AOI, invalid geometries repaired with `buffer(0)`, area/perimeter computed directly in EPSG:32735 (already a projected CRS appropriate for this AOI).
7. **Spatial statistics** — {grid_size_m:.0f} m regular analysis grid ({n_grid_cells} cells), {weights_type} contiguity weights (row-standardized for Moran's I, binary for Gi\\*), {permutations} permutations, seed={random_seed}, Benjamini-Hochberg FDR correction {fdr_status} on Gi\\* p-values.
8. **Experimental spatial ML** — {ml_status}.
9. **Database** — results written to a GeoPackage (SQLite-based OGC format) at `{database_path}`.

## 4. Results

- **Baseline vs. CVA:** baseline flags {baseline_changed_pct:.2f}% of valid pixels above its own Otsu-style threshold; CVA flags {cva_changed_pct:.2f}% above `{threshold_method}` = {threshold_value:.4f}. {baseline_vs_cva_note}
- **Change area / feature count:** {feature_count} polygons totalling {changed_area_m2:,.0f} m^2 ({changed_area_percent:.2f}% of AOI).
- **Largest change objects (top 5 by area):**

{largest_features_table}

- **Global Moran's I:** I = {global_moran_i:.4f}, E[I] = {global_moran_ei:.4f}, z = {global_moran_z:.2f}, permutation p = {global_moran_p:.4f} ({permutations} permutations, seed={random_seed}).
- **Local Moran's I (LISA) cluster counts:** {lisa_counts}
- **Getis-Ord Gi\\* hotspot counts:** {hotspot_counts}
- **Experimental ML anomaly results:** {ml_results_note}

## 5. Interpretation

The AOI is an active open-pit mining site. Spatially coherent, high-magnitude RGB change consistent with the observed patterns **may indicate**:

- Open-pit excavation expansion or bench advancement
- Newly exposed soil or rock surfaces
- Waste-rock or tailings deposition/redistribution
- Haul-road construction or resurfacing / operational surface changes
- Moisture or water-extent variation (pit water, settling ponds)
- Vegetation removal at the pit margins

RGB imagery from two dates alone **cannot distinguish** between these causes, and cannot rule out illumination/haze/shadow or (small) co-registration artifacts contributing to some detections. Detections are reported as *consistent with* surface disturbance, not as a confirmed land-cover transition.

## 6. Limitations

- Only B02/B03/B04 were provided; **NDVI could not be computed** (requires a NIR band such as B08).
- No cloud mask / Scene Classification Layer (SCL) was provided; cloud/shadow contamination cannot be explicitly excluded.
- Only two dates are available, so seasonal and transient (non-mining) surface change cannot be separated from persistent change.
- No ground-truth labels exist for this AOI; no accuracy/precision/recall is computed or claimed anywhere in this project.
- `confidence` is a documented heuristic score (see README), **not** a calibrated probability.
- The spatial-ML results (`spatial_ml.py`) are exploratory anomaly rankings/clusters, not validated predictions — no train/test or cross-validation score is reported because neighboring grid cells are spatially autocorrelated (confirmed by the Global Moran's I result above) and would leak information across any naive split.
- Statistical significance (Gi\\*/Moran's I p-values) describes spatial pattern, not land-use cause.

## 7. Operational Recommendations

- Acquire a denser Sentinel-2 time series (monthly or better) to separate persistent change from noise/seasonality.
- Use B08 (NIR) and SCL to add NDVI and cloud/shadow masking.
- Validate top-confidence / top-hotspot / top-anomaly features against high-resolution imagery or field visits before any operational decision.
- Track change persistence across >=3 consecutive acquisitions before treating a detection as an operational alert.
- For production monitoring: add automated cloud/shadow filtering, a persistent per-pixel baseline (e.g. a rolling median), and alerting thresholds tuned against a small manually-reviewed validation set.

---
*Generated by `solafune-change report` — run id `{run_id}`, package version `{package_version}`.*
"""


def render_report_markdown(context: dict[str, Any]) -> str:
    return REPORT_TEMPLATE.format(**context)
