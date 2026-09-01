#!/usr/bin/env python
"""Generates a detailed Korean-language PDF usage guide for the submission bundle.

Covers both the QGIS plugin version and the script/CLI version of
solafune-change, step by step. Requires ``reportlab`` (dev-only dependency;
not part of the core pipeline's runtime requirements) and a Korean-capable
TrueType font on the system (defaults to Windows' bundled Malgun Gothic;
override with --font/--font-bold if unavailable).

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


def register_fonts(regular: str, bold: str) -> None:
    if not Path(regular).exists() or not Path(bold).exists():
        raise SystemExit(
            f"Korean font not found at {regular} / {bold}. "
            "Pass --font/--font-bold pointing at a Korean-capable TTF pair."
        )
    pdfmetrics.registerFont(TTFont("KR", regular))
    pdfmetrics.registerFont(TTFont("KR-Bold", bold))


def build_styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title", fontName="KR-Bold", fontSize=26, leading=32, textColor=NAVY, spaceAfter=6
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName="KR", fontSize=13, leading=18, textColor=GRAY, spaceAfter=4
        ),
        "meta": ParagraphStyle("meta", fontName="KR", fontSize=9.5, leading=13, textColor=GRAY),
        "h1": ParagraphStyle(
            "h1",
            fontName="KR-Bold",
            fontSize=17,
            leading=22,
            textColor=NAVY,
            spaceBefore=16,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName="KR-Bold",
            fontSize=13,
            leading=18,
            textColor=DARK,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "h3",
            fontName="KR-Bold",
            fontSize=11,
            leading=15,
            textColor=ACCENT,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", fontName="KR", fontSize=10, leading=15, textColor=DARK, spaceAfter=6
        ),
        "note": ParagraphStyle(
            "note",
            fontName="KR",
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#8a5a00"),
            backColor=colors.HexColor("#fff6e0"),
            borderColor=colors.HexColor("#e0b84d"),
            borderWidth=0.6,
            borderPadding=6,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "code": ParagraphStyle(
            "code",
            fontName="Courier",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#0a3d0a"),
            backColor=LIGHT_BG,
            borderColor=colors.HexColor("#cccccc"),
            borderWidth=0.5,
            borderPadding=8,
            spaceBefore=4,
            spaceAfter=10,
        ),
        "table_head": ParagraphStyle(
            "table_head", fontName="KR-Bold", fontSize=9, leading=12, textColor=colors.white
        ),
        "table_cell": ParagraphStyle("table_cell", fontName="KR", fontSize=9, leading=13),
        "table_cell_mono": ParagraphStyle(
            "table_cell_mono", fontName="Courier", fontSize=8.3, leading=12
        ),
        "caption": ParagraphStyle(
            "caption", fontName="KR", fontSize=8.5, leading=12, textColor=GRAY
        ),
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
        start="•",
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
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
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
    canvas.drawString(20 * mm, 12 * mm, "Solafune Sentinel-2 Change Analysis — Usage Guide")
    canvas.drawRightString(190 * mm, 12 * mm, f"{doc.page}")
    canvas.restoreState()


def build_story(styles: dict) -> list:
    s = styles
    story: list = []

    # ---------------------------------------------------------------- Title page
    story.append(Spacer(1, 40))
    story.append(Paragraph("Solafune Sentinel-2 Change Analysis", s["title"]))
    story.append(
        Paragraph("사용 설명서 — QGIS 플러그인 버전 &amp; 스크립트(CLI) 버전", s["subtitle"])
    )
    story.append(hr(color=NAVY, thickness=1.4, space_before=10, space_after=16))
    story.append(
        Paragraph(
            "이 문서는 제출 번들(submission/)에 포함된 두 실행 방식 — "
            "① QGIS 안에서 GUI로 실행하는 <b>플러그인 버전</b>과 "
            "② 터미널에서 명령어로 실행하는 <b>스크립트(CLI) 버전</b> — 의 "
            "설치와 사용법을 단계별로 정리합니다. 두 버전 모두 동일한 분석 엔진"
            "(<font face='Courier'>solafune_change</font> 코어 패키지)을 공유하므로 결과가 동일합니다.",
            s["body"],
        )
    )
    story.append(Spacer(1, 14))
    meta_rows = [
        ["GitHub 저장소", "https://github.com/yeonjun7724/solafune-sentinel2-change"],
        ["AOI", "Zambia 노천 광산, 약 264.6 km²"],
        ["비교 대상 시점", "2023-08-12 vs 2023-09-02 (Sentinel-2 B02/B03/B04)"],
        ["대상 QGIS 버전", "3.28 이상 (3.44.12에서 실제 검증)"],
        ["대상 Python 버전", "3.10 이상 (3.12에서 개발/테스트)"],
    ]
    story.append(make_table(["항목", "내용"], meta_rows, s, col_widths=[110, 340]))
    story.append(PageBreak())

    # ---------------------------------------------------------------- 목차 개요
    story.append(Paragraph("0. 제출 번들 구성", s["h1"]))
    story.append(
        Paragraph(
            "<font face='Courier'>submission/</font> 폴더 하나에 아래 세 가지가 함께 들어 있습니다.",
            s["body"],
        )
    )
    story.append(
        make_table(
            ["파일/폴더", "설명", "QGIS 필요?"],
            [
                [
                    "solafune_change_analyzer.zip",
                    "① QGIS 플러그인 설치 파일 (분석 엔진 내장, 이 파일 하나로 설치 완료)",
                    "필요",
                ],
                [
                    "solafune-sentinel2-change-source.zip",
                    "② 스크립트(CLI) 버전 — 전체 소스코드 + 입력 데이터 포함, git archive로 생성한 실제 커밋 스냅샷",
                    "불필요",
                ],
                [
                    "data/",
                    "③ 원본 입력 위성영상 별도 복사본 (확인용, ①·②에는 이미 포함되어 있어 없어도 실행 가능)",
                    "불필요",
                ],
            ],
            s,
            col_widths=[150, 260, 55],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "두 버전 모두 같은 코어 엔진을 쓰기 때문에 분석 로직이 두 벌로 존재하지 않습니다 — "
            "QGIS 플러그인은 이 코어 패키지를 그대로 vendored해서 포함하거나(임베디드 모드), "
            "②번 스크립트 버전의 Python 환경을 그대로 호출해서 실행합니다(외부 인터프리터 모드).",
            s["body"],
        )
    )

    # ================================================================== PART A
    story.append(PageBreak())
    story.append(Paragraph("PART A. QGIS 플러그인 버전 사용법", s["h1"]))

    story.append(Paragraph("A.1 사전 준비", s["h2"]))
    story.append(
        bullet_list(
            [
                "QGIS 3.28 이상 설치 (개발/검증은 QGIS 3.44.12, OSGeo4W 빌드 기준)",
                "설치 파일: <font face='Courier'>solafune_change_analyzer.zip</font> (제출 번들에 포함)",
            ],
            s,
        )
    )

    story.append(Paragraph("A.2 설치 단계", s["h2"]))
    story.append(
        bullet_list(
            [
                "QGIS 실행",
                "메뉴 <b>Plugins → Manage and Install Plugins → Install from ZIP</b> 선택",
                "<font face='Courier'>solafune_change_analyzer.zip</font> 파일 선택 후 <b>Install Plugin</b> 클릭",
                '<b>Installed</b> 탭에서 "Solafune Change Analyzer"가 체크(활성화)되어 있는지 확인',
                "툴바 아이콘 클릭 또는 <b>Plugins → Solafune Change Analyzer</b> 메뉴로 Dock Widget 열기",
            ],
            s,
        )
    )

    story.append(Paragraph("A.3 의존성(Dependencies) 확인 — 반드시 먼저 확인", s["h2"]))
    story.append(
        Paragraph(
            "대부분의 Windows/OSGeo4W QGIS는 <font face='Courier'>rasterio</font>, "
            "<font face='Courier'>scikit-learn</font>, <font face='Courier'>libpysal</font>, "
            "<font face='Courier'>esda</font> 등이 기본 내장되어 있지 않습니다. "
            "Dock Widget의 <b>Dependencies 탭</b>에서 현재 QGIS 내장 Python의 패키지 준비 상태를 "
            "표로 바로 확인할 수 있습니다.",
            s["body"],
        )
    )
    story.append(
        Paragraph(
            '⚠ "Missing"으로 표시된 항목이 있다면 — 특히 rasterio, libpysal, esda, scikit-learn — '
            '"Run Analysis"나 "Validate Inputs"를 눌러도 분석 자체가 되지 않습니다. '
            "아래 A.4 절차대로 <b>External interpreter</b>를 반드시 설정하세요.",
            s["note"],
        )
    )
    story.append(Paragraph("의존성 그룹별 필요 기능", s["h3"]))
    story.append(
        make_table(
            ["패키지 그룹", "필요한 기능"],
            [
                ["numpy, geopandas, shapely, pyproj, scipy, PyYAML", "기본 실행 (설정 파싱 등)"],
                ["rasterio, scikit-image", "래스터 입출력, 변화탐지, 후처리 — 가장 핵심"],
                ["libpysal, esda", "공간통계 (Moran's I, Getis-Ord Gi*)"],
                ["scikit-learn, (선택) hdbscan", "실험적 비지도 공간 ML"],
                ["matplotlib, folium", "정적 그림 / 인터랙티브 지도 시각화"],
            ],
            s,
            col_widths=[220, 245],
        )
    )

    story.append(Paragraph("A.4 External Interpreter 설정 (의존성 부족 시 필수)", s["h2"]))
    story.append(
        Paragraph(
            "PART B(스크립트 버전)를 먼저 압축 해제하고 가상환경을 만들어 두면, 그 Python을 "
            "QGIS 플러그인이 그대로 호출해서 분석/검증을 수행하도록 설정할 수 있습니다.",
            s["body"],
        )
    )
    story.append(
        bullet_list(
            [
                "PART B의 B.2 설치 단계대로 <font face='Courier'>.venv</font> 가상환경을 먼저 만든다",
                "Dock Widget <b>Dependencies 탭</b>으로 이동",
                '"External interpreter" 입력란 옆 <b>...</b> 버튼으로 '
                "<font face='Courier'>...\\.venv\\Scripts\\python.exe</font> 선택",
                '<b>Check dependencies</b> 클릭 → 표의 모든 항목이 "Ready"로 바뀌는지 확인',
                '"Execution environment" 라디오 버튼은 <b>Automatic</b>로 두면 됨 — '
                "임베디드 Python이 부족하면 자동으로 이 외부 인터프리터를 사용합니다",
            ],
            s,
        )
    )

    story.append(Paragraph("A.5 Dock Widget 탭별 사용법", s["h2"]))

    story.append(Paragraph("① Inputs 탭", s["h3"]))
    story.append(
        bullet_list(
            [
                "Before / After Sentinel-2 폴더 선택 (각 폴더는 B02/B03/B04 GeoTIFF 또는 JP2를 직접 포함해야 함)",
                "AOI 벡터 파일 선택 (GeoJSON/GeoPackage/Shapefile)",
                "출력 폴더 선택",
                "<b>Validate Inputs</b> 클릭 → CRS/해상도/밴드 존재 여부 등을 검사하고, 결과를 "
                "Valid / Valid with warnings / Invalid 배지와 밴드 메타데이터 표로 보여줌",
            ],
            s,
        )
    )

    story.append(Paragraph("② Change Detection 탭", s["h3"]))
    story.append(
        bullet_list(
            [
                "분석 방법: Provided baseline / Robust RGB CVA / Run both (기본값)",
                "방사보정: None / Robust median-MAD (기본값) / Percentile matching / PIF",
                "Threshold 방법: Otsu (기본값) / Percentile / Manual",
                "Morphology(opening/closing) 및 최소 변화면적(m²) 설정",
            ],
            s,
        )
    )

    story.append(Paragraph("③ Spatial Analysis 탭", s["h3"]))
    story.append(
        bullet_list(
            [
                "공간통계 활성화 여부, 분석 격자(grid) 크기(m), 가중치(Queen/Rook/KNN), permutation 횟수, "
                "유의수준(alpha), FDR 보정 여부",
                '실험적 비지도 공간 ML(Isolation Forest / DBSCAN) — 화면에 "정답 레이블이 없으므로 '
                '탐색적 결과일 뿐"이라는 경고 문구가 항상 표시됨',
            ],
            s,
        )
    )

    story.append(Paragraph("④ Outputs 탭", s["h3"]))
    story.append(
        bullet_list(
            [
                "GeoTIFF 스택/중간 산출물 저장 여부, 인터랙티브 지도 생성 여부, QML 스타일 자동 적용 여부, "
                "결과를 현재 QGIS 프로젝트에 자동 로드할지 여부 등을 체크박스로 설정",
            ],
            s,
        )
    )

    story.append(Paragraph("⑤ Run & Results 탭", s["h3"]))
    story.append(
        bullet_list(
            [
                "<b>Run Analysis</b> 클릭 → 진행률 바, 현재 단계, 경과 시간, 실시간 로그가 표시됨",
                "<b>Cancel</b>로 언제든 안전하게 중단 가능 (중간 산출물이 완료된 결과로 표시되지 않음)",
                "완료 시 요약 표(변화 객체 수, 총 변화면적, Global Moran's I 등)와 함께 "
                "<b>Open Report</b> / <b>Open Interactive Map</b> / <b>Open Output Folder</b> 버튼 활성화",
            ],
            s,
        )
    )

    story.append(Paragraph("⑥ Dependencies 탭", s["h3"]))
    story.append(
        Paragraph("A.3~A.4에서 설명한 의존성 확인 및 External interpreter 설정 화면.", s["body"])
    )

    story.append(Paragraph("A.6 실행 후 결과 확인", s["h2"]))
    story.append(
        Paragraph(
            "완료되면 QGIS 레이어 패널에 <font face='Courier'>Solafune Change Analysis — &lt;run id&gt;</font> "
            "그룹이 생기고, 그 아래 Inputs / Change Detection / Spatial Statistics / Experimental ML "
            "하위 그룹으로 AOI, Before/After RGB, CVA Intensity/Binary, Change Features(변화 폴리곤), "
            "Analysis Grid, LISA Clusters, Gi* Hotspots, (ML 활성화 시) Spatial Anomalies 레이어가 "
            "자동으로 로드되고 미리 만들어진 QML 스타일이 적용됩니다.",
            s["body"],
        )
    )

    story.append(Paragraph("A.7 Processing Toolbox에서 사용", s["h2"]))
    story.append(
        Paragraph(
            "Processing Toolbox → <b>Solafune Geospatial Analytics → Sentinel-2 Change Analysis</b>에서도 "
            "동일한 엔진을 실행할 수 있습니다 (배치 처리·모델 빌더 연동에 유용). 파라미터는 Dock Widget의 "
            "핵심 옵션과 동일하게 구성되어 있습니다.",
            s["body"],
        )
    )

    story.append(Paragraph("A.8 문제 해결 (Troubleshooting)", s["h2"]))
    story.append(
        make_table(
            ["증상", "원인 / 해결"],
            [
                [
                    '"Validate Inputs" 클릭 시 아무 반응 없거나 오류창',
                    "Dependencies 탭에서 상태 확인 → External interpreter 설정 (A.4)",
                ],
                [
                    "Before/After 폴더 선택했는데 밴드를 못 찾음",
                    "폴더 안에 B02/B03/B04 파일이 직접 있어야 함 (하위 폴더 X)",
                ],
                [
                    "Run Analysis 눌러도 진행이 안 됨",
                    '로그 패널 확인 → QGIS 메뉴 "View → Panels → Log Messages"의 "Solafune Change Analyzer" 탭에서 상세 로그 확인',
                ],
                [
                    "결과 레이어가 안 뜸",
                    'Outputs 탭의 "Load results into current QGIS project" 체크 여부 확인',
                ],
                [
                    "External 실행이 안 끝남",
                    "인터프리터 경로가 실제 python.exe인지 확인 (.bat/바로가기 아님), 그 환경에 pip install -e . 이 되어 있는지 확인",
                ],
            ],
            s,
            col_widths=[165, 245],
        )
    )

    story.append(Paragraph("A.9 체크섬 검증 (선택)", s["h2"]))
    story.append(
        Paragraph(
            "Windows PowerShell / 명령 프롬프트에서 아래 명령을 실행한 뒤, 출력된 해시값을 "
            "<font face='Courier'>solafune_change_analyzer.zip.sha256</font> 파일 내용과 비교합니다.",
            s["body"],
        )
    )
    story.append(code_block("certutil -hashfile solafune_change_analyzer.zip SHA256", s))

    # ================================================================== PART B
    story.append(PageBreak())
    story.append(Paragraph("PART B. 스크립트(CLI) 버전 사용법", s["h1"]))

    story.append(Paragraph("B.1 사전 준비", s["h2"]))
    story.append(
        bullet_list(
            [
                "Python 3.10 이상 (개발/테스트는 3.12)",
                "설치 파일: <font face='Courier'>solafune-sentinel2-change-source.zip</font>",
            ],
            s,
        )
    )

    story.append(Paragraph("B.2 설치 단계", s["h2"]))
    story.append(Paragraph("1) 압축 해제", s["body"]))
    story.append(
        code_block(
            "unzip solafune-sentinel2-change-source.zip -d solafune-sentinel2-change\n"
            "cd solafune-sentinel2-change",
            s,
        )
    )
    story.append(Paragraph("2) 가상환경 생성", s["body"]))
    story.append(code_block("python -m venv .venv", s))
    story.append(Paragraph("3) 의존성 설치", s["body"]))
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
            "macOS/Linux는 <font face='Courier'>.venv\\Scripts\\pip</font> 대신 "
            "<font face='Courier'>source .venv/bin/activate</font> 후 <font face='Courier'>pip ...</font>를 사용합니다.",
            s["body"],
        )
    )

    story.append(Paragraph("B.3 한 줄 실행 (권장)", s["h2"]))
    story.append(code_block("solafune-change all --config config/default.yaml", s))
    story.append(
        Paragraph(
            "입력 검증 → 스택 생성 → baseline + robust CVA 변화탐지 → 임계값/후처리 → 벡터화 → "
            "공간통계(Moran's I / Gi*) → GeoPackage DB 저장 → 정적 그림/인터랙티브 지도 → "
            "<font face='Courier'>report.md</font> 생성까지 약 30초 안에 끝납니다. "
            "결과는 <font face='Courier'>outputs/</font>와 <font face='Courier'>data/processed/</font>에 생성됩니다.",
            s["body"],
        )
    )

    story.append(Paragraph("B.4 개별 CLI 명령어", s["h2"]))
    story.append(
        make_table(
            ["명령어", "설명"],
            [
                [
                    "solafune-change validate --config config/default.yaml",
                    "입력만 검증 (dry-run, 분석 실행 없음)",
                ],
                ["solafune-change run --config config/default.yaml", "전체 파이프라인 실행"],
                [
                    "solafune-change stats --config config/default.yaml",
                    "공간통계를 강제로 활성화하여 실행",
                ],
                [
                    "solafune-change report --config config/default.yaml",
                    "파이프라인 실행 후 report.md 재생성",
                ],
                [
                    "solafune-change all --config config/default.yaml",
                    "validate → run을 한 번에 (권장)",
                ],
                ["python -m solafune_change --help", "위 명령어와 동일 (모듈 실행 방식)"],
            ],
            s,
            col_widths=[260, 210],
            mono_cols={0},
        )
    )

    story.append(Paragraph("B.5 자주 쓰는 옵션 오버라이드", s["h2"]))
    story.append(
        make_table(
            ["옵션", "설명"],
            [
                ["--before / --after / --aoi / --output-dir", "입력·출력 경로 덮어쓰기"],
                ["--method baseline|cva|both", "분석 방법 선택 (기본값: both)"],
                ["--threshold-method otsu|percentile|manual", "임계값 방식"],
                ["--percentile 97", "percentile 방식일 때 백분위수"],
                ["--threshold-value 5.5", "manual 방식일 때 절대 임계값"],
                ["--min-area-m2 900", "최소 변화 객체 면적(m²)"],
                ["--grid-size-m 200", "공간통계 분석 격자 크기(m)"],
                ["--permutations 499", "Moran's I / Gi* permutation 횟수"],
                ["--seed 7", "재현성용 random seed"],
                ["--ml / --no-ml", "실험적 공간 ML 강제 on/off"],
                ["--json-progress", "JSON Lines 진행률 출력 (QGIS 플러그인 외부 실행 모드용)"],
                ["-v / --verbose", "디버그 로그 출력"],
            ],
            s,
            col_widths=[190, 280],
            mono_cols={0},
        )
    )
    story.append(Paragraph("실행 예시", s["h3"]))
    story.append(
        code_block(
            "solafune-change run --config config/default.yaml \\\n"
            "  --threshold-method percentile --percentile 97 \\\n"
            "  --min-area-m2 900 --grid-size-m 200 --seed 7 --ml",
            s,
        )
    )

    story.append(Paragraph("B.6 설정 파일 (config/default.yaml)", s["h2"]))
    story.append(
        Paragraph(
            "모든 CLI 옵션은 <font face='Courier'>config/default.yaml</font>에서 기본값을 관리합니다. "
            "이 파일을 직접 복사·수정해서 <font face='Courier'>--config</font>로 다른 설정 파일을 "
            "지정할 수도 있습니다. 주요 섹션: <font face='Courier'>paths</font> (입출력 경로), "
            "<font face='Courier'>preprocessing</font> (방사보정), "
            "<font face='Courier'>change_detection</font> (방법/임계값/형태학적 후처리), "
            "<font face='Courier'>spatial_statistics</font>, <font face='Courier'>spatial_ml</font>, "
            "<font face='Courier'>output</font>.",
            s["body"],
        )
    )

    story.append(Paragraph("B.7 출력 결과 위치", s["h2"]))
    story.append(
        make_table(
            ["경로", "내용"],
            [
                ["data/processed/sentinel2_&lt;date&gt;_stack.tif", "RGB 순서 밴드 스택"],
                [
                    "data/processed/baseline_change_intensity.tif, baseline_change_binary.tif",
                    "baseline 변화강도/이진 래스터",
                ],
                [
                    "data/processed/cva_change_intensity.tif, cva_change_binary.tif",
                    "robust CVA 변화강도/이진 래스터",
                ],
                ["outputs/database/change_analysis.gpkg", "GeoPackage (SQLite 기반 공간 DB)"],
                ["outputs/figures/change_comparison.png", "baseline vs CVA vs Gi* 비교 그림"],
                ["outputs/maps/interactive_map.html", "인터랙티브 지도 (오프라인에서도 열림)"],
                ["outputs/statistics/global_moran.json, spatial_statistics.csv", "공간통계 수치"],
                ["outputs/qgis/styles/*.qml", "QGIS 스타일 파일"],
                [
                    "outputs/{summary,run_manifest,quality_report}.json, report.md",
                    "요약·메타데이터·분석 리포트",
                ],
            ],
            s,
            col_widths=[280, 190],
            mono_cols={0},
        )
    )

    story.append(Paragraph("B.8 QGIS 플러그인 ZIP 직접 다시 빌드하기", s["h2"]))
    story.append(
        code_block(
            "python scripts/build_qgis_plugin.py\n"
            "python scripts/validate_qgis_plugin.py outputs/qgis/solafune_change_analyzer.zip",
            s,
        )
    )

    story.append(Paragraph("B.9 테스트 / 코드 품질", s["h2"]))
    story.append(
        Paragraph(
            "테스트(62개), 린트(ruff), 포맷 검사(black)를 각각 아래 명령으로 실행할 수 있습니다.",
            s["body"],
        )
    )
    story.append(
        code_block(
            "python -m pytest tests/ -v\n"
            "ruff check .\n"
            "black --check src/ tests/ scripts/ qgis_plugin/solafune_change_analyzer --exclude vendor",
            s,
        )
    )

    story.append(Paragraph("B.10 문제 해결 (Troubleshooting)", s["h2"]))
    story.append(
        make_table(
            ["증상", "원인 / 해결"],
            [
                [
                    '"command not found: solafune-change"',
                    "가상환경 활성화 안 됨 또는 pip install -e . 안 함",
                ],
                [
                    "입력 파일 CRS/밴드 오류",
                    "solafune-change validate --config ... 로 먼저 원인 확인",
                ],
                ["실행이 느리거나 멈춤", "grid-size-m을 키우거나 permutations를 줄여서 재시도"],
                [
                    "결과 수치가 report.md와 다름",
                    "동일 seed로 재실행했는지, config가 같은지 확인 (재현성 보장됨)",
                ],
            ],
            s,
            col_widths=[165, 245],
        )
    )

    # ================================================================== 부록
    story.append(PageBreak())
    story.append(Paragraph("부록. 요약 비교", s["h1"]))
    story.append(
        make_table(
            ["항목", "① QGIS 플러그인 버전", "② 스크립트(CLI) 버전"],
            [
                [
                    "필요 파일",
                    "solafune_change_analyzer.zip",
                    "solafune-sentinel2-change-source.zip",
                ],
                ["QGIS 필요 여부", "필요 (3.28+)", "불필요"],
                ["실행 방식", "GUI (Dock Widget 클릭)", "터미널 명령어"],
                [
                    "의존성 설치",
                    "External interpreter로 ②의 .venv 재사용 가능",
                    "requirements-dev.txt로 직접 설치",
                ],
                ["결과 확인", "QGIS 레이어 패널에 자동 로드", "outputs/ 폴더 파일로 확인"],
                ["분석 엔진", "동일 (solafune_change 코어 패키지 공유)", "동일"],
            ],
            s,
            col_widths=[95, 180, 180],
        )
    )
    story.append(Spacer(1, 14))
    story.append(
        Paragraph(
            "두 버전 모두 실제 입력 데이터(2023-08-12 vs 2023-09-02, Zambia 노천 광산 AOI)로 "
            "실행 검증을 마쳤으며, 514개 변화 객체 / 총 변화면적 37,405,887 m² (AOI의 14.14%) / "
            "Global Moran's I = 0.834 (p = 0.001)라는 동일한 결과를 재현합니다. "
            "자세한 분석 방법론과 해석상의 한계는 각 zip에 포함된 최상위 "
            "<font face='Courier'>README.md</font>와 <font face='Courier'>report.md</font>를 참고하세요.",
            s["body"],
        )
    )

    return story


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--font", type=str, default=DEFAULT_FONT, help="Korean-capable regular TTF path"
    )
    parser.add_argument(
        "--font-bold", type=str, default=DEFAULT_FONT_BOLD, help="Korean-capable bold TTF path"
    )
    args = parser.parse_args()

    register_fonts(args.font, args.font_bold)
    styles = build_styles()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(args.out),
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title="Solafune Sentinel-2 Change Analysis - Usage Guide",
        author="Yeon-jun Kim",
    )
    story = build_story(styles)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
