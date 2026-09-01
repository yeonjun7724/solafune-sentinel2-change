"""Static comparison figures, a standalone interactive HTML map, and QML styles.

RGB stretch policy: percentile stretch parameters (2nd/98th percentile per
band, configurable) are computed once from the *before* image's valid pixels
and applied identically to both dates, so a genuine reflectance change is not
disguised or exaggerated by re-stretching each date independently.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path

import matplotlib

# This package only ever renders figures to files/bytes, never to an
# interactive window. Force the non-interactive Agg backend before importing
# pyplot: otherwise matplotlib's automatic backend selection can pick an
# interactive backend (e.g. TkAgg) depending on import order/environment,
# which then fails intermittently in headless/test environments without a
# working Tcl/Tk installation.
matplotlib.use("Agg")

import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Patch
from pyproj import Transformer

logger = logging.getLogger(__name__)

HOTSPOT_COLORS = {
    "hot_99": "#67000d",
    "hot_95": "#d7301f",
    "hot_90": "#fc9272",
    "not_significant": "#f0f0f0",
    "cold_90": "#9ecae1",
    "cold_95": "#3182bd",
    "cold_99": "#08306b",
}
LISA_COLORS = {
    "High-High": "#d7301f",
    "Low-Low": "#3182bd",
    "High-Low": "#fdae61",
    "Low-High": "#a6bddb",
    "Not significant": "#f0f0f0",
}


def compute_rgb_stretch(
    dn: np.ndarray, valid_mask: np.ndarray, low_pct: float = 2.0, high_pct: float = 98.0
) -> dict:
    """Compute per-band percentile stretch parameters from valid pixels of one date."""
    params = {}
    for b in range(dn.shape[0]):
        vals = dn[b][valid_mask]
        lo, hi = np.percentile(vals, [low_pct, high_pct])
        params[b] = (float(lo), float(hi) if hi > lo else float(lo) + 1.0)
    return params


def apply_rgb_stretch(
    dn: np.ndarray, stretch_params: dict, valid_mask: np.ndarray | None = None
) -> np.ndarray:
    """Apply a precomputed per-band stretch to a (bands, H, W) array, return (H, W, bands) uint8."""
    bands, h, w = dn.shape
    out = np.zeros((h, w, bands), dtype=np.uint8)
    for b in range(bands):
        lo, hi = stretch_params[b]
        scaled = np.clip((dn[b] - lo) / (hi - lo), 0, 1)
        out[:, :, b] = (scaled * 255).astype(np.uint8)
    if valid_mask is not None:
        out[~valid_mask] = 0
    return out


def _png_bytes(rgb_uint8: np.ndarray) -> bytes:
    buf = io.BytesIO()
    plt.imsave(buf, rgb_uint8, format="png")
    return buf.getvalue()


def plot_static_comparison(
    before_rgb: np.ndarray,
    after_rgb: np.ndarray,
    baseline_intensity: np.ndarray,
    cva_intensity: np.ndarray,
    change_polygons: gpd.GeoDataFrame,
    grid_gdf: gpd.GeoDataFrame | None,
    aoi_gdf: gpd.GeoDataFrame,
    extent: tuple[float, float, float, float],
    before_date: str,
    after_date: str,
    threshold_method: str,
    output_path: Path,
) -> None:
    """Save a multi-panel high-resolution PNG comparing baseline vs. CVA results."""
    fig, axes = plt.subplots(2, 3, figsize=(20, 13), constrained_layout=True)
    extent_mpl = (extent[0], extent[2], extent[1], extent[3])

    axes[0, 0].imshow(before_rgb, extent=extent_mpl)
    axes[0, 0].set_title(f"Before: {before_date} (RGB, true-color)")

    axes[0, 1].imshow(after_rgb, extent=extent_mpl)
    axes[0, 1].set_title(f"After: {after_date} (RGB, true-color)")

    im2 = axes[0, 2].imshow(baseline_intensity, extent=extent_mpl, cmap="magma", vmin=0, vmax=1)
    axes[0, 2].set_title("Baseline change intensity (Euclidean, min-max normalized)")
    fig.colorbar(im2, ax=axes[0, 2], fraction=0.04, label="Normalized intensity [0-1]")

    cva_vmax = (
        float(np.percentile(cva_intensity[cva_intensity > 0], 98))
        if np.any(cva_intensity > 0)
        else 1.0
    )
    im3 = axes[1, 0].imshow(cva_intensity, extent=extent_mpl, cmap="viridis", vmin=0, vmax=cva_vmax)
    axes[1, 0].set_title("Robust RGB CVA magnitude")
    fig.colorbar(im3, ax=axes[1, 0], fraction=0.04, label="CVA magnitude (robust z-units)")

    axes[1, 1].imshow(after_rgb, extent=extent_mpl, alpha=0.85)
    if not change_polygons.empty:
        change_polygons.plot(ax=axes[1, 1], facecolor="none", edgecolor="red", linewidth=0.8)
    if aoi_gdf is not None:
        # aoi_gdf may still be in its source CRS (e.g. EPSG:4326 degrees) while this
        # panel is in the raster's projected CRS (e.g. EPSG:32735 meters); plotting
        # degree-scale coordinates directly on a meter-scale axes blows up autoscale
        # to a near-empty view. Reproject to the change-polygon CRS first.
        working_crs = change_polygons.crs if not change_polygons.empty else None
        aoi_plot = (
            aoi_gdf.to_crs(working_crs)
            if working_crs is not None and aoi_gdf.crs != working_crs
            else aoi_gdf
        )
        aoi_plot.boundary.plot(ax=axes[1, 1], color="cyan", linewidth=1.2)
    # Re-assert the imagery extent: geopandas .plot() calls can otherwise leave the
    # axes autoscaled to the union of all plotted artists rather than the image.
    axes[1, 1].set_xlim(extent_mpl[0], extent_mpl[1])
    axes[1, 1].set_ylim(extent_mpl[2], extent_mpl[3])
    axes[1, 1].set_title(f"Final change polygons (threshold={threshold_method}) over After RGB")

    if grid_gdf is not None and "hotspot_class" in grid_gdf.columns and not grid_gdf.empty:
        colors = grid_gdf["hotspot_class"].map(HOTSPOT_COLORS).fillna("#f0f0f0")
        grid_gdf.plot(ax=axes[1, 2], color=colors, linewidth=0)
        legend_handles = [Patch(facecolor=c, label=k) for k, c in HOTSPOT_COLORS.items()]
        axes[1, 2].legend(handles=legend_handles, fontsize=6, loc="upper right", ncol=1)
        axes[1, 2].set_title("Getis-Ord Gi* hotspot classification")
    else:
        axes[1, 2].axis("off")
        axes[1, 2].set_title("Spatial statistics disabled")

    for ax in axes.ravel():
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        ax.tick_params(labelsize=7)

    fig.suptitle(
        f"Solafune Sentinel-2 Change Analysis — {before_date} vs {after_date} — "
        f"Zambia open-pit mining AOI (EPSG:32735)",
        fontsize=13,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200)
    plt.close(fig)
    logger.info("Wrote static comparison figure: %s", output_path)


def create_interactive_map(
    aoi_gdf: gpd.GeoDataFrame,
    before_rgb: np.ndarray,
    after_rgb: np.ndarray,
    raster_crs: str,
    raster_bounds: tuple[float, float, float, float],
    change_polygons: gpd.GeoDataFrame,
    grid_gdf: gpd.GeoDataFrame | None,
    output_path: Path,
    before_date: str,
    after_date: str,
) -> None:
    """Save a standalone Folium HTML map (no external tiles/API keys required to see analysis layers)."""
    import folium

    transformer = Transformer.from_crs(raster_crs, "EPSG:4326", always_xy=True)
    lon0, lat0 = transformer.transform(raster_bounds[0], raster_bounds[1])
    lon1, lat1 = transformer.transform(raster_bounds[2], raster_bounds[3])
    bounds_wgs84 = [[min(lat0, lat1), min(lon0, lon1)], [max(lat0, lat1), max(lon0, lon1)]]
    center = [
        (bounds_wgs84[0][0] + bounds_wgs84[1][0]) / 2,
        (bounds_wgs84[0][1] + bounds_wgs84[1][1]) / 2,
    ]

    fmap = folium.Map(location=center, zoom_start=13, tiles=None, control_scale=True)
    folium.TileLayer(
        tiles="OpenStreetMap", name="OpenStreetMap (requires internet)", show=False
    ).add_to(fmap)
    folium.TileLayer(
        tiles='<div style="background:#222;color:#eee;">No basemap</div>',
        name="Blank / offline background",
        attr="none",
        show=True,
    ).add_to(fmap)

    def _overlay(rgb: np.ndarray, name: str, show: bool) -> None:
        b64 = base64.b64encode(_png_bytes(rgb)).decode("ascii")
        folium.raster_layers.ImageOverlay(
            image=f"data:image/png;base64,{b64}",
            bounds=bounds_wgs84,
            name=name,
            opacity=0.95,
            show=show,
            interactive=True,
            cross_origin=False,
        ).add_to(fmap)

    _overlay(before_rgb, f"Before RGB ({before_date})", show=True)
    _overlay(after_rgb, f"After RGB ({after_date})", show=False)

    folium.GeoJson(
        aoi_gdf.to_crs(4326),
        name="AOI",
        style_function=lambda _: {"color": "cyan", "weight": 2, "fillOpacity": 0},
    ).add_to(fmap)

    if not change_polygons.empty:
        cp = change_polygons.to_crs(4326)
        folium.GeoJson(
            cp,
            name="Change polygons",
            style_function=lambda f: {
                "color": "red",
                "weight": 1,
                "fillOpacity": 0.15 + 0.5 * (f["properties"].get("confidence") or 0),
                "fillColor": "red",
            },
            tooltip=folium.GeoJsonTooltip(
                fields=[
                    "id",
                    "area_m2",
                    "mean_change",
                    "confidence",
                    "hotspot_class",
                    "lisa_cluster",
                ],
                aliases=[
                    "ID",
                    "Area (m2)",
                    "Mean change",
                    "Confidence (heuristic)",
                    "Gi* class",
                    "LISA cluster",
                ],
            ),
        ).add_to(fmap)

    if grid_gdf is not None and not grid_gdf.empty:
        gj = grid_gdf.to_crs(4326)
        if "hotspot_class" in gj.columns:
            folium.GeoJson(
                gj,
                name="Gi* hotspots (grid)",
                style_function=lambda f: {
                    "color": "none",
                    "fillColor": HOTSPOT_COLORS.get(
                        f["properties"].get("hotspot_class"), "#f0f0f0"
                    ),
                    "fillOpacity": 0.55,
                    "weight": 0,
                },
                show=False,
            ).add_to(fmap)
        if "lisa_cluster" in gj.columns:
            folium.GeoJson(
                gj,
                name="LISA clusters (grid)",
                style_function=lambda f: {
                    "color": "none",
                    "fillColor": LISA_COLORS.get(f["properties"].get("lisa_cluster"), "#f0f0f0"),
                    "fillOpacity": 0.55,
                    "weight": 0,
                },
                show=False,
            ).add_to(fmap)
        if "ml_anomaly_score" in gj.columns:
            import branca

            colormap = branca.colormap.LinearColormap(
                colors=["#f7fbff", "#6baed6", "#08306b"],
                vmin=float(gj["ml_anomaly_score"].min()),
                vmax=float(gj["ml_anomaly_score"].max()),
                caption="Isolation Forest anomaly score (exploratory, not a probability)",
            )
            folium.GeoJson(
                gj,
                name="ML anomaly score (experimental)",
                style_function=lambda f: {
                    "color": "none",
                    "fillColor": colormap(f["properties"].get("ml_anomaly_score", 0)),
                    "fillOpacity": 0.55,
                    "weight": 0,
                },
                show=False,
            ).add_to(fmap)
            fmap.add_child(colormap)

    folium.LayerControl(collapsed=False).add_to(fmap)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_path))
    logger.info("Wrote interactive map: %s", output_path)


# --- QML style generation --------------------------------------------------

_QML_RASTER_TEMPLATE = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28">
  <pipe>
    <rasterrenderer band="1" type="singlebandpseudocolor" opacity="1" alphaBand="-1" classificationMin="{vmin}" classificationMax="{vmax}">
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="1">
          <item value="{vmin}" color="#ffffff00" alpha="0" label="No change"/>
          <item value="{mid1}" color="#ffff6600" alpha="180" label="Moderate"/>
          <item value="{mid2}" color="#ff0000" alpha="230" label="Strong"/>
          <item value="{vmax}" color="#800026" alpha="255" label="Very strong"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
  </pipe>
</qgis>
"""

