"""Raster alignment, AOI masking, band stacking and radiometric normalization.

Design choices (see README "Key Assumptions" for the full rationale):

* Stack band order is Red-Green-Blue (B04, B03, B02) — the conventional
  true-color composite order — not the numeric B02/B03/B04 order.
* The first ("before") date's grid is the reference grid. If the second date
  is not already on that grid it is reprojected/resampled onto it (bilinear
  for the continuous reflectance bands).
* Sentinel-2 surface reflectance here is stored as scaled uint16 (DN). No
  product metadata/XML was shipped with the assignment, so a scale factor of
  10000 (the standard ESA L1C/L2A convention, DN/10000 -> reflectance in
  [0, 1]) is assumed and documented rather than silently guessed at.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import rasterio
from rasterio import features
from rasterio.crs import CRS
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

from .atomic import atomic_output
from .errors import RasterAlignmentError

logger = logging.getLogger(__name__)

BAND_ORDER: tuple[str, ...] = ("B04", "B03", "B02")  # Red, Green, Blue
BAND_DESCRIPTIONS: dict[str, str] = {"B04": "Red (B04)", "B03": "Green (B03)", "B02": "Blue (B02)"}

NormalizationMethod = Literal["robust_median_mad", "percentile_matching", "pif_linear", "none"]


@dataclass
class GridSpec:
    crs: CRS
    transform: Affine
    width: int
    height: int

    @property
    def pixel_size_x(self) -> float:
        return abs(self.transform.a)

    @property
    def pixel_size_y(self) -> float:
        return abs(self.transform.e)

    @property
    def pixel_area_m2(self) -> float:
        return self.pixel_size_x * self.pixel_size_y

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(left, bottom, right, top) in the grid's CRS."""
        left = self.transform.c
        top = self.transform.f
        right = left + self.width * self.transform.a
        bottom = top + self.height * self.transform.e
        return (left, bottom, right, top)


@dataclass
class DateStack:
    date_label: str
    dn: np.ndarray  # (bands, H, W) uint16/float, order = BAND_ORDER
    valid_mask: np.ndarray  # (H, W) bool, True where all bands are non-NoData
    grid: GridSpec
    nodata: float


@dataclass
class AlignedInputs:
    before: DateStack
    after: DateStack
    aoi_mask: np.ndarray  # (H, W) bool
    combined_valid_mask: np.ndarray  # (H, W) bool: valid in both dates AND inside AOI
    grid: GridSpec
    resampled_after: bool


def _normalize_crs(crs: CRS) -> CRS:
    """Snap a CRS to its registry EPSG code when the two are equivalent.

    Some GeoTIFF writers embed a custom WKT (e.g. missing a PROJCS AUTHORITY
    tag) that is geometrically identical to a standard EPSG definition but
    does not resolve via ``CRS.to_epsg()``. Downstream tools (QGIS included)
    are more reliable when the output carries a recognized EPSG code, so we
    fuzzy-match against the EPSG database (``min_confidence`` guards against
    snapping to an unrelated but similarly-shaped CRS) and fall back to the
    original CRS unchanged if no confident match is found.
    """
    if crs is None:
        return crs
    try:
        if crs.to_epsg() is not None:
            return crs
    except Exception:  # noqa: BLE001
        pass
    try:
        epsg = crs.to_epsg(confidence_threshold=70)
    except Exception:  # noqa: BLE001
        epsg = None
    if epsg is not None:
        normalized = CRS.from_epsg(epsg)
        logger.info("Normalized input CRS (no direct EPSG match) to EPSG:%d", epsg)
        return normalized
    return crs


def _read_band_grid(path: Path) -> GridSpec:
    with rasterio.open(path) as src:
        return GridSpec(
            crs=_normalize_crs(src.crs), transform=src.transform, width=src.width, height=src.height
        )


