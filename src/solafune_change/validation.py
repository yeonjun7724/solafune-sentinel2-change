"""Raster/AOI metadata extraction and consistency validation.

Every band and date is inspected (CRS, transform, dimensions, dtype, NoData,
valid-pixel ratio) and cross-checked so that alignment problems are caught
before any analysis runs, with a clear, structured report rather than an
opaque failure deep inside numpy.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.errors import RasterioIOError

from .errors import RasterAlignmentError
from .types import ValidationReport

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RasterMetadata:
    path: str
    date_label: str
    band: str
    crs: str | None
    width: int
    height: int
    transform: tuple[float, float, float, float, float, float]
    pixel_size_x: float
    pixel_size_y: float
    bounds: tuple[float, float, float, float]
    dtype: str
    nodata: float | None
    valid_pixel_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_raster_metadata(path: Path, date_label: str, band: str) -> RasterMetadata:
    """Open a single band raster and extract its metadata plus valid-pixel ratio."""
    try:
        with rasterio.open(path) as src:
            arr = src.read(1)
            nodata = src.nodata
            if nodata is not None:
                valid = arr != nodata
            else:
                valid = np.ones_like(arr, dtype=bool)
            valid_ratio = float(valid.mean()) if valid.size else 0.0
            transform = src.transform
            return RasterMetadata(
                path=str(path),
                date_label=date_label,
                band=band,
                crs=src.crs.to_string() if src.crs else None,
                width=src.width,
                height=src.height,
                transform=(
                    transform.a,
                    transform.b,
                    transform.c,
                    transform.d,
                    transform.e,
                    transform.f,
                ),
                pixel_size_x=abs(transform.a),
                pixel_size_y=abs(transform.e),
                bounds=tuple(src.bounds),
                dtype=str(src.dtypes[0]),
                nodata=nodata,
                valid_pixel_ratio=valid_ratio,
            )
    except RasterioIOError as exc:
        raise RasterAlignmentError(f"Could not open raster: {path}", detail=str(exc)) from exc


def validate_inputs(
    before_bands: dict[str, Path],
    after_bands: dict[str, Path],
    aoi_path: Path,
    before_label: str,
    after_label: str,
) -> ValidationReport:
    """Run the full set of input-consistency checks and return a structured report.

    Checks: per-band metadata extraction, band-to-band grid agreement within a
    date, date-to-date grid agreement, CRS presence, and AOI validity/overlap.
    Errors block the pipeline; warnings (e.g. AOI needing reprojection) do not.
    """
    report = ValidationReport()

    before_meta: dict[str, RasterMetadata] = {}
    after_meta: dict[str, RasterMetadata] = {}

    for band, path in before_bands.items():
        try:
            meta = read_raster_metadata(path, before_label, band)
            before_meta[band] = meta
            report.band_metadata.append(meta.to_dict())
            if meta.crs is None:
                report.add(
                    "error", "missing_crs", f"{before_label}/{band} has no CRS", path=str(path)
                )
            if meta.valid_pixel_ratio < 0.5:
                report.add(
                    "warning",
                    "low_valid_ratio",
                    f"{before_label}/{band} has only {meta.valid_pixel_ratio:.1%} valid (non-NoData) pixels",
                    path=str(path),
                )
        except RasterAlignmentError as exc:
            report.add("error", "unreadable_raster", exc.user_message, path=str(path))

    for band, path in after_bands.items():
        try:
            meta = read_raster_metadata(path, after_label, band)
            after_meta[band] = meta
            report.band_metadata.append(meta.to_dict())
            if meta.crs is None:
                report.add(
                    "error", "missing_crs", f"{after_label}/{band} has no CRS", path=str(path)
                )
            if meta.valid_pixel_ratio < 0.5:
                report.add(
                    "warning",
                    "low_valid_ratio",
                    f"{after_label}/{band} has only {meta.valid_pixel_ratio:.1%} valid (non-NoData) pixels",
                    path=str(path),
                )
        except RasterAlignmentError as exc:
            report.add("error", "unreadable_raster", exc.user_message, path=str(path))

    if not report.errors:
        _check_grid_agreement(before_meta, f"within {before_label}", report)
        _check_grid_agreement(after_meta, f"within {after_label}", report)

        ref_band = "B04"
        if ref_band in before_meta and ref_band in after_meta:
            b, a = before_meta[ref_band], after_meta[ref_band]
            if b.crs != a.crs:
                report.add(
                    "warning",
                    "date_crs_mismatch",
                    f"{before_label} and {after_label} have different CRS; the after image will be "
                    "reprojected to the before image's grid.",
                    before_crs=b.crs,
                    after_crs=a.crs,
                )
            elif (b.width, b.height, b.transform) != (a.width, a.height, a.transform):
                report.add(
                    "warning",
                    "date_grid_mismatch",
                    f"{before_label} and {after_label} are on different pixel grids; the after image will "
                    f"be resampled to the {before_label} grid.",
                )

    _check_aoi(aoi_path, before_meta, report)

    return report


def _check_grid_agreement(
    meta_by_band: dict[str, RasterMetadata], context: str, report: ValidationReport
) -> None:
    if len(meta_by_band) < 2:
        return
    items = list(meta_by_band.items())
    ref_band, ref = items[0]
    for band, meta in items[1:]:
        if meta.crs != ref.crs:
            report.add(
                "error",
                "band_crs_mismatch",
                f"CRS mismatch {context}: {ref_band}={ref.crs} vs {band}={meta.crs}",
            )
        if (meta.width, meta.height) != (ref.width, ref.height):
            report.add(
                "error",
                "band_dimension_mismatch",
                f"Dimension mismatch {context}: {ref_band}={ref.width}x{ref.height} vs "
                f"{band}={meta.width}x{meta.height}",
            )
        if meta.transform != ref.transform:
            report.add(
                "error",
                "band_transform_mismatch",
                f"Transform mismatch {context}: {ref_band} vs {band}",
            )


def _check_aoi(
    aoi_path: Path, before_meta: dict[str, RasterMetadata], report: ValidationReport
) -> None:
    if not Path(aoi_path).exists():
        report.add("error", "aoi_missing", f"AOI file not found: {aoi_path}")
        return
    try:
        aoi = gpd.read_file(aoi_path)
    except Exception as exc:  # noqa: BLE001 - surface any vector I/O failure as a validation issue
        report.add(
            "error", "aoi_unreadable", f"Could not read AOI file: {aoi_path}", detail=str(exc)
        )
        return

    if aoi.empty:
        report.add("error", "aoi_empty", f"AOI file has no features: {aoi_path}")
        return
    if not aoi.is_valid.all():
        report.add(
            "warning",
            "aoi_invalid_geometry",
            "AOI contains invalid geometries; they will be repaired (buffer(0)).",
        )
    if aoi.crs is None:
        report.add("warning", "aoi_missing_crs", "AOI has no CRS; assuming EPSG:4326 (WGS84).")

    ref_band = "B04" if "B04" in before_meta else (next(iter(before_meta), None))
    if ref_band is None or aoi.crs is None:
        return
    raster_crs = before_meta[ref_band].crs
    try:
        aoi_reprojected = aoi.to_crs(raster_crs)
    except Exception as exc:  # noqa: BLE001
        report.add(
            "error",
            "aoi_reprojection_failed",
            "Could not reproject AOI to raster CRS",
            detail=str(exc),
        )
        return

    raster_bounds = before_meta[ref_band].bounds
    from shapely.geometry import box

    raster_box = box(*raster_bounds)
    if not aoi_reprojected.unary_union.intersects(raster_box):
        report.add(
            "error",
            "aoi_no_overlap",
            "AOI does not intersect the imagery extent",
            aoi_bounds=tuple(aoi_reprojected.total_bounds),
            raster_bounds=raster_bounds,
        )
