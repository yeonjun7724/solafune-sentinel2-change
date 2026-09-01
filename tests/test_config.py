from __future__ import annotations

from pathlib import Path

from solafune_change.config import config_to_request, load_config, request_to_yaml_dict


def test_load_default_config():
    repo_root = Path(__file__).resolve().parent.parent
    config = load_config(repo_root / "config" / "default.yaml", base_dir=repo_root)
    assert config.paths.before_folder.name == "sentinel2_20230812"
    assert config.change_detection.method == "both"
    assert config.spatial_statistics.grid_size_m == 150.0


def test_config_to_request_round_trip():
    repo_root = Path(__file__).resolve().parent.parent
    config = load_config(repo_root / "config" / "default.yaml", base_dir=repo_root)
    request = config_to_request(config)
    assert request.method == config.change_detection.method
    assert request.spatial_grid_size_m == config.spatial_statistics.grid_size_m

    doc = request_to_yaml_dict(request)
    assert doc["change_detection"]["method"] == config.change_detection.method
    assert doc["spatial_statistics"]["grid_size_m"] == config.spatial_statistics.grid_size_m


def test_load_config_missing_file_raises(tmp_path):
    import pytest

    from solafune_change.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        load_config(tmp_path / "missing.yaml")
