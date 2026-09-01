from __future__ import annotations

import geopandas as gpd
import numpy as np
import rasterio

from solafune_change import preprocessing as pp
from solafune_change.discovery import discover_bands


def test_build_aligned_inputs_no_resample_needed(synthetic_bands):
    before_bands = discover_bands(synthetic_bands["before_dir"])
    after_bands = discover_bands(synthetic_bands["after_dir"])
    aoi = gpd.read_file(synthetic_bands["aoi_path"])
    aligned = pp.build_aligned_inputs(
        before_bands, after_bands, "before", "after", aoi, nodata_value=0.0
    )
    assert aligned.resampled_after is False
    assert aligned.before.dn.shape == aligned.after.dn.shape
    assert aligned.combined_valid_mask.sum() > 0
    # the injected change block should be inside the valid mask
    assert aligned.combined_valid_mask[5:15, 5:15].all()


def test_build_aligned_inputs_triggers_resample_on_grid_mismatch(synthetic_bands):
    # Shift the after-date grid's origin slightly so it's a different transform.

    after_dir = synthetic_bands["after_dir"]
    for band in ("B02", "B03", "B04"):
        path = after_dir / f"{band}.tif"
        with rasterio.open(path) as src:
            data = src.read(1)
            profile = src.profile.copy()
        transform = profile["transform"]
        shifted = rasterio.Affine(
            transform.a, transform.b, transform.c + 3.0, transform.d, transform.e, transform.f
        )
        profile["transform"] = shifted
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data, 1)

    before_bands = discover_bands(synthetic_bands["before_dir"])
    after_bands = discover_bands(after_dir)
    aoi = gpd.read_file(synthetic_bands["aoi_path"])
    aligned = pp.build_aligned_inputs(
        before_bands, after_bands, "before", "after", aoi, nodata_value=0.0
    )
    assert aligned.resampled_after is True


def test_to_reflectance_scales_correctly():
    dn = np.array([[5000, 10000]], dtype=np.uint16)
    refl = pp.to_reflectance(dn, 10000.0)
    assert np.allclose(refl, [[0.5, 1.0]])


def test_normalize_robust_median_mad_matches_medians():
    rng = np.random.default_rng(0)
    before = rng.normal(0.15, 0.01, size=(1, 20, 20)).astype(np.float32)
    after = rng.normal(0.20, 0.02, size=(1, 20, 20)).astype(np.float32)
    valid = np.ones((20, 20), dtype=bool)
    normalized, meta = pp.normalize_robust_median_mad(before, after, valid)
    assert abs(np.median(normalized[0]) - np.median(before[0])) < 0.01
    assert meta["method"] == "robust_median_mad"


def test_write_single_band_geotiff_masks_invalid(tmp_path):
    grid = pp.GridSpec(
        crs="EPSG:32735",
        transform=rasterio.transform.from_origin(0, 100, 10, 10),
        width=5,
        height=5,
    )
    arr = np.arange(25, dtype=np.float32).reshape(5, 5)
    valid = np.ones((5, 5), dtype=bool)
    valid[0, 0] = False
    out_path = tmp_path / "test.tif"
    pp.write_single_band_geotiff(
        out_path,
        arr,
        grid,
        nodata=-9999.0,
        dtype="float32",
        valid_mask=valid,
        build_overviews=False,
    )
    with rasterio.open(out_path) as src:
        result = src.read(1)
        assert result[0, 0] == -9999.0
        assert result[1, 1] == arr[1, 1]
