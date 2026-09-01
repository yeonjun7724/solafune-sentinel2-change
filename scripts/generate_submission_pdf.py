#!/usr/bin/env python
"""Generates a detailed English-language PDF usage guide for the submission bundle.

Covers both the QGIS plugin version and the script/CLI version of
solafune-change, step by step, plus project background, algorithm detail,
database schema, dependency setup options (including a no-separate-venv
path verified against a real QGIS install), and the bugs found and fixed
during development. Requires ``reportlab`` (dev-only dependency; not part
of the core pipeline's runtime requirements) and a TrueType font on the
system (defaults to Windows' bundled Malgun Gothic, which also renders
Latin text cleanly; override with --font/--font-bold if unavailable).

Usage:
    python scripts/generate_submission_pdf.py [--out submission/Usage_Guide.pdf]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "submission" / "Usage_Guide.pdf"
DEFAULT_FONT = r"C:\Windows\Fonts\malgun.ttf"
DEFAULT_FONT_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"

NAVY = colors.HexColor("#0b3d91")
DARK = colors.HexColor("#1a1a1a")
GRAY = colors.HexColor("#555555")
LIGHT_BG = colors.HexColor("#f4f4f4")
ACCENT = colors.HexColor("#ff5722")
GREEN = colors.HexColor("#1b6b1b")


def register_fonts(regular: str, bold: str) -> None:
    if not Path(regular).exists() or not Path(bold).exists():
        raise SystemExit(
            f"Font not found at {regular} / {bold}. "
            "Pass --font/--font-bold pointing at a TTF pair (any Unicode-capable font works)."
        )
    pdfmetrics.registerFont(TTFont("KR", regular))
    pdfmetrics.registerFont(TTFont("KR-Bold", bold))


def build_styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title", fontName="KR-Bold", fontSize=25, leading=31, textColor=NAVY, spaceAfter=6
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName="KR", fontSize=12.5, leading=17, textColor=GRAY, spaceAfter=4
        ),
        "h1": ParagraphStyle(
            "h1",
            fontName="KR-Bold",
            fontSize=16,
            leading=21,
            textColor=NAVY,
            spaceBefore=16,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName="KR-Bold",
            fontSize=12.5,
            leading=17,
            textColor=DARK,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "h3",
            fontName="KR-Bold",
            fontSize=10.5,
            leading=14,
            textColor=ACCENT,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", fontName="KR", fontSize=9.5, leading=14, textColor=DARK, spaceAfter=6
        ),
        "note": ParagraphStyle(
            "note",
            fontName="KR",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#8a5a00"),
            backColor=colors.HexColor("#fff6e0"),
            borderColor=colors.HexColor("#e0b84d"),
            borderWidth=0.6,
            borderPadding=6,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "highlight": ParagraphStyle(
            "highlight",
            fontName="KR",
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#0a4d0a"),
            backColor=colors.HexColor("#e9f7e9"),
            borderColor=GREEN,
            borderWidth=0.6,
            borderPadding=7,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "code": ParagraphStyle(
            "code",
            fontName="Courier",
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor("#0a3d0a"),
            backColor=LIGHT_BG,
            borderColor=colors.HexColor("#cccccc"),
            borderWidth=0.5,
            borderPadding=8,
            spaceBefore=4,
            spaceAfter=10,
        ),
        "table_head": ParagraphStyle(
            "table_head", fontName="KR-Bold", fontSize=8.5, leading=11.5, textColor=colors.white
        ),
        "table_cell": ParagraphStyle("table_cell", fontName="KR", fontSize=8.5, leading=12),
        "table_cell_mono": ParagraphStyle(
            "table_cell_mono", fontName="Courier", fontSize=7.8, leading=11
        ),
        "caption": ParagraphStyle("caption", fontName="KR", fontSize=8, leading=11, textColor=GRAY),
        "footer": ParagraphStyle("footer", fontName="KR", fontSize=8, leading=10, textColor=GRAY),
    }


def code_block(text: str, styles: dict) -> Paragraph:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = escaped.replace("\n", "<br/>")
    return Paragraph(html, styles["code"])


def bullet_list(items: list[str], styles: dict) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(item, styles["body"]), leftIndent=8) for item in items],
        bulletType="bullet",
        start="\u2022",
        leftIndent=14,
        spaceBefore=2,
        spaceAfter=8,
    )


def make_table(
    header: list[str], rows: list[list[str]], styles: dict, col_widths=None, mono_cols=None
) -> Table:
    mono_cols = mono_cols or set()
    header_row = [Paragraph(h, styles["table_head"]) for h in header]
    data = [header_row]
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            style_key = "table_cell_mono" if i in mono_cols else "table_cell"
            cells.append(Paragraph(cell, styles[style_key]))
        data.append(cells)
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def hr(color=None, thickness=0.8, space_before=4, space_after=10) -> HRFlowable:
    return HRFlowable(
        width="100%",
        thickness=thickness,
        color=color or colors.HexColor("#dddddd"),
        spaceBefore=space_before,
        spaceAfter=space_after,
    )


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("KR", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(20 * mm, 12 * mm, "Solafune Sentinel-2 Change Analysis \u2014 Usage Guide")
    canvas.drawRightString(190 * mm, 12 * mm, f"{doc.page}")
    canvas.restoreState()


def build_story(styles: dict) -> list:
    s = styles
    story: list = []

    # ================================================================== Cover page
    story.append(Spacer(1, 30))
    story.append(Paragraph("Solafune Sentinel-2 Change Analysis", s["title"]))
    story.append(
        Paragraph(
            "Detailed Usage Guide &mdash; QGIS Plugin Edition &amp; Script (CLI) Edition",
            s["subtitle"],
        )
    )
    story.append(hr(color=NAVY, thickness=1.4, space_before=10, space_after=16))
    story.append(
        Paragraph(
            "This document walks through installation, configuration, and usage &mdash; screen by "
            "screen, field by field &mdash; for both execution modes included in the submission bundle "
            "(<font face='Courier'>submission/</font>): (1) the <b>QGIS plugin edition</b>, run interactively "
            "inside QGIS, and (2) the <b>script (CLI) edition</b>, run from a terminal. It also covers "
            "project background, the rationale behind each algorithm, the spatial database schema, bugs "
            "actually found and fixed during development, and the test/verification record. Both editions "
            "share the exact same analysis engine (the <font face='Courier'>solafune_change</font> core "
            "package), so results are identical regardless of which one you use.",
            s["body"],
        )
    )
    story.append(Spacer(1, 12))
    story.append(
        make_table(
            ["Item", "Value"],
            [
                [
                    "GitHub repository",
                    "https://github.com/yeonjun7724/solafune-sentinel2-change (Public)",
                ],
                [
                    "AOI",
                    "Open-pit mine, Zambia, approx. 264.6 km\u00b2 (EPSG:32735, UTM 35S, 10 m resolution)",
                ],
                [
                    "Compared acquisitions",
                    "2023-08-12 vs 2023-09-02 (Sentinel-2 bands B02/B03/B04)",
                ],
                [
                    "Headline results",
                    "514 change features / total changed area 37,405,887 m\u00b2 (14.14% of AOI) / Global Moran's I = 0.834 (p=0.001)",
                ],
                [
                    "Target QGIS version",
                    "3.28 or later (installed and run on a real 3.44.12 instance)",
                ],
                ["Target Python version", "3.10 or later (developed/tested on 3.12)"],
                ["Tests", "65 pytest cases, all passing; ruff/black clean"],
            ],
            s,
            col_widths=[110, 340],
        )
    )
    story.append(PageBreak())

    # ================================================================== Table of contents
    story.append(Paragraph("Table of Contents", s["h1"]))
    toc_rows = [
        ["0", "Submission bundle contents (full layout)"],
        ["1", "Original assignment requirements vs. delivered work"],
        ["PART A", "QGIS Plugin Edition \u2014 install through results"],
        ["A.1\u2013A.2", "Prerequisites / installation steps"],
        ["A.3\u2013A.4", "Dependency check and setup (no-venv path included, field-verified)"],
        ["A.5", "Dock widget \u2014 all 6 tabs, every field, in detail"],
        ["A.6", "Run progress \u2014 all 12 pipeline stages"],
        ["A.7", "Result layer tree and styling"],
        ["A.8\u2013A.9", "Processing Toolbox / Before-After comparison"],
        ["A.10", "Newly added Clear Inputs (reset) button"],
        ["A.11\u2013A.12", "Troubleshooting / checksum verification"],
        ["PART B", "Script (CLI) Edition \u2014 install through results"],
        ["B.1\u2013B.9", "Install, run, full CLI command/option reference"],
        ["B.10", "Full config/default.yaml field reference"],
        ["B.11\u2013B.12", "Tests / rebuild / troubleshooting"],
        ["2", "Actual analysis results, in detail"],
        ["3", "Algorithm choices and rationale (with formulas)"],
        ["4", "Full spatial database schema"],
        ["5", "Bugs actually found and fixed during development (8)"],
        ["6", "Test and verification record"],
        ["7", "Key assumptions and limitations"],
        ["Appendix", "Example SQL queries / glossary"],
    ]
    story.append(make_table(["Sec.", "Contents"], toc_rows, s, col_widths=[70, 380]))
    story.append(PageBreak())

    # ================================================================== 0. Submission bundle contents
    story.append(Paragraph("0. Submission Bundle Contents (Full Layout)", s["h1"]))
    story.append(
        Paragraph(
            "The <font face='Courier'>submission/</font> folder contains everything needed for review in "
            "one place: both runnable editions, the actual final outputs, a copy of the raw input data, "
            "and this document.",
            s["body"],
        )
    )
    story.append(
        make_table(
            ["Path", "Description", "QGIS needed?"],
            [
                ["Usage_Guide.pdf", "This document", "-"],
                [
                    "solafune_change_analyzer.zip (+.sha256)",
                    "(1) QGIS plugin install package (analysis engine vendored inside). Checksum file included",
                    "Yes",
                ],
                [
                    "solafune-sentinel2-change-source.zip",
                    "(2) Script (CLI) edition, and also the complete source repository as a single archive "
                    "(wrapped in a solafune-sentinel2-change-master/ folder, matching GitHub's \u201cDownload "
                    "ZIP\u201d layout). Built with git archive from the exact commit pushed to GitHub, excluding "
                    "only the submission/ and yeonjun/ packaging folders themselves (see the note below)",
                    "No",
                ],
                [
                    "data/",
                    "(3) A standalone copy of the raw input satellite imagery (AOI + band GeoTIFFs), for quick inspection",
                    "No",
                ],
                [
                    "results/outputs/",
                    "(4) The actual final outputs produced by a real pipeline run \u2014 GeoPackage database, "
                    "static comparison figure, interactive map, spatial-statistics JSON/CSV, report.md, and more. "
                    "Open directly, no re-run required",
                    "No (opens best in QGIS)",
                ],
                [
                    "results/data_processed/",
                    "(4) The stacked GeoTIFF and the baseline/CVA intensity and binary change rasters, as produced",
                    "No",
                ],
            ],
            s,
            col_widths=[150, 265, 75],
        )
    )
    story.append(
        Paragraph(
            "<b>Item (2) is the \u201centire repository as one zip file.\u201d</b> It is built directly from the "
            "commit actually pushed to GitHub via <font face='Courier'>git archive</font>, wrapped in the same "
            "<font face='Courier'>solafune-sentinel2-change-master/</font> folder GitHub's Code &rarr; Download "
            "ZIP button produces \u2014 the full source code, tests, docs, and configuration, byte-for-byte from "
            "that commit. It is at the same time the \u201cscript/CLI edition\u201d package: unzip it and it is "
            "immediately runnable (see PART B). One deliberate exclusion: the "
            "<font face='Courier'>submission/</font> and <font face='Courier'>yeonjun/</font> packaging folders "
            "(this very bundle, and the author's personal working notes) are left out of the archive, since "
            "including them would make the zip contain a copy of itself and grow without bound every time it is "
            "rebuilt. Everything needed to build and run the project from scratch is included.",
            s["highlight"],
        )
    )
    story.append(
        Paragraph(
            "<b>Item (4) (results/) is the \u201cfinal output artifacts.\u201d</b> These are copies of what the "
            "pipeline actually produced on a real run, placed here so they can be opened immediately without "
            "re-running anything \u2014 GeoPackage, figures, map, statistics. (Item (2), the source zip, does "
            "not include these output files, to keep its size reasonable; open results/ instead if you just "
            "want to see the outcome without executing the pipeline.)",
            s["highlight"],
        )
    )
    story.append(PageBreak())

    # ================================================================== 1. Requirements comparison
    story.append(Paragraph("1. Original Assignment Requirements vs. Delivered Work", s["h1"]))
    story.append(
        Paragraph(
            "The five parts required by <font face='Courier'>instructions.pdf</font>, checked one by one "
            "against what was actually delivered.",
            s["body"],
        )
    )
    story.append(
        make_table(
            ["Part", "Requirement", "Delivered / verified"],
            [
                [
                    "1. Data Preparation",
                    "Load B2/B3/B4, verify CRS/transform/dimensions, stack bands",
                    "Verified via validation.py; produces data/processed/sentinel2_&lt;date&gt;_stack.tif with exactly the expected naming",
                ],
                [
                    "2. Change Detection",
                    "May reference the example, but must not copy it verbatim; own algorithm required",
                    "baseline.py (independent reimplementation of the example's idea) plus cva.py (robust CVA, the primary method) \u2014 both implemented, each producing intensity and binary rasters",
                ],
                [
                    "3. Feature Extraction &amp; Storage",
                    "Polygonize, store in SQLite or PostGIS, id/date_before/date_after/area_m2/confidence/geometry",
                    "Polygonized via vectorization.py, stored in GeoPackage (SQLite-based) with a real geometry column; all required fields present plus 15 additional fields (spatial statistics, ML)",
                ],
                [
                    "4. Visualization",
                    "AOI polygon, change raster/polygon display (interactive is a plus)",
                    "Both a static comparison figure (PNG) and a Folium interactive map (HTML, works fully offline) were actually generated and verified",
                ],
                [
                    "5. Analysis &amp; Interpretation",
                    "report.md with Method / Results / Interpretation sections",
                    "Expanded to 7 sections including those three, populated with numbers from an actual run",
                ],
            ],
            s,
            col_widths=[95, 175, 180],
        )
    )
    story.append(
        Paragraph(
            "All required deliverables (code, database, README.md, report.md) are present. On top of that, "
            "spatial statistics, unsupervised spatial ML, a QGIS plugin, and a 65-case automated test suite "
            "were added, none of which the assignment required.",
            s["body"],
        )
    )
    story.append(PageBreak())

    # ================================================================== PART A
    story.append(Paragraph("PART A. QGIS Plugin Edition", s["h1"]))

    story.append(Paragraph("A.1 Prerequisites", s["h2"]))
    story.append(
        bullet_list(
            [
                "QGIS 3.28 or later (developed and verified against QGIS 3.44.12, OSGeo4W build)",
                "Install package: <font face='Courier'>solafune_change_analyzer.zip</font>",
            ],
            s,
        )
    )

    story.append(Paragraph("A.2 Installation Steps", s["h2"]))
    story.append(
        bullet_list(
            [
                "Launch QGIS",
                "Menu: <b>Plugins \u2192 Manage and Install Plugins \u2192 Install from ZIP</b>",
                "Select <font face='Courier'>solafune_change_analyzer.zip</font> \u2192 <b>Install Plugin</b>",
                "In the <b>Installed</b> tab, confirm \u201cSolafune Change Analyzer\u201d is checked",
                "Open the dock widget via the toolbar icon or <b>Plugins \u2192 Solafune Change Analyzer</b>",
            ],
            s,
        )
    )

    story.append(Paragraph("A.3 Why Dependencies Are Missing", s["h2"]))
    story.append(
        Paragraph(
            "The plugin's analysis engine depends on standard geospatial-science Python packages: rasterio, "
            "geopandas, scikit-image, scikit-learn, libpysal, esda, matplotlib, and folium. <b>The Windows/"
            "OSGeo4W build of QGIS does not ship these inside its own Python by default</b> (QGIS's own GIS "
            "functionality talks to GDAL/PROJ directly at the C++ level, so it has no built-in need for a "
            "Python-level rasterio, etc.). Checked against a real QGIS 3.44.12 install:",
            s["body"],
        )
    )
    story.append(
        make_table(
            ["Package", "Bundled with QGIS?", "What it's needed for"],
            [
                [
                    "numpy, geopandas, shapely, pyproj, scipy, PyYAML, matplotlib, folium",
                    "Yes (Ready)",
                    "Core execution, visualization",
                ],
                [
                    "rasterio",
                    "No (Missing)",
                    "Raster I/O \u2014 the most critical one; nothing runs without it",
                ],
                ["scikit-image", "No (Missing)", "Morphological post-processing"],
                ["libpysal, esda", "No (Missing)", "Spatial statistics (Moran's I, Getis-Ord Gi*)"],
                ["scikit-learn", "No (Missing)", "Experimental unsupervised spatial ML"],
            ],
            s,
            col_widths=[195, 100, 155],
        )
    )

    story.append(Paragraph("A.4 Two Ways to Install the Dependencies", s["h2"]))
    story.append(
        Paragraph(
            "\u201cDo I have to set up a separate <font face='Courier'>.venv</font> folder?\u201d Short answer: "
            "<b>no, you don't.</b> Both options below were actually field-tested end to end against a real "
            "QGIS 3.44.12 install.",
            s["body"],
        )
    )

    story.append(
        Paragraph(
            "Option 1 (recommended, no extra folder): install straight into QGIS's own Python",
            s["h3"],
        )
    )
    story.append(
        Paragraph(
            "Run a single <font face='Courier'>pip install --user</font> against QGIS's own bundled Python "
            "interpreter. After that, the Dependencies tab automatically reports \u201cReady,\u201d and "
            "<b>Embedded mode works as-is</b> \u2014 no External interpreter configuration needed at all. "
            "Packages land under <font face='Courier'>%APPDATA%\\Python\\Python312\\site-packages</font> (a "
            "per-user folder, no admin rights required), which is already on QGIS's "
            "<font face='Courier'>sys.path</font>.",
            s["body"],
        )
    )
    story.append(
        Paragraph("Windows (adjust the path if your QGIS is installed elsewhere):", s["body"])
    )
    story.append(
        code_block(
            'cd "C:\\Program Files\\QGIS 3.44.12\\bin"\n'
            "python-qgis-ltr.bat -m pip install --user rasterio geopandas shapely pyproj scipy "
            "scikit-image PyYAML libpysal esda scikit-learn matplotlib folium",
            s,
        )
    )
    story.append(
        Paragraph(
            "<b>Field-verified result</b> (QGIS 3.44.12, after running the command above): every required "
            "package in the Dependencies tab flipped to Ready; rasterio coexisted with QGIS's own GDAL in the "
            "same process without conflict (CRS lookups etc. worked normally); and <b>both Validate Inputs and "
            "a full pipeline run (Run Analysis, with spatial statistics and experimental ML enabled) succeeded "
            "start to finish in Embedded mode</b> (514 change features, Global Moran's I = 0.804 \u2014 a sane "
            "value). This was verified for this specific QGIS-version / package-version combination; other "
            "QGIS/OS combinations could in theory still hit a GDAL version conflict (Option 2 below eliminates "
            "that risk entirely).",
            s["highlight"],
        )
    )

    story.append(
        Paragraph("Option 2 (isolated, safer): separate .venv + External interpreter", s["h3"])
    )
    story.append(
        Paragraph(
            "Option 1 loads a second GDAL into the same process as QGIS, which carries a theoretical conflict "
            "risk depending on the QGIS build. If you want full isolation (so nothing you install can affect "
            "QGIS itself or other plugins), create an independent <font face='Courier'>.venv</font> that runs "
            "in a separate process, and point the plugin at it via <b>External interpreter</b> mode. Follow "
            "PART B's B.2 installation steps to create the <font face='Courier'>.venv</font>, then set that "
            "environment's <font face='Courier'>python.exe</font> path in the Dock Widget's Dependencies tab.",
            s["body"],
        )
    )
    story.append(
        make_table(
            ["", "Option 1: install into QGIS's own Python", "Option 2: separate .venv"],
            [
                ["Extra folder needed", "No", "Yes (.venv/)"],
                [
                    "Execution process",
                    "Same process as QGIS (embedded)",
                    "Separate process (external call)",
                ],
                [
                    "Setup steps",
                    "One pip command",
                    "Create .venv + install + set the path in the Dependencies tab",
                ],
                [
                    "GDAL conflict risk",
                    "Theoretical (none observed on QGIS 3.44.12 in testing)",
                    "None (fully isolated separate process)",
                ],
                [
                    "Speed",
                    "Slightly faster (no process-spawn overhead)",
                    "Slightly slower (a new process per run)",
                ],
                [
                    "Recommended for",
                    "Wanting something quick and simple",
                    "Not wanting to affect other QGIS plugins/projects",
                ],
            ],
            s,
            col_widths=[90, 205, 155],
        )
    )

    story.append(Paragraph("A.5 Dock Widget \u2014 All 6 Tabs, Every Field", s["h2"]))

    story.append(Paragraph("\u2460 Inputs tab", s["h3"]))
    story.append(
        make_table(
            ["Field", "Description"],
            [
                [
                    "Before / After Sentinel-2 folder",
                    "Each folder must contain B02/B03/B04 GeoTIFF or JP2 files <b>directly</b> (not in a "
                    "subfolder). Example: inputs/data/sentinel2_20230812",
                ],
                [
                    "AOI vector file",
                    "GeoJSON, GeoPackage, or Shapefile. Does not need to be in WGS84 \u2014 it is automatically "
                    "reprojected to match the raster CRS",
                ],
                [
                    "Output directory",
                    "Where results are written. Created automatically if it doesn't exist",
                ],
                [
                    "Run label",
                    "Optional label to tell runs apart. Prepended to the run_id and shown in the layer group "
                    "name / run_metadata. Left blank, only a timestamp is used",
                ],
                [
                    "Validate Inputs button",
                    "Checks CRS, resolution, and band presence, then shows a Valid / Valid with warnings / "
                    "Invalid badge plus a band metadata table",
                ],
                [
                    "Clear Inputs (reset) button",
                    "(New) Clears all four path fields, the Run label, and the validation display. Also "
                    "clears the values persisted from the previous session, so stale paths don't linger after "
                    "restarting QGIS. Does not touch settings in other tabs (Change Detection, etc.)",
                ],
            ],
            s,
            col_widths=[130, 310],
        )
    )

    story.append(Paragraph("\u2461 Change Detection tab", s["h3"]))
    story.append(
        make_table(
            ["Field", "Description"],
            [
                [
                    "Method",
                    "Provided baseline (example method only) / Robust RGB CVA (improved method only) / "
                    "<b>Run both (default, runs both and compares)</b>",
                ],
                [
                    "Radiometric normalization",
                    "None (no correction) / <b>Robust median/MAD (default)</b> \u2014 linear matching using the "
                    "median and MAD of valid pixels common to both dates / Percentile matching \u2014 matched "
                    "using the 2nd/98th percentiles / PIF (Pseudo-Invariant Features) \u2014 linear regression "
                    "over pixels with low change only",
                ],
                [
                    "Threshold method",
                    "<b>Otsu (default)</b> \u2014 automatic binarization / Percentile \u2014 flags anything above "
                    "a given percentile as change / Manual \u2014 an explicit absolute value",
                ],
                [
                    "Morphology",
                    "Whether to apply opening/closing morphological operations to the binary raster, and the "
                    "kernel size (px)",
                ],
                [
                    "Minimum change area",
                    "Connected components smaller than this are treated as noise and dropped (in m\u00b2; "
                    "converted automatically from pixel area)",
                ],
            ],
            s,
            col_widths=[100, 340],
        )
    )

    story.append(Paragraph("\u2462 Spatial Analysis tab", s["h3"]))
    story.append(
        make_table(
            ["Field", "Description"],
            [
                [
                    "Enable spatial statistics",
                    "Turns on grid-aggregated spatial statistics (on by default)",
                ],
                [
                    "Grid cell size",
                    "Side length of the analysis grid, in meters. Default 150 m \u2014 statistics are computed "
                    "after aggregating to this grid rather than at pixel resolution, to avoid a dense spatial "
                    "weight matrix",
                ],
                [
                    "Spatial weights",
                    "Queen contiguity (default, shares an edge or a corner) / Rook contiguity (edge only) / "
                    "K nearest neighbors",
                ],
                [
                    "Permutations",
                    "Number of Monte Carlo permutation-test iterations (default 999, reproducible via a fixed seed)",
                ],
                ["Significance alpha", "Significance level (default 0.05)"],
                [
                    "FDR correction",
                    "Benjamini-Hochberg correction \u2014 mitigates the inflated significance that comes from "
                    "testing many locations at once with Gi*",
                ],
                [
                    "Global/Local Moran's I",
                    "Global: spatial autocorrelation of overall change intensity. Local (LISA): per-cell "
                    "High-High / Low-Low / High-Low / Low-High cluster classification",
                ],
                [
                    "Getis-Ord Gi*",
                    "Detects statistically significant hot spots / cold spots (90/95/99% bands)",
                ],
                [
                    "Experimental unsupervised spatial ML",
                    "Since there is no ground truth at all, a warning is always shown on screen. Choose "
                    "Isolation Forest (anomaly score) or DBSCAN (spatial clustering), with tunable "
                    "hyperparameters (contamination / eps / min_samples, etc.)",
                ],
            ],
            s,
            col_widths=[130, 310],
        )
    )

    story.append(Paragraph("\u2463 Outputs tab", s["h3"]))
    story.append(
        bullet_list(
            [
                "Whether to keep intermediate GeoTIFFs/stacks, whether to build the interactive map, whether "
                "to auto-apply QML styling",
                "Whether to auto-load results into the current QGIS project, and whether to zoom to them afterward",
                "Whether to keep temporary files from a failed or cancelled run",
            ],
            s,
        )
    )

    story.append(Paragraph("\u2464 Run &amp; Results tab", s["h3"]))
    story.append(
        bullet_list(
            [
                "<b>Run Analysis</b> \u2014 shows a progress bar, current stage, elapsed time, and a live log",
                "<b>Cancel</b> \u2014 safe to stop at any point (atomic file writes ensure a partial output is "
                "never mistaken for a completed result)",
                "On completion, a summary (feature count, total changed area, Global Moran's I, permutation "
                "p-value, 95% hotspot count, mean confidence, run time) is shown alongside <b>Open Report / "
                "Open Interactive Map / Open Output Folder / Add Results to Map / Copy Summary / Save Log</b> "
                "buttons",
            ],
            s,
        )
    )

    story.append(Paragraph("\u2465 Dependencies tab", s["h3"]))
    story.append(
        bullet_list(
            [
                "Execution environment: Automatic (default \u2014 embedded when possible, external otherwise) / "
                "force Embedded / force External",
                "Set an External interpreter path and check its package status live with the <b>Check "
                "dependencies</b> button",
                "A Ready/Missing table per package, including version info",
                "Restore defaults / Import configuration YAML / Export configuration YAML",
            ],
            s,
        )
    )

    story.append(Paragraph("A.6 Run Progress (12 Stages)", s["h2"]))
    story.append(
        make_table(
            ["Progress", "Stage"],
            [
                ["0\u20135%", "Input discovery \u2014 locating B02/B03/B04 files"],
                [
                    "5\u201312%",
                    "Validation \u2014 CRS / transform / dimensions / AOI overlap checks",
                ],
                [
                    "12\u201322%",
                    "Raster alignment \u2014 grid alignment (resampling if needed), AOI masking",
                ],
                [
                    "22\u201330%",
                    "Stack creation \u2014 building the RGB-ordered band-stack GeoTIFF",
                ],
                ["30\u201342%", "Radiometric normalization \u2014 applying the chosen correction"],
                ["42\u201355%", "Baseline detection \u2014 example-method change detection"],
                ["55\u201368%", "Robust CVA \u2014 improved-method change detection"],
                [
                    "68\u201375%",
                    "Threshold &amp; morphology \u2014 binarization plus post-processing",
                ],
                ["75\u201382%", "Polygon extraction \u2014 vectorization, confidence scoring"],
                ["82\u201390%", "Spatial statistics \u2014 Moran's I / Gi* / FDR"],
                [
                    "90\u201394%",
                    "Experimental spatial ML \u2014 (if enabled) Isolation Forest / DBSCAN",
                ],
                [
                    "94\u2013100%",
                    "Database, visualization &amp; report \u2014 GeoPackage, figures, map, report.md",
                ],
            ],
            s,
            col_widths=[80, 360],
        )
    )

    story.append(Paragraph("A.7 Result Layer Tree", s["h2"]))
    story.append(
        code_block(
            "Solafune Change Analysis - <run id>\n"
            "  Inputs\n"
            "    AOI, Before RGB, After RGB\n"
            "  Change Detection\n"
            "    Baseline Intensity/Binary, CVA Intensity/Binary, Change Features\n"
            "  Spatial Statistics\n"
            "    Analysis Grid, LISA Clusters, Gi* Hotspots\n"
            "  Experimental ML\n"
            "    Spatial Anomalies (only if ml_enabled=True)",
            s,
        )
    )
    story.append(
        Paragraph(
            "Each layer gets a pre-built QML style applied automatically (continuous rasters have their color "
            "ramp rescaled at runtime to the actual data range). Groups for results that don't exist for a "
            "given run (e.g. Spatial Anomalies when ML is disabled) are simply not created.",
            s["body"],
        )
    )

    story.append(Paragraph("A.8 Using the Processing Toolbox", s["h2"]))
    story.append(
        Paragraph(
            "The same engine can also be run from Processing Toolbox &rarr; <b>Solafune Geospatial Analytics "
            "&rarr; Sentinel-2 Change Analysis</b> (15 parameters, useful for batch processing and Model "
            "Builder integration). It goes through the same request builder as the dock widget and calls the "
            "same <font face='Courier'>run_pipeline()</font>, so the analysis logic is never duplicated.",
            s["body"],
        )
    )

    story.append(Paragraph("A.9 Before/After Comparison", s["h2"]))
    story.append(
        Paragraph(
            "Toggle the visibility checkboxes on the \u201cBefore RGB\u201d/\u201cAfter RGB\u201d layers in the "
            "result layer group, or adjust their opacity in the layer panel, to compare the two dates. The RGB "
            "stretch is applied consistently across both dates (the 2nd/98th-percentile stretch computed on the "
            "before image is reused for the after image), so the visual comparison isn't skewed by "
            "independently-stretched images.",
            s["body"],
        )
    )

    story.append(Paragraph("A.10 Troubleshooting", s["h2"]))
    story.append(
        make_table(
            ["Symptom", "Cause / fix"],
            [
                [
                    "An error dialog on \u201cValidate Inputs\u201d (used to be a hard crash)",
                    "rasterio, etc. missing from the embedded Python \u2014 check status in the Dependencies "
                    "tab, install via Option 1 or 2 in A.4",
                ],
                [
                    "Before/After folder selected but no bands are found",
                    "B02/B03/B04 files must sit directly inside the folder (not in a subfolder)",
                ],
                [
                    "Stale paths from a previous session keep reappearing",
                    "Use the <b>Clear Inputs</b> button on the Inputs tab to clear both the fields and the "
                    "persisted values",
                ],
                [
                    "Results are written to an unexpected folder (e.g. under some unknown temp directory)",
                    "This was a bug in an earlier version (processed_dir path computation) \u2014 fixed in the "
                    "current version; the path is now always computed correctly relative to the output directory",
                ],
                [
                    "Run Analysis doesn't seem to progress",
                    "Check the \u201cSolafune Change Analyzer\u201d tab under QGIS's \u201cView \u2192 Panels "
                    "\u2192 Log Messages\u201d panel for detailed logs",
                ],
                [
                    "Result layers don't appear",
                    "Check whether \u201cLoad results into current QGIS project\u201d is enabled on the Outputs tab",
                ],
                [
                    "External-mode run never finishes",
                    "Confirm the interpreter path points at an actual python.exe (not a .bat file or shortcut), "
                    "and that pip install -e . has been run in that environment",
                ],
            ],
            s,
            col_widths=[165, 245],
        )
    )

    story.append(Paragraph("A.11 Checksum Verification (Optional)", s["h2"]))
    story.append(
        Paragraph(
            "Run this in PowerShell or Command Prompt and compare the printed hash against the contents of "
            "<font face='Courier'>solafune_change_analyzer.zip.sha256</font>.",
            s["body"],
        )
    )
    story.append(code_block("certutil -hashfile solafune_change_analyzer.zip SHA256", s))
    story.append(PageBreak())

    # ================================================================== PART B
    story.append(Paragraph("PART B. Script (CLI) Edition", s["h1"]))

    story.append(Paragraph("B.1 Prerequisites", s["h2"]))
    story.append(
        bullet_list(
            [
                "Python 3.10 or later (developed/tested on 3.12)",
                "Install package: <font face='Courier'>solafune-sentinel2-change-source.zip</font>",
            ],
            s,
        )
    )

    story.append(Paragraph("B.2 Installation Steps", s["h2"]))
    story.append(
        Paragraph(
            "1) Unzip (folder name ends in -master, matching GitHub's Download ZIP layout)",
            s["body"],
        )
    )
    story.append(
        code_block(
            "unzip solafune-sentinel2-change-source.zip\n" "cd solafune-sentinel2-change-master",
            s,
        )
    )
    story.append(Paragraph("2) Create a virtual environment", s["body"]))
    story.append(code_block("python -m venv .venv", s))
    story.append(Paragraph("3) Install dependencies", s["body"]))
    story.append(
        code_block(
            ".venv\\Scripts\\pip install --upgrade pip\n"
            ".venv\\Scripts\\pip install -r requirements-dev.txt\n"
            ".venv\\Scripts\\pip install -e .",
            s,
        )
    )
    story.append(
        Paragraph(
            "On macOS/Linux, replace <font face='Courier'>.venv\\Scripts\\pip</font> with "
            "<font face='Courier'>source .venv/bin/activate</font> followed by "
            "<font face='Courier'>pip ...</font>.",
            s["body"],
        )
    )

    story.append(Paragraph("B.3 One-Line Run (Recommended)", s["h2"]))
    story.append(code_block("solafune-change all --config config/default.yaml", s))
    story.append(
        Paragraph(
            "The full pipeline finishes in roughly 30 seconds; results land in "
            "<font face='Courier'>outputs/</font> and <font face='Courier'>data/processed/</font>.",
            s["body"],
        )
    )

    story.append(Paragraph("B.4 Individual CLI Commands", s["h2"]))
    story.append(
        make_table(
            ["Command", "Description"],
            [
                [
                    "solafune-change validate --config &lt;yaml&gt;",
                    "Validates inputs only (dry run)",
                ],
                ["solafune-change run --config &lt;yaml&gt;", "Runs the full pipeline"],
                ["solafune-change stats --config &lt;yaml&gt;", "Forces spatial statistics on"],
                [
                    "solafune-change report --config &lt;yaml&gt;",
                    "Regenerates report.md from a prior run",
                ],
                ["solafune-change all --config &lt;yaml&gt;", "validate then run (recommended)"],
                ["python -m solafune_change --help", "Same as above, invoked as a module"],
            ],
            s,
            col_widths=[260, 210],
            mono_cols={0},
        )
    )

    story.append(Paragraph("B.5 Full Option Reference", s["h2"]))
    story.append(
        make_table(
            ["Option", "Description"],
            [
                ["--before / --after / --aoi / --output-dir", "Path overrides"],
                ["--method baseline|cva|both", "Analysis method (default both)"],
                ["--threshold-method otsu|percentile|manual", "Threshold method"],
                ["--percentile N", "Percentile for the percentile method"],
                ["--threshold-value N", "Absolute value for the manual method"],
                ["--min-area-m2 N", "Minimum change-feature area"],
                ["--grid-size-m N", "Spatial-statistics grid size"],
                ["--permutations N", "Number of permutations"],
                ["--seed N", "Random seed"],
                ["--ml / --no-ml", "Toggle experimental ML on/off"],
                [
                    "--json-progress",
                    "JSON Lines progress output (used for external/plugin execution)",
                ],
                ["-v / --verbose", "Debug-level logging"],
            ],
            s,
            col_widths=[190, 280],
            mono_cols={0},
        )
    )
    story.append(Paragraph("Example", s["h3"]))
    story.append(
        code_block(
            "solafune-change run --config config/default.yaml \\\n"
            "  --threshold-method percentile --percentile 97 \\\n"
            "  --min-area-m2 900 --grid-size-m 200 --seed 7 --ml",
            s,
        )
    )

    story.append(Paragraph("B.6 Output File Locations", s["h2"]))
    story.append(
        make_table(
            ["Path", "Contents"],
            [
                ["data/processed/sentinel2_&lt;date&gt;_stack.tif", "RGB-ordered band stack"],
                [
                    "data/processed/{baseline,cva}_change_{intensity,binary}.tif",
                    "Four change-detection rasters",
                ],
                [
                    "outputs/database/change_analysis.gpkg",
                    "GeoPackage (SQLite-based spatial database)",
                ],
                [
                    "outputs/figures/change_comparison.png",
                    "Baseline vs. CVA vs. Gi* comparison figure",
                ],
                ["outputs/maps/interactive_map.html", "Interactive map (fully offline)"],
                [
                    "outputs/statistics/global_moran.json, spatial_statistics.csv",
                    "Spatial-statistics values",
                ],
                [
                    "outputs/qgis/styles/*.qml, solafune_change_analyzer.zip",
                    "QGIS styles, plugin zip",
                ],
                [
                    "outputs/{summary,run_manifest,quality_report}.json, report.md",
                    "Summary, metadata, and report",
                ],
            ],
            s,
            col_widths=[280, 175],
            mono_cols={0},
        )
    )

    story.append(Paragraph("B.7 Rebuilding the QGIS Plugin ZIP", s["h2"]))
    story.append(
        code_block(
            "python scripts/build_qgis_plugin.py\n"
            "python scripts/validate_qgis_plugin.py outputs/qgis/solafune_change_analyzer.zip",
            s,
        )
    )

    story.append(Paragraph("B.8 Regenerating This PDF", s["h2"]))
    story.append(
        Paragraph(
            "This PDF is itself generated by a script (a reportlab script that embeds the Malgun Gothic font, "
            "which also renders Latin text cleanly).",
            s["body"],
        )
    )
    story.append(
        code_block("python scripts/generate_submission_pdf.py --out submission/Usage_Guide.pdf", s)
    )

    story.append(Paragraph("B.9 Tests / Code Quality", s["h2"]))
    story.append(
        code_block(
            "python -m pytest tests/ -v\n"
            "ruff check .\n"
            "black --check src/ tests/ scripts/ qgis_plugin/solafune_change_analyzer --exclude vendor",
            s,
        )
    )

    story.append(Paragraph("B.10 Full config/default.yaml Field Reference", s["h2"]))
    story.append(
        make_table(
            ["Section.field", "Default", "Description"],
            [
                ["paths.aoi/before_folder/after_folder", "-", "Required input paths"],
                ["paths.output_dir", "outputs", "Output directory"],
                [
                    "paths.processed_dir",
                    "(auto-computed from output_dir if unset)",
                    "Intermediate GeoTIFF folder",
                ],
                [
                    "preprocessing.normalization",
                    "robust_median_mad",
                    "none / robust_median_mad / percentile_matching / pif_linear",
                ],
                ["preprocessing.reflectance_scale", "10000.0", "DN-to-reflectance scale factor"],
                ["change_detection.method", "both", "baseline / cva / both"],
                ["change_detection.threshold_method", "otsu", "otsu / percentile / manual"],
                ["change_detection.min_area_m2", "400.0", "Minimum change-feature area"],
                [
                    "change_detection.morphology.*",
                    "opening_then_closing, 3px",
                    "Morphological post-processing",
                ],
                ["spatial_statistics.enabled", "true", "Toggle spatial statistics"],
                ["spatial_statistics.grid_size_m", "150.0", "Analysis grid size"],
                ["spatial_statistics.weights", "queen", "queen / rook / knn"],
                ["spatial_statistics.permutations", "999", "Number of permutations"],
                ["spatial_statistics.fdr_correction", "true", "Toggle BH-FDR correction"],
                ["spatial_ml.enabled", "false", "Toggle experimental ML (opt-in)"],
                ["spatial_ml.model", "isolation_forest", "isolation_forest / dbscan"],
                ["run.random_seed", "42", "Global reproducibility seed"],
            ],
            s,
            col_widths=[150, 145, 155],
            mono_cols={0},
        )
    )

    story.append(Paragraph("B.11 Troubleshooting", s["h2"]))
    story.append(
        make_table(
            ["Symptom", "Cause / fix"],
            [
                [
                    "\u201ccommand not found: solafune-change\u201d",
                    "Virtual environment not activated, or pip install -e . was not run",
                ],
                [
                    "CRS/band errors on the input files",
                    "Diagnose first with solafune-change validate --config ...",
                ],
                ["Run is slow or hangs", "Retry with a larger grid-size-m or fewer permutations"],
                [
                    "Result numbers differ from report.md",
                    "Confirm you re-ran with the same seed and config (reproducibility is guaranteed when they match)",
                ],
            ],
            s,
            col_widths=[165, 245],
        )
    )
    story.append(PageBreak())

    # ================================================================== 2. Actual results
    story.append(Paragraph("2. Actual Analysis Results (config/default.yaml, seed=42)", s["h1"]))
    story.append(
        make_table(
            ["Metric", "Value"],
            [
                ["Change feature count", "514"],
                ["Total changed area", "37,405,887 m\u00b2 (14.14% of AOI)"],
                ["Primary method / threshold", "Robust CVA / Otsu (value = 5.2199)"],
                [
                    "Vs. baseline",
                    "baseline flags 47.85% of pixels as changed (far noisier than CVA's 15.32%)",
                ],
                [
                    "Global Moran's I",
                    "0.8335 (E[I]=-0.0001, z=178.37, permutation p=0.001, 999 permutations, seed=42)",
                ],
                ["Features overlapping a 95%+ Gi* hotspot", "95"],
                ["Largest change feature", "15,987,700 m\u00b2"],
                [
                    "Experimental ML (Isolation Forest, opt-in)",
                    "Top-K outlier stability (spatial block bootstrap) = 0.72",
                ],
                ["Run time", "~30 seconds (full pipeline, CLI)"],
            ],
            s,
            col_widths=[190, 265],
        )
    )
    story.append(
        Paragraph(
            "Interpretation: the strong, statistically significant spatial clustering of change "
            "(Moran's I = 0.834, p = 0.001) is consistent with genuine, structured surface change rather than "
            "noise \u2014 clustering is exactly what real, connected surface disturbance (excavation, waste-rock "
            "placement, land clearing, vegetation removal) would produce, and exactly what random sensor or "
            "atmospheric noise would not. However, two RGB-only dates cannot by themselves confirm which of "
            "those specific activities is responsible, and cannot rule out non-mining confounds. Both "
            "report.md and this guide deliberately use \u201cconsistent with\u201d phrasing and stop short of any "
            "definitive land-use classification.",
            s["body"],
        )
    )
    story.append(
        Paragraph(
            "Interpreting uncertainty: real change vs. clouds, shadow, season, brightness", s["h3"]
        )
    )
    story.append(
        Paragraph(
            "Each alternative explanation for a detection is addressed explicitly below, rather than assumed "
            "away:",
            s["body"],
        )
    )
    story.append(
        make_table(
            [
                "Possible confound",
                "Could it explain a detection here?",
                "How this pipeline addresses it",
            ],
            [
                [
                    "Clouds / cloud shadow",
                    "Not ruled out \u2014 no Scene Classification Layer (SCL) or cloud mask was supplied",
                    "Not filtered; explicitly flagged as an unresolved limitation, never silently ignored",
                ],
                [
                    "Terrain / pit-wall shadow",
                    "Possible at steep pit edges where illumination geometry differs slightly between dates",
                    "Robust median/MAD normalization plus Otsu thresholding reduce (not eliminate) shadow-driven false positives; morphological opening removes single-pixel shadow speckle",
                ],
                [
                    "Seasonal change (vegetation, soil moisture)",
                    "Low risk for this pair (~3 weeks apart), but not verified in general",
                    "Cannot be separated from persistent change with only two dates; a denser time series is recommended in report.md's Operational Recommendations",
                ],
                [
                    "Whole-scene brightness / illumination difference",
                    "Likely present to some degree between any two acquisitions",
                    "Directly targeted by the robust_median_mad radiometric-normalization step before CVA is computed \u2014 this is precisely why baseline (no normalization) is far noisier than CVA",
                ],
                [
                    "Small co-registration offset",
                    "Possible at sharp edges (pit rim, road margins)",
                    "Not explicitly corrected; the minimum-change-area filter (400 m\u00b2) removes some of the resulting small spurious polygons",
                ],
            ],
            s,
            col_widths=[110, 165, 180],
        )
    )
    story.append(
        Paragraph(
            "None of these confounds can be fully excluded with two RGB-only dates and no cloud mask. This "
            "table is reproduced verbatim in <font face='Courier'>report.md</font> Section 5 (Interpretation), "
            "so it travels with every run, not just this document.",
            s["caption"],
        )
    )

    # ================================================================== 3. Algorithm rationale
    story.append(Paragraph("3. Algorithm Choices and Rationale", s["h1"]))
    story.append(Paragraph("Baseline (reimplementation of the provided example)", s["h3"]))
    story.append(
        Paragraph(
            "Computes per-pixel multi-band Euclidean distance and min-max normalizes it. Because it applies no "
            "radiometric correction and uses global min-max scaling, a single extreme-value pixel can distort "
            "the entire intensity scale \u2014 this weakness was deliberately preserved by reimplementing the "
            "example's core idea faithfully (not copied; an independent implementation with type hints, "
            "logging, and error handling).",
            s["body"],
        )
    )
    story.append(Paragraph("Robust RGB CVA (primary method)", s["h3"]))
    story.append(
        Paragraph(
            "Per-band differences are standardized by median/MAD before being combined: "
            "<font face='Courier'>z_b = (diff_b - median(diff_b)) / (1.4826 * MAD(diff_b))</font>, "
            "<font face='Courier'>CVA = sqrt(z_B04^2 + z_B03^2 + z_B02^2)</font>. If MAD is close to zero, the "
            "standard deviation is used as a safe fallback. In practice, CVA flags only 15.32% of pixels as "
            "changed versus baseline's 47.85%, confirming it is markedly less sensitive to noise.",
            s["body"],
        )
    )
    story.append(Paragraph("Spatial statistics", s["h3"]))
    story.append(
        Paragraph(
            "Rather than building a dense pixel-level spatial weight matrix, values are first aggregated to a "
            "150 m grid (11,967 cells), then Global/Local Moran's I is computed with Queen contiguity weights "
            "and Getis-Ord Gi* with binary weights. Gi* p-values are corrected with the Benjamini-Hochberg FDR "
            "procedure.",
            s["body"],
        )
    )
    story.append(Paragraph("Experimental unsupervised spatial ML", s["h3"]))
    story.append(
        Paragraph(
            "With no ground truth available, accuracy/precision/recall are never claimed. Instead, a spatial "
            "block bootstrap is used to diagnose whether the top-ranked outliers stay stable under "
            "resampling. It is disabled by default (opt-in), and every surface \u2014 UI and documentation "
            "alike \u2014 explicitly labels it as \u201cexploratory.\u201d",
            s["body"],
        )
    )
    story.append(Paragraph("Why GeoPackage as the database", s["h3"]))
    story.append(
        Paragraph(
            "The assignment's SQLite requirement is satisfied by GeoPackage, an OGC standard that is itself a "
            "SQLite file \u2014 openable with no server, and backed by a real geometry column and spatial index "
            "rather than WKT text.",
            s["body"],
        )
    )
    story.append(PageBreak())

    # ================================================================== 4. DB schema
    story.append(Paragraph("4. Full Spatial Database Schema", s["h1"]))
    story.append(Paragraph("change_features (514 rows, MULTIPOLYGON, EPSG:32735)", s["h3"]))
    story.append(
        make_table(
            ["Field", "Description"],
            [
                ["id", "Feature ID"],
                ["date_before / date_after", "Compared acquisition dates (20230812 / 20230902)"],
                ["method / threshold_method / threshold_value", "Method and threshold used"],
                [
                    "area_m2 / perimeter_m / compactness",
                    "Area / perimeter / Polsby-Popper compactness",
                ],
                [
                    "mean_change / max_change / p95_change",
                    "Change-intensity statistics within the feature",
                ],
                [
                    "confidence",
                    "A 0-1 heuristic score (not a calibrated probability) \u2014 weighted combination of "
                    "threshold-exceedance magnitude, consistency, size, hotspot significance, and ML rank",
                ],
                [
                    "gi_zscore / gi_pvalue / gi_qvalue / hotspot_class",
                    "Getis-Ord Gi* results (q is the FDR-corrected value)",
                ],
                ["lisa_cluster", "Local Moran's I cluster type (e.g. High-High)"],
                ["ml_anomaly_score / ml_cluster_id", "(If ML enabled) outlier score / cluster ID"],
                ["geom", "The actual geometry column (MULTIPOLYGON)"],
            ],
            s,
            col_widths=[140, 320],
            mono_cols={0},
        )
    )
    story.append(Paragraph("spatial_grid (11,967 cells, POLYGON)", s["h3"]))
    story.append(
        Paragraph(
            "Per-cell mean/median/p90/p95 CVA, changed_proportion, mean per-band difference, local_std_cva, "
            "plus the same Gi*/LISA/ML fields found on change_features.",
            s["body"],
        )
    )
    story.append(Paragraph("run_metadata (1 row per run)", s["h3"]))
    story.append(
        Paragraph(
            "run_id, timestamp, input paths, CRS/resolution, method/normalization/threshold parameters, "
            "spatial_statistics/spatial_ml enabled flags, package_version, random_seed \u2014 everything needed "
            "to reproduce the run.",
            s["body"],
        )
    )
    story.append(Paragraph("quality_checks", s["h3"]))
    story.append(
        Paragraph("Warnings/errors raised during validation (zero for this run).", s["body"])
    )
    story.append(PageBreak())

    # ================================================================== 5. Bugs
    story.append(Paragraph("5. Bugs Actually Found and Fixed During Development", s["h1"]))
    story.append(
        Paragraph(
            "These are problems actually reproduced through running, testing, or real usage \u2014 not "
            "hypothetical issues found by code review alone.",
            s["body"],
        )
    )
    story.append(
        make_table(
            ["Bug", "How it was found", "Fix"],
            [
                [
                    "QGIS \u201cValidate Inputs\u201d crash",
                    "Clicked after installing on a real QGIS instance \u2192 rasterio missing, "
                    "ModuleNotFoundError propagated uncaught",
                    "Check dependencies up front and fall back to the External interpreter automatically, or "
                    "show a friendly dialog otherwise",
                ],
                [
                    "processed_dir path miscomputed",
                    "Reported that results were being written under an unrelated temp folder during real "
                    "usage \u2192 traced the root cause",
                    "Now always computed as an absolute path relative to output_dir; two regression tests added",
                ],
                [
                    "write_intermediate setting silently ignored",
                    "Found during a full code review",
                    "Now actually controls whether intermediate GeoTIFFs are saved",
                ],
                [
                    "run_label value was discarded",
                    "Found in the same review",
                    "Now sanitized into run_id and shown in the layer group name / run_metadata",
                ],
                [
                    "Intermittent matplotlib TclError",
                    "Test suite occasionally failed at random \u2014 initially misdiagnosed as a PROJ issue, "
                    "traced via the actual traceback",
                    "Forced the non-interactive Agg backend before importing pyplot (no recurrence over 5 "
                    "consecutive runs)",
                ],
                [
                    "Crash when polygonization yields zero features",
                    "Found while testing the extreme case where min_area filters out every feature",
                    "Empty GeoDataFrame now created with an explicit schema",
                ],
                [
                    "Garbled Korean text in PDF code blocks",
                    "Found while reviewing an earlier draft of this document",
                    "Courier-styled code blocks are ASCII-only; localized text was moved to separate "
                    "paragraphs/tables",
                ],
                [
                    "Possible unguarded CRS lookup failure at runtime",
                    "Found while reproducing a PROJ conflict in the development environment",
                    "Added defensive handling so a PROJ lookup failure can't propagate uncaught",
                ],
            ],
            s,
            col_widths=[95, 175, 190],
        )
    )

    # ================================================================== 6. Tests
    story.append(Paragraph("6. Test and Verification Record", s["h1"]))
    story.append(
        bullet_list(
            [
                "<b>All 65 pytest cases pass</b> \u2014 synthetic-data unit tests + real-data integration tests "
                "+ 2 processed_dir regression tests",
                "<b>ruff check ., black --check</b> clean",
                "<b>Verified against a real QGIS 3.44.12 install</b>: plugin lifecycle, no duplicate "
                "registration on reload, Processing provider registration/teardown, Dependencies tab checked "
                "live, the on_validate crash reproduced and re-verified as fixed, Clear Inputs button behavior, "
                "and a full pipeline run succeeding via the no-venv (embedded) install path",
                "<b>Real-data pipeline run</b>: GeoTIFF/GeoPackage re-opened and checked after the run, all 9 "
                "queries in docs/example_queries.sql executed successfully against the real database",
                "<b>Reproducibility</b>: running twice with the same seed produces numerically identical results",
            ],
            s,
        )
    )

    # ================================================================== 7. Limitations
    story.append(Paragraph("7. Key Assumptions and Limitations", s["h1"]))
    story.append(
        bullet_list(
            [
                "Assumes a Sentinel-2 reflectance scale factor of 10000 (no metadata was provided; standard "
                "ESA convention applied)",
                "Band stack order is R-G-B (B04, B03, B02)",
                "No B08 (NIR) band, so NDVI cannot be computed",
                "No cloud/shadow mask (SCL) \u2014 cloud contamination cannot be ruled out",
                "Only two acquisition dates, so seasonal effects cannot be separated from permanent change",
                "No ground truth \u2014 accuracy/precision/recall are never claimed anywhere",
                "confidence is an explicit heuristic score, not a calibrated probability",
                "Gi*/Moran's I significance describes spatial pattern only; it does not establish a cause "
                "(e.g. mining activity)",
            ],
            s,
        )
    )
    story.append(PageBreak())

    # ================================================================== Appendix
    story.append(Paragraph("Appendix A. Example SQL Queries", s["h1"]))
    story.append(
        Paragraph(
            "<font face='Courier'>docs/example_queries.sql</font> contains 9 queries, all executed against the "
            "real database as part of verification. A representative example:",
            s["body"],
        )
    )
    story.append(
        code_block(
            "-- Top 10 change features by area\n"
            "SELECT id, area_m2, mean_change, confidence, hotspot_class\n"
            "FROM change_features ORDER BY area_m2 DESC LIMIT 10;\n\n"
            "-- Change features intersecting a 95%+ significance hotspot\n"
            "SELECT id, area_m2, gi_zscore, gi_qvalue\n"
            "FROM change_features WHERE hotspot_class IN ('hot_95','hot_99');",
            s,
        )
    )

    story.append(Paragraph("Appendix B. Glossary", s["h1"]))
    story.append(
        make_table(
            ["Term", "Description"],
            [
                [
                    "CVA",
                    "Change Vector Analysis \u2014 combines multi-band change into a single vector magnitude",
                ],
                ["MAD", "Median Absolute Deviation \u2014 an outlier-robust measure of dispersion"],
                [
                    "Moran's I",
                    "Global spatial-autocorrelation index (-1 to 1; positive = clustered, negative = dispersed)",
                ],
                [
                    "LISA",
                    "Local Indicators of Spatial Association \u2014 cluster classification based on Local Moran's I",
                ],
                ["Getis-Ord Gi*", "Statistical significance test for local hot/cold spots"],
                [
                    "FDR",
                    "False Discovery Rate \u2014 controls the false-positive rate under multiple testing",
                ],
                ["confidence", "A 0-1 heuristic score, not a calibrated probability"],
                ["GeoPackage", "An OGC-standard spatial data format, internally a SQLite file"],
            ],
            s,
            col_widths=[100, 335],
        )
    )
    story.append(Spacer(1, 10))
    story.append(hr())
    story.append(
        Paragraph(
            "The GitHub repository's top-level <font face='Courier'>README.md</font> and "
            "<font face='Courier'>report.md</font> also document this project in English.",
            s["caption"],
        )
    )

    return story


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--font", type=str, default=DEFAULT_FONT, help="Regular TTF path (any Unicode-capable font)"
    )
    parser.add_argument(
        "--font-bold",
        type=str,
        default=DEFAULT_FONT_BOLD,
        help="Bold TTF path (any Unicode-capable font)",
    )
    args = parser.parse_args()

    register_fonts(args.font, args.font_bold)
    styles = build_styles()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(args.out),
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title="Solafune Sentinel-2 Change Analysis - Usage Guide",
        author="Yeon-jun Kim",
    )
    story = build_story(styles)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
