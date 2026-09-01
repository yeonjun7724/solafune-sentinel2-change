#!/usr/bin/env python
"""Generates a detailed Korean-language PDF usage guide for the submission bundle.

Covers both the QGIS plugin version and the script/CLI version of
solafune-change, step by step, plus project background, algorithm detail,
database schema, dependency setup options (including a no-separate-venv
path verified against a real QGIS install), and the bugs found and fixed
during development. Requires ``reportlab`` (dev-only dependency; not part
of the core pipeline's runtime requirements) and a Korean-capable TrueType
font on the system (defaults to Windows' bundled Malgun Gothic; override
with --font/--font-bold if unavailable).

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
            f"Korean font not found at {regular} / {bold}. "
            "Pass --font/--font-bold pointing at a Korean-capable TTF pair."
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
    canvas.drawString(20 * mm, 12 * mm, "Solafune Sentinel-2 Change Analysis — Usage Guide")
    canvas.drawRightString(190 * mm, 12 * mm, f"{doc.page}")
    canvas.restoreState()


def build_story(styles: dict) -> list:
    s = styles
    story: list = []

    # ================================================================== 표지
    story.append(Spacer(1, 30))
    story.append(Paragraph("Solafune Sentinel-2 Change Analysis", s["title"]))
    story.append(
        Paragraph("상세 사용 설명서 — QGIS 플러그인 버전 &amp; 스크립트(CLI) 버전", s["subtitle"])
    )
    story.append(hr(color=NAVY, thickness=1.4, space_before=10, space_after=16))
    story.append(
        Paragraph(
            "이 문서는 제출 번들(<font face='Courier'>submission/</font>)에 포함된 두 실행 방식 — "
            "① QGIS 안에서 GUI로 실행하는 <b>플러그인 버전</b>과 "
            "② 터미널에서 명령어로 실행하는 <b>스크립트(CLI) 버전</b> — 의 설치·설정·사용법을 "
            "화면/필드 단위로 정리하고, 프로젝트 배경, 알고리즘 근거, 데이터베이스 스키마, "
            "실제 개발 중 발견하고 수정한 버그, 테스트 검증 기록까지 함께 담았습니다. "
            "두 버전 모두 동일한 분석 엔진(<font face='Courier'>solafune_change</font> 코어 패키지)을 "
            "공유하므로 결과가 동일합니다.",
            s["body"],
        )
    )
    story.append(Spacer(1, 12))
    story.append(
        make_table(
            ["항목", "내용"],
            [
                [
                    "GitHub 저장소",
                    "https://github.com/yeonjun7724/solafune-sentinel2-change (Public)",
                ],
                ["AOI", "Zambia 노천 광산, 약 264.6 km² (EPSG:32735, UTM 35S, 10m 해상도)"],
                ["비교 시점", "2023-08-12 vs 2023-09-02 (Sentinel-2 B02/B03/B04)"],
                [
                    "핵심 결과",
                    "변화 객체 514개 / 총 변화면적 37,405,887 m² (AOI의 14.14%) / Global Moran's I = 0.834 (p=0.001)",
                ],
                ["대상 QGIS 버전", "3.28 이상 (3.44.12에서 실제 설치·실행 검증)"],
                ["대상 Python 버전", "3.10 이상 (3.12에서 개발/테스트)"],
                ["테스트", "pytest 65개 전부 통과, ruff/black 클린"],
            ],
            s,
            col_widths=[110, 340],
        )
    )
    story.append(PageBreak())

    # ================================================================== 목차
    story.append(Paragraph("목차", s["h1"]))
    toc_rows = [
        ["0", "제출 번들 구성 (전체)"],
        ["1", "원본 과제 요구사항 대조"],
        ["PART A", "QGIS 플러그인 버전 — 설치부터 결과 확인까지"],
        ["A.1–A.2", "사전 준비 / 설치 단계"],
        ["A.3–A.4", "의존성 확인 및 설치 (venv 없이 하는 법 포함, 실측 검증)"],
        ["A.5", "Dock Widget 6개 탭 전체 필드 상세"],
        ["A.6", "실행 진행 단계 (12단계) 상세"],
        ["A.7", "결과 레이어 구조와 스타일"],
        ["A.8–A.9", "Processing Toolbox / Before-After 비교"],
        ["A.10", "새로 추가된 Clear Inputs(초기화) 버튼"],
        ["A.11–A.12", "문제 해결 / 체크섬 검증"],
        ["PART B", "스크립트(CLI) 버전 — 설치부터 결과 확인까지"],
        ["B.1–B.9", "설치, 실행, CLI 명령어/옵션 전체 레퍼런스"],
        ["B.10", "config/default.yaml 전체 필드 레퍼런스"],
        ["B.11–B.12", "테스트/재빌드 / 문제 해결"],
        ["2", "실제 분석 결과 상세"],
        ["3", "알고리즘 선택과 근거 (수식 포함)"],
        ["4", "공간 데이터베이스 스키마 전체"],
        ["5", "개발 중 실제로 발견하고 수정한 버그 (8건)"],
        ["6", "테스트 및 검증 기록"],
        ["7", "주요 가정 및 한계"],
        ["부록", "SQL 쿼리 예시 / 용어 설명"],
    ]
    story.append(make_table(["절", "내용"], toc_rows, s, col_widths=[70, 380]))
    story.append(PageBreak())

    # ================================================================== 0. 제출 번들 구성
    story.append(Paragraph("0. 제출 번들 구성 (전체)", s["h1"]))
    story.append(
        Paragraph(
            "<font face='Courier'>submission/</font> 폴더 하나에 실행 파일 + 최종 결과물 + 원본 데이터 + "
            "이 문서까지 전부 들어 있습니다. (이 폴더 자체는 git에 커밋되지 않는 로컬 전용 제출용 묶음입니다.)",
            s["body"],
        )
    )
    story.append(
        make_table(
            ["경로", "설명", "QGIS 필요?"],
            [
                ["Usage_Guide.pdf", "이 문서", "-"],
                [
                    "solafune_change_analyzer.zip (+.sha256)",
                    "① QGIS 플러그인 설치 파일 (분석 엔진 내장). 체크섬 파일 포함",
                    "필요",
                ],
                [
                    "solafune-sentinel2-change-source.zip",
                    '② 스크립트(CLI) 버전 — GitHub "Download ZIP"과 동일한 구조(solafune-sentinel2-change-master/ 폴더로 감싸짐), git archive HEAD 스냅샷이라 커밋 내용과 100% 일치',
                    "불필요",
                ],
                [
                    "data/",
                    "③ 원본 입력 위성영상 별도 복사본 (아오이/밴드 GeoTIFF, 확인용)",
                    "불필요",
                ],
                [
                    "results/outputs/",
                    "④ 실제로 실행해서 나온 최종 산출물 원본 — GeoPackage DB, 정적 비교 그림, 인터랙티브 지도, 공간통계 JSON/CSV, report.md 등. 재실행 없이 바로 열어볼 수 있음",
                    "불필요 (QGIS로 열어보면 더 좋음)",
                ],
                [
                    "results/data_processed/",
                    "④ 스택 GeoTIFF, baseline/CVA intensity·binary 래스터 원본",
                    "불필요",
                ],
            ],
            s,
            col_widths=[150, 265, 75],
        )
    )
    story.append(
        Paragraph(
            '<b>②번이 "github zip으로 묶은 파일"에 해당합니다</b>: GitHub 저장소 페이지의 '
            "Code → Download ZIP을 눌렀을 때와 동일한 폴더 구조(<font face='Courier'>"
            "solafune-sentinel2-change-master/</font>로 감싸짐)로 만들었고, 실제로 GitHub에 푸시된 "
            "최신 커밋을 <font face='Courier'>git archive</font>로 그대로 떠낸 것이라 웹에서 직접 "
            "다운로드받는 것과 내용이 100% 동일합니다.",
            s["highlight"],
        )
    )
    story.append(
        Paragraph(
            '<b>④번(results/)이 "최종 output 결과물"</b>입니다: 코드를 실행하지 않아도 실제 분석이 끝난 '
            "상태의 GeoPackage, 그림, 지도, 통계 파일을 바로 열어볼 수 있도록 그대로 복사해 두었습니다. "
            "(② 소스 zip 안에는 용량 문제로 이 결과 파일들이 포함되어 있지 않으므로, 재실행 없이 바로 "
            "결과만 보고 싶다면 이 results/ 폴더를 여세요.)",
            s["highlight"],
        )
    )
    story.append(PageBreak())

    # ================================================================== 1. 요구사항 대조
    story.append(Paragraph("1. 원본 과제 요구사항 대조", s["h1"]))
    story.append(
        Paragraph(
            "<font face='Courier'>instructions.pdf</font>가 요구한 5개 파트를 실제 산출물과 대조한 결과입니다.",
            s["body"],
        )
    )
    story.append(
        make_table(
            ["Part", "요구사항", "실제 구현/검증"],
            [
                [
                    "1. Data Preparation",
                    "B2/B3/B4 로드, CRS/transform/dimensions 검증, 밴드 스택",
                    "validation.py로 검증, data/processed/sentinel2_&lt;date&gt;_stack.tif 파일명까지 정확히 일치 생성",
                ],
                [
                    "2. Change Detection",
                    "예제 참고하되 그대로 복사 금지 + 자체 알고리즘",
                    "baseline.py(예제 독립 재구현) + cva.py(robust CVA, 주 분석법)",
                ],
                [
                    "3. Feature Extraction &amp; Storage",
                    "폴리곤화, SQLite/PostGIS, id/date_before/date_after/area_m2/confidence/geometry",
                    "GeoPackage(SQLite)에 실제 geometry 컬럼, 요구 필드 + 15개 추가 필드",
                ],
                [
                    "4. Visualization",
                    "AOI 폴리곤, 변화 래스터/폴리곤 (인터랙티브는 plus)",
                    "정적 PNG + Folium 인터랙티브 HTML(오프라인 동작) 둘 다",
                ],
                [
                    "5. Analysis &amp; Interpretation",
                    "report.md: Method/Results/Interpretation",
                    "7개 섹션으로 확장, 실제 실행 수치 반영",
                ],
            ],
            s,
            col_widths=[95, 175, 180],
        )
    )
    story.append(
        Paragraph(
            "Deliverables(Code/Database/README.md/report.md) 전부 충족 + 과제가 요구하지 않은 공간통계, "
            "비지도 공간 ML, QGIS 플러그인, 65개 자동화 테스트까지 추가 구현했습니다.",
            s["body"],
        )
    )
    story.append(PageBreak())

    # ================================================================== PART A
    story.append(Paragraph("PART A. QGIS 플러그인 버전", s["h1"]))

    story.append(Paragraph("A.1 사전 준비", s["h2"]))
    story.append(
        bullet_list(
            [
                "QGIS 3.28 이상 (개발/검증은 QGIS 3.44.12, OSGeo4W 빌드 기준)",
                "설치 파일: <font face='Courier'>solafune_change_analyzer.zip</font>",
            ],
            s,
        )
    )

    story.append(Paragraph("A.2 설치 단계", s["h2"]))
    story.append(
        bullet_list(
            [
                "QGIS 실행",
                "메뉴 <b>Plugins → Manage and Install Plugins → Install from ZIP</b>",
                "<font face='Courier'>solafune_change_analyzer.zip</font> 선택 → <b>Install Plugin</b>",
                '<b>Installed</b> 탭에서 "Solafune Change Analyzer" 체크 확인',
                "툴바 아이콘 클릭 또는 <b>Plugins → Solafune Change Analyzer</b>로 Dock Widget 열기",
            ],
            s,
        )
    )

    story.append(Paragraph("A.3 왜 의존성 문제가 생기는가", s["h2"]))
    story.append(
        Paragraph(
            "이 플러그인의 분석 엔진은 rasterio, geopandas, scikit-image, scikit-learn, libpysal, esda, "
            "matplotlib, folium 같은 순수 지리정보 과학 패키지에 의존합니다. 그런데 <b>Windows/OSGeo4W용 "
            "QGIS는 자체 Python에 이 패키지들을 기본 포함하지 않습니다</b> (QGIS 자체 GIS 기능은 "
            "GDAL/PROJ를 C++ 레벨에서 직접 쓰기 때문에 Python 패키지로 rasterio 등을 넣어둘 필요가 없기 "
            "때문입니다). 실제로 QGIS 3.44.12에서 확인한 결과:",
            s["body"],
        )
    )
    story.append(
        make_table(
            ["패키지", "QGIS 기본 내장 여부", "필요한 기능"],
            [
                [
                    "numpy, geopandas, shapely, pyproj, scipy, PyYAML, matplotlib, folium",
                    "있음 (Ready)",
                    "기본 실행, 시각화",
                ],
                [
                    "rasterio",
                    "없음 (Missing)",
                    "래스터 입출력 — 가장 핵심, 없으면 아무 분석도 안 됨",
                ],
                ["scikit-image", "없음 (Missing)", "형태학적 후처리"],
                ["libpysal, esda", "없음 (Missing)", "공간통계 (Moran's I, Getis-Ord Gi*)"],
                ["scikit-learn", "없음 (Missing)", "실험적 비지도 공간 ML"],
            ],
            s,
            col_widths=[195, 100, 155],
        )
    )

    story.append(Paragraph("A.4 의존성 설치 방법 — 두 가지 옵션", s["h2"]))
    story.append(
        Paragraph(
            '"별도 .venv 폴더를 꼭 만들어야 하나?"라는 질문에 대한 답: <b>아닙니다, 안 만들어도 됩니다.</b> '
            "실제로 QGIS 3.44.12에서 두 방법을 모두 실측 검증했습니다.",
            s["body"],
        )
    )

    story.append(
        Paragraph("옵션 1 (권장, 별도 폴더 불필요): QGIS 자체 Python에 직접 설치", s["h3"])
    )
    story.append(
        Paragraph(
            "QGIS가 내장한 Python 인터프리터 자체에 <font face='Courier'>--user</font> 옵션으로 "
            '패키지를 한 번만 설치하면, 그 뒤로는 Dependencies 탭이 자동으로 "Ready"를 표시하고 '
            "<b>Embedded 모드가 그대로 작동합니다</b> — External interpreter를 따로 설정할 필요가 전혀 없습니다. "
            "설치 위치는 <font face='Courier'>%APPDATA%\\Python\\Python312\\site-packages</font>(사용자 폴더, "
            "관리자 권한 불필요)이고, QGIS의 <font face='Courier'>sys.path</font>에 이미 자동으로 포함되어 있습니다.",
            s["body"],
        )
    )
    story.append(Paragraph("Windows (QGIS 설치 경로가 다르면 그 경로로 바꾸세요):", s["body"]))
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
            "<b>실측 검증 결과</b> (QGIS 3.44.12, 이 명령 실행 후): Dependencies 탭의 모든 필수 패키지가 "
            "Ready로 전환되었고, rasterio가 QGIS 자체 GDAL과 같은 프로세스 안에서 충돌 없이 공존했으며 "
            "(CRS 조회 등 정상), <b>Validate Inputs와 전체 파이프라인 실행(Run Analysis, 공간통계+실험적 "
            "ML 포함)이 임베디드 모드에서 처음부터 끝까지 성공</b>했습니다 (514개 변화 객체, Global Moran's "
            "I=0.804 — 정상 수치). 다만 이는 이 QGIS 버전·패키지 버전 조합에서 검증된 결과이며, 다른 "
            "QGIS/OS 조합에서는 GDAL 버전 차이로 인한 충돌 가능성이 이론적으로 남아있습니다 (아래 옵션 2가 "
            "그 위험을 원천 차단하는 대안입니다).",
            s["highlight"],
        )
    )

    story.append(Paragraph("옵션 2 (격리, 더 안전): 별도 .venv + External interpreter", s["h3"]))
    story.append(
        Paragraph(
            "옵션 1은 QGIS와 같은 프로세스 안에 새 GDAL을 얹는 방식이라 QGIS 버전에 따라 충돌 가능성이 "
            "이론적으로 있습니다. 완전히 격리하고 싶다면(다른 QGIS 플러그인이나 QGIS 자체 동작에 영향을 "
            "주고 싶지 않다면), 별도 프로세스에서 실행되는 독립 <font face='Courier'>.venv</font>를 만들고 "
            "플러그인이 <b>External interpreter</b> 모드로 그 프로세스를 호출하게 하는 방법입니다. "
            "PART B의 B.2 설치 단계로 <font face='Courier'>.venv</font>를 만든 뒤, Dock Widget "
            "Dependencies 탭에서 그 <font face='Courier'>python.exe</font> 경로를 지정하면 됩니다.",
            s["body"],
        )
    )
    story.append(
        make_table(
            ["", "옵션 1: QGIS 자체 Python에 설치", "옵션 2: 별도 .venv"],
            [
                ["별도 폴더 필요", "불필요", "필요 (.venv/)"],
                ["실행 프로세스", "QGIS와 동일 프로세스 (임베디드)", "별도 프로세스 (외부 호출)"],
                [
                    "설정 단계",
                    "pip 명령 1번 실행",
                    ".venv 생성 + 설치 + Dependencies 탭에서 경로 지정",
                ],
                [
                    "GDAL 충돌 위험",
                    "이론상 있음 (실측으로는 QGIS 3.44.12에서 없었음)",
                    "없음 (완전히 격리된 별도 프로세스)",
                ],
                [
                    "속도",
                    "약간 빠름 (프로세스 생성 오버헤드 없음)",
                    "약간 느림 (매 실행마다 새 프로세스)",
                ],
                [
                    "권장 대상",
                    "빠르고 간단하게 쓰고 싶은 경우",
                    "다른 QGIS 플러그인/프로젝트에 영향 주고 싶지 않은 경우",
                ],
            ],
            s,
            col_widths=[90, 205, 155],
        )
    )

    story.append(Paragraph("A.5 Dock Widget 6개 탭 전체 필드 상세", s["h2"]))

    story.append(Paragraph("① Inputs 탭", s["h3"]))
    story.append(
        make_table(
            ["필드", "설명"],
            [
                [
                    "Before / After Sentinel-2 folder",
                    "각 폴더 안에 B02/B03/B04 GeoTIFF 또는 JP2가 <b>직접</b> 있어야 함 (하위 폴더 안 됨). 예: inputs/data/sentinel2_20230812",
                ],
                [
                    "AOI vector file",
                    "GeoJSON/GeoPackage/Shapefile 중 하나. WGS84가 아니어도 자동으로 래스터 CRS에 맞춰 재투영됨",
                ],
                ["Output directory", "결과가 저장될 폴더. 없으면 자동 생성됨"],
                [
                    "Run label",
                    "실행을 구분하기 위한 라벨(선택). run_id 앞에 붙어서 레이어 그룹명/run_metadata에 표시됨. 비워두면 타임스탬프만 사용",
                ],
                [
                    "Validate Inputs 버튼",
                    "CRS/해상도/밴드 존재 여부 등을 검사하고 Valid/Valid with warnings/Invalid 배지 + 밴드 메타데이터 표를 보여줌",
                ],
                [
                    "Clear Inputs (초기화) 버튼",
                    "(신규) 위 4개 경로 필드와 Run label, 검증 결과를 모두 비움. 이전 세션에 저장된 값도 함께 지워서 QGIS를 재시작해도 옛날 경로가 남아있지 않게 함. 다른 탭(Change Detection 등) 설정은 건드리지 않음",
                ],
            ],
            s,
            col_widths=[130, 310],
        )
    )

    story.append(Paragraph("② Change Detection 탭", s["h3"]))
    story.append(
        make_table(
            ["필드", "설명"],
            [
                [
                    "분석 방법",
                    "Provided baseline(예제 방식만) / Robust RGB CVA(개선 방식만) / <b>Run both(기본값, 둘 다 실행하고 비교)</b>",
                ],
                [
                    "방사보정",
                    "None(보정 없음) / <b>Robust median/MAD(기본값)</b> — 두 시점 공통 유효 픽셀의 중앙값·MAD로 선형 매칭 / Percentile matching — 2·98백분위수로 매칭 / PIF(Pseudo-Invariant Features) — 변화가 적은 픽셀만 골라 선형회귀",
                ],
                [
                    "Threshold 방법",
                    "<b>Otsu(기본값)</b> — 자동 이진화 / Percentile — 지정 백분위수 이상을 변화로 판정 / Manual — 절대값 직접 지정",
                ],
                [
                    "Morphology",
                    "이진 래스터에 opening/closing 형태학적 연산 적용 여부, 커널 크기(px)",
                ],
                [
                    "Minimum change area",
                    "이보다 작은 연결 객체는 노이즈로 간주해 제거 (m² 단위, 픽셀 면적 기준 자동 환산)",
                ],
            ],
            s,
            col_widths=[100, 340],
        )
    )

    story.append(Paragraph("③ Spatial Analysis 탭", s["h3"]))
    story.append(
        make_table(
            ["필드", "설명"],
            [
                ["Enable spatial statistics", "격자 집계 기반 공간통계 활성화 (기본 켜짐)"],
                [
                    "Grid cell size",
                    "분석 격자 한 변 길이(m). 기본 150m — 픽셀 단위로 통계를 내지 않고 이 크기로 집계 후 계산 (dense weight matrix를 피하기 위함)",
                ],
                [
                    "Spatial weights",
                    "Queen contiguity(기본, 변+꼭짓점 접촉) / Rook contiguity(변만 접촉) / K nearest neighbors",
                ],
                [
                    "Permutations",
                    "Monte Carlo permutation 검정 반복 횟수 (기본 999회, seed 고정으로 재현 가능)",
                ],
                ["Significance alpha", "유의수준 (기본 0.05)"],
                [
                    "FDR correction",
                    "Benjamini-Hochberg 보정 — Gi* 다중 지역 검정으로 인한 과잉 유의성 문제를 완화",
                ],
                [
                    "Global/Local Moran's I",
                    "Global: 전체 변화강도의 공간적 자기상관 / Local(LISA): 셀 단위 High-High/Low-Low/High-Low/Low-High 군집 분류",
                ],
                ["Getis-Ord Gi*", "통계적으로 유의한 hotspot/coldspot 탐지 (90/95/99% 구간)"],
                [
                    "실험적 비지도 공간 ML",
                    "정답 레이블이 전혀 없으므로 화면에 항상 경고 문구 표시. Isolation Forest(이상치 점수) 또는 DBSCAN(공간 군집화) 중 선택, contamination/eps/min_samples 등 하이퍼파라미터 조정 가능",
                ],
            ],
            s,
            col_widths=[130, 310],
        )
    )

    story.append(Paragraph("④ Outputs 탭", s["h3"]))
    story.append(
        bullet_list(
            [
                "GeoTIFF 스택/중간 산출물 저장 여부, 인터랙티브 지도 생성 여부, QML 스타일 자동 적용 여부",
                "결과를 현재 QGIS 프로젝트에 자동 로드할지, 로드 후 결과로 화면을 자동 확대(zoom)할지",
                "실패/취소된 실행의 임시 파일을 보존할지 여부",
            ],
            s,
        )
    )

    story.append(Paragraph("⑤ Run &amp; Results 탭", s["h3"]))
    story.append(
        bullet_list(
            [
                "<b>Run Analysis</b> — 진행률 바, 현재 단계, 경과 시간, 실시간 로그 표시",
                "<b>Cancel</b> — 언제든 안전하게 중단 (중간 산출물이 완료된 결과로 표시되지 않도록 원자적 파일 쓰기 사용)",
                "완료 시 요약(변화 객체 수, 총 변화면적, Global Moran's I, permutation p-value, 95% hotspot 개수, 평균 confidence, 실행 시간)과 함께 "
                "<b>Open Report / Open Interactive Map / Open Output Folder / Add Results to Map / Copy Summary / Save Log</b> 버튼 활성화",
            ],
            s,
        )
    )

    story.append(Paragraph("⑥ Dependencies 탭", s["h3"]))
    story.append(
        bullet_list(
            [
                "Execution environment: Automatic(기본, 임베디드가 가능하면 임베디드, 아니면 외부) / Embedded 강제 / External 강제",
                "External interpreter 경로 지정 + <b>Check dependencies</b> 버튼으로 그 인터프리터의 패키지 상태 실시간 조회",
                "패키지별 Ready/Missing 상태 표 (버전 정보 포함)",
                "Restore defaults / Import configuration YAML / Export configuration YAML",
            ],
            s,
        )
    )

    story.append(Paragraph("A.6 실행 진행 단계 (12단계)", s["h2"]))
    story.append(
        make_table(
            ["진행률", "단계"],
            [
                ["0–5%", "Input discovery — B02/B03/B04 파일 탐색"],
                ["5–12%", "Validation — CRS/transform/dimensions/AOI overlap 검증"],
                ["12–22%", "Raster alignment — 격자 정렬(필요시 리샘플링), AOI 마스킹"],
                ["22–30%", "Stack creation — RGB 순서 밴드 스택 GeoTIFF 생성"],
                ["30–42%", "Radiometric normalization — 방사보정 적용"],
                ["42–55%", "Baseline detection — 예제 방식 변화탐지"],
                ["55–68%", "Robust CVA — 개선 변화탐지"],
                ["68–75%", "Threshold &amp; morphology — 이진화 + 후처리"],
                ["75–82%", "Polygon extraction — 벡터화, confidence 산출"],
                ["82–90%", "Spatial statistics — Moran's I / Gi* / FDR"],
                ["90–94%", "Experimental spatial ML — (활성화 시) Isolation Forest/DBSCAN"],
                [
                    "94–100%",
                    "Database &amp; visualization &amp; report — GeoPackage, 그림, 지도, report.md",
                ],
            ],
            s,
            col_widths=[80, 360],
        )
    )

    story.append(Paragraph("A.7 결과 레이어 구조", s["h2"]))
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
            "각 레이어는 미리 만들어진 QML 스타일이 자동 적용됩니다 (연속형 래스터는 실제 데이터 범위에 맞춰 "
            "런타임에 색상 램프를 재조정). 존재하지 않는 결과(예: ML 비활성화 시 Spatial Anomalies)는 "
            "그룹 자체가 생성되지 않습니다.",
            s["body"],
        )
    )

    story.append(Paragraph("A.8 Processing Toolbox에서 사용", s["h2"]))
    story.append(
        Paragraph(
            "Processing Toolbox → <b>Solafune Geospatial Analytics → Sentinel-2 Change Analysis</b>에서도 "
            "동일한 엔진을 실행할 수 있습니다 (15개 파라미터, 배치 처리·모델 빌더 연동에 유용). Dock Widget과 "
            "동일한 request builder를 거쳐 동일한 <font face='Courier'>run_pipeline()</font>을 호출하므로 "
            "분석 로직이 중복되지 않습니다.",
            s["body"],
        )
    )

    story.append(Paragraph("A.9 Before/After 비교", s["h2"]))
    story.append(
        Paragraph(
            '결과 레이어 그룹의 "Before RGB"/"After RGB" 레이어의 가시성 체크박스를 번갈아 켜고 끄거나, '
            "레이어 패널에서 투명도(Opacity)를 조절해 두 시점을 비교할 수 있습니다. RGB 스트레치는 두 시점에 "
            "동일하게 적용되어 있어(before 이미지 기준 2·98백분위수 스트레치를 after에도 동일 적용) 비교가 "
            "왜곡되지 않습니다.",
            s["body"],
        )
    )

    story.append(Paragraph("A.10 문제 해결 (Troubleshooting)", s["h2"]))
    story.append(
        make_table(
            ["증상", "원인 / 해결"],
            [
                [
                    '"Validate Inputs" 클릭 시 오류창 (예전엔 크래시)',
                    "임베디드 Python에 rasterio 등이 없음 → Dependencies 탭에서 상태 확인, A.4의 옵션 1 또는 2로 설치",
                ],
                [
                    "Before/After 폴더 선택했는데 밴드를 못 찾음",
                    "폴더 안에 B02/B03/B04 파일이 직접 있어야 함 (하위 폴더에 있으면 안 됨)",
                ],
                [
                    "이전 세션의 잘못된 경로가 계속 남아있음",
                    "Inputs 탭의 <b>Clear Inputs(초기화)</b> 버튼으로 경로와 저장된 값을 함께 지우기",
                ],
                [
                    "결과가 예상 밖 폴더(예: 알 수 없는 임시 폴더 하위)에 생성됨",
                    "과거 버전의 버그였음 (processed_dir 경로 계산 오류) — 현재 버전에서 수정 완료, output directory를 기준으로 정확히 계산됨",
                ],
                [
                    "Run Analysis 눌러도 진행이 안 됨",
                    'QGIS 메뉴 "View → Panels → Log Messages"의 "Solafune Change Analyzer" 탭에서 상세 로그 확인',
                ],
                [
                    "결과 레이어가 안 뜸",
                    'Outputs 탭의 "Load results into current QGIS project" 체크 여부 확인',
                ],
                [
                    "External 모드 실행이 안 끝남",
                    "인터프리터 경로가 실제 python.exe인지 확인(.bat/바로가기 아님), 그 환경에 pip install -e . 되어 있는지 확인",
                ],
            ],
            s,
            col_widths=[165, 245],
        )
    )

    story.append(Paragraph("A.11 체크섬 검증 (선택)", s["h2"]))
    story.append(
        Paragraph(
            "Windows PowerShell/명령 프롬프트에서 실행 후 출력된 해시값을 "
            "<font face='Courier'>solafune_change_analyzer.zip.sha256</font> 파일 내용과 비교합니다.",
            s["body"],
        )
    )
    story.append(code_block("certutil -hashfile solafune_change_analyzer.zip SHA256", s))
    story.append(PageBreak())

    # ================================================================== PART B
    story.append(Paragraph("PART B. 스크립트(CLI) 버전", s["h1"]))

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
    story.append(
        Paragraph(
            "1) 압축 해제 (GitHub Download ZIP과 동일 구조라 폴더명이 -master로 끝남)", s["body"]
        )
    )
    story.append(
        code_block(
            "unzip solafune-sentinel2-change-source.zip\n" "cd solafune-sentinel2-change-master",
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
            "<font face='Courier'>source .venv/bin/activate</font> 후 <font face='Courier'>pip ...</font>.",
            s["body"],
        )
    )

    story.append(Paragraph("B.3 한 줄 실행 (권장)", s["h2"]))
    story.append(code_block("solafune-change all --config config/default.yaml", s))
    story.append(
        Paragraph(
            "약 30초 안에 전체 파이프라인이 끝나고 결과는 <font face='Courier'>outputs/</font>와 "
            "<font face='Courier'>data/processed/</font>에 생성됩니다.",
            s["body"],
        )
    )

    story.append(Paragraph("B.4 개별 CLI 명령어", s["h2"]))
    story.append(
        make_table(
            ["명령어", "설명"],
            [
                ["solafune-change validate --config &lt;yaml&gt;", "입력만 검증 (dry-run)"],
                ["solafune-change run --config &lt;yaml&gt;", "전체 파이프라인 실행"],
                ["solafune-change stats --config &lt;yaml&gt;", "공간통계 강제 활성화"],
                ["solafune-change report --config &lt;yaml&gt;", "실행 후 report.md 재생성"],
                ["solafune-change all --config &lt;yaml&gt;", "validate → run (권장)"],
                ["python -m solafune_change --help", "위와 동일 (모듈 실행)"],
            ],
            s,
            col_widths=[260, 210],
            mono_cols={0},
        )
    )

    story.append(Paragraph("B.5 옵션 오버라이드 전체", s["h2"]))
    story.append(
        make_table(
            ["옵션", "설명"],
            [
                ["--before / --after / --aoi / --output-dir", "경로 오버라이드"],
                ["--method baseline|cva|both", "분석 방법 (기본 both)"],
                ["--threshold-method otsu|percentile|manual", "임계값 방식"],
                ["--percentile N", "percentile 방식 백분위수"],
                ["--threshold-value N", "manual 방식 절대값"],
                ["--min-area-m2 N", "최소 변화 객체 면적"],
                ["--grid-size-m N", "공간통계 격자 크기"],
                ["--permutations N", "permutation 횟수"],
                ["--seed N", "random seed"],
                ["--ml / --no-ml", "실험적 ML on/off"],
                ["--json-progress", "JSON Lines 진행률 (플러그인 외부 실행용)"],
                ["-v / --verbose", "디버그 로그"],
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

    story.append(Paragraph("B.6 출력 결과 위치", s["h2"]))
    story.append(
        make_table(
            ["경로", "내용"],
            [
                ["data/processed/sentinel2_&lt;date&gt;_stack.tif", "RGB 순서 밴드 스택"],
                [
                    "data/processed/{baseline,cva}_change_{intensity,binary}.tif",
                    "변화탐지 래스터 4종",
                ],
                ["outputs/database/change_analysis.gpkg", "GeoPackage (SQLite 기반 공간 DB)"],
                ["outputs/figures/change_comparison.png", "baseline vs CVA vs Gi* 비교 그림"],
                ["outputs/maps/interactive_map.html", "인터랙티브 지도 (오프라인 동작)"],
                ["outputs/statistics/global_moran.json, spatial_statistics.csv", "공간통계 수치"],
                [
                    "outputs/qgis/styles/*.qml, solafune_change_analyzer.zip",
                    "QGIS 스타일, 플러그인 zip",
                ],
                [
                    "outputs/{summary,run_manifest,quality_report}.json, report.md",
                    "요약·메타데이터·리포트",
                ],
            ],
            s,
            col_widths=[280, 175],
            mono_cols={0},
        )
    )

    story.append(Paragraph("B.7 QGIS 플러그인 ZIP 재빌드", s["h2"]))
    story.append(
        code_block(
            "python scripts/build_qgis_plugin.py\n"
            "python scripts/validate_qgis_plugin.py outputs/qgis/solafune_change_analyzer.zip",
            s,
        )
    )

    story.append(Paragraph("B.8 이 사용설명서 PDF 재생성", s["h2"]))
    story.append(
        Paragraph(
            "이 PDF 자체도 스크립트로 생성됩니다 (Malgun Gothic 폰트를 임베딩하는 reportlab 스크립트).",
            s["body"],
        )
    )
    story.append(
        code_block("python scripts/generate_submission_pdf.py --out submission/Usage_Guide.pdf", s)
    )

    story.append(Paragraph("B.9 테스트 / 코드 품질", s["h2"]))
    story.append(
        code_block(
            "python -m pytest tests/ -v\n"
            "ruff check .\n"
            "black --check src/ tests/ scripts/ qgis_plugin/solafune_change_analyzer --exclude vendor",
            s,
        )
    )

    story.append(Paragraph("B.10 config/default.yaml 전체 필드 레퍼런스", s["h2"]))
    story.append(
        make_table(
            ["섹션.필드", "기본값", "설명"],
            [
                ["paths.aoi/before_folder/after_folder", "-", "필수 입력 경로"],
                ["paths.output_dir", "outputs", "결과 출력 폴더"],
                [
                    "paths.processed_dir",
                    "(미지정 시 output_dir 기준 자동 계산)",
                    "중간 GeoTIFF 저장 폴더",
                ],
                [
                    "preprocessing.normalization",
                    "robust_median_mad",
                    "none/robust_median_mad/percentile_matching/pif_linear",
                ],
                ["preprocessing.reflectance_scale", "10000.0", "DN → 반사도 환산 계수"],
                ["change_detection.method", "both", "baseline/cva/both"],
                ["change_detection.threshold_method", "otsu", "otsu/percentile/manual"],
                ["change_detection.min_area_m2", "400.0", "최소 변화면적"],
                ["change_detection.morphology.*", "opening_then_closing, 3px", "형태학적 후처리"],
                ["spatial_statistics.enabled", "true", "공간통계 on/off"],
                ["spatial_statistics.grid_size_m", "150.0", "분석 격자 크기"],
                ["spatial_statistics.weights", "queen", "queen/rook/knn"],
                ["spatial_statistics.permutations", "999", "permutation 횟수"],
                ["spatial_statistics.fdr_correction", "true", "BH-FDR 보정 on/off"],
                ["spatial_ml.enabled", "false", "실험적 ML on/off (opt-in)"],
                ["spatial_ml.model", "isolation_forest", "isolation_forest/dbscan"],
                ["run.random_seed", "42", "전체 재현성 시드"],
            ],
            s,
            col_widths=[150, 145, 155],
            mono_cols={0},
        )
    )

    story.append(Paragraph("B.11 문제 해결 (Troubleshooting)", s["h2"]))
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
                    "동일 seed·config로 재실행했는지 확인 (재현성 보장됨)",
                ],
            ],
            s,
            col_widths=[165, 245],
        )
    )
    story.append(PageBreak())

    # ================================================================== 2. 실제 분석 결과
    story.append(Paragraph("2. 실제 분석 결과 (config/default.yaml, seed=42)", s["h1"]))
    story.append(
        make_table(
            ["지표", "값"],
            [
                ["변화 객체 수", "514개"],
                ["총 변화면적", "37,405,887 m² (AOI의 14.14%)"],
                ["주 분석법 / threshold", "Robust CVA / Otsu (값 = 5.2199)"],
                [
                    "baseline 대비",
                    "baseline은 픽셀의 47.85% 변화 판정 (CVA 15.32%보다 훨씬 노이즈 많음)",
                ],
                [
                    "Global Moran's I",
                    "0.8335 (E[I]=-0.0001, z=178.37, permutation p=0.001, 999회, seed=42)",
                ],
                ["95%+ Gi* hotspot과 겹치는 객체", "95개"],
                ["가장 큰 변화 객체", "15,987,700 m²"],
                [
                    "실험적 ML (Isolation Forest, opt-in)",
                    "Top-K 이상치 안정성(공간 블록 부트스트랩) = 0.72",
                ],
                ["실행 시간", "약 30초 (전체 파이프라인, CLI 기준)"],
            ],
            s,
            col_widths=[190, 265],
        )
    )
    story.append(
        Paragraph(
            "해석: 변화가 통계적으로 강하게 공간 군집되어 있음(Moran's I=0.834, p=0.001)은 실제 구조화된 "
            "지표 변화와 일치합니다. 다만 RGB 두 시점만으로는 굴착 확장/폐석 적치/도로 변화/수분 변화/식생 "
            '제거 중 무엇인지 확정할 수 없어, report.md에서는 "consistent with" 표현만 사용합니다.',
            s["body"],
        )
    )

    # ================================================================== 3. 알고리즘
    story.append(Paragraph("3. 알고리즘 선택과 근거", s["h1"]))
    story.append(Paragraph("Baseline (제공 예제 재구현)", s["h3"]))
    story.append(
        Paragraph(
            "픽셀별 다중 밴드 유클리드 거리를 계산하고 min-max 정규화합니다. 정규화 없이(방사보정 없이) "
            "전역 스케일링을 쓰기 때문에 극단값 픽셀 하나가 전체 강도 스케일을 왜곡하는 약점을 그대로 "
            "가지고 있습니다 — 예제의 핵심 아이디어를 의도적으로 그대로 살려서 재구현했습니다 (복사는 "
            "아니고 타입힌트/로깅/예외처리를 갖춘 독립 구현).",
            s["body"],
        )
    )
    story.append(Paragraph("Robust RGB CVA (주 분석법)", s["h3"]))
    story.append(
        Paragraph(
            "밴드별 차이를 median/MAD로 표준화한 뒤 결합합니다: "
            "<font face='Courier'>z_b = (diff_b - median(diff_b)) / (1.4826 * MAD(diff_b))</font>, "
            "<font face='Courier'>CVA = sqrt(z_B04^2 + z_B03^2 + z_B02^2)</font>. MAD가 0에 가까우면 "
            "표준편차로 안전하게 대체합니다. 실측으로 baseline(47.85%)보다 훨씬 적은 15.32%만 변화로 "
            "판정해, 노이즈에 덜 민감함을 확인했습니다.",
            s["body"],
        )
    )
    story.append(Paragraph("공간통계", s["h3"]))
    story.append(
        Paragraph(
            "픽셀 단위로 dense spatial weight matrix를 만들지 않고 150m 격자로 집계(11,967개 셀) 후 "
            "Queen contiguity로 Global/Local Moran's I를, binary weights로 Getis-Ord Gi*를 계산합니다. "
            "Gi* p-value에는 Benjamini-Hochberg FDR 보정을 적용합니다.",
            s["body"],
        )
    )
    story.append(Paragraph("실험적 비지도 공간 ML", s["h3"]))
    story.append(
        Paragraph(
            "정답 레이블이 없으므로 accuracy/precision/recall을 절대 주장하지 않습니다. 대신 공간 블록 "
            '부트스트랩으로 "상위 이상치 순위가 재샘플링에도 안정적인가"를 진단합니다. 기본값은 '
            '비활성화(opt-in)이며 UI/문서 어디서나 "탐색적 결과"임을 명시합니다.',
            s["body"],
        )
    )
    story.append(Paragraph("GeoPackage를 데이터베이스로 선택한 이유", s["h3"]))
    story.append(
        Paragraph(
            "과제가 요구한 SQLite 옵션을 GeoPackage(OGC 표준, SQLite 파일 그 자체)로 만족시킵니다 — "
            "서버 없이 열어볼 수 있고 WKT 텍스트가 아닌 진짜 geometry 컬럼과 공간 인덱스를 제공합니다.",
            s["body"],
        )
    )
    story.append(PageBreak())

    # ================================================================== 4. DB 스키마
    story.append(Paragraph("4. 공간 데이터베이스 스키마 전체", s["h1"]))
    story.append(Paragraph("change_features (514개 행, MULTIPOLYGON, EPSG:32735)", s["h3"]))
    story.append(
        make_table(
            ["필드", "설명"],
            [
                ["id", "객체 ID"],
                ["date_before / date_after", "비교 시점 (20230812 / 20230902)"],
                ["method / threshold_method / threshold_value", "사용된 분석법과 임계값"],
                ["area_m2 / perimeter_m / compactness", "면적/둘레/Polsby-Popper 컴팩트니스"],
                ["mean_change / max_change / p95_change", "객체 내부 변화강도 통계"],
                [
                    "confidence",
                    "0-1 휴리스틱 점수 (보정된 확률 아님) — threshold 초과 정도+일관성+크기+hotspot 유의성+ML 순위 가중합",
                ],
                [
                    "gi_zscore / gi_pvalue / gi_qvalue / hotspot_class",
                    "Getis-Ord Gi* 결과 (q는 FDR 보정값)",
                ],
                ["lisa_cluster", "Local Moran's I 군집 유형 (High-High 등)"],
                ["ml_anomaly_score / ml_cluster_id", "(ML 활성화 시) 이상치 점수/군집 ID"],
                ["geom", "실제 geometry 컬럼 (MULTIPOLYGON)"],
            ],
            s,
            col_widths=[140, 320],
            mono_cols={0},
        )
    )
    story.append(Paragraph("spatial_grid (11,967개 셀, POLYGON)", s["h3"]))
    story.append(
        Paragraph(
            "각 셀의 mean/median/p90/p95 CVA, changed_proportion, 밴드별 평균 차이, local_std_cva, "
            "그리고 change_features와 동일한 Gi*/LISA/ML 필드를 포함합니다.",
            s["body"],
        )
    )
    story.append(Paragraph("run_metadata (1행/실행)", s["h3"]))
    story.append(
        Paragraph(
            "run_id, 실행 시각, 입력 경로, CRS/해상도, 방법/정규화/threshold 파라미터, "
            "spatial_statistics/spatial_ml 활성화 여부, package_version, random_seed 등 재현에 필요한 모든 정보.",
            s["body"],
        )
    )
    story.append(Paragraph("quality_checks", s["h3"]))
    story.append(Paragraph("검증 단계에서 발생한 경고/오류 기록 (이번 실행에서는 0건).", s["body"]))
    story.append(PageBreak())

    # ================================================================== 5. 버그
    story.append(Paragraph("5. 개발 중 실제로 발견하고 수정한 버그", s["h1"]))
    story.append(
        Paragraph(
            "코드 리뷰나 추측이 아니라 실행/테스트/실사용 중 실제로 재현된 문제들입니다.", s["body"]
        )
    )
    story.append(
        make_table(
            ["버그", "발견 경위", "수정"],
            [
                [
                    'QGIS "Validate Inputs" 크래시',
                    "실제 QGIS에 설치 후 클릭 → rasterio 없어 ModuleNotFoundError 전파",
                    "의존성 사전 확인 후 External interpreter로 자동 폴백 또는 안내창",
                ],
                [
                    "processed_dir 경로 계산 오류",
                    "실사용 중 결과가 알 수 없는 임시 폴더 하위에 생성됨 → 원인 추적",
                    "output_dir 기준으로 항상 절대경로 계산하도록 수정, 회귀 테스트 2개 추가",
                ],
                [
                    "write_intermediate 설정 무시됨",
                    "코드 전수 재검토 중 발견",
                    "실제로 중간 GeoTIFF 저장 여부를 제어하도록 수정",
                ],
                [
                    "run_label 값이 버려짐",
                    "동일 재검토",
                    "run_id에 반영, 레이어 그룹명/run_metadata에 표시",
                ],
                [
                    "matplotlib TclError 간헐적 발생",
                    "테스트가 가끔 무작위 실패 → 추적 후 원인 특정",
                    "비대화형 Agg 백엔드 강제 지정",
                ],
                [
                    "폴리곤화 결과 0개일 때 크래시",
                    "극단 케이스 테스트 중 발견",
                    "빈 GeoDataFrame 스키마 명시",
                ],
                [
                    "PDF 코드블록 한글 깨짐",
                    "본 문서 초안 검토 중 발견",
                    "코드블록은 ASCII만, 한글은 별도 문단/표",
                ],
                [
                    "실행 CRS 조회 실패 가능성",
                    "개발 환경 PROJ 충돌 재현 중 발견",
                    "PROJ 조회 실패 방어 코드 추가",
                ],
            ],
            s,
            col_widths=[95, 175, 190],
        )
    )

    # ================================================================== 6. 테스트
    story.append(Paragraph("6. 테스트 및 검증 기록", s["h1"]))
    story.append(
        bullet_list(
            [
                "<b>pytest 65개 전부 통과</b> — 합성 데이터 단위 테스트 + 실제 데이터 통합 테스트 + processed_dir 회귀 테스트 2개",
                "<b>ruff check ., black --check</b> 클린",
                "<b>실제 QGIS 3.44.12 검증</b>: 생명주기, 재로드 시 중복 없음, Processing provider, Dependencies 탭 실측, "
                "on_validate 크래시 재현·수정, Clear Inputs 버튼 동작, embedded-without-venv 방식 전체 파이프라인 성공",
                "<b>실제 데이터 파이프라인 실행</b>: GeoTIFF/GeoPackage 재오픈 검증, docs/example_queries.sql 9개 쿼리 실행 확인",
                "<b>재현성</b>: 동일 seed 두 번 실행 시 수치 완전 동일 확인",
            ],
            s,
        )
    )

    # ================================================================== 7. 한계
    story.append(Paragraph("7. 주요 가정 및 한계", s["h1"]))
    story.append(
        bullet_list(
            [
                "Sentinel-2 반사도 scale factor = 10000 가정 (메타데이터 미제공, ESA 표준 관행 적용)",
                "밴드 스택 순서는 R-G-B(B04,B03,B02)",
                "B08(NIR) 없어 NDVI 계산 불가",
                "구름/그림자 마스크(SCL) 없음",
                "시점 2개뿐이라 계절성/영구적 변화 분리 불가",
                "정답 레이블 없음 — accuracy/precision/recall 어디서도 주장하지 않음",
                "confidence는 보정된 확률이 아닌 휴리스틱 점수",
                "Gi*/Moran's I 유의성은 공간 패턴만 설명, 원인(채굴 행위 등) 확정 아님",
            ],
            s,
        )
    )
    story.append(PageBreak())

    # ================================================================== 부록
    story.append(Paragraph("부록 A. 예시 SQL 쿼리", s["h1"]))
    story.append(
        Paragraph(
            "<font face='Courier'>docs/example_queries.sql</font>에 9개 쿼리가 있고, 전부 실제 DB에 실행해 "
            "검증했습니다. 대표 예시:",
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

    story.append(Paragraph("부록 B. 용어 설명", s["h1"]))
    story.append(
        make_table(
            ["용어", "설명"],
            [
                [
                    "CVA",
                    "Change Vector Analysis — 다중 밴드 변화를 하나의 벡터 크기로 결합하는 기법",
                ],
                ["MAD", "Median Absolute Deviation — 이상치에 강건한 산포도 지표"],
                ["Moran's I", "전역 공간 자기상관 지수 (-1~1, 양수=군집, 음수=분산)"],
                [
                    "LISA",
                    "Local Indicators of Spatial Association — Local Moran's I 기반 군집 분류",
                ],
                ["Getis-Ord Gi*", "국지적 hot/cold spot 통계적 유의성 검정"],
                ["FDR", "False Discovery Rate — 다중 검정 시 거짓 양성 비율 통제"],
                ["confidence", "0-1 휴리스틱 점수, 보정된 확률 아님"],
                ["GeoPackage", "OGC 표준 공간 데이터 포맷, 내부적으로 SQLite 파일"],
            ],
            s,
            col_widths=[100, 335],
        )
    )
    story.append(Spacer(1, 10))
    story.append(hr())
    story.append(
        Paragraph(
            "함께 제출된 <font face='Courier'>README.md</font>(GitHub 저장소 최상위)와 "
            "<font face='Courier'>report.md</font>에도 이 내용의 영문판이 있습니다.",
            s["caption"],
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
