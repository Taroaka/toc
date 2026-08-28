# ToC Audience Unit Registry

更新日: 2026-08-09

この文書は、Workstream 3 が獲得、proof、面談、CRM、分析で使う audience unit の正本である。

audience unit は、次の一対だけで構成する。

```text
1 persona
  x
1 customer attribute
  =
1 audience unit
```

## Definitions

- `persona`: 本人が内側に持つ欲求、進みたい状態、感じている障壁
- `customer_attribute`: 購買文脈として観察できる顧客属性
- `audience_unit`: 一つの persona と一つの customer attribute を固定した獲得・分析単位

persona と customer attribute を一つの曖昧なラベルへまとめない。一つの実験、広告、投稿、LP、proof、面談集計は、必ず一つの `audience_unit_id` だけを参照する。

## Upstream compatibility

`marketing/README.md` と `marketing/positioning-and-offer.md` は現在 `side_business` を primary target / persona label として使う。Workstream 3 では、この互換ラベルを残したまま、本人の欲求を表す persona と購買文脈を表す customer attribute を別 ID で記録する。上流定義の変更は Workstream 1 への handoff とし、この registry だけで黙って上書きしない。

## Append-only rules

1. 公開済み・実験済みの `audience_unit_id` の意味を変更しない
2. 新しい persona または customer attribute を扱う場合は、新しい行と新しい ID を追加する
3. 同じ `persona_id` を別の `customer_attribute_id` へ付け替えない。顧客属性が変わる場合は新しい persona / audience unit として定義する
4. 対象から外す場合も削除せず、status を `deferred` または `retired` にする
5. 表現だけを改善する場合は `message_version` を増やし、persona の意味は変えない
6. 定義を実質的に変更する場合は新しい ID を作り、`supersedes` で旧 ID と関係づける
7. 集計は `audience_unit_id` ごとに分け、異なる unit を同じ母数へ混ぜない

## Active registry

### AU-001

| Field | Value |
|-------|-------|
| audience_unit_id | `AU-001` |
| status | `active` |
| effective_from | `2026-08-09` |
| persona_id | `P-001` |
| persona statement | `自分の想いを動画にしたい人` |
| meaning of 想い | 自分の経験、知識、物語、企画、伝えたい価値観 |
| desired progress | 自分の言葉から最初の動画を完成させ、公開して反応を確かめる |
| main obstacle | 制作工程、編集、複数ツール、時間、費用によって完成・公開できない |
| customer_attribute_id | `CA-001` |
| customer attribute | 副業として発信・反応検証に取り組む個人 |
| observable fit | 具体的テーマ、直近の制作行動または停止、反応検証の目的がある |
| upstream target label | `side_business` |
| primary production mode | `video` |
| public entrance | `あなたの想いを、映像に。` |
| message_version | `MV-001` |
| supersedes | none |

## Deferred candidate queue

`small_business_operator` は upstream の将来 target として保持するが、まだ audience unit を発行しない。Eコマース寄りの表現、商品導線、事業別カスタマイズの要件を整理し、その市場固有の persona statement が決まった時点で、新しい `persona_id`、`customer_attribute_id`、`audience_unit_id` を追記する。

`AU-001` を小規模ビジネス向けに書き換えたり、同じ実験母数へ混ぜたりしない。

## New unit template

```yaml
audience_unit_id: AU-XXX
status: draft|active|deferred|retired
effective_from: YYYY-MM-DD
persona:
  persona_id: P-XXX
  statement: ""
  desired_progress: ""
  main_obstacle: ""
customer_attribute:
  customer_attribute_id: CA-XXX
  definition: ""
  observable_fit: []
upstream_target_label: ""
primary_production_mode: image_batch|video
public_entrance: ""
message_version: MV-XXX
supersedes: none|AU-XXX
decision_source: ""
```

## Required references

Every new experiment、proof request、interview aggregate、CRM aggregate、analytics result records:

- `audience_unit_id`
- `persona_id`
- `customer_attribute_id`
- `message_version`

The prose labels may be copied for readability, but IDs are the join keys.
