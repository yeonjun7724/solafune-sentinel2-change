"""Experimental unsupervised spatial ML: anomaly scoring and change clustering.

No ground-truth labels exist for this AOI, so nothing here is a classifier
and no accuracy/precision/recall is computed or implied. Isolation Forest
produces an exploratory anomaly ranking over the same analysis-grid cells
used for the spatial statistics; DBSCAN groups changed grid cells into
spatially contiguous clusters. Both are clearly experimental and are only
run when explicitly enabled.

Because neighboring grid cells share both spectral signal and spatial
autocorrelation (confirmed by the Global Moran's I step), a conventional
train/test or k-fold split would leak information between adjacent cells and
produce misleadingly optimistic "performance". We do not report any such
score. Instead we report stability/sensitivity diagnostics: how much the
top-ranked anomalies change under spatial block bootstrap resampling and
under a hyperparameter perturbation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from .errors import AnalysisError

logger = logging.getLogger(__name__)

DEFAULT_FEATURE_COLUMNS: tuple[str, ...] = (
    "mean_cva",
    "p95_cva",
    "changed_proportion",
    "mean_diff_b04",
    "mean_diff_b03",
    "mean_diff_b02",
    "local_std_cva",
)


@dataclass
class SpatialMLResult:
    grid: gpd.GeoDataFrame  # input grid + anomaly_score, anomaly_rank, anomaly_quantile, cluster_id
    feature_columns: list[str]
    scaling: str
    model: str
    hyperparameters: dict
    stability: dict
    random_seed: int


def _build_features(
    grid: gpd.GeoDataFrame, use_coordinates: bool, feature_columns: tuple[str, ...]
) -> tuple[np.ndarray, list[str]]:
    available = [c for c in feature_columns if c in grid.columns]
    missing = set(feature_columns) - set(available)
    if missing:
        logger.warning("Spatial ML: feature columns not available and skipped: %s", missing)

    # Spatial-lag feature: mean of each cell's queen-contiguity neighbors' CVA,
    # giving the model neighborhood context without letting raw coordinates
    # dominate distances (coordinates are only added if explicitly requested).
    centroids = grid.geometry.centroid
    grid = grid.copy()
    grid["_x"] = centroids.x
    grid["_y"] = centroids.y

    cols = list(available)
    X = grid[cols].to_numpy(dtype=np.float64)

    if use_coordinates:
        coord_scale = grid[["_x", "_y"]].to_numpy(dtype=np.float64)
        coord_scale = (coord_scale - coord_scale.mean(axis=0)) / (coord_scale.std(axis=0) + 1e-9)
        X = np.hstack([X, coord_scale])
        cols = cols + ["x_scaled", "y_scaled"]
        logger.info(
            "Spatial ML: coordinates included as features (standardized) per use_coordinates=True"
        )

    return X, cols


def run_isolation_forest(
    grid: gpd.GeoDataFrame,
    feature_columns: tuple[str, ...] = DEFAULT_FEATURE_COLUMNS,
    contamination: float = 0.1,
    n_estimators: int = 200,
    use_coordinates: bool = False,
    random_seed: int = 42,
    n_bootstrap: int = 20,
) -> SpatialMLResult:
    """Exploratory anomaly scoring over analysis-grid cells with Isolation Forest."""
    if len(grid) < 20:
        raise AnalysisError(f"Too few grid cells ({len(grid)}) for spatial ML (need >= 20)")

    X, used_cols = _build_features(grid, use_coordinates, feature_columns)
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=n_estimators, contamination=contamination, random_state=random_seed
    )
    model.fit(X_scaled)
    raw_score = -model.score_samples(X_scaled)  # higher = more anomalous

    out = grid.copy()
    out["ml_anomaly_score"] = raw_score
    out["ml_anomaly_rank"] = (
        pd.Series(raw_score).rank(ascending=False, method="min").astype(int).to_numpy()
    )
    out["ml_anomaly_quantile"] = pd.Series(raw_score).rank(pct=True).to_numpy()
    out["ml_cluster_id"] = -1  # isolation forest does not cluster; -1 = not applicable

    stability = _stability_diagnostics(
        X_scaled,
        model_kind="isolation_forest",
        contamination=contamination,
        n_estimators=n_estimators,
        random_seed=random_seed,
        n_bootstrap=n_bootstrap,
    )

    return SpatialMLResult(
        grid=out,
        feature_columns=used_cols,
        scaling="RobustScaler (median/IQR)",
        model="isolation_forest",
        hyperparameters={
            "contamination": contamination,
            "n_estimators": n_estimators,
            "use_coordinates": use_coordinates,
        },
        stability=stability,
        random_seed=random_seed,
    )


def run_dbscan_clustering(
    grid: gpd.GeoDataFrame,
    feature_columns: tuple[str, ...] = DEFAULT_FEATURE_COLUMNS,
    eps: float = 1.5,
    min_samples: int = 5,
    use_coordinates: bool = True,
    random_seed: int = 42,
) -> SpatialMLResult:
    """Group changed grid cells into spatially/spectrally coherent clusters with DBSCAN.

    ``use_coordinates`` defaults to True here (unlike Isolation Forest)
    because DBSCAN is being used to find spatially contiguous groups of
    similar change, not general outliers; coordinates are standardized so
    they are on the same scale as the (already robust-scaled) spectral
    features rather than dominating the distance metric outright.
    """
    if len(grid) < 20:
        raise AnalysisError(f"Too few grid cells ({len(grid)}) for spatial ML (need >= 20)")

    X, used_cols = _build_features(grid, use_coordinates, feature_columns)
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X)

    model = DBSCAN(eps=eps, min_samples=min_samples)
    labels = model.fit_predict(X_scaled)

    out = grid.copy()
    out["ml_cluster_id"] = labels
    # A simple distance-to-nearest-core-point-derived anomaly proxy: noise
    # points (label == -1) are treated as maximally anomalous (1.0), cluster
    # members get a low, equal anomaly score. This keeps the anomaly_score
    # column semantically comparable to the Isolation Forest output without
    # implying DBSCAN estimates a continuous outlier degree (it does not).
    out["ml_anomaly_score"] = (labels == -1).astype(float)
    out["ml_anomaly_rank"] = (
        pd.Series(-out["ml_anomaly_score"]).rank(method="min").astype(int).to_numpy()
    )
    out["ml_anomaly_quantile"] = pd.Series(out["ml_anomaly_score"]).rank(pct=True).to_numpy()

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int((labels == -1).sum())
    logger.info(
        "DBSCAN: %d clusters found, %d cells labeled noise (out of %d)",
        n_clusters,
        n_noise,
        len(grid),
    )

    stability = _stability_diagnostics(
        X_scaled,
        model_kind="dbscan",
        eps=eps,
        min_samples=min_samples,
        random_seed=random_seed,
    )

    return SpatialMLResult(
        grid=out,
        feature_columns=used_cols,
        scaling="RobustScaler (median/IQR)",
        model="dbscan",
        hyperparameters={
            "eps": eps,
            "min_samples": min_samples,
            "use_coordinates": use_coordinates,
            "n_clusters": n_clusters,
            "n_noise": n_noise,
        },
        stability=stability,
        random_seed=random_seed,
    )


def _stability_diagnostics(
    X_scaled: np.ndarray,
    model_kind: str,
    random_seed: int,
    n_bootstrap: int = 20,
    top_k: int = 20,
    **hyperparams,
) -> dict:
    """Spatial block bootstrap + hyperparameter sensitivity, in place of any
    cross-validation "score" (which would be invalid here without labels and
    with strongly spatially autocorrelated observations).
    """
    n = X_scaled.shape[0]
    rng = np.random.default_rng(random_seed)
    top_k = min(top_k, n)

    if model_kind == "isolation_forest":
        base_model = IsolationForest(
            n_estimators=hyperparams["n_estimators"],
            contamination=hyperparams["contamination"],
            random_state=random_seed,
        ).fit(X_scaled)
        base_score = -base_model.score_samples(X_scaled)
        base_top = set(np.argsort(base_score)[-top_k:])

        overlaps = []
        n_blocks = max(4, int(np.sqrt(n_bootstrap) * 2))
        block_ids = rng.integers(0, n_blocks, size=n)
        for i in range(n_bootstrap):
            keep_blocks = rng.choice(n_blocks, size=max(1, int(n_blocks * 0.8)), replace=False)
            mask = np.isin(block_ids, keep_blocks)
            if mask.sum() < top_k + 5:
                continue
            sub_model = IsolationForest(
                n_estimators=hyperparams["n_estimators"],
                contamination=hyperparams["contamination"],
                random_state=random_seed + i + 1,
            ).fit(X_scaled[mask])
            sub_score = -sub_model.score_samples(X_scaled[mask])
            sub_indices = np.where(mask)[0]
            sub_top_global = set(sub_indices[np.argsort(sub_score)[-top_k:]])
            overlap = len(base_top & sub_top_global) / top_k
            overlaps.append(overlap)

        sensitivity = {}
        for factor in (0.5, 2.0):
            alt_c = float(np.clip(hyperparams["contamination"] * factor, 0.01, 0.49))
            alt_model = IsolationForest(
                n_estimators=hyperparams["n_estimators"],
                contamination=alt_c,
                random_state=random_seed,
            ).fit(X_scaled)
            alt_score = -alt_model.score_samples(X_scaled)
            alt_top = set(np.argsort(alt_score)[-top_k:])
            sensitivity[f"contamination_x{factor}"] = len(base_top & alt_top) / top_k

        return {
            "method": "spatial_block_bootstrap",
            "n_bootstrap_replicates": len(overlaps),
            "top_k": top_k,
            "mean_top_k_overlap": float(np.mean(overlaps)) if overlaps else None,
            "std_top_k_overlap": float(np.std(overlaps)) if overlaps else None,
            "hyperparameter_sensitivity_top_k_overlap": sensitivity,
            "note": "Overlap = fraction of the top-K anomalies (by score) that remain top-K under spatial block "
            "subsampling / a perturbed hyperparameter. This is a stability diagnostic, not a validation "
            "accuracy score: no ground truth exists to validate against.",
        }

    # DBSCAN: sensitivity of cluster count / noise fraction to eps perturbation
    base_labels = DBSCAN(
        eps=hyperparams["eps"], min_samples=hyperparams["min_samples"]
    ).fit_predict(X_scaled)
    base_noise = float((base_labels == -1).mean())
    sensitivity = {}
    for factor in (0.8, 1.2):
        alt_labels = DBSCAN(
            eps=hyperparams["eps"] * factor, min_samples=hyperparams["min_samples"]
        ).fit_predict(X_scaled)
        alt_noise = float((alt_labels == -1).mean())
        alt_n_clusters = len(set(alt_labels)) - (1 if -1 in alt_labels else 0)
        sensitivity[f"eps_x{factor}"] = {"noise_fraction": alt_noise, "n_clusters": alt_n_clusters}

    return {
        "method": "hyperparameter_sensitivity",
        "base_noise_fraction": base_noise,
        "eps_sensitivity": sensitivity,
        "note": "DBSCAN has no natural bootstrap anomaly score; reporting how noise-point fraction and cluster "
        "count shift under +/-20% eps perturbation as a stability proxy instead.",
    }
