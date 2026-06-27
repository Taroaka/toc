# Design

## Pipeline Contract

画像生成 request の prompt contract を次の 3 段階に分ける。

### 1. deterministic compiler

`scripts/generate-assets-from-manifest.py` が request materialization 時に `api_prompt_payload` を作る。

- asset stage:
  - source: `SceneSpec.image_prompt`
  - output: `api_prompt_payload.policy_version=image_api_prompt_v1`
  - output: `api_prompt_payload.prompt`
  - output: `api_prompt_payload.sha256`
- scene stage:
  - existing `_image_api_prompt_payload_for_scene()` を維持する

### 2. prompt editor

最初の実装では deterministic editor として入れる。

- `_final_image_prompt_editor()` が provider に描かせる文だけを整える
- story title + scene id、first-frame authoring metadata、debug marker、motion-only metadata を削る
- asset prompt は `[全体 / 不変条件]`, `[作成するもの]`, `[人物固定]`, `[小道具固定]`, `[場所固定]`, `[禁止]` のような drawable block を残す

将来 LLM agent を使う場合も、出力先は `api_prompt_payload.prompt` に固定する。agent の review/report は別 artifact に置き、API prompt へ混ぜない。

### 3. leak gate

検査対象は request file の `api_prompt` fence とし、debug fence は対象外にする。

検査語:

- `debug_prompt_source`
- `first_frame_visual_plan`
- `source_event_beat_id`
- `event_time_position`
- `what_happens`
- `visible_action`
- `motion_brief`
- `cut_contract`
- `scene_event`
- `validation_gates`
- `api_prompt_payload`
- `sceneNN_cutNN`
- `物語「...」の sceneNN`
- `この画像は物語「...」の一場面`

## Integration Points

- `scripts/generate-assets-from-manifest.py`
  - asset stage request entries now receive `api_prompt_payload`
  - asset stage entries do not receive `first_frame_visual_plan`
  - request preview writer continues to prefer `api_prompt` when present
- `scripts/verify-pipeline.py`
  - p550 checks final API prompt fences for leaks
- `tests/test_request_preview_prompt.py`
  - asset request includes `api_prompt`
  - asset request omits first-frame debug
  - asset API prompt uses asset prompt source

## Done Criteria

- A materialized asset request from an asset-stage manifest contains `prompt_policy_version: image_api_prompt_v1` and an `api_prompt` fence.
- The same request does not contain `debug_prompt_source`, `first_frame_visual_plan`, `source_event_beat_id`, or `このcut`.
- Existing scene request tests still pass and continue to include debug separation.
- `python -m unittest tests.test_request_preview_prompt` passes.
- `python scripts/verify-pipeline.py --run-dir output/シンデレラ_20260622_2330 --flow immersive --profile fast` does not fail because asset request prompt includes scene/debug metadata.
