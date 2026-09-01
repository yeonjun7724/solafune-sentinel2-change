# 제출 번들 안내 (Submission Bundle)

이 폴더 하나에 **QGIS 플러그인 버전**, **스크립트(CLI) 버전**, **원본 데이터**, **실제 실행 결과물**, 그리고 상세 사용 설명서가 함께 들어 있습니다.

**먼저 볼 것: `Usage_Guide.pdf` (16페이지)** — 아래 요약보다 훨씬 자세합니다. QGIS 플러그인 설치/의존성 설정(별도 venv 없이 하는 법 포함, 실측 검증)/탭별 필드 전체/진행 단계/문제 해결, 스크립트 버전의 전체 CLI·config 레퍼런스, 실제 분석 결과, 알고리즘 근거, DB 스키마, 개발 중 발견한 버그 8건, 테스트 기록, 한계까지 전부 담았습니다.

```
submission/
├── README.md                              ← 이 파일 (요약)
├── Usage_Guide.pdf                        ← 상세 사용 설명서 (16페이지)
├── solafune_change_analyzer.zip           ← ① QGIS 플러그인 설치 파일
├── solafune_change_analyzer.zip.sha256    ← ①의 체크섬
├── solafune-sentinel2-change-source.zip   ← ② 스크립트(CLI) 버전 = GitHub "Download ZIP"과 동일 구조
├── data/                                  ← ③ 원본 입력 데이터 (확인용 별도 복사본)
└── results/                               ← ④ 실제 실행 결과물 원본 (재실행 없이 바로 확인)
    ├── outputs/                           ← GeoPackage DB, 정적 그림, 인터랙티브 지도, 공간통계, report.md 등
    └── data_processed/                    ← 스택 GeoTIFF, baseline/CVA intensity·binary 래스터
```

GitHub 원본 저장소(커밋 이력 포함): https://github.com/yeonjun7724/solafune-sentinel2-change

---

## ① `solafune_change_analyzer.zip` — QGIS 플러그인 버전

QGIS **안에서 GUI로** 클릭해서 사용하는 버전입니다. 이 zip 파일 **하나만** 있으면 됩니다 (분석 엔진 코드가 내부에 vendored되어 있어 다른 파일이 필요 없음).

### 설치
1. QGIS 실행 (3.28 이상, 3.44.12에서 실제 테스트 완료)
2. 메뉴 **Plugins → Manage and Install Plugins → Install from ZIP**
3. `solafune_change_analyzer.zip` 선택 → **Install Plugin**
4. 설치 후 `Installed` 탭에서 "Solafune Change Analyzer" 체크(활성화) 확인
5. 툴바 아이콘 클릭 또는 **Plugins → Solafune Change Analyzer** 메뉴로 실행

### 의존성 설정 — 별도 `.venv` 없이도 가능
대부분의 Windows/OSGeo4W QGIS는 `rasterio`/`scikit-learn`/`libpysal`/`esda` 등이 기본 내장되어 있지 않습니다. **별도 폴더를 만들지 않고** QGIS 자체 Python에 한 번만 설치하면 됩니다 (실측 검증 완료 — 전체 파이프라인이 임베디드 모드에서 끝까지 성공):
```powershell
cd "C:\Program Files\QGIS 3.44.12\bin"
python-qgis-ltr.bat -m pip install --user rasterio geopandas shapely pyproj scipy scikit-image PyYAML libpysal esda scikit-learn matplotlib folium
```
더 격리된 방식(별도 `.venv` + External interpreter)을 원한다면 `Usage_Guide.pdf`의 A.4절을 참고하세요.

