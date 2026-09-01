"""Resolves and lazily imports the shared ``solafune_change`` core engine.

Import order:

1. An already-installed ``solafune_change`` on ``sys.path`` (e.g. the user's
   project ``.venv`` was added to QGIS's Python path, or they ``pip
   install``ed the package into QGIS's own environment).
2. The vendored copy under ``vendor/solafune_change`` that
   ``scripts/build_qgis_plugin.py`` copies in at build time (release ZIPs
   only -- the copy does not exist in the source tree, see vendor/README).

Nothing here imports ``qgis`` or ``PyQt`` -- this module (and everything it
returns) is safe to import in a plain Python test environment.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

_PLUGIN_DIR = Path(__file__).resolve().parent
_VENDOR_DIR = _PLUGIN_DIR / "vendor"


class CoreImportError(RuntimeError):
    """Raised when the ``solafune_change`` core package cannot be imported."""


def _try_import(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def import_core() -> ModuleType:
    """Return the ``solafune_change`` package module, installed or vendored.

    Raises :class:`CoreImportError` with an actionable message if neither is
    available or importable (most commonly: a required third-party
    dependency such as ``rasterio`` is missing -- see ``dependency_check.py``
    for a friendlier, per-package diagnosis before calling this).
    """
    mod = _try_import("solafune_change")
    if mod is not None:
        return mod

    vendored_src = _VENDOR_DIR / "solafune_change"
    if vendored_src.exists():
        vendor_path_str = str(_VENDOR_DIR)
        if vendor_path_str not in sys.path:
            sys.path.insert(0, vendor_path_str)
        mod = _try_import("solafune_change")
        if mod is not None:
            return mod

    raise CoreImportError(
        "Could not import the 'solafune_change' core engine. Either install it "
        "into QGIS's Python environment (pip install solafune-change), or use "
        "'External environment' execution mode and point it at a Python "
        "interpreter that has it installed (see the Dependencies panel)."
    )


def core_source_kind() -> str:
    """Return 'installed', 'vendored', or 'unavailable' -- for diagnostics/UI display."""
    if "solafune_change" in sys.modules:
        mod = sys.modules["solafune_change"]
    else:
        mod = _try_import("solafune_change")
    if mod is None:
        vendored_src = _VENDOR_DIR / "solafune_change"
        return "vendored (not yet importable)" if vendored_src.exists() else "unavailable"
    mod_path = Path(getattr(mod, "__file__", "")).resolve()
    return "vendored" if _VENDOR_DIR in mod_path.parents else "installed"
