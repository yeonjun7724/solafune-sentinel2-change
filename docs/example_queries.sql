-- Example SQL queries against outputs/database/change_analysis.gpkg
-- (a GeoPackage is a plain SQLite file: open it with `sqlite3`, DB Browser
-- for SQLite, QGIS's DB Manager, or Python's sqlite3 module).
--
-- All queries below were run against a real pipeline output; see
-- report.md / summary.json for the actual numbers from the reference run.

-- 1. Total number of change objects and total change area
SELECT COUNT(*) AS n_features, SUM(area_m2) AS total_area_m2
FROM change_features;

-- 2. Top 10 change objects by area
SELECT id, area_m2, mean_change, confidence, hotspot_class, lisa_cluster
FROM change_features
ORDER BY area_m2 DESC
LIMIT 10;

-- 3. Change objects intersecting a 95%+ significance Gi* hotspot
SELECT id, area_m2, mean_change, gi_zscore, gi_pvalue, gi_qvalue, hotspot_class
FROM change_features
WHERE hotspot_class IN ('hot_95', 'hot_99')
ORDER BY gi_zscore DESC;

-- 4. Top 10 change objects by experimental ML anomaly score
-- (exploratory ranking only -- not a validated prediction, see report.md)
SELECT id, area_m2, ml_anomaly_score, ml_cluster_id, confidence
FROM change_features
WHERE ml_anomaly_score IS NOT NULL
ORDER BY ml_anomaly_score DESC
LIMIT 10;

-- 5. Change area by LISA cluster type
SELECT lisa_cluster, COUNT(*) AS n_features, SUM(area_m2) AS total_area_m2
FROM change_features
GROUP BY lisa_cluster
ORDER BY total_area_m2 DESC;

-- 6. High-confidence features only (confidence is a heuristic 0-1 score, not a
--    calibrated probability -- see README "Confidence Score")
SELECT id, area_m2, mean_change, confidence, hotspot_class
FROM change_features
WHERE confidence >= 0.6
ORDER BY confidence DESC;

-- 7. Run metadata for the most recent run
SELECT run_id, run_timestamp, before_date, after_date, method, threshold_method,
       threshold_value, min_area_m2, package_version, random_seed
FROM run_metadata
ORDER BY run_timestamp DESC
LIMIT 1;

-- 8. Any validation warnings/errors recorded for the run
SELECT run_id, check_name, severity, message
FROM quality_checks
ORDER BY severity DESC;

-- 9. Analysis-grid summary: mean CVA and changed-pixel proportion by hotspot class
SELECT hotspot_class, COUNT(*) AS n_cells, AVG(mean_cva) AS avg_mean_cva,
       AVG(changed_proportion) AS avg_changed_proportion
FROM spatial_grid
GROUP BY hotspot_class
ORDER BY avg_mean_cva DESC;

-- 10. Spatial extent check: bounding box of all change features (SpatiaLite/GDAL builds only)
-- SELECT ST_AsText(ST_Envelope(ST_Collect(geom))) FROM change_features;
-- NOTE: query 10 requires a SQLite build with the SpatiaLite extension loaded.
-- Plain sqlite3 without that extension cannot evaluate ST_* functions; use
-- GeoPandas/QGIS instead for pure-geometry aggregate queries if it is unavailable:
--   import geopandas as gpd
--   gdf = gpd.read_file("outputs/database/change_analysis.gpkg", layer="change_features")
--   print(gdf.total_bounds)
