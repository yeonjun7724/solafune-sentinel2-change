"""QSettings persistence and YAML import/export for the plugin's dock widget state.

Deliberately stores/reads plain Python types only (str/float/int/bool) --
no PyQt objects and no ``solafune_change`` dataclasses -- so this module has
no hard dependency on either being importable, and the same settings dict
round-trips through the CLI's YAML schema unmodified.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qgis.PyQt.QtCore import QSettings

NAMESPACE = "solafune_change_analyzer"

DEFAULTS: dict[str, Any] = {
    "paths/before_folder": "",
    "paths/after_folder": "",
    "paths/aoi": "",
    "paths/output_dir": "",
    "run/label": "run",
    "change/method": "both",
    "change/normalization": "robust_median_mad",
    "change/threshold_method": "otsu",
    "change/percentile": 95.0,
    "change/manual_threshold": 0.0,
    "change/morphology_enabled": True,
    "change/morphology_operation": "opening_then_closing",
    "change/morphology_kernel_size": 3,
    "change/fill_holes": False,
    "change/min_area_m2": 400.0,
    "stats/enabled": True,
    "stats/grid_size_m": 150.0,
    "stats/weights": "queen",
    "stats/knn_k": 8,
    "stats/permutations": 999,
    "stats/alpha": 0.05,
    "stats/fdr_correction": True,
    "ml/enabled": False,
    "ml/model": "isolation_forest",
    "ml/contamination": 0.1,
    "ml/dbscan_eps": 1.5,
    "ml/dbscan_min_samples": 5,
    "ml/use_coordinates": False,
    "output/write_stacks": True,
    "output/write_intermediate": True,
    "output/create_interactive_map": True,
    "output/create_qgis_styles": True,
    "output/load_results": True,
    "output/apply_styles": True,
    "output/zoom_to_results": True,
    "execution/external_python_path": "",
    "execution/mode": "auto",  # auto | embedded | external
    "run/random_seed": 42,
}


def _settings() -> QSettings:
    return QSettings()


def load_all() -> dict[str, Any]:
    s = _settings()
    s.beginGroup(NAMESPACE)
    values: dict[str, Any] = {}
    for key, default in DEFAULTS.items():
        raw = s.value(key, default)
        if isinstance(default, bool):
            values[key] = raw in (True, "true", "True", 1, "1")
        elif isinstance(default, float):
            values[key] = float(raw)
        elif isinstance(default, int):
            values[key] = int(raw)
        else:
            values[key] = str(raw)
    s.endGroup()
    return values


def save_all(values: dict[str, Any]) -> None:
    s = _settings()
    s.beginGroup(NAMESPACE)
    for key, value in values.items():
        s.setValue(key, value)
    s.endGroup()
    s.sync()


def restore_defaults() -> dict[str, Any]:
    save_all(DEFAULTS)
    return dict(DEFAULTS)


def export_yaml(values: dict[str, Any], path: str) -> None:
    import yaml

    # Always write an explicit, absolute processed_dir anchored to output_dir
    # (matching solafune_change.pipeline's own fallback convention:
    # output_dir.parent / "data" / "processed") rather than leaving it unset.
    # This YAML file is frequently a short-lived temp file (the QGIS plugin's
    # external-execution mode writes one per run under the OS temp
    # directory), and resolving a *relative* default against that temp
    # file's own location -- rather than against the real output directory --
    # previously sent output to a nonsensical path.
    output_dir = Path(values["paths/output_dir"])
    processed_dir = str(output_dir.parent / "data" / "processed")

    doc = {
        "paths": {
            "aoi": values["paths/aoi"],
            "before_folder": values["paths/before_folder"],
            "after_folder": values["paths/after_folder"],
            "output_dir": values["paths/output_dir"],
            "processed_dir": processed_dir,
        },
        "preprocessing": {
            "normalization": values["change/normalization"],
            "resampling": "bilinear",
            "reference_date": "before",
        },
        "change_detection": {
            "method": values["change/method"],
            "threshold_method": values["change/threshold_method"],
            "percentile": values["change/percentile"],
            "manual_threshold": values["change/manual_threshold"],
            "morphology": {
                "enabled": values["change/morphology_enabled"],
                "operation": values["change/morphology_operation"],
                "structure_size": values["change/morphology_kernel_size"],
                "fill_holes": values["change/fill_holes"],
            },
            "min_area_m2": values["change/min_area_m2"],
        },
        "spatial_statistics": {
            "enabled": values["stats/enabled"],
            "grid_size_m": values["stats/grid_size_m"],
            "weights": values["stats/weights"],
            "knn_k": values["stats/knn_k"],
            "permutations": values["stats/permutations"],
            "alpha": values["stats/alpha"],
            "fdr_correction": values["stats/fdr_correction"],
            "random_seed": values["run/random_seed"],
        },
        "spatial_ml": {
            "enabled": values["ml/enabled"],
            "model": values["ml/model"],
            "contamination": values["ml/contamination"],
            "clustering": {
                "algorithm": "dbscan",
                "eps": values["ml/dbscan_eps"],
                "min_samples": values["ml/dbscan_min_samples"],
            },
            "random_seed": values["run/random_seed"],
            "use_coordinates": values["ml/use_coordinates"],
        },
        "output": {
            "write_stacks": values["output/write_stacks"],
            "write_intermediate": values["output/write_intermediate"],
            "create_interactive_map": values["output/create_interactive_map"],
            "create_qgis_styles": values["output/create_qgis_styles"],
        },
        "run": {"random_seed": values["run/random_seed"]},
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False)


def import_yaml(path: str) -> dict[str, Any]:
    import yaml

    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}

    values = dict(DEFAULTS)
    p, prep, cd, ss, ml, out, run = (
        doc.get("paths", {}),
        doc.get("preprocessing", {}),
        doc.get("change_detection", {}),
        doc.get("spatial_statistics", {}),
        doc.get("spatial_ml", {}),
        doc.get("output", {}),
        doc.get("run", {}),
    )
    morph = cd.get("morphology", {})
    cluster = ml.get("clustering", {})

    values.update(
        {
            "paths/aoi": p.get("aoi", values["paths/aoi"]),
            "paths/before_folder": p.get("before_folder", values["paths/before_folder"]),
            "paths/after_folder": p.get("after_folder", values["paths/after_folder"]),
            "paths/output_dir": p.get("output_dir", values["paths/output_dir"]),
            "change/normalization": prep.get("normalization", values["change/normalization"]),
            "change/method": cd.get("method", values["change/method"]),
            "change/threshold_method": cd.get(
                "threshold_method", values["change/threshold_method"]
            ),
            "change/percentile": float(cd.get("percentile", values["change/percentile"])),
            "change/manual_threshold": float(cd.get("manual_threshold") or 0.0),
            "change/morphology_enabled": bool(
                morph.get("enabled", values["change/morphology_enabled"])
            ),
            "change/morphology_operation": morph.get(
                "operation", values["change/morphology_operation"]
            ),
            "change/morphology_kernel_size": int(
                morph.get("structure_size", values["change/morphology_kernel_size"])
            ),
            "change/fill_holes": bool(morph.get("fill_holes", values["change/fill_holes"])),
            "change/min_area_m2": float(cd.get("min_area_m2", values["change/min_area_m2"])),
            "stats/enabled": bool(ss.get("enabled", values["stats/enabled"])),
            "stats/grid_size_m": float(ss.get("grid_size_m", values["stats/grid_size_m"])),
            "stats/weights": ss.get("weights", values["stats/weights"]),
            "stats/permutations": int(ss.get("permutations", values["stats/permutations"])),
            "stats/alpha": float(ss.get("alpha", values["stats/alpha"])),
            "stats/fdr_correction": bool(ss.get("fdr_correction", values["stats/fdr_correction"])),
            "ml/enabled": bool(ml.get("enabled", values["ml/enabled"])),
            "ml/model": ml.get("model", values["ml/model"]),
            "ml/contamination": float(ml.get("contamination", values["ml/contamination"])),
            "ml/dbscan_eps": float(cluster.get("eps", values["ml/dbscan_eps"])),
            "ml/dbscan_min_samples": int(
                cluster.get("min_samples", values["ml/dbscan_min_samples"])
            ),
            "ml/use_coordinates": bool(ml.get("use_coordinates", values["ml/use_coordinates"])),
            "output/write_stacks": bool(out.get("write_stacks", values["output/write_stacks"])),
            "output/create_interactive_map": bool(
                out.get("create_interactive_map", values["output/create_interactive_map"])
            ),
            "output/create_qgis_styles": bool(
                out.get("create_qgis_styles", values["output/create_qgis_styles"])
            ),
            "run/random_seed": int(run.get("random_seed", values["run/random_seed"])),
        }
    )
    return values
