# Phase 5 Batch Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 東京駅周辺3 kmの20 ODペアについて5プロファイルを一括評価し、9通りの重み感度分析を再現可能なCSVへ出力するとともに、プレゼンテーション向けUIと簡易起動導線を提供する。

**Architecture:** 既存の`backend.app.routing`へプロファイル設定の明示的注入とエッジ列を使う経路シグネチャを追加し、互換性を維持したまま`backend.app.evaluation`から直接呼び出す。OD選定、評価CLI、Web UI、Windows起動ファイルを責務ごとに分離し、生成データは`data/processed`へ、再現用入力だけを`data/input`へ保存する。

**Tech Stack:** Python 3.12、NetworkX、OSMnx、pandas、FastAPI、pytest、HTML/CSS/JavaScript、Leaflet、Windows CMD

**Spec:** `docs/superpowers/specs/2026-09-14-phase-5-batch-evaluation-design.md`

## Global Constraints

- 5プロファイルのIDと既存API入出力は維持する。
- `information`の表示名だけを「OSMデータ充足度優先」へ変更する。
- `medium`×`medium`は現在の`ROUTE_PROFILES`と同じ重みにする。
- 感度倍率は`weak=0.5`、`medium=1.0`、`strong=2.0`とする。
- 通常評価は20×5=100行、感度分析は20×5×9=900行、感度集計は5×9=45行とする。
- CSVはUTF-8 BOM付きで保存する。
- 生成データはGit管理外、`data/input/od_pairs.csv`はGit管理対象とする。
- グローバルな`ROUTE_PROFILES`を評価中に変更しない。
- Pythonの動作変更はred-green-refactorで進める。
- 法的な違反判定、重みの妥当性確定、注意地点表示、自然言語の選定理由生成は行わない。

---

### Task 1: 注入可能なプロファイル設定とエッジ経路

**Files:**
- Modify: `backend/app/routing.py:31-380`
- Modify: `backend/tests/test_routing.py`
- Modify: `backend/tests/test_route_api.py`

**Interfaces:**
- Produces: `ProfileMap = Mapping[str, Mapping[str, Any]]`
- Produces: `scale_profile_weights(*, safety_multiplier: float, unknown_multiplier: float) -> dict[str, dict[str, Any]]`
- Extends: `calculate_profile_cost(edge, profile_id, *, profiles=ROUTE_PROFILES) -> float`
- Extends: `build_route_result(graph: nx.MultiDiGraph, *, source: Hashable, target: Hashable, profile_id: str = "shortest", profiles: ProfileMap = ROUTE_PROFILES) -> dict[str, Any]`
- Extends: `build_route_comparison(graph: nx.MultiDiGraph, *, source: Hashable, target: Hashable, profiles: ProfileMap = ROUTE_PROFILES) -> list[dict[str, Any]]`
- Adds result field: `edge_path: list[tuple[Hashable, Hashable, Hashable]]`

- [ ] **Step 1: Write failing tests for the renamed profile and isolated scaling**

Add to `backend/tests/test_routing.py`:

```python
from copy import deepcopy

from backend.app.routing import ROUTE_PROFILES, scale_profile_weights


def test_information_profile_uses_osm_completeness_label() -> None:
    assert ROUTE_PROFILES["information"]["label"] == "OSMデータ充足度優先"


def test_scaled_profile_weights_do_not_mutate_defaults() -> None:
    original = deepcopy(ROUTE_PROFILES)

    scaled = scale_profile_weights(
        safety_multiplier=2.0,
        unknown_multiplier=0.5,
    )

    assert scaled["safety"]["weights"] == {
        "road_type": 1.6,
        "cycleway": 1.2,
        "unknown": 0.05,
    }
    assert ROUTE_PROFILES == original
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_routing.py -k "osm_completeness or scaled_profile" -v
```

Expected: collection fails because`scale_profile_weights` does not exist, and the old label does not match.

- [ ] **Step 3: Implement immutable scaling and rename the label**

In `backend/app/routing.py`, use a deep copy and scale only the intended components:

