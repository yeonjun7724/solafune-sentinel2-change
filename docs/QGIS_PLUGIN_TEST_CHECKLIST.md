# QGIS Plugin Test Checklist

## What was actually run, and where

QGIS 3.44.12 (OSGeo4W build) **was** installed on the development machine at
`C:\Program Files\QGIS 3.44.12`, so several checks below were run for real
against real QGIS Python bindings (`bin\python-qgis-ltr.bat`), not just
statically analyzed. Others require a full GUI session (opening dialogs,
clicking buttons) and are left as a manual checklist for whoever installs the
plugin in an interactive QGIS session.

### Automated, QGIS-independent (run as part of `pytest`)

```
tests/test_qgis_plugin_structure.py
```
- [x] Core engine (`src/solafune_change`) never imports `qgis`/`PyQt`
- [x] Plugin files never import `PyQt5`/`PyQt6` directly (only `qgis.PyQt`)
- [x] `metadata.txt` has all required fields
- [x] `__init__.py` defines `classFactory`
- [x] Every plugin `.py` file compiles
- [x] No `pass`-only placeholder handlers
- [x] Built ZIP has the correct single top-level folder + vendored core

### Automated, real QGIS 3.44.12 (run manually via `python-qgis-ltr.bat`, recorded here)

Command used:
```powershell
$env:OSGEO4W_ROOT = "C:\Program Files\QGIS 3.44.12"
& "C:\Program Files\QGIS 3.44.12\bin\python-qgis-ltr.bat" qgis_plugin_smoke.py
```

Recorded result (abbreviated):
```
QGIS initialized: python  (Qgis.QGIS_VERSION = 3.44.12-Solothurn)
Using qgis.testing.mocked.get_iface()
classFactory OK: <solafune_change_analyzer.plugin.SolafuneChangeAnalyzerPlugin ...>
initGui OK
run() OK, dock created: <solafune_change_analyzer.dock_widget.SolafuneChangeDockWidget ...>
dependency statuses (embedded QGIS python):
  numpy True   rasterio False   geopandas True   shapely True   pyproj True
  scipy True   scikit-image False   PyYAML True   libpysal False   esda False
  scikit-learn False   hdbscan False   matplotlib True   folium False
refresh_dependency_panel OK
unload OK
second init/run/unload cycle OK   <- no duplicate action/dock registration
ALL SMOKE TESTS PASSED
```
This is the real basis for the "embedded mode unavailable on a stock
Windows/OSGeo4W install, external mode required for full functionality"
statement made throughout this repository's docs — it is a measured fact
about this machine's QGIS install, not an assumption.

- [x] `classFactory(iface)` succeeds
- [x] `initGui()` succeeds (toolbar action + menu entry + Processing provider registration)
- [x] `run()` creates and shows the dock widget
- [x] Dependency panel populates from a live `check_current_interpreter()` call
- [x] `unload()` succeeds (removes action/menu/dock/provider)
- [x] A second `initGui/run/unload` cycle does not error or duplicate anything

Processing provider/algorithm check (same launcher, separate script):
```
Provider added. id=solafune_geospatial_analytics name=Solafune Geospatial Analytics
Algorithms: ['sentinel2_change_analysis']
createInstance OK
displayName: Sentinel-2 Change Analysis
group: Change Detection
param count: 15  (all QgsProcessingParameter* objects created successfully)
Provider removed OK
```
- [x] `SolafuneGeospatialProvider` registers and lists the algorithm
- [x] `Sentinel2ChangeAnalysisAlgorithm.initAlgorithm()` builds all 15 parameters without error
- [x] Provider unregisters cleanly

### Real-world bug found and fixed via actual installed-plugin use