def load_date_stack(
    band_paths: dict[str, Path],
    date_label: str,
    nodata_value: float,
    reference_grid: GridSpec | None = None,
    resampling: Resampling = Resampling.bilinear,
) -> tuple[DateStack, bool]:
    """Read B04/B03/B02 for one date, optionally reprojecting onto ``reference_grid``.

    Returns the stack and a flag indicating whether resampling was applied.
    """
    first_path = band_paths[BAND_ORDER[0]]
    native_grid = _read_band_grid(first_path)
    target_grid = reference_grid or native_grid
    needs_resample = reference_grid is not None and (
        native_grid.crs != target_grid.crs
        or native_grid.transform != target_grid.transform
        or native_grid.width != target_grid.width
        or native_grid.height != target_grid.height
    )

    bands = []
    for band in BAND_ORDER:
        path = band_paths[band]
        with rasterio.open(path) as src:
            arr = src.read(1).astype(np.float32)
            src_nodata = src.nodata if src.nodata is not None else nodata_value
            if needs_resample:
                dst = np.full(
                    (target_grid.height, target_grid.width), nodata_value, dtype=np.float32
                )
                reproject(
                    source=arr,
                    destination=dst,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=target_grid.transform,
                    dst_crs=target_grid.crs,
                    dst_nodata=nodata_value,
                    src_nodata=src_nodata,
                    resampling=resampling,
                )
                arr = dst
            bands.append(arr)

    dn = np.stack(bands, axis=0)
    valid_mask = np.all(dn != nodata_value, axis=0)
    stack = DateStack(
        date_label=date_label, dn=dn, valid_mask=valid_mask, grid=target_grid, nodata=nodata_value
    )
    if needs_resample:
        logger.warning(
            "Date %s was reprojected/resampled from its native grid onto the reference grid (bilinear).",
            date_label,
        )
    return stack, needs_resample


def rasterize_aoi(aoi_gdf, grid: GridSpec) -> np.ndarray:
    """Rasterize an AOI GeoDataFrame (already reprojected to ``grid.crs``) onto ``grid``."""
    shapes = [(geom, 1) for geom in aoi_gdf.geometry if geom is not None and not geom.is_empty]
    if not shapes:
        raise RasterAlignmentError("AOI has no valid geometries to rasterize")
    mask = features.rasterize(
        shapes,
        out_shape=(grid.height, grid.width),
        transform=grid.transform,
        fill=0,
        dtype="uint8",
    )
    return mask.astype(bool)


def build_aligned_inputs(
    before_bands: dict[str, Path],
    after_bands: dict[str, Path],
    before_label: str,
    after_label: str,
    aoi_gdf,
    nodata_value: float = 0.0,
) -> AlignedInputs:
    """Load both dates onto a common grid, clipped to the AOI's valid intersection."""
    before_grid = _read_band_grid(before_bands[BAND_ORDER[0]])
    before, _ = load_date_stack(before_bands, before_label, nodata_value, reference_grid=None)
    after, resampled = load_date_stack(
        after_bands,
        after_label,
        nodata_value,
        reference_grid=before_grid,
        resampling=Resampling.bilinear,
    )

    aoi_reprojected = aoi_gdf.to_crs(before.grid.crs) if aoi_gdf.crs != before.grid.crs else aoi_gdf
    aoi_mask = rasterize_aoi(aoi_reprojected, before.grid)

    combined = before.valid_mask & after.valid_mask & aoi_mask
    if combined.sum() == 0:
        raise RasterAlignmentError(
            "No pixels are simultaneously valid in both dates and inside the AOI",
            detail=f"before_valid={before.valid_mask.sum()}, after_valid={after.valid_mask.sum()}, aoi={aoi_mask.sum()}",
        )

    return AlignedInputs(
        before=before,
        after=after,
        aoi_mask=aoi_mask,
        combined_valid_mask=combined,
        grid=before.grid,
        resampled_after=resampled,
    )


def to_reflectance(dn: np.ndarray, scale: float) -> np.ndarray:
    """Convert scaled digital numbers to approximate surface reflectance in [0, ~1]."""
    return (dn.astype(np.float32) / float(scale)).astype(np.float32)


