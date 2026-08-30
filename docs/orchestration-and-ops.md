# Orchestration / QA / Compliance / Publishing

変更内容:
- production order を asset/image-first に切り替え、公開 workflow を `asset -> scene implementation / image -> narration -> video -> render -> qa` に再編した。
- canonical stage は `research`, `story`, `script`, `narration`, `asset`, `scene_implementation`, `video_generation`, `render`, `qa` に揃えた。

修正理由:
- asset と scene image を先に確定し、実際の visual に合わせて narration と video を仕上げるため。

旧仕様との差分:
- 旧運用は narration/audio を asset / image より前に置いていた。
- 新運用は scene implementation を公開 stage にし、asset/image-first を固定する。

運用設計ドキュメント（追加レイヤー）

## 位置づけ

```
[情報収集] → [物語生成] → [動画生成] → [配信/分析] → [改善]
         ↑           ↑           ↑           ↑           ↑
         docs/information-gathering.md
                     docs/story-creation.md
                                 docs/video-generation.md
                                                    本書
```

本書は、上記3システムを**一連の組織プロセス**として統合し、品質・権利・運用・改善の仕組みを定義する。

---

## 1. Orchestration（全体制御）

### 1.1 目的
- サブエージェントの順序・依存関係・再実行を管理する
- 人間の承認ゲートを明示する
- すべての成果物をトレース可能にする

### 1.2 ステートマシン

```
INIT → RESEARCH → STORY → VIDEO → PUBLISH → ANALYZE → IMPROVE → DONE
        ↑   └─────────────┐
        └── RETRY/REVISE ─┘
```

### 1.3 オーケストレーション・マニフェスト

```yaml
job:
  job_id: "JOB_2026-01-10_0001"
  topic: "桃太郎"
  created_at: "ISO8601"
  status: "RESEARCH | STORY | VIDEO | PUBLISH | ANALYZE | IMPROVE | DONE"

inputs:
  user_prompt: "string"
  review_mode: "standard | preapproved"
  constraints:
    duration_seconds: 60
    aspect_ratio: "9:16"
    language: "ja"

artifacts:
  research: "output/<topic>_<timestamp>/research.md"
  story: "output/<topic>_<timestamp>/story.md"
  video: "output/<topic>_<timestamp>/video.mp4"
  improvement: "output/<topic>_<timestamp>/improvement.md"

gates:
  research_review: "required | optional | skipped"
  story_review: "required | optional | skipped"
  video_review: "required | optional | skipped"

audit:
  steps:
    - step: "RESEARCH"
      status: "done"
      reviewer: "human | auto"
      notes: "string"
```

