# 自転車ルール遵守支援システム（初期研究基盤）

交通制度変更を背景に、OpenStreetMap（OSM）の道路属性を用いて、自転車利用者が交通ルールを守りやすい経路を比較できるWebアプリを研究・開発するための初期基盤です。

現段階はロードマップのPhase 3.2です。比較基準となる距離最短経路と、その経路を分析する土台までを実装しています。

- OSMから小範囲の自転車道路ネットワークを取得
- GraphML、GeoJSON、CSV、JSONとして保存
- 道路数、道路延長、信号等の基礎集計
- 自転車関連タグの記録率・不明率の集計
- FastAPIのヘルスチェックAPI
- HTML/CSS/JavaScriptとLeafletによる道路地図
- API接続状態と取得道路数の表示
- 地図上の2点を結ぶ距離最短経路
- 経路上の幹線道路率、自転車レーン率、信号数、属性不明率
- Phase 4に向けた道路コスト要素の試算（ルート選定には未使用）
- 自動テストと再現可能な確認コマンド

本システムは研究用の注意喚起支援であり、交通違反を法的に判定するものではありません。

## 技術構成

学生が各部分を説明しやすいよう、初期段階では構成を小さくしています。

| 役割 | 使用技術 |
|---|---|
| API・静的ファイル配信 | Python 3.10、FastAPI、Uvicorn |
| OSM取得・道路グラフ | OSMnx、NetworkX |
| 地理データ処理 | GeoPandas、Shapely |
| 画面 | HTML、CSS、JavaScript |
| 地図 | Leaflet、OpenStreetMapタイル |
| テスト | pytest、FastAPI TestClient |

React、TypeScript、Vite、npm、Docker、データベース、認証、UIライブラリは使用していません。

## システムの流れ

```text
OpenStreetMap / Overpass API
        ↓
OSMnxで network_type="bike" の道路グラフを取得
        ↓
GraphML保存・GeoDataFrame変換
        ↓
GeoJSON出力・タグ欠損率集計
        ↓
FastAPIがAPIと静的画面を配信
        ↓
Leafletが道路GeoJSONを地図上に描画
        ↓
地図で2点選択 → 最寄りノード → NetworkX距離最短経路
        ↓
経路GeoJSON・距離・道路属性指標を表示
```

## ディレクトリ構成

```text
bicycle-rule-routing/
├─ backend/
│  ├─ app/
│  │  ├─ main.py               # FastAPIと静的ファイル配信
│  │  ├─ osm_analysis.py       # OSMタグの分類・集計
│  │  └─ routing.py            # 最短経路・経路指標・仮コスト
│  ├─ scripts/
│  │  └─ fetch_osm_sample.py   # OSM取得・保存・集計
│  ├─ tests/                   # 自動テスト
│  └─ requirements.txt
├─ frontend/
│  ├─ index.html
│  ├─ styles.css
│  └─ app.js
├─ data/
│  ├─ raw/                     # GraphML
│  ├─ exports/                 # GeoJSON
│  └─ processed/               # 集計CSV・JSON
├─ docs/
│  ├─ environment-report.md
│  ├─ rule-tag-mapping.md       # 交通ルールとOSMタグ対応表
│  └─ work-log.md
├─ .cache/                     # pip・OSMnxキャッシュ（Git対象外）
├─ .venv/                      # Python仮想環境（Git対象外）
├─ .env.example
└─ README.md
```

## セットアップ

PowerShellでプロジェクトへ移動します。

```powershell
Set-Location E:\graduation-research\bicycle-rule-routing
```

既に作成済みの仮想環境を使う場合、activateは不要です。常に仮想環境のPythonを直接指定できます。

```powershell
.\.venv\Scripts\python.exe --version
```

環境を作り直す場合は、pipキャッシュをEドライブ内へ向けてから依存関係を入れます。

