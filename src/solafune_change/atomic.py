"""Atomic-write helper: write to a temp path, then rename into place.

Used for every pipeline output so a cancelled or crashed run never leaves a
half-written file at the canonical output path — a caller (the QGIS plugin,
in particular) can safely treat "file exists at its canonical path" as "this
artifact is complete".
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def atomic_output(path: Path) -> Iterator[Path]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the original suffix (e.g. ".gpkg", ".tif") on the temp file: some
    # drivers/libraries (observed: pyogrio/GDAL's GPKG driver) infer format
    # from the file extension and warn/misbehave on a bare ".tmp" suffix.
    tmp_path = path.with_name(f"{path.stem}.tmp{path.suffix}")
    try:
        yield tmp_path
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
