.PHONY: setup validate run test lint format plugin plugin-resources plugin-test plugin-build plugin-validate plugin-clean clean-derived

VENV := .venv
PYTHON := $(VENV)/Scripts/python

setup:
	python -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements-dev.txt
	$(PYTHON) -m pip install -e .
	$(PYTHON) -m pre_commit install

validate:
	$(PYTHON) -m solafune_change validate --config config/default.yaml

run:
	$(PYTHON) -m solafune_change all --config config/default.yaml

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m black --check src/ tests/ scripts/ qgis_plugin/solafune_change_analyzer --exclude vendor

format:
	$(PYTHON) -m ruff check . --fix
	$(PYTHON) -m black src/ tests/ scripts/ qgis_plugin/solafune_change_analyzer --exclude vendor

# --- QGIS plugin ---

plugin-resources:
	@echo "No compiled Qt resources are used (icons are loaded from disk by path); nothing to build."

plugin-test:
	$(PYTHON) -m pytest tests/test_qgis_plugin_structure.py -v

plugin-build:
	$(PYTHON) scripts/build_qgis_plugin.py

plugin-validate:
	$(PYTHON) scripts/validate_qgis_plugin.py outputs/qgis/solafune_change_analyzer.zip

plugin: plugin-test plugin-build plugin-validate

plugin-clean:
	rm -rf build/qgis_plugin_staging
	rm -rf qgis_plugin/solafune_change_analyzer/vendor/solafune_change
	rm -f outputs/qgis/solafune_change_analyzer.zip outputs/qgis/solafune_change_analyzer.zip.sha256

# Removes only pipeline-generated outputs. Never touches inputs/.
clean-derived:
	rm -rf data/processed/*.tif
	rm -rf outputs/figures/*.png outputs/maps/*.html outputs/maps/*.gpkg
	rm -rf outputs/database/*.gpkg outputs/statistics/*.json outputs/statistics/*.csv
	rm -rf outputs/qgis/styles/*.qml
	rm -f outputs/summary.json outputs/run_manifest.json outputs/quality_report.json outputs/report.md
	@echo "Removed generated outputs under data/processed/ and outputs/. inputs/ was not touched."
