"""Exception hierarchy shared by the CLI, the core pipeline and the QGIS plugin.

The QGIS plugin (and the CLI) rely on this hierarchy to decide what a user
should see (a short, actionable message) versus what only belongs in the log
file (a full traceback). Every exception carries a ``user_message`` that is
safe to show directly in a dialog or message bar.
"""

from __future__ import annotations


class SolafuneChangeError(Exception):
    """Base class for all errors raised by the solafune_change core engine."""

    def __init__(self, user_message: str, *, detail: str | None = None) -> None:
        super().__init__(user_message if detail is None else f"{user_message} ({detail})")
        self.user_message = user_message
        self.detail = detail


class ConfigurationError(SolafuneChangeError):
    """Raised when configuration values are missing, malformed or inconsistent."""


class InputDiscoveryError(SolafuneChangeError):
    """Raised when required band files cannot be uniquely located on disk."""


class RasterAlignmentError(SolafuneChangeError):
    """Raised when rasters cannot be validated or aligned to a common grid."""


class AnalysisError(SolafuneChangeError):
    """Raised when a change-detection, statistics or ML step fails at runtime."""


class DatabaseWriteError(SolafuneChangeError):
    """Raised when the GeoPackage/SQLite output cannot be written or read back."""


class DependencyError(SolafuneChangeError):
    """Raised when an optional Python dependency required for a feature is missing."""


class CancelledError(SolafuneChangeError):
    """Raised when a run is stopped by a user-triggered cancellation token."""

    def __init__(self, stage: str) -> None:
        super().__init__(f"Analysis cancelled during stage '{stage}'.")
        self.stage = stage
