from __future__ import annotations

import yaml
from typer.testing import CliRunner

from solafune_change.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "validate" in result.output
    assert "run" in result.output


def _write_config(synthetic_bands, tmp_path) -> str:
    config = {
        "paths": {
            "aoi": str(synthetic_bands["aoi_path"]),
            "before_folder": str(synthetic_bands["before_dir"]),
            "after_folder": str(synthetic_bands["after_dir"]),
            "output_dir": str(tmp_path / "out"),
            "processed_dir": str(tmp_path / "out" / "processed"),
        },
        "change_detection": {"method": "cva", "threshold_method": "otsu", "min_area_m2": 50.0},
        "spatial_statistics": {"enabled": False},
        "spatial_ml": {"enabled": False},
    }
    config_path = tmp_path / "test_config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return str(config_path)


def test_cli_validate_smoke(synthetic_bands, tmp_path):
    config_path = _write_config(synthetic_bands, tmp_path)
    result = runner.invoke(app, ["validate", "--config", config_path])
    assert result.exit_code == 0


def test_cli_run_smoke(synthetic_bands, tmp_path):
    config_path = _write_config(synthetic_bands, tmp_path)
    result = runner.invoke(app, ["run", "--config", config_path])
    assert result.exit_code == 0
    assert (tmp_path / "out" / "summary.json").exists()


def test_cli_run_json_progress_emits_valid_json_lines(synthetic_bands, tmp_path):
    import json

    config_path = _write_config(synthetic_bands, tmp_path)
    result = runner.invoke(app, ["run", "--config", config_path, "--json-progress"])
    assert result.exit_code == 0
    lines = [ln for ln in result.output.strip().splitlines() if ln.strip()]
    assert len(lines) > 0
    payloads = [json.loads(ln) for ln in lines]
    assert payloads[-1]["type"] == "result"
    assert "manifest" in payloads[-1]
