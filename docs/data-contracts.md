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
stage.research.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.story.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.script.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.narration.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.render.status=pending|in_progress|awaiting_approval|done|failed|skipped
gate.research_review=required|optional|skipped
gate.story_review=required|optional|skipped
gate.script_review=required|optional|skipped
gate.image_review=required|optional|skipped
gate.narration_review=required|optional|skipped
gate.video_review=required|optional|skipped
artifact.research=output/<topic>_<timestamp>/research.md
artifact.research_review=output/<topic>_<timestamp>/research_review.md
artifact.story=output/<topic>_<timestamp>/story.md
artifact.visual_value=output/<topic>_<timestamp>/visual_value.md
artifact.script=output/<topic>_<timestamp>/script.md
artifact.script_review=output/<topic>_<timestamp>/script_review.md
artifact.manifest_review=output/<topic>_<timestamp>/manifest_review.md
artifact.video=output/<topic>_<timestamp>/video.mp4
artifact.video_review_report=output/<topic>_<timestamp>/video_review.md
eval.research.status=approved|changes_requested
eval.image_prompt.score=0.0-1.0
eval.image_prompt.findings=0
eval.image_prompt.unresolved_entries=0
eval.script.status=approved|changes_requested
eval.script.findings=0
eval.manifest.status=approved|changes_requested
eval.manifest.findings=0
eval.video.status=approved|changes_requested
eval.video.findings=0
eval.narration.score=0.0-1.0
eval.narration.findings=0
eval.narration.unresolved_entries=0
---
```

対応テンプレート: `workflow/state-schema.txt`

Evaluator summary:

- `eval.research.*`
  - research evaluator の run 単位 summary
  - `status` は `approved|changes_requested`
- `eval.script.*`
  - script evaluator の run 単位 summary
- `eval.manifest.*`
  - scene/cut evaluator の run 単位 summary
- `eval.video.*`
  - video generation 後の evaluator summary
- `eval.image_prompt.*`
  - 画像 prompt evaluator の run 単位 summary
  - `score` は average overall score
  - `findings` と `unresolved_entries` は gate 状況の把握用
  - `rubric.*` に criterion average を持てる
- `eval.narration.*`
  - ナレーション evaluator の run 単位 summary
  - `rubric.tts_readiness` / `story_role_fit` / `anti_redundancy` / `pacing_fit` / `spoken_japanese` を持てる

派生物（machine-facing）:

```
output/<topic>_<timestamp>/run_status.json
```

- `state.txt` の flat / nested view
- artifact inventory
- pending gate
- `eval_report.json`（あれば埋め込む）

### 1.1 `status` と `stage.*.status` の役割分担

- `status`
  - 粗い現在地を示す
  - `RESEARCH` / `STORY` / `SCRIPT` / `VIDEO` / `QA` / `DONE`
- `stage.<name>.status`
  - 実務上の完了状況を示す
  - `state.txt` を見るだけで「調査済み」「ナレーション済み」「render 済み」が読める粒度
  - `awaiting_approval` は「作業自体は終わったが、ユーザー承認待ちで次工程に進めない」を意味する

標準 stage:

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

各 stage は少なくとも次の key を持てる:

```text
stage.<name>.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.<name>.started_at=ISO8601
stage.<name>.finished_at=ISO8601
```

承認待ちが標準発生する stage:

- `stage.script`
- `stage.image_generation`
- `stage.narration`

この 3 つが `awaiting_approval` の間は、**次のフローに進んではならない**。

対応 gate / review:

- `stage.script` → `gate.script_review` / `review.script.*`
- `stage.image_generation` → `gate.image_review` / `review.image.*`
- `stage.narration` → `gate.narration_review` / `review.narration.*`

### 1.2 読み方

例えば最新 block が次なら、`state.txt` だけで状況が分かる。

```text
status=VIDEO
stage.research.status=done
stage.story.status=done
stage.script.status=awaiting_approval
review.script.status=pending
gate.script_review=required
```

この場合は:

- 調査は終わった
- 物語は終わった
- 台本作成は終わった
- ただしユーザー承認待ち
- まだナレーションや render に進めない

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

### 4.4 Stage evaluator contracts

- `research.md.evaluation_contract`
  - `target_questions`
  - `must_cover`
  - `must_resolve_conflicts`
  - `done_when`
- `script.md.evaluation_contract`
  - `target_arc`
  - `must_cover`
  - `must_avoid`
  - `done_when`
  - `reveal_constraints`
- `video_manifest.md.scenes[].cuts[].scene_contract`
  - `target_beat`
  - `must_show`
  - `must_avoid`
  - `done_when`
- `video_manifest.md.quality_check.review_contract`
  - `target_outcome`
  - `must_have_artifacts`
  - `must_avoid`
  - `done_when`

### 4.5 Stage evaluator rubric families

- research
  - `source_grounding`
  - `coverage`
  - `conflict_readiness`
  - `structure_readiness`
  - `scene_mapping`
- script
  - `arc_coverage`
  - `scene_specificity`
  - `reference_grounding`
  - `anti_todo`
  - `production_readiness`
- manifest(scene/cut)
  - `beat_clarity`
  - `visual_specificity`
  - `continuity_readiness`
  - `narration_alignment`
  - `production_readiness`
- video
  - `render_integrity`
  - `asset_completeness`
  - `review_readiness`
  - `audio_packaging`
  - `publish_readiness`

---

## 5. `image_generation.review` contract

画像生成前 gate の review 状態は `video_manifest.md` の各 renderable image node に直接保持する。派生の `prompt_collection` は正本ではない。

各 `scenes[].image_generation.review` または `scenes[].cuts[].image_generation.review` は、少なくとも次の review field を持つ。

```yaml
contract:
  target_focus: "character|relationship|setpiece|blocking|environment"
  must_include: []
  must_avoid: []
  done_when: []
