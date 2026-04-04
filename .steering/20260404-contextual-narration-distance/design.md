# Design

## Core Principle

`narration` と `visual_beat` の関係は phase 固定ではなく、**scene の仕事**で決める。

- immersion-first
  - 視聴者を世界と出来事に没入させる
  - `narration` は `visual_beat` に近くてよい
- meaning-first
  - 映像を見たあとに意味・代償・余韻を残す
  - `narration` は `visual_beat` と少し離れてよい

## Policy

- opening
  - 原則 `stay_close`
  - 状況理解と安定感を優先
- middle
  - 原則 `stay_close`
  - reveal / complication / emotional hinge の cut だけ `contextual`
- ending
  - 原則 `contextual`
  - `change_if_useful`, not `must_change`
  - まだ没入維持が必要な cut では close を許容

## Story Ending Type

script / evaluator が考慮するべき結末型:

- `happy`
- `bittersweet`
- `tragic`
- `cautionary`
- `ambiguous`

例:

- happy
  - 終盤 narration は達成・回復・祝福を価値化しやすい
- bittersweet
  - 得たもの / 失ったものの両方を残す
- tragic
  - 喪失そのものの重さを残す
- cautionary
  - 行為と代償の関係を残す

浦島太郎は基本的に `bittersweet|tragic|cautionary` 側として扱う。

## Recommended Script Fields

```yaml
script_metadata:
  ending_mode: "happy|bittersweet|tragic|cautionary|ambiguous"

scenes:
  - scene_id: 15
    narration_distance_policy: "stay_close|contextual|meaning_first"
    narrative_value_goal:
      mode: "immersion|meaning|mixed"
      leave_viewer_with: ["何を失ったのか", "なぜそれが重いのか"]
```

## Evaluator Intent

将来的に evaluator は次を判断する。

- `stay_close`
  - `narration` と `visual_beat` の近さを減点しない
- `contextual`
  - 近くてもよいし、少し離れてもよい
- `meaning_first`
  - 単なる visual の言い換えだけなら弱い
  - 「映像のあとに意味が残る一文」があると加点

## Urashima-specific Guidance

- 序盤 / 中盤
  - 物語への没入を優先
  - `narration` は `visual_beat` と近くてよい
- 帰還以後
  - 代償の理解が主題になる
  - `narration` は必要に応じて意味層を足してよい
  - 特に
    - 何を失ったのか
    - なぜそれが重いのか
    を価値化してよい
