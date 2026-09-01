"""QGIS-independent structural checks on the plugin source and the built ZIP.

These run in a plain Python environment (no ``qgis``/PyQt installed) and
verify: the core engine never imports qgis/PyQt (so it stays usable outside
QGIS), the plugin source has no leftover placeholders, and metadata.txt is
well-formed. Real QGIS runtime behavior (classFactory/initGui/Processing
registration) was verified manually against QGIS 3.44 — see
docs/QGIS_PLUGIN_TEST_CHECKLIST.md for that record and instructions to repeat it.
"""

from __future__ import annotations

import ast
import configparser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_SRC = REPO_ROOT / "src" / "solafune_change"
PLUGIN_SRC = REPO_ROOT / "qgis_plugin" / "solafune_change_analyzer"


def test_core_engine_never_imports_qgis_or_pyqt():
    offenders = []
    for py_file in CORE_SRC.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name == "qgis" or name.startswith("qgis.") or name.startswith("PyQt"):
                    offenders.append(f"{py_file.relative_to(REPO_ROOT)}: imports '{name}'")
    assert not offenders, "core engine must stay importable without QGIS:\n" + "\n".join(offenders)


def test_plugin_qt_modules_only_use_qgis_pyqt_shim():
    offenders = []
    for py_file in PLUGIN_SRC.rglob("*.py"):
        if "vendor" in py_file.parts:
            continue
        source = py_file.read_text(encoding="utf-8")
        if (
            "import PyQt5" in source
            or "import PyQt6" in source
            or "from PyQt5" in source
            or "from PyQt6" in source
        ):
            offenders.append(str(py_file.relative_to(REPO_ROOT)))
    assert not offenders, f"plugin files must import Qt via qgis.PyQt, not directly: {offenders}"


def test_metadata_txt_has_required_fields():
    parser = configparser.ConfigParser()
    parser.read(PLUGIN_SRC / "metadata.txt", encoding="utf-8")
    assert "general" in parser
    for field in ("name", "qgisMinimumVersion", "description", "version", "author", "email"):
        assert parser["general"].get(field, "").strip(), f"metadata.txt missing field: {field}"


def test_init_defines_class_factory():
    source = (PLUGIN_SRC / "__init__.py").read_text(encoding="utf-8")
    assert "def classFactory" in source


def test_plugin_source_files_compile():
    import py_compile

    for py_file in PLUGIN_SRC.rglob("*.py"):
        if "vendor" in py_file.parts:
            continue
        py_compile.compile(str(py_file), doraise=True)


def test_no_pass_only_placeholder_handlers():
    offenders = []
    for py_file in PLUGIN_SRC.rglob("*.py"):
        if "vendor" in py_file.parts:
            continue
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and len(node.body) == 1
                and isinstance(node.body[0], ast.Pass)
            ):
                offenders.append(f"{py_file.relative_to(REPO_ROOT)}: {node.name}")
    assert not offenders, f"pass-only placeholder handlers found: {offenders}"


def test_built_zip_structure_if_present():
    zip_path = REPO_ROOT / "outputs" / "qgis" / "solafune_change_analyzer.zip"
    if not zip_path.exists():
        pytest.skip("plugin ZIP not built yet; run scripts/build_qgis_plugin.py")
    import zipfile

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        top_levels = {n.split("/")[0] for n in names if n.strip("/")}
        assert top_levels == {"solafune_change_analyzer"}
        assert "solafune_change_analyzer/__init__.py" in names
        assert "solafune_change_analyzer/metadata.txt" in names
        assert "solafune_change_analyzer/vendor/solafune_change/__init__.py" in names
