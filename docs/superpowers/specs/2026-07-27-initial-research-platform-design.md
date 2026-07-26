# 自転車ルール遵守支援システム 初期研究基盤 設計書

## 1. 目的

交通反則制度の変更を背景として、OpenStreetMap（OSM）の道路属性を利用し、自転車利用者が交通ルールを守りやすいルートを比較できる研究基盤を準備する。

本段階ではルート評価モデルを完成させない。次の研究段階へ進むため、開発環境、OSMデータ取得、保存、可視化、属性充足率・欠損率の初期集計までを再現可能にする。

このシステムは交通違反を法的に判定するものではない。OSMに記録された情報を用いて注意情報を提示する研究用支援システムとする。

## 2. 設計方針

- 学生が全体を理解して説明できる小規模な構成にする。
- React、TypeScript、Vite、Docker、データベース、認証、UIライブラリを導入しない。
- FastAPIがAPIと静的なHTML/CSS/JavaScriptを同一オリジンで配信する。
- 地図表示にはLeafletを使用する。
- OSM取得とネットワーク処理にはOSMnx、NetworkX、GeoPandas、Shapelyを使用する。
- Python仮想環境、pipキャッシュ、OSMnxキャッシュ、取得データはEドライブへ置く。
- OSMの属性欠損を「設備が存在しない」と解釈せず、「情報不明」として区別する。
- OpenStreetMapの帰属表示とODbLへの案内を画面および文書に記載する。

## 3. システム構成

```text
ブラウザ
  ├─ GET /                 index.html
  ├─ GET /static/styles.css
  ├─ GET /static/app.js
  ├─ GET /data/sample_edges.geojson
  └─ GET /api/health
          ↓
       FastAPI

OSM取得スクリプト
  ↓
Overpass API
  ↓
OSMnx MultiDiGraph
  ├─ GraphML
  ├─ GeoJSON
  ├─ CSV
  └─ 属性集計JSON/CSV
```

FastAPIのWebアプリとOSM取得スクリプトは分離する。Webアプリを起動するだけではOverpass APIへ問い合わせない。これにより、外部API障害やレート制限が通常の画面起動へ影響しない。

## 4. ファイル構成

```text
bicycle-rule-routing/
├─ .cache/
│  ├─ pip/
│  └─ osmnx/
├─ .venv/
├─ backend/
│  ├─ app/
│  │  └─ main.py
│  ├─ scripts/
│  │  └─ fetch_osm_sample.py
│  ├─ tests/
│  │  ├─ test_health.py
│  │  ├─ test_static_app.py
│  │  └─ test_osm_analysis.py
│  └─ requirements.txt
├─ frontend/
│  ├─ index.html
│  ├─ styles.css
│  └─ app.js
├─ data/
│  ├─ raw/
│  ├─ processed/
│  └─ exports/
├─ docs/
│  ├─ environment-report.md
│  ├─ work-log.md
│  └─ superpowers/
├─ .env.example
├─ .gitignore
└─ README.md
```

`.venv`、`.cache`、取得済みデータはGit管理外とする。分析結果の小さなサンプルのみ、必要に応じてGit管理対象にできる。

## 5. OSM取得

初期対象は大学周辺など、中心座標から半径500〜800メートル程度とする。検証用の初期値は東京駅（緯度35.681236、経度139.767125）を中心とした半径500メートルとし、`.env` で任意の対象地域へ変更できるようにする。OSMnxの `graph_from_point` を `network_type="bike"` で実行し、自転車で利用可能と判断された道路ネットワークを取得する。

取得前にOSMnxの保持対象タグを拡張する。

### 道路タグ

- `access`
- `bicycle`
- `bridge`
- `cycleway`
- `cycleway:left`
- `cycleway:right`
- `cycleway:both`
- `highway`
- `junction`
- `lanes`
- `maxspeed`
- `name`
- `oneway`
- `oneway:bicycle`
- `service`
- `surface`
- `tunnel`
- `width`

### ノードタグ

- `highway`
- `junction`
- `crossing`
- `bicycle`
- `traffic_signals`

OSMnxのHTTPキャッシュを `E:\graduation-research\bicycle-rule-routing\.cache\osmnx` に設定し、同一条件の問い合わせを繰り返さない。

