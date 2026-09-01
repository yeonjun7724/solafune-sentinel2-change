from __future__ import annotations

import numpy as np
import pytest

from solafune_change.errors import AnalysisError
from solafune_change.postprocessing import (
    apply_morphology,
    filter_min_area,
    min_area_to_pixel_count,
)
from solafune_change.thresholding import compute_threshold


def _bimodal_intensity():
    rng = np.random.default_rng(2)
    low = rng.normal(0.1, 0.02, size=500)
    high = rng.normal(0.8, 0.02, size=100)
    values = np.concatenate([low, high])
    arr = values.reshape(20, 30)
    return arr.astype(np.float32)


def test_otsu_threshold_separates_bimodal_distribution():
    arr = _bimodal_intensity()
    valid = np.ones_like(arr, dtype=bool)
    result = compute_threshold(arr, valid, method="otsu")
    assert 0.1 < result.value < 0.8
    assert result.binary.sum() > 0


def test_percentile_threshold_matches_percentile():
    arr = _bimodal_intensity()
    valid = np.ones_like(arr, dtype=bool)
    result = compute_threshold(arr, valid, method="percentile", percentile=90.0)
    assert np.isclose(result.value, np.percentile(arr, 90.0))


def test_manual_threshold_requires_value():
    arr = _bimodal_intensity()
    valid = np.ones_like(arr, dtype=bool)
    with pytest.raises(AnalysisError):
        compute_threshold(arr, valid, method="manual", manual_value=None)


def test_manual_threshold_uses_given_value():
    arr = _bimodal_intensity()
    valid = np.ones_like(arr, dtype=bool)
    result = compute_threshold(arr, valid, method="manual", manual_value=0.5)
    assert result.value == 0.5
    assert np.array_equal(result.binary, (arr > 0.5) & valid)


def test_morphology_opening_removes_isolated_pixel():
    binary = np.zeros((10, 10), dtype=bool)
    binary[5, 5] = True  # single isolated pixel
    binary[2:5, 2:5] = True  # solid 3x3 block survives opening
    cleaned = apply_morphology(binary, "opening", 3)
    assert not cleaned[5, 5]
    assert cleaned[3, 3]


def test_min_area_to_pixel_count():
    assert min_area_to_pixel_count(100.0, 100.0) == 1
    assert min_area_to_pixel_count(250.0, 100.0) == 3  # ceil(2.5)


def test_filter_min_area_drops_small_components():
    binary = np.zeros((10, 10), dtype=bool)
    binary[0, 0] = True  # single-pixel component: dropped
    binary[3:6, 3:6] = True  # 3x3 = 9 pixel component: kept
    result = filter_min_area(binary, min_pixel_count=4)
    assert result.binary[0, 0] == False  # noqa: E712
    assert result.binary[4, 4] == True  # noqa: E712
    assert result.n_components_after_filter == 1