```python
from copy import deepcopy
from collections.abc import Mapping

ProfileMap = Mapping[str, Mapping[str, Any]]


def scale_profile_weights(
    *,
    safety_multiplier: float,
    unknown_multiplier: float,
) -> dict[str, dict[str, Any]]:
    if safety_multiplier < 0 or unknown_multiplier < 0:
        raise ValueError("weight multipliers must be non-negative")
    profiles = deepcopy(ROUTE_PROFILES)
    for profile in profiles.values():
        weights = profile["weights"]
        weights["road_type"] *= safety_multiplier
        weights["cycleway"] *= safety_multiplier
        weights["unknown"] *= unknown_multiplier
    return profiles
```

Change only the information label:

```python
"label": "OSMデータ充足度優先",
```

- [ ] **Step 4: Add failing tests for custom profile routing and edge identity**

Add to `backend/tests/test_routing.py`:

```python
def test_route_result_exposes_selected_edge_path() -> None:
    result = build_route_result(
        build_profile_test_graph(), source=1, target=4, profile_id="shortest"
    )
    assert result["edge_path"] == [(1, 2, 0), (2, 4, 0)]


def test_custom_profiles_change_route_without_mutating_defaults() -> None:
    graph = build_profile_test_graph()
    custom = scale_profile_weights(
        safety_multiplier=3.0,
        unknown_multiplier=1.0,
    )

    result = build_route_result(
        graph,
        source=1,
        target=4,
        profile_id="balanced",
        profiles=custom,
    )

    assert result["node_path"] == [1, 3, 4]
```

- [ ] **Step 5: Run the new tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_routing.py -k "edge_path or custom_profiles" -v
```

Expected: `build_route_result` rejects the `profiles` keyword and does not return `edge_path`.

- [ ] **Step 6: Thread the profile map through routing helpers**

Update these functions to accept the same profile map without changing default callers. In`calculate_profile_cost`, replace the global lookup with`profiles.get(profile_id)`, keep the existing component calculation, and read weights from the returned profile:

```python
def calculate_profile_cost(
    edge: dict[str, Any],
    profile_id: str,
    *,
    profiles: ProfileMap = ROUTE_PROFILES,
) -> float:
    profile = profiles.get(profile_id)
    if profile is None:
        raise ValueError(f"unknown route profile: {profile_id}")
    components = calculate_edge_cost_components(edge)
    if profile["enforce_prohibited"] and components["prohibited"]:
        return math.inf
    weights = profile["weights"]
    multiplier = (
        1.0
        + weights["road_type"] * components["road_type_risk"]
        + weights["cycleway"] * components["cycleway_risk"]
        + weights["unknown"] * components["unknown_risk"]
    )
    return round(components["distance_m"] * multiplier, 6)
```

Use these exact public signatures for the two route builders:

```python

def build_route_result(
    graph: nx.MultiDiGraph,
    *,
    source: Hashable,
    target: Hashable,
    profile_id: str = "shortest",
    profiles: ProfileMap = ROUTE_PROFILES,
) -> dict[str, Any]:

def build_route_comparison(
    graph: nx.MultiDiGraph,
    *,
    source: Hashable,
    target: Hashable,
    profiles: ProfileMap = ROUTE_PROFILES,
) -> list[dict[str, Any]]:
```

Pass `profiles` into `_profile_weight_function`, `_select_profile_parallel_edge`, and `_edge_feature`. Add this field to the result:

```python
"edge_path": [(start, end, key) for start, end, key, _data in selected_edges],
```

- [ ] **Step 7: Run routing and API tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_routing.py backend\tests\test_route_api.py -v
```

Expected: all tests pass and the existing API remains compatible.

- [ ] **Step 8: Commit Task 1**

```powershell
git add backend/app/routing.py backend/tests/test_routing.py backend/tests/test_route_api.py
git commit -m "feat: support configurable route profiles"
```

---

### Task 2: OD入力検証と通常一括評価

**Files:**
- Create: `backend/app/evaluation.py`
- Create: `backend/tests/test_evaluation.py`