A user actually installed the plugin from ZIP into a real QGIS 3.44.12
profile (`%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\solafune_change_analyzer\`)
and clicked **Validate Inputs**. `on_validate()` unconditionally attempted
the embedded import path and only caught `CoreImportError`; QGIS's embedded
interpreter has no `rasterio` (confirmed above), so `from solafune_change.pipeline
import validate_request` raised a plain `ModuleNotFoundError` several frames
deep (via `cva.py` -> `preprocessing.py` -> `import rasterio`), which was
**not** caught, producing an unhandled traceback in the QGIS Log Messages
panel instead of a friendly message.

Fix (`controller.py`): `on_validate()` now checks `dependency_check.embedded_mode_available()`
*before* attempting anything, exactly like `on_run()`'s `_resolve_execution_mode()`
already did. If embedded deps are missing it now either (a) runs validation
through the configured External interpreter via a bounded, synchronous
`python -m solafune_change validate --config <temp.yaml> --json` subprocess
call (new `--json` flag added to the CLI's `validate` command), or (b) shows
a clear, actionable warning instead of crashing if no external interpreter
is configured either. `_resolve_execution_mode()`'s "auto" branch was also
hardened to check that an external interpreter is actually set before
falling back to external mode.

Re-verified for real against QGIS 3.44.12 (`qgis.testing.mocked.get_iface()`,
`QMessageBox.warning` stubbed to avoid a headless modal-dialog hang):

```
=== Scenario 1: no external interpreter configured, embedded deps missing ===
  [QMessageBox.warning would show] Dependencies missing: ...set an External interpreter...
state after on_validate: IDLE          <- no crash (previously: unhandled traceback)

=== Scenario 2: external interpreter configured (project .venv) ===
state after on_validate: READY
validation_status_label: Valid
band_table rows: 6                     <- real band metadata from the external process
```

- [x] `on_validate()` no longer crashes when embedded dependencies are missing
- [x] `on_validate()` successfully validates via a configured External interpreter
- [x] `solafune-change validate --config ... --json` covered by `tests/test_cli.py`

### Real-world bug found and fixed: `processed_dir` path resolution

During real external-mode runs, results were observed landing under an
unrelated, third-party-hijacked TEMP directory instead of next to the chosen
output folder. Root cause: `config.py`'s `load_config()` always defaulted
`processed_dir` to a relative path resolved against the temp config file's
own parent-of-parent directory — meaningless for the short-lived temp YAML
the plugin writes for an external run. Reproduced directly on this machine
(`tempfile.mkdtemp()` lands under the same hijacked path as the reported
error). Fixed in `config.py` (`processed_dir` now `Path | None`, omitted
from `request_to_yaml_dict()` when unset) and `settings.py` (`export_yaml()`
now always computes and writes an explicit absolute `processed_dir` next to
`output_dir`). Covered by two new regression tests:

- [x] `test_processed_dir_defaults_to_none_when_unset_in_yaml` / `test_processed_dir_respected_when_explicitly_set` (`tests/test_config.py`)
- [x] `test_processed_dir_none_falls_back_to_sibling_of_output_dir` (`tests/test_pipeline_integration.py`)

### Real QGIS 3.44.12: Clear Inputs button

Driven headlessly via `qgis.testing.mocked.get_iface()`: populated all four
Inputs-tab path fields, the run label, and the validation status/band table
with stale values, called `controller.persist_settings()` to simulate a
previous session, then called `on_clear_inputs()`.

```
Before clear: before_edit = "C:\some\stale\before", persisted before_folder = "C:\some\stale\before"
After clear:  before_edit = "", after_edit = "", aoi_edit = "", output_dir_edit = "",
              run_label_edit = "run", band_table rows = 0, controller.state = "IDLE",
              persisted before_folder = ""
CLEAR INPUTS TEST PASSED
```

- [x] Clears all four path fields, run label (reset to default "run"), and the validation display
- [x] Also clears the values persisted from the previous session (not just the widgets)
- [x] Does not touch settings on other tabs (Change Detection, Spatial Analysis, etc.)

### Real QGIS 3.44.12: dependency install without a separate `.venv`

`Usage_Guide.pdf` documents two dependency-setup paths (a separate `.venv` +
External interpreter, or installing straight into QGIS's own Python via
`pip install --user`). The second path was field-tested, not just described:

```powershell
cd "C:\Program Files\QGIS 3.44.12\bin"
python-qgis-ltr.bat -m pip install --user rasterio geopandas shapely pyproj scipy scikit-image PyYAML libpysal esda scikit-learn matplotlib folium
```

After this, every Dependencies-tab row showed "Ready", and a full pipeline
run (spatial statistics + experimental ML enabled) completed **entirely in
Embedded mode** — rasterio coexisted with QGIS's own GDAL in the same
process without a CRS-lookup or import conflict:

```
514 change features, Global Moran's I = 0.804  (a sane value, run in embedded mode)
```

- [x] All required packages report "Ready" after the `--user` install
- [x] `Validate Inputs` succeeds in Embedded mode
- [x] `Run Analysis` (with spatial statistics and experimental ML) completes in Embedded mode
- [x] Verified for this specific QGIS/package-version combination only — a different combination could in theory still hit a GDAL conflict, which is why the isolated `.venv` option remains documented as the safer alternative

### Manual checklist (needs an interactive QGIS session — not run by this assessment; check off as you go)

- [ ] Fresh QGIS profile, install plugin via **Install from ZIP**
- [ ] Toolbar icon visible and clickable
- [ ] Dock opens on click, docks to the right by default
- [ ] Browse dialogs work for all four path fields
- [ ] **Validate Inputs** against the real `inputs/` folders shows "Valid" with a populated band metadata table
- [ ] Deliberately break an input (delete a band file) and confirm Validate Inputs reports a clear, specific error
- [ ] Set External interpreter to the project `.venv`, **Check dependencies** shows all "Ready"
- [ ] **Run Analysis** with default settings completes, progress bar reaches 100%, log shows every stage
- [ ] **Cancel** mid-run stops promptly and UI returns to an actionable state (no crash, no zombie process)
- [ ] Layer group appears with AOI/RGB/intensity/binary/polygons/grid layers, styled per `styles/*.qml`
- [ ] Attribute table / feature selection on Change Features works via standard QGIS tools
- [ ] Processing Toolbox > Solafune Geospatial Analytics > Sentinel-2 Change Analysis runs successfully with the same inputs
- [ ] Save and reopen the QGIS project; result layers reload correctly
- [ ] Disable/re-enable the plugin from Plugin Manager without restarting QGIS
- [ ] Uninstall cleanly removes the toolbar icon and menu entry

## Known gaps

- The manual interactive-session checklist above was not executed as part of
  this assessment (no way to drive an interactive GUI session from this
  environment); everything above the manual section **was** executed for
  real against QGIS 3.44.12 and is not merely a static claim.
- HDBSCAN was not tested (not installed in either environment); the plugin
  correctly reports it as unavailable and does not offer it as a clustering option.
