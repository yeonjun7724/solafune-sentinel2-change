"""Wires the dock widget's signals to validation/execution/layer-loading.

Owns the explicit state machine (IDLE/VALIDATING/READY/RUNNING/CANCELLING/
COMPLETED/FAILED/CANCELLED) described in the plugin spec, so state transition
logic lives in one place instead of being scattered across UI callbacks.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import webbrowser
from pathlib import Path

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsProject
from qgis.PyQt.QtCore import QTimer, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QApplication, QMessageBox

from . import dependency_check, settings
from .core_bridge import CoreImportError, import_core
from .dock_widget import SolafuneChangeDockWidget
from .external_runner import ExternalAnalysisRunner
from .result_model import UiResult, from_core_result, from_manifest_files
from .task import EmbeddedAnalysisTask
from .validation_model import UiValidationIssue, UiValidationReport, from_core_report

logger = logging.getLogger(__name__)

VALID_STATES = (
    "IDLE",
    "VALIDATING",
    "READY",
    "RUNNING",
    "CANCELLING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
)


class Controller:
    def __init__(self, iface, dock: SolafuneChangeDockWidget) -> None:
        self.iface = iface
        self.dock = dock
        self.state = "IDLE"
        self._task = None
        self._external_runner = None
        self._result: UiResult | None = None
        self._start_time = 0.0
        self._elapsed_timer = QTimer()
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._temp_config_path: str | None = None

        self._load_settings_into_dock()
        self._connect_signals()
        self._refresh_dependency_panel()

    # ------------------------------------------------------------------ wiring
    def _connect_signals(self) -> None:
        d = self.dock
        d.validateRequested.connect(self.on_validate)
        d.clearInputsRequested.connect(self.on_clear_inputs)
        d.runRequested.connect(self.on_run)
        d.cancelRequested.connect(self.on_cancel)
        d.restoreDefaultsRequested.connect(self.on_restore_defaults)
        d.importYamlRequested.connect(self.on_import_yaml)
        d.exportYamlRequested.connect(self.on_export_yaml)
        d.openOutputFolderRequested.connect(self.on_open_output_folder)
        d.openReportRequested.connect(self.on_open_report)
        d.openMapRequested.connect(self.on_open_map)
        d.addResultsToMapRequested.connect(self.on_add_results_to_map)
        d.copySummaryRequested.connect(self.on_copy_summary)
        d.checkExternalInterpreterRequested.connect(self.on_check_external_interpreter)

    def _set_state(self, state: str) -> None:
        assert state in VALID_STATES, f"invalid state: {state}"
        self.state = state
        self.dock.set_state(state)

    # ------------------------------------------------------------------ settings
    def _load_settings_into_dock(self) -> None:
        values = settings.load_all()
        self.dock.set_paths(values)
        interp = values.get("execution/external_python_path", "")
        if interp:
            self.dock.external_interpreter_edit.setText(interp)

    def _current_settings_dict(self) -> dict:
        d = self.dock
        values = dict(settings.DEFAULTS)
        paths = d.get_paths()
        values.update(
            {
                "paths/before_folder": paths["before_folder"],
                "paths/after_folder": paths["after_folder"],
                "paths/aoi": paths["aoi"],
                "paths/output_dir": paths["output_dir"],
                "run/label": paths["run_label"],
            }
        )
        cd = d.get_change_detection_options()
        values.update({f"change/{k}": v for k, v in cd.items() if v is not None})
        sp = d.get_spatial_options()
        values.update(
            {
                f"stats/{k.replace('spatial_', '').replace('statistics_', '')}": v
                for k, v in sp.items()
                if k.startswith(
                    (
                        "spatial_statistics",
                        "spatial_grid",
                        "spatial_weights",
                        "knn",
                        "row_standardization",
                        "permutations",
                        "alpha",
                        "fdr",
                    )
                )
            }
        )
        values["stats/enabled"] = sp["spatial_statistics_enabled"]
        values["stats/grid_size_m"] = sp["spatial_grid_size_m"]
        values["stats/weights"] = sp["spatial_weights"]
        values["ml/enabled"] = sp["spatial_ml_enabled"]
        values["ml/model"] = sp["ml_model"]
        values["ml/contamination"] = sp["ml_contamination"]
        values["ml/dbscan_eps"] = sp["dbscan_eps"]
        values["ml/dbscan_min_samples"] = sp["dbscan_min_samples"]
        out = d.get_output_options()
        values.update({f"output/{k}": v for k, v in out.items()})
        values["execution/external_python_path"] = d.external_interpreter_edit.text()
        values["execution/mode"] = d.get_execution_mode()
        return values

    def on_restore_defaults(self) -> None:
        values = settings.restore_defaults()
        self.dock.set_paths(values)

    def on_import_yaml(self, path: str) -> None:
        try:
            values = settings.import_yaml(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self.dock, "Import failed", f"Could not import configuration: {exc}"
            )
            return
        self.dock.set_paths(values)
        settings.save_all(values)

    def on_export_yaml(self, path: str) -> None:
        try:
            settings.export_yaml(self._current_settings_dict(), path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self.dock, "Export failed", f"Could not export configuration: {exc}"
            )

    def persist_settings(self) -> None:
        settings.save_all(self._current_settings_dict())

    # ------------------------------------------------------------------ dependency panel
    def _refresh_dependency_panel(self) -> None:
        statuses = dependency_check.check_current_interpreter()
        self.dock.set_dependency_table(statuses)
        embedded_ok = dependency_check.embedded_mode_available(statuses)
        self.dock.set_execution_mode_label(
            "Embedded QGIS Python (ready)"
            if embedded_ok
            else "Embedded QGIS Python (missing dependencies; use External environment)"
        )
        ml_ready = any(
            s.available
            for s in statuses
            if "spatial ML" in s.required_for and "scikit-learn" in s.name
        )
        self.dock.ml_dependency_label.setText(
            ""
            if ml_ready
            else "scikit-learn not available in the embedded interpreter; "
            "experimental ML requires External environment execution mode."
        )

    def on_check_external_interpreter(self, python_path: str) -> None:
        if not python_path:
            QMessageBox.information(
                self.dock,
                "No interpreter selected",
                "Browse to a Python interpreter first (e.g. .venv/Scripts/python.exe).",
            )
            return
        statuses = dependency_check.check_external_interpreter(python_path)
        if statuses is None:
            QMessageBox.warning(
                self.dock, "Check failed", f"Could not run the interpreter at:\n{python_path}"
            )
            self.dock.set_execution_mode_label(f"External interpreter unreachable: {python_path}")
            return
        self.dock.set_dependency_table(statuses)
        ok = dependency_check.embedded_mode_available(statuses) and any(
            s.name == "solafune_change" and s.available for s in statuses
        )
        self.dock.set_execution_mode_label(
            f"External interpreter {'ready' if ok else 'missing packages, see table'}: {python_path}"
        )

    # ------------------------------------------------------------------ validation
    def _build_request_kwargs(self) -> dict:
        d = self.dock
        paths = d.get_paths()
        kwargs = {
            "before_folder": Path(paths["before_folder"]),
            "after_folder": Path(paths["after_folder"]),
            "aoi_path": Path(paths["aoi"]),
            "output_dir": Path(paths["output_dir"]),
            "run_label": paths["run_label"],
        }
        kwargs.update(d.get_change_detection_options())
        kwargs.update(d.get_spatial_options())
        kwargs.update(d.get_output_options())
        kwargs.pop("load_results", None)
        kwargs.pop("apply_styles", None)
        kwargs.pop("zoom_to_results", None)
        return kwargs

    def on_clear_inputs(self) -> None:
        """Reset the Inputs tab (paths, run label, validation result) and forget
        the persisted path values too, so a stale before/after/AOI/output
        selection from a previous session doesn't silently linger after a
        QGIS restart."""
        self.dock.clear_inputs()
        settings.save_all(
            {
                "paths/before_folder": "",
                "paths/after_folder": "",
                "paths/aoi": "",
                "paths/output_dir": "",
                "run/label": "run",
            }
        )
        self._result = None
        self._set_state("IDLE")

    def on_validate(self) -> None:
        self._set_state("VALIDATING")
        statuses = dependency_check.check_current_interpreter()
        embedded_ok = dependency_check.embedded_mode_available(statuses)

        if embedded_ok:
            self._validate_embedded()
        elif self.dock.external_interpreter_edit.text():
            self._validate_external()
        else:
            QMessageBox.warning(
                self.dock,
                "Dependencies missing",
                "The embedded QGIS Python interpreter is missing packages required for "
                "validation (e.g. rasterio, geopandas) — see the Dependencies tab. Set an "
                "'External interpreter' there (e.g. this project's .venv) and try again.",
            )
            self._set_state("IDLE")

    def _validate_embedded(self) -> None:
        try:
            import_core()
            from solafune_change.pipeline import validate_request
            from solafune_change.types import PipelineRequest
        except (CoreImportError, ImportError) as exc:
            QMessageBox.warning(
                self.dock,
                "Dependencies missing",
                f"Could not import a package the embedded core engine needs: {exc}\n\n"
                "Set an External interpreter in the Dependencies tab instead.",
            )
            self._set_state("IDLE")
            return

        try:
            request = PipelineRequest(**self._build_request_kwargs())
            report = validate_request(request)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self.dock, "Validation error", str(exc))
            self._set_state("IDLE")
            return

        ui_report = from_core_report(report)
        self.dock.set_validation_report(ui_report.status, ui_report.issues, ui_report.band_metadata)
        self._set_state("READY" if ui_report.is_valid else "IDLE")

    def _validate_external(self) -> None:
        # Blocking on purpose: validation only reads a handful of raster headers and
        # is normally sub-second to a few seconds, unlike a full analysis run (which
        # always goes through the async QProcess path in _run_external). A short,
        # bounded freeze here is a deliberate simplification, not an oversight.
        import subprocess

        python_path = self.dock.external_interpreter_edit.text()
        config_path = self._write_temp_config()
        try:
            proc = subprocess.run(
                [
                    python_path,
                    "-m",
                    "solafune_change",
                    "validate",
                    "--config",
                    config_path,
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            QMessageBox.warning(
                self.dock, "Validation failed", f"Could not run the external interpreter: {exc}"
            )
            self._set_state("IDLE")
            return

        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            tail = (proc.stderr or proc.stdout or "(no output)")[-2000:]
            QMessageBox.warning(
                self.dock,
                "Validation failed",
                f"Unexpected output from external validation:\n{tail}",
            )
            self._set_state("IDLE")
            return

        if "error" in payload:
            QMessageBox.warning(self.dock, "Validation error", payload["error"])
            self._set_state("IDLE")
            return

        issues = [
            UiValidationIssue(i["severity"], i["code"], i["message"])
            for i in payload.get("issues", [])
        ]
        ui_report = UiValidationReport(
            status=payload.get("status", "invalid"),
            issues=issues,
            band_metadata=payload.get("band_metadata", []),
        )
        self.dock.set_validation_report(ui_report.status, ui_report.issues, ui_report.band_metadata)
        self._set_state("READY" if ui_report.is_valid else "IDLE")

    # ------------------------------------------------------------------ run
    def on_run(self) -> None:
        self.persist_settings()
        mode = self._resolve_execution_mode()
        if mode is None:
            return

        self._release_stale_output_layers(self.dock.get_paths()["output_dir"])

        self.dock.log_view.clear()
        self._set_state("RUNNING")
        self._start_time = time.time()
        self._elapsed_timer.start(1000)

        if mode == "embedded":
            self._run_embedded()
        else:
            self._run_external()

    def _release_stale_output_layers(self, output_dir: str) -> None:
        """Windows guard against WinError 5 (Access Denied) on re-run.

        A previous run's rasters/vectors may still be loaded as QGIS layers
        (added by layer_loader.load_results(), never auto-removed since each
        run's layer group has a unique run_id). GDAL opens files on Windows
        without FILE_SHARE_DELETE, so a still-open layer blocks this run's
        atomic_output() from os.replace()-ing the very same path -- even in
        External mode, since the file is locked by *this* QGIS process, not
        the subprocess. Drop any project layer whose source file lives under
        this run's output/processed directories before writing starts.
        """
        if not output_dir:
            return
        out_path = Path(output_dir).expanduser().resolve()
        processed_path = out_path.parent / "data" / "processed"
        targets = (out_path, processed_path)

        project = QgsProject.instance()
        stale_ids = []
        for layer_id, layer in project.mapLayers().items():
            source = layer.source().split("|")[0]
            try:
                source_path = Path(source).resolve()
            except (OSError, ValueError):
                continue
            if any(source_path == t or source_path.is_relative_to(t) for t in targets):
                stale_ids.append(layer_id)
        if stale_ids:
            self.dock.append_log(
                f"Removing {len(stale_ids)} layer(s) from a previous run to avoid file locks."
            )
            project.removeMapLayers(stale_ids)

    def _resolve_execution_mode(self) -> str | None:
        requested = self.dock.get_execution_mode()
        statuses = dependency_check.check_current_interpreter()
        embedded_ok = dependency_check.embedded_mode_available(statuses)

        if requested == "embedded":
            if not embedded_ok:
                QMessageBox.warning(
                    self.dock,
                    "Embedded mode unavailable",
                    "The embedded QGIS Python interpreter is missing required packages. See the Dependencies tab.",
                )
                return None
            return "embedded"
        if requested == "external":
            if not self.dock.external_interpreter_edit.text():
                QMessageBox.warning(
                    self.dock,
                    "No external interpreter",
                    "Set an external Python interpreter path in the Dependencies tab.",
                )
                return None
            return "external"
        # requested == "auto"
        if embedded_ok:
            return "embedded"
        if self.dock.external_interpreter_edit.text():
            return "external"
        QMessageBox.warning(
            self.dock,
            "No usable Python environment",
            "The embedded QGIS Python interpreter is missing required packages, and no "
            "External interpreter is configured. Set one in the Dependencies tab (e.g. "
            "this project's .venv/Scripts/python.exe).",
        )
        return None

    def _write_temp_config(self) -> str:
        fd, path = tempfile.mkstemp(prefix="solafune_change_", suffix=".yaml")
        os.close(fd)
        settings.export_yaml(self._current_settings_dict(), path)
        self._temp_config_path = path
        return path

    def _run_embedded(self) -> None:
        from solafune_change.types import PipelineRequest

        request = PipelineRequest(**self._build_request_kwargs())
        self._task = EmbeddedAnalysisTask(request)
        self._task.taskCompleted.connect(self._on_embedded_finished)
        self._task.taskTerminated.connect(self._on_embedded_finished)
        self.dock.append_log(f"Starting embedded analysis (task id={id(self._task)})...")
        QgsApplication.taskManager().addTask(self._task)

    def _on_embedded_finished(self) -> None:
        self._elapsed_timer.stop()
        for stage, message, percent, _severity in getattr(self._task, "progress_log", []):
            self.dock.set_progress(percent, stage, message)
            self.dock.append_log(f"[{percent:5.1f}%] {stage}: {message}")

        if self._task.result is not None:
            self._result = from_core_result(self._task.result)
            self._on_run_success()
        else:
            error = self._task.error_message or "Unknown error"
            if "Cancelled" in error:
                self._set_state("CANCELLED")
                self.dock.append_log("Run cancelled by user.")
            else:
                self._set_state("FAILED")
                self.dock.append_log(f"FAILED: {error}")
                QMessageBox.critical(self.dock, "Analysis failed", error)
        self._task = None

    def _run_external(self) -> None:
        python_path = self.dock.external_interpreter_edit.text()
        config_path = self._write_temp_config()
        self._external_runner = ExternalAnalysisRunner(python_path, config_path)
        self._external_runner.progress.connect(self._on_external_progress)
        self._external_runner.finished.connect(self._on_external_finished)
        self.dock.append_log(
            f"Starting external analysis: {python_path} -m solafune_change all --config {config_path}"
        )
        self._external_runner.start()

    def _on_external_progress(
        self, stage: str, message: str, percent: float, severity: str
    ) -> None:
        self.dock.set_progress(percent, stage, message)
        self.dock.append_log(f"[{percent:5.1f}%] {stage}: {message}")

    def _on_external_finished(self, success: bool, manifest_or_error: str) -> None:
        self._elapsed_timer.stop()
        if success:
            manifest_path = manifest_or_error
            summary_path = str(Path(manifest_path).parent / "summary.json")
            try:
                self._result = from_manifest_files(manifest_path, summary_path)
                self._on_run_success()
            except Exception as exc:  # noqa: BLE001
                self._set_state("FAILED")
                self.dock.append_log(f"FAILED to parse results: {exc}")
                QMessageBox.critical(
                    self.dock,
                    "Analysis failed",
                    f"Run finished but results could not be read: {exc}",
                )
        elif "Cancelled" in manifest_or_error:
            self._set_state("CANCELLED")
            self.dock.append_log("Run cancelled by user.")
        else:
            self._set_state("FAILED")
            self.dock.append_log(f"FAILED: {manifest_or_error}")
            QMessageBox.critical(self.dock, "Analysis failed", manifest_or_error)
        self._external_runner = None

    def _on_run_success(self) -> None:
        self._set_state("COMPLETED")
        self.dock.set_progress(100.0, "report", "Run complete")
        self.dock.set_summary(self._result.summary)
        self.dock.append_log(f"Run complete: {self._result.run_id}")
        for w in self._result.warnings:
            self.dock.append_log(f"WARNING: {w}")

        if self.dock.get_output_options()["load_results"]:
            self._load_results_into_project()

    def _load_results_into_project(self) -> None:
        from . import layer_loader

        aoi_path = self.dock.get_paths()["aoi"]
        try:
            loaded, warnings = layer_loader.load_results(self._result, aoi_path)
            self.dock.append_log(f"Loaded {len(loaded)} layer(s): {', '.join(loaded)}")
            for w in warnings:
                self.dock.append_log(f"WARNING: {w}")
            if warnings:
                QgsMessageLog.logMessage(
                    "; ".join(warnings), "Solafune Change Analyzer", Qgis.Warning
                )
                QMessageBox.warning(
                    self.dock,
                    "Some layers did not load",
                    f"{len(warnings)} of the expected result layer(s) could not be loaded:\n\n"
                    + "\n".join(warnings)
                    + "\n\nSee the log below and the QGIS Log Messages panel "
                    "(Solafune Change Analyzer tab) for detail.",
                )
            if self.dock.get_output_options()["zoom_to_results"] and self.iface is not None:
                self.iface.mapCanvas().refresh()
        except Exception as exc:  # noqa: BLE001
            self.dock.append_log(f"Layer loading failed: {exc}")
            QgsMessageLog.logMessage(
                f"Layer loading failed: {exc}", "Solafune Change Analyzer", Qgis.Critical
            )
            QMessageBox.critical(
                self.dock,
                "Layer loading failed",
                f"The run completed, but loading its result layers into the QGIS project failed:\n\n{exc}\n\n"
                "The output files themselves should still be on disk in the output folder "
                "(Open Output Folder). See the QGIS Log Messages panel (Solafune Change Analyzer "
                "tab) for the full traceback.",
            )

    # ------------------------------------------------------------------ cancel
    def on_cancel(self) -> None:
        self._set_state("CANCELLING")
        if self._task is not None:
            self._task.cancel()
        if self._external_runner is not None:
            self._external_runner.cancel()

    def _tick_elapsed(self) -> None:
        elapsed = time.time() - self._start_time
        self.dock.set_elapsed(f"Elapsed: {elapsed:0.0f}s")

    # ------------------------------------------------------------------ result actions
    def on_open_output_folder(self) -> None:
        if self._result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._result.output_dir))

    def on_open_report(self) -> None:
        if self._result:
            path = self._result.get_path("report_md")
            if path and path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def on_open_map(self) -> None:
        if self._result:
            path = self._result.get_path("interactive_map_html")
            if path and path.exists():
                webbrowser.open(path.as_uri())

    def on_add_results_to_map(self) -> None:
        if self._result:
            self._load_results_into_project()

    def on_copy_summary(self) -> None:
        QApplication.clipboard().setText(self.dock.get_summary_text())

    # ------------------------------------------------------------------ teardown
    def shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()
        if self._external_runner is not None:
            self._external_runner.cancel()
        self._elapsed_timer.stop()
        if self._temp_config_path and os.path.exists(self._temp_config_path):
            try:
                os.remove(self._temp_config_path)
            except OSError:
                pass