**Interfaces:**
- Produces: `ODPair` frozen dataclass
- Produces: `load_od_pairs(path: Path) -> list[ODPair]`
- Produces: `route_signature(edge_path: Sequence[tuple[Hashable, Hashable, Hashable]]) -> str`
- Produces: `evaluate_profiles(graph: nx.MultiDiGraph, od_pairs: Sequence[ODPair], *, profiles=ROUTE_PROFILES) -> pd.DataFrame`

- [ ] **Step 1: Write failing OD CSV validation tests**

Create `backend/tests/test_evaluation.py` with fixtures that write CSVs through pandas and verify:

```python
def test_load_od_pairs_reads_valid_csv(tmp_path: Path) -> None:
    path = tmp_path / "od_pairs.csv"
    pd.DataFrame([
        {
            "od_id": "OD-01",
            "origin_label": "地点01-A",
            "origin_lat": 35.0,
            "origin_lon": 139.0,
            "destination_label": "地点01-B",
            "destination_lat": 35.001,
            "destination_lon": 139.001,
            "distance_band": "short",
        }
    ]).to_csv(path, index=False)

    pairs = load_od_pairs(path)

    assert pairs[0].od_id == "OD-01"
    assert pairs[0].origin_lat == 35.0


def valid_row() -> dict[str, object]:
    return {
        "od_id": "OD-01",
        "origin_label": "地点01-A",
        "origin_lat": 35.0,
        "origin_lon": 139.0,
        "destination_label": "地点01-B",
        "destination_lat": 35.001,
        "destination_lon": 139.001,
        "distance_band": "short",
    }


def test_load_od_pairs_rejects_missing_column(tmp_path: Path) -> None:
    row = valid_row()
    del row["destination_lon"]
    path = tmp_path / "od_pairs.csv"
    pd.DataFrame([row]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="必須列"):
        load_od_pairs(path)


def test_load_od_pairs_rejects_duplicate_id(tmp_path: Path) -> None:
    path = tmp_path / "od_pairs.csv"
    pd.DataFrame([valid_row(), valid_row()]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="重複"):
        load_od_pairs(path)


def test_load_od_pairs_rejects_out_of_range_latitude(tmp_path: Path) -> None:
    row = valid_row()
    row["origin_lat"] = 91
    path = tmp_path / "od_pairs.csv"
    pd.DataFrame([row]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="緯度"):
        load_od_pairs(path)
```

Add matching tests for an empty file, a non-numeric coordinate, an out-of-range longitude, a blank ID, and an unknown distance band.

- [ ] **Step 2: Run the OD tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_evaluation.py -k load_od_pairs -v
```

Expected: import fails because`backend.app.evaluation` does not exist.

- [ ] **Step 3: Implement ODPair and strict CSV loading**

Use these fields and validations:

```python
@dataclass(frozen=True)
class ODPair:
    od_id: str
    origin_label: str
    origin_lat: float
    origin_lon: float
    destination_label: str
    destination_lat: float
    destination_lon: float
    distance_band: str
```

`load_od_pairs` must require exactly the eight named columns, reject an empty file, reject blank or duplicate IDs, coerce four coordinate columns with`pd.to_numeric(errors="raise")`, enforce latitude`[-90, 90]`, longitude`[-180, 180]`, and restrict`distance_band` to`short`,`medium`,`long`.

- [ ] **Step 4: Write failing route signature tests**

```python
def test_route_signature_uses_order_and_parallel_edge_key() -> None:
    first = route_signature([(1, 2, 0), (2, 3, 0)])
    same = route_signature([(1, 2, 0), (2, 3, 0)])
    other_key = route_signature([(1, 2, 1), (2, 3, 0)])
    reversed_order = route_signature([(2, 3, 0), (1, 2, 0)])

    assert first == same
    assert len(first) == 64
    assert first != other_key
    assert first != reversed_order
```

- [ ] **Step 5: Implement stable SHA-256 route signatures**

Normalize each tuple member with`str`, encode compact JSON as UTF-8, and return`hashlib.sha256(payload).hexdigest()`.

- [ ] **Step 6: Write failing normal-evaluation tests**

Define this small graph once in`backend/tests/test_evaluation.py`and use it for two OD pairs:

```python
def build_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=139.000, y=35.000)
    graph.add_node(2, x=139.001, y=35.000)
    graph.add_node(3, x=139.001, y=35.001)
    graph.add_node(4, x=139.002, y=35.000)
    for start, end in ((1, 2), (2, 4)):
        graph.add_edge(start, end, key=0, length=100.0, highway="primary")
    for start, end in ((1, 3), (3, 4)):
        graph.add_edge(
            start,
            end,
            key=0,
            length=130.0,
            highway="residential",
            bicycle="yes",
            cycleway="lane",
            maxspeed="30",
            width="4",
            surface="asphalt",
        )
    return graph
