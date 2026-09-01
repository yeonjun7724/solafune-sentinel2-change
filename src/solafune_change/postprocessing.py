"""Morphological cleanup, connected-component labeling and minimum-area filtering
for a binary change raster."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy import ndimage
from skimage.measure import label
from skimage.morphology import closing, footprint_rectangle, opening

logger = logging.getLogger(__name__)

MorphOperation = Literal["opening", "closing", "opening_then_closing", "none"]


@dataclass
class PostprocessResult:
    binary: np.ndarray  # (H, W) bool, final cleaned binary raster
    labels: np.ndarray  # (H, W) int32, connected-component labels (0 = background)
    n_components_before_filter: int
    n_components_after_filter: int
    min_pixel_count: int


def apply_morphology(
    binary: np.ndarray, operation: MorphOperation, structure_size: int
) -> np.ndarray:
    """Apply binary opening/closing to remove speckle and fill small gaps."""
    if operation == "none" or structure_size < 1:
        return binary
    footprint = footprint_rectangle((structure_size, structure_size))
    result = binary
    if operation in ("opening", "opening_then_closing"):
        result = opening(result, footprint)
    if operation in ("closing", "opening_then_closing"):
        result = closing(result, footprint)
    return result


def filter_min_area(
    binary: np.ndarray, min_pixel_count: int, fill_holes: bool = False
) -> PostprocessResult:
    """Label connected components and drop any smaller than ``min_pixel_count`` pixels."""
    labels, n_before = label(binary, connectivity=2, return_num=True)
    counts = np.bincount(labels.ravel())
    keep_labels = np.where(counts >= min_pixel_count)[0]
    keep_labels = keep_labels[keep_labels != 0]

    keep_mask = np.isin(labels, keep_labels)
    filtered = binary & keep_mask

    if fill_holes:
        filtered = ndimage.binary_fill_holes(filtered)

    labels_after, n_after = label(filtered, connectivity=2, return_num=True)

    logger.info(
        "Connected components: %d found, %d kept after min_pixel_count=%d filter (fill_holes=%s)",
        n_before,
        n_after,
        min_pixel_count,
        fill_holes,
    )
    return PostprocessResult(
        binary=filtered,
        labels=labels_after,
        n_components_before_filter=n_before,
        n_components_after_filter=n_after,
        min_pixel_count=min_pixel_count,
    )


def min_area_to_pixel_count(min_area_m2: float, pixel_area_m2: float) -> int:
    """Convert a minimum-area threshold in m^2 to a minimum pixel count for this grid."""
    if pixel_area_m2 <= 0:
        raise ValueError("pixel_area_m2 must be positive")
    return max(1, int(np.ceil(min_area_m2 / pixel_area_m2)))
