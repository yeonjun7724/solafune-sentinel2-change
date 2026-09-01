from __future__ import annotations

import numpy as np
import pytest
import rasterio

from solafune_change.errors import AnalysisError
from solafune_change.preprocessing import GridSpec
from solafune_change.spatial_statistics import (
    bh_fdr,
    build_analysis_grid,
    compute_global_moran,
    compute_local_statistics,
)


def _grid(size=60):
    return GridSpec(
        crs="EPSG:32735",
        transform=rasterio.transform.from_origin(500000.0, 8600000.0, 10.0, 10.0),
        width=size,
        height=size,
    )


def _synthetic_grid_gdf():
    """A 60x60 px raster (600x600 m) with a spatially clustered high-CVA region,
    aggregated onto a 60 m grid -> 10x10 = 100 cells, safely above the Moran's I
    minimum-cell threshold."""
    grid = _get_pixel_grid()
    valid = np.ones((grid.height, grid.width), dtype=bool)
    cva = np.full((grid.height, grid.width), 1.0, dtype=np.float32)
    cva[10:30, 10:30] = 8.0  # spatially clustered block of high change
    binary = cva > 4.0
    band_diff = np.stack([cva * 0.3, cva * 0.3, cva * 0.3], axis=0)

    return build_analysis_grid(grid, valid, binary, cva, band_diff, cell_size_m=60.0)


def _get_pixel_grid():
    return _grid(size=60)


def test_build_analysis_grid_cell_count():
    grid_gdf = _synthetic_grid_gdf()
    assert len(grid_gdf) == 100  # 600m / 60m = 10 -> 10x10
    assert "mean_cva" in grid_gdf.columns
    assert grid_gdf["valid_pixel_count"].sum() == 60 * 60


def test_build_analysis_grid_rejects_cell_smaller_than_pixel():
    grid = _get_pixel_grid()
    valid = np.ones((grid.height, grid.width), dtype=bool)
    cva = np.ones((grid.height, grid.width), dtype=np.float32)
    binary = np.zeros_like(cva, dtype=bool)
    band_diff = np.zeros((3, grid.height, grid.width), dtype=np.float32)
    with pytest.raises(AnalysisError):
        build_analysis_grid(grid, valid, binary, cva, band_diff, cell_size_m=5.0)


def test_global_moran_detects_positive_autocorrelation():
    grid_gdf = _synthetic_grid_gdf()
    result = compute_global_moran(
        grid_gdf, "mean_cva", weights_type="queen", permutations=199, seed=42
    )
    assert result.moran_i > 0.3  # a spatially clustered block -> strong positive I
    assert result.n_units == 100
    assert 0.0 <= result.p_sim <= 1.0
    assert result.permutations == 199


def test_global_moran_too_few_cells_raises():
    grid = _grid(size=10)
    valid = np.ones((grid.height, grid.width), dtype=bool)
    cva = np.ones((grid.height, grid.width), dtype=np.float32)
    binary = np.zeros_like(cva, dtype=bool)
    band_diff = np.zeros((3, grid.height, grid.width), dtype=np.float32)
    grid_gdf = build_analysis_grid(grid, valid, binary, cva, band_diff, cell_size_m=60.0)
    with pytest.raises(AnalysisError):
        compute_global_moran(grid_gdf, "mean_cva", permutations=99)


def test_local_statistics_has_required_fields():
    grid_gdf = _synthetic_grid_gdf()
    result = compute_local_statistics(
        grid_gdf, "mean_cva", permutations=199, alpha=0.05, fdr_correction=True, seed=42
    )
    for col in (
        "local_moran_stat",
        "local_moran_p",
        "lisa_cluster",
        "gi_star",
        "gi_zscore",
        "gi_pvalue",
        "gi_qvalue",
        "hotspot_class",
    ):
        assert col in result.columns
    assert set(result["lisa_cluster"].unique()) <= {
        "High-High",
        "Low-Low",
        "High-Low",
        "Low-High",
        "Not significant",
    }
    valid_hotspot_labels = {
        "hot_99",
        "hot_95",
        "hot_90",
        "not_significant",
        "cold_90",
        "cold_95",
        "cold_99",
    }
    assert set(result["hotspot_class"].unique()) <= valid_hotspot_labels
    # q-values from FDR correction should never be smaller than the raw p-values
    assert (result["gi_qvalue"] >= result["gi_pvalue"] - 1e-9).all()


def test_bh_fdr_is_monotonic_and_bounded():
    pvalues = np.array([0.001, 0.2, 0.03, 0.5, 0.9, 0.04])
    q = bh_fdr(pvalues)
    assert (q >= 0).all() and (q <= 1).all()
    order = np.argsort(pvalues)
    assert np.all(np.diff(q[order]) >= -1e-9)  # non-decreasing when sorted by p-value


def test_bh_fdr_empty_array():
    assert bh_fdr(np.array([])).size == 0