```

Assert:

```python
result = evaluate_profiles(graph, pairs)

assert len(result) == 10
assert set(result["profile_id"]) == set(ROUTE_PROFILE_IDS)
shortest = result.query("od_id == 'OD-01' and profile_id == 'shortest'").iloc[0]
assert shortest["distance_increase_pct"] == 0.0
assert bool(shortest["same_as_shortest"]) is True
assert result.groupby("od_id")["unique_route_count"].nunique().eq(1).all()
assert result["same_route_profile_pct"].between(0, 100).all()
```

Add a disconnected OD and assert that it still contributes five rows with`available=False` while the reachable OD remains present.

- [ ] **Step 7: Implement evaluate_profiles without aborting the batch**

For each OD:

1. Snap both coordinates with`find_nearest_node`.
2. Call`build_route_result` separately for every`ROUTE_PROFILE_IDS` entry.
3. Preserve an unavailable row on`NetworkXNoPath`.
4. Calculate the shortest-distance baseline.
5. Count route signatures among available profiles.
6. Populate same-route count, same-route percentage, unique route count, and shortest equality.

Return a DataFrame in a fixed column order defined by`ROUTE_COMPARISON_COLUMNS`.

- [ ] **Step 8: Run Task 2 tests and all existing backend tests**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_evaluation.py -v
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit Task 2**

```powershell
git add backend/app/evaluation.py backend/tests/test_evaluation.py
git commit -m "feat: evaluate route profiles across od pairs"
```

---

### Task 3: 9通りの感度分析と集計

**Files:**
- Modify: `backend/app/evaluation.py`
- Modify: `backend/tests/test_evaluation.py`

**Interfaces:**
- Produces: `SENSITIVITY_LEVELS = {"weak": 0.5, "medium": 1.0, "strong": 2.0}`
- Produces: `evaluate_sensitivity(graph, od_pairs) -> pd.DataFrame`
- Produces: `summarize_sensitivity(results: pd.DataFrame) -> pd.DataFrame`

- [ ] **Step 1: Write failing 9-combination tests**

```python
def build_pair() -> ODPair:
    return ODPair(
        od_id="OD-01",
        origin_label="地点01-A",
        origin_lat=35.0,
        origin_lon=139.0,
        destination_label="地点01-B",
        destination_lat=35.0,
        destination_lon=139.002,
        distance_band="short",
    )


def test_evaluate_sensitivity_returns_every_weight_combination() -> None:
    result = evaluate_sensitivity(build_graph(), [build_pair()])

    assert len(result) == 45
    combinations = result[["safety_level", "unknown_level"]].drop_duplicates()
    assert len(combinations) == 9
    assert set(combinations["safety_level"]) == {"weak", "medium", "strong"}
    assert set(combinations["unknown_level"]) == {"weak", "medium", "strong"}


def test_medium_medium_matches_standard_route_signatures() -> None:
    standard = evaluate_profiles(build_graph(), [build_pair()])
    sensitivity = evaluate_sensitivity(build_graph(), [build_pair()])
    medium = sensitivity.query(
        "safety_level == 'medium' and unknown_level == 'medium'"
    )

    assert medium["route_signature"].tolist() == standard["route_signature"].tolist()
    assert medium["same_as_standard"].all()
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_evaluation.py -k sensitivity -v
```

Expected: functions and constants are missing.

- [ ] **Step 3: Implement the Cartesian product of weight levels**

Use`itertools.product(SENSITIVITY_LEVELS.items(), repeat=2)`. For each combination, call`scale_profile_weights`, then`evaluate_profiles`. Add level and multiplier columns. Build the standard signature and distance lookup from the`medium`×`medium` rows, then add:

```python
same_as_standard: bool | pd.NA
distance_change_from_standard_pct: float | pd.NA
```

Unavailable rows retain blank comparison values.

- [ ] **Step 4: Write failing summary tests**

```python
def test_summarize_sensitivity_returns_one_row_per_scenario_and_profile() -> None:
    results = evaluate_sensitivity(build_graph(), [build_pair()])
    summary = summarize_sensitivity(results)

    assert len(summary) == 45
    assert summary["evaluated_od_count"].eq(1).all()
    assert summary["available_od_count"].eq(1).all()
    medium = summary.query(
        "safety_level == 'medium' and unknown_level == 'medium'"
    )
    assert medium["route_changed_from_standard_pct"].eq(0.0).all()
