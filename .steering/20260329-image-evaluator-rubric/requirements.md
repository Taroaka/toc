# Requirements

## Goal

画像 prompt evaluator を lint/checklist 中心から rubric + contract 中心へ拡張し、gradability を上げる。

## Requirements

- image review は criterion ごとの score を持つ
- score は `image_generation.review` に source manifest へ書き戻す
- image node ごとに contract を持てる
- evaluator は contract 未定義、must include 未達、must avoid 違反を検出できる
- 重要軸は `story_alignment` と `subject_specificity` を重めに扱う
- 既存の missing ids / required block / self-contained review は維持する