def write_stack_geotiff(
    path: Path,
    dn: np.ndarray,
    grid: GridSpec,
    nodata: float,
    dtype: str = "uint16",
    build_overviews: bool = True,
) -> None:
    """Write a (bands, H, W) array as a tiled, compressed, georeferenced GeoTIFF."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": grid.height,
        "width": grid.width,
        "count": dn.shape[0],
        "dtype": dtype,
        "crs": grid.crs,
        "transform": grid.transform,
        "nodata": nodata,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "compress": "deflate",
        "predictor": 2 if dtype != "float32" else 3,
    }
    out = dn.astype(dtype)
    with atomic_output(path) as tmp_path:
        with rasterio.open(tmp_path, "w", **profile) as dst:
            for i, band in enumerate(BAND_ORDER, start=1):
                dst.write(out[i - 1], i)
                dst.set_band_description(i, BAND_DESCRIPTIONS[band])
            if build_overviews:
                factors = [2, 4, 8]
                dst.build_overviews(factors, Resampling.average)
                dst.update_tags(ns="rio_overview", resampling="average")
    logger.info("Wrote stack GeoTIFF: %s", path)


def write_single_band_geotiff(
    path: Path,
    array: np.ndarray,
    grid: GridSpec,
    nodata: float,
    dtype: str = "float32",
    valid_mask: np.ndarray | None = None,
    build_overviews: bool = True,
    description: str | None = None,
) -> None:
    """Write a single-band (H, W) array as a tiled, compressed, georeferenced GeoTIFF.

    If ``valid_mask`` is given, pixels outside it are set to ``nodata`` before
    writing (used for intensity/binary change rasters, which are only
    meaningful inside the AOI / common valid-data mask).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = (
        array.astype(dtype, copy=True)
        if np.issubdtype(array.dtype, np.floating)
        else array.astype(dtype)
    )
    if valid_mask is not None:
        out = np.where(valid_mask, out, nodata).astype(dtype)

    profile = {
        "driver": "GTiff",
        "height": grid.height,
        "width": grid.width,
        "count": 1,
        "dtype": dtype,
        "crs": grid.crs,
        "transform": grid.transform,
        "nodata": nodata,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "compress": "deflate",
        "predictor": 3 if dtype == "float32" else 2,
    }
    with atomic_output(path) as tmp_path:
        with rasterio.open(tmp_path, "w", **profile) as dst:
            dst.write(out, 1)
            if description:
                dst.set_band_description(1, description)
            if build_overviews:
                dst.build_overviews(
                    [2, 4, 8], Resampling.average if dtype == "float32" else Resampling.nearest
                )
    logger.info("Wrote GeoTIFF: %s", path)


# --- Radiometric normalization -------------------------------------------------

_MAD_EPS = 1e-6


def _median_mad(values: np.ndarray) -> tuple[float, float]:
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return median, mad


def normalize_robust_median_mad(
    before_refl: np.ndarray, after_refl: np.ndarray, valid_mask: np.ndarray
) -> tuple[np.ndarray, dict]:
    """Band-wise robust linear match: shift+scale 'after' so its median/MAD matches 'before'.

    Uses only common valid pixels (inside AOI, valid in both dates) to estimate
    statistics, then applies the transform to the full array. Robust to the
    small fraction of extreme outliers (bright rock/water glint) that would
    distort a mean/std based match.
    """
    n_bands = before_refl.shape[0]
    normalized = after_refl.copy()
    params = {}
    for b in range(n_bands):
        b_vals = before_refl[b][valid_mask]
        a_vals = after_refl[b][valid_mask]
        med_b, mad_b = _median_mad(b_vals)
        med_a, mad_a = _median_mad(a_vals)
        scale = (mad_b / mad_a) if mad_a > _MAD_EPS else 1.0
        normalized[b] = (after_refl[b] - med_a) * scale + med_b
        params[BAND_ORDER[b]] = {
            "median_before": med_b,
            "mad_before": mad_b,
            "median_after": med_a,
            "mad_after": mad_a,
            "scale": scale,
        }
    logger.info("Robust median/MAD normalization parameters: %s", params)
    return normalized, {"method": "robust_median_mad", "bands": params}