```

- [ ] **Step 5: Implement fixed summary columns**

Group by level, multiplier, profile ID, and profile label. Aggregate evaluated OD count, available OD count, six mean research metrics, and the percentage where`same_as_standard == False`. Round percentage and mean outputs to two decimals.

- [ ] **Step 6: Run evaluation tests and commit Task 3**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_evaluation.py -v
git add backend/app/evaluation.py backend/tests/test_evaluation.py
git commit -m "feat: add profile weight sensitivity analysis"
```

---

### Task 4: 再現可能な20 ODペア生成

**Files:**
- Create: `backend/scripts/generate_od_pairs.py`
- Create: `backend/tests/test_generate_od_pairs.py`
- Create: `data/input/od_pairs.csv`
- Modify: `.env.example`

**Interfaces:**
- Produces: `select_od_pairs(graph: nx.MultiDiGraph, *, seed: int = 20260914) -> list[ODPair]`
- Produces: `write_od_pairs(od_pairs: Sequence[ODPair], path: Path) -> None`
- CLI: `.venv\Scripts\python.exe -m backend.scripts.generate_od_pairs`

- [ ] **Step 1: Write failing deterministic-selection tests**

Build a bidirectional 7×7 synthetic grid with node coordinates spaced by exactly0.01 degrees. Test:

```python
def test_select_od_pairs_is_deterministic_and_balanced() -> None:
    graph = build_grid_graph()

    first = select_od_pairs(graph, seed=20260914)
    second = select_od_pairs(graph, seed=20260914)

    assert first == second
    assert len(first) == 20
    assert Counter(pair.distance_band for pair in first) == {
        "short": 5,
        "medium": 10,
        "long": 5,
    }
    assert len({pair.od_id for pair in first}) == 20
```

Also assert every selected snapped node pair is distinct and reachable.

- [ ] **Step 2: Run the test and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_generate_od_pairs.py -v
```

Expected: module does not exist.

- [ ] **Step 3: Implement deterministic OD selection**

Use the largest strongly connected component, choose at most400 candidate nodes with a seeded random sample, enumerate unique pairs, calculate haversine distance, and classify with these inclusive lower/exclusive upper limits:

```python
DISTANCE_BANDS = {
    "short": (300.0, 1_000.0, 5),
    "medium": (1_000.0, 2_500.0, 10),
    "long": (2_500.0, 6_000.0, 5),
}
```

Shuffle candidates with`random.Random(seed)`, reject repeated directed node pairs, and rotate through eight bearing buckets so one direction does not dominate. Assign IDs`OD-01` through`OD-20` and labels`地点01-A`/`地点01-B`.

Raise`ValueError("20組のODペアを選定できません")`if any band is undersupplied.

- [ ] **Step 4: Implement UTF-8 BOM CSV writing and CLI**

Default paths:

```python
PROJECT_ROOT / "data" / "raw" / "sample_bike.graphml"
PROJECT_ROOT / "data" / "input" / "od_pairs.csv"
```

Write columns in the order defined by the design. The CLI prints the total and band counts and returns0.

- [ ] **Step 5: Change the sample area default to 3,000 m**

Update only this line in`.env.example`:

```dotenv
OSM_DISTANCE_METERS=3000
```

- [ ] **Step 6: Run generator tests and commit the source**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_generate_od_pairs.py -v
git add backend/scripts/generate_od_pairs.py backend/tests/test_generate_od_pairs.py .env.example
git commit -m "feat: generate balanced od pair samples"
```

