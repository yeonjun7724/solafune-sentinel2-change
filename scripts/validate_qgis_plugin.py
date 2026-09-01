#!/usr/bin/env python
"""Standalone structural/static validation of a built QGIS plugin ZIP.

Checks: ZIP layout, required files, classFactory presence, metadata.txt
required fields, no bare PyQt5/PyQt6 imports (must go through qgis.PyQt), no
leftover TODO/pass-only placeholder handlers, and that every .py file
compiles.

Usage:
    python scripts/validate_qgis_plugin.py outputs/qgis/solafune_change_analyzer.zip
"""

from __future__ import annotations

import ast
import configparser
import py_compile
import re
import sys
import tempfile
import zipfile
from pathlib import Path

REQUIRED_METADATA_FIELDS = (
    "name",
    "qgisMinimumVersion",
    "description",
    "version",
    "author",
    "email",
)
FORBIDDEN_IMPORT_RE = re.compile(r"^\s*(from|import)\s+PyQt[56]\b", re.MULTILINE)


def _error(errors: list[str], message: str) -> None:
    errors.append(message)
    print(f"  FAIL: {message}")


def validate(zip_path: Path) -> list[str]:
    errors: list[str] = []
    if not zip_path.exists():
        return [f"ZIP not found: {zip_path}"]

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        top_levels = {n.split("/")[0] for n in names if n.strip("/")}
        print(f"Top-level entries: {top_levels}")
        if len(top_levels) != 1:
            _error(errors, f"Expected exactly one top-level folder, found {top_levels}")
            return errors
        plugin_dir = next(iter(top_levels))

        for required in ("__init__.py", "metadata.txt", "plugin.py"):
            if f"{plugin_dir}/{required}" not in names:
                _error(errors, f"Missing required file: {plugin_dir}/{required}")

        init_src = zf.read(f"{plugin_dir}/__init__.py").decode("utf-8")
        if "classFactory" not in init_src:
            _error(errors, "__init__.py does not define classFactory")

        metadata_raw = zf.read(f"{plugin_dir}/metadata.txt").decode("utf-8")
        parser = configparser.ConfigParser()
        parser.read_string(metadata_raw)
        if "general" not in parser:
            _error(errors, "metadata.txt missing [general] section")
        else:
            for field in REQUIRED_METADATA_FIELDS:
                value = parser["general"].get(field, "").strip()
                if not value:
                    _error(errors, f"metadata.txt [general] missing/empty required field: {field}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zf.extractall(tmp_path)
            for py_file in sorted((tmp_path / plugin_dir).rglob("*.py")):
                rel = py_file.relative_to(tmp_path)
                try:
                    py_compile.compile(str(py_file), doraise=True)
                except py_compile.PyCompileError as exc:
                    _error(errors, f"{rel}: compile error: {exc}")

                source = py_file.read_text(encoding="utf-8")
                if "vendor" not in py_file.parts and FORBIDDEN_IMPORT_RE.search(source):
                    _error(errors, f"{rel}: imports PyQt5/PyQt6 directly (must use qgis.PyQt)")

                if "vendor" not in py_file.parts:
                    tree = ast.parse(source, filename=str(py_file))
                    for node in ast.walk(tree):
                        if (
                            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and len(node.body) == 1
                            and isinstance(node.body[0], ast.Pass)
                        ):
                            _error(
                                errors, f"{rel}: function '{node.name}' has an empty pass-only body"
                            )

    return errors


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    zip_path = Path(sys.argv[1])
    print(f"Validating {zip_path} ...")
    errors = validate(zip_path)
    if errors:
        print(f"\n{len(errors)} problem(s) found.")
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
