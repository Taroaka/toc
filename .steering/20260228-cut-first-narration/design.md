# Cut planning from narration (design)

## Core rule

- 1カット = 1ナレーション
- メインカット（最低1つ）: 5–15 秒（ナレーション実秒）
- サブカット（任意 / 複数可）: 3–15 秒（短尺3–4秒はサブのみ）
- scene と narration が揃った時点で、カット分割の要否を都度判断する

## Manifest representation

- `video_manifest.md` は `scenes[]` の中に `cuts[]` を持てる（既存実装）。
- これまで `timestamp` から動画/音声尺を推定していたが、カットごとに秒数を持てないため、
  `video_generation.duration_seconds`（および必要なら `duration_seconds`）を **cut単位**で解釈できるように実装を拡張する。

## Pipeline / Ops

- 先に音声を作る場合は `scripts/generate-assets-from-manifest.py` を **audio-only** で実行できる:
  - `--skip-images --skip-videos` を併用
- 完成レンダリングは `scripts/render-video.sh` の `--narration-list` を基本にし、
  既存の単一 `--audio` 方式は後方互換として残す（没入型の既存 run を壊さない）。

## Exclusion

- `cloud_island_walk` 体験（哲学を島でPOV視点で語る）に関するテンプレ/手順は変更しない。
