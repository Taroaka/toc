# Data Contracts (MVP)

本書は `todo.txt` の 6) Data contracts を具体化する。

変更内容:
- production order を audio-first へ切り替え、固定 workflow の後半を `narration -> asset -> scene_implementation -> video_generation -> render -> qa` に再編した。
- `video_manifest.md` に `manifest_phase: skeleton|production` を追加した。

修正理由:
- 実 TTS 秒数だけが最終尺の正本であり、asset / scene / video をその後ろに置く方が duration drift に強いため。

旧仕様との差分:
- 旧 contract は `image_prompt` を公開 stage とし、audio stage は後段だった。
- 新 contract では `scene_implementation` を公開 stage とし、audio-first を前提にする。

## 0. Core Terms / Glossary

この repo では、物語上の単位、生成実行の単位、設計書の単位を混同しない。

- `scene` / シーン
  - 物語上のまとまり。1つの出来事、場所、感情変化、または段落を表す。
  - 例: 「亀を助ける」「竜宮城に着く」「故郷に戻る」。
  - `script.md.scenes[]` と `video_manifest.md.scenes[]` の基本単位。
- `cut` / カット
  - scene を映像として実装するための小単位。
  - 1つの画、短い動き、反応、間、transition、または narration beat を担う。
  - cut の枠は script / skeleton manifest で作り、production manifest で image / audio / video の実行情報を持つ。
  - cut は `audio`, `image_generation`, `video_generation`, `scene_contract` などの部品を束ねる統合単位であり、audio そのものとは別概念。
- `audio` / 音声
  - cut または scene に属する narration runtime。
  - `tts_text`, voice, prompt contract, generated audio path, actual duration を持つ。
  - 概念上は cut の部品だが、実 TTS 秒数が後続の video duration / hold / render を決めるため、stage としては p500 / narration で先に確定する。
- `visual`
  - cut または scene が画として何を伝えるかを表す設計領域。
  - `visual_beat`, `scene_contract`, `image_generation`, `still_image_plan`, `reference_usage` などを含む。
  - visual planning stage では、cut prompt そのものではなく、visual identity / scene visual value / anchor / reference strategy を決める。
- `asset`
  - 複数 cut / scene で visual identity を固定するための再利用可能な素材。
  - character, object, location, reusable still を含む。
  - 単発 cut の便利画像ではなく、continuity anchor として扱う。
- `design document` / 設計書
  - 生成物を直接作るファイルではなく、後続 stage が迷わないための仕様・判断基準・契約。
  - 例: `visual_value.md`, `asset_plan.md`, `video_manifest.md`, `docs/*`, `workflow/*`。
  - run artifact の設計書は、その stage の source of truth または handoff として扱う。
- `manifest`
  - 実行可能な生成契約。
  - `video_manifest.md` は scene / cut / audio / image / video / asset reference を materialize し、生成スクリプトが読む正本。
- `render unit`
  - 最終 video request / clip list に載る動画単位。
  - 複数 cut を1つの動画として生成・連結したい場合、scene の `render_units[]` が cut 群を束ねる。

責務の関係:

```text
Scene
  Cut
    audio: narration runtime and actual duration
    visual: image prompt, still plan, references, visual contract
    video: motion prompt, duration, generated clip
  RenderUnit(optional): one generated video unit that can bundle multiple cuts
```

標準順序:

- p300 visual planning: cut を作る前に、visual identity / visual value / anchor / reference strategy を決める。
- p400 script: scene / cut skeleton と narration / tts_text を作る。
- p500 narration: cut audio を生成し、実 duration を確定する。
- p600 asset: cut で使う reusable asset / reference を設計・生成する。
- p700 scene implementation: audio duration と asset references を使って cut の image / video 実装を作る。
- p800/p900 video/render: render unit / clip list / final render を作る。

## 1. State schema（ジョブ状態）

`docs/orchestration-and-ops.md` のマニフェストを最小化し、
**テキスト（key=value）で状態を管理**する。

状態ファイルはプロジェクトフォルダに置く：

```
output/<topic>_<timestamp>/state.txt
```

人間向けの run navigation は別に持つ：

```
output/<topic>_<timestamp>/p000_index.md
```

更新方式は **追記型**（最新のブロックが現在状態）。

