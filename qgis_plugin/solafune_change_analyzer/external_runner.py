"""External execution mode: runs the CLI in a separate Python interpreter via QProcess.

Used when the embedded QGIS Python interpreter is missing core dependencies
(the common case for an OSGeo4W/Windows QGIS install, which does not ship
rasterio/scikit-learn/libpysal by default). ``QProcess`` is asynchronous I/O
driven by the Qt event loop, so running it on the main thread does not block
the UI -- no worker thread is needed here, unlike :mod:`task` (CPU-bound
Python code, which *does* need a thread).

Security: the interpreter path and every argument are passed as a list to
``QProcess.start()`` -- never as a single shell string -- so there is no
shell-injection surface from user-supplied paths.
"""

from __future__ import annotations

import json
from pathlib import Path

from qgis.PyQt.QtCore import QObject, QProcess, pyqtSignal


class ExternalAnalysisRunner(QObject):
    """Wraps ``python -m solafune_change all --config <cfg> --json-progress``."""

    progress = pyqtSignal(str, str, float, str)  # stage, message, percent, severity
    finished = pyqtSignal(bool, str)  # success, manifest_path_or_error_message

    def __init__(self, python_path: str, config_path: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._python_path = python_path
        self._config_path = config_path
        self._process: QProcess | None = None
        self._manifest_path: str | None = None
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._cancelled = False

    def start(self) -> None:
        self._process = QProcess(self)
        self._process.setProgram(self._python_path)
        self._process.setArguments(
            ["-m", "solafune_change", "all", "--config", self._config_path, "--json-progress"]
        )
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)
        self._process.start()

    def cancel(self) -> None:
        self._cancelled = True
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            self._process.terminate()
            if not self._process.waitForFinished(3000):
                self._process.kill()

    def _on_stdout(self) -> None:
        if self._process is None:
            return
        self._stdout_buffer += bytes(self._process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            ptype = payload.get("type", "info")
            if ptype == "result":
                self._manifest_path = payload.get("manifest")
            elif ptype in ("info", "warning", "error"):
                self.progress.emit(
                    payload.get("stage", ""),
                    payload.get("message", ""),
                    float(payload.get("percent", 0.0)),
                    ptype,
                )

    def _on_stderr(self) -> None:
        if self._process is None:
            return
        self._stderr_buffer += bytes(self._process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        )

    def _on_finished(
        self, exit_code: int, exit_status
    ) -> None:  # noqa: ARG002 - Qt signal signature
        if self._cancelled:
            self.finished.emit(False, "Cancelled by user")
            return
        if exit_code == 0 and self._manifest_path and Path(self._manifest_path).exists():
            self.finished.emit(True, self._manifest_path)
        else:
            tail = self._stderr_buffer[-2000:] if self._stderr_buffer else "(no stderr captured)"
            self.finished.emit(
                False, f"External process exited with code {exit_code}. Details: {tail}"
            )

    def _on_error(self, error) -> None:  # noqa: ARG002 - Qt signal signature
        if not self._cancelled:
            self.finished.emit(False, f"Could not start external interpreter: {self._python_path}")
