# Design

## Overview

音声生成後の `duration sync` の直後に、新しい尺ゲートを入れる。
repo 側では subagent の自動起動はできないため、prompt artifact を自動生成し、
run を `changes_requested` 状態で止める。

## Workflow

1. `generate-assets-from-manifest.py --skip-images --skip-videos`
2. `sync-manifest-durations-from-audio.py`
3. `check-audio-duration-gate.py`
   - actual seconds を読む
   - minimum seconds を解決する
   - pass なら state / slot を更新して続行
   - fail なら review prompt artifact を 2 本生成して停止
4. pass の場合だけ human review / image / video に進む

## Threshold resolution

優先順:

1. CLI `--min-seconds`
2. `state.txt`
   - `runtime.target_video_seconds`
   - `runtime.duration_gate.minimum_seconds`
3. `video_manifest.md`
   - `video_metadata.minimum_duration_seconds`
   - `video_metadata.target_duration_seconds`
4. `video_metadata.experience == cinematic_story`
   - 300 秒
5. `script.md`
   - `script_metadata.target_duration`
6. fallback
   - gate なし

## New p-slots

- `p830`: duration fit gate
- `p840`: scene stretch review
- `p850`: narration stretch review
- `p860`: audio QA / human review handoff

## State additions

- `review.duration_fit.status=passed|changes_requested|skipped`
- `review.duration_fit.actual_seconds`
- `review.duration_fit.minimum_seconds`
- `review.duration_fit.note`
- `review.duration_fit.at`
- `review.duration_fit.scene_prompt`
- `review.duration_fit.narration_prompt`

## Prompt artifacts

- `logs/review/duration_scene.subagent_prompt.md`
- `logs/review/duration_narration.subagent_prompt.md`

## Integration point

`scripts/toc-immersive-ride-generate.sh` の audio-only 生成と duration sync の直後に
`check-audio-duration-gate.py` を差し込む。
