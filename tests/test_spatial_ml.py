from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.geometry import box

from solafune_change.spatial_ml import run_dbscan_clustering, run_isolation_forest


def _synthetic_grid(n=25):
    rng = np.random.default_rng(7)
    rows = []
    geoms = []
    for i in range(n):
        for j in range(n):
            is_anomaly = (i, j) == (0, 0)
            rows.append(
                {
                    # the (0,0) cell is pushed far outside the normal range on every
                    # feature dimension, not just one, so Isolation Forest isolates
                    # it deterministically regardless of the random seed used for
                    # the background cells.
                    "mean_cva": 10.0 if is_anomaly else rng.normal(1.0, 0.2),
                    "p95_cva": 15.0 if is_anomaly else rng.normal(1.5, 0.2),
                    "changed_proportion": 0.95 if is_anomaly else rng.uniform(0, 0.1),
                    "mean_diff_b04": 0.5 if is_anomaly else rng.normal(0, 0.01),
                    "mean_diff_b03": 0.5 if is_anomaly else rng.normal(0, 0.01),
                    "mean_diff_b02": 0.5 if is_anomaly else rng.normal(0, 0.01),
                    "local_std_cva": 5.0 if is_anomaly else rng.uniform(0, 0.5),
                    "grid_id": i * n + j,
                }
            )
            geoms.append(box(i * 10, j * 10, i * 10 + 10, j * 10 + 10))
    return gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:32735")


def test_isolation_forest_flags_injected_anomaly():
    grid = _synthetic_grid()
    result = run_isolation_forest(
        grid, contamination=0.05, n_estimators=100, random_seed=42, n_bootstrap=5
    )
    assert "ml_anomaly_score" in result.grid.columns
    top_row = result.grid.loc[result.grid["ml_anomaly_score"].idxmax()]
    assert top_row["grid_id"] == 0  # the (0,0) cell we made anomalous
    assert result.stability["method"] == "spatial_block_bootstrap"


def test_isolation_forest_reproducible_with_same_seed():
    grid = _synthetic_grid()
    r1 = run_isolation_forest(
        grid, contamination=0.1, n_estimators=100, random_seed=123, n_bootstrap=3
    )
    r2 = run_isolation_forest(
        grid, contamination=0.1, n_estimators=100, random_seed=123, n_bootstrap=3
    )
    assert np.allclose(
        r1.grid["ml_anomaly_score"].to_numpy(), r2.grid["ml_anomaly_score"].to_numpy()
    )


def test_dbscan_clustering_runs_and_labels_cells():
    grid = _synthetic_grid()
    result = run_dbscan_clustering(
        grid, eps=1.5, min_samples=5, use_coordinates=True, random_seed=42
    )
    assert "ml_cluster_id" in result.grid.columns
    assert result.stability["method"] == "hyperparameter_sensitivity"