```text
timestamp=ISO8601
job_id=JOB_YYYY-MM-DD_0001
topic=string
status=INIT|RESEARCH|STORY|SCRIPT|VIDEO|QA|DONE
stage.research.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.research.grounding.status=ready|missing_docs|missing_inputs
stage.research.grounding.report=logs/grounding/research.json
stage.research.readset.report=logs/grounding/research.readset.json
stage.research.audit.status=passed|failed
stage.research.audit.report=logs/grounding/research.audit.json
stage.research.subagent.prompt=logs/grounding/research.subagent_prompt.md
stage.research.playbooks.report=logs/grounding/research.playbooks.json
stage.research.playbooks.selected_count=0
stage.story.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.story.grounding.status=ready|missing_docs|missing_inputs
stage.story.grounding.report=logs/grounding/story.json
stage.story.readset.report=logs/grounding/story.readset.json
stage.story.audit.status=passed|failed
stage.story.audit.report=logs/grounding/story.audit.json
stage.story.subagent.prompt=logs/grounding/story.subagent_prompt.md
stage.story.playbooks.report=logs/grounding/story.playbooks.json
stage.story.playbooks.selected_count=0
review.story.status=pending|approved|changes_requested
review.story.subagent.prompt=logs/review/story.subagent_prompt.md
review.story.subagent.prompt.generated_at=ISO8601
eval.story.loop.status=pending|running|passed|changes_requested|failed
eval.story.loop.max_rounds=5
eval.story.loop.current_round=0
eval.story.loop.final_report=story_review.md
eval.story.loop.round_01.critic_1=logs/eval/story/round_01/critic_1.md
eval.story.loop.round_01.critic_1_prompt=logs/eval/story/round_01/prompts/critic_1.prompt.md
eval.story.loop.round_01.critic_5=logs/eval/story/round_01/critic_5.md
eval.story.loop.round_01.critic_5_prompt=logs/eval/story/round_01/prompts/critic_5.prompt.md
eval.story.loop.round_01.aggregated_review=logs/eval/story/round_01/aggregated_review.md
stage.script.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.script.grounding.status=ready|missing_docs|missing_inputs
stage.script.grounding.report=logs/grounding/script.json
stage.script.readset.report=logs/grounding/script.readset.json
stage.script.audit.status=passed|failed
stage.script.audit.report=logs/grounding/script.audit.json
stage.script.subagent.prompt=logs/grounding/script.subagent_prompt.md
stage.script.playbooks.report=logs/grounding/script.playbooks.json
stage.script.playbooks.selected_count=0
stage.narration.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.narration.grounding.status=ready|missing_docs|missing_inputs
stage.narration.grounding.report=logs/grounding/narration.json
stage.narration.readset.report=logs/grounding/narration.readset.json
stage.narration.audit.status=passed|failed
stage.narration.audit.report=logs/grounding/narration.audit.json
stage.narration.subagent.prompt=logs/grounding/narration.subagent_prompt.md
stage.narration.playbooks.report=logs/grounding/narration.playbooks.json
stage.narration.playbooks.selected_count=0
stage.asset.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.asset.grounding.status=ready|missing_docs|missing_inputs
stage.asset.grounding.report=logs/grounding/asset.json
stage.asset.readset.report=logs/grounding/asset.readset.json
stage.asset.audit.status=passed|failed
stage.asset.audit.report=logs/grounding/asset.audit.json
stage.asset.subagent.prompt=logs/grounding/asset.subagent_prompt.md
stage.asset.playbooks.report=logs/grounding/asset.playbooks.json
stage.asset.playbooks.selected_count=0
stage.scene_implementation.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.render.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.scene_implementation.grounding.status=ready|missing_docs|missing_inputs
stage.scene_implementation.grounding.report=logs/grounding/scene_implementation.json
stage.scene_implementation.readset.report=logs/grounding/scene_implementation.readset.json
stage.scene_implementation.audit.status=passed|failed
stage.scene_implementation.audit.report=logs/grounding/scene_implementation.audit.json
stage.scene_implementation.subagent.prompt=logs/grounding/scene_implementation.subagent_prompt.md
review.image_prompt.subagent.prompt=logs/review/image_prompt.subagent_prompt.md
stage.scene_implementation.playbooks.report=logs/grounding/scene_implementation.playbooks.json
stage.scene_implementation.playbooks.selected_count=0
stage.video_generation.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.video_generation.grounding.status=ready|missing_docs|missing_inputs
stage.video_generation.grounding.report=logs/grounding/video_generation.json
stage.video_generation.readset.report=logs/grounding/video_generation.readset.json
stage.video_generation.audit.status=passed|failed
stage.video_generation.audit.report=logs/grounding/video_generation.audit.json
stage.video_generation.subagent.prompt=logs/grounding/video_generation.subagent_prompt.md
stage.video_generation.playbooks.report=logs/grounding/video_generation.playbooks.json
stage.video_generation.playbooks.selected_count=0
gate.research_review=required|optional|skipped
gate.story_review=required|optional|skipped
gate.script_review=required|optional|skipped
gate.image_review=required|optional|skipped
gate.narration_review=required|optional|skipped
gate.video_review=required|optional|skipped
review.policy.story=required|optional
review.policy.image=required|optional
review.policy.narration=required|optional
artifact.research=output/<topic>_<timestamp>/research.md
artifact.research_review=output/<topic>_<timestamp>/research_review.md
artifact.story=output/<topic>_<timestamp>/story.md
artifact.story_review=output/<topic>_<timestamp>/story_review.md
artifact.visual_value=output/<topic>_<timestamp>/visual_value.md
artifact.script=output/<topic>_<timestamp>/script.md
artifact.script_review=output/<topic>_<timestamp>/script_review.md
artifact.asset_plan=output/<topic>_<timestamp>/asset_plan.md
artifact.manifest_review=output/<topic>_<timestamp>/manifest_review.md
artifact.video=output/<topic>_<timestamp>/video.mp4
artifact.video_review_report=output/<topic>_<timestamp>/video_review.md
artifact.grounding.research=output/<topic>_<timestamp>/logs/grounding/research.json
artifact.grounding.story=output/<topic>_<timestamp>/logs/grounding/story.json
artifact.grounding.script=output/<topic>_<timestamp>/logs/grounding/script.json
artifact.grounding.narration=output/<topic>_<timestamp>/logs/grounding/narration.json
artifact.grounding.asset=output/<topic>_<timestamp>/logs/grounding/asset.json
artifact.grounding.scene_implementation=output/<topic>_<timestamp>/logs/grounding/scene_implementation.json
artifact.grounding.video_generation=output/<topic>_<timestamp>/logs/grounding/video_generation.json
artifact.grounding.playbooks.research=output/<topic>_<timestamp>/logs/grounding/research.playbooks.json
artifact.grounding.playbooks.story=output/<topic>_<timestamp>/logs/grounding/story.playbooks.json
artifact.grounding.playbooks.script=output/<topic>_<timestamp>/logs/grounding/script.playbooks.json
artifact.grounding.playbooks.narration=output/<topic>_<timestamp>/logs/grounding/narration.playbooks.json
artifact.grounding.playbooks.asset=output/<topic>_<timestamp>/logs/grounding/asset.playbooks.json
artifact.grounding.playbooks.scene_implementation=output/<topic>_<timestamp>/logs/grounding/scene_implementation.playbooks.json
artifact.grounding.playbooks.video_generation=output/<topic>_<timestamp>/logs/grounding/video_generation.playbooks.json
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

### 1.0 Authoring-after evaluator-improvement loop

Authoring の直後に置かれる review slot は、一回限りの採点ではなく **最大 5 round の evaluator-improvement loop** として扱う。

対象 slot:

- `p130`: research authoring 後の review
- `p230`: story authoring 後の review
- `p320`: visual planning authoring 後の review
- `p430`: script authoring 後の review
- `p520`: narration text authoring 後の review
- `p640`: asset plan authoring 後の review
- `p730` / `p740`: scene implementation authoring 後の hard review / judgment review
- `p820` / `p850`: motion / video authoring 後の review
- `p930`: final QA / runtime summary 後の review

各 round の構成:

- critic agent: 5 agents
  - それぞれ独立に同じ canonical artifact と stage readset を読み、rubric finding を出す
  - critic は canonical artifact、`state.txt`、`p000_index.md` を直接編集しない
- aggregator: 1 agent
  - 5 critic outputs を統合し、重複排除、severity、採用すべき修正方針、次 round の pass/fail をまとめる
  - aggregator も canonical artifact を直接編集しない
- orchestrator / main agent:
  - aggregator report から採用する修正を選び、canonical artifact に反映する single writer
  - 修正後、同じ review slot の次 round を実行する

停止条件:

- aggregator が `passed` を返したら loop を終了し、対応 stage を次 slot へ進める
- aggregator が `changes_requested` を返し、round < 5 なら orchestrator が修正して次 round を実行する
- round 5 後も `changes_requested` なら `eval.<stage>.loop.status=changes_requested` とし、human review / explicit override なしに次工程へ進めない

state key pattern:

```text
eval.<stage>.loop.status=pending|running|passed|changes_requested|failed
eval.<stage>.loop.max_rounds=5
eval.<stage>.loop.current_round=0-5
eval.<stage>.loop.final_report=<stage>_review.md
eval.<stage>.loop.round_01.critic_1=logs/eval/<stage>/round_01/critic_1.md
eval.<stage>.loop.round_01.critic_1_prompt=logs/eval/<stage>/round_01/prompts/critic_1.prompt.md
eval.<stage>.loop.round_01.critic_5=logs/eval/<stage>/round_01/critic_5.md
eval.<stage>.loop.round_01.critic_5_prompt=logs/eval/<stage>/round_01/prompts/critic_5.prompt.md
eval.<stage>.loop.round_01.aggregator_prompt=logs/eval/<stage>/round_01/prompts/aggregator.prompt.md
eval.<stage>.loop.round_01.aggregated_review=logs/eval/<stage>/round_01/aggregated_review.md
```

`eval.<stage>.*` summary は loop の最新 round / aggregator 結果から更新する。critic 個別 report は根拠 artifact、aggregator report は gate 判定の正本、canonical artifact の最終差分は orchestrator の編集を正本とする。

`video_manifest.md` top-level contract:

```text
manifest_phase=skeleton|production
```

- `skeleton`: narration review / TTS / duration gate に必要な最小構造
- `production`: image / video 実装 field を持つ生成正本

対応テンプレート: `workflow/state-schema.txt`

grounding 契約の正本:

- `workflow/stage-grounding.yaml`
- `scripts/resolve-stage-grounding.py`
- `scripts/select-stage-playbooks.py`

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

### 1.0.1 Run navigation index

`p000_index.md` は run 直下の人間向け入口で、少なくとも次を含む。

- current stage
- next required human review
- stage table
- current run inventory
- file-to-stage mapping

`current_position` は現在の stage / runtime progress を示す。未承認の human review gate が残っている場合も、進行中の stage を上書きせず、`next_required_human_review` と `pending_gates` に分けて表示する。

番号運用は navigation layer だが、slot contract は固定である。

- `100` 番台ごとに大工程を割り当てる
- `10` 番台刻みは fixed slot contract の一部として扱う
- `p000_index.md` は fixed slot contract に基づく run progress の source of truth
- 第1段階では `assets/**`, `logs/**`, `scratch/**` を rename しない
- narration は
  - `p400`: narration draft / `tts_text` / script review / human changes / skeleton manifest materialization
  - `p500`: TTS 実行 / duration fit gate / audio runtime handoff
  に分けて扱う

### 1.0.2 Fixed p-slot workflow contract

Canonical p300 requirements live in this section. Other docs may summarize p300, but this section is the source of truth for what `visual_value.md` must contain and what p300 must not produce.

`p100` から `p900` までの slot 意味は、すべての story で共通の固定契約とする。story ごとの差分は slot の意味を変えるのではなく、各 slot の状態と要件で表現する。

各 slot は次の generic keys を持つ。

```text
slot.pXXX.status=pending|in_progress|awaiting_approval|done|failed|skipped
slot.pXXX.requirement=required|optional
slot.pXXX.skip_reason=string
slot.pXXX.note=string
slot.pXXX.review_loop.status=pending|running|passed|changes_requested|failed
slot.pXXX.review_loop.current_round=0-5
```

固定 slot の意味:

- `p100`: research
- `p200`: story
- `p300`: visual planning
  - `visual_value.md` を正本として、cut 作成前に visual identity / scene visual value / anchor / reference strategy / asset candidates / regeneration risks / downstream handoff を決める
- `p400`: script / narration draft / human changes
- `p500`: narration / audio runtime
- `p600`: asset
- `p700`: scene implementation
- `p800`: video
- `p900`: render / QA / runtime

stage target resolution:

- `p100` / `100` / `research` -> `p130` research review handoff
- `p200` / `200` / `story` -> `p230` story review handoff
- `p300` / `300` / `visual_value` -> `p330` visual planning handoff
- `p400` / `400` -> `p450` script handoff / skeleton manifest materialization
- `p500` / `500` / `narration` -> `p570` audio QA / human review handoff
- `p600` / `600` / `asset` -> `p680` asset continuity / human review handoff
- `p700` / `700` / `scene_implementation` -> `p750` generation-ready handoff
- `p800` / `800` / `video_generation` -> `p850` video review / exclusions handoff
- `p900` / `900` / `render` / `video` -> `p930` final QA / runtime handoff

100 番台の coarse p-number target は stage 開始 slot ではなく、対応 stage の human-review handoff slot まで進める。細番号 target（例: `p450`）はその slot を直接指す。

運用ルール:

- story 固有の差分は `slot.pXXX.status` / `slot.pXXX.requirement` / `slot.pXXX.skip_reason` / `slot.pXXX.note` にのみ載せる
- slot の意味や順序を story ごとに変更しない
- `p000_index.md` はこの固定 slot contract を run progress の正本として要約する
- `p800` は個別 clip / scene compile の生成までを担い、最終結合前に全 scene compile の audio/video stream を正規化できる状態で終える
- `p900` は最終 render / QA の責務として、scene compile をそのまま `concat -c copy` しない。最終結合前に全 scene compile を同一仕様へ正規化する
  - video: `1280x720` または run の target size、`24fps`、`yuv420p`
  - audio: `AAC`, `44100Hz`, `stereo`
  - 理由: `mono -> stereo` など channel layout が途中で変わると、concat 境界以降でジャミング音・ノイズ化が発生するため

Canonical p300 done 条件:

- `visual_value.md` が存在する
- 主要 story scene に `scene_visual_values[]` の coverage がある
- `asset_bible_candidates` が列挙されている
- `anchor_cut_candidates` が列挙されている
- `reference_strategy` がある
- `regeneration_risks[]` がある
- `handoff_to_p400_p600_p700` がある
- 本番 cut prompt、画像生成 request、asset 画像、動画 motion prompt を p300 で作っていない

### 1.1 `status` と `stage.*.status` の役割分担

- `status`
  - 粗い現在地を示す
  - `RESEARCH` / `STORY` / `SCRIPT` / `VIDEO` / `QA` / `DONE`
- `stage.<name>.status`
  - 実務上の完了状況を示す
  - `state.txt` を見るだけで「調査済み」「ナレーション済み」「render 済み」が読める粒度
  - `awaiting_approval` は「作業自体は終わったが、ユーザー承認待ちで次工程に進めない」を意味する

canonical generation stage と p-slot stage の扱い:

- canonical production / generation stage は `research`, `story`, `script`, `narration`, `asset`, `scene_implementation`, `video_generation`, `render`, `qa`
- `visual_value` は p300 visual planning を追跡するための stage key / grounding entry であり、画像・動画・asset を生成する canonical generation stage ではない
- `--stage p300|300|visual_value` は `p330` visual planning handoff まで進める同義指定として扱う

標準 stage keys:

- `stage.research`
- `stage.story`
- `stage.visual_value`
- `stage.script`
- `stage.narration`
- `stage.asset`
- `stage.scene_implementation`
- `stage.video_generation`
- `stage.render`
- `stage.qa`

各 stage は少なくとも次の key を持てる:

```text
stage.<name>.status=pending|in_progress|awaiting_approval|done|failed|skipped
stage.<name>.started_at=ISO8601
stage.<name>.finished_at=ISO8601
stage.<name>.grounding.status=ready|missing_docs|missing_inputs
stage.<name>.grounding.report=logs/grounding/<stage>.json
stage.<name>.readset.report=logs/grounding/<stage>.readset.json
stage.<name>.audit.status=passed|failed
stage.<name>.audit.report=logs/grounding/<stage>.audit.json
stage.<name>.subagent.prompt=logs/grounding/<stage>.subagent_prompt.md
review.image_prompt.subagent.prompt=logs/review/image_prompt.subagent_prompt.md
slot.pXXX.status=pending|in_progress|done|skipped|blocked|awaiting_approval|failed
slot.pXXX.requirement=required|optional
slot.pXXX.skip_reason=string
slot.pXXX.note=string
```

asset stage を分ける場合は次を追加する。

- `stage.asset_plan_review`
- `stage.asset_generation`

承認待ちが標準発生する stage:

- `stage.script`
- `stage.asset_generation`
- `stage.narration`
- `stage.scene_implementation`

この 4 つが `awaiting_approval` の間は、**次のフローに進んではならない**。

対応 gate / review:

- `stage.script` → `gate.script_review` / `review.script.*`
- `stage.asset_generation` → `gate.asset_review` / `review.asset.*`
- `stage.scene_implementation` → `gate.image_review` / `review.image.*`
- `stage.narration` → `gate.narration_review` / `review.narration.*`

grounding ルール:

- stage は開始前に `scripts/resolve-stage-grounding.py` を実行して required docs / templates / inputs を解決する
- 直後に `scripts/audit-stage-grounding.py` を実行して readset / audit を確定する
- `stage.<name>.grounding.status=ready` と `stage.<name>.audit.status=passed` を確認できない限り、当該 stage は開始しない
- artifact が存在しても grounding report が欠けていれば verifier / evaluator は fail にできる
- `requires_approved_input` は `workflow/stage-grounding.yaml` を正本とし、`review.policy.*=optional` の run では対象 review gate を skip できる

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
- `workflow/asset-plan-template.yaml`
- `workflow/scene-outline-template.yaml`（story → 画像/動画生成の橋渡し。未知トピックでモデル記憶に依存しないための asset brief）
- `workflow/stage-grounding.yaml`（stage ごとの必須参照契約）

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

### 4.5 `script.md` と `video_manifest.md` の正本境界

境界は次で固定する。

- `script.md`
  - 物語と映像意図の正本
  - `scene_summary`, `visual_beat`, reveal, `narration`, `tts_text`, human review 指示を持つ
- `video_manifest.md`
  - image/video/audio generation の実装正本
  - `scene_contract`, `image_generation`, `still_assets[]`, `reference_usage[]`, `video_generation` を持つ
  - human review の理由本文は持たず、`applied_request_ids[]` と `implementation_trace` で trace を持つ
  - optional `render_units[]` を持てる
    - `render_units[]` は最終 render 用の動画クリップ単位
    - `unit_id`, `source_cut_ids[]`, `video_generation` を持つ
    - scene に `render_units[]` がある場合、最終 render の動画正本は cut ではなく render unit 側を使う

generator の読み順:

- image generation
  1. `video_manifest.md`
  2. `script.md`
  3. narration は補助参照
- video generation
  1. `video_manifest.md`
  2. `script.md`
  3. narration は補助参照

制約:

- `audio.narration.tts_text` は TTS 専用字段
- `tts_text` を image/video generation の主ソースにしてはならない
- `approved_image_notes[]` / `approved_video_notes[]` / `human_change_requests[]` は `script.md` に保持し、生成前に `video_manifest.md` へ materialize する
- materialize された `image_generation_requests.md` / `video_generation_requests.md` は review artifact として `source_requests` metadata を含んでよい
- story cut の `video_generation` 採否は human review 正本に従う
  - `delete_scene` / `delete_cut` で消されていない cut は既定で `video_generation` を持つ
  - `still_image_plan.mode` は image planning 用であり、動画 cut の削除理由には使わない
  - ただし scene に `render_units[]` がある場合、非 deleted cut はどれか 1 つの render unit にちょうど 1 回だけ含まれることを正とする
  - `video_generation_requests.md` は render unit selector を出力してよい

### 4.6 `asset_plan.md`（asset stage 正本）

画像生成の stage 1 では、`video_manifest.md` の前段として `asset_plan.md` を持てる。

- 目的
  - reusable asset の設計・review・承認
- 入力
  - `script.md`
  - `story.md`
  - 必要なら `video_manifest.md.assets.*`
- 出力
  - `assets/characters/*`
  - `assets/objects/*`
  - `assets/locations/*`
  - reusable `assets/scenes/*`

最低限の top-level:

- `asset_plan_metadata`
- `review_contract`
- `assets.characters[]`
- `assets.objects[]`
- `assets.locations[]`
- `assets.reusable_stills[]`

各 asset entry の必須 field:

- `asset_id`
- `asset_type`
- `source_script_selectors[]`
- `story_purpose`
- `visual_spec`
- `generation_plan`
- `creation_status`
- `existing_outputs[]`
- `review`

`generation_plan` の追加 field:

- `execution_lane: standard|bootstrap_builtin`
- `bootstrap_allowed: true|false`
- `bootstrap_reason: no_reference_seed|other`

asset stage の character variant ルール:

- 同一人物の variant は、必ず main の `character_reference` を基準参照にする
- `generation_plan.reference_inputs[]` には main reference の front / side / back などを入れる
- `generation_plan.derived_from_asset_id` で、どの main asset から派生するかを明示する
- 例: `urashima_old` は `urashima` から派生し、別人として新規設計しない

bootstrap lane ルール:

- `reference_inputs[]` が空で、かつ `bootstrap_allowed=true` の asset だけ `execution_lane=bootstrap_builtin` にできる
- `reference_inputs[]` が 1 件以上ある asset は常に `execution_lane=standard`
- `derived_from_asset_id` がある asset は常に `execution_lane=standard`
- `bootstrap_builtin` という lane 名は互換のため維持するが、repo 全体では「no-reference built-in image lane」を意味する
- したがって asset stage だけでなく、cut image stage の materialized request でも `reference_count == 0` なら `execution_lane=bootstrap_builtin` を使う
- bootstrap 生成物は human review の `review.status=approved` になるまで canonical 扱いにしない
- 承認後は、そのまま canonical asset として `existing_outputs[]` に記録してよい

asset stage の location / still variant ルール:

- 同じ場所の昼夜差分、現在/未来差分、状態違いは、main の `location_anchor` または `reusable_still` を基準に派生させる
- `generation_plan.reference_inputs[]` には main anchor を入れる
- `generation_plan.derived_from_asset_id` で、どの base location / still から派生するかを明示する
- 例: `scene15_cut03_night_anchor` は `scene15_cut03_day_anchor` から派生する
- 例: `future beach` が `present beach` の時間差分である場合は、同一ロケーションの base anchor から派生させる

`source_script_selectors[]` と `generation_plan.reference_inputs[]` は意味が違う:

- `source_script_selectors[]`
  - その asset が物語上どこで使われるか
  - 生成時の参照画像を意味しない
- `generation_plan.reference_inputs[]`
  - 生成時に本当に参照する既存 visual source
  - 同一人物 variant、同一場所の状態差分、same-camera 派生のときだけ使う
- つまり、scene/cut で使われるからといって、その scene still を location asset の `reference_inputs[]` に入れてよいわけではない

location の例外ルール:

- 同じ建物の中でも、物語上は別エリアとして扱う場所は `derived_from_asset_id` で派生させなくてよい
- 例: 竜宮城の宴会エリアと、その手前の foyer は別 `location_anchor` にしてよい
- 独立した location anchor は `reference_inputs: []` を基本にする
- 例: `clock_museum` は終盤の独立空間であり、浜辺や別ロケーションの参照を不要とする
- ただし、別エリアから主エリアが見える、遠景にだけ映る、背景としてだけ存在する場合は `reference_usage[]` で参照関係を残す
- この場合の典型は `mode: background_glimpse` または `mode: foreground_anchor`
- つまり `derived_from` は「同じ場所の状態差分」、`reference_usage` は「別の場所から見える/一部だけ参照する」の表現に使い分ける

運用:

- asset stage document は human review を通してから asset 生成へ進む
- character asset は front / side / back 等の既存 multi-view 運用を維持する
- object / location / setpiece / reusable still は単体 still を基本にする
- asset を作る主目的は、複数 cut で使う visual identity を固定し、同一 cut 内の関連 asset 派生も含めて continuity を守ること
- したがって asset contract は reuse と continuity を優先し、単発 cut 専用画像を増やすためには使わない
- 例外的に既存 scene still を asset へ昇格することはあるが、それは移行中 run の互換措置であり、標準フローではない
- provider 実行直前に request file を materialize する
  - asset stage: `artifact.asset_generation_requests`
  - cut image stage: `artifact.image_generation_requests`
  - video stage: `artifact.video_generation_requests`
- request file は selector ごとの final prompt / references / output を記録し、人レビューの対象にできる
  - scene に `render_units[]` がある場合、video request file は cut ではなく render unit selector を出し、review metadata として `source_cuts` を併記してよい
- asset request file では、review 用 metadata として少なくとも次を見えるようにする
  - `asset_id`
  - `asset_type`
  - `execution_lane`
  - `reference_count`
  - `output`（canonical output path）
  - `review.status`
- image request file は review 用に image prompt を持つ全 scene/cut を載せる
  - `still_mode`
  - `generation_status: missing|created|recreate`
  - `plan_source`
  - `execution_lane`
  - `reference_count`
- story から落とした cut は `cut_status: deleted` と `deletion_reason` を残して監査痕跡にする
  - deleted cut は request / image generation / video generation / audio generation / final concat から除外する
  - 除外対象は `generation_exclusion_report.md` と `*_generation_exclusions.md` に記録する
  - `scripts/build-clip-lists.py` は scene に `render_units[]` がある場合、`video_clips.txt` を render unit 単位で、`video_narration_list.txt` を `source_cut_ids[]` の順で作る
- request には prompt 以外の判断材料も十分に残す
  - explicit `references`
  - `character_ids` / `object_ids` / `location_ids` から解決される asset reference
  - つまり request review 時点で「何を参照して作るか」が人間に見えている状態を正とする
- `plan` は AI/実装側の設計用文書、`request` は人間が最終確認する凍結文書として役割を分ける
- 人レビューの既定対象は `request` 側とし、`plan` 側は必要時だけ参照する
- image/video request は stateful な前提を置かない
- 他 cut / 他 scene との関係性は、原則として `references` に入った画像を通してのみ担保する
- request 本文では「参照画像の誰/場所/小道具が、この場面でどう見えるか」を明記する
- `後続する scene` / `前の prompt を引き継ぐ` のような、画像参照を伴わない continuity 指示は request では使わない
- request 本文では `cut` のような運用メタ語を使わない
- 物語に実在する人物 / 場所 / 場面を扱う request では、必要に応じて `物語「<topic>」` の文脈を明示する
- cut stage は既存どおり `video_manifest.md` を使う
- `script.md.human_review_criteria.narration[]`
  - 人間レビュー時の固定観点
- `script.md.script_metadata.ending_mode`（optional）
  - `happy|bittersweet|tragic|cautionary|ambiguous`
- `script.md.scenes[].narration_distance_policy`（optional）
  - `stay_close|contextual|meaning_first`
- `script.md.scenes[].narrative_value_goal`（optional）
  - `mode: immersion|meaning|mixed`
  - `leave_viewer_with: [string, ...]`
- `script.md.script_metadata.elevenlabs`
  - `provider`, `model_id`, `voice_name`, `voice_id`, `prompt_contract_version`, `default_stability_profile`, `text_policy`
  - 再現 baseline は `provider: elevenlabs`, `model_id: eleven_v3`, `voice_name: Shohei - Warm, Clear and Husky`, `voice_id: 8FuuqoKHuM48hIEwni5e`
- `script.md.scenes[].cuts[].elevenlabs_prompt`
  - `spoken_context`, `voice_tags`, `spoken_body`, `stability_profile`
- `script.md.scenes[].cuts[].tts_text`
  - ElevenLabs v3 に渡す final string の正本
  - 通常はひらがな寄せ + `[]` audio tag を許容する
  - 音声品質を優先する cut では、漢字かな交じりの自然な日本語を許可する
  - 締め / 教訓 narration の再現 baseline は `spoken_context: ""`, `voice_tags: ["low", "measured"]`, `stability_profile: "natural"`
  - 採用例は `tts_text: "[low][measured] 知らない世界には、強い引力があります。"`
- `script.md.scenes[].cuts[].human_review`
  - `status`
  - `notes`
  - `change_requests`
  - `approved_narration`
  - `approved_tts_text`
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
  - `story_material_readiness`
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
human_review:
  status: "pending|approved|changes_requested"
  notes: ""
  change_requests: []
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
- `human_review`
  - 通常の human feedback loop の記録
  - `human_review_ok` とは別物
  - `change_requests[]` を持つ場合、個別要求の正本はこちらに置く

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

Hard/soft split:

- 関数 review の hard gate は、missing contract / missing ids / required prompt block 欠落 / reveal 破り / self-contained 違反のような構造的問題を中心に扱う
- `must_avoid` の素朴な文字列一致、`target_focus` の語一致、`production_readiness` の弱さは warning として残してよい
- これらの warning を別コンテキストで評価したい場合は `scripts/build-subagent-image-review-prompt.py` で `logs/review/image_prompt.subagent_prompt.md` を生成し、contextless subagent に judgment review を依頼する

Optional `human_review.change_requests[]` item:

```yaml
- request_id: "hr-001"
  status: "open|accepted|rejected|deferred|resolved"
  category: "story_alignment|reveal|subject_specificity|continuity|craft|other"
  requested_change: ""
  rationale: ""
  proposed_patch: ""
  requested_at: "ISO8601"
  resolved_at: ""
  resolution_notes: ""
```

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
human_review:
  status: "pending|approved|changes_requested"
  notes: ""
  change_requests: []
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
- `human_review`
  - 通常の human review loop の記録
  - narration 文面の source of truth は `script.md` だが、manifest 側にも同期された review 状態を持てる
  - `change_requests[]` は override ではなく修正要求の本文
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
- `narration_contains_meta_marker`
- `tts_unfriendly_literal`
- `needs_text_normalization`
- `sentence_too_long_for_tts`
- `missing_pause_punctuation`
- `visual_direction_leaked_into_narration`
- `narration_story_role_mismatch`
- `narration_too_visual_redundant`
- `narration_pacing_mismatch`
- `narration_spoken_japanese_weak`

Intentional silent cut contract:

```yaml
audio:
  narration:
    tool: "silent"
    text: ""
    tts_text: ""
    silence_contract:
      intentional: true
      kind: "visual_value_hold|transition_hold|reaction_hold|breathing_room|other"
      confirmed_by_human: true
      reason: "映像で見せる価値が大きい追加カット"
```

- `tool: "silent"` だけでは不十分
- renderable cut で narration を空にする場合は `silence_contract` を必須にする
- `confirmed_by_human: true` は、人レビューで「この cut は無音でよい」と確定した印
- 最終連結では、この cut の `video_generation.duration_seconds` 分の無音 mp3 をつなぐ
- audio-only 生成後は `check-audio-duration-gate.py` を通し、`review.duration_fit.status` を更新する
- `cinematic_story` の既定 target は 300 秒で、未達時は次を artifact 化する
  - `logs/review/duration_scene.subagent_prompt.md`
  - `logs/review/duration_narration.subagent_prompt.md`
- 未達時は scene 設計 / narration 設計の見直しを先に行い、人レビューへは進めない

Lifecycle:

1. subagent が narration text を review し、finding がある node を `agent_review_ok: false` にする
2. subagent が `agent_review_reason_keys` / `agent_review_reason_messages` を残す
3. fix を source manifest に反映する
4. subagent が再 review し、解消済み node を `agent_review_ok: true` に戻す
5. なお未解消 finding を人間判断で許容する場合だけ `human_review_ok: true` と `human_review_reason` を記録する

## 7. Script → Manifest narration sync

ナレーション文面の human review 正本は `script.md` とする。

- source: `script.md`
- sink: `video_manifest.md`
- sync target:
  - `audio.narration.text`
  - `audio.narration.tts_text`

script 側の `tts_text` は `elevenlabs_prompt` を materialize した final string として扱う。
この slice では manifest/runtime 側の contract は据え置きだが、script からの sync では
次の優先順位で値を選ぶ。

sync 優先順位:

1. `scenes[].cuts[].human_review.approved_tts_text`
2. `scenes[].cuts[].tts_text`
3. materialized `scenes[].cuts[].elevenlabs_prompt`
4. `scenes[].cuts[].human_review.approved_narration`
5. `scenes[].cuts[].narration`

Narration human review contract:

```yaml
human_review:
  status: "pending|approved|changes_requested"
  notes: ""
  change_requests:
    - request_id: "hr-001"
      status: "open|accepted|rejected|deferred|resolved"
      category: "naturality|reveal|pronunciation|story_alignment|timing|other"
      requested_change: ""
      rationale: ""
      suggested_narration: ""
      suggested_tts_text: ""
      requested_at: "ISO8601"
      resolved_at: ""
      resolution_notes: ""
  approved_narration: ""
  approved_tts_text: ""
```

- `status: changes_requested` のときは `change_requests[]` を空にしない
- `approved_*` は open request を隠すために使わない
- manifest 側の `human_review_ok` は例外許容 override であり、この block の代替ではない
- `elevenlabs_prompt` 用の `approved_*` mirror field は追加しない
- `elevenlabs_prompt` を直した場合は、同じ変更を `tts_text` にも反映する

同期コマンド:

```bash
python scripts/sync-narration-from-script.py \
  --script output/<topic>_<timestamp>/script.md \
  --manifest output/<topic>_<timestamp>/video_manifest.md
```

## 8. Narration distance policy

`narration` と `visual_beat` の距離は固定ルールではなく、scene 文脈で判断する。

- `stay_close`
  - 物語への没入を優先
  - 序盤 / 中盤の標準
- `contextual`
  - close でも meaning add でもよい
  - 終盤の標準
- `meaning_first`
  - 映像のあとに意味が残る一文を優先
  - cautionary / tragic / bittersweet の重要 cut で使いやすい

Evaluator の意図:

- `stay_close` の cut では、`narration` と `visual_beat` が近いこと自体を減点しない
- `contextual` / `meaning_first` の cut では、必要なときだけ映像のあとに意味が残る一文を許可する

## 9. Human review change-request expansion

`script.md` は narration だけでなく visual / asset / image / video 指示を含む human review の正本でもある。

Top-level:

```yaml
human_change_requests:
  - request_id: "hr-001"
    source: "human_script_review"
    created_at: "ISO8601"
    raw_request: "string"
    original_selectors: ["scene3_cut2"]
    current_selectors: ["scene3.1_cut2.1"]
    normalized_actions: []
    status: "pending|normalized|applied|verified|waived"
    resolution_notes: ""
    applied_manifest_targets: []
```

Canonical `normalized_actions[].action`:

- `add_scene`, `delete_scene`, `add_cut`, `delete_cut`, `renumber_scene`, `renumber_cut`
- `update_scene_summary`, `update_story_visual`
- `update_narration`, `clear_narration`, `set_silent_cut`
- `update_visual_beat`, `update_scene_contract`
- `add_location_asset`, `add_object_asset`, `add_character_variant`
- `create_still_asset`, `derive_still_asset`, `reference_asset`
- `set_image_direction`, `set_video_direction`

`script.md.scenes[].human_review`:

- `status`
- `notes`
- `approved_scene_summary`
- `approved_story_visual`
- `change_request_ids[]`

`script.md.scenes[].cuts[].human_review` add:

- `approved_visual_beat`
- `approved_image_notes[]`
- `approved_video_notes[]`
- `change_request_ids[]`

`video_manifest.md` execution additions:

- `assets.location_bible[]`
  - `location_id`, `reference_images`, `reference_variants[]`, `fixed_prompts`, `review_aliases[]`, `continuity_notes[]`, `notes`
- `image_generation.location_ids[]`
- `image_generation.location_variant_ids[]`
- `still_assets[]`
  - `asset_id`, `role`, `output`, `image_generation`, `derived_from_asset_ids[]`, `reference_asset_ids[]`, `reference_usage[]`, `direction_notes[]`, `applied_request_ids[]`
- `reference_usage[]`
  - `asset_id`, `mode`, `placement`, `keep[]`, `change[]`, `notes`
- `video_generation.input_asset_id`
- `video_generation.first_frame_asset_id`
- `video_generation.last_frame_asset_id`
- `video_generation.reference_asset_ids[]`
- `video_generation.direction_notes[]`
- `video_generation.continuity_notes[]`
- `video_generation.applied_request_ids[]`
- `audio.narration.applied_request_ids[]`
- `implementation_trace`
  - `source_request_ids[]`, `status`, `notes`

ID policy:

- `scene_id` / `cut_id` は dotted numeric string を許可する
- canonical selector は `scene<scene_id>_cut<cut_id>`
- sort は numeric token sort
- 出力 file slug は `.` を `_` に変える
- stable UID は導入しない

Canonical reason key:

- `human_change_request_unresolved`
- `human_change_request_trace_missing`
- `location_asset_missing`
- `still_asset_missing`
- `still_asset_dependency_missing`
- `video_asset_reference_missing`
- `reference_usage_target_missing`
- `dotted_selector_invalid`
- `renumber_trace_missing`
