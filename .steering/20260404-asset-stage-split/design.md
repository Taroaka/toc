# Design

## Stage split

### Stage 1: asset design / review / generation

新設 artifact:

- `asset_plan.md`

役割:

- reusable asset の設計正本
- human review の正本
- script review 中に出た asset 指示の受け皿

対象:

- character reference
- object / setpiece / phenomenon reference
- location anchor
- reusable still anchor

入力:

- `script.md`
- `story.md`
- 必要なら `video_manifest.md` の assets bible

出力:

- approved `asset_plan.md`
- そこから生成された `assets/characters/*`, `assets/objects/*`, `assets/locations/*`, `assets/scenes/*`

### Stage 2: cut image generation

既存の `video_manifest.md` ベース運用を維持する。

- `scene_contract`
- `image_generation.prompt`
- `still_assets[]`
- `reference_usage[]`
- `image_generation.review`

## `asset_plan.md` contract

最低限:

- `asset_plan_metadata`
- `review_contract`
- `assets.characters[]`
- `assets.objects[]`
- `assets.locations[]`
- `assets.reusable_stills[]`

各 asset entry は少なくとも:

- `asset_id`
- `asset_type`
- `source_script_selectors[]`
- `story_purpose`
- `visual_spec`
- `generation_plan`
- `review`

を持つ。

## Source priority

asset stage では次を読む。

1. `script.md`
   - `scene_summary`
   - `visual_beat`
   - `approved_image_notes`
   - `human_change_requests[]`
2. `story.md`
3. 必要なら `video_manifest.md.assets.*`

asset stage では、cut prompt 本文ではなく **reusable asset の正しさ** を優先する。

## Review policy

asset stage review は cut stage review と分ける。

- asset stage review
  - その asset が今後の cut で再利用可能か
  - script の該当箇所を外していないか
  - 人レビューの参照/背景/派生指示を満たしているか
- cut stage review
  - 既存どおり scene/cut prompt の品質を確認

## State / gates

新設:

- `stage.asset_plan_review`
- `stage.asset_generation`
- `gate.asset_review`
- `review.asset.status`
- `artifact.asset_plan`

cut stage の既存 key:

- `stage.image_prompt_review`
- `stage.image_generation`

は維持する。
