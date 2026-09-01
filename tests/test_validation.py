from __future__ import annotations

from solafune_change.discovery import discover_bands
from solafune_change.validation import read_raster_metadata, validate_inputs


def test_validate_inputs_clean_data_is_valid(synthetic_bands):
    before_bands = discover_bands(synthetic_bands["before_dir"])
    after_bands = discover_bands(synthetic_bands["after_dir"])
    report = validate_inputs(
        before_bands, after_bands, synthetic_bands["aoi_path"], "before", "after"
    )
    assert report.is_valid
    assert len(report.band_metadata) == 6


def test_validate_inputs_detects_dimension_mismatch(synthetic_bands, tmp_path):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    bad_path = synthetic_bands["before_dir"] / "B02.tif"
    transform = from_origin(500000.0, 8600000.0, 10.0, 10.0)
    with rasterio.open(
        bad_path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="uint16",
        crs="EPSG:32735",
        transform=transform,
        nodata=0,
    ) as dst:
        dst.write(np.ones((10, 10), dtype="uint16"), 1)

    before_bands = discover_bands(synthetic_bands["before_dir"])
    after_bands = discover_bands(synthetic_bands["after_dir"])
    report = validate_inputs(
        before_bands, after_bands, synthetic_bands["aoi_path"], "before", "after"
    )
    assert not report.is_valid
    assert any(i.code == "band_dimension_mismatch" for i in report.errors)


def test_validate_inputs_missing_aoi(synthetic_bands, tmp_path):
    before_bands = discover_bands(synthetic_bands["before_dir"])
    after_bands = discover_bands(synthetic_bands["after_dir"])
    report = validate_inputs(
        before_bands, after_bands, tmp_path / "missing.geojson", "before", "after"
    )
    assert not report.is_valid
    assert any(i.code == "aoi_missing" for i in report.errors)


def test_read_raster_metadata_reports_valid_ratio(synthetic_bands):
    before_bands = discover_bands(synthetic_bands["before_dir"])
    meta = read_raster_metadata(before_bands["B04"], "before", "B04")
    assert 0.0 < meta.valid_pixel_ratio <= 1.0
    assert meta.dtype == "uint16"
    assert meta.pixel_size_x == 10.0
