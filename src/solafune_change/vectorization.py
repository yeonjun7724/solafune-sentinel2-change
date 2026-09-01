"""Polygonize a filtered binary change raster into change-feature polygons.

Multipart policy: raster regions are extracted with 8-connectivity (matching
the connected-component labeling in :mod:`solafune_change.postprocessing`) and
any polygon parts sharing the same component label are merged with
``unary_union`` into one feature — so a component that is a single
8-connected blob always becomes one row, even if it happens to touch itself
only at pixel corners (which 4-connectivity vectorization would otherwise
split into a MultiPolygon). If ``unary_union`` still yields a MultiPolygon
(disjoint parts sharing a label cannot occur from a true connected-component
labeling, but the check is kept as a safety net) it is stored as-is rather
than silently exploded, so one row = one connected component.

Area and perimeter are computed directly in the working CRS (EPSG:32735,
UTM Zone 35S), which is the CRS the input imagery is already delivered in.
UTM 35S is an appropriate equal-enough-area projected CRS for this AOI (an
open-pit mine in Zambia that falls inside zone 35S), so no further
reprojection is performed for area calculations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union

from .preprocessing import GridSpec

logger = logging.getLogger(__name__)

CHANGE_FEATURE_COLUMNS: tuple[str, ...] = (
    "id",
    "date_before",
    "date_after",
    "method",
    "threshold_method",
    "threshold_value",
    "area_m2",
    "perimeter_m",
    "compactness",
    "mean_change",
    "max_change",
    "p95_change",
    "confidence",
    "gi_zscore",
    "gi_pvalue",
    "gi_qvalue",
    "hotspot_class",
    "lisa_cluster",
    "ml_anomaly_score",
    "ml_cluster_id",
    "geometry",
)


@dataclass
class VectorizationSummary:
    n_raw_components: int
    n_after_aoi_clip: int
    n_after_min_area: int


def polygonize_change(
    labels: np.ndarray,
    intensity: np.ndarray,
    grid: GridSpec,
    aoi_gdf: gpd.GeoDataFrame,
    date_before: str,
    date_after: str,
    method: str,
    threshold_method: str,
    threshold_value: float,
    min_area_m2: float,
) -> tuple[gpd.GeoDataFrame, VectorizationSummary]:
    """Convert a labeled connected-component raster into change-feature polygons.

    Parameters
    ----------
    labels:
        (H, W) int array of connected-component labels (0 = background),
        already morphology- and min-pixel-count-filtered.
    intensity:
        (H, W) float array (the CVA or baseline intensity) used to compute
        per-feature mean/max/p95 change statistics.
    """
    if labels.max() == 0:
        empty = gpd.GeoDataFrame(columns=CHANGE_FEATURE_COLUMNS, geometry="geometry", crs=grid.crs)
        return empty, VectorizationSummary(0, 0, 0)

    shape_gen = features.shapes(labels, mask=labels > 0, connectivity=8, transform=grid.transform)
    parts_by_label: dict[int, list] = {}
    for geom_json, value in shape_gen:
        label_id = int(value)
        parts_by_label.setdefault(label_id, []).append(shape(geom_json))
    n_raw = len(parts_by_label)

    aoi_union = (
        aoi_gdf.to_crs(grid.crs).geometry.union_all()
        if aoi_gdf.crs != grid.crs
        else aoi_gdf.geometry.union_all()
    )

    records = []
    for label_id, parts in parts_by_label.items():
        geom = unary_union(parts) if len(parts) > 1 else parts[0]
        if not geom.is_valid:
            geom = geom.buffer(0)
        geom = geom.intersection(aoi_union)
        if geom.is_empty:
            continue

        component_mask = labels == label_id
        values = intensity[component_mask]
        if values.size == 0:
            continue

        area_m2 = float(geom.area)
        perimeter_m = float(geom.length)
        compactness = float(4.0 * np.pi * area_m2 / (perimeter_m**2)) if perimeter_m > 0 else 0.0

        records.append(
            {
                "id": label_id,
                "date_before": date_before,
                "date_after": date_after,
                "method": method,
                "threshold_method": threshold_method,
                "threshold_value": float(threshold_value),
                "area_m2": area_m2,
                "perimeter_m": perimeter_m,
                "compactness": min(compactness, 1.0),
                "mean_change": float(values.mean()),
                "max_change": float(values.max()),
                "p95_change": float(np.percentile(values, 95)),
                "confidence": np.nan,
                "gi_zscore": np.nan,
                "gi_pvalue": np.nan,
                "gi_qvalue": np.nan,
                "hotspot_class": None,
                "lisa_cluster": None,
                "ml_anomaly_score": np.nan,
                "ml_cluster_id": np.nan,
                "geometry": geom,
            }
        )
    n_after_aoi = len(records)

    records = [r for r in records if r["area_m2"] >= min_area_m2]
    n_after_min_area = len(records)

    if records:
        gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=grid.crs)
        gdf["id"] = range(1, len(gdf) + 1)
    else:
        gdf = gpd.GeoDataFrame(columns=CHANGE_FEATURE_COLUMNS, geometry="geometry", crs=grid.crs)

    logger.info(
        "Vectorization: %d raw components -> %d after AOI clip -> %d after min_area_m2=%.1f filter",
        n_raw,
        n_after_aoi,
        n_after_min_area,
        min_area_m2,
    )
    return gdf, VectorizationSummary(n_raw, n_after_aoi, n_after_min_area)


def compute_confidence(
    gdf: gpd.GeoDataFrame,
    threshold_value: float,
    weights: dict[str, float] | None = None,
) -> gpd.GeoDataFrame:
    """Attach a 0-1 heuristic ``confidence`` score to each change feature.

    This is explicitly NOT a calibrated probability of true change. It is a
    weighted combination of independent, defensible signals:

    * ``threshold_excess``  — how far the patch's mean change is above the
      binarization threshold, relative to the spread of change values above
      threshold in the whole raster (capped at 1).
    * ``consistency``       — 1 - coefficient of variation proxy: how uniform
      the change intensity is within the patch (max vs mean), so a patch that
      is uniformly "hot" scores higher than one with a single hot pixel.
    * ``size_score``        — log-scaled patch area relative to the largest
      patch, rewarding spatially coherent (larger) patches over 1-2 pixel blobs.
    * ``hotspot_score``     — 1 if the patch's Gi* hotspot class is
      significant at 95%/99%, 0.5 at 90%, else 0 (0 for coldspots / not
      computed).
    * ``ml_score``          — normalized Isolation Forest anomaly rank, if the
      experimental spatial ML step was run, else excluded from the weighted sum.

    The exact weights are defined here and reported in ``report.md`` /
    ``README.md`` — nothing here is presented as a calibrated probability.
    """
    if gdf.empty:
        return gdf

    default_weights = {
        "threshold_excess": 0.30,
        "consistency": 0.20,
        "size_score": 0.20,
        "hotspot_score": 0.20,
        "ml_score": 0.10,
    }
    w = weights or default_weights

    mean_change = gdf["mean_change"].to_numpy()
    max_change = gdf["max_change"].to_numpy()
    area = gdf["area_m2"].to_numpy()

    excess = np.clip(
        (mean_change - threshold_value) / (mean_change.max() - threshold_value + 1e-9), 0, 1
    )
    consistency = np.clip(1.0 - (max_change - mean_change) / (max_change + 1e-9), 0, 1)
    size_score = np.clip(np.log1p(area) / np.log1p(area.max() + 1e-9), 0, 1)

    hotspot_class = gdf["hotspot_class"].fillna("not_significant")
    hotspot_map = {
        "hot_99": 1.0,
        "hot_95": 0.85,
        "hot_90": 0.6,
        "cold_90": 0.0,
        "cold_95": 0.0,
        "cold_99": 0.0,
        "not_significant": 0.3,
    }
    hotspot_score = hotspot_class.map(hotspot_map).fillna(0.3).to_numpy()

    has_ml = gdf["ml_anomaly_score"].notna().any()
    if has_ml:
        ml_vals = gdf["ml_anomaly_score"].to_numpy()
        finite = np.isfinite(ml_vals)
        ml_score = np.zeros_like(mean_change)
        if finite.any():
            rank = np.zeros_like(ml_vals)
            rank[finite] = (ml_vals[finite] - ml_vals[finite].min()) / (
                np.ptp(ml_vals[finite]) + 1e-9
            )
            ml_score = np.nan_to_num(rank, nan=0.0)
        total_w = sum(w.values())
        confidence = (
            w["threshold_excess"] * excess
            + w["consistency"] * consistency
            + w["size_score"] * size_score
            + w["hotspot_score"] * hotspot_score
            + w["ml_score"] * ml_score
        ) / total_w
    else:
        total_w = w["threshold_excess"] + w["consistency"] + w["size_score"] + w["hotspot_score"]
        confidence = (
            w["threshold_excess"] * excess
            + w["consistency"] * consistency
            + w["size_score"] * size_score
            + w["hotspot_score"] * hotspot_score
        ) / total_w

    gdf = gdf.copy()
    gdf["confidence"] = np.clip(confidence, 0, 1)
    return gdf
