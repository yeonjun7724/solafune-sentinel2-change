"""Plugin lifecycle: toolbar/menu registration, dock widget, Processing provider."""

from __future__ import annotations

import os

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

PLUGIN_NAME = "Solafune Change Analyzer"


class SolafuneChangeAnalyzerPlugin:
    def __init__(self, iface) -> None:
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self._action: QAction | None = None
        self._dock = None
        self._controller = None
        self._provider = None

    # ------------------------------------------------------------------ lifecycle
    def initGui(self) -> None:  # noqa: N802 - QGIS API
        icon = QIcon(os.path.join(self.plugin_dir, "icons", "solafune_change.svg"))
        self._action = QAction(icon, PLUGIN_NAME, self.iface.mainWindow())
        self._action.setToolTip(
            "Sentinel-2 change detection with spatial statistics and experimental spatial ML"
        )
        self._action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self._action)
        self.iface.addPluginToMenu(PLUGIN_NAME, self._action)

        try:
            from .processing.provider import SolafuneGeospatialProvider

            self._provider = SolafuneGeospatialProvider()
            QgsApplication.processingRegistry().addProvider(self._provider)
        except Exception:  # noqa: BLE001 - Processing registration is best-effort
            self._provider = None

    def run(self) -> None:  # noqa: D102 - QGIS API
        if self._dock is None:
            from .controller import Controller
            from .dock_widget import SolafuneChangeDockWidget

            self._dock = SolafuneChangeDockWidget(self.iface.mainWindow())
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self._dock)
            self._controller = Controller(self.iface, self._dock)
        self._dock.show()
        self._dock.raise_()

    def unload(self) -> None:  # noqa: N802 - QGIS API
        if self._controller is not None:
            self._controller.shutdown()
            self._controller = None
        if self._dock is not None:
            self.iface.removeDockWidget(self._dock)
            self._dock.deleteLater()
            self._dock = None
        if self._action is not None:
            self.iface.removePluginMenu(PLUGIN_NAME, self._action)
            self.iface.removeToolBarIcon(self._action)
            self._action.deleteLater()
            self._action = None
        if self._provider is not None:
            QgsApplication.processingRegistry().removeProvider(self._provider)
            self._provider = None