### 1.4 実行ルール
- **必須レビューゲート（standard）**: 事実性（Research）と最終納品（Video）
- **自動再試行**: 失敗原因が機械的（APIエラー、品質低下）の場合のみ
- **人間レビュー（standard）**: 重要テーマ（時事、政治、医療、法律）は強制。frontend create の明示 `preapproved` は reviewer turn を省略できるが、選択と deterministic validation の証跡を残す
- **run-level orchestration**: L1 Run Orchestrator は `p100` 番台ごとの L2 P-Bucket Supervisor を順番に起動し、本文 artifact を読まずに handoff artifact と slot state だけで次 bucket へ進む
- **L2 progress memo**: L1 Run Orchestrator は L2 supervisor 起動時に `logs/orchestration/l2_supervisor_progress.md` へ `invoked` を追記する。記録対象は L2 supervisor だけで、L3 task/review agents はここへ記録しない
- **bucket single writer**: L2 P-Bucket Supervisor は担当 bucket 内の canonical artifact、`state.txt`、`p000_index.md` の single writer として動く。L3 task/review agents は isolated output のみを書く
- **state transaction**: orchestrator はshared state storeへ変更keyだけを一つのatomic delta eventとして渡す。`state.txt`全履歴のread/merge/full-snapshot appendや、`state.current.json` / `run_status.json` / `p000_index.md`への状態の直接書込みを行わない
- **bucket completion artifact**: 各 bucket は完了時に `logs/orchestration/pXXX.supervisor_result.json` を書き、`status` / `completed_slots` / `required_artifacts` / `state_keys` / `review_outputs` / `next_bucket` / `blocked_reason` を残す
- **grounding preflight**: stage 開始前に `scripts/resolve-stage-grounding.py` を実行し、必要 docs / templates / upstream artifact の解決結果を `logs/grounding/<stage>.json` と `state.txt` へ残す
- **readset audit**: grounding 後に `scripts/audit-stage-grounding.py` を実行し、`logs/grounding/<stage>.readset.json` と `logs/grounding/<stage>.audit.json` を残す
- **chat/manual stage helper**: chat で stage 作業を始めるときは、担当 L2 supervisor が `scripts/prepare-stage-context.py` を標準入口として使い、内部で `resolve -> audit -> readset確認` を直列で終えてから編集へ進む。返ってきた `readset_path` を起点に `global_docs -> stage_docs -> templates -> inputs` の順で読む
- **user-triggered subagent audit**: stage 完了後に `scripts/build-subagent-audit-prompt.py` を使って貼り付け用 prompt を生成し、ユーザーが contextless audit subagent を起動して独立検証してもよい。script は `logs/grounding/<stage>.subagent_prompt.md` も保存し、subagent は content artifact を編集しない
- **user-triggered image judgment subagent**: image prompt の意味評価は `scripts/build-subagent-image-review-prompt.py` で貼り付け用 prompt を生成し、ユーザーが contextless subagent に渡してよい。script は `logs/review/image_prompt.subagent_prompt.md` を保存し、subagent は hard schema 判定ではなく story/script/manifest の意味整合と revision 優先度を見る
- **review policy**: run 開始時に `runtime.review_mode=standard|preapproved` と `review.policy.story|image|narration=required|optional|skipped` を固定し、grounding はこの policy に従って承認 gate を有効/無効化する。既定の `standard` は external semantic reviewer と frontend human review を省略しない。`skipped` は frontend create の明示 `create_input.json.review_mode=preapproved` に限り、reviewer turn の省略を表す。pack / digest / deterministic / provenance / output validation は preapproved でも必須とする
- **Codex app-server transport gate**: semantic QA / prompt repair / image generation / chat で app-server を使う前に shared runtime contract の preflight を通す。DNS、WebSocket、HTTP fallback、`backend-api/codex/responses` の stream failure、writable `CODEX_HOME` を満たせない runtime setup failure は `runtime.app_server.transport.status=failed` または `review.semantic.<stage>.transport.status=failed` として扱い、semantic QA の意味判定 failure とは分離する。semantic QA / producer repair の app-server turn timeout は固定の total deadline ではなく no-progress watchdog とする。Codex app-server の turn notification、semantic report、producer report、修正対象 artifact のいずれかが更新されている間は改善中として待ち、観測可能な進捗が止まった時だけ `review.semantic.<stage>.watchdog.status=no_progress_timeout` で blocked にする。semantic report が存在しない transport failure では production-side repair loop を起動しない。semantic report が changes_requested を返した後の修正 agent 実行中に transport が落ちた場合も、producer report が未完了なら semantic failure ではなく `review.semantic.<stage>.repair.status=blocked_transport` で止める。producer report がすでに `status: done` なら、その成果物を採用して再レビューへ進む。
- **Frontend create runtime path**: `/api/image-gen/runs/create` は backend process から `scripts/toc-immersive-frontend-run.py` を直接実行する。app-server skill turn の内側で同 helper を起動する nested app-server 経路は禁止する。restart helper が確認する runtime と実生成 runtime を一致させ、asset/scene 画像生成の失敗を health check と state diagnostics で同じ層から検出できるようにするため。

### 1.4.0 Frontend create の review mode

frontend の作成ダイアログは `レビューモード` を持ち、`通常レビュー`（`standard`、既定）と
`全レビュー済み`（`preapproved`）を選択できる。選択値は各 create endpoint の request に
`review_mode` として渡し、run 作成時に `logs/orchestration/create_input.json` の
`toc.create_input.v1` へ保存する。`review_mode` は `standard|preapproved` のみを許可し、
run 後に推測・変更しない。

