"""Solafune Sentinel-2 change analysis core engine.

This package is the single analysis engine shared by the CLI
(:mod:`solafune_change.cli`) and the QGIS plugin (``qgis_plugin/``). It has
no dependency on QGIS or any GUI toolkit so it can be imported and tested in
a plain Python environment.
"""

from __future__ import annotations

import os
from pathlib import Path

# The host machine may have a stale PROJ_LIB/PROJ_DATA environment variable
# pointing at another application's bundled PROJ database (observed here: a
# PostGIS install), which shadows rasterio's own bundled, version-matched
# proj.db and makes GDAL emit spurious CRS mismatch warnings on every raster
# open. Point PROJ at rasterio's own bundled data directory instead, before
# rasterio touches PROJ anywhere else in this package.
try:
    import rasterio

    _proj_dir = str(Path(rasterio.__file__).parent / "proj_data")
    if Path(_proj_dir).exists():
        os.environ["PROJ_LIB"] = _proj_dir
        os.environ["PROJ_DATA"] = _proj_dir
except Exception:  # noqa: BLE001 - best-effort; never block import on this
    pass

__version__ = "0.1.0"