```powershell
python -m venv .venv
$env:PIP_CACHE_DIR = 'E:\graduation-research\bicycle-rule-routing\.cache\pip'
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

システム全体のPATHやPowerShell実行ポリシーは変更しません。

## 対象地域の設定

設定例をコピーします。

```powershell
Copy-Item .env.example .env
```

`.env`の緯度・経度・取得半径・表示名を対象地域へ変更します。

```dotenv
OSM_CENTER_LAT=35.681236
OSM_CENTER_LON=139.767125
OSM_DISTANCE_METERS=500
OSM_PLACE_LABEL=Tokyo Station
```

取得半径は100〜5000 mに制限しています。最初は500〜1000 m程度を推奨します。

## OSM道路データの取得

プロジェクト直下で次を実行します。

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.fetch_osm_sample
```

スクリプトは`network_type="bike"`で自転車が利用できるとOSMnxが判断した道路を取得し、次を出力します。

| 出力 | 内容 |
|---|---|
| `data/raw/sample_bike.graphml` | 道路グラフ本体 |
| `data/exports/sample_nodes.geojson` | 交差点・道路ノード |
| `data/exports/sample_edges.geojson` | 地図表示用道路区間 |
| `data/processed/tag_coverage.csv` | 道路延長で重み付けしたタグ集計 |
| `data/processed/summary.json` | ノード数・エッジ数・道路延長等 |

OSMnxの通信キャッシュは`.cache/osmnx`へ保存します。同じ条件で再実行した場合はキャッシュを利用します。

## Webアプリの起動

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

ブラウザで`http://127.0.0.1:8000/`を開きます。

- APIが正常なら「API: 接続済み」
- GeoJSONがある場合は「道路データ: ○○区間を表示」
- 道路GeoJSONを緑色で地図上に表示
- 地図を2回クリックすると、出発地点と目的地点の距離最短経路を青色で表示
- 最短経路の距離、道路区間数、属性指標、仮コストを表示

ヘルスチェックAPIは`http://127.0.0.1:8000/api/health`です。

最短経路APIは次の形式です。

```text
GET /api/routes/shortest
    ?start_lat=35.6812
    &start_lon=139.7671
    &end_lat=35.6900
    &end_lon=139.7800
```

GraphMLは初回の経路要求時に読み込み、同じサーバープロセス内では再利用します。