_QML_BINARY_TEMPLATE = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28">
  <pipe>
    <rasterrenderer band="1" type="paletted" opacity="1" alphaBand="-1">
      <colorPalette>
        <paletteEntry value="0" color="#ffffff" alpha="0" label="No change"/>
        <paletteEntry value="1" color="#ff00ff" alpha="255" label="Changed"/>
      </colorPalette>
    </rasterrenderer>
  </pipe>
</qgis>
"""

_QML_POLYGON_CONFIDENCE = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28">
  <renderer-v2 type="graduatedSymbol" attr="confidence" graduatedMethod="GraduatedColor">
    <ranges>
      <range lower="0.0" upper="0.3" label="Low confidence (0.0-0.3)" symbol="0"/>
      <range lower="0.3" upper="0.6" label="Medium confidence (0.3-0.6)" symbol="1"/>
      <range lower="0.6" upper="1.01" label="High confidence (0.6-1.0)" symbol="2"/>
    </ranges>
    <symbols>
      <symbol type="fill" name="0" alpha="0.35"><layer class="SimpleFill"><Option><Option name="color" value="255,255,0,90"/><Option name="outline_color" value="255,255,0,255"/><Option name="outline_width" value="0.3"/></Option></layer></symbol>
      <symbol type="fill" name="1" alpha="0.45"><layer class="SimpleFill"><Option><Option name="color" value="255,140,0,120"/><Option name="outline_color" value="255,140,0,255"/><Option name="outline_width" value="0.4"/></Option></layer></symbol>
      <symbol type="fill" name="2" alpha="0.55"><layer class="SimpleFill"><Option><Option name="color" value="220,20,20,150"/><Option name="outline_color" value="220,20,20,255"/><Option name="outline_width" value="0.5"/></Option></layer></symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""

_QML_LISA = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28">
  <renderer-v2 type="categorizedSymbol" attr="lisa_cluster">
    <categories>
      <category value="High-High" label="High-High" symbol="0"/>
      <category value="Low-Low" label="Low-Low" symbol="1"/>
      <category value="High-Low" label="High-Low" symbol="2"/>
      <category value="Low-High" label="Low-High" symbol="3"/>
      <category value="Not significant" label="Not significant" symbol="4"/>
    </categories>
    <symbols>
      <symbol type="fill" name="0"><layer class="SimpleFill"><Option><Option name="color" value="215,48,31,200"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="1"><layer class="SimpleFill"><Option><Option name="color" value="49,130,189,200"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="2"><layer class="SimpleFill"><Option><Option name="color" value="253,174,97,200"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="3"><layer class="SimpleFill"><Option><Option name="color" value="166,189,219,200"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="4"><layer class="SimpleFill"><Option><Option name="color" value="240,240,240,120"/><Option name="outline_width" value="0"/></Option></layer></symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""

_QML_HOTSPOT = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28">
  <renderer-v2 type="categorizedSymbol" attr="hotspot_class">
    <categories>
      <category value="hot_99" label="99% Hotspot" symbol="0"/>
      <category value="hot_95" label="95% Hotspot" symbol="1"/>
      <category value="hot_90" label="90% Hotspot" symbol="2"/>
      <category value="not_significant" label="Not significant" symbol="3"/>
      <category value="cold_90" label="90% Coldspot" symbol="4"/>
      <category value="cold_95" label="95% Coldspot" symbol="5"/>
      <category value="cold_99" label="99% Coldspot" symbol="6"/>
    </categories>
    <symbols>
      <symbol type="fill" name="0"><layer class="SimpleFill"><Option><Option name="color" value="103,0,13,220"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="1"><layer class="SimpleFill"><Option><Option name="color" value="215,48,31,220"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="2"><layer class="SimpleFill"><Option><Option name="color" value="252,146,114,220"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="3"><layer class="SimpleFill"><Option><Option name="color" value="240,240,240,90"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="4"><layer class="SimpleFill"><Option><Option name="color" value="158,202,225,220"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="5"><layer class="SimpleFill"><Option><Option name="color" value="49,130,189,220"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="6"><layer class="SimpleFill"><Option><Option name="color" value="8,48,107,220"/><Option name="outline_width" value="0"/></Option></layer></symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""

_QML_ML_ANOMALY = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28">
  <!-- Styled on ml_anomaly_quantile (rank percentile, always in [0,1] by construction),
       not the raw ml_anomaly_score, so this static style is valid across runs.
       EXPERIMENTAL: exploratory anomaly ranking, not a validated probability. -->
  <renderer-v2 type="graduatedSymbol" attr="ml_anomaly_quantile" graduatedMethod="GraduatedColor">
    <ranges>
      <range lower="0.0" upper="0.5" label="Below median anomaly rank" symbol="0"/>
      <range lower="0.5" upper="0.9" label="Above median (top 50%)" symbol="1"/>
      <range lower="0.9" upper="1.01" label="Top 10% anomaly rank" symbol="2"/>
    </ranges>
    <symbols>
      <symbol type="fill" name="0"><layer class="SimpleFill"><Option><Option name="color" value="247,251,255,60"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="1"><layer class="SimpleFill"><Option><Option name="color" value="107,174,214,140"/><Option name="outline_width" value="0"/></Option></layer></symbol>
      <symbol type="fill" name="2"><layer class="SimpleFill"><Option><Option name="color" value="8,48,107,200"/><Option name="outline_width" value="0"/></Option></layer></symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""


def write_qml(path: Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("Wrote QGIS style: %s", path)


def generate_intensity_qml(vmin: float, vmax: float) -> str:
    mid1 = vmin + (vmax - vmin) * 0.33
    mid2 = vmin + (vmax - vmin) * 0.66
    return _QML_RASTER_TEMPLATE.format(vmin=vmin, vmax=vmax, mid1=mid1, mid2=mid2)


def generate_all_styles(
    output_dir: Path,
    cva_vmin: float,
    cva_vmax: float,
    baseline_vmin: float = 0.0,
    baseline_vmax: float = 1.0,
) -> dict[str, Path]:
    """Write all per-run QML style files and return their paths, keyed by name."""
    output_dir = Path(output_dir)
    paths = {}
    mapping = {
        "cva_intensity.qml": generate_intensity_qml(cva_vmin, cva_vmax),
        "baseline_intensity.qml": generate_intensity_qml(baseline_vmin, baseline_vmax),
        "change_binary.qml": _QML_BINARY_TEMPLATE,
        "change_polygons.qml": _QML_POLYGON_CONFIDENCE,
        "lisa_clusters.qml": _QML_LISA,
        "gi_hotspots.qml": _QML_HOTSPOT,
        "ml_anomalies.qml": _QML_ML_ANOMALY,
    }
    for name, content in mapping.items():
        p = output_dir / name
        write_qml(p, content)
        paths[name] = p
    return paths
