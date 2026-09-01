from __future__ import annotations

from pathlib import Path

from solafune_change.pipeline import run_pipeline, validate_request
from solafune_change.types import PipelineRequest


def _request(synthetic_bands, output_dir: Path, **overrides) -> PipelineRequest:
    base = dict(
        before_folder=synthetic_bands["before_dir"],
        after_folder=synthetic_bands["after_dir"],
        aoi_path=synthetic_bands["aoi_path"],
        output_dir=output_dir,
        processed_dir=output_dir / "processed",
        method="both",
        spatial_statistics_enabled=True,
        spatial_grid_size_m=60.0,
        permutations=99,
        spatial_ml_enabled=False,
        min_area_m2=50.0,
        random_seed=42,
    )
    base.update(overrides)
    return PipelineRequest(**base)


def test_validate_request_passes_on_synthetic_data(synthetic_bands, tmp_path):
    request = _request(synthetic_bands, tmp_path / "out")
    report = validate_request(request)
    assert report.is_valid


def test_validate_request_fails_on_missing_folder(synthetic_bands, tmp_path):
    request = _request(synthetic_bands, tmp_path / "out", before_folder=tmp_path / "nope")
    report = validate_request(request)
    assert not report.is_valid


def test_run_pipeline_end_to_end_on_synthetic_data(synthetic_bands, tmp_path):
    request = _request(synthetic_bands, tmp_path / "out")
    result = run_pipeline(request)

    assert result.cva_intensity.exists()
    assert result.cva_binary.exists()
    assert result.baseline_intensity.exists()
    assert result.database.exists()
    assert result.summary_json.exists()
    assert result.run_manifest_json.exists()
    assert result.report_md.exists()
    assert result.summary["feature_count"] >= 1  # the injected change block should be detected
    assert result.summary["global_moran_i"] is not None


def test_run_pipeline_is_reproducible_with_fixed_seed(synthetic_bands, tmp_path):
    r1 = run_pipeline(_request(synthetic_bands, tmp_path / "out1", random_seed=7))
    r2 = run_pipeline(_request(synthetic_bands, tmp_path / "out2", random_seed=7))

    assert r1.summary["feature_count"] == r2.summary["feature_count"]
    assert r1.summary["changed_area_m2"] == r2.summary["changed_area_m2"]
    assert r1.summary["global_moran_i"] == r2.summary["global_moran_i"]
