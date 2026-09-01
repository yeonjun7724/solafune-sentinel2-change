"""Robust RGB Change Vector Analysis (CVA) — the primary change detection method.

For each band, the pixel-wise difference between dates is standardized with
robust statistics (median and MAD, computed over the common valid mask only)
before being combined into a change-vector magnitude:

    z_b   = (diff_b - median(diff_b)) / (1.4826 * MAD(diff_b))
    CVA   = sqrt(z_B04^2 + z_B03^2 + z_B02^2)

Standardizing per band before combining prevents the band with the largest
raw digital-number range from dominating the magnitude, and using median/MAD
instead of mean/std keeps a handful of extreme pixels (cloud edges, glint,
sensor artifacts) from distorting the scale used for every other pixel — the
main weakness identified in the baseline method (see :mod:`solafune_change.baseline`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .preprocessing import BAND_ORDER

logger = logging.getLogger(__name__)

# 1.4826 scales MAD to be a consistent estimator of the standard deviation
# under a normal distribution, which is the conventional robust-statistics
# convention (see e.g. Rousseeuw & Croux, 1993).
_MAD_TO_STD = 1.4826
_MAD_EPS = 1e-6


@dataclass
class CVAResult:
    cva: np.ndarray  # (H, W) float32, robust change-vector magnitude (unitless, >= 0)
    band_diff: (
        np.ndarray
    )  # (bands, H, W) float32, signed raw reflectance differences (after - before)
    band_zscore: np.ndarray  # (bands, H, W) float32, robust per-band standardized differences
    brightness_diff: np.ndarray  # (H, W) float32, mean of signed band differences
    stats: dict


def compute_robust_cva(
    before_refl: np.ndarray, after_refl: np.ndarray, valid_mask: np.ndarray
) -> CVAResult:
    """Compute robust multivariate CVA magnitude from co-registered reflectance stacks.

    ``after_refl`` should already have any radiometric normalization applied
    upstream (see :mod:`solafune_change.preprocessing`); this function only
    performs the per-band robust standardization required by CVA itself.
    """
    if before_refl.shape != after_refl.shape:
        raise ValueError(f"Shape mismatch: before={before_refl.shape} after={after_refl.shape}")

    n_bands = before_refl.shape[0]
    band_diff = after_refl.astype(np.float32) - before_refl.astype(np.float32)
    band_zscore = np.zeros_like(band_diff, dtype=np.float32)
    stats: dict[str, dict] = {}

    for b in range(n_bands):
        vals = band_diff[b][valid_mask]
        median = float(np.median(vals))
        mad = float(np.median(np.abs(vals - median)))
        robust_std = mad * _MAD_TO_STD
        mad_near_zero = robust_std < _MAD_EPS
        if mad_near_zero:
            # Fall back to (robust) standard deviation when MAD collapses to ~0
            # (e.g. a near-constant band difference); if that is also ~0 the
            # band contributes no signal and z-scores are set to zero rather
            # than dividing by a near-zero number.
            fallback_std = float(np.std(vals))
            denom = fallback_std if fallback_std > _MAD_EPS else 1.0
            logger.warning(
                "Band %s: MAD ~ 0 (median=%.6f); falling back to std=%.6f for standardization.",
                BAND_ORDER[b],
                median,
                fallback_std,
            )
        else:
            denom = robust_std

        band_zscore[b] = (band_diff[b] - median) / denom
        stats[BAND_ORDER[b]] = {
            "median_diff": median,
            "mad": mad,
            "robust_std": robust_std,
            "mad_near_zero_fallback": mad_near_zero,
            "denominator_used": denom,
        }

    cva = np.sqrt(np.sum(band_zscore.astype(np.float64) ** 2, axis=0)).astype(np.float32)
    brightness_diff = np.mean(band_diff, axis=0).astype(np.float32)

    logger.info("Robust CVA per-band standardization stats: %s", stats)
    return CVAResult(
        cva=cva,
        band_diff=band_diff.astype(np.float32),
        band_zscore=band_zscore,
        brightness_diff=brightness_diff,
        stats=stats,
    )