- [ ] **Step 7: Fetch the 3 km graph and generate the tracked input CSV**

Update the ignored`.env` to`OSM_DISTANCE_METERS=3000`, then run:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.fetch_osm_sample
.\.venv\Scripts\python.exe -m backend.scripts.generate_od_pairs
```

Verify:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from backend.app.evaluation import load_od_pairs; pairs=load_od_pairs(Path('data/input/od_pairs.csv')); assert len(pairs)==20; print({b: sum(p.distance_band==b for p in pairs) for b in ['short','medium','long']})"
```

Expected:`{'short': 5, 'medium': 10, 'long': 5}`.

- [ ] **Step 8: Commit the generated OD input**

```powershell
git add data/input/od_pairs.csv
git commit -m "data: add phase 5 od evaluation pairs"
```

---

### Task 5: 評価CLIとCSV出力

**Files:**
- Create: `backend/scripts/evaluate_profiles.py`
- Create: `backend/tests/test_evaluate_profiles.py`

**Interfaces:**
- Produces: `run_evaluation(*, graph_path: Path, od_path: Path, comparison_path: Path, sensitivity_path: Path, summary_path: Path) -> dict[str, int]`
- CLI: `.venv\Scripts\python.exe -m backend.scripts.evaluate_profiles`

- [ ] **Step 1: Write a failing end-to-end CLI function test**

Create a temporary GraphML from a small strongly connected test graph, a one-row valid OD CSV, and three output paths. Assert:

```python
counts = run_evaluation(
    graph_path=graph_path,
    od_path=od_path,
    comparison_path=comparison_path,
    sensitivity_path=sensitivity_path,
    summary_path=summary_path,
)

assert counts == {"comparison_rows": 5, "sensitivity_rows": 45, "summary_rows": 45}
assert pd.read_csv(comparison_path, encoding="utf-8-sig").shape[0] == 5
assert pd.read_csv(sensitivity_path, encoding="utf-8-sig").shape[0] == 45
assert pd.read_csv(summary_path, encoding="utf-8-sig").shape[0] == 45
```

- [ ] **Step 2: Run test and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_evaluate_profiles.py -v
```

Expected: module does not exist.

- [ ] **Step 3: Implement run_evaluation and argparse defaults**

`run_evaluation` must load GraphML and OD pairs, call the three evaluation functions, create parent directories, and write all files with:

```python
frame.to_csv(path, index=False, encoding="utf-8-sig")
```

Add argparse options`--graph`,`--od-pairs`,`--comparison-output`,`--sensitivity-output`,`--summary-output`with the design defaults. Catch`FileNotFoundError`and`ValueError`in`main`, print`f"評価を開始できません: {exc}"`to stderr, and return1.

- [ ] **Step 4: Run CLI tests and all backend tests**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_evaluate_profiles.py -v
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

- [ ] **Step 5: Run the actual 20-pair evaluation**

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.evaluate_profiles
```

Verify exact row counts and that all available numeric percentages are within expected ranges. Print the number of unavailable rows and do not treat them as missing output.

- [ ] **Step 6: Commit Task 5**

```powershell
git add backend/scripts/evaluate_profiles.py backend/tests/test_evaluate_profiles.py
git commit -m "feat: export batch route evaluation results"
```

---

### Task 6: プレゼンテーション向けWeb UI

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Modify: `frontend/app.js`
- Modify: `backend/tests/test_static_app.py`

**Interfaces:**
- Preserves IDs consumed by JavaScript: `map`, `api-status`, `data-status`, `route-status`, `reset-route`, `profile-legend`, `route-comparison`, `route-comparison-body`, `route-summary`, and all`metric-*`elements
- Adds table column: signal count

- [ ] **Step 1: Strengthen the static-page test and verify RED**

Add assertions:

