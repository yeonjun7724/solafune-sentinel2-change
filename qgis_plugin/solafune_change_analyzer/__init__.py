"""QGIS plugin entry point.

This module MUST be importable by the QGIS Plugin Manager even when none of
the core engine's dependencies (rasterio, scikit-learn, ...) are installed in
QGIS's Python environment -- so it imports nothing heavy at module scope.
Everything dependency-sensitive is deferred to :mod:`plugin`, which itself
only imports it lazily when the user actually runs an analysis.
"""

from __future__ import annotations


def classFactory(iface):  # noqa: N802 - QGIS-mandated function name
    from .plugin import SolafuneChangeAnalyzerPlugin

    return SolafuneChangeAnalyzerPlugin(iface)
