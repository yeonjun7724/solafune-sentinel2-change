"""Safe discovery of Sentinel-2 band files inside a date folder.

Band files are located by filename pattern rather than hardcoded paths, so
the pipeline works regardless of where the caller points it. Ambiguity
(missing or duplicate bands) is treated as a hard error — silently picking
"the first match" could point analysis at the wrong band.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import InputDiscoveryError

logger = logging.getLogger(__name__)

REQUIRED_BANDS: tuple[str, ...] = ("B02", "B03", "B04")
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".tif", ".tiff", ".jp2")

# Matches e.g. "B02.tif", "T35LTG_20230812T...._B02_10m.jp2", "band4.tif" is NOT matched
# (we require the canonical Sentinel-2 "B0x"/"B8A" band token to avoid false positives).
_BAND_PATTERN = re.compile(r"(?<![A-Za-z0-9])(B0[2348]|B8A)(?![A-Za-z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class BandFile:
    band: str
    path: Path


def _candidate_files(folder: Path) -> list[Path]:
    return [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]


def discover_bands(folder: Path, bands: tuple[str, ...] = REQUIRED_BANDS) -> dict[str, Path]:
    """Locate one file per requested band inside ``folder``.

    Parameters
    ----------
    folder:
        Directory containing one Sentinel-2 date's band files.
    bands:
        Band tokens to look for, e.g. ``("B02", "B03", "B04")``.

    Returns
    -------
    Mapping of band token to its resolved file path.

    Raises
    ------
    InputDiscoveryError
        If the folder does not exist, a band is missing, or more than one
        file matches a single band token.
    """
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        raise InputDiscoveryError(f"Input folder does not exist: {folder}")

    candidates = _candidate_files(folder)
    if not candidates:
        raise InputDiscoveryError(
            f"No GeoTIFF/JP2 files found in {folder}",
            detail=f"supported extensions: {SUPPORTED_EXTENSIONS}",
        )

    matches: dict[str, list[Path]] = {b: [] for b in bands}
    for path in candidates:
        found = _BAND_PATTERN.findall(path.stem)
        normalized = {m.upper() for m in found}
        for band in bands:
            if band.upper() in normalized:
                matches[band].append(path)

    result: dict[str, Path] = {}
    problems: list[str] = []
    for band in bands:
        found_paths = matches[band]
        if len(found_paths) == 0:
            problems.append(f"band {band} not found in {folder}")
        elif len(found_paths) > 1:
            names = ", ".join(p.name for p in found_paths)
            problems.append(f"band {band} matched multiple files in {folder}: {names}")
        else:
            result[band] = found_paths[0]

    if problems:
        raise InputDiscoveryError(
            f"Could not uniquely resolve required bands in {folder}",
            detail="; ".join(problems),
        )

    logger.info("Discovered bands in %s: %s", folder, {k: v.name for k, v in result.items()})
    return result


def extract_date_label(folder: Path) -> str:
    """Extract a YYYYMMDD-like date label from a folder name, else fall back to the name."""
    match = re.search(r"(20\d{6})", folder.name)
    if match:
        return match.group(1)
    logger.warning(
        "Could not find an 8-digit date in folder name '%s'; using folder name.", folder.name
    )
    return folder.name