## テスト

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -v
.\.venv\Scripts\python.exe -m pip check
```

## 現時点の取得結果

東京駅周辺・半径3,000 mの現在の研究用データは次のとおりです。

| 指標 | 結果 |
|---|---:|
| ノード数 | 12,989 |
| 有向エッジ数 | 28,300 |
| 有向エッジ総延長 | 1,374.765 km |
| 重複方向をまとめた街路総延長 | 983.589 km |
| 信号ノード | 1,037 |
| 一時停止ノード | 1 |
| crossing情報を持つノード | 109 |

代表的な道路タグの記録率は次のとおりです。割合は道路区間数ではなく道路延長で重み付けしています。

| タグ | 記録率 | 不明率 |
|---|---:|---:|
| `cycleway` | 3.28% | 96.72% |
| `cycleway:left` | 7.15% | 92.85% |
| `maxspeed` | 22.92% | 77.08% |
| `lanes` | 33.28% | 66.72% |
| `width` | 1.33% | 98.67% |
| `surface` | 63.03% | 36.97% |
| `access` | 4.99% | 95.01% |

この結果から、OSMは道路ネットワークの取得には利用できる一方、幅員や自転車関連属性は地域によって欠損が多く、欠損を無視したルート評価は危険だと説明できます。

## タグの扱い

取得・分析対象は次のとおりです。

- 方向・通行規制: `oneway`、`oneway:bicycle`、`bicycle`、`access`
- 自転車設備: `cycleway`、`cycleway:left`、`cycleway:right`、`cycleway:both`
- 道路特性: `highway`、`maxspeed`、`lanes`、`width`、`surface`
- 注意地点: `highway=traffic_signals`、`highway=stop`、`crossing`

各タグを次の3状態に分類します。

| 状態 | 意味 | 例 |
|---|---|---|
| `present` | 属性値が記録されている | `cycleway=lane` |
| `explicit_absent` | 「ない」と明記されている | `cycleway=no` |
| `unknown` | タグがなく、実際にないか未調査か判断できない | タグ欠損 |

「タグがない」ことを「設備がない」と断定しない点が、今後のルート評価で重要です。

## 最初の段階で報告できる内容

初期報告では、次の順序で説明できます。

1. 背景  
   自転車への交通反則通告制度適用を背景に、最短距離だけでなくルール遵守を支援する必要がある。
2. 研究目的  
   OSM道路属性を使い、ルール上の注意点・安全性・情報不足を説明できるルート比較システムを開発する。
3. 開発方針  
   FastAPI、HTML/CSS/JavaScript、Leafletによる小さなWeb構成とし、経路評価部分を段階的に追加する。
4. OSM取得手順  
   指定座標の周辺を`network_type="bike"`で取得し、道路グラフと属性をGraphML・GeoJSONへ保存する。
5. 初期成果  
   280ノード・474エッジを取得し、Web地図へ474道路区間を描画できた。
6. 初期分析  
   `cycleway`、`width`、`maxspeed`等の記録率を算出し、OSM属性欠損を定量的に確認した。
7. 課題  
   法令とOSMタグの対応検証、対象地域の決定、経路評価式、欠損時の扱い、現地確認が未実施である。

初期報告のデモでは、OSM取得コマンド、生成ファイル、タグ集計CSV、API接続状態、道路地図を見せられます。

## OSMデータ上の注意

- OSMは共同編集データであり、現地の標識・規制・道路状況と一致する保証はありません。
- `network_type="bike"`はOSMnxの既定アクセス規則も使って道路を抽出します。`bicycle`タグがないことは、直ちに自転車通行不可を意味しません。
- OSMnxは一部属性を道路グラフ用に正規化します。今回の`oneway`記録率100%は、元のOSMで全道路にタグが明記されていることを意味しません。
- `oneway:bicycle`は特に一方通行道路で意味を持つため、全道路に対する単純な記録率だけで品質を判断しません。
- 信号、一時停止、横断情報はノード化・簡略化の方法にも影響されます。
- 将来の評価では、警察庁等の一次資料、OSMタグ仕様、現地標識を照合します。
- OSMデータを公開・配布する際はOpenStreetMap contributorsの表示とODbLの条件を確認します。

## トラブルシューティング

- PowerShellで仮想環境をactivateできない  
  `.\.venv\Scripts\python.exe`を直接使えば実行ポリシー変更は不要です。
- Overpass APIの取得に失敗する  
  通信状態を確認し、少し時間を置いて再実行します。取得半径を小さくする方法もあります。
- 道路データが画面に出ない  
  OSM取得スクリプトを実行し、`data/exports/sample_edges.geojson`の存在を確認します。
- 地図の背景だけ表示されない  
  Leaflet本体とOSMタイルはインターネットから読み込むため、ネット接続を確認します。
- 対象地域を変えたのに古いデータが見える  
  `.env`を確認して取得スクリプトを再実行し、ブラウザを再読み込みします。

## 次工程TODO

- 研究対象地域を大学周辺へ変更し、地域選定理由を整理する
- 交通ルールとOSMタグ対応表の暫定判断を代表地点で検証する
- 通行不可をハード制約、注意・安全性・欠損をソフトコストとして設計する
- ルール遵守優先、安全優先、情報信頼性優先、バランス型を実装する
- ルートごとの距離、注意地点、幹線道路距離、設備利用率、不明率を比較する
- 注意地点を地図上に表示し、選定理由を説明する
- `oneway`の生OSMタグとOSMnx正規化後属性を区別して分析する
- 一方通行道路に限定した`oneway:bicycle`充足率を追加する
- OSM属性の一部を現地調査または公的情報で検証する
- 複数の出発地・目的地ペアで評価実験を行う
- 制度変更前後ではなく「距離中心モデル」と「制度対応モデル」の比較として実験を設計する

## 参考ドキュメント

- `docs/environment-report.md`: PC環境とEドライブ配置方針
- `docs/rule-tag-mapping.md`: 交通ルール、OSMタグ、暫定コストの対応
- `docs/work-log.md`: 実行コマンド、確認結果、発生した問題
- `docs/superpowers/specs/2026-07-27-initial-research-platform-design.md`: 初期設計
- `docs/superpowers/plans/2026-07-27-initial-research-platform.md`: 実装計画