```python
assert "自転車経路比較" in response.text
assert "距離・ルール・安全性・OSMデータ充足度" in response.text
assert "研究用・暫定評価" in response.text
assert "テストページ" not in response.text
assert "Phase 4の比較機能です" not in response.text
assert '<th scope="col">信号</th>' in response.text
assert 'class="workspace"' in response.text
```

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_static_app.py -v
```

Expected: assertions fail against the old layout.

- [ ] **Step 2: Rebuild the semantic layout while preserving IDs**

Structure`frontend/index.html`with this complete top-level layout, then move the existing legend, metric definitions, and comparison table into the indicated elements without changing their IDs:

```html
<header class="site-header">
  <div>
    <p class="eyebrow">ROUTE PROFILE STUDY</p>
    <h1>自転車経路比較</h1>
    <p class="subtitle">距離・ルール・安全性・OSMデータ充足度</p>
  </div>
  <section class="status-panel" aria-label="システム状態">
    <p><span class="status-dot" aria-hidden="true"></span>API <strong id="api-status">確認中</strong></p>
    <p><span class="status-dot" aria-hidden="true"></span>道路 <strong id="data-status">確認中</strong></p>
  </section>
</header>
<main>
  <section class="workspace">
    <div class="map-card">
      <div class="section-label">ROUTE MAP</div>
      <div id="map" aria-label="OpenStreetMap道路地図"></div>
    </div>
    <aside class="route-panel" aria-label="地点選択と経路指標">
      <div class="route-heading">
        <div><h2>地点を選択</h2><p id="route-status">地図上で出発地点を選択</p></div>
        <button id="reset-route" type="button">リセット</button>
      </div>
      <div id="profile-legend" class="profile-legend" aria-label="ルート凡例"></div>
      <dl id="route-summary" class="route-summary" hidden></dl>
    </aside>
  </section>
  <section id="route-comparison" class="comparison-card" hidden>
    <div class="comparison-heading"><h2>プロファイル比較</h2><p>選択した行を地図で強調</p></div>
    <div class="comparison-wrap"><table><thead></thead><tbody id="route-comparison-body"></tbody></table></div>
  </section>
  <footer>研究用・暫定評価</footer>
</main>
```

Keep short operational text only. Remove the old paragraph with`research-note`.

- [ ] **Step 3: Apply the visual system in CSS**

Use CSS custom properties for navy text, off-white background, white cards, muted borders, and existing route colors. Implement:

- maximum width1,440 px
- two-column workspace`minmax(0, 1.75fr) minmax(320px, 0.75fr)`
- card border radius16 px and subtle shadow
- map height620 px on desktop
- compact status pills
- two-column metric tiles in the side panel
- full-width comparison table below the workspace
- one-column layout below900 px
- reduced map height below600 px

Do not add gradients, decorative generated imagery, animations, or external UI libraries.

- [ ] **Step 4: Add signal values to comparison rows**

In`addComparisonRow`, insert:

```javascript
`${result.summary.traffic_signal_count}か所`,
```

at the same column position as the new signal header, including a`"-"`cell value for unavailable routes.

- [ ] **Step 5: Run static and full backend tests**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_static_app.py -v
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

- [ ] **Step 6: Run FastAPI and verify the browser**

Start the server, open`http://127.0.0.1:8000/`, select two map points, and verify:

- desktop two-column layout
- mobile one-column layout
- API/data status pills
- five route layers and legend entries
- seven comparison columns including signal count
- selected route row and map layer stay synchronized
- browser console has no JavaScript errors

- [ ] **Step 7: Commit Task 6**

```powershell
git add frontend/index.html frontend/styles.css frontend/app.js backend/tests/test_static_app.py
git commit -m "feat: polish route comparison presentation ui"
```

---

### Task 7: 簡易起動ファイルとREADME

**Files:**
- Create: `start_app.cmd`
- Create: `run_evaluation.cmd`
- Modify: `README.md`
- Create: `backend/tests/test_launchers.py`

**Interfaces:**
- `start_app.cmd`: starts`backend.app.main:app`on`127.0.0.1:8000`
- `run_evaluation.cmd`: runs`backend.scripts.evaluate_profiles`

- [ ] **Step 1: Write failing launcher-content tests**

