# Audio-First Production Order Design

## Core decision

- 最終尺の正本は実 TTS 秒数であり、production order はそれに従う。
- したがって fixed workflow の後半は `p500 narration/audio -> p600 asset -> p700 scene implementation -> p800 video -> p900 render` とする。

## Contract changes

- `p400` に `p450 skeleton manifest materialization` を追加する。
- `video_manifest.md` は top-level `manifest_phase: skeleton|production` を持つ。
- stage grounding contract は `narration`, `asset`, `scene_implementation`, `video_generation` を canonical stage とする。
- `scene_implementation` には `image_prompt` を alias として残す。

## Migration

- slot key を old->new mapping で書き換える。
- `stage.image_prompt.*` と `logs/grounding/image_prompt.*` は `scene_implementation` へ移す。
- 既存 manifest に `manifest_phase` が無ければ `production` を付与する。
- 各 run の migration 後に `p000_index.md` と `run_status.json` を再生成する。

## Enforcement

- `generate-assets-from-manifest.py` は image/video generation 時に `manifest_phase=production` を必須にする。
- manifest evaluator / verifier も production manifest を前提にする。
- duration gate は新 slot (`p540`/`p550`/`p560`/`p570`) を更新する。
