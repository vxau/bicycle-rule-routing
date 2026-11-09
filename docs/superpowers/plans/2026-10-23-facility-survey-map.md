# Facility Survey Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全道路の設備情報を3分類で可視化し、現地確認用の調査CSVを保存できるようにする。

**Architecture:** 既存の設備判定を公開ヘルパーとして共有し、GraphMLから分類GeoJSONを返すAPIを追加する。Leafletの調査レイヤー、選択とCSV処理は新しいJSファイルへ分離する。

**Tech Stack:** Python / FastAPI / NetworkX / pytest、既存Leaflet、素のJavaScript。追加の実行依存なし。

**Spec:** `docs/superpowers/specs/2026-10-23-facility-survey-map-design.md`

## Global Constraints

- 分離済みのクラウドチェックアウトを使い、worktreeを追加しない。
- 元のGraphMLとOD CSVを変更しない。調査情報を設備なし判定や配置入力へ自動反映しない。
- 方向間不一致は不明。集計は端点とエッジキーでまとめた区間単位とする。
- UIは日本語、色と文字・線種を併用。CSVはBOM付きで数式文字列を無害化する。

## Review Focus

- 左右別タグ・方向間不一致・未知の値を現地確認済みと誤読しないこと。
- データ更新時に保存された選択が別区間へ紐づかないこと。
- 外部由来の名前・タグでHTMLやCSV数式が実行されないこと。
- 調査操作が経路の始終点選択や既存レイヤーの可視性を壊さないこと。
- データ欠損・空グラフ・保存不可でも調査機能が明確な状態を表示すること。

### Task 1: 分類API

**Files:** `backend/app/facility_placement.py`, new `backend/app/facility_inventory.py`, `backend/app/main.py`, new `backend/tests/test_facility_inventory.py`.

**Interfaces:** 公開 `facility_state(data)` / `segment_key(u,v,key)` を既存配置と共有。`build_facility_inventory(graph)` は `{type, features, summary, dataset_id}` を返す。`GET /api/facilities` はGraphML依存を利用する。

- [x] 分類・往復集約・方向不一致・長さ集計・空グラフ・不変性・データ識別・503のテストを書く。
- [x] 未実装による失敗を確認する。
- [x] 共通判定と分類APIを実装し、API・既存配置テストを通す。

### Task 2: 調査UIとCSV

**Files:** new `frontend/facility-survey.js`, `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`, new `frontend/tests/facility-survey.test.cjs`.

**Interfaces:** `FacilitySurvey.create({map, onStatus})` が `setActive(boolean)` を返す。分類・保存・CSVの純粋関数はNode組込みテストで直接確認する。APIのfeaturesに `segment_id, facility_state, length_m, directions` を含める。

- [x] 選択のデータ識別・CSVの引用符/BOM/数式保護・空値の振る舞いをテストし、失敗確認後に実装する。
- [x] モード切替、3分類フィルタ、集計、区間詳細、調査選択一覧、CSV保存を実装する。
- [x] 実際のLeafletとブラウザを使ってフィルタ、選択/解除/復元、モード切替、CSV出力を確認する。

### Task 3: ドキュメントと回帰確認

**Files:** `README.md`, `docs/research/facility-placement.md`, `docs/work-log.md`.

- [x] 調査手順、分類の限界、CSVの使い方を記載する。
- [x] 全pytest、Nodeテスト、JavaScript構文、git diffチェックを実行する。
- [x] 新しいコンテキストのレビューを実施し、重要な指摘をテストとともに修正する。
- [x] 変更を確認可能な状態で残し、実データ検証の可否を区別して報告する。

検証結果: Python 70成功・既存の道路データ欠損起因1失敗、Node 3成功、架空道路での実ブラウザ検証成功。実データ規模での動作・表示確認はデータ取得後に実施する。
