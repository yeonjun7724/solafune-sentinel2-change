from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point, Polygon

from solafune_change.database import run_verification_queries, write_geopackage


def _dummy_features():
    poly1 = Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])
    poly2 = Polygon([(20, 20), (20, 30), (30, 30), (30, 20)])
    return gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "date_before": ["d1", "d1"],
            "date_after": ["d2", "d2"],
            "area_m2": [100.0, 100.0],
            "mean_change": [5.0, 8.0],
            "confidence": [0.5, 0.9],
            "hotspot_class": ["not_significant", "hot_95"],
            "ml_anomaly_score": [0.1, 0.9],
        },
        geometry=[poly1, poly2],
        crs="EPSG:32735",
    )


def test_write_and_readback_geometry(tmp_path):
    features = _dummy_features()
    grid = gpd.GeoDataFrame({"grid_id": [1]}, geometry=[Point(5, 5).buffer(2)], crs="EPSG:32735")
    gpkg_path = tmp_path / "test.gpkg"

    write_geopackage(
        gpkg_path,
        features,
        grid,
        run_metadata={"run_id": "r1", "crs": "EPSG:32735"},
        quality_checks=[{"run_id": "r1", "check_name": "c1", "severity": "info", "message": "ok"}],
    )
    assert gpkg_path.exists()

    read_back = gpd.read_file(gpkg_path, layer="change_features")
    assert len(read_back) == 2
    assert read_back.geometry.iloc[0].geom_type in ("Polygon", "MultiPolygon")
    assert read_back.crs.to_epsg() == 32735


def test_run_verification_queries(tmp_path):
    features = _dummy_features()
    gpkg_path = tmp_path / "test.gpkg"
    write_geopackage(gpkg_path, features, None, run_metadata={"run_id": "r1"}, quality_checks=[])

    summary = run_verification_queries(gpkg_path)
    assert summary.total_change_features == 2
    assert summary.total_change_area_m2 == 200.0
    assert summary.hotspot_95_intersection_count == 1
    assert len(summary.top_anomaly_features) == 2
