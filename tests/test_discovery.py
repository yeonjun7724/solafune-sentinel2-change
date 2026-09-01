from __future__ import annotations

import pytest

from solafune_change.discovery import discover_bands, extract_date_label
from solafune_change.errors import InputDiscoveryError


def test_discover_bands_finds_all_three(synthetic_bands):
    bands = discover_bands(synthetic_bands["before_dir"])
    assert set(bands.keys()) == {"B02", "B03", "B04"}
    for path in bands.values():
        assert path.exists()


def test_discover_bands_missing_band_raises(synthetic_bands, tmp_path):
    (synthetic_bands["before_dir"] / "B04.tif").unlink()
    with pytest.raises(InputDiscoveryError, match="B04"):
        discover_bands(synthetic_bands["before_dir"])


def test_discover_bands_duplicate_band_raises(synthetic_bands):
    extra = synthetic_bands["before_dir"] / "B02_duplicate.tif"
    extra.write_bytes((synthetic_bands["before_dir"] / "B02.tif").read_bytes())
    with pytest.raises(InputDiscoveryError, match="multiple"):
        discover_bands(synthetic_bands["before_dir"])


def test_discover_bands_missing_folder_raises(tmp_path):
    with pytest.raises(InputDiscoveryError):
        discover_bands(tmp_path / "does_not_exist")


def test_extract_date_label():
    from pathlib import Path

    assert extract_date_label(Path("sentinel2_20230812")) == "20230812"
    assert extract_date_label(Path("no_digits_here")) == "no_digits_here"
