# Initial Bicycle Research Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a lightweight Windows research platform that retrieves a small OSM bicycle network, records attribute completeness, and displays the retrieved roads in a plain HTML/CSS/JavaScript Leaflet page served by FastAPI.

**Architecture:** One FastAPI process serves a health API, static frontend files, and generated GeoJSON. A separate Python module performs deterministic tag classification and coverage calculations, while a command-line script alone contacts Overpass through OSMnx and writes GraphML, GeoJSON, CSV, and JSON artifacts.

**Tech Stack:** Python 3.10.11, FastAPI, Uvicorn, OSMnx 2.0.6, NetworkX, GeoPandas, Shapely, pytest, plain HTML/CSS/JavaScript, Leaflet 1.9.4.

## Global Constraints

- Project root is exactly `E:\graduation-research\bicycle-rule-routing`.
- Keep `.venv`, pip cache, OSMnx cache, and downloaded data on drive E.
- Do not install Docker, React, TypeScript, Vite, npm packages, a database, authentication, or a UI component library.
- Do not change PowerShell execution policy, machine PATH, registry, or system-wide Python configuration.
- Use existing Python 3.10.11 and pin OSMnx 2.0.6 because it officially supports Python 3.10.
- Treat an absent OSM tag as unknown; do not infer that the mapped facility is absent.
- The product is a research aid and must not claim to make legal violation determinations.
- Behavioral Python code follows red-green-refactor. Declarative HTML/CSS/configuration is verified by integration and browser checks.

---

### Task 1: Reproducible E-drive environment

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `backend/requirements.txt`
- Create: `docs/environment-report.md`
- Create: `docs/work-log.md`
- Create: `data/raw/.gitkeep`
- Create: `data/processed/.gitkeep`
- Create: `data/exports/.gitkeep`

**Interfaces:**
- Consumes: existing Python at `C:\Users\p-user\AppData\Local\Programs\Python\Python310\python.exe`
- Produces: `.venv\Scripts\python.exe`, `.cache\pip`, `.cache\osmnx`, documented environment variables

- [ ] **Step 1: Create project directories and configuration files**

`.env.example`:

```dotenv
OSM_CENTER_LAT=35.681236
OSM_CENTER_LON=139.767125
OSM_DISTANCE_METERS=500
OSM_PLACE_LABEL=Tokyo Station
```

`.gitignore`:

```gitignore
.venv/
.cache/
.env
__pycache__/
.pytest_cache/
*.py[cod]
data/raw/*
data/processed/*
data/exports/*
!data/raw/.gitkeep
!data/processed/.gitkeep
!data/exports/.gitkeep
```

`backend/requirements.txt`:

```text
fastapi>=0.115,<1
httpx>=0.28,<1
osmnx==2.0.6
python-dotenv>=1,<2
pytest>=8,<10
uvicorn>=0.34,<1
```

- [ ] **Step 2: Create the E-drive virtual environment and pip cache**

Run:

```powershell
$env:PIP_CACHE_DIR='E:\graduation-research\bicycle-rule-routing\.cache\pip'
python -m venv 'E:\graduation-research\bicycle-rule-routing\.venv'
E:\graduation-research\bicycle-rule-routing\.venv\Scripts\python.exe -m pip install --upgrade pip
E:\graduation-research\bicycle-rule-routing\.venv\Scripts\python.exe -m pip install -r E:\graduation-research\bicycle-rule-routing\backend\requirements.txt
```

- [ ] **Step 3: Verify imports and resolved versions**

Run:

```powershell
E:\graduation-research\bicycle-rule-routing\.venv\Scripts\python.exe -c "import fastapi, osmnx, networkx, geopandas, shapely; print(fastapi.__version__, osmnx.__version__)"
E:\graduation-research\bicycle-rule-routing\.venv\Scripts\python.exe -m pip check
```

Expected: imports succeed, OSMnx reports `2.0.6`, and `pip check` reports no broken requirements.

- [ ] **Step 4: Record the environment**

Document OS version, E-drive free space, installed/missing tools, Python/Node/Git/VS Code versions, the `npm.ps1` policy observation, the OSMnx/Python compatibility decision, download/cache locations, and that no administrator or system-wide change was made.

- [ ] **Step 5: Commit**

```powershell
git add .gitignore .env.example backend/requirements.txt docs/environment-report.md docs/work-log.md
git commit -m "chore: prepare E-drive research environment"
```

