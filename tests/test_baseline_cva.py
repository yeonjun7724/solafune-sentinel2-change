from __future__ import annotations

import numpy as np

from solafune_change.baseline import compute_baseline_change
from solafune_change.cva import compute_robust_cva


def test_baseline_change_detects_injected_block():
    before = np.full((3, 20, 20), 0.15, dtype=np.float32)
    after = before.copy()
    after[:, 5:15, 5:15] += 0.3
    valid = np.ones((20, 20), dtype=bool)

    result = compute_baseline_change(before, after, valid)
    assert result.intensity[10, 10] > result.intensity[0, 0]
    assert result.intensity.max() <= 1.0 + 1e-6
    assert result.intensity.min() >= 0.0


def test_baseline_constant_distance_is_all_zero():
    before = np.full((3, 5, 5), 0.1, dtype=np.float32)
    after = before.copy()  # zero difference everywhere -> constant distance
    valid = np.ones((5, 5), dtype=bool)
    result = compute_baseline_change(before, after, valid)
    assert np.allclose(result.intensity, 0.0)


def test_robust_cva_flags_injected_block_as_high_magnitude():
    rng = np.random.default_rng(1)
    before = rng.normal(0.15, 0.01, size=(3, 20, 20)).astype(np.float32)
    after = before.copy()
    after[:, 5:15, 5:15] += 0.2
    valid = np.ones((20, 20), dtype=bool)

    result = compute_robust_cva(before, after, valid)
    assert result.cva[10, 10] > np.median(result.cva)
    assert result.band_diff.shape == before.shape


def test_robust_cva_handles_mad_near_zero_without_crashing():
    before = np.full((3, 10, 10), 0.1, dtype=np.float32)
    after = before.copy()
    after[0, 0, 0] += 0.5  # single outlier -> band diff MAD is ~0 elsewhere
    valid = np.ones((10, 10), dtype=bool)

    result = compute_robust_cva(before, after, valid)
    assert np.isfinite(result.cva).all()
    assert any(stat["mad_near_zero_fallback"] for stat in result.stats.values())
