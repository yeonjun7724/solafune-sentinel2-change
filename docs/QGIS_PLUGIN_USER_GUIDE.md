# QGIS Plugin User Guide — Solafune Change Analyzer

## 1. Install

1. Download/locate `solafune_change_analyzer.zip` (build it yourself with
   `python scripts/build_qgis_plugin.py` if you don't have a prebuilt one —
   it is written to `outputs/qgis/solafune_change_analyzer.zip`).
2. In QGIS: **Plugins > Manage and Install Plugins > Install from ZIP**.
3. Browse to the ZIP, click **Install Plugin**.
4. Enable it under **Installed** if it isn't already.
5. Open it: toolbar icon, or **Plugins > Solafune Change Analyzer**.

Supported QGIS version: 3.28+ (developed and manually tested against 3.44.12).

## 2. Prepare a Python environment for full functionality

Most QGIS installs (especially Windows/OSGeo4W ones) do **not** ship
`rasterio`, `scikit-image`, `scikit-learn`, `libpysal`, `esda`, or `folium`.
The plugin detects this (**Dependencies** tab) and can run the analysis in a
separate Python environment instead of QGIS's own:

```bash
cd path\to\solafune-sentinel2-change
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .
```

Then in the plugin's **Dependencies** tab, browse "External interpreter" to
`.venv\Scripts\python.exe` and click **Check dependencies** — every row
should show "Ready". Leave "Execution environment" on **Automatic**; the
plugin will pick embedded QGIS Python if it's fully capable, else the
external interpreter you configured.

## 3. First run

1. **Inputs tab**: select the before/after Sentinel-2 folders (each must
   directly contain B02/B03/B04 as GeoTIFF or JP2), the AOI file, and an
   output directory. Click **Validate Inputs**. Fix any red "Invalid" issues.
2. **Change Detection tab**: pick a method (default: "Run both" — baseline +
   Robust RGB CVA), normalization, threshold method, morphology and minimum
   area settings.
3. **Spatial Analysis tab**: leave "Enable spatial statistics" on for
   Moran's I / Gi* hotspot analysis. Optionally enable the experimental
   spatial ML section (clearly marked — see the warning banner there).
4. **Outputs tab**: choose what gets written/loaded (defaults are sensible).
5. **Run & Results tab**: click **Run Analysis**. Progress, stage, elapsed
   time and a live log are shown; **Cancel** stops the run cleanly.
6. When it finishes, layers load automatically into a
   "Solafune Change Analysis — `<run id>`" group, and the summary table plus
   buttons (**Open Report**, **Open Interactive Map**, **Open Output
   Folder**, ...) become active.

## 4. Reading the results

- **CVA Intensity / Baseline Intensity**: continuous change-magnitude rasters.
- **CVA Binary / Baseline Binary**: thresholded change/no-change rasters.
- **Change Features**: polygons with area, mean change, `confidence`
  (heuristic 0-1 score — **not** a calibrated probability), Gi*/LISA
  attributes, and (if ML was enabled) an anomaly score/cluster id.
- **LISA Clusters** / **Gi* Hotspots**: the same analysis grid, styled by
  Local Moran's I cluster type / Getis-Ord Gi* significance class.
- **Spatial Anomalies (experimental)**: styled by `ml_anomaly_quantile`, only
  present if experimental ML was enabled — treat as an exploratory ranking.

Use the toolbar's "Show Before" / "Show After" / "Toggle Before/After"
actions (change-overlay opacity slider) to visually compare the two dates.

## 5. GeoPackage database

`outputs/database/change_analysis.gpkg` is a plain SQLite file with four
tables: `change_features`, `spatial_grid` (both with real geometry columns),
`run_metadata`, `quality_checks`. Open it directly in QGIS's DB Manager, or
see `docs/example_queries.sql` for ready-to-run SQL.

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "Embedded QGIS Python (missing dependencies)" | Expected on most Windows installs — set up an External interpreter (section 2). |
| Validate Inputs shows "B04 not found" | Folder must directly contain `B02`/`B03`/`B04` files (GeoTIFF/JP2), not a nested subfolder. |
| Run fails immediately with a dependency error | Check the **Dependencies** tab; the chosen execution mode is missing a package. |
| Nothing loads after a successful run | "Load results into current QGIS project" (Outputs tab) must be checked; also check the log panel for per-layer warnings. |
| External run never finishes | Confirm the interpreter path is a real `python.exe`/`python3` binary, not a `.bat`/shortcut, and that `pip install -e .` succeeded in that environment. |
| Need full detail on an error | QGIS **Log Messages Panel > Solafune Change Analyzer** tab has the full log; the run also writes `outputs/quality_report.json` and `outputs/run_manifest.json`. |

## 7. Uninstall

**Plugins > Manage and Install Plugins > Installed**, select "Solafune Change
Analyzer", click **Uninstall Plugin**. This does not remove any previously
generated output files.

## 8. Processing Toolbox

The same engine is also available as **Solafune Geospatial Analytics >
Sentinel-2 Change Analysis** in the Processing Toolbox — useful for
batch/model-builder workflows. It exposes the same parameters as the dock
widget's core options (method, normalization, threshold, spatial statistics,
experimental ML) and requires the same dependencies as External mode.