agent_review_ok: true|false
agent_review_reason_keys: []
rubric_scores: {}
overall_score: 0.0-1.0
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
- `rubric_scores`
  - criterion score
  - canonical 軸は `story_alignment` / `subject_specificity` / `prompt_craft` / `continuity_readiness` / `production_readiness`
- `overall_score`
  - rubric score の加重合計
  - 単独では gate にせず、criterion 単位の弱点把握に使う
- `human_review_ok`
  - 人間が finding を理解したうえで例外許容した記録
  - subagent finding 自体の解消を意味しない
- `human_review_reason`
  - 人間 override の理由
  - `human_review_ok: true` のときは必須

Canonical reason key:

- `source_anchor_missing_from_prompt`
- `missing_character_id`
- `missing_object_id`
- `prompt_only_local_mismatch`
- `prompt_missing_expected_character_anchor`
- `prompt_missing_expected_object_anchor`
- `prompt_subject_drift`
- `blocking_drift`
- `missing_required_prompt_block`
- `prompt_not_self_contained`
- `non_japanese_prompt_term`
- `prompt_mentions_character_but_character_ids_empty`
- `image_contract_missing`
- `image_contract_must_include_unmet`
- `image_contract_must_avoid_violated`
- `image_contract_target_focus_unmet`
- `image_prompt_story_alignment_weak`
- `image_prompt_subject_specificity_weak`
- `image_prompt_continuity_weak`
- `image_prompt_production_readiness_weak`

Lifecycle:

1. subagent が不足を検出した node を `agent_review_ok: false` にする
2. subagent が `agent_review_reason_keys` を残す
3. fix を source manifest に反映する
4. subagent が再 review し、解消済み node を `agent_review_ok: true` に戻す
5. なお未解消 finding を人間判断で許容する場合だけ `human_review_ok: true` と `human_review_reason` を記録する

Image contract:

- `target_focus`
  - その cut で evaluator が最優先で読む軸
  - `character|relationship|setpiece|blocking|environment`
- `must_include`
  - prompt に必ず含める anchor
- `must_avoid`
  - prompt に入れてはいけない drift source
- `done_when`
  - 生成前に満たしたい具体条件

Required prompt blocks:

- `[全体 / 不変条件]`
- `[登場人物]`
- `[小道具 / 舞台装置]`
- `[シーン]`
- `[連続性]`
- `[禁止]`

subagent review は上記 6 block を必須 criterion とする。1 つでも欠けていれば `agent_review_ok: false` とし、`missing_required_prompt_block` を reason key に含める。

---

## 6. `audio.narration.review` contract

音声生成前 gate の review 状態は `video_manifest.md` の各 renderable narration node に直接保持する。

各 narration node は review の前提として `audio.narration.contract` を持てる。

```yaml
contract:
  target_function: "opening_setup|middle_complication|ending_resolution|time|causality|inner_state|viewpoint|rule|meaning"
  must_cover: []
  must_avoid: []
  done_when: []
```

各 `scenes[].audio.narration.review` または `scenes[].cuts[].audio.narration.review` は、少なくとも次の review field を持つ。

```yaml
agent_review_ok: true|false
agent_review_reason_keys: []
agent_review_reason_messages: []
human_review_ok: true|false
human_review_reason: ""
rubric_scores: {}
overall_score: 0.0-1.0
```

Semantics:

- `agent_review_ok`
  - narration text / tts_text が gate を満たしているかを subagent が判定した結果
  - 未修正の finding がある間は `false`
- `agent_review_reason_keys`
  - `agent_review_ok: false` の理由 key
  - false のときは空にしない
  - fix 後に subagent が `true` に戻したら空配列でよい
- `agent_review_reason_messages`
  - false 理由の短い説明
- `human_review_ok`
  - 人間が finding を理解したうえで例外許容した記録
  - subagent finding 自体の解消を意味しない
- `human_review_reason`
  - 人間 override の理由
  - `human_review_ok: true` のときは必須
- `rubric_scores`
  - criterion ごとの score
- `overall_score`
  - weighted overall score

Canonical reason key:

- `narration_contract_missing`
- `narration_contract_must_cover_unmet`
- `narration_contract_must_avoid_violated`
- `narration_contract_target_function_unmet`
- `narration_empty`
- `narration_tts_text_missing`
- `narration_text_not_hiragana_only`
- `tts_text_not_hiragana_only`
- `narration_contains_meta_marker`
- `tts_unfriendly_literal`
- `unsupported_audio_tag_for_v2`
- `needs_text_normalization`
- `sentence_too_long_for_tts`
- `missing_pause_punctuation`
- `visual_direction_leaked_into_narration`
- `narration_story_role_mismatch`
- `narration_too_visual_redundant`
- `narration_pacing_mismatch`
- `narration_spoken_japanese_weak`

Lifecycle:

1. subagent が narration text を review し、finding がある node を `agent_review_ok: false` にする
2. subagent が `agent_review_reason_keys` / `agent_review_reason_messages` を残す
3. fix を source manifest に反映する
4. subagent が再 review し、解消済み node を `agent_review_ok: true` に戻す
5. なお未解消 finding を人間判断で許容する場合だけ `human_review_ok: true` と `human_review_reason` を記録する
