# Design: 視覚化価値想像エージェントで「中盤の視覚報酬」を設計する

## 方針

### A) エージェント配置

実行順は次を想定する。

`Deep Research -> Story/Director -> Visual Value Ideator -> Scriptwriter`

Story/Director の出力を土台にしつつ、
Scriptwriter の前で「視覚価値の高い寄与パート」を一度明示的に設計する。

### B) 何を抽出するか

新エージェントは次の観点で候補を出す。

- 非現実的な場所
- 禁忌やルールを持つアイテム
- 実写セットでは高コストすぎる壮大な現象
- 観客が探索 / 接近 / 開封 / 滞在したくなる対象

判断基準は「物語上の必須説明」ではなく、
`動画生成AIで実写風に見せると視聴者の興味を強く引けるか` に置く。

### C) 出力契約

1つの価値パートにつき以下を返す。

- `part_id`
- `title`
- `placement_window`
- `why_this_matters`
- `visual_value_hypothesis`
- `cuts[]`

`cuts[]` の各要素:

- `cut_id`
- `duration_seconds: 4`
- `narration: ""`
- `focus`
- `description`
- `viewer_payoff`

### D) Scriptwriter への接続

- Scriptwriter は通常の story 出力に加え、
  視覚化価値想像エージェントの出力を入力として受け取る
- 価値パートは原則として動画全体の 20% - 80% に配置する
- 最序盤と最終盤には置かない
- 該当カットは narration-driven ではなく visual-driven にする

### E) Manifest / asset への接続

価値パートが setpiece / artifact に依存する場合は、
既存の `assets.object_bible` と `image_generation.object_ids` に接続する。

例:

- `ryugu_palace`
- `tamatebako`
- `otohime_chamber_entrance`

## 浦島太郎への適用

代表例は `竜宮城の中身をPOVで探索する中盤シーケンス`。

- 配置: 40% - 65%
- 構成: 6 カット
- 形式: すべて 4 秒、ナレーションなし、POV
- 役割:
  - 視聴報酬
  - 異界の体験
  - 乙姫登場前の期待形成
