# QGIS Plugin Development Guide

## Structure

```
qgis_plugin/solafune_change_analyzer/
├── __init__.py            classFactory only, imports nothing heavy
├── metadata.txt
├── plugin.py               lifecycle: initGui / run / unload
├── dock_widget.py           UI only (6 tabs), no analysis logic
├── controller.py           state machine, wires dock <-> execution modes
├── task.py                  embedded QgsTask wrapper
├── external_runner.py       QProcess wrapper (external interpreter mode)
├── core_bridge.py           resolves installed-or-vendored solafune_change
├── dependency_check.py      per-package readiness (current + external interpreter)
├── layer_loader.py          main-thread-only: adds result layers to the project
├── style_manager.py         applies bundled QML + rescales continuous rasters
├── settings.py              QSettings + YAML import/export
├── validation_model.py      dependency-free UI mirror of ValidationReport
├── result_model.py          dependency-free UI mirror of PipelineResult
├── processing/
│   ├── provider.py          "Solafune Geospatial Analytics" provider
│   └── change_algorithm.py  "Sentinel-2 Change Analysis" algorithm
├── styles/*.qml              bundled default styles (see styles/README.md)
├── icons/solafune_change.svg
├── help/index.html
└── vendor/                   EMPTY in source control; populated at build time
```

## Local installation (development)

QGIS looks for plugins in its profile's `python/plugins/` directory. On
Windows that is typically:
`%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`

Two options:

1. **Symlink** (recommended — edits are picked up on next plugin reload):
   ```powershell
   New-Item -ItemType SymbolicLink `
     -Path "$env:APPDATA\QGIS\QGIS3\profiles\default\python\plugins\solafune_change_analyzer" `
     -Target "C:\path\to\solafune-sentinel2-change\qgis_plugin\solafune_change_analyzer"
   ```
2. **Copy** the `qgis_plugin/solafune_change_analyzer/` folder into that
   directory (re-copy after each change).

Then in QGIS: **Plugins > Manage and Install Plugins > Installed**, enable
"Solafune Change Analyzer". The [Plugin Reloader](https://plugins.qgis.org/plugins/plugin_reloader/)
plugin speeds up the edit/reload loop.

## Resource "build"

No compiled Qt resources (`.qrc`/`resources.py`) are used — the icon is
loaded from `icons/solafune_change.svg` by file path at runtime, which is
simpler and avoids a `pyrcc5`/`pyrcc6` build step. `make plugin-resources` is
a no-op that documents this choice.

## Running the QGIS-independent tests

```bash
python -m pytest tests/test_qgis_plugin_structure.py -v
```

These check: the core engine never imports `qgis`/`PyQt`, the plugin never
imports `PyQt5`/`PyQt6` directly (must go through `qgis.PyQt`), `metadata.txt`
has all required fields, every plugin `.py` file compiles, and there are no
`pass`-only placeholder handlers.

## Running real-QGIS checks (requires a QGIS install)

If QGIS is installed, use its bundled interpreter (Windows/OSGeo4W example):

```powershell
$env:OSGEO4W_ROOT = "C:\Program Files\QGIS 3.44.12"
& "C:\Program Files\QGIS 3.44.12\bin\python-qgis-ltr.bat" your_script.py
```

A minimal smoke test (classFactory -> initGui -> run -> unload, using
`qgis.testing.mocked.get_iface()`) is described in
`docs/QGIS_PLUGIN_TEST_CHECKLIST.md`, along with the exact output recorded
when it was run against this repository's plugin on QGIS 3.44.12.

## Building the release ZIP

```bash
python scripts/build_qgis_plugin.py
python scripts/validate_qgis_plugin.py outputs/qgis/solafune_change_analyzer.zip
```

or `make plugin` (runs the QGIS-independent tests, then build, then validate).

## Version bump / release checklist

1. Bump `version=` in `metadata.txt`.
2. Update `changelog=` in `metadata.txt`.
3. Bump `__version__` in `src/solafune_change/__init__.py` if the core changed.
4. `make plugin` (test -> build -> validate).
5. Manually smoke-test the ZIP by installing it in a QGIS test profile
   (see `docs/QGIS_PLUGIN_TEST_CHECKLIST.md`).
6. Commit `outputs/qgis/*.zip` only if you intend it as a tracked release
   artifact — by default it is `.gitignore`d as a build output; attach it to
   a GitHub Release instead.
