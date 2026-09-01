from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CRS = "EPSG:32735"
PIXEL_SIZE = 10.0
WIDTH, HEIGHT = 40, 30
ORIGIN_X, ORIGIN_Y = 500000.0, 8600000.0


def _write_band(path: Path, values: np.ndarray, nodata: float = 0.0) -> None:
    transform = from_origin(ORIGIN_X, ORIGIN_Y, PIXEL_SIZE, PIXEL_SIZE)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype=values.dtype,
        crs=CRS,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(values, 1)


@pytest.fixture()
def synthetic_bands(tmp_path: Path) -> dict:
    """Two date folders with B02/B03/B04, a small border of NoData, and one
    synthetic 'changed' block so downstream steps have real signal to find."""
    rng = np.random.default_rng(42)
    before_dir = tmp_path / "sentinel2_20230101"
    after_dir = tmp_path / "sentinel2_20230201"
    before_dir.mkdir()
    after_dir.mkdir()

    base = {
        "B02": rng.integers(1000, 1500, size=(HEIGHT, WIDTH)).astype(np.uint16),
        "B03": rng.integers(1200, 1700, size=(HEIGHT, WIDTH)).astype(np.uint16),
        "B04": rng.integers(1400, 1900, size=(HEIGHT, WIDTH)).astype(np.uint16),
    }
    after = {k: v.copy() for k, v in base.items()}
    # inject a clear, spatially coherent change block
    after["B02"][5:15, 5:15] += 800
    after["B03"][5:15, 5:15] += 800
    after["B04"][5:15, 5:15] += 800

    # a NoData border, identical in both dates (common valid-mask case)
    for arr in (*base.values(), *after.values()):
        arr[0, :] = 0
        arr[:, 0] = 0

    for band, arr in base.items():
        _write_band(before_dir / f"{band}.tif", arr)
    for band, arr in after.items():
        _write_band(after_dir / f"{band}.tif", arr)

    aoi_path = tmp_path / "aoi.geojson"
    bounds_geom = box(
        ORIGIN_X, ORIGIN_Y - HEIGHT * PIXEL_SIZE, ORIGIN_X + WIDTH * PIXEL_SIZE, ORIGIN_Y
    )
    gpd.GeoDataFrame({"name": ["aoi"]}, geometry=[bounds_geom], crs=CRS).to_crs(4326).to_file(
        aoi_path, driver="GeoJSON"
    )

    return {
        "before_dir": before_dir,
        "after_dir": after_dir,
        "aoi_path": aoi_path,
        "tmp_path": tmp_path,
    }
