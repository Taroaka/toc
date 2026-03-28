# Data Contracts (MVP)

本書は `todo.txt` の 6) Data contracts を具体化する。

## 1. State schema（ジョブ状態）

`docs/orchestration-and-ops.md` のマニフェストを最小化し、
**テキスト（key=value）で状態を管理**する。

状態ファイルはプロジェクトフォルダに置く：

```
output/<topic>_<timestamp>/state.txt
```

更新方式は **追記型**（最新のブロックが現在状態）。

```text
timestamp=ISO8601
job_id=JOB_YYYY-MM-DD_0001
topic=string
status=INIT|RESEARCH|STORY|SCRIPT|VIDEO|QA|DONE
gate.research_review=required|optional|skipped
gate.story_review=required|optional|skipped
gate.video_review=required|optional|skipped
artifact.research=output/<topic>_<timestamp>/research.md
artifact.story=output/<topic>_<timestamp>/story.md
artifact.visual_value=output/<topic>_<timestamp>/visual_value.md
artifact.script=output/<topic>_<timestamp>/script.md
artifact.video=output/<topic>_<timestamp>/video.mp4
---
```

対応テンプレート: `workflow/state-schema.txt`

派生物（machine-facing）:

```
output/<topic>_<timestamp>/run_status.json
```

- `state.txt` の flat / nested view
- artifact inventory
- pending gate
- `eval_report.json`（あれば埋め込む）

---

## 2. Artifact paths（成果物パス）

標準パス:

```
output/<topic>_<timestamp>/
  research.md
  story.md
  visual_value.md
  script.md
  video.mp4
  video_manifest.md
  assets/
```

scene-series（Q&A動画を複数本）:

```
output/<topic>_<timestamp>/
  series_plan.md
  scenes/sceneXX/
    evidence.md
    script.md
    video_manifest.md
    assets/
    video.mp4
```

---

## 3. Output templates（最小テンプレ）

以下のテンプレートをMVPの出力契約とする。

- `workflow/research-template.yaml`
- `workflow/research-template.production.yaml`（情報量を最大化したい場合の推奨スキーマ）
- `workflow/story-template.yaml`
- `workflow/visual-value-template.yaml`
- `workflow/script-template.yaml`
- `workflow/scene-outline-template.yaml`（story → 画像/動画生成の橋渡し。未知トピックでモデル記憶に依存しないための asset brief）

各テンプレートは `docs/information-gathering.md` / `docs/story-creation.md` /
`docs/script-creation.md` のスキーマから最小フィールドのみ抽出。

評価仕様の正本:

- `workflow/evaluation_criteria.md`
- `workflow/evals/golden-topics.yaml`

---

## 4. Immersive `video_manifest.md`（assets bible）

`/toc-immersive-ride` は `output/<topic>_<timestamp>/video_manifest.md` を正本として、
画像/動画/TTS を一括生成する。

この manifest の契約は、最終的に `scripts/generate-assets-from-manifest.py` が読み取り、各 provider に投げる前提。

### 4.1 `assets`（bible）

- `assets.character_bible[]`（人物の参照画像 + 不変条件 + optional な体格契約）
- `assets.character_bible[].reference_variants[]`（optional）
  - `variant_id`
  - `reference_images: [string, ...]`
  - `fixed_prompts: [string, ...]`（optional）
- `assets.character_bible[].review_aliases[]`（optional。story/script review で使う別名）
- `assets.character_bible[].physical_scale.height_cm|body_length_cm|shell_length_cm|shoulder_height_cm`（optional）
- `assets.character_bible[].physical_scale.silhouette_notes[]`（optional）
- `assets.character_bible[].relative_scale_rules[]`（optional。複数キャラ scene の相対サイズ固定）
- `assets.style_guide`（スタイル/禁止/参照）
- `assets.object_bible[]`（主役級アイテム/舞台装置の参照画像 + 不変条件）
  - `assets.object_bible[].reference_variants[]`（optional, character と同型）
  - `assets.object_bible[].review_aliases[]`（optional。story/script review で使う別名）
  - 詳細仕様（正本）: `docs/implementation/asset-bibles.md`

### 4.2 `scenes[].image_generation`

- `prompt` は構造化テンプレで書く（正本: `docs/implementation/image-prompting.md`）
- 言語: 原則 **日本語**（見出しタグは固定推奨、`AVOID` は英語キーワード併記可）
- `character_ids: []` は常に明示（B-roll は `[]`）
- `character_variant_ids: []` は optional。複数 state/time variant がある場合だけ、scene/cut ごとに使う variant を明示する
- `object_ids: []` は常に明示（setpiece/アイテムが無い scene でも `[]`）
- `object_variant_ids: []` は optional。複数 variant がある object/setpiece を scene/cut ごとに切り替えるときに使う
- 新規の静止画生成は必須ではない。連続性アンカーを作る scene/cut、または同じ場所/物体/人物状態を複数scene/cutで再利用したい場合に優先する
- 既存の参照画像や直前の anchor frame を再利用できる場合は、同じ構図の再生成を避けてよい

### 4.3 `scenes[].cuts[]`（optional, recommended）

シーンを「複数カット（3〜5枚）」で表現したい場合、`scenes[]` の各要素に `cuts[]` を持たせる。
生成スクリプトは `cuts[]` を展開して画像/動画を生成する（cutごとに `image_generation` / `video_generation` を持つ）。

---

## 5. `image_generation.review` contract

画像生成前 gate の review 状態は `video_manifest.md` の各 renderable image node に直接保持する。派生の `prompt_collection` は正本ではない。

各 `scenes[].image_generation.review` または `scenes[].cuts[].image_generation.review` は、少なくとも次の review field を持つ。

```yaml
agent_review_ok: true|false
agent_review_reason_keys: []
human_review_ok: true|false
human_review_reason: ""
```

補足:

- 現行表記として `agent_review_reason_codes` を使っていてもよいが、意味は `agent_review_reason_keys` と同じに保つ
- `agent_review_reason_summary` は任意の補助説明であり、reason key の代替にはしない

Semantics:

- `agent_review_ok`
  - subagent がその manifest node を story/script/reference 契約に照らして再生成可能と判断した結果
  - 不足がある間は `false`
- `agent_review_reason_keys`
  - `agent_review_ok: false` の理由 key
  - false のときは空にしない
  - fix 後に subagent が `true` に戻したら空配列でよい
- `human_review_ok`
  - 人間が finding を理解したうえで例外許容した記録
  - subagent finding 自体の解消を意味しない
- `human_review_reason`
  - 人間 override の理由
  - `human_review_ok: true` のときは必須

Canonical reason key:

- `missing_character_ids`
- `missing_object_ids`
- `environment_only_prompt`
- `missing_story_action`
- `missing_story_relationship`
- `continuity_anchor_missing`
- `reference_missing`
- `missing_required_prompt_block`
- `camera_or_composition_under_specified`

Lifecycle:

1. subagent が不足を検出した node を `agent_review_ok: false` にする
2. subagent が `agent_review_reason_keys` を残す
3. fix を source manifest に反映する
4. subagent が再 review し、解消済み node を `agent_review_ok: true` に戻す
5. なお未解消 finding を人間判断で許容する場合だけ `human_review_ok: true` と `human_review_reason` を記録する

Required prompt blocks:

- `[全体 / 不変条件]`
- `[登場人物]`
- `[小道具 / 舞台装置]`
- `[シーン]`
- `[連続性]`
- `[禁止]`

subagent review は上記 6 block を必須 criterion とする。1 つでも欠けていれば `agent_review_ok: false` とし、`missing_required_prompt_block` を reason key に含める。
