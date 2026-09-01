"""GeoPackage (OGC, SQLite-based) output database.

GeoPackage is used as the single results database because it is itself a
plain SQLite file with OGC-standard geometry columns and spatial indexes —
no server process is required to open or query it, which matters for a
reviewer inspecting this repository. ``change_features`` and ``spatial_grid``
store real geometry columns (written via GeoPandas/pyogrio, not WKT text
columns); ``run_metadata`` and ``quality_checks`` are plain non-spatial
tables added into the same file with a direct ``sqlite3`` connection, since a
GeoPackage is simply a SQLite database with extra conventions.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd

from .atomic import atomic_output
from .errors import DatabaseWriteError

logger = logging.getLogger(__name__)

RUN_METADATA_COLUMNS = (
    "run_id",
    "run_timestamp",
    "before_folder",
    "after_folder",
    "before_date",
    "after_date",
    "aoi_path",
    "input_checksum_before",
    "input_checksum_after",
    "crs",
    "pixel_size_m",
    "method",
    "normalization",
    "threshold_method",
    "threshold_value",
    "min_area_m2",
    "spatial_statistics_enabled",
    "spatial_grid_size_m",
    "spatial_ml_enabled",
    "package_version",
    "random_seed",
    "output_paths_json",
)

QUALITY_CHECK_COLUMNS = ("run_id", "check_name", "severity", "message", "context_json")


def write_geopackage(
    gpkg_path: Path,
    change_features: gpd.GeoDataFrame,
    spatial_grid: gpd.GeoDataFrame | None,
    run_metadata: dict[str, Any],
    quality_checks: list[dict[str, Any]],
) -> None:
    """Write/replace the four required layers/tables in one GeoPackage file."""
    gpkg_path = Path(gpkg_path)

    with atomic_output(gpkg_path) as tmp_path:
        try:
            change_features.to_file(tmp_path, layer="change_features", driver="GPKG")
            if spatial_grid is not None and not spatial_grid.empty:
                spatial_grid.to_file(tmp_path, layer="spatial_grid", driver="GPKG")
        except Exception as exc:  # noqa: BLE001
            raise DatabaseWriteError(
                f"Failed writing spatial layers to GeoPackage: {gpkg_path}", detail=str(exc)
            ) from exc

        try:
            conn = sqlite3.connect(str(tmp_path))
            try:
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS run_metadata ({', '.join(c + ' TEXT' for c in RUN_METADATA_COLUMNS)})"
                )
                row = [_stringify(run_metadata.get(c)) for c in RUN_METADATA_COLUMNS]
                placeholders = ", ".join("?" for _ in RUN_METADATA_COLUMNS)
                conn.execute(
                    f"INSERT INTO run_metadata ({', '.join(RUN_METADATA_COLUMNS)}) VALUES ({placeholders})",
                    row,
                )

                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS quality_checks (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    f"{', '.join(c + ' TEXT' for c in QUALITY_CHECK_COLUMNS)})"
                )
                for qc in quality_checks:
                    values = [_stringify(qc.get(c)) for c in QUALITY_CHECK_COLUMNS]
                    placeholders = ", ".join("?" for _ in QUALITY_CHECK_COLUMNS)
                    conn.execute(
                        f"INSERT INTO quality_checks ({', '.join(QUALITY_CHECK_COLUMNS)}) VALUES ({placeholders})",
                        values,
                    )

                # Register the two non-spatial tables in gpkg_contents as GeoPackage
                # "attributes" tables (OGC GeoPackage spec, clause 1.3.2) so
                # spec-conformant readers (incl. QGIS's Browser panel) list them
                # alongside the spatial layers instead of hiding them.
                for table in ("run_metadata", "quality_checks"):
                    conn.execute(
                        "INSERT OR REPLACE INTO gpkg_contents (table_name, data_type, identifier) VALUES (?, 'attributes', ?)",
                        (table, table),
                    )
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise DatabaseWriteError(
                f"Failed writing metadata tables to GeoPackage: {gpkg_path}", detail=str(exc)
            ) from exc

    logger.info("Wrote GeoPackage: %s", gpkg_path)


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


@dataclass
class DatabaseSummary:
    total_change_features: int
    total_change_area_m2: float
    largest_features: list[dict[str, Any]]
    hotspot_95_intersection_count: int
    top_anomaly_features: list[dict[str, Any]]


def run_verification_queries(gpkg_path: Path) -> DatabaseSummary:
    """Run the sample verification queries against a written GeoPackage (read-back check)."""
    conn = sqlite3.connect(str(gpkg_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), COALESCE(SUM(area_m2), 0) FROM change_features")
        total_count, total_area = cur.fetchone()

        cur.execute(
            "SELECT id, area_m2, mean_change, confidence FROM change_features ORDER BY area_m2 DESC LIMIT 10"
        )
        largest = [
            {"id": r[0], "area_m2": r[1], "mean_change": r[2], "confidence": r[3]}
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT COUNT(*) FROM change_features WHERE hotspot_class IN ('hot_95','hot_99')"
        )
        hotspot_count = cur.fetchone()[0]

        cur.execute(
            "SELECT id, ml_anomaly_score, area_m2 FROM change_features "
            "WHERE ml_anomaly_score IS NOT NULL ORDER BY ml_anomaly_score DESC LIMIT 10"
        )
        top_anomaly = [
            {"id": r[0], "ml_anomaly_score": r[1], "area_m2": r[2]} for r in cur.fetchall()
        ]

        return DatabaseSummary(
            total_change_features=total_count,
            total_change_area_m2=float(total_area),
            largest_features=largest,
            hotspot_95_intersection_count=hotspot_count,
            top_anomaly_features=top_anomaly,
        )
    finally:
        conn.close()
