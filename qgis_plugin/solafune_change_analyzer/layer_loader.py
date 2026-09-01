"""Loads a completed run's outputs into the QGIS layer tree, main-thread only.

Called exclusively from the main-thread completion handler of either
execution mode (never from a worker thread / QgsTask.run()) -- QgsProject and
the layer tree may only be touched from the main thread.
"""

from __future__ import annotations

import logging
from pathlib import Path

from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

from . import style_manager
from .result_model import UiResult

logger = logging.getLogger(__name__)


def load_results(
    result: UiResult, aoi_path: str, load_grid_layers: bool = True
) -> tuple[list[str], list[str]]:
    """Load AOI/before/after/change/statistics/ML layers into a dedicated group.

    Returns ``(loaded_layer_names, warnings)``. Missing/invalid layers are
    skipped with a warning rather than aborting the whole load.
    """
    warnings: list[str] = []
    loaded: list[str] = []

    project = QgsProject.instance()
    root = project.layerTreeRoot()
    group_name = f"Solafune Change Analysis — {result.run_id}"
    existing = root.findGroup(group_name)
    if existing is not None:
        root.removeChildNode(existing)
    top_group = root.insertGroup(0, group_name)

    inputs_group = top_group.addGroup("Inputs")
    change_group = top_group.addGroup("Change Detection")
    stats_group = top_group.addGroup("Spatial Statistics")
    ml_group = top_group.addGroup("Experimental ML")

    def _add_raster(
        path_key: str, display_name: str, group, style_key: str | None = None, visible: bool = True
    ) -> None:
        path = result.get_path(path_key)
        if path is None or not path.exists():
            return
        layer = QgsRasterLayer(str(path), display_name)
        if not layer.isValid():
            warnings.append(f"Layer '{display_name}' failed to load (invalid raster): {path}")
            return
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        layer.setCustomProperty("solafune_change/run_id", result.run_id)
        if style_key:
            style_manager.apply_style(layer, style_key)
        layer.setItemVisibilityChecked(visible)
        loaded.append(display_name)

    def _add_vector(
        path: str | None,
        layer_name: str,
        display_name: str,
        group,
        style_key: str | None = None,
        visible: bool = True,
    ) -> None:
        if not path or not Path(path).exists():
            return
        layer = QgsVectorLayer(f"{path}|layername={layer_name}", display_name, "ogr")
        if not layer.isValid():
            warnings.append(
                f"Layer '{display_name}' failed to load (invalid vector source): {path}"
            )
            return
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        layer.setCustomProperty("solafune_change/run_id", result.run_id)
        if style_key:
            style_manager.apply_style(layer, style_key)
        layer.setItemVisibilityChecked(visible)
        loaded.append(display_name)

    # --- Inputs ---
    if aoi_path and Path(aoi_path).exists():
        aoi_layer = QgsVectorLayer(aoi_path, "AOI", "ogr")
        if aoi_layer.isValid():
            project.addMapLayer(aoi_layer, False)
            inputs_group.addLayer(aoi_layer)
            loaded.append("AOI")
        else:
            warnings.append(f"AOI layer failed to load: {aoi_path}")

    _add_raster("before_stack", f"Before RGB ({result.before_date})", inputs_group, visible=True)
    _add_raster("after_stack", f"After RGB ({result.after_date})", inputs_group, visible=False)

    # --- Change detection ---
    _add_raster(
        "baseline_intensity",
        "Baseline Intensity",
        change_group,
        style_key="baseline_intensity",
        visible=False,
    )
    _add_raster(
        "baseline_binary", "Baseline Binary", change_group, style_key="binary", visible=False
    )
    _add_raster(
        "cva_intensity", "CVA Intensity", change_group, style_key="cva_intensity", visible=True
    )
    _add_raster("cva_binary", "CVA Binary", change_group, style_key="binary", visible=False)

    db_path = result.paths.get("database")
    if db_path and Path(db_path).exists():
        _add_vector(
            db_path,
            "change_features",
            "Change Features",
            change_group,
            style_key="change_polygons",
            visible=True,
        )

    # --- Spatial statistics ---
    if load_grid_layers:
        grid_path = result.paths.get("spatial_grid_gpkg") or db_path
        if grid_path and Path(grid_path).exists():
            _add_vector(grid_path, "spatial_grid", "Analysis Grid", stats_group, visible=False)
            _add_vector(
                grid_path,
                "spatial_grid",
                "LISA Clusters",
                stats_group,
                style_key="lisa_clusters",
                visible=True,
            )
            _add_vector(
                grid_path,
                "spatial_grid",
                "Gi* Hotspots",
                stats_group,
                style_key="gi_hotspots",
                visible=True,
            )

            # --- Experimental ML (reuses the same grid source, styled differently) ---
            _add_vector(
                grid_path,
                "spatial_grid",
                "Spatial Anomalies (experimental)",
                ml_group,
                style_key="ml_anomalies",
                visible=False,
            )

    if not stats_group.children():
        top_group.removeChildNode(stats_group)
    if not ml_group.children():
        top_group.removeChildNode(ml_group)

    logger.info(
        "Loaded %d layer(s) for run %s (%d warning(s))", len(loaded), result.run_id, len(warnings)
    )
    return loaded, warnings
