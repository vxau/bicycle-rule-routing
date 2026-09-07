# 交通ルールとOSMタグの対応表（Phase 2）

確認日: 2026-08-24

## 位置づけ

本表は、交通ルールとOpenStreetMap（OSM）の道路属性を、経路選定システム上でどのように扱うかを整理した初期設計である。OSMタグだけで現地の標識・道路状況・法的例外を完全には判定できないため、本システムは違反判定を行わず、通行制約候補・注意項目・研究用コストとして利用する。

警察庁は、自転車は軽車両であり、車道の左側通行が原則、歩道通行は例外であること、交差点では信号と一時停止を守ることを示している。また、2026年4月1日から16歳以上の自転車運転者に交通反則通告制度が適用されている。

## 対応表

| 交通ルール・評価項目 | 主なOSMタグ | Phase 3.2での扱い | Phase 4での候補 | 欠損時の扱い・限界 |
|---|---|---|---|---|
| 自転車通行可否 | `bicycle=*`、`access=*` | `no`や`private`を通行禁止候補として識別 | ハード制約として除外 | タグなしを通行禁止・通行可のどちらとも断定しない |
| 一方通行 | `oneway=*` | OSMnxが作る有向グラフの向きを利用 | 逆方向を通行不可とする | OSMnxによる正規化後の値と生OSMタグを区別する必要がある |
| 自転車の一方通行例外 | `oneway:bicycle=*` | 取得・欠損率集計まで実施 | `oneway:bicycle=no`の場合の逆方向エッジを検証 | 一方通行道路に限定した評価が必要 |
| 自転車設備 | `cycleway=*`、`cycleway:left/right/both=*` | 設備あり区間の距離割合を集計 | 設備なし・不明へソフトペナルティ | タグなしは設備なしではなく不明 |
| 道路種別 | `highway=*` | `trunk`、`primary`、`secondary`、`tertiary`を段階的な仮リスクに分類 | プロファイル別に重み変更 | 道路種別だけで実交通量・危険性は判断できない |
| 制限速度 | `maxspeed=*` | 経路上の不明率を集計 | 高い値へソフトペナルティ | 法定速度や暗黙値がタグに現れない場合がある |
| 道幅・車線数 | `width=*`、`lanes=*` | `width`の不明率を集計 | 狭い道路の評価に利用 | `lanes`から実幅員を正確には求められない |
| 路面 | `surface=*` | 経路上の不明率を集計 | 未舗装・走りにくい路面へペナルティ | 状態の経年変化や局所的な荒れを反映できない |
| 信号・一時停止 | `highway=traffic_signals`、`highway=stop` | 最短経路上の信号数を集計 | 注意地点・交差点コストとして利用 | 停止方向や信号対象方向を追加確認する必要がある |
| 横断 | `crossing=*`、`bicycle=*` | データ取得・全体集計まで実施 | 注意地点として表示 | 横断方法の法的妥当性をタグだけで断定しない |
| 属性欠損 | 対象タグなし | 不明率と仮`unknown_risk`を算出 | 情報信頼性優先プロファイルへ利用 | 「存在しない」と「未調査」を区別する |

## Phase 3.2の仮コスト

現段階の最短経路は`length`だけで選定する。次の値はPhase 4へ向けた計算基盤であり、経路選定にはまだ使わない。

```text
provisional_cost
= distance
 × (1
    + 0.4 × road_type_risk
    + 0.2 × cycleway_risk
    + 0.5 × unknown_risk)
```

- `road_type_risk`: 道路種別に対する暫定値
- `cycleway_risk`: `cycleway`が確認できる場合0、それ以外1
- `unknown_risk`: `bicycle`、`cycleway`、`maxspeed`、`width`、`surface`の不明割合
- `bicycle=no`または`access=no/private`: 通行禁止候補として識別し、仮コストは算出対象外

係数は有効性を示す確定値ではない。Phase 5では、根拠、感度分析、現地確認を通して見直す。

## Phase 4の経路プロファイル

同じ道路コスト要素に異なる暫定重みを与え、次の5種類を比較する。

| ID | 表示名 | 道路種別 | 自転車設備なし | 属性不明 | 明示的通行禁止 |
|---|---|---:|---:|---:|---|
| `shortest` | 距離最短 | 0.0 | 0.0 | 0.0 | 比較基準では除外しない |
| `rule` | ルール遵守優先 | 0.1 | 0.1 | 0.35 | 除外 |
| `safety` | 安全性優先 | 0.8 | 0.6 | 0.1 | 除外 |
| `information` | 情報信頼性優先 | 0.0 | 0.0 | 1.0 | 除外 |
| `balanced` | バランス型 | 0.4 | 0.2 | 0.5 | 除外 |

`shortest`は従来型との比較基準を残すため距離のみで計算する。他の4種類は`bicycle=no`または`access=no/private`を通行不可とし、方向規制はOSMnxが生成した有向グラフに従う。タグ欠損は「通行不可」や「危険」と断定せず、評価情報の不確実性としてのみ加点する。

## 参照した一次・技術資料

- [警察庁「自転車は車のなかま～自転車はルールを守って安全運転～」](https://www.npa.go.jp/bureau/traffic/bicycle/info.html)
- [警察庁「自転車の新しい制度」](https://www.npa.go.jp/bureau/traffic/bicycle/portal/system.html)
- [OpenStreetMap Wiki: Key:oneway](https://wiki.openstreetmap.org/wiki/Key:oneway)
- [OpenStreetMap Wiki: Key:bicycle](https://wiki.openstreetmap.org/wiki/Key:bicycle)
- [OpenStreetMap Wiki: Key:access](https://wiki.openstreetmap.org/wiki/Key:access)
- [OpenStreetMap Wiki: Key:cycleway](https://wiki.openstreetmap.org/wiki/Key:cycleway)
- [OpenStreetMap Wiki: Key:highway](https://wiki.openstreetmap.org/wiki/Key:highway)
- [OpenStreetMap Wiki: Key:maxspeed](https://wiki.openstreetmap.org/wiki/Key:maxspeed)
- [OpenStreetMap Wiki: Key:surface](https://wiki.openstreetmap.org/wiki/Key:surface)
- [OpenStreetMap Wiki: Key:width](https://wiki.openstreetmap.org/wiki/Key:width)

## Phase 5へ残す検証

- 生OSMタグとOSMnx正規化後グラフの方向・通行可否を比較する
- 一方通行道路だけを対象に`oneway:bicycle`の充足率を算出する
- 日本の標識・例外規定とOSMタグの対応を代表地点で現地確認する
- 仮コストの各重みを変えた感度分析を行う
- 複数ODペアで各プロファイルの距離・道路属性指標を比較する
