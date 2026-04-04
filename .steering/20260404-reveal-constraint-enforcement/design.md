# Design

## Shared Reveal Constraint Helper

`toc/reveal_constraints.py` を追加し、次を共通化する。

- `evaluation_contract.reveal_constraints` の parse
- `sceneYY_cutZZ` selector の parse
- manifest 内 cut 順序の index 化
- asset alias を使った subject 出現判定
- 「selector より前で subject が出た」違反の抽出

image reviewer と manifest stage evaluator は同じ helper を使う。

## Image Review Integration

- `review-image-prompt-story-consistency.py` は `script.md` の structured data から reveal constraints を取得する
- 各 prompt entry について、story shot かつ selector より前なら:
  - `image_generation.character_ids` / `object_ids`
  - prompt 本文の alias hit
  を evidence として評価する
- 違反時は `script_reveal_constraint_violated` を finding に追加する

## Manifest Stage Integration

- `toc/stage_evaluator.py` の manifest review で `script.md` を読み、同じ reveal helper を使う
- manifest node の `image_generation.prompt`, `video_generation.motion_prompt`, `audio.narration.text`, `character_ids`, `object_ids` をまとめて評価し、違反時は `manifest.script_reveal_constraints_violated` check を fail にする

## Docs / Tests

- `docs/data-contracts.md`, `docs/how-to-run.md`, `docs/implementation/image-prompting.md`, `workflow/video-manifest-template.md` に script reveal contract の読み取りを追記する
- `tests/test_image_prompt_story_review.py` に image reviewer の違反検出テストを追加する
- `tests/test_stage_evaluator_scripts.py` に manifest stage evaluator の違反検出テストを追加する