- `standard`: external semantic reviewer turn と frontend human review turn を通常どおり
  実行する。`gate.*=required` と未承認の review status を保ち、L1/L2 が自動承認してはならない。
- `preapproved`: frontend create で明示された場合だけ使う。`research`, `story`, `scene_set`,
  `scene_detail`, `cut_blueprint`, `asset_plan`, `image_prompt` の external semantic / human
  reviewer turn を省略するが、各 stage の semantic `collection` / `scope` / `prompt` / `report`
  を作成し、source/input digest に束縛された `deterministic_preapproval` report を残す。
  `review.semantic.<stage>.mode=preapproved`、`report.source=deterministic_preapproval`、
  `transport.status=skipped_preapproved`、`repair.status=skipped_preapproved`（shard stage は
  `shards.status=skipped_preapproved`）を provenance として記録する。pack / digest、grounding・
  schema・参照整合、request snapshot、provider provenance、生成 output の存在・decode・
  fixed-slot completeness は必ず検証し、blocking diagnostics は fail-close する。

preapproved の p680 handoff は、media generation と deterministic validation が終わるまで
完了扱いにしない。materialization 直後は `gate.image_review=skipped` でも
`review.image.status=pending` とし、terminal validation に成功した時だけ
`slot.p680.status=done`、`review.image.status=approved`、`gate.image_review=skipped` を記録する。
standard の同じ境界は `slot.p680.status=awaiting_approval`、`review.image.status=pending`、
`gate.image_review=required` で frontend に handoff する。preapproved の `skipped` は reviewer
turn だけの省略であり、deterministic/output/provenance checks の省略ではない。

### 1.4.1 canonical state の書き分け

`state.txt` では、`status=` と `stage.*.status=` を分けて扱う。

- `status=`
  - 粗い現在地
- `stage.*.status=`
  - 作業単位の完了状況
  - `awaiting_approval` は、作業は終わったが承認待ちで停止している状態
- `runtime.review_mode=standard|preapproved`
  - `logs/orchestration/create_input.json` の `review_mode` と一致する run-level contract
- `runtime.review_policy=frontend|preapproved`
  - `review_mode` から導出する実行 policy

標準 stage:

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

legacy compatibility keys:

- `stage.image_prompt_review`
- `stage.image_generation`

これらは旧 run / 旧 evaluator 互換の補助キーであり、公開 workflow の正本 stage ではない。

各作業は **開始時** と **完了時** に append する:

1. 開始時:
   - `stage.<name>.grounding.status=ready`
   - `stage.<name>.audit.status=passed`
   - `stage.<name>.status=in_progress`
   - `stage.<name>.started_at=...`
2. 完了時:
   - grounding が `ready` かつ audit が `passed` のときだけ stage 完了へ進める
   - 承認不要なら `stage.<name>.status=done`
   - 承認待ちが必要なら `stage.<name>.status=awaiting_approval`
   - `stage.<name>.finished_at=...`
3. 失敗時:
   - `stage.<name>.status=failed`
   - `last_error=...`

標準で承認待ちを挟む stage:

- `stage.script`
- `stage.narration`
- `stage.scene_implementation`

この 3 つが `awaiting_approval` の間は、**次工程へ進まない**。

承認待ちの stage を報告するときは、単に `awaiting_approval` と書くだけで終わらせず、次にユーザーがレビューすべき対象を短く明示して確認を促す。

対応 review:

- `review.script.status`
- `review.image.status`
- `review.narration.status`

grounding 状態と証跡:

- `stage.<name>.grounding.status=ready|missing_docs|missing_inputs`
- `stage.<name>.grounding.report=logs/grounding/<stage>.json`
- `stage.<name>.readset.report=logs/grounding/<stage>.readset.json`
- `stage.<name>.audit.status=passed|failed`
- `stage.<name>.audit.report=logs/grounding/<stage>.audit.json`
- `stage.<name>.subagent.prompt=logs/grounding/<stage>.subagent_prompt.md`
- `review.image_prompt.subagent.prompt=logs/review/image_prompt.subagent_prompt.md`
- `orchestration.pXXX.supervisor.status=done|blocked|failed`
- `orchestration.pXXX.supervisor.progress=logs/orchestration/l2_supervisor_progress.md`
- `orchestration.pXXX.supervisor.call_status=invoked|returned|blocked|failed`
- `orchestration.pXXX.supervisor.invoked_at=ISO8601`
- `orchestration.pXXX.supervisor.last_event_at=ISO8601`
- `orchestration.pXXX.supervisor.stop_slot=pXXX`
- `orchestration.pXXX.supervisor.result=logs/orchestration/pXXX.supervisor_result.json`
- `orchestration.pXXX.supervisor.finished_at=ISO8601`
- canonical stage は `research`, `story`, `script`, `narration`, `asset`, `scene_implementation`, `video_generation`, `render`, `qa`
- evaluator / verifier では互換 alias として `manifest=scene_implementation`, `image_prompt=scene_implementation`, `video=video_generation` を許可する

run 開始時に固定する review policy:

- `review.policy.story`
  - `story.md` を `script` / `scene_implementation` の upstream として使う前に承認が要るか
- `review.policy.image`
  - `video_generation` 前に `review.image.status=approved` を要求するか
- `review.policy.narration`
  - `video_generation` 前に `review.narration.status=approved` を要求するか

各 policy の値は `required|optional|skipped`。default は `required` だが、script draft まで
一気に進めたい run では開始時に `optional` を選べる。`skipped` は
`create_input.json.review_mode=preapproved` による明示 frontend create だけで使用し、
外部 reviewer turn の省略を表す。preapproved でも canonical review pack / digest、
deterministic checks、request-bound provenance、generated-output validation は必須である。

これにより、`state.txt` だけで

- 調査は終わった
- 物語は終わった
- ナレーションは終わった
- render はまだ

のような読み方ができる。

### 1.4.2 run navigation layer

run 直下には `p000_index.md` を置き、人間向けの入口にする。

- `100` 番台ごとに大工程を割り当てる
- 細番号も全作品共通の fixed slot contract とする
- story ごとの差は slot meaning を変えず、`slot.<code>.status` / `slot.<code>.requirement` / `slot.<code>.skip_reason` / `slot.<code>.note` で表す
- `p000_index.md` の stage table / slot table を、その run の進捗正本とする
- 第1段階では binary / logs / scratch の物理 rename は行わず、navigation layer として番号を導入する
- narration は
  - `p400`: narration contract / narration draft / human changes / skeleton manifest materialization
  - `p700`: TTS 実行 / duration fit gate / audio handoff
  の 2 層で扱う
- 画像生成の request 改稿は、scene 単位で自然言語エージェントへ割り当てる
  - 各 scene agent は L2 `p600` supervisor の配下で `script.md`、`video_manifest.md`、現在の request draft を読む
  - その scene の `visual_beat` を semantic source として、stateless な request 文へ落とす
  - 出力はまず scene-specific scratch rewrite に置き、L2 supervisor が統合する
  - この手順を固定しておくと、毎回の image generation run で再現できる

標準 slot override 例:

```bash
python scripts/toc-state.py set-slot \
  --run-dir output/<topic>_<timestamp> \
  --slot p540 \
  --status skipped \
  --requirement optional \
  --skip-reason "asset stage not needed for this run"
```

### 1.5 Production Order の内部サブフロー

```
SCRIPT:
  1) scene / narration draft
  2) skeleton manifest materialization

NARRATION:
  1) narration text review
  2) TTS generation
  3) duration fit gate

ASSET:
  1) reusable asset inventory
  2) asset plan / generation

SCENE_IMPLEMENTATION:
  1) production manifest / prompt authoring
  2) hard review
  3) judgment review
  4) scene still generation

VIDEO:
  1) motion prompt review
  2) clip generation

RENDER:
  1) クリップ結合 + 音声ミックス
  2) 字幕作成・焼き込み
  3) 最終レンダリング（mp4出力）
  4) 品質ゲート通過
```

