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

- `assets.character_bible[]`（人物の参照画像 + 不変条件）
- `assets.character_bible[].reference_variants[]`（optional）
  - `variant_id`
  - `reference_images: [string, ...]`
  - `fixed_prompts: [string, ...]`（optional）
- `assets.style_guide`（スタイル/禁止/参照）
- `assets.object_bible[]`（主役級アイテム/舞台装置の参照画像 + 不変条件）
  - `assets.object_bible[].reference_variants[]`（optional, character と同型）
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
