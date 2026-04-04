# LangGraph Topology（正本）

このドキュメントは `.steering/20260117-langgraph-topology/` で合意した内容を **恒久仕様として昇華**したもの。

## 目的

LangGraph のトポロジ（状態・遷移・ゲート・再試行・サブグラフ）を定義し、以降の実装の正本とする。

## トップレベル状態

`INIT → RESEARCH → STORY → SCRIPT → VIDEO → QA → DONE`

## 実行トリガー

- 起点は Claude Code の slash command（例: `/toc-run`）
- 統括エージェントが `state.txt` を更新する

## レビューゲート

- ゲート値: `required | optional | skipped`
- デフォルト（運用方針）:
  - research_review: `required`
  - story_review: `optional`
  - hybridization_review: `required`（矛盾ソースの混成がある場合のみ）
  - video_review: `required`

## QA再試行ルール

`docs/orchestration-and-ops.md` の閾値を採用:
- `accuracy_score < 0.75` → `RESEARCH`
- `engagement_score < 0.7` → `STORY`
- `consistency_score < 0.7` → `VIDEO`

再試行上限（設計値）:
- 同一ステージの自動再試行は最大2回
- 超過時は人間レビューへ昇格

## サブグラフ（概要）

### SCRIPT：シーン作成ループ

`ScenePlan → DraftScene → ReviewScene → (ReviseScene)* → Accept`

- シーンは順序依存のため直列
- 受理済みシーンのみ `script.md` に統合

### VIDEO：シーン素材生成 + 最終合成

素材生成（承認済みシーンごと）:
- `GenerateImage`
- `WriteNarration`（ナレーション原稿の確定。`audio.narration.text` と `audio.narration.tts_text` を埋める）
- `GenerateTTS`
- `SyncDurationsFromAudio`（実秒→`duration_seconds`/`timestamp` 同期）
- `GenerateClip`
- `ValidateAssets`

最終合成:
- `AssembleTimeline → RenderVideo → ValidateVideo`

## データフロー（入出力）

- RESEARCH: topic/constraints → `research.md`
- STORY: `research.md` → `story.md`
- SCRIPT: `story.md` → `script.md`
- VIDEO: `script.md` → `assets/*`, `video_manifest.md`, `video.mp4`
- QA: 主要成果物 → QAスコア/判定

## state（ファイル）

状態は `output/<topic>_<timestamp>/state.txt` に **追記型**で記録する（key=value）。

- スキーマ: `workflow/state-schema.txt`
- 途中停止: 最新ブロックから再開
- 擬似ロールバック: 過去ブロックをコピーして末尾に追記

## 参照

- `docs/orchestration-and-ops.md`
- `docs/data-contracts.md`
- `workflow/state-schema.txt`