### 1.6 mp4出力の必須条件

```yaml
video_delivery_gate:
  mp4_exists: true
  duration_ok: true
  audio_sync: true
  subtitle_ok: true
  aspect_ratio_ok: true
```

---

## 2. QA（品質評価）

### 2.1 目的
- 事実の正確性、物語の一貫性、視聴体験の質を保証
- 再現性のある評価指標を提供

### 2.2 QAチェックリスト

```yaml
qa_checks:
  factual_accuracy:
    min_confidence: 0.7
    verified_facts_ratio: 0.8
    no_fabrication: true

  narrative_quality:
    hook_strength: "good | fair | weak"
    tension_curve: "clear | uneven | flat"
    transformation_present: true

  visual_consistency:
    character_consistency: true
    style_consistency: true

  audio_quality:
    narration_clarity: true
    bgm_balance: true
    sfx_timing: true
```

### 2.3 評価スコア（例）

```yaml
qa_scores:
  accuracy_score: 0.0-1.0
  engagement_score: 0.0-1.0
  consistency_score: 0.0-1.0
  overall_score: 0.0-1.0
  pass_threshold: 0.75
```

### 2.4 フェイル時の対応
- `accuracy_score < 0.75` → Researchを再実行
- `engagement_score < 0.7` → Storyを再実行
- `consistency_score < 0.7` → Videoを再実行

---

## 3. Compliance（権利・倫理・安全）

### 3.1 目的
- 著作権侵害・肖像権・人格権リスクを抑える
- AI利用の透明性を確保する

### 3.2 ルールセット

```yaml
compliance_rules:
  copyright:
    prohibit_direct_copy: true
    require_source_tracking: true
  likeness:
    real_person: "consent_required"
    public_figure: "caution_required"
  data_usage:
    training_opt_out: "respect"
    api_terms: "enforced"
  disclosure:
    ai_generated_notice: true
```

---

## 4. Publishing（配信・分析・改善ループ）

### 4.1 配信設計
- チャンネルの戦略（Shorts/Long/Series）
- タイトル/サムネ/説明文のテンプレ

### 4.2 分析指標

```yaml
analytics:
  retention:
    average_view_duration: "seconds"
    relative_retention: "above | average | below"
  engagement:
    like_ratio: 0.0-1.0
    comment_rate: 0.0-1.0
    share_rate: 0.0-1.0
  growth:
    subscribers_delta: int
```

### 4.3 改善エージェント（4番目）

```yaml
improvement_agent:
  inputs:
    - "output/<topic>_<timestamp>/video.mp4"
    - "analytics_metrics.json"
    - "comment_samples.json"
  outputs:
    - "output/<topic>_<timestamp>/improvement.md"
  tasks:
    - "競合比較（構成/テンポ/フック）"
    - "改善仮説の提示"
    - "次回A/Bテスト案の提案"
```

---

## 5. ディレクトリ構成（推奨）

```
output/
  <topic>_<timestamp>/
    research.md
    story.md
    video_manifest.md
    video.mp4
    improvement.md
    clips.txt
    narration_list.txt
    assets/
      characters/
      styles/
      scenes/
      audio/
logs/
  orchestration/
```

---

## 6. 連携ポイント

- **Research → Story**: 事実性とフックの転写
- **Story → Video**: シーン分解とスタイルガイドの適用
- **Video → Publishing**: タイトル/サムネ/説明の生成
- **Publishing → Improvement**: 視聴維持とコメント分析を反映

---

## 7. 最小実装（MVP）手順

```
1. Research実行 → 出力生成
2. Story実行 → 台本生成
3. Video実行 → mp4生成
~まずはここまで
4. 手動でYouTube公開
5. 1週間後、コメントと維持率を収集
6. Improvement実行 → 改善案を次作に反映

```

---

## 8. 1物語フォルダ作成（補助）

```bash
scripts/create-story-folder.py --topic momotaro
# 例: output/momotaro_20260111_0930/ が生成される
```
