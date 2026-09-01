"""Dock widget UI: five tabs (Inputs, Change Detection, Spatial Analysis,
Outputs, Run & Results) plus a Dependencies tab for execution-mode setup.

Pure UI construction and value get/set -- no analysis logic and no direct
``solafune_change`` import. ``controller.py`` connects to this widget's
signals (``validateRequested``, ``runRequested``, ``cancelRequested``, ...)
and calls its ``set_*``/``append_log`` methods to reflect state back.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

STATUS_COLORS = {
    "not_run": "#888",
    "valid": "#2e7d32",
    "valid_with_warnings": "#e65100",
    "invalid": "#c62828",
}
STATUS_LABELS = {
    "not_run": "Not validated",
    "valid": "Valid",
    "valid_with_warnings": "Valid, with warnings",
    "invalid": "Invalid",
}


def _browse_row(parent: QWidget, is_dir: bool, filter_str: str = "") -> tuple[QWidget, QLineEdit]:
    container = QWidget(parent)
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    edit = QLineEdit(container)
    button = QToolButton(container)
    button.setText("...")

    def _browse() -> None:
        if is_dir:
            path = QFileDialog.getExistingDirectory(parent, "Select folder", edit.text())
        else:
            path, _ = QFileDialog.getOpenFileName(parent, "Select file", edit.text(), filter_str)
        if path:
            edit.setText(path)

    button.clicked.connect(_browse)
    layout.addWidget(edit)
    layout.addWidget(button)
    return container, edit


class SolafuneChangeDockWidget(QDockWidget):
    validateRequested = pyqtSignal()
    clearInputsRequested = pyqtSignal()
    runRequested = pyqtSignal()
    cancelRequested = pyqtSignal()
    restoreDefaultsRequested = pyqtSignal()
    importYamlRequested = pyqtSignal(str)
    exportYamlRequested = pyqtSignal(str)
    openOutputFolderRequested = pyqtSignal()
    openReportRequested = pyqtSignal()
    openMapRequested = pyqtSignal()
    addResultsToMapRequested = pyqtSignal()
    copySummaryRequested = pyqtSignal()
    saveLogRequested = pyqtSignal(str)
    checkExternalInterpreterRequested = pyqtSignal(str)
    toggleBeforeAfterRequested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__("Solafune Change Analyzer", parent)
        self.setObjectName("SolafuneChangeAnalyzerDockWidget")
        self._build_ui()
        self.set_state("IDLE")

    # ------------------------------------------------------------------ UI build
    def _build_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        self.tabs = QTabWidget(root)
        root_layout.addWidget(self.tabs)
        self.setWidget(root)

        self.tabs.addTab(self._build_inputs_tab(), "Inputs")
        self.tabs.addTab(self._build_change_tab(), "Change Detection")
        self.tabs.addTab(self._build_spatial_tab(), "Spatial Analysis")
        self.tabs.addTab(self._build_outputs_tab(), "Outputs")
        self.tabs.addTab(self._build_run_tab(), "Run && Results")
        self.tabs.addTab(self._build_dependencies_tab(), "Dependencies")

    def _build_inputs_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)

        before_row, self.before_edit = _browse_row(w, is_dir=True)
        after_row, self.after_edit = _browse_row(w, is_dir=True)
        aoi_row, self.aoi_edit = _browse_row(
            w, is_dir=False, filter_str="Vector files (*.geojson *.gpkg *.shp);;All files (*)"
        )
        out_row, self.output_dir_edit = _browse_row(w, is_dir=True)
        self.run_label_edit = QLineEdit("run")

        layout.addRow("Before Sentinel-2 folder:", before_row)
        layout.addRow("After Sentinel-2 folder:", after_row)
        layout.addRow("AOI vector file:", aoi_row)
        layout.addRow("Output directory:", out_row)
        layout.addRow("Run label:", self.run_label_edit)

        button_row = QWidget(w)
        button_row_layout = QHBoxLayout(button_row)
        button_row_layout.setContentsMargins(0, 0, 0, 0)
        self.validate_button = QPushButton("Validate Inputs")
        self.validate_button.clicked.connect(self.validateRequested.emit)
        self.clear_inputs_button = QPushButton("Clear Inputs (초기화)")
        self.clear_inputs_button.setToolTip(
            "Clears the Before/After/AOI/Output paths and the validation status/results on "
            "this tab. Does not touch Change Detection / Spatial Analysis / Outputs settings."
        )
        self.clear_inputs_button.clicked.connect(self.clearInputsRequested.emit)
        button_row_layout.addWidget(self.validate_button)
        button_row_layout.addWidget(self.clear_inputs_button)
        layout.addRow(button_row)

        self.validation_status_label = QLabel()
        layout.addRow("Status:", self.validation_status_label)

        self.validation_issues_text = QTextEdit()
        self.validation_issues_text.setReadOnly(True)
        self.validation_issues_text.setMaximumHeight(90)
        layout.addRow("Issues:", self.validation_issues_text)

        self.band_table = QTableWidget(0, 8)
        self.band_table.setHorizontalHeaderLabels(
            ["Date", "Band", "Filename", "CRS", "Pixel size", "Width", "Height", "Valid ratio"]
        )
        self.band_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addRow("Band metadata:", self.band_table)
        return w

    def _build_change_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)

        self.method_combo = QComboBox()
        self.method_combo.addItems(["Provided baseline", "Robust RGB CVA", "Run both"])
        self.method_combo.setCurrentIndex(2)
        layout.addRow("Analysis method:", self.method_combo)

        self.normalization_combo = QComboBox()
        self.normalization_combo.addItems(
            ["None", "Robust median/MAD", "Percentile matching", "Pseudo-invariant features (PIF)"]
        )
        self.normalization_combo.setCurrentIndex(1)
        layout.addRow("Radiometric normalization:", self.normalization_combo)

        self.threshold_combo = QComboBox()
        self.threshold_combo.addItems(["Otsu", "Percentile", "Manual"])
        self.threshold_combo.currentIndexChanged.connect(self._sync_threshold_controls)
        layout.addRow("Threshold method:", self.threshold_combo)

        self.percentile_spin = QDoubleSpinBox()
        self.percentile_spin.setRange(0.0, 100.0)
        self.percentile_spin.setValue(95.0)
        layout.addRow("Percentile:", self.percentile_spin)

        self.manual_threshold_spin = QDoubleSpinBox()
        self.manual_threshold_spin.setRange(0.0, 1_000_000.0)
        self.manual_threshold_spin.setDecimals(4)
        layout.addRow("Manual threshold value:", self.manual_threshold_spin)

        self.morphology_checkbox = QCheckBox("Enable morphology")
        self.morphology_checkbox.setChecked(True)
        layout.addRow(self.morphology_checkbox)

        self.morphology_op_combo = QComboBox()
        self.morphology_op_combo.addItems(["Open", "Close", "Open then Close"])
        self.morphology_op_combo.setCurrentIndex(2)
        layout.addRow("Operation:", self.morphology_op_combo)

        self.kernel_size_spin = QSpinBox()
        self.kernel_size_spin.setRange(1, 15)
        self.kernel_size_spin.setValue(3)
        layout.addRow("Kernel size (px):", self.kernel_size_spin)

        self.fill_holes_checkbox = QCheckBox("Fill small holes")
        layout.addRow(self.fill_holes_checkbox)

        self.min_area_spin = QDoubleSpinBox()
        self.min_area_spin.setRange(0.0, 10_000_000.0)
        self.min_area_spin.setValue(400.0)
        self.min_area_spin.setSuffix(" m2")
        layout.addRow("Minimum change area:", self.min_area_spin)

        self._sync_threshold_controls()
        return w

    def _sync_threshold_controls(self) -> None:
        method = self.threshold_combo.currentText()
        self.percentile_spin.setEnabled(method == "Percentile")
        self.manual_threshold_spin.setEnabled(method == "Manual")

    def _build_spatial_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        stats_box = QGroupBox("Spatial statistics")
        stats_layout = QFormLayout(stats_box)
        self.stats_enabled_checkbox = QCheckBox("Enable spatial statistics")
        self.stats_enabled_checkbox.setChecked(True)
        self.stats_enabled_checkbox.toggled.connect(self._sync_stats_controls)
        stats_layout.addRow(self.stats_enabled_checkbox)

        self.grid_size_spin = QDoubleSpinBox()
        self.grid_size_spin.setRange(20.0, 5000.0)
        self.grid_size_spin.setValue(150.0)
        self.grid_size_spin.setSuffix(" m")
        stats_layout.addRow("Grid cell size:", self.grid_size_spin)

        self.weights_combo = QComboBox()
        self.weights_combo.addItems(["Queen contiguity", "Rook contiguity", "K nearest neighbors"])
        self.weights_combo.setToolTip(
            "Contiguity/adjacency definition used to build the spatial weights graph between grid cells."
        )
        stats_layout.addRow("Spatial weights:", self.weights_combo)

        self.knn_k_spin = QSpinBox()
        self.knn_k_spin.setRange(3, 30)
        self.knn_k_spin.setValue(8)
        stats_layout.addRow("K (if KNN):", self.knn_k_spin)

        self.row_standardize_checkbox = QCheckBox("Row-standardize weights (Moran's I)")
        self.row_standardize_checkbox.setChecked(True)
        stats_layout.addRow(self.row_standardize_checkbox)

        self.permutations_spin = QSpinBox()
        self.permutations_spin.setRange(99, 9999)
        self.permutations_spin.setValue(999)
        stats_layout.addRow("Permutations:", self.permutations_spin)

        self.alpha_spin = QDoubleSpinBox()
        self.alpha_spin.setRange(0.001, 0.5)
        self.alpha_spin.setSingleStep(0.01)
        self.alpha_spin.setValue(0.05)
        stats_layout.addRow("Significance alpha:", self.alpha_spin)

        self.fdr_checkbox = QCheckBox("Benjamini-Hochberg FDR correction (Gi*)")
        self.fdr_checkbox.setChecked(True)
        self.fdr_checkbox.setToolTip(
            "Corrects Gi* p-values for multiple local significance tests across all grid cells."
        )
        stats_layout.addRow(self.fdr_checkbox)

        gm_label = QLabel(
            "Global Moran's I: overall spatial autocorrelation of change intensity.\n"
            "Local Moran's I: per-cell HH/LL/HL/LH cluster membership.\n"
            "Getis-Ord Gi*: statistically significant hot/cold spots."
        )
        gm_label.setWordWrap(True)
        gm_label.setStyleSheet("color: #666; font-size: 10px;")
        stats_layout.addRow(gm_label)
        layout.addWidget(stats_box)

        ml_box = QGroupBox("Experimental unsupervised spatial ML")
        ml_layout = QFormLayout(ml_box)
        warning = QLabel(
            "No ground-truth labels are provided. ML outputs are exploratory anomaly rankings, not validated predictions."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #b45309; font-weight: bold;")
        ml_layout.addRow(warning)

        self.ml_enabled_checkbox = QCheckBox("Enable unsupervised spatial ML (experimental)")
        self.ml_enabled_checkbox.toggled.connect(self._sync_ml_controls)
        ml_layout.addRow(self.ml_enabled_checkbox)

        self.ml_model_combo = QComboBox()
        self.ml_model_combo.addItems(["Isolation Forest", "DBSCAN"])
        self.ml_model_combo.currentIndexChanged.connect(self._sync_ml_controls)
        ml_layout.addRow("Model:", self.ml_model_combo)

        self.ml_contamination_spin = QDoubleSpinBox()
        self.ml_contamination_spin.setRange(0.01, 0.49)
        self.ml_contamination_spin.setSingleStep(0.01)
        self.ml_contamination_spin.setValue(0.1)
        ml_layout.addRow("Contamination:", self.ml_contamination_spin)

        self.ml_eps_spin = QDoubleSpinBox()
        self.ml_eps_spin.setRange(0.1, 20.0)
        self.ml_eps_spin.setValue(1.5)
        ml_layout.addRow("DBSCAN eps:", self.ml_eps_spin)

        self.ml_min_samples_spin = QSpinBox()
        self.ml_min_samples_spin.setRange(2, 100)
        self.ml_min_samples_spin.setValue(5)
        ml_layout.addRow("DBSCAN min samples:", self.ml_min_samples_spin)

        self.ml_dependency_label = QLabel()
        self.ml_dependency_label.setWordWrap(True)
        ml_layout.addRow(self.ml_dependency_label)

        layout.addWidget(ml_box)
        layout.addStretch(1)
        self._sync_stats_controls()
        self._sync_ml_controls()
        return w

    def _sync_stats_controls(self) -> None:
        enabled = self.stats_enabled_checkbox.isChecked()
        for widget in (
            self.grid_size_spin,
            self.weights_combo,
            self.knn_k_spin,
            self.row_standardize_checkbox,
            self.permutations_spin,
            self.alpha_spin,
            self.fdr_checkbox,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            self.ml_enabled_checkbox.setChecked(False)
        self.ml_enabled_checkbox.setEnabled(enabled)

    def _sync_ml_controls(self) -> None:
        enabled = self.ml_enabled_checkbox.isChecked()
        is_if = self.ml_model_combo.currentText() == "Isolation Forest"
        self.ml_contamination_spin.setEnabled(enabled and is_if)
        self.ml_eps_spin.setEnabled(enabled and not is_if)
        self.ml_min_samples_spin.setEnabled(enabled and not is_if)

    def _build_outputs_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.write_stacks_checkbox = QCheckBox("Write stacked GeoTIFFs")
        self.write_stacks_checkbox.setChecked(True)
        self.write_intermediate_checkbox = QCheckBox(
            "Write intermediate rasters (baseline + CVA intensity/binary)"
        )
        self.write_intermediate_checkbox.setChecked(True)
        self.create_map_checkbox = QCheckBox("Create interactive HTML map")
        self.create_map_checkbox.setChecked(True)
        self.create_styles_checkbox = QCheckBox("Create/apply QGIS QML styles")
        self.create_styles_checkbox.setChecked(True)
        self.load_results_checkbox = QCheckBox("Load results into current QGIS project")
        self.load_results_checkbox.setChecked(True)
        self.zoom_checkbox = QCheckBox("Zoom to results after loading")
        self.zoom_checkbox.setChecked(True)
        self.replace_group_checkbox = QCheckBox("Replace previous result group")
        self.replace_group_checkbox.setChecked(True)
        self.keep_failed_checkbox = QCheckBox("Keep temporary files from a failed/cancelled run")

        for cb in (
            self.write_stacks_checkbox,
            self.write_intermediate_checkbox,
            self.create_map_checkbox,
            self.create_styles_checkbox,
            self.load_results_checkbox,
            self.zoom_checkbox,
            self.replace_group_checkbox,
            self.keep_failed_checkbox,
        ):
            layout.addWidget(cb)

        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setMaximumHeight(140)
        preview.setPlainText(
            "outputs/\n  database/change_analysis.gpkg\n  figures/change_comparison.png\n"
            "  maps/interactive_map.html\n  statistics/global_moran.json, spatial_statistics.csv\n"
            "  qgis/styles/*.qml\n  summary.json, run_manifest.json, quality_report.json, report.md\n"
            "data/processed/\n  sentinel2_<date>_stack.tif, baseline_*.tif, cva_*.tif"
        )
        layout.addWidget(QLabel("Expected output structure:"))
        layout.addWidget(preview)
        layout.addStretch(1)
        return w

    def _build_run_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        button_row = QHBoxLayout()
        self.run_button = QPushButton("Run Analysis")
        self.run_button.clicked.connect(self.runRequested.emit)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancelRequested.emit)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        status_row = QHBoxLayout()
        self.stage_label = QLabel("Idle")
        self.elapsed_label = QLabel("")
        status_row.addWidget(self.stage_label)
        status_row.addStretch(1)
        status_row.addWidget(self.elapsed_label)
        layout.addLayout(status_row)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        layout.addWidget(self.log_view, stretch=1)

        self.summary_table = QTableWidget(0, 2)
        self.summary_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.summary_table.setMaximumHeight(220)
        layout.addWidget(self.summary_table)

        result_buttons = QHBoxLayout()
        self.open_folder_button = QPushButton("Open Output Folder")
        self.open_report_button = QPushButton("Open Report")
        self.open_map_button = QPushButton("Open Interactive Map")
        self.add_to_map_button = QPushButton("Add Results to Map")
        self.copy_summary_button = QPushButton("Copy Summary")
        self.save_log_button = QPushButton("Save Log")
        for btn, signal in (
            (self.open_folder_button, self.openOutputFolderRequested),
            (self.open_report_button, self.openReportRequested),
            (self.open_map_button, self.openMapRequested),
            (self.add_to_map_button, self.addResultsToMapRequested),
        ):
            btn.clicked.connect(signal.emit)
            result_buttons.addWidget(btn)
        self.copy_summary_button.clicked.connect(self.copySummaryRequested.emit)
        result_buttons.addWidget(self.copy_summary_button)
        result_buttons.addWidget(self.save_log_button)
        layout.addLayout(result_buttons)
        return w

    def _build_dependencies_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        mode_box = QGroupBox("Execution environment")
        mode_layout = QVBoxLayout(mode_box)
        self.mode_auto_radio = QRadioButton("Automatic (embedded if possible, else external)")
        self.mode_embedded_radio = QRadioButton("Embedded QGIS Python")
        self.mode_external_radio = QRadioButton("External Python environment")
        self.mode_auto_radio.setChecked(True)
        for rb in (self.mode_auto_radio, self.mode_embedded_radio, self.mode_external_radio):
            mode_layout.addWidget(rb)

        interp_row, self.external_interpreter_edit = _browse_row(
            w, is_dir=False, filter_str="Python interpreter (python.exe python);;All files (*)"
        )
        mode_layout.addWidget(
            QLabel("External interpreter (e.g. project .venv/Scripts/python.exe):")
        )
        mode_layout.addWidget(interp_row)
        self.check_interpreter_button = QPushButton("Check dependencies")
        self.check_interpreter_button.clicked.connect(
            lambda: self.checkExternalInterpreterRequested.emit(
                self.external_interpreter_edit.text()
            )
        )
        mode_layout.addWidget(self.check_interpreter_button)

        self.execution_mode_label = QLabel("Execution environment: not checked yet")
        mode_layout.addWidget(self.execution_mode_label)
        layout.addWidget(mode_box)

        self.dependency_table = QTableWidget(0, 4)
        self.dependency_table.setHorizontalHeaderLabels(
            ["Package", "Required for", "Status", "Version"]
        )
        self.dependency_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(QLabel("Feature readiness:"))
        layout.addWidget(self.dependency_table)

        config_row = QHBoxLayout()
        self.restore_defaults_button = QPushButton("Restore defaults")
        self.import_yaml_button = QPushButton("Import configuration YAML")
        self.export_yaml_button = QPushButton("Export configuration YAML")
        self.restore_defaults_button.clicked.connect(self.restoreDefaultsRequested.emit)
        self.import_yaml_button.clicked.connect(self._prompt_import_yaml)
        self.export_yaml_button.clicked.connect(self._prompt_export_yaml)
        config_row.addWidget(self.restore_defaults_button)
        config_row.addWidget(self.import_yaml_button)
        config_row.addWidget(self.export_yaml_button)
        layout.addLayout(config_row)
        layout.addStretch(1)
        return w

    def _prompt_import_yaml(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import configuration", "", "YAML files (*.yaml *.yml)"
        )
        if path:
            self.importYamlRequested.emit(path)

    def _prompt_export_yaml(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export configuration", "solafune_change_config.yaml", "YAML files (*.yaml)"
        )
        if path:
            self.exportYamlRequested.emit(path)

    # ------------------------------------------------------------------ state management
    def set_state(self, state: str) -> None:
        running = state in ("VALIDATING", "RUNNING", "CANCELLING")
        for widget in (
            self.before_edit,
            self.after_edit,
            self.aoi_edit,
            self.output_dir_edit,
            self.run_label_edit,
            self.validate_button,
            self.clear_inputs_button,
            self.method_combo,
            self.threshold_combo,
            self.stats_enabled_checkbox,
            self.ml_enabled_checkbox,
            self.restore_defaults_button,
            self.import_yaml_button,
        ):
            widget.setEnabled(not running)
        self.run_button.setEnabled(state in ("IDLE", "READY", "COMPLETED", "FAILED", "CANCELLED"))
        self.cancel_button.setEnabled(state == "RUNNING")
        result_ready = state == "COMPLETED"
        for btn in (
            self.open_folder_button,
            self.open_report_button,
            self.open_map_button,
            self.add_to_map_button,
            self.copy_summary_button,
        ):
            btn.setEnabled(result_ready)
        self.stage_label.setText(
            {
                "IDLE": "Idle",
                "VALIDATING": "Validating inputs...",
                "READY": "Ready to run",
                "RUNNING": "Running...",
                "CANCELLING": "Cancelling...",
                "COMPLETED": "Completed",
                "FAILED": "Failed",
                "CANCELLED": "Cancelled by user",
            }.get(state, state)
        )

    # ------------------------------------------------------------------ value getters
    def get_paths(self) -> dict[str, str]:
        return {
            "before_folder": self.before_edit.text(),
            "after_folder": self.after_edit.text(),
            "aoi": self.aoi_edit.text(),
            "output_dir": self.output_dir_edit.text(),
            "run_label": self.run_label_edit.text() or "run",
        }

    def get_change_detection_options(self) -> dict:
        method_map = {"Provided baseline": "baseline", "Robust RGB CVA": "cva", "Run both": "both"}
        norm_map = {
            "None": "none",
            "Robust median/MAD": "robust_median_mad",
            "Percentile matching": "percentile_matching",
            "Pseudo-invariant features (PIF)": "pif_linear",
        }
        threshold_map = {"Otsu": "otsu", "Percentile": "percentile", "Manual": "manual"}
        morph_map = {
            "Open": "opening",
            "Close": "closing",
            "Open then Close": "opening_then_closing",
        }
        return {
            "method": method_map[self.method_combo.currentText()],
            "normalization": norm_map[self.normalization_combo.currentText()],
            "threshold_method": threshold_map[self.threshold_combo.currentText()],
            "percentile": self.percentile_spin.value(),
            "manual_threshold": (
                self.manual_threshold_spin.value()
                if self.threshold_combo.currentText() == "Manual"
                else None
            ),
            "morphology_enabled": self.morphology_checkbox.isChecked(),
            "morphology_operation": morph_map[self.morphology_op_combo.currentText()],
            "morphology_kernel_size": self.kernel_size_spin.value(),
            "fill_holes": self.fill_holes_checkbox.isChecked(),
            "min_area_m2": self.min_area_spin.value(),
        }

    def get_spatial_options(self) -> dict:
        weights_map = {
            "Queen contiguity": "queen",
            "Rook contiguity": "rook",
            "K nearest neighbors": "knn",
        }
        return {
            "spatial_statistics_enabled": self.stats_enabled_checkbox.isChecked(),
            "spatial_grid_size_m": self.grid_size_spin.value(),
            "spatial_weights": weights_map[self.weights_combo.currentText()],
            "knn_k": self.knn_k_spin.value(),
            "row_standardization": self.row_standardize_checkbox.isChecked(),
            "permutations": self.permutations_spin.value(),
            "alpha": self.alpha_spin.value(),
            "fdr_correction": self.fdr_checkbox.isChecked(),
            "spatial_ml_enabled": self.ml_enabled_checkbox.isChecked(),
            "ml_model": (
                "isolation_forest"
                if self.ml_model_combo.currentText() == "Isolation Forest"
                else "dbscan"
            ),
            "ml_contamination": self.ml_contamination_spin.value(),
            "dbscan_eps": self.ml_eps_spin.value(),
            "dbscan_min_samples": self.ml_min_samples_spin.value(),
        }

    def get_output_options(self) -> dict:
        return {
            "write_stacks": self.write_stacks_checkbox.isChecked(),
            "write_intermediate": self.write_intermediate_checkbox.isChecked(),
            "create_interactive_map": self.create_map_checkbox.isChecked(),
            "create_qgis_styles": self.create_styles_checkbox.isChecked(),
            "load_results": self.load_results_checkbox.isChecked(),
            "apply_styles": self.create_styles_checkbox.isChecked(),
            "zoom_to_results": self.zoom_checkbox.isChecked(),
        }

    def get_execution_mode(self) -> str:
        if self.mode_embedded_radio.isChecked():
            return "embedded"
        if self.mode_external_radio.isChecked():
            return "external"
        return "auto"

    # ------------------------------------------------------------------ value setters
    def set_paths(self, values: dict) -> None:
        self.before_edit.setText(values.get("before_folder", ""))
        self.after_edit.setText(values.get("after_folder", ""))
        self.aoi_edit.setText(values.get("aoi", ""))
        self.output_dir_edit.setText(values.get("output_dir", ""))

    def clear_inputs(self) -> None:
        """Reset the Inputs tab to a blank slate: paths, run label, and any
        previous Validate Inputs result. Leaves every other tab untouched."""
        self.before_edit.clear()
        self.after_edit.clear()
        self.aoi_edit.clear()
        self.output_dir_edit.clear()
        self.run_label_edit.setText("run")
        self.validation_status_label.setText("")
        self.validation_status_label.setStyleSheet("")
        self.validation_issues_text.clear()
        self.band_table.setRowCount(0)

    def set_validation_report(self, status: str, issues: list, band_metadata: list) -> None:
        color = STATUS_COLORS.get(status, "#888")
        self.validation_status_label.setText(STATUS_LABELS.get(status, status))
        self.validation_status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.validation_issues_text.setPlainText(
            "\n".join(f"[{i.severity.upper()}] {i.code}: {i.message}" for i in issues)
            or "No issues."
        )

        self.band_table.setRowCount(len(band_metadata))
        for row, meta in enumerate(band_metadata):
            values = [
                meta.get("date_label", ""),
                meta.get("band", ""),
                meta.get("path", "").split("\\")[-1].split("/")[-1],
                meta.get("crs", ""),
                f"{meta.get('pixel_size_x', 0):.1f}",
                str(meta.get("width", "")),
                str(meta.get("height", "")),
                f"{meta.get('valid_pixel_ratio', 0):.1%}",
            ]
            for col, value in enumerate(values):
                self.band_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.band_table.resizeColumnsToContents()

    def set_progress(self, percent: float, stage: str, message: str) -> None:
        self.progress_bar.setValue(int(percent))
        self.stage_label.setText(f"{stage}: {message}")

    def append_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)

    def set_elapsed(self, text: str) -> None:
        self.elapsed_label.setText(text)

    def set_summary(self, summary: dict) -> None:
        self.summary_table.setRowCount(len(summary))
        for row, (key, value) in enumerate(summary.items()):
            self.summary_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.summary_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self.summary_table.resizeColumnsToContents()

    def set_dependency_table(self, statuses: list) -> None:
        self.dependency_table.setRowCount(len(statuses))
        for row, status in enumerate(statuses):
            self.dependency_table.setItem(row, 0, QTableWidgetItem(status.name))
            self.dependency_table.setItem(row, 1, QTableWidgetItem(status.required_for))
            item = QTableWidgetItem("Ready" if status.available else "Missing")
            item.setForeground(Qt.darkGreen if status.available else Qt.red)
            self.dependency_table.setItem(row, 2, item)
            self.dependency_table.setItem(row, 3, QTableWidgetItem(status.version or "-"))
        self.dependency_table.resizeColumnsToContents()

    def set_execution_mode_label(self, text: str) -> None:
        self.execution_mode_label.setText(f"Execution environment: {text}")

    def get_log_text(self) -> str:
        return self.log_view.toPlainText()

    def get_summary_text(self) -> str:
        rows = []
        for row in range(self.summary_table.rowCount()):
            key = self.summary_table.item(row, 0).text()
            value = self.summary_table.item(row, 1).text()
            rows.append(f"{key}: {value}")
        return "\n".join(rows)
