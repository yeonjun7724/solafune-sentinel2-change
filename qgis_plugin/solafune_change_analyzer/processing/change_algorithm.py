"""Processing Toolbox algorithm: 'Sentinel-2 Change Analysis'.

Uses the exact same :func:`solafune_change.pipeline.run_pipeline` request
builder as the dock widget (via :mod:`..core_bridge`) -- no analysis logic is
duplicated here, only Processing-parameter <-> ``PipelineRequest`` plumbing.
"""

from __future__ import annotations

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
)


class Sentinel2ChangeAnalysisAlgorithm(QgsProcessingAlgorithm):
    BEFORE_FOLDER = "BEFORE_FOLDER"
    AFTER_FOLDER = "AFTER_FOLDER"
    AOI = "AOI"
    OUTPUT_DIR = "OUTPUT_DIR"
    METHOD = "METHOD"
    NORMALIZATION = "NORMALIZATION"
    THRESHOLD_METHOD = "THRESHOLD_METHOD"
    THRESHOLD_VALUE = "THRESHOLD_VALUE"
    MIN_AREA = "MIN_AREA"
    STATS_ENABLED = "STATS_ENABLED"
    GRID_SIZE = "GRID_SIZE"
    WEIGHTS = "WEIGHTS"
    PERMUTATIONS = "PERMUTATIONS"
    ML_ENABLED = "ML_ENABLED"
    SEED = "SEED"

    OUT_GEOPACKAGE = "OUT_GEOPACKAGE"
    OUT_SUMMARY = "OUT_SUMMARY"
    OUT_REPORT = "OUT_REPORT"
    OUT_FOLDER = "OUT_FOLDER"

    METHOD_OPTIONS = ["baseline", "cva", "both"]
    NORMALIZATION_OPTIONS = ["none", "robust_median_mad", "percentile_matching", "pif_linear"]
    THRESHOLD_OPTIONS = ["otsu", "percentile", "manual"]
    WEIGHTS_OPTIONS = ["queen", "rook", "knn"]

    def createInstance(self):  # noqa: N802
        return Sentinel2ChangeAnalysisAlgorithm()

    def name(self) -> str:
        return "sentinel2_change_analysis"

    def displayName(self) -> str:  # noqa: N802
        return "Sentinel-2 Change Analysis"

    def group(self) -> str:
        return "Change Detection"

    def groupId(self) -> str:  # noqa: N802
        return "change_detection"

    def shortHelpString(self) -> str:  # noqa: N802
        return (
            "Runs the shared solafune_change engine: baseline + robust RGB Change Vector Analysis, "
            "thresholding/morphology, polygonization, Global/Local Moran's I, Getis-Ord Gi* (with FDR "
            "correction), and writes a GeoPackage + summary + report.md. Requires the same Python "
            "dependencies as the CLI (rasterio, geopandas, libpysal, esda, ...) in the interpreter "
            "running QGIS's Processing framework."
        )

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterFile(
                self.BEFORE_FOLDER,
                "Before Sentinel-2 folder",
                behavior=QgsProcessingParameterFile.Folder,
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.AFTER_FOLDER,
                "After Sentinel-2 folder",
                behavior=QgsProcessingParameterFile.Folder,
            )
        )
        self.addParameter(QgsProcessingParameterFile(self.AOI, "AOI vector file"))
        self.addParameter(
            QgsProcessingParameterFolderDestination(self.OUTPUT_DIR, "Output directory")
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.METHOD, "Method", options=self.METHOD_OPTIONS, defaultValue=2
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.NORMALIZATION,
                "Radiometric normalization",
                options=self.NORMALIZATION_OPTIONS,
                defaultValue=1,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.THRESHOLD_METHOD,
                "Threshold method",
                options=self.THRESHOLD_OPTIONS,
                defaultValue=0,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.THRESHOLD_VALUE,
                "Percentile / manual threshold value",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=95.0,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MIN_AREA,
                "Minimum change area (m^2)",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=400.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.STATS_ENABLED, "Enable spatial statistics", defaultValue=True
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.GRID_SIZE,
                "Spatial statistics grid size (m)",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=150.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.WEIGHTS, "Spatial weights", options=self.WEIGHTS_OPTIONS, defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PERMUTATIONS,
                "Permutations",
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=999,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.ML_ENABLED, "Enable experimental spatial ML", defaultValue=False
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SEED, "Random seed", type=QgsProcessingParameterNumber.Integer, defaultValue=42
            )
        )

        self.addOutput(QgsProcessingOutputFile(self.OUT_GEOPACKAGE, "Change analysis GeoPackage"))
        self.addOutput(QgsProcessingOutputFile(self.OUT_SUMMARY, "Summary JSON"))
        self.addOutput(QgsProcessingOutputFile(self.OUT_REPORT, "Report (Markdown)"))
        self.addOutput(QgsProcessingOutputFolder(self.OUT_FOLDER, "Output folder"))

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802
        try:
            from ..core_bridge import import_core

            import_core()
            from solafune_change.errors import CancelledError, SolafuneChangeError
            from solafune_change.pipeline import run_pipeline
            from solafune_change.types import CancellationToken, PipelineRequest, ProgressEvent
        except Exception as exc:  # noqa: BLE001
            raise QgsProcessingException(
                f"Could not import the solafune_change core engine: {exc}. Run this algorithm with a QGIS "
                "Python environment that has the CLI's dependencies installed."
            ) from exc

        from pathlib import Path

        before = self.parameterAsFile(parameters, self.BEFORE_FOLDER, context)
        after = self.parameterAsFile(parameters, self.AFTER_FOLDER, context)
        aoi = self.parameterAsFile(parameters, self.AOI, context)
        output_dir = self.parameterAsString(parameters, self.OUTPUT_DIR, context)
        method = self.METHOD_OPTIONS[self.parameterAsEnum(parameters, self.METHOD, context)]
        normalization = self.NORMALIZATION_OPTIONS[
            self.parameterAsEnum(parameters, self.NORMALIZATION, context)
        ]
        threshold_method = self.THRESHOLD_OPTIONS[
            self.parameterAsEnum(parameters, self.THRESHOLD_METHOD, context)
        ]
        threshold_value = self.parameterAsDouble(parameters, self.THRESHOLD_VALUE, context)
        weights = self.WEIGHTS_OPTIONS[self.parameterAsEnum(parameters, self.WEIGHTS, context)]

        request = PipelineRequest(
            before_folder=Path(before),
            after_folder=Path(after),
            aoi_path=Path(aoi),
            output_dir=Path(output_dir),
            method=method,
            normalization=normalization,
            threshold_method=threshold_method,
            percentile=threshold_value if threshold_method == "percentile" else 95.0,
            manual_threshold=threshold_value if threshold_method == "manual" else None,
            min_area_m2=self.parameterAsDouble(parameters, self.MIN_AREA, context),
            spatial_statistics_enabled=self.parameterAsBoolean(
                parameters, self.STATS_ENABLED, context
            ),
            spatial_grid_size_m=self.parameterAsDouble(parameters, self.GRID_SIZE, context),
            spatial_weights=weights,
            permutations=self.parameterAsInt(parameters, self.PERMUTATIONS, context),
            spatial_ml_enabled=self.parameterAsBoolean(parameters, self.ML_ENABLED, context),
            random_seed=self.parameterAsInt(parameters, self.SEED, context),
        )

        token = CancellationToken()

        def _progress(evt: ProgressEvent) -> None:
            feedback.setProgress(evt.percent)
            feedback.pushInfo(f"[{evt.percent:5.1f}%] {evt.stage}: {evt.message}")
            if feedback.isCanceled():
                token.cancel()

        try:
            result = run_pipeline(request, progress_callback=_progress, cancellation_token=token)
        except CancelledError:
            feedback.pushInfo("Cancelled by user.")
            return {}
        except SolafuneChangeError as exc:
            raise QgsProcessingException(exc.user_message) from exc

        feedback.pushInfo(f"Run complete: {result.run_id} ({result.runtime_seconds:.1f}s)")
        return {
            self.OUT_GEOPACKAGE: str(result.database) if result.database else "",
            self.OUT_SUMMARY: str(result.summary_json) if result.summary_json else "",
            self.OUT_REPORT: str(result.report_md) if result.report_md else "",
            self.OUT_FOLDER: str(result.output_dir),
        }