### 사용법 (Dock Widget)
1. **Inputs 탭**: Before/After Sentinel-2 폴더, AOI 파일, 출력 폴더 선택 → **Validate Inputs** 클릭 (경로를 다시 고르고 싶으면 **Clear Inputs(초기화)** 버튼)
2. **Change Detection 탭**: 분석 방법(baseline/CVA/both), threshold, morphology 등 설정
3. **Spatial Analysis 탭**: 공간통계(Moran's I / Gi*) 및 실험적 ML 옵션 설정
4. **Dependencies 탭**: 위 설치가 끝났다면 모든 항목이 "Ready"로 표시됩니다
5. **Run & Results 탭**: **Run Analysis** 클릭 → 진행률/로그 확인 → 완료 시 결과 레이어가 QGIS 프로젝트에 자동 로드됨

### 체크섬 검증 (선택)
```powershell
certutil -hashfile solafune_change_analyzer.zip SHA256
# solafune_change_analyzer.zip.sha256 파일 내용과 비교
```

### 자세한 문서
`Usage_Guide.pdf` 전체, 또는 `solafune-sentinel2-change-source.zip`을 풀면 나오는 `docs/QGIS_PLUGIN_USER_GUIDE.md`(사용법), `docs/QGIS_PLUGIN_DEVELOPMENT.md`(개발), `docs/QGIS_PLUGIN_ARCHITECTURE.md`(구조), `docs/QGIS_PLUGIN_TEST_CHECKLIST.md`(실제 검증 기록)를 참고하세요.

---

## ② `solafune-sentinel2-change-source.zip` — 스크립트(CLI) 버전 (= GitHub Download ZIP)

QGIS 없이 **터미널에서 명령어로** 실행하는 버전입니다. `git archive HEAD`로 만들어 GitHub에 올라간 최신 커밋과 **완전히 동일한 내용**이며(`solafune-sentinel2-change-master/` 폴더로 감싸진 구조 — GitHub 저장소 페이지의 "Code → Download ZIP"과 동일), 원본 입력 데이터(`inputs/`)까지 이미 포함되어 있어 압축만 풀면 바로 실행됩니다.

### 설치
```bash
unzip solafune-sentinel2-change-source.zip
cd solafune-sentinel2-change-master

python -m venv .venv
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\pip install -e .
```
(macOS/Linux는 `.venv\Scripts\...` 대신 `source .venv/bin/activate` 후 `pip ...`)

### 실행 — 한 줄 명령
```bash
solafune-change all --config config/default.yaml
```
약 30초 안에 전체 파이프라인이 끝나고, 결과는 `outputs/`(DB, 그림, 지도, 통계, 요약 JSON)와 `data/processed/`(중간 GeoTIFF)에 생성됩니다.

### 개별 명령어 / 옵션 / config.yaml 전체 필드
`Usage_Guide.pdf`의 PART B (B.4~B.10)에 전체 표로 정리되어 있습니다.

### 테스트
```bash
python -m pytest tests/ -v      # 65개 테스트
```

---

## ③ `data/` — 원본 입력 데이터 (확인용)

`aoi.geojson`, `example_change_detection.py`, `instructions.pdf`, `data/sentinel2_20230812/`·`data/sentinel2_20230902/`(B02/B03/B04 GeoTIFF). ①·②에는 이미 포함되어 있어 없어도 실행 가능 — 압축을 풀지 않고 원본 위성영상을 바로 열어보고 싶을 때를 위한 별도 복사본입니다.

## ④ `results/` — 실제 실행 결과물 원본 (재실행 불필요)

코드를 실행하지 않아도 바로 열어볼 수 있는, 실제로 파이프라인을 돌려서 나온 최종 산출물입니다.

- `results/outputs/database/change_analysis.gpkg` — GeoPackage (QGIS/DB Browser로 바로 열람 가능)
- `results/outputs/figures/change_comparison.png` — baseline vs CVA vs Gi* 비교 그림
- `results/outputs/maps/interactive_map.html` — 인터랙티브 지도 (브라우저로 더블클릭해서 열기, 오프라인 동작)
- `results/outputs/statistics/`, `results/outputs/report.md`, `results/outputs/summary.json` 등
- `results/data_processed/` — 스택 GeoTIFF, baseline/CVA intensity·binary 래스터

(② 소스 zip에는 용량 문제로 이 결과 파일들이 포함되어 있지 않습니다 — 재실행 없이 바로 결과만 보고 싶다면 여기를 여세요.)

---

## 요약 표

| 실행 방식 | 필요한 파일 | 실행 명령/방법 | QGIS 필요 여부 |
|---|---|---|---|
| GUI (플러그인) | `solafune_change_analyzer.zip` | Plugins → Install from ZIP → Dock Widget에서 Run 클릭 | 필요 (QGIS 3.28+) |
| CLI (스크립트) | `solafune-sentinel2-change-source.zip` | 압축 해제 → `pip install -e .` → `solafune-change all --config config/default.yaml` | 불필요 |
| 결과만 확인 | `results/` | 그대로 열람 (QGIS/브라우저 등으로) | 불필요 |
| 데이터만 확인 | `data/` | 그대로 열람 (QGIS/GDAL 등으로) | 불필요 |

두 실행 방식 모두 **같은 분석 엔진**(`solafune_change` 코어 패키지)을 사용하므로 결과가 동일합니다 — 코드가 두 벌로 나뉘어 있지 않습니다.
