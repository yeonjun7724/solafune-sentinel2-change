from __future__ import annotations

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import box
from skimage.measure import label

from solafune_change.preprocessing import GridSpec
from solafune_change.vectorization import compute_confidence, polygonize_change


def _grid():
    return GridSpec(
        crs="EPSG:32735",
        transform=rasterio.transform.from_origin(500000.0, 8600000.0, 10.0, 10.0),
        width=20,
        height=20,
    )


def _aoi(grid: GridSpec):
    bounds = box(
        grid.transform.c,
        grid.transform.f - grid.height * 10,
        grid.transform.c + grid.width * 10,
        grid.transform.f,
    )
    return gpd.GeoDataFrame({"name": ["aoi"]}, geometry=[bounds], crs=grid.crs)


def test_polygonize_change_produces_expected_area():
    grid = _grid()
    binary = np.zeros((grid.height, grid.width), dtype=bool)
    binary[5:10, 5:10] = True  # 5x5 pixels @ 10m = 2500 m^2
    labels = label(binary, connectivity=2).astype(np.int32)
    intensity = np.where(binary, 5.0, 0.5)

    gdf, summary = polygonize_change(
        labels, intensity, grid, _aoi(grid), "d1", "d2", "cva", "otsu", 1.0, min_area_m2=0.0
    )
    assert len(gdf) == 1
    row = gdf.iloc[0]
    assert abs(row["area_m2"] - 2500.0) < 1.0
    assert row["mean_change"] == 5.0
    assert 0.0 < row["compactness"] <= 1.0


def test_polygonize_change_min_area_filter_drops_small_component():
    grid = _grid()
    binary = np.zeros((grid.height, grid.width), dtype=bool)
    binary[0:1, 0:1] = True  # 1 pixel = 100 m^2
    labels = label(binary, connectivity=2).astype(np.int32)
    intensity = np.where(binary, 5.0, 0.0)

    gdf, summary = polygonize_change(
        labels, intensity, grid, _aoi(grid), "d1", "d2", "cva", "otsu", 1.0, min_area_m2=1000.0
    )
    assert len(gdf) == 0
    assert summary.n_raw_components == 1


def test_compute_confidence_bounds_zero_to_one():
    grid = _grid()
    binary = np.zeros((grid.height, grid.width), dtype=bool)
    binary[2:5, 2:5] = True
    binary[10:12, 10:12] = True
    labels = label(binary, connectivity=2).astype(np.int32)
    intensity = np.where(binary, 5.0, 0.5)
    gdf, _ = polygonize_change(
        labels, intensity, grid, _aoi(grid), "d1", "d2", "cva", "otsu", 1.0, min_area_m2=0.0
    )

    scored = compute_confidence(gdf, threshold_value=1.0)
    assert (scored["confidence"] >= 0.0).all()
    assert (scored["confidence"] <= 1.0).all()
