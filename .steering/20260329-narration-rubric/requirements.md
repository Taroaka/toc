# Requirements

## Goal

ナレーション evaluator を lint から rubric へ拡張し、「正しく読める」だけでなく「映像と役割分担できているか」まで gradable にする。

## Requirements

- narration review は criterion ごとの score を持つ
- score は `audio.narration.review` に source manifest へ書き戻す
- score は改善行動に直結するよう、criterion ごとに reason key を持てる
- evaluator は repo の標準運用である `eleven_multilingual_v2` を前提にする
- 基準は、モデルが元々満たしやすい軸と失敗しやすい軸を分けて扱う
- 重要軸は `non_visual_value` と `anti_redundancy` を重めに扱う
- 機械判定だけでなく、image/video prompt との関係から「映像の説明をなぞっていないか」を見る
