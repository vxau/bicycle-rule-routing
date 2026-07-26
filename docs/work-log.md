# 作業記録

## 2026-07-27: 初期診断と設計

- Windows、Python、Node.js、Git、VS Codeの既存環境を診断した。
- Eドライブの空き容量と書き込み可否を確認した。
- React、Docker、データベースを使わない軽量構成を決定した。
- FastAPIがHTML/CSS/JavaScriptとAPIを配信する構成を選択した。
- OSMnx 2.0.6をPython 3.10環境で利用する方針を決定した。
- 設計書と実装計画を作成した。

## 2026-07-27: 環境構築

主な実行コマンド:

```powershell
python -m venv .venv
$env:PIP_CACHE_DIR = 'E:\graduation-research\bicycle-rule-routing\.cache\pip'
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pip check
git init
```

結果:

- `.venv`、`.cache\pip`、`.cache\osmnx`をEドライブ内に作成した。
- OSMnx 2.0.6、FastAPI 0.116.1等を固定バージョンで導入した。
- 管理者権限、システムPATH変更、PowerShell実行ポリシー変更は行っていない。
- Docker、React、Nodeパッケージは導入していない。

発生した問題と判断:

- 最初の依存関係導入は実行時間上限で表示が途切れた。プロセスとログを確認して再実行し、`pip check`とimportで導入完了を検証した。
- 最新OSMnx 2.1.1はPython 3.11以上を要求するため、既存Python 3.10を維持できる2.0.6を選んだ。
- 最新FastAPI系列ではTestClientに警告が出たため、Python 3.10で警告なく再現できる0.116.1へ固定した。

## 2026-07-27: API・画面・OSM分析

主な実行コマンド:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -v
.\.venv\Scripts\python.exe -m backend.scripts.fetch_osm_sample
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

作成内容:

- `/api/health`を返すFastAPIアプリ
- HTML/CSS/JavaScriptとLeafletによる研究用地図画面
- OSMnxによる`network_type="bike"`の取得スクリプト
- GraphML、ノードGeoJSON、道路GeoJSON、タグ集計CSV、概要JSON
- タグ値を「記録あり」「明示的になし」「不明」へ分ける集計処理
- FastAPI、静的ファイル、設定値、GeoJSON変換、タグ集計の自動テスト

東京駅周辺・半径500 mの初期結果:

- 280ノード、474有向エッジ
- 有向エッジ総延長24.447 km、街路総延長20.514 km
- 信号16、一時停止0、crossing情報2
- `cycleway`記録率9.12%、`width`記録率0.38%、`surface`記録率80.22%

## 2026-07-27: 結合確認

HTTP確認:

- `GET /api/health`: 200、`status=ok`
- `GET /`: 200
- `GET /data/sample_edges.geojson`: 200

実ブラウザ確認:

- API状態: 「接続済み」
- 道路データ状態: 「474区間を表示」
- Leaflet初期化: 成功
- OSM背景タイル: 15枚を確認
- GeoJSON道路パス: 474本を確認
- ブラウザの警告・エラー: 0件

OSM取得は初回にOverpass APIへ接続して成功し、同一条件の再取得はEドライブ内のOSMnxキャッシュを利用して約4秒で完了した。

最終再検証:

- `pip check`: 依存関係の破損なし
- pytest: 18件すべて成功
- OSM再取得: キャッシュから成功
- GraphML読み戻し: 280ノード、474エッジ
- GeoJSON読み戻し: 280ノード、474道路区間
- タグ集計CSV: 必須8列・13タグを確認
- HTTP: ヘルスAPI、トップ画面、道路GeoJSONがすべて200
- `git diff --check`: 空白エラーなし

## 作成ファイルの要点

- `backend/app/main.py`: APIと画面・データ配信
- `backend/app/osm_analysis.py`: 属性状態分類と道路延長ベースの集計
- `backend/scripts/fetch_osm_sample.py`: OSM取得・保存・初期統計
- `backend/tests/`: 自動テスト
- `frontend/`: HTML/CSS/JavaScriptとLeaflet画面
- `data/`: 取得・生成データ（Git管理対象外）
- `README.md`: 再現手順、初期報告内容、制約、次工程

## 現時点の残課題

- 大学周辺の緯度・経度へ変更する。
- 法令とOSMタグの対応を一次資料で検証する。
- 最短距離、ルール遵守、安全性、情報信頼性の各ルートを実装する。
- OSMnx正規化後ではなく生OSMタグの欠損も分析する。
- 注意地点とルート選定理由を画面へ追加する。
- 現地確認と複数ODペアによる評価実験を行う。
