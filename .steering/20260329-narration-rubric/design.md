# Design

## Rubric

初期 rubric は次の 5 criterion とする。

- `tts_readiness`
- `non_visual_value`
- `anti_redundancy`
- `pacing_fit`
- `spoken_japanese`

## Weighting

重みは次とする。

- `tts_readiness`: 0.30
- `non_visual_value`: 0.25
- `anti_redundancy`: 0.20
- `pacing_fit`: 0.15
- `spoken_japanese`: 0.10

これは、記事の design evaluator と同様に「モデルが自然にできる基礎能力」より「放置すると平凡/冗長になりやすい軸」を重くする設計。

## Score semantics

- `tts_readiness`
  - v2 で破綻なく読めるか
- `non_visual_value`
  - 時間 / 因果 / 内面 / 視点 / 禁忌 / 軽い意味づけを足せているか
- `anti_redundancy`
  - image/video prompt をなぞるだけの説明になっていないか
- `pacing_fit`
  - cut 尺に対して密度・文分割・句読点が合っているか
- `spoken_japanese`
  - 書き言葉や制作語でなく、自然なナレーション日本語になっているか

## Manifest contract

`audio.narration.review` は以下を持つ。

- `agent_review_ok`
- `agent_review_reason_keys`
- `agent_review_reason_messages`
- `human_review_ok`
- `human_review_reason`
- `rubric_scores`
- `overall_score`

## Reason key expansion

rubric 由来の key を追加する。

- `narration_adds_too_little_non_visual_value`
- `narration_too_visual_redundant`
- `narration_pacing_mismatch`
- `narration_spoken_japanese_weak`
