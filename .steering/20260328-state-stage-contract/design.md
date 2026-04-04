# Design

## Decision

- 高レベルの `status=` はそのまま残す
- 詳細進行は `stage.<name>.status=` で表す
- `state.txt` は append-only の snapshot log を維持する

## Stage keys

標準化する stage:

- `stage.research`
- `stage.story`
- `stage.visual_value`
- `stage.script`
- `stage.image_prompt_review`
- `stage.image_generation`
- `stage.video_generation`
- `stage.narration`
- `stage.render`
- `stage.qa`

各 stage で持てるキー:

- `stage.<name>.status=pending|in_progress|done|failed|skipped`
- `stage.<name>.started_at=ISO8601`
- `stage.<name>.finished_at=ISO8601`

## Role split

- `status=`:
  - 粗い現在位置
  - RESEARCH / STORY / SCRIPT / VIDEO / QA / DONE
- `stage.*.status=`:
  - 実務上の完了状況
  - `state.txt` だけで「ナレーションまで終わったか」を読むための粒度

## Write flow

各作業で 2 回 append を基本とする。

1. 開始時:
   - `status=...`
   - `stage.<name>.status=in_progress`
   - `stage.<name>.started_at=...`
2. 完了時:
   - `status=...`（必要なら次の大段階へ）
   - `stage.<name>.status=done`
   - `stage.<name>.finished_at=...`
   - 対応 artifact / review key

失敗時:

- `stage.<name>.status=failed`
- `last_error=...`

スキップ時:

- `stage.<name>.status=skipped`

## Docs updates

- `workflow/state-schema.txt`
- `docs/data-contracts.md`
- `docs/how-to-run.md`
- `docs/orchestration-and-ops.md`
