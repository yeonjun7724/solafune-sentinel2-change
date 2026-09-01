# Sentinel-2 Change Analysis Report

## 1. Executive Summary

- **Dates compared:** 20230812 vs 20230902
- **AOI:** open-pit mining site, Zambia (`inputs/aoi.geojson`), area ~264.57 km^2
- **Primary method:** Robust RGB Change Vector Analysis (CVA) over B04/B03/B02, threshold = otsu (5.2199)
- **Total detected change area:** 37,405,887 m^2 (14.14% of the valid AOI)
- **Change features (polygons):** 514
- **Key spatial pattern:** Global Moran's I = 0.834 (permutation p = 0.0010) on mean CVA per 150 m analysis cell —
  positive spatial autocorrelation — changed pixels cluster spatially rather than appearing at random locations
- **95%+ Gi\* hotspot cells:** 95
- **Important limitation:** no ground truth exists for this AOI; all figures below are descriptive/exploratory, not validated accuracy.

## 2. Data

- **Bands used:** B02 (Blue), B03 (Green), B04 (Red) — 10 m Sentinel-2, already clipped to the AOI.
- **CRS:** EPSG:32735 (10 m pixel size); grid: 1673 x 1597 pixels.
- **Extent (working CRS):** (368430.0, 8637800.0, 385160.0, 8653770.0)
- **NoData:** 0.0 (0.98% of the raster footprint outside the AOI polygon).
- **Quality checks:** 0 warning(s), 0 error(s) (see quality_report.json)

## 3. Method

1. **Baseline** — an independent reimplementation of the idea in `inputs/example_change_detection.py`: per-pixel multi-band Euclidean distance, min-max normalized to [0, 1] over the AOI/valid mask. No radiometric normalization is applied (mirrors the example's implicit assumption).
2. **Radiometric normalization** — `robust_median_mad` applied to the "after" date before CVA, using only pixels valid in both dates and inside the AOI to estimate the transform. See README "Radiometric Normalization" for the full rationale and limitations.
3. **Robust RGB CVA** — per-band differences standardized with median/MAD (MAD-near-zero pixels fall back to standard deviation; see `cva.py`), combined as `sqrt(sum(z_b^2))`.
4. **Threshold** — `otsu` on the CVA raster (value = 5.2199), computed over valid pixels only.
5. **Morphology / cleanup** — opening_then_closing (kernel=3px); minimum change area = 400 m^2 (4 px).
6. **Vectorization** — 8-connectivity polygonization, clipped to the AOI, invalid geometries repaired with `buffer(0)`, area/perimeter computed directly in EPSG:32735 (already a projected CRS appropriate for this AOI).
7. **Spatial statistics** — 150 m regular analysis grid (11967 cells), queen contiguity weights (row-standardized for Moran's I, binary for Gi\*), 999 permutations, seed=42, Benjamini-Hochberg FDR correction enabled on Gi\* p-values.
8. **Experimental spatial ML** — disabled (opt-in only).
9. **Database** — results written to a GeoPackage (SQLite-based OGC format) at `outputs/database/change_analysis.gpkg`.

## 4. Results

- **Baseline vs. CVA:** baseline flags 47.85% of valid pixels above its own Otsu-style threshold; CVA flags 15.32% above `otsu` = 5.2199. CVA's robust per-band standardization generally yields a more spatially coherent result than the baseline's unnormalized, globally min-max-scaled distance (see Global Moran's I above).
- **Change area / feature count:** 514 polygons totalling 37,405,887 m^2 (14.14% of AOI).
- **Largest change objects (top 5 by area):**

| ID | Area (m2) | Mean change | Confidence | Gi* class |
|---|---|---|---|---|
| 477 | 15,987,700 | 9.088 | 0.60 | hot_99 |
| 173 | 6,583,500 | 10.560 | 0.65 | hot_99 |
| 165 | 6,229,200 | 9.705 | 0.55 | hot_90 |
| 141 | 3,583,700 | 9.194 | 0.62 | hot_99 |
| 124 | 791,500 | 13.011 | 0.73 | hot_99 |

- **Global Moran's I:** I = 0.8335, E[I] = -0.0001, z = 178.37, permutation p = 0.0010 (999 permutations, seed=42).
- **Local Moran's I (LISA) cluster counts:** {'Not significant': 5246, 'Low-Low': 4475, 'High-High': 2178, 'Low-High': 66, 'High-Low': 2}
- **Getis-Ord Gi\* hotspot counts:** {'not_significant': 5017, 'cold_99': 2753, 'hot_99': 1515, 'cold_95': 1003, 'cold_90': 865, 'hot_95': 497, 'hot_90': 317}
- **Experimental ML anomaly results:** not run (spatial_ml_enabled=False or an earlier stage skipped it)

## 5. Interpretation

The AOI is an active open-pit mining site. Spatially coherent, high-magnitude RGB change consistent with the observed patterns **may indicate**:

- Open-pit excavation expansion or bench advancement
- Newly exposed soil or rock surfaces
- Waste-rock or tailings deposition/redistribution
- Haul-road construction or resurfacing / operational surface changes
- Moisture or water-extent variation (pit water, settling ponds)
- Vegetation removal at the pit margins

RGB imagery from two dates alone **cannot distinguish** between these causes, and cannot rule out illumination/haze/shadow or (small) co-registration artifacts contributing to some detections. Detections are reported as *consistent with* surface disturbance, not as a confirmed land-cover transition.

## 6. Limitations

- Only B02/B03/B04 were provided; **NDVI could not be computed** (requires a NIR band such as B08).
- No cloud mask / Scene Classification Layer (SCL) was provided; cloud/shadow contamination cannot be explicitly excluded.
- Only two dates are available, so seasonal and transient (non-mining) surface change cannot be separated from persistent change.
- No ground-truth labels exist for this AOI; no accuracy/precision/recall is computed or claimed anywhere in this project.
- `confidence` is a documented heuristic score (see README), **not** a calibrated probability.
- The spatial-ML results (`spatial_ml.py`) are exploratory anomaly rankings/clusters, not validated predictions — no train/test or cross-validation score is reported because neighboring grid cells are spatially autocorrelated (confirmed by the Global Moran's I result above) and would leak information across any naive split.
- Statistical significance (Gi\*/Moran's I p-values) describes spatial pattern, not land-use cause.

## 7. Operational Recommendations

- Acquire a denser Sentinel-2 time series (monthly or better) to separate persistent change from noise/seasonality.
- Use B08 (NIR) and SCL to add NDVI and cloud/shadow masking.
- Validate top-confidence / top-hotspot / top-anomaly features against high-resolution imagery or field visits before any operational decision.
- Track change persistence across >=3 consecutive acquisitions before treating a detection as an operational alert.
- For production monitoring: add automated cloud/shadow filtering, a persistent per-pixel baseline (e.g. a rolling median), and alerting thresholds tuned against a small manually-reviewed validation set.

---
*Generated by `solafune-change report` — run id `20260901T063130Z-94eb4ac2`, package version `0.1.0`.*