def normalize_percentile_matching(
    before_refl: np.ndarray,
    after_refl: np.ndarray,
    valid_mask: np.ndarray,
    low: float = 2.0,
    high: float = 98.0,
) -> tuple[np.ndarray, dict]:
    """Band-wise linear match using two percentiles instead of median/MAD."""
    n_bands = before_refl.shape[0]
    normalized = after_refl.copy()
    params = {}
    for b in range(n_bands):
        b_vals = before_refl[b][valid_mask]
        a_vals = after_refl[b][valid_mask]
        b_lo, b_hi = np.percentile(b_vals, [low, high])
        a_lo, a_hi = np.percentile(a_vals, [low, high])
        denom = (a_hi - a_lo) if abs(a_hi - a_lo) > _MAD_EPS else 1.0
        scale = (b_hi - b_lo) / denom
        offset = b_lo - a_lo * scale
        normalized[b] = after_refl[b] * scale + offset
        params[BAND_ORDER[b]] = {
            "low_pct": low,
            "high_pct": high,
            "scale": float(scale),
            "offset": float(offset),
        }
    logger.info("Percentile matching normalization parameters: %s", params)
    return normalized, {"method": "percentile_matching", "bands": params}


def normalize_pif_linear(
    before_refl: np.ndarray,
    after_refl: np.ndarray,
    valid_mask: np.ndarray,
    low_change_percentile: float = 10.0,
) -> tuple[np.ndarray, dict]:
    """Pseudo-invariant-feature linear normalization.

    Pixels with the smallest initial (unnormalized) band-difference magnitude
    are assumed to be radiometrically stable ("pseudo-invariant") and used to
    fit a per-band linear regression after -> before, which is then applied to
    every pixel.
    """
    diff_mag = np.sqrt(np.sum((after_refl - before_refl) ** 2, axis=0))
    diff_valid = diff_mag[valid_mask]
    threshold = np.percentile(diff_valid, low_change_percentile)
    pif_mask = valid_mask & (diff_mag <= threshold)
    if pif_mask.sum() < 30:
        logger.warning(
            "PIF selection found too few stable pixels (%d); falling back to all valid pixels.",
            pif_mask.sum(),
        )
        pif_mask = valid_mask

    n_bands = before_refl.shape[0]
    normalized = after_refl.copy()
    params = {}
    for b in range(n_bands):
        x = after_refl[b][pif_mask]
        y = before_refl[b][pif_mask]
        a, c = np.polyfit(x, y, deg=1)
        normalized[b] = after_refl[b] * a + c
        params[BAND_ORDER[b]] = {
            "slope": float(a),
            "intercept": float(c),
            "n_pif_pixels": int(pif_mask.sum()),
        }
    logger.info("PIF linear normalization parameters: %s", params)
    return normalized, {
        "method": "pif_linear",
        "low_change_percentile": low_change_percentile,
        "bands": params,
    }


def apply_normalization(
    method: NormalizationMethod,
    before_refl: np.ndarray,
    after_refl: np.ndarray,
    valid_mask: np.ndarray,
) -> tuple[np.ndarray, dict]:
    """Dispatch to the requested normalization method; 'none' is a documented passthrough."""
    if method == "robust_median_mad":
        return normalize_robust_median_mad(before_refl, after_refl, valid_mask)
    if method == "percentile_matching":
        return normalize_percentile_matching(before_refl, after_refl, valid_mask)
    if method == "pif_linear":
        return normalize_pif_linear(before_refl, after_refl, valid_mask)
    if method == "none":
        return after_refl.copy(), {"method": "none"}
    raise RasterAlignmentError(f"Unknown normalization method: {method}")
