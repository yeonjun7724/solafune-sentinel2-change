"""Spatial statistics: regular analysis grid, Global/Local Moran's I, Getis-Ord Gi*.

Pixel-level analysis is deliberately aggregated onto a regular grid before any
spatial-weights matrix is built — building a weights matrix over ~2.6 million
pixels would be both wasteful and largely meaningless at the pixel scale.
Aggregating to a coarser grid (default 150 m, configurable) turns the problem
into a few thousand areal units, which is the right scale for contiguity-based
spatial autocorrelation statistics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from esda.getisord import G_Local
from esda.moran import Moran, Moran_Local
from libpysal.weights import KNN, Queen, Rook, W
from shapely.geometry import box

from .errors import AnalysisError
from .preprocessing import GridSpec

logger = logging.getLogger(__name__)

GRID_STAT_COLUMNS: tuple[str, ...] = (
    "cell_row",
    "cell_col",
    "valid_pixel_count",
    "total_pixel_count",
    "mean_cva",
    "median_cva",
    "p90_cva",
    "p95_cva",
    "changed_proportion",
    "mean_diff_b04",
    "mean_diff_b03",
    "mean_diff_b02",
    "local_std_cva",
)


@dataclass
class GlobalMoranResult:
    variable: str
    weights_type: str
    row_standardized: bool
    n_units: int
    n_islands: int
    moran_i: float
    expected_i: float
    z_score: float
    p_norm: float
    p_sim: float
    permutations: int
    random_seed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable": self.variable,
            "weights_type": self.weights_type,
            "row_standardized": self.row_standardized,
            "n_units": self.n_units,
            "n_islands": self.n_islands,
            "moran_i": self.moran_i,
            "expected_i": self.expected_i,
            "z_score": self.z_score,
            "p_norm": self.p_norm,
            "p_sim": self.p_sim,
            "permutations": self.permutations,
            "random_seed": self.random_seed,
        }


def build_analysis_grid(
    grid: GridSpec,
    combined_valid_mask: np.ndarray,
    binary: np.ndarray,
    cva: np.ndarray,
    band_diff: np.ndarray,
    cell_size_m: float,
) -> gpd.GeoDataFrame:
    """Aggregate pixel-level rasters onto a regular ``cell_size_m`` grid.

    Only pixels inside ``combined_valid_mask`` (AOI intersected with both
    dates' valid-data masks) contribute to cell statistics. Cells with zero
    valid pixels are dropped.
    """
    if cell_size_m <= grid.pixel_size_x:
        raise AnalysisError(
            f"spatial_grid_size_m ({cell_size_m}) must be larger than the pixel size ({grid.pixel_size_x})"
        )

    rows, cols = np.where(combined_valid_mask)
    if rows.size == 0:
        raise AnalysisError("No valid pixels available to build the spatial analysis grid")

    x = grid.transform.c + (cols + 0.5) * grid.transform.a
    y = grid.transform.f + (rows + 0.5) * grid.transform.e

    cell_col = np.floor((x - grid.transform.c) / cell_size_m).astype(np.int64)
    cell_row = np.floor((grid.transform.f - y) / cell_size_m).astype(np.int64)

    df = pd.DataFrame(
        {
            "cell_row": cell_row,
            "cell_col": cell_col,
            "cva": cva[rows, cols],
            "changed": binary[rows, cols].astype(np.float64),
            "diff_b04": band_diff[0][rows, cols],
            "diff_b03": band_diff[1][rows, cols],
            "diff_b02": band_diff[2][rows, cols],
        }
    )

    agg = (
        df.groupby(["cell_row", "cell_col"])
        .agg(
            valid_pixel_count=("cva", "size"),
            mean_cva=("cva", "mean"),
            median_cva=("cva", "median"),
            p90_cva=("cva", lambda s: np.percentile(s, 90)),
            p95_cva=("cva", lambda s: np.percentile(s, 95)),
            changed_proportion=("changed", "mean"),
            mean_diff_b04=("diff_b04", "mean"),
            mean_diff_b03=("diff_b03", "mean"),
            mean_diff_b02=("diff_b02", "mean"),
            local_std_cva=("cva", "std"),
        )
        .reset_index()
    )
    agg["local_std_cva"] = agg["local_std_cva"].fillna(0.0)
    agg["total_pixel_count"] = agg["valid_pixel_count"]

    geoms = []
    for r, c in zip(agg["cell_row"], agg["cell_col"], strict=True):
        x0 = grid.transform.c + c * cell_size_m
        x1 = x0 + cell_size_m
        y1 = grid.transform.f - r * cell_size_m
        y0 = y1 - cell_size_m
        geoms.append(box(x0, y0, x1, y1))

    gdf = gpd.GeoDataFrame(agg, geometry=geoms, crs=grid.crs)
    gdf["grid_id"] = range(1, len(gdf) + 1)
    logger.info("Built analysis grid: %d cells at %.0f m resolution", len(gdf), cell_size_m)
    return gdf


def _build_weights(gdf: gpd.GeoDataFrame, weights_type: str, knn_k: int) -> W:
    if weights_type == "queen":
        w = Queen.from_dataframe(gdf, use_index=False, silence_warnings=True)
    elif weights_type == "rook":
        w = Rook.from_dataframe(gdf, use_index=False, silence_warnings=True)
    elif weights_type == "knn":
        w = KNN.from_dataframe(gdf, k=knn_k, use_index=False)
    else:
        raise AnalysisError(f"Unknown spatial weights type: {weights_type}")

    if len(w.islands) > 0:
        logger.warning(
            "%d spatial unit(s) have no neighbors under '%s' weights (islands): %s",
            len(w.islands),
            weights_type,
            w.islands[:20],
        )
    return w


def compute_global_moran(
    gdf: gpd.GeoDataFrame,
    value_col: str,
    weights_type: str = "queen",
    knn_k: int = 8,
    permutations: int = 999,
    row_standardize: bool = True,
    seed: int = 42,
) -> GlobalMoranResult:
    """Global Moran's I with permutation inference on ``gdf[value_col]``."""
    if len(gdf) < 8:
        raise AnalysisError(
            f"Too few spatial cells ({len(gdf)}) for a meaningful Global Moran's I (need >= 8)"
        )

    w = _build_weights(gdf, weights_type, knn_k)
    if row_standardize:
        w.set_transform("r")

    y = gdf[value_col].to_numpy(dtype=np.float64)
    np.random.seed(seed)
    moran = Moran(y, w, permutations=permutations)

    return GlobalMoranResult(
        variable=value_col,
        weights_type=weights_type,
        row_standardized=row_standardize,
        n_units=len(gdf),
        n_islands=len(w.islands),
        moran_i=float(moran.I),
        expected_i=float(moran.EI),
        z_score=float(moran.z_sim if permutations > 0 else moran.z_norm),
        p_norm=float(moran.p_norm),
        p_sim=float(moran.p_sim if permutations > 0 else moran.p_norm),
        permutations=permutations,
        random_seed=seed,
    )


def bh_fdr(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR-adjusted q-values for an array of p-values."""
    pvalues = np.asarray(pvalues, dtype=np.float64)
    n = pvalues.size
    if n == 0:
        return pvalues
    order = np.argsort(pvalues)
    ranked = pvalues[order]
    ranks = np.arange(1, n + 1)
    raw_q = ranked * n / ranks
    # enforce monotonicity from the largest p-value downward
    q_monotone = np.minimum.accumulate(raw_q[::-1])[::-1]
    q = np.empty(n, dtype=np.float64)
    q[order] = np.clip(q_monotone, 0, 1)
    return q


_HOTSPOT_LABELS = {
    (True, 0.01): "hot_99",
    (True, 0.05): "hot_95",
    (True, 0.10): "hot_90",
    (False, 0.01): "cold_99",
    (False, 0.05): "cold_95",
    (False, 0.10): "cold_90",
}

_LISA_QUADRANT = {1: "High-High", 2: "Low-High", 3: "Low-Low", 4: "High-Low"}


def _classify_hotspot(z: float, p: float) -> str:
    is_hot = z > 0
    for level in (0.01, 0.05, 0.10):
        if p < level:
            return _HOTSPOT_LABELS[(is_hot, level)]
    return "not_significant"


def compute_local_statistics(
    gdf: gpd.GeoDataFrame,
    value_col: str,
    weights_type: str = "queen",
    knn_k: int = 8,
    permutations: int = 999,
    alpha: float = 0.05,
    fdr_correction: bool = True,
    seed: int = 42,
) -> gpd.GeoDataFrame:
    """Attach Local Moran's I (LISA) and Getis-Ord Gi* results to each grid cell."""
    gdf = gdf.copy()
    w_row = _build_weights(gdf, weights_type, knn_k)
    w_row.set_transform("r")
    w_binary = _build_weights(gdf, weights_type, knn_k)
    w_binary.set_transform("b")

    y = gdf[value_col].to_numpy(dtype=np.float64)

    np.random.seed(seed)
    lisa = Moran_Local(y, w_row, permutations=permutations, seed=seed)
    gdf["local_moran_stat"] = lisa.Is
    gdf["local_moran_p"] = lisa.p_sim if permutations > 0 else lisa.p_norm
    gdf["spatial_lag"] = lisa.lag if hasattr(lisa, "lag") else np.nan
    quadrant = np.asarray(lisa.q)
    lisa_cluster = np.where(
        gdf["local_moran_p"].to_numpy() < alpha,
        np.vectorize(_LISA_QUADRANT.get)(quadrant),
        "Not significant",
    )
    gdf["lisa_cluster"] = lisa_cluster

    np.random.seed(seed)
    gi = G_Local(y, w_binary, transform="B", star=True, permutations=permutations, seed=seed)
    gi_z = np.asarray(gi.Zs)
    gi_p = np.asarray(gi.p_sim if permutations > 0 else gi.p_norm)
    gdf["gi_star"] = gi.Gs
    gdf["gi_zscore"] = gi_z
    gdf["gi_pvalue"] = gi_p
    gdf["gi_qvalue"] = bh_fdr(gi_p) if fdr_correction else gi_p
    gdf["hotspot_class"] = [
        _classify_hotspot(z, q if fdr_correction else p)
        for z, p, q in zip(gi_z, gi_p, gdf["gi_qvalue"], strict=True)
    ]

    logger.info(
        "Local statistics computed for %d cells; hotspot class counts: %s",
        len(gdf),
        gdf["hotspot_class"].value_counts().to_dict(),
    )
    return gdf


DEFAULT_NUMERIC_ATTACH_COLS: tuple[str, ...] = (
    "gi_zscore",
    "gi_pvalue",
    "gi_qvalue",
    "ml_anomaly_score",
    "ml_anomaly_rank",
    "ml_anomaly_quantile",
)
DEFAULT_CATEGORICAL_ATTACH_COLS: tuple[str, ...] = (
    "hotspot_class",
    "lisa_cluster",
    "ml_cluster_id",
)


def attach_grid_attributes_to_features(
    features_gdf: gpd.GeoDataFrame,
    grid_gdf: gpd.GeoDataFrame,
    numeric_cols: tuple[str, ...] = DEFAULT_NUMERIC_ATTACH_COLS,
    categorical_cols: tuple[str, ...] = DEFAULT_CATEGORICAL_ATTACH_COLS,
) -> gpd.GeoDataFrame:
    """Attribute each change-feature polygon with area-weighted grid statistics.

    A change feature can straddle more than one analysis-grid cell. We
    intersect each feature with the grid, weight each numeric grid attribute
    (Gi* z-score/p/q-value, ML anomaly score/rank/quantile) by the overlap
    area, and take the grid cell with the largest overlap area for
    categorical attributes (``hotspot_class``, ``lisa_cluster``,
    ``ml_cluster_id``). This "largest-overlap wins" + "area-weighted mean"
    policy is documented here as the join method. Only columns actually
    present in ``grid_gdf`` are attached (e.g. ML columns are skipped when
    the experimental spatial ML step was not run).
    """
    if features_gdf.empty:
        return features_gdf

    numeric_present = [c for c in numeric_cols if c in grid_gdf.columns]
    categorical_present = [c for c in categorical_cols if c in grid_gdf.columns]
    if not numeric_present and not categorical_present:
        return features_gdf

    stat_cols = ["grid_id", *numeric_present, *categorical_present, "geometry"]
    grid_small = grid_gdf[stat_cols].copy()

    pieces = gpd.overlay(
        features_gdf[["id", "geometry"]], grid_small, how="intersection", keep_geom_type=False
    )
    if pieces.empty:
        return features_gdf

    pieces["overlap_area"] = pieces.geometry.area

    def _aggregate(g: pd.DataFrame) -> pd.Series:
        out = {}
        for col in numeric_present:
            vals = g[col].astype(float)
            weights = g["overlap_area"]
            valid = vals.notna()
            out[col] = (
                float(np.average(vals[valid], weights=weights[valid])) if valid.any() else np.nan
            )
        best_idx = g["overlap_area"].idxmax()
        for col in categorical_present:
            out[col] = g.loc[best_idx, col]
        return pd.Series(out)

    weighted = pieces.groupby("id").apply(_aggregate, include_groups=False).reset_index()

    out = features_gdf.drop(
        columns=[c for c in (*numeric_present, *categorical_present) if c in features_gdf.columns]
    ).merge(weighted, on="id", how="left")
    return gpd.GeoDataFrame(out, geometry="geometry", crs=features_gdf.crs)
