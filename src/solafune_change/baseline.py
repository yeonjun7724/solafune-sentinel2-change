"""Baseline change detection: an independent reimplementation of the idea in
``inputs/example_change_detection.py``.

The provided example computes a per-pixel Euclidean distance across bands
between the two dates and min-max normalizes it to [0, 1] / [0, 255]. That
core idea is reproduced here (not copy-pasted): typed, logged, restricted to
the AOI/valid-pixel mask for normalization, and returning both the raw
distance and the normalized intensity as separate, documented values.

Assumptions inherited from the example (and their consequences):

* No radiometric/atmospheric normalization between dates — any whole-scene
  brightness shift between 2023-08-12 and 2023-09-02 is folded directly into
  "change".
* Global min-max normalization — a single extreme pixel (cloud edge, sensor
  artifact) stretches the whole intensity scale and can suppress genuine but
  moderate change elsewhere. This is the main motivation for the robust CVA
  method in :mod:`solafune_change.cva`, which standardizes per band with
  median/MAD instead.
* Distance in raw band units treats all three bands as equally scaled, which
  is reasonable here since B02/B03/B04 share the same DN scale, but would not
  generalize to bands with different units.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BaselineResult:
    distance: np.ndarray  # (H, W) float32, raw Euclidean distance in reflectance units
    intensity: np.ndarray  # (H, W) float32 in [0, 1], min-max normalized over valid pixels only
    valid_mask: np.ndarray  # (H, W) bool


def compute_baseline_change(
    before_refl: np.ndarray, after_refl: np.ndarray, valid_mask: np.ndarray
) -> BaselineResult:
    """Pixel-wise multi-band Euclidean distance, min-max normalized within the valid mask.

    Parameters
    ----------
    before_refl, after_refl:
        Arrays shaped (bands, H, W), same band order, already co-registered.
    valid_mask:
        (H, W) boolean mask of pixels considered in the min-max normalization
        range (AOI intersected with both dates' valid-data masks). Pixels
        outside the mask still get a distance value but do not influence the
        normalization range.
    """
    if before_refl.shape != after_refl.shape:
        raise ValueError(f"Shape mismatch: before={before_refl.shape} after={after_refl.shape}")

    diff = after_refl.astype(np.float32) - before_refl.astype(np.float32)
    distance = np.sqrt(np.sum(diff.astype(np.float64) ** 2, axis=0)).astype(np.float32)

    valid_values = distance[valid_mask]
    if valid_values.size == 0:
        raise ValueError("valid_mask selects zero pixels; cannot normalize baseline distance")

    min_val = float(valid_values.min())
    max_val = float(valid_values.max())
    value_range = max_val - min_val

    if value_range < 1e-12:
        logger.warning(
            "Baseline distance is constant over the valid mask; intensity set to zero everywhere."
        )
        intensity = np.zeros_like(distance, dtype=np.float32)
    else:
        intensity = ((distance - min_val) / value_range).astype(np.float32)
        intensity = np.clip(intensity, 0.0, 1.0)

    logger.info(
        "Baseline change: min=%.6f max=%.6f (valid-pixel range used for normalization)",
        min_val,
        max_val,
    )
    return BaselineResult(distance=distance, intensity=intensity, valid_mask=valid_mask)
