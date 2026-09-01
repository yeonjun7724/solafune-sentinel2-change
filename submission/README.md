# Submission Bundle Guide

This single folder contains the **QGIS plugin edition**, the **script (CLI) edition**, a copy of the **raw input data**, the **actual output artifacts** from a real run, and a detailed usage guide.

**Start here: `Usage_Guide.pdf`** — far more detailed than the summary below. It covers QGIS plugin installation and dependency setup (including how to do it without a separate venv, field-verified), every field on every tab, all pipeline stages, troubleshooting, the full CLI/config reference for the script edition, actual analysis results, algorithm rationale, the database schema, 8 bugs found and fixed during development, the test record, and known limitations.

```
submission/
├── README.md                              <- this file (summary)
├── Usage_Guide.pdf                        <- detailed usage guide (English)
├── solafune_change_analyzer.zip           <- (1) QGIS plugin install package
├── solafune_change_analyzer.zip.sha256    <- checksum for (1)
├── solafune-sentinel2-change-source.zip   <- (2) script (CLI) edition = the full source repository as one archive
├── data/                                  <- (3) raw input data (standalone copy, for inspection)
└── results/                               <- (4) actual output artifacts from a real run (no re-run needed)
    ├── outputs/                           <- GeoPackage database, static figure, interactive map, spatial statistics, report.md, etc.
    └── data_processed/                    <- stacked GeoTIFF, baseline/CVA intensity & binary rasters
```

Original GitHub repository (full commit history): https://github.com/yeonjun7724/solafune-sentinel2-change

---

## (1) `solafune_change_analyzer.zip` — QGIS plugin edition

Runs **inside QGIS**, driven from a GUI. This single zip file is all you need (the analysis engine is vendored inside it, so no other files are required).

### Install
1. Launch QGIS (3.28 or later; field-tested on 3.44.12)
2. Menu: **Plugins → Manage and Install Plugins → Install from ZIP**
3. Select `solafune_change_analyzer.zip` → **Install Plugin**
4. In the **Installed** tab, confirm "Solafune Change Analyzer" is checked (enabled)
5. Launch it from the toolbar icon or **Plugins → Solafune Change Analyzer**

### Dependency setup — no separate `.venv` required
Most Windows/OSGeo4W QGIS builds don't ship `rasterio` / `scikit-learn` / `libpysal` / `esda`, etc. by default. **You don't need to create a separate folder** — installing once into QGIS's own Python is enough (field-verified: the full pipeline succeeds end to end in embedded mode):
```powershell
cd "C:\Program Files\QGIS 3.44.12\bin"
python-qgis-ltr.bat -m pip install --user rasterio geopandas shapely pyproj scipy scikit-image PyYAML libpysal esda scikit-learn matplotlib folium
```
For a more isolated setup (a separate `.venv` + External interpreter), see Section A.4 of `Usage_Guide.pdf`.

### Usage (Dock Widget)
1. **Inputs tab**: select the Before/After Sentinel-2 folders, AOI file, and output folder → click **Validate Inputs** (use **Clear Inputs** to reset if you want to pick different paths)
2. **Change Detection tab**: choose the method (baseline/CVA/both), threshold, morphology, etc.
3. **Spatial Analysis tab**: configure spatial statistics (Moran's I / Gi*) and the optional experimental ML step
4. **Dependencies tab**: once the install above is done, every item should show "Ready"
5. **Run & Results tab**: click **Run Analysis** → watch progress/log → on completion, result layers are auto-loaded into the QGIS project

### Checksum verification (optional)
```powershell
certutil -hashfile solafune_change_analyzer.zip SHA256
# compare against the contents of solafune_change_analyzer.zip.sha256
```

### Further documentation
See the full `Usage_Guide.pdf`, or unzip `solafune-sentinel2-change-source.zip` and read `docs/QGIS_PLUGIN_USER_GUIDE.md` (usage), `docs/QGIS_PLUGIN_DEVELOPMENT.md` (development), `docs/QGIS_PLUGIN_ARCHITECTURE.md` (architecture), and `docs/QGIS_PLUGIN_TEST_CHECKLIST.md` (verification record).

---

## (2) `solafune-sentinel2-change-source.zip` — script (CLI) edition (= the entire repository as one archive)

Runs **from a terminal**, no QGIS required. Built with `git archive HEAD`, so its contents are a byte-for-byte snapshot of the exact commit pushed to GitHub (wrapped in a `solafune-sentinel2-change-master/` folder, the same layout GitHub's "Code → Download ZIP" produces) — full source code, tests, docs, and config, ready to run right after unzipping since it already includes the raw input data (`inputs/`).

One deliberate difference from a literal "Download ZIP": the `submission/` and `yeonjun/` packaging folders (this bundle, and the author's personal Korean working notes) are excluded from the archive. Including them would make this zip contain a copy of itself, growing without bound every time it's regenerated — so this file is best read as "the entire codebase," not literally every byte of the GitHub repository.

### Install
```bash
unzip solafune-sentinel2-change-source.zip
cd solafune-sentinel2-change-master

python -m venv .venv
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\pip install -e .
```
(On macOS/Linux, use `source .venv/bin/activate` then `pip ...` instead of `.venv\Scripts\...`.)

### Run — one command
```bash
solafune-change all --config config/default.yaml
```
The full pipeline finishes in about 30 seconds. Results are written to `outputs/` (database, figures, map, statistics, summary JSON) and `data/processed/` (intermediate GeoTIFFs).

### Individual commands / options / the full config.yaml field reference
See PART B (B.4–B.10) of `Usage_Guide.pdf` for complete tables.

### Tests
```bash
python -m pytest tests/ -v      # 65 tests
```

---

## (3) `data/` — raw input data (for inspection)

`aoi.geojson`, `example_change_detection.py`, `instructions.pdf`, `data/sentinel2_20230812/` and `data/sentinel2_20230902/` (B02/B03/B04 GeoTIFFs). Both (1) and (2) already include this data, so it isn't strictly required to run either edition — this is a separate standalone copy for opening the raw imagery directly without unzipping anything.

## (4) `results/` — actual output artifacts (no re-run needed)

The real, final output of an actual pipeline run — open these directly without executing any code.

- `results/outputs/database/change_analysis.gpkg` — GeoPackage (opens directly in QGIS or any DB Browser)
- `results/outputs/figures/change_comparison.png` — baseline vs. CVA vs. Gi* comparison figure
- `results/outputs/maps/interactive_map.html` — interactive map (double-click to open in a browser, works fully offline)
- `results/outputs/statistics/`, `results/outputs/report.md`, `results/outputs/summary.json`, etc.
- `results/data_processed/` — stacked GeoTIFF, baseline/CVA intensity & binary rasters

(Item (2), the source zip, does not include these result files to keep its size down — open this folder instead if you just want to see the outcome without re-running anything.)

---

## Summary table

| How to run | Files needed | Command / method | QGIS required? |
|---|---|---|---|
| GUI (plugin) | `solafune_change_analyzer.zip` | Plugins → Install from ZIP → click Run in the Dock Widget | Yes (QGIS 3.28+) |
| CLI (script) | `solafune-sentinel2-change-source.zip` | Unzip → `pip install -e .` → `solafune-change all --config config/default.yaml` | No |
| View results only | `results/` | Open directly (QGIS, browser, etc.) | No |
| View data only | `data/` | Open directly (QGIS, GDAL, etc.) | No |

Both execution modes share the **same analysis engine** (the `solafune_change` core package), so results are identical — the analysis logic is never duplicated between them.
