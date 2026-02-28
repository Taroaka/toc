# Entrypoint（/toc-scene-series）仕様（正本）

このドキュメントは `/toc-scene-series` の仕様を定義する。

## 目的

topic を起点に、**情報収集 → sceneごとのQ&A縦動画（複数本）** を一連で作る。

## 仕様（想定）

- コマンド: `/toc-scene-series`
- 引数:
  - `topic`（必須）
  - `--min-seconds`（任意。default 30）
  - `--max-seconds`（任意。default 60）
  - `--scene-ids`（任意。部分実行用）
  - `--dry-run`（任意。外部生成APIは呼ばない）

## 挙動（成果物）

run root:

- `output/<topic>_<timestamp>/`
  - `state.txt`（追記型）
  - `research.md`
  - `story.md`
  - `series_plan.md`
  - `scenes/sceneXX/`（scene単位の成果物）

scene folder（1本の縦動画）:

- `output/<topic>_<timestamp>/scenes/sceneXX/`
  - `evidence.md`
  - `script.md`
  - `video_manifest.md`
  - `assets/**`
  - `video.mp4`

## question の扱い

- 原則: `story.md` / `script.md` の `text_overlay.sub_text` を question として扱う
- question に対して:
  - まず既存 `research.md` から根拠を抽出
  - 不足時のみ追加のWeb調査（テキスト中心）

## 実装メモ

- 雛形生成ヘルパ: `scripts/toc-scene-series.py`
  - `--placeholder-e2e` でプレースホルダ素材→結合まで実行可能
- カット設計: `video_manifest.md` は `scenes[].cuts[]` を使い、**1カット=1ナレーション**（メイン=5–15秒、サブ=3–15秒）を基本にする

## 参照

- `.claude/commands/toc/toc-scene-series.md`
- `docs/how-to-run.md`
- `docs/implementation/video-integration.md`
