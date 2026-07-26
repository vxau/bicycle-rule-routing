# 環境診断レポート

診断日: 2026-07-27

## OSと保存先

- OS: Microsoft Windows 11 Pro 64ビット（10.0.22631）
- プロジェクト: `E:\graduation-research\bicycle-rule-routing`
- Eドライブ: NTFS、総容量238.46 GiB、診断時空き容量46.12 GiB
- Eドライブ書き込みテスト: 成功

## 既存ツール

| ツール | 診断結果 |
|---|---|
| Python | 3.10.11 |
| pip | 25.3 |
| Node.js | 22.16.0 |
| npm | 10.9.2（`npm.cmd`で動作） |
| Git | 2.41.0.windows.1 |
| VS Code | 1.108.0 x64 |
| winget | 1.29.280 |

`npm.ps1`は現在のPowerShell実行ポリシーにより拒否されたが、本研究の初期構成ではNode.jsとnpmを使用しないため、実行ポリシーは変更していない。

## 未導入だが初期構成では不要なツール

- Docker
- CMake
- Ninja
- Visual Studio C/C++ Build Tools
- pnpm、Yarn

これらを導入しなくても、使用するPythonパッケージのWindows向けwheelで初期研究基盤を構築できる。

## PythonとOSMnxの選定

2026-07-27時点のOSMnx 2.1.1はPython 3.11以上を要求する。既存環境を壊さず追加ランタイムを増やさないため、Python 3.10を正式サポートするOSMnx 2.0.6を使用する。OSM取得、GraphML保存、GeoDataFrame変換、タグ保持設定など、本研究の初期段階で必要な2.x APIを利用できる。

## Eドライブへ置くもの

- Python仮想環境: `.venv`
- pipキャッシュ: `.cache\pip`
- OSMnx HTTPキャッシュ: `.cache\osmnx`
- 取得したGraphML: `data\raw`
- GeoJSON: `data\exports`
- 属性集計CSVと概要JSON: `data\processed`

## システムへの影響

- 管理者権限を使用していない。
- システム環境変数、PATH、PowerShell実行ポリシーを変更していない。
- Cドライブへ新しいSDKや大容量ツールを導入していない。
- 既存のPython、Node.js、Git、VS Codeを削除・更新していない。

