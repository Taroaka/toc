# Requirements: Existing-story value amplification

## Goal

既に完成し評価されている物語を改変するのではなく、その原作価値を scene / cut の映像・演技・音・編集へ追跡し、生成AIによる映像化で観客体験を最大化できる正本契約を追加する。

## Success criteria

- 新規 authoring agent が、会話履歴を知らなくても必要な key、意味、出力例を grounding readset から取得できる。
- `source value -> scene amplification -> cut expression` の参照が machine-readable である。
- 原作イベントの保存と、映像表現による価値増幅を別契約として扱う。
- scene / cut が「綺麗な説明絵」へ縮退することを `must_not_reduce_to` と観客体験差分で検出できる。
- schema の型検証だけで意味品質を合格扱いにせず、deterministic validator と semantic review の責務を分ける。
- provider prompt へ内部 ID や抽象的な設計文を直接流さない。
- legacy artifact は明示 marker がない限り、新契約不足だけで破壊しない。

## Scope

- 正本の設計文書と stage grounding readset
- story / visual value / script / manifest の template
- adaptation-value block の machine-readable schema
- story / script の deterministic validation と単体テスト
- frontend create scaffold の新規 artifact projection（既存の未コミット変更を保持した最小差分）

## Non-goals

- 原作の主要イベント、結末、人物関係を自動改変すること
- すべての provider prompt へ設計 metadata を直接追加すること
- 今回の変更だけで音響ミックス、カラー、編集UIを完成させること
- 既存 run を一括 migration すること

## Decision rules

- 原作価値の変更は自動修正せず、人間承認へ送る。
- 映像表現の修正は原作価値を保つ範囲で自動 repair できる。
- 型・必須 key・参照整合は deterministic validator、表現が本当に価値を増幅するかは semantic reviewer が判定する。

