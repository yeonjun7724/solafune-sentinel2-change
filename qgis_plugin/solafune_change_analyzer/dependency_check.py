"""Per-feature dependency diagnostics for the current Python interpreter.

Deliberately has zero ``qgis``/``PyQt`` imports so it can run against *any*
interpreter path (the embedded QGIS one, or an external project ``.venv``)
via a small subprocess probe, and so it is unit-testable outside QGIS.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from dataclasses import asdict, dataclass

# name -> (import name, feature it gates)
_REQUIRED_BASIC = {
    "numpy": "numpy",
    "rasterio": "rasterio",
    "geopandas": "geopandas",
    "shapely": "shapely",
    "pyproj": "pyproj",
    "scipy": "scipy",
    "skimage": "scikit-image",
    "yaml": "PyYAML",
}
_REQUIRED_STATS = {"libpysal": "libpysal", "esda": "esda"}
_OPTIONAL_ML = {"sklearn": "scikit-learn", "hdbscan": "hdbscan (optional, for HDBSCAN clustering)"}
_OPTIONAL_VIZ = {"matplotlib": "matplotlib", "folium": "folium"}


@dataclass
class DependencyStatus:
    name: str
    required_for: str
    available: bool
    version: str | None
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def _check_one(import_name: str, display_name: str, required_for: str) -> DependencyStatus:
    try:
        mod = importlib.import_module(import_name)
        version = getattr(mod, "__version__", "unknown")
        return DependencyStatus(
            display_name, required_for, True, version, f"{display_name} {version} available"
        )
    except ImportError as exc:
        return DependencyStatus(
            display_name, required_for, False, None, f"Missing: pip install {display_name} ({exc})"
        )


def check_current_interpreter() -> list[DependencyStatus]:
    """Check all tracked dependencies against *this* running interpreter."""
    results: list[DependencyStatus] = []
    for import_name, display in _REQUIRED_BASIC.items():
        results.append(_check_one(import_name, display, "basic change detection"))
    for import_name, display in _REQUIRED_STATS.items():
        results.append(_check_one(import_name, display, "spatial statistics"))
    for import_name, display in _OPTIONAL_ML.items():
        results.append(_check_one(import_name, display, "experimental spatial ML"))
    for import_name, display in _OPTIONAL_VIZ.items():
        results.append(_check_one(import_name, display, "visualization"))
    return results


_PROBE_SCRIPT = """
import importlib, json, sys
names = {names!r}
out = {{}}
for n in names:
    try:
        m = importlib.import_module(n)
        out[n] = getattr(m, "__version__", "unknown")
    except ImportError:
        out[n] = None
print(json.dumps(out))
"""


def check_external_interpreter(
    python_path: str, timeout: float = 15.0
) -> list[DependencyStatus] | None:
    """Probe a *different* Python interpreter (e.g. a project .venv) via subprocess.

    Returns ``None`` if the interpreter itself could not be run at all
    (bad path, not executable, timeout).
    """
    all_names = {
        **_REQUIRED_BASIC,
        **_REQUIRED_STATS,
        **_OPTIONAL_ML,
        **_OPTIONAL_VIZ,
        "solafune_change": "solafune_change",
    }
    script = _PROBE_SCRIPT.format(names=list(all_names.keys()))
    try:
        proc = subprocess.run(
            [python_path, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        versions: dict[str, str | None] = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return None

    required_for = {
        **{k: "basic change detection" for k in _REQUIRED_BASIC},
        **{k: "spatial statistics" for k in _REQUIRED_STATS},
        **{k: "experimental spatial ML" for k in _OPTIONAL_ML},
        **{k: "visualization" for k in _OPTIONAL_VIZ},
        "solafune_change": "core engine",
    }
    results = []
    for name, display in all_names.items():
        version = versions.get(name)
        available = version is not None
        msg = f"{display} {version} available" if available else f"Missing: pip install {display}"
        results.append(DependencyStatus(display, required_for[name], available, version, msg))
    return results


def embedded_mode_available(statuses: list[DependencyStatus] | None = None) -> bool:
    """True if the basic-change-detection dependencies are importable right now."""
    statuses = statuses or check_current_interpreter()
    basic_names = set(_REQUIRED_BASIC.values())
    return all(s.available for s in statuses if s.name in basic_names)


def feature_readiness(statuses: list[DependencyStatus]) -> dict[str, bool]:
    by_feature: dict[str, list[bool]] = {}
    for s in statuses:
        by_feature.setdefault(s.required_for, []).append(s.available)
    return {feature: all(flags) for feature, flags in by_feature.items()}


if __name__ == "__main__":
    for status in check_current_interpreter():
        print(status.to_dict())
