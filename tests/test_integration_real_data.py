"""Integration tests against the actual assignment input data.

Skipped automatically if inputs/ is not present (e.g. a CI checkout that
excludes the (large, real) satellite imagery). Run explicitly with:
    pytest -m integration
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_BEFORE = REPO_ROOT / "inputs" / "data" / "sentinel2_20230812"
REAL_AFTER = REPO_ROOT / "inputs" / "data" / "sentinel2_20230902"
REAL_AOI = REPO_ROOT / "inputs" / "aoi.geojson"

pytestmark = pytest.mark.integration
requires_real_data = pytest.mark.skipif(
    not (REAL_BEFORE.exists() and REAL_AFTER.exists() and REAL_AOI.exists()),
    reason="real assignment input data not present under inputs/",
)


@requires_real_data
def test_validate_request_on_real_data(tmp_path):
    from solafune_change.pipeline import validate_request
    from solafune_change.types import PipelineRequest

    request = PipelineRequest(
        before_folder=REAL_BEFORE,
        after_folder=REAL_AFTER,
        aoi_path=REAL_AOI,
        output_dir=tmp_path / "out",
    )
    report = validate_request(request)
    assert report.is_valid


@requires_real_data
def test_full_pipeline_on_real_data(tmp_path):
    from solafune_change.pipeline import run_pipeline
    from solafune_change.types import PipelineRequest

    request = PipelineRequest(
        before_folder=REAL_BEFORE,
        after_folder=REAL_AFTER,
        aoi_path=REAL_AOI,
        output_dir=tmp_path / "out",
        processed_dir=tmp_path / "out" / "processed",
        method="both",
        spatial_statistics_enabled=True,
        spatial_grid_size_m=200.0,
        permutations=99,
        spatial_ml_enabled=False,
    )
    result = run_pipeline(request)

    assert result.database.exists()
    assert result.summary["feature_count"] > 0
    assert result.summary["global_moran_i"] is not None
    assert -1.0 <= result.summary["global_moran_i"] <= 1.0
