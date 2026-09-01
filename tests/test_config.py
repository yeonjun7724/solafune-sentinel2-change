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


def test_processed_dir_defaults_to_none_when_unset_in_yaml(tmp_path):
    """Regression test for a real bug: a config file with no explicit
    paths.processed_dir must NOT fall back to a relative default resolved
    against the config file's own location. That location can be a
    short-lived temp file far from any sensible project root (the QGIS
    plugin's external-execution mode writes exactly such a file per run),
    so processed_dir must stay None here and let
    solafune_change.pipeline.run_pipeline() derive it from the (always
    absolute) resolved output_dir instead.
    """
    import yaml

    # Config file lives somewhere unrelated to output_dir, simulating a temp file.
    config_dir = tmp_path / "unrelated" / "nested" / "temp_location"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "solafune_change_tmp.yaml"

    output_dir = tmp_path / "chosen_output"
    doc = {
        "paths": {
            "aoi": str(tmp_path / "aoi.geojson"),
            "before_folder": str(tmp_path / "before"),
            "after_folder": str(tmp_path / "after"),
            "output_dir": str(output_dir),
        }
    }
    config_path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    config = load_config(config_path, base_dir=config_path.resolve().parent.parent)
    assert config.paths.processed_dir is None

    request = config_to_request(config)
    assert request.processed_dir is None


def test_processed_dir_respected_when_explicitly_set(tmp_path):
    import yaml

    config_path = tmp_path / "config.yaml"
    doc = {
        "paths": {
            "aoi": str(tmp_path / "aoi.geojson"),
            "before_folder": str(tmp_path / "before"),
            "after_folder": str(tmp_path / "after"),
            "output_dir": str(tmp_path / "out"),
            "processed_dir": str(tmp_path / "custom_processed"),
        }
    }
    config_path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    config = load_config(config_path, base_dir=tmp_path)
    assert config.paths.processed_dir == tmp_path / "custom_processed"
