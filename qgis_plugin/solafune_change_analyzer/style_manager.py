"""Applies bundled QML styles to result layers.

For the two continuous rasters (CVA / baseline intensity) the bundled QML's
numeric stops are placeholders (see ``styles/README`` in the styles folder) --
after loading the QML this module recomputes the classification min/max from
the layer's actual pixel statistics (2nd/98th percentile) and rewrites the
color-ramp shader in place, so the style is correct for *this* run's data
range without needing a fresh QML file per run.
"""

from __future__ import annotations

import logging
from pathlib import Path

from qgis.core import QgsRasterBandStats, QgsRasterLayer

logger = logging.getLogger(__name__)

STYLES_DIR = Path(__file__).resolve().parent / "styles"

RASTER_STYLE_MAP = {
    "cva_intensity": "cva_intensity.qml",
    "baseline_intensity": "baseline_intensity.qml",
    "binary": "change_binary.qml",
}
VECTOR_STYLE_MAP = {
    "change_polygons": "change_polygons.qml",
    "lisa_clusters": "lisa_clusters.qml",
    "gi_hotspots": "gi_hotspots.qml",
    "ml_anomalies": "ml_anomalies.qml",
}


def apply_style(layer, style_key: str) -> bool:
    """Load the bundled QML matching ``style_key`` onto ``layer``. Returns success."""
    qml_name = RASTER_STYLE_MAP.get(style_key) or VECTOR_STYLE_MAP.get(style_key)
    if qml_name is None:
        logger.warning("No bundled style registered for key '%s'", style_key)
        return False
    qml_path = STYLES_DIR / qml_name
    if not qml_path.exists():
        logger.warning("Bundled style file missing: %s", qml_path)
        return False

    # QgsMapLayer.loadNamedStyle's C++ signature is loadNamedStyle(uri, bool
    # &resultFlag, ...); PyQGIS turns the by-reference resultFlag into a
    # second *return* value, so the tuple order is (message, ok) -- NOT
    # (ok, message). Unpacking it the other way around silently treats every
    # successful load (message="") as a failure, which was skipping the
    # raster rescale/repaint step for every styled layer.
    message, ok = layer.loadNamedStyle(str(qml_path))
    if not ok:
        logger.warning("Failed to apply style %s to layer %s: %s", qml_name, layer.name(), message)
        return False

    if isinstance(layer, QgsRasterLayer) and style_key in ("cva_intensity", "baseline_intensity"):
        _rescale_continuous_raster(layer)

    layer.triggerRepaint()
    return True


def _rescale_continuous_raster(layer: QgsRasterLayer) -> None:
    """Recompute the color-ramp min/max from this layer's actual 2nd/98th percentile."""
    try:
        provider = layer.dataProvider()
        stats = provider.bandStatistics(1, QgsRasterBandStats.All)
        renderer = layer.renderer()
        shader = renderer.shader() if renderer is not None else None
        if shader is None:
            return
        color_ramp_shader = shader.rasterShaderFunction()
        vmin = max(stats.minimumValue, 0.0)
        vmax = stats.mean + 2 * stats.stdDev if stats.stdDev > 0 else stats.maximumValue
        vmax = min(vmax, stats.maximumValue) if stats.maximumValue > vmin else vmin + 1.0
        color_ramp_shader.setMinimumValue(vmin)
        color_ramp_shader.setMaximumValue(vmax)
        renderer.setClassificationMin(vmin)
        renderer.setClassificationMax(vmax)
        logger.info(
            "Rescaled continuous raster style for %s to [%.4f, %.4f]", layer.name(), vmin, vmax
        )
    except Exception:  # noqa: BLE001 - styling is best-effort, never fatal to the run
        logger.exception(
            "Could not rescale raster style for %s; keeping placeholder range.", layer.name()
        )