### Task 2: FastAPI health API and static delivery

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/tests/test_static_app.py`
- Create: `frontend/index.html`
- Create: `frontend/styles.css`
- Create: `frontend/app.js`

**Interfaces:**
- Produces: `backend.app.main.app: FastAPI`
- Produces: `GET /api/health -> {"status":"ok","service":"bicycle-rule-routing-api"}`
- Produces: `GET /`, `/static/*`, and `/data/*`

- [ ] **Step 1: Write the failing health test**

```python
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_health_reports_service_ready() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "bicycle-rule-routing-api",
    }
```

- [ ] **Step 2: Run the health test and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend\tests\test_health.py -v
```

Expected: collection/import fails because `backend.app.main` does not yet exist.

- [ ] **Step 3: Implement the minimal FastAPI application**

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
EXPORT_DIR = PROJECT_ROOT / "data" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Bicycle Rule Routing Research API")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/data", StaticFiles(directory=EXPORT_DIR), name="data")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "bicycle-rule-routing-api"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
```

- [ ] **Step 4: Run the health test and verify GREEN**

Run the Step 2 command. Expected: one passing test.

- [ ] **Step 5: Write the failing static-page test**

```python
def test_root_serves_research_map_shell() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="map"' in response.text
    assert 'id="api-status"' in response.text
```

- [ ] **Step 6: Run the static-page test and verify RED**

Expected: file-not-found or response failure because `frontend/index.html` does not exist.

- [ ] **Step 7: Add the minimal HTML, CSS, and JavaScript**

`frontend/index.html`:

```html
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>自転車ルール遵守支援システム</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
    <link rel="stylesheet" href="/static/styles.css">
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" defer></script>
    <script src="/static/app.js" defer></script>
  </head>
  <body>
    <header>
      <p class="eyebrow">卒業研究・初期基盤</p>
      <h1>自転車ルール遵守支援システム</h1>
      <p>OpenStreetMapから取得した自転車道路ネットワークを確認します。</p>
    </header>
    <main>
      <section class="status-panel" aria-label="システム状態">
        <p>API: <strong id="api-status">確認中</strong></p>
        <p>道路データ: <strong id="data-status">確認中</strong></p>
      </section>
      <div id="map" aria-label="OpenStreetMap道路地図"></div>
      <p class="notice">
        本システムは研究用の注意喚起支援であり、交通違反を法的に判定するものではありません。
      </p>
    </main>
  </body>
</html>
```

`frontend/styles.css`:

```css
:root {
  font-family: "Yu Gothic UI", "Meiryo", sans-serif;
  color: #1f2933;
  background: #f4f7f5;
}

body {
  margin: 0;
}

header,
main {
  width: min(960px, calc(100% - 32px));
  margin: 0 auto;
}

header {
  padding: 32px 0 16px;
}

h1 {
  margin: 4px 0 8px;
}

.eyebrow {
  margin: 0;
  color: #26734d;
  font-weight: 700;
}

.status-panel {
  display: flex;
  gap: 24px;
  padding: 12px 16px;
  background: white;
  border: 1px solid #d7e1db;
}

#map {
  height: 520px;
  margin-top: 16px;
  border: 1px solid #c5d2ca;
}

.notice {
  font-size: 0.9rem;
}

@media (max-width: 600px) {
  .status-panel {
    display: block;
  }

  #map {
    height: 420px;
  }
}
```

`frontend/app.js`:

```javascript
const apiStatus = document.querySelector("#api-status");
const dataStatus = document.querySelector("#data-status");
const map = L.map("map").setView([35.681236, 139.767125], 15);

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

async function checkApi() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    apiStatus.textContent = result.status === "ok" ? "接続済み" : "異常";
  } catch (error) {
    apiStatus.textContent = "接続できません";
    console.error("Health API check failed:", error);
  }
}

async function loadRoads() {
  try {
    const response = await fetch("/data/sample_edges.geojson");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const geojson = await response.json();
    const layer = L.geoJSON(geojson, {
      style: { color: "#256f4a", weight: 3, opacity: 0.8 },
    }).addTo(map);
    if (layer.getBounds().isValid()) map.fitBounds(layer.getBounds());
    dataStatus.textContent = `${geojson.features.length}区間を表示`;
  } catch (error) {
    dataStatus.textContent = "未生成（OSM取得スクリプトを実行してください）";
    console.warn("Road GeoJSON is not available:", error);
  }
}

checkApi();
loadRoads();
```

- [ ] **Step 8: Run both API tests and verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend\tests\test_health.py backend\tests\test_static_app.py -v
```

- [ ] **Step 9: Commit**

```powershell
git add backend frontend
git commit -m "feat: serve health API and research map"
```

### Task 3: OSM tag-state and coverage analysis

**Files:**
- Create: `backend/app/osm_analysis.py`
- Create: `backend/tests/test_osm_analysis.py`

**Interfaces:**
- Produces: `classify_tag(value: object) -> str`
- Produces: `calculate_tag_coverage(edges: geopandas.GeoDataFrame, tags: list[str]) -> pandas.DataFrame`
- Produces: `build_network_summary(node_count: int, edge_count: int, edges: geopandas.GeoDataFrame) -> dict[str, float | int]`

- [ ] **Step 1: Write the failing classification tests**

```python
import pytest

from backend.app.osm_analysis import classify_tag


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "unknown"),
        ("", "unknown"),
        ("no", "explicit_absent"),
        (False, "explicit_absent"),
        ("lane", "present"),
        (True, "present"),
        (["no", "lane"], "present"),
    ],
)
def test_classify_tag_distinguishes_unknown_absent_and_present(
    value: object,
    expected: str,
) -> None:
    assert classify_tag(value) == expected
```

- [ ] **Step 2: Verify RED, then implement minimal classification**

Normalize scalar/list values. Empty or null values are unknown, only `no`, `none`, and boolean false are explicit absence, and any positive value makes a list present.

- [ ] **Step 3: Verify classification GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend\tests\test_osm_analysis.py -v
```

- [ ] **Step 4: Write the failing length-weighted coverage test**

```python
import geopandas as gpd
from shapely.geometry import LineString

from backend.app.osm_analysis import calculate_tag_coverage


def test_coverage_is_weighted_by_length_and_preserves_unknown() -> None:
    edges = gpd.GeoDataFrame(
        {"length": [100.0, 200.0, 300.0], "cycleway": ["lane", "no", None]},
        geometry=[
            LineString([(0, 0), (100, 0)]),
            LineString([(0, 0), (200, 0)]),
            LineString([(0, 0), (300, 0)]),
        ],
        crs="EPSG:3857",
    )

    row = calculate_tag_coverage(edges, ["cycleway"]).iloc[0]

    assert row.to_dict() == {
        "tag": "cycleway",
        "total_length_m": 600.0,
        "recorded_length_m": 300.0,
        "present_length_m": 100.0,
        "explicit_absent_length_m": 200.0,
        "unknown_length_m": 300.0,
        "recorded_pct": 50.0,
        "unknown_pct": 50.0,
    }
```

- [ ] **Step 5: Verify RED, implement minimal coverage calculation, verify GREEN**

The result must contain these columns:

```text
tag
total_length_m
recorded_length_m
present_length_m
explicit_absent_length_m
unknown_length_m
recorded_pct
unknown_pct
```

- [ ] **Step 6: Write the failing network summary test**

```python
from backend.app.osm_analysis import build_network_summary


def test_summary_reports_counts_and_total_length() -> None:
    edges = gpd.GeoDataFrame(
        {"length": [100.0, 250.0]},
        geometry=[
            LineString([(0, 0), (100, 0)]),
            LineString([(0, 0), (250, 0)]),
        ],
        crs="EPSG:3857",
    )

    assert build_network_summary(3, 2, edges) == {
        "node_count": 3,
        "edge_count": 2,
        "total_edge_length_m": 350.0,
        "total_edge_length_km": 0.35,
    }
```

- [ ] **Step 7: Verify RED, implement summary, verify all GREEN**

Run the complete test module and then the full backend test suite.

- [ ] **Step 8: Commit**

```powershell
git add backend/app/osm_analysis.py backend/tests/test_osm_analysis.py
git commit -m "feat: analyze OSM tag completeness"
```

### Task 4: OSM acquisition and artifact generation

**Files:**
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/fetch_osm_sample.py`
- Create: `backend/tests/test_fetch_config.py`

**Interfaces:**
- Produces: `parse_fetch_config(values: Mapping[str, str]) -> FetchConfig`
- Produces: `load_fetch_config() -> FetchConfig`
- Produces: `main() -> int`
- Writes: `data/raw/sample_bike.graphml`
- Writes: `data/exports/sample_nodes.geojson`
- Writes: `data/exports/sample_edges.geojson`
- Writes: `data/processed/tag_coverage.csv`
- Writes: `data/processed/summary.json`

- [ ] **Step 1: Write a failing configuration validation test**

```python
import pytest

from backend.scripts.fetch_osm_sample import parse_fetch_config


def test_parse_fetch_config_accepts_valid_values() -> None:
    config = parse_fetch_config(
        {
            "OSM_CENTER_LAT": "35.681236",
            "OSM_CENTER_LON": "139.767125",
            "OSM_DISTANCE_METERS": "500",
            "OSM_PLACE_LABEL": "Tokyo Station",
        }
    )
    assert config.latitude == 35.681236
    assert config.longitude == 139.767125
    assert config.distance_m == 500
    assert config.place_label == "Tokyo Station"


@pytest.mark.parametrize(
    "override",
    [
        {"OSM_CENTER_LAT": "91"},
        {"OSM_CENTER_LON": "-181"},
        {"OSM_DISTANCE_METERS": "99"},
        {"OSM_DISTANCE_METERS": "5001"},
    ],
)
def test_parse_fetch_config_rejects_out_of_range_values(
    override: dict[str, str],
) -> None:
    values = {
        "OSM_CENTER_LAT": "35.681236",
        "OSM_CENTER_LON": "139.767125",
        "OSM_DISTANCE_METERS": "500",
        "OSM_PLACE_LABEL": "Tokyo Station",
        **override,
    }
    with pytest.raises(ValueError):
        parse_fetch_config(values)
```

- [ ] **Step 2: Verify RED, implement `FetchConfig`, verify GREEN**

Load `.env` with `python-dotenv`, allow process environment variables to override it, and return a frozen dataclass.

- [ ] **Step 3: Implement the external acquisition boundary**

Configure OSMnx cache under `.cache/osmnx`, append the specified way/node tags without duplicates, call `ox.graph.graph_from_point((lat, lon), dist=distance, network_type="bike")`, reject an empty graph, convert to GeoDataFrames, save GraphML/GeoJSON, run coverage and summary functions, and write UTF-8 CSV/JSON.

- [ ] **Step 4: Run all automated tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest backend\tests -v
```

- [ ] **Step 5: Run a real 500-meter acquisition**

Run:

```powershell
Copy-Item .env.example .env
.venv\Scripts\python.exe -m backend.scripts.fetch_osm_sample
```

Expected: all five output files exist and contain non-empty data.

- [ ] **Step 6: Inspect outputs and re-run to exercise cache**

Record node/edge counts, road length, tag coverage, output sizes, elapsed time, and cache file count before and after the second run.

- [ ] **Step 7: Commit**

Commit source and tests only. Keep `.env`, cache, virtual environment, and raw/generated research data ignored.

### Task 5: Browser-visible integration

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Modify: `frontend/app.js`
- Modify: `docs/work-log.md`

**Interfaces:**
- Consumes: `/api/health`, `/data/sample_edges.geojson`
- Produces: browser-visible API status, data status, base map, and retrieved road overlay

- [ ] **Step 1: Start FastAPI**

Run:

```powershell
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

- [ ] **Step 2: Verify HTTP boundaries**

Run:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-WebRequest http://127.0.0.1:8000/
Invoke-WebRequest http://127.0.0.1:8000/data/sample_edges.geojson
```

- [ ] **Step 3: Inspect in a browser**

Verify the page shows the map, API-connected status, OSM attribution, research disclaimer, and retrieved roads. Verify the browser console has no application errors.

- [ ] **Step 4: Record evidence and commit any necessary corrections**

Add actual commands and observations to `docs/work-log.md`. Any bug correction must first receive a failing regression test where practical.

### Task 6: Documentation and completion audit

**Files:**
- Create: `README.md`
- Modify: `docs/environment-report.md`
- Modify: `docs/work-log.md`

**Interfaces:**
- Produces: reproducible setup, fetch, run, test, troubleshooting, research interpretation, and next-step instructions

- [ ] **Step 1: Write README**

Include project purpose, non-goals, architecture, directory layout, E-drive storage policy, setup commands, `.env` configuration, OSM fetch command, run command, test command, generated artifact descriptions, tag interpretation, OSM limitations/attribution, troubleshooting, and next-stage TODOs.

- [ ] **Step 2: Add next-stage TODOs**

List rule/tag correspondence validation, shortest baseline, rule-compliance cost, safety cost, unknown-data cost, route comparison, warning-point display, study-area change, ground-truth sampling, and evaluation design.

- [ ] **Step 3: Run fresh verification**

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m pytest backend\tests -v
.venv\Scripts\python.exe -m backend.scripts.fetch_osm_sample
git status --short
```

Also verify each required artifact exists, JSON/GeoJSON parse, CSV has expected columns, and GraphML reloads through OSMnx.

- [ ] **Step 4: Commit documentation**

```powershell
git add README.md docs .gitignore .env.example backend frontend
git commit -m "docs: document initial research workflow"
```

- [ ] **Step 5: Requirement-by-requirement audit**

Map every Goal requirement to direct evidence: file path, test output, HTTP output, browser observation, generated artifact inspection, or environment report entry. Any missing evidence means the Goal remains active.
