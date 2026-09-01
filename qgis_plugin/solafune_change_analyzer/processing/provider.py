from __future__ import annotations

import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon


class SolafuneGeospatialProvider(QgsProcessingProvider):
    def id(self) -> str:  # noqa: A003 - QGIS API
        return "solafune_geospatial_analytics"

    def name(self) -> str:
        return "Solafune Geospatial Analytics"

    def icon(self) -> QIcon:
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "icons", "solafune_change.svg"
        )
        return QIcon(icon_path) if os.path.exists(icon_path) else super().icon()

    def loadAlgorithms(self) -> None:  # noqa: N802 - QGIS API
        from .change_algorithm import Sentinel2ChangeAnalysisAlgorithm

        self.addAlgorithm(Sentinel2ChangeAnalysisAlgorithm())