## 6. 保存と集計

取得した道路ネットワークを次の形式へ保存する。

- `data/raw/sample_bike.graphml`: OSMnxで再利用するグラフ
- `data/exports/sample_nodes.geojson`: 地図表示用ノード
- `data/exports/sample_edges.geojson`: 地図表示用道路
- `data/processed/tag_coverage.csv`: 属性充足率・欠損率
- `data/processed/summary.json`: ノード数、エッジ数、道路総延長など

属性充足率は道路レコード数だけでなく、道路延長を基準に集計する。

```text
属性充足率 = 属性が記録された道路の総延長 / 全道路の総延長
属性欠損率 = 1 - 属性充足率
```

`cycleway=no` のように「存在しないことが明示された値」と、タグ自体が存在しない「情報不明」を別の状態として集計する。

## 7. 最小Web画面

画面には次を表示する。

- 研究テーマ名
- FastAPIへの接続状態
- Leaflet地図
- `.env` で指定した初期表示地点
- 取得済み `sample_edges.geojson` の道路ネットワーク
- GeoJSONが未生成の場合の実行案内
- OpenStreetMapの帰属表示
- 「現段階では法的な違反判定を行わない」という注意書き

地図は `sample_edges.geojson` を静的に読み込んで道路を一色で描画する。初期段階ではルート比較、リスク別の色分け、注意地点のポップアップは実装しない。

## 8. エラー処理

- `/api/health` は外部サービスへ依存せず、アプリ自身の状態だけを返す。
- ブラウザからAPIへ接続できない場合は、画面に「接続できません」と表示する。
- OSM取得時は座標と距離を検証し、異常値なら問い合わせ前に終了する。
- Overpass APIのタイムアウトや通信エラーは、原因と再実行方法を表示して異常終了する。
- 出力先が書き込めない場合は対象パスを表示して異常終了する。
- 取得結果が空の場合は、空の成果物を正常結果として扱わず異常終了する。

## 9. テストと確認

実装コードはテストファーストで作成する。HTML/CSS、環境変数例、依存関係ファイルなどの宣言的な設定は、生成後に動作確認する。

自動テストでは次を確認する。

- `/api/health` が200と期待するJSONを返す。
- `/` がHTMLを返し、地図要素とAPI状態要素を含む。
- 取得済みGeoJSONを配信するパスが設定されている。
- 属性状態の分類が「明示あり」「明示なし」「情報不明」を区別する。
- 道路延長基準の充足率計算が正しい。

実環境確認では次を実行する。

- Python依存関係のインポート
- pytest
- FastAPIのローカル起動
- ブラウザで地図とAPI接続状態を確認
- 小範囲のOSM取得
- GraphML、GeoJSON、CSV、JSONの生成確認
- 取得した道路ネットワークがLeaflet地図へ表示されることの確認
- 同一条件の再実行でOSMnxキャッシュが使用されることの確認

## 10. 初期研究報告で説明できる内容

- 研究背景、目的、対象外事項
- OSMのノード、ウェイ、タグと道路グラフの関係
- OSMnxとOverpass APIによる取得手順
- 取得対象タグと交通ルール・安全評価の将来的な対応
- 対象地域の道路ネットワーク地図
- ノード数、エッジ数、道路総延長
- 自転車関連タグの充足率・欠損率
- OSM属性欠損を情報不明として扱う理由
- 次段階で作成する最短距離、ルール遵守、安全、バランス型ルートの比較計画

## 11. 初期段階の完了条件

- Eドライブ内でPython仮想環境とキャッシュが利用できる。
- Gitリポジトリ、README、環境診断、作業記録が存在する。
- FastAPIと静的画面を1つのコマンドで起動できる。
- ヘルスチェックと静的画面の自動テストが通る。
- 小範囲の自転車道路ネットワークを取得できる。
- GraphML、GeoJSON、CSV、JSONを生成できる。
- 取得した道路ネットワークをLeaflet地図で表示できる。
- 実データの属性充足率・欠損率を説明できる。
- 実行コマンド、確認結果、制約、次工程がREADMEに記録されている。
