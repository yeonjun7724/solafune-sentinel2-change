#!/usr/bin/env python
"""Builds an installable QGIS plugin ZIP from qgis_plugin/solafune_change_analyzer.

Steps: validate source -> vendor a fresh copy of src/solafune_change into
vendor/solafune_change -> stage a clean copy (excluding dev/test/cache files)
-> py_compile every staged .py file -> zip with the correct top-level folder
-> reopen the ZIP and check its structure -> write a sha256 checksum file.

Usage:
    python scripts/build_qgis_plugin.py
"""

from __future__ import annotations

import compileall
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_NAME = "solafune_change_analyzer"
PLUGIN_SRC = REPO_ROOT / "qgis_plugin" / PLUGIN_NAME
CORE_SRC = REPO_ROOT / "src" / "solafune_change"
OUTPUT_DIR = REPO_ROOT / "outputs" / "qgis"
ZIP_PATH = OUTPUT_DIR / f"{PLUGIN_NAME}.zip"

EXCLUDE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
EXCLUDE_TOP_LEVEL = {"vendor"}  # handled separately: freshly re-vendored, not copied verbatim


def _fail(message: str) -> None:
    print(f"BUILD FAILED: {message}", file=sys.stderr)
    sys.exit(1)


def validate_source() -> None:
    if not PLUGIN_SRC.exists():
        _fail(f"Plugin source not found: {PLUGIN_SRC}")
    for required in ("__init__.py", "metadata.txt", "plugin.py"):
        if not (PLUGIN_SRC / required).exists():
            _fail(f"Missing required plugin file: {required}")
    if not CORE_SRC.exists():
        _fail(f"Core source not found: {CORE_SRC}")


def vendor_core() -> None:
    vendor_dst = PLUGIN_SRC / "vendor" / "solafune_change"
    if vendor_dst.exists():
        shutil.rmtree(vendor_dst)
    shutil.copytree(CORE_SRC, vendor_dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"Vendored core: {CORE_SRC} -> {vendor_dst}")


def stage_plugin(staging_root: Path) -> Path:
    dest = staging_root / PLUGIN_NAME
    if dest.exists():
        shutil.rmtree(dest)

    def _ignore(directory: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            path = Path(directory) / name
            if name in EXCLUDE_DIR_NAMES:
                ignored.add(name)
            elif path.is_file() and path.suffix in EXCLUDE_SUFFIXES:
                ignored.add(name)
        return ignored

    shutil.copytree(PLUGIN_SRC, dest, ignore=_ignore)
    return dest


def compile_check(staged_dir: Path) -> None:
    ok = compileall.compile_dir(str(staged_dir), quiet=1, force=True)
    if not ok:
        _fail("One or more staged .py files failed to compile (syntax error).")
    print("All staged Python files compiled successfully.")


def build_zip(staged_dir: Path) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(staged_dir.rglob("*")):
            if path.is_dir():
                continue
            if "__pycache__" in path.parts:
                continue
            arcname = Path(PLUGIN_NAME) / path.relative_to(staged_dir)
            zf.write(path, arcname)
    print(f"Wrote ZIP: {ZIP_PATH}")


def validate_zip_structure() -> None:
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = zf.namelist()
        top_levels = {n.split("/")[0] for n in names}
        if top_levels != {PLUGIN_NAME}:
            _fail(
                f"ZIP must contain exactly one top-level folder '{PLUGIN_NAME}/', found: {top_levels}"
            )
        required = {
            f"{PLUGIN_NAME}/__init__.py",
            f"{PLUGIN_NAME}/metadata.txt",
            f"{PLUGIN_NAME}/plugin.py",
        }
        missing = required - set(names)
        if missing:
            _fail(f"ZIP is missing required files: {missing}")
        init_content = zf.read(f"{PLUGIN_NAME}/__init__.py").decode("utf-8")
        if "classFactory" not in init_content:
            _fail("__init__.py does not define classFactory")
        vendored_core_init = f"{PLUGIN_NAME}/vendor/solafune_change/__init__.py"
        if vendored_core_init not in names:
            _fail("Vendored core package is missing from the ZIP")
    print(
        "ZIP structure validated: single top-level plugin folder, required files present, classFactory found, core vendored."
    )


def write_checksum() -> None:
    digest = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
    checksum_path = ZIP_PATH.with_suffix(ZIP_PATH.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {ZIP_PATH.name}\n", encoding="utf-8")
    print(f"SHA-256: {digest}")
    print(f"Wrote checksum: {checksum_path}")


def main() -> None:
    validate_source()
    vendor_core()
    staging_root = REPO_ROOT / "build" / "qgis_plugin_staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staged_dir = stage_plugin(staging_root)
    compile_check(staged_dir)
    build_zip(staged_dir)
    validate_zip_structure()
    write_checksum()
    shutil.rmtree(staging_root, ignore_errors=True)
    print("\nBuild complete.")


if __name__ == "__main__":
    main()
