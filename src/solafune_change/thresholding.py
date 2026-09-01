"""Threshold selection and binarization for a change-intensity raster."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
from skimage.filters import threshold_otsu

from .errors import AnalysisError

logger = logging.getLogger(__name__)

ThresholdMethod = Literal["otsu", "percentile", "manual"]


@dataclass
class ThresholdResult:
    method: ThresholdMethod
    value: float
    binary: np.ndarray  # (H, W) bool, True = changed, restricted to valid_mask


def compute_threshold(
    intensity: np.ndarray,
    valid_mask: np.ndarray,
    method: ThresholdMethod = "otsu",
    percentile: float = 95.0,
    manual_value: float | None = None,
) -> ThresholdResult:
    """Select a threshold on ``intensity`` and binarize (valid-pixel restricted).

    * ``otsu``: automatic bimodal threshold (Otsu, 1979) computed on valid pixels.
    * ``percentile``: value at the given percentile of the valid-pixel distribution.
    * ``manual``: a user-supplied absolute value.
    """
    valid_values = intensity[valid_mask]
    if valid_values.size == 0:
        raise AnalysisError("Cannot threshold an intensity raster with zero valid pixels")

    if method == "otsu":
        try:
            value = float(threshold_otsu(valid_values))
        except ValueError as exc:
            raise AnalysisError(
                "Otsu thresholding failed (degenerate/constant intensity distribution)",
                detail=str(exc),
            ) from exc
    elif method == "percentile":
        if not (0.0 <= percentile <= 100.0):
            raise AnalysisError(f"percentile must be within [0, 100], got {percentile}")
        value = float(np.percentile(valid_values, percentile))
    elif method == "manual":
        if manual_value is None:
            raise AnalysisError("threshold_method='manual' requires manual_threshold to be set")
        value = float(manual_value)
    else:
        raise AnalysisError(f"Unknown threshold method: {method}")

    binary = np.zeros_like(intensity, dtype=bool)
    binary[valid_mask] = intensity[valid_mask] > value

    logger.info(
        "Threshold method=%s value=%.6f -> %d / %d valid pixels flagged as changed (%.2f%%)",
        method,
        value,
        int(binary.sum()),
        int(valid_mask.sum()),
        100.0 * binary.sum() / max(valid_mask.sum(), 1),
    )
    return ThresholdResult(method=method, value=value, binary=binary)