```python
def test_start_app_uses_project_relative_virtualenv() -> None:
    content = (PROJECT_ROOT / "start_app.cmd").read_text(encoding="utf-8")
    assert "%~dp0" in content
    assert ".venv\\Scripts\\python.exe" in content
    assert "backend.app.main:app" in content


def test_run_evaluation_uses_project_relative_virtualenv() -> None:
    content = (PROJECT_ROOT / "run_evaluation.cmd").read_text(encoding="utf-8")
    assert "%~dp0" in content
    assert ".venv\\Scripts\\python.exe" in content
    assert "backend.scripts.evaluate_profiles" in content
```

Run and verify missing-file failures.

- [ ] **Step 2: Create start_app.cmd**

Use`@echo off`,`cd /d "%~dp0"`, and explicit checks for the virtualenv Python and GraphML. Start a hidden two-second browser-opening helper, then keep Uvicorn in the visible console so Ctrl+C stops it:

```cmd
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000/'"
".venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Display one short Japanese line before startup. End with`exit /b 1`on missing prerequisites.

- [ ] **Step 3: Create run_evaluation.cmd**

Use the same root and prerequisite checks, then run:

```cmd
".venv\Scripts\python.exe" -m backend.scripts.evaluate_profiles
```

Propagate the command exit code. On success display the three output paths.

- [ ] **Step 4: Update README quick-start and Phase 5 sections**

At the top of setup instructions, add the two double-click options. Replace the old E-drive-specific`Set-Location`example with`Set-Location 'C:\path\to\bicycle-rule-routing'`. Document the three Phase5 output files, 3km default, OD generator command, evaluation command, row counts, sensitivity factors, and the renamed profile.

- [ ] **Step 5: Run launcher and static tests**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_launchers.py backend\tests\test_static_app.py -v
```

- [ ] **Step 6: Commit Task 7**

```powershell
git add start_app.cmd run_evaluation.cmd README.md backend/tests/test_launchers.py
git commit -m "docs: add one-click research workflows"
```

---

### Task 8: End-to-end verification and research record

**Files:**
- Modify: `docs/work-log.md`

**Interfaces:**
- Consumes all Phase 5 artifacts
- Produces reproducible verification evidence in the work log

- [ ] **Step 1: Run dependency and full test checks**

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest backend\tests -v
```

Expected: no broken requirements and all tests pass.

- [ ] **Step 2: Regenerate the 3 km graph, OD input, and outputs**

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.fetch_osm_sample
.\.venv\Scripts\python.exe -m backend.scripts.generate_od_pairs
.\.venv\Scripts\python.exe -m backend.scripts.evaluate_profiles
```

- [ ] **Step 3: Audit exact output shapes and ranges**

Run a verification command that asserts:

```python
len(load_od_pairs(Path("data/input/od_pairs.csv"))) == 20
len(pd.read_csv("data/processed/route_comparison.csv")) == 100
len(pd.read_csv("data/processed/sensitivity_analysis.csv")) == 900
len(pd.read_csv("data/processed/sensitivity_summary.csv")) == 45
```

Also assert all non-null distance increases are at least0, all percentage metrics are within0–100, every sensitivity level has the documented multiplier, and medium×medium signatures equal the standard output.

- [ ] **Step 4: Verify HTTP and browser boundaries**

Start`start_app.cmd`, confirm`GET /api/health`,`GET /`, and`GET /data/sample_edges.geojson`return200, then repeat the desktop and mobile browser checklist from Task6.

- [ ] **Step 5: Record measured results**

Append a dated Phase5 entry to`docs/work-log.md`containing:

- graph node/edge counts and generation time
- OD band counts and unavailable OD count
- output row counts
- per-profile mean distance increase, major-road rate, cycleway rate, signals, and unknown rate
- scenario/profile route-change percentages
- test count and browser observations
- the statement that weights remain provisional

- [ ] **Step 6: Run whitespace and Git-status checks**

```powershell
git diff --check
git status --short
```

Expected: only the intended work-log change is unstaged; ignored GraphML and generated result CSVs do not appear.

- [ ] **Step 7: Commit the research record**

```powershell
git add docs/work-log.md
git commit -m "docs: record phase 5 batch evaluation"
```

- [ ] **Step 8: Run final verification on committed HEAD**

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
git status --short --branch
```

Expected: all tests pass and the working tree is clean.
