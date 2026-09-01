"""Embedded execution mode: runs the core pipeline on a QgsTask worker thread.

Only used when :func:`dependency_check.embedded_mode_available` is true for
the running QGIS Python interpreter. The worker thread never touches
QgsProject/the layer tree/any widget -- it only computes and returns a
result; the caller (``controller.py``) does all QGIS-object mutation from the
task's ``taskCompleted``/``taskTerminated`` signals, which QGIS delivers on
the main thread.
"""

from __future__ import annotations

import logging
import traceback

from qgis.core import Qgis, QgsMessageLog, QgsTask

logger = logging.getLogger(__name__)


class EmbeddedAnalysisTask(QgsTask):
    """Runs ``solafune_change.pipeline.run_pipeline`` off the UI thread."""

    def __init__(self, request, description: str = "Solafune Change Analysis"):
        super().__init__(description, QgsTask.CanCancel)
        self._request = request
        self.result = None
        self.error_message: str | None = None
        self.progress_log: list[tuple[str, str, float, str]] = []

    def run(self) -> bool:  # noqa: D102 - QgsTask API
        from .core_bridge import import_core

        try:
            import_core()
            from solafune_change import errors as core_errors
            from solafune_change import pipeline as core_pipeline
        except Exception as exc:  # noqa: BLE001
            self.error_message = str(exc)
            return False

        class _TokenAdapter:
            def __init__(self, task: EmbeddedAnalysisTask) -> None:
                self._task = task

            def check(self, stage: str) -> None:
                if self._task.isCanceled():
                    raise core_errors.CancelledError(stage)

        def _on_progress(evt) -> None:
            self.progress_log.append((evt.stage, evt.message, evt.percent, evt.severity))
            self.setProgress(evt.percent)
            QgsMessageLog.logMessage(
                f"[{evt.percent:5.1f}%] {evt.stage}: {evt.message}",
                "Solafune Change Analyzer",
                Qgis.Info,
            )

        try:
            self.result = core_pipeline.run_pipeline(
                self._request,
                progress_callback=_on_progress,
                cancellation_token=_TokenAdapter(self),
            )
            return True
        except core_errors.CancelledError:
            self.error_message = "Cancelled by user"
            return False
        except core_errors.SolafuneChangeError as exc:
            self.error_message = exc.user_message
            logger.error("Analysis failed: %s", exc.user_message)
            return False
        except Exception as exc:  # noqa: BLE001 - last-resort: never crash QGIS
            self.error_message = f"Unexpected error: {exc}"
            logger.error("Unexpected error in analysis task:\n%s", traceback.format_exc())
            return False

    def cancel(self) -> None:  # noqa: D102 - QgsTask API
        QgsMessageLog.logMessage(
            "Cancellation requested by user", "Solafune Change Analyzer", Qgis.Info
        )
        super().cancel()
