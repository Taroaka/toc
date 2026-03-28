# Design

## Review gate
- `scripts/review-image-prompt-story-consistency.py` に `prompt_mentions_character_but_character_ids_empty` を追加する
- 条件:
  - prompt 本文に character alias hit がある
  - `image_generation.character_ids` が空
- これにより source text から取れないケースでも、prompt 側の人物 mention を根拠に fail できる

## Still selection
- `SceneSpec` に `still_image_plan_mode` を追加する
- manifest parse 時に cut / scene の `still_image_plan.mode` を保持する
- image generation pass では helper で eligibility を判定する
  - reference image path は常に eligible
  - story still は `--image-plan-modes` に含まれる mode だけ eligible
- default `--image-plan-modes` は `generate_still`

## Operator control
- `--image-plan-modes generate_still,reuse_anchor` のように明示的に broaden できる
- default は review/export 対象と一致させ、運用上の surprise をなくす
