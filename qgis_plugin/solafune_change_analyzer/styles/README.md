# Bundled QML styles

Generated once at development time via `solafune_change.visualization.generate_all_styles(...)`
(see `scripts/build_qgis_plugin.py`), **not** regenerated per analysis run.

- `change_binary.qml`, `change_polygons.qml`, `lisa_clusters.qml`, `gi_hotspots.qml`,
  `ml_anomalies.qml` are styled on fields with a fixed, run-independent domain
  (0/1, fixed category labels, or `confidence`/`ml_anomaly_quantile`, which are
  always in `[0, 1]` by construction) — these are correct for every run as-is.
- `cva_intensity.qml` and `baseline_intensity.qml` are continuous rasters whose
  actual value range depends on the run's data. They ship with a placeholder
  range (CVA: 0-10, baseline: 0-1) and `style_manager.apply_style()`
  automatically rescales the color-ramp shader's min/max to that layer's real
  2nd/98th-percentile-ish range (mean +/- 2 stddev, clipped to the data max)
  immediately after loading the QML.
