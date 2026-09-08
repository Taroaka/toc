# Production review / audit removal inventory (contracts)

調査対象は現在の checkout の `docs/`, `workflow/`, `config/`, `skills/`,
`.agents/`, `.codex/`, `.claude/`（`rg --hidden`、`output/`, runtime/cache/history、
`.claude/worktrees/**` は除外）と、repo 外に install 済みの ToC stage skill コピー。
このファイル以外は変更していない。

## 判定の軸

- **削除候補**: production の critic / reviewer / aggregator、review-loop、review
  report/score/pass の存在・currentness・人数・digest・signature 監査、review 不在を
  `preapproved` で擬似的に埋める証跡、review slot を進行条件にする記述。
- **分離**: 上記と、通常の source/readset 解決、schema/type/ID/selector 整合、request と
  provider output の対応、画像 decode/provenance、lock/path/権限を同じ gate にしている箇所。
- **保持候補**: 作成 agent、source-grounded な資料読み、構造化入力の検証、実ファイルの
  存在・decode、request の immutable binding、候補を人が選ぶ UI、human change の保存。
- **関連・別系統**: generic code/security review、compliance audit、公開/配信時の最終
  confirmation。制作 reviewer 廃止へ一括削除しない。

## 正本とミラーの階層

### 正本ポインタ

- `AGENTS.md:1-15`, `CLAUDE.md:1-15` — 同一ポインタ。詳細は
  `docs/root-pointer-guide.md` を読む契約。ここ自体に production review の実装はない。
- `docs/root-pointer-guide.md:3-9,21-27` — `docs/`, `workflow/`, `scripts/` を正本、
  `/toc-run`, `/toc-scene-series`, `/toc-immersive-ride`, `/toc-world-walk` を入口とする。
- `docs/root-pointer-guide.md:39-42,99-116,158-189,191-212` — frontend create は
  grounding、deterministic verifier、review-loop materialization、semantic reviewer、
  p650/p680 validation を通すという現行の強制契約。特に `review_mode` に関係なく残る
  reintroduction source。`global_docs -> stage_docs -> templates -> inputs` の資料読み
  順序は ordinary source-reading として切り出して保持できる。

### 現行の主要正本（削除・分離の中心）

- `docs/data-contracts.md:91-115,117-279` — append-only state、stage grounding/audit、
  `review.*`, `eval.*`, score、review report path、critic 1..5 / aggregator の state key
  catalog。`283-357` は `toc.create_input.v1`、`review_mode`、p680 handoff。`359-439` は
  L1/L2 supervisor result と `review_outputs`。`441-502` は authoring-after loop、
  対象 review slot、5 critic + 1 aggregator、max 5 round、停止条件と state key。`515-539`
  は grounding/evaluator summary。`575-617` は fixed p-slot と coarse target。
- `docs/orchestration-and-ops.md:31-98` — orchestration manifest の `gates`/`audit`、
  standard の必須 review、人間 review、grounding/readset audit、review policy、semantic
  transport/recovery gate。`100-126` は frontend `standard|preapproved` の UI/状態。
  `128-227` は `runtime.review_*`, `stage.*.audit.*`, `review.*`, supervisor state と
  policy。`268-299` は内部 subflow の narration/image/video review。`314-358` は QA
  score と `0.75/0.7` retry threshold。review 解体時は通常処理と分離する。
- `docs/system-architecture.md:13-27,50-70,86-113,115-142` — L1/L2/L3 topology、
  5 critics + aggregator、p720 5 semantic critics、semantic report/current hash、
  preapproved の pseudo-pass、runtime transport gate。`260-272` は supervisor result
  の required `review_outputs`。`274-375` が固定 p-slot の最も明確な一覧（下表参照）。
  `376-425` は supervisor map、5+1 loop、L2 が修正と gate close を決める契約。
- `docs/how-to-run.md:55-79,81-115` — human-facing review-mode UI と p680 handoff、
  preapproved warning、headless create。`212-226` は image/asset review と output
  validation の混在。`240-318` は p100-p900、L1/L2/L3、5+1、supervisor result。`330-367`
  は duration/manifest/evaluator loop。`495-532` は grounding audit、review policy、
  human exception。`534-669` は stage/slot/review/eval state key と sample。
- `docs/script-creation.md:158-206,337-371` — p410 scene-set/detail review、p420
  cut review、p430 script review、p435 production readiness council、p450 materialization、
  5 critic assignments、aggregator gates、`eval.p400_readiness`。`498-527,534-651` は
  human narration source、p720 two-layer review、p750 explicit audio approval。
- `docs/implementation/scene-loop.md:8-20,71-125,153-181,195-239` — p410/p420 の
  review order、blocking findings、5 critics + aggregator、review-only state。scene/cut の
  semantic/causal fieldsは構造設計として保持できるが、review を gate にする部分は削除。
- `docs/implementation/cut-loop.md:1-34,76-123,125-164` — p420 の canonical operating
  guide。「review is a gate, not advice」、aggregate の `Cut Blueprint Gate` 21項目、
  blocking reason key。cut contract/handoff の構造 validator と review orchestration を分離。
- `docs/implementation/image-prompting.md:1-26,38-68,109-153` — asset/cut review、
  `agent_review_ok`, reason keys, `rubric_scores`, `overall_score`、both-false stop、
  standard/preapproved、semantic pack/reviewed-draft/freeze。`219-315` は manifest review
  lifecycle schema と human override。`369-407,472-493,1049-1095` は criterion/reason
  keys、first-frame blocker、judgment-review helper。prompt compiler の source priority、
  conditional groups、API metadata 除外は保持し、reviewer/pass/score dependency を外す。
- `docs/implementation/image-prompt-judgment-review.md:1-25,27-62` — contextless
  image judgment reviewer の専用 helper、collection/scope/prompt/report、`passed|failed`
  report。production reviewer 削除候補。prompt の通常構造/metadata exclusion は image
  compiler/structural validation 側へ移す。
- `docs/implementation/asset-bibles.md:14-29,31-117,119-153,196-202,319-328` — p510
  grounding audit、p520 inventory、p530 plan、p540 review loop（複数 critic + aggregator）、
  p550 requests、p560 generation、p570 continuity、p660 output gate。asset identity/
  reference/DAG/provenance/decode は保持、review/approved を canonical 化条件にする箇所を分離。
- `docs/implementation/video-integration.md:20-41,105-157,157-212,213-276` — stage order、
  p710 image-to-voice、p720 deterministic + 5 semantic critics、mandatory review、hash/current
  checks、p730 candidate、p740 duration gate、p750 full-run human approval。TTS text/source と
  timeline の構造・実測は保持し、critic/aggregate/pass/currentness gate を削除。
- `docs/implementation/narration-prompting.md:1-20,22-55` — registry の `review_visibility`
  と semantic pack への review-only visual context。source projection（authoring relevance /
  spoken projection）は保持、semantic critic 専用部分は削除または optional trace 化。
- `docs/implementation/video-prompting.md:1-35,53-112,114-173,223-245` — provider prompt
  compiler、`projection_review_contract`/`review_only_sources`、quality_issues の blocking、
  request materialization/current drift。provider-facing prompt と IR/reference/hash の構造
  契約は保持できる。`review_only` は「reviewerを起動する」意味と混同しないよう名称/用途を分離。
- `docs/video-generation.md:190-196,263-282,329-394,460-486,699-734,758-884,1091-1106` —
  cut/event/motion の構造、human change request、request review projection、provider binding、
  per-item approval、quality_issues、video gate。人が候補を選ぶ/変更要求を保存する UI は関連保持、
  review report の存在・pass・quality score を provider gate にする部分は削除候補。
- `docs/adaptation-value-amplification.md:1-7,34-71,91-119` — adaptation value の
  source/value projection、validator と semantic reviewer の境界。source IDs、non-negotiable
  facts、compiler projection は保持。semantic reviewer にのみ任せる品質判定は今回の削除対象。
- `docs/implementation/agent-roles-and-prompts.md:1-14,18-69,71-83,108-179,212-250` —
  L1/L2/L3 supervisor contract、L3 critic/aggregator、p410/p420 critics、Stage Evaluator、
  5 critic + aggregator、human/approval 非自動化。L1/L2 single-writer/handoff は保持し、L3
  review roles、loop、review gate の採用判断を通常 task/structural validation へ置換。
- `docs/implementation/langgraph-topology.md:1-50,65-85` — 古い「正本」表記で、old default
  review gates、5+1 loop、score retry (`0.75/0.7`)、max 2 retry、人間昇格を重複定義。現行
  `system-architecture`/`data-contracts` と衝突する legacy/duplicate source。更新しないと
  review を再導入する。
- `docs/implementation/codex-built-in-image-runbook.md:80-90,98-114,150-170` — image
  continuity review gate と provenance gate。人物/asset review を production gate から外す
  ときも request-bound provenance、destination、hash、cross-process slot は保持。
- `docs/implementation/cut-to-image-narration-video.md:1-24,26-89,90-137` — p600/p700/p800
  の同一 cut contract と triangulation review。event boundary、first-frame、motion、narration
  の構造チェックは保持候補、`triangulation_review` を必須 report/pass にする部分は削除候補。
- `docs/implementation/orchestration-logging.md:1-43` — `eval_report.json`/`run_report.md`
  を stage-gated output として説明するログ正本。ログ/報告を作る通常処理を残すか、review-only
  fields を削るか分離する。
- `docs/adr/0003-stage-gated-eval-harness.md:1-24` — Accepted ADR（2026-03-09）で、各 stage
  の deterministic/rubric check、`eval_report.json`/`run_report.md`、state eval score を決定した
  historical rationale。削除実装と同時に supersede/更新しないと ADR が review harness を再導入する。
- `docs/adr/0004-image-generation-provenance-before-parallelism.md:1-49` — Accepted provenance
  ADR。`generation_job_id`/`item_id`/`turn_id`/prompt/reference hash/destination、serial fallback
  policy、deterministic provenance failure を定義する。review とは独立なので保持し、review gate
  と混同しない。
- `docs/adr/0002-state-txt-canonical-run-status-json-derived.md:1-24` — append-only state と
  derived view の storage rationale。review/eval fields 変更後も state canonicality は保持。

### Active / legacy / duplicate status

| status | sources | inventory consequence |
|---|---|---|
| **Active canonical** | `docs/root-pointer-guide.md`, `docs/system-architecture.md`, `docs/data-contracts.md`, `docs/orchestration-and-ops.md`, `docs/how-to-run.md`, `docs/story-creation.md`, `docs/script-creation.md`, `docs/video-generation.md`, `docs/implementation/{scene-loop,cut-loop,image-prompting,asset-bibles,video-integration,narration-prompting,video-prompting,immersive-ride-entrypoint,agent-roles-and-prompts}.md`, `workflow/stage-grounding.yaml`, `workflow/state-schema.txt`, `workflow/evaluation_criteria.md`, current manifest/script templates, `workflow/multiagent-immersive-narration-playbook.md`, `.codex/skills/toc-immersive-runner` | Update these first. Removing only a mirror leaves the active contract intact. |
| **Active but adjacent/structural** | `docs/information-gathering.md`, `docs/adaptation-value-amplification.md`, `docs/implementation/cut-to-image-narration-video.md`, `docs/implementation/codex-built-in-image-runbook.md`, `docs/implementation/orchestration-logging.md`, asset/cut/handoff templates, Kling/compiler playbooks | Keep source reading, value/contract projection, request binding, decode/provenance and optional structural checks; remove only review-gated use. |
| **Legacy or compatibility duplicate** | `docs/implementation/langgraph-topology.md` (old accepted “正本” with old gates), `.claude/commands/toc/*.md` (Codex runner calls these legacy references), `workflow/multiagent-immersive-cuts-playbook.md`, `workflow/multiagent-scene-series-playbook.md`, legacy `scene_contract`, `image_generation.prompt`, `stage.image_prompt_review`, `stage.image_generation`, `review_*` aliases in templates | Mark/supersede or update even when not used by the main route; these are the easiest future reintroduction paths. The two multiagent playbooks currently have no 5+1 loop and should not be deleted for this task. |
| **Mirrored role/config source** | `.claude/agents/*.md` ↔ `.codex/agents/*.toml`; installed `/Users/kantaro/.codex/skills/toc-*` copies | Sync both in-repo wrappers and separately reinstall/update the external copies. |

### story authoring 正本の直接レビュー要求

- `docs/story-creation.md:111,119-132` — canonical event coverageをreview gateとし、review済みresearchを入力にする。preapprovedでも作成agentは必須という区別がある。作成agentは残し、review済みという入力条件を外す。
- `docs/story-creation.md:160-164` — candidate scoring / source-vs-creative audit / grounding auditをcontextless subagentへ委譲し、p230 story_reviewで候補スコア・scene密度・根拠境界・handoffを評価。p210 auditとp230 review両方が直接撤去対象。
- `docs/story-creation.md:812` — `quality_scores` schema。review採点の必須欄として外す。資料内の感情設計・シーン設計自体は保持候補。
- `docs/story-creation.md:1009-1034` — review済み上流入力、authoring_preflight、独立contextless reviewerとcriterion再評価、shift_left_escape、producer repairへの戻し方。資料読み/ID参照preflightを保持し、独立review/pass/repair監査要求を分離して撤去する。

### 正本だが品質レビューではない隣接文書

- `docs/information-gathering.md:51-79,251-266,603-606,882-884,999-1022,1258-1260` —
  source reading、uncertainty、curiosity/confidence/completeness/engagement の研究メタデータ。
  これは reviewer score/pass ではなく調査内容の不確実性・素材優先度なので保持候補。`source`
  と `verification` の読みをレビュー撤去で落とさない。
- `docs/security-compliance.md:17-33` — compliance の audit log（`reviewer`, `decision`を含む）。
  制作品質 reviewer とは別系統で、今回の一括削除対象外。
- `docs/implementation/assistant-tooling.md:15-42,59-80,130-153` — Claude/Codex の
  command/agent/skill 配置、single-writer、install。production review があることを列挙する
  `pending gate`/verify 説明だけ更新対象になり得る。generic tooling は保持。

### Config / clean adjacent contracts

- `config/system.yaml:1-44`, `config/projects.yaml:1-7` — 現在の checkout には
  production reviewer、grounding audit、critic/aggregator、review score/pass の設定値がない。
  変更対象ではない。`config/tts-pronunciation-aliases.tsv` は TTS 読み替えデータであり、
  p720 reviewer 撤去とは別に保持する。
- `workflow/asset-inventory-template.yaml:1-26`, `workflow/scene-evidence-template.md:1-23`,
  `workflow/scene-script-template.md:1-76` — inventory/evidence/scene authoring の通常入力。
  source/asset/cut fields を保持し、review prerequisite を追加しない。
- `workflow/scene-conte-template.md:1-183`, `workflow/cut-conte-template.md:1-96` — p400
  bridge/legacy cut prose。`reviewer が完了判断できる条件` の placeholder と p500/p600/p700/
  p800 handoff は review artifact に再接続しない。bridge の実データ fields は保持。
- `workflow/visual-value-template.yaml:1-215` — p300 visual planning と downstream handoff。
  `review_focus` は design guidance であり、reviewer/pass artifact を要求する gate へ戻さない。

## 固定 p-slot と review dependency

正本は `docs/system-architecture.md:291-375`。coarse target と handoff は
`docs/data-contracts.md:605-617`、細番号列は `docs/how-to-run.md:273-294` にも重複する。

| bucket | current fixed slots | current review/audit dependency | removal note |
|---|---|---|---|
| p100 research | p110 grounding, p120 authoring, **p130 evaluator loop** | p130 5 critics+aggregator; research review/pass | p110 readset/source resolution と p120 authoring を保持。p130 review artifact/pass/score を進行条件から外す。|
| p200 story | p210 grounding, p220 authoring, **p230 evaluator loop** | p230 story semantic/reviewed research; candidate score | story creation/source trace は保持。p230 reviewer/score/report を削除または optional note 化。|
| p300 visual | p310 authoring, **p320 evaluator loop**, p330 handoff | p320 5+1; p330 human-review handoff wording | visual value/anchor/reference planning を保持。p320 evaluator は外す。p330 は downstream handoff と任意の人の編集を分ける。|
| p400 script | p410 scene completion (p410b set/p410c detail), p420 cut blueprint, **p430 evaluator**, **p435 readiness council**, p440 human changes, p450 skeleton | scene/cut reviewer/aggregator、p400 readiness `approved`、5+1 report presence | scene/cut/event/role/reveal/handoff schema と deterministic ID/selector checks を保持。p410b/c、p430、p435 の reviewer/critic/report/pass/score dependency を外す。p440 の human change request は UI/編集機能として別保持。|
| p500 asset | p510 grounding, p520 inventory, p530 plan, **p540 evaluator**, p550 requests, p560 generation, p570 continuity | p540 critic+aggregator、p570 `review.status=approved` / human handoff | asset inventory/plan/reference/provenance/decode を保持。p540 reviewer gate と approved-only promotion を外す。p570 の実画像 continuity check は通常 output validator/任意人選択へ分離。|
| p600 scene/image | p610 grounding, p620 authoring, **p630 hard evaluator**, **p640 judgment evaluator**, p650 ready, p660 image generation, p670 image QA/fix, p680 human handoff | p630/p640 5+1、p650 frozen after semantic pass、p670 semantic QA、p680 `review.image`/`gate.image_review` | compiler/request snapshot/reference hash/output decode は保持。semantic reviewer/repair loop、p630/p640 report/pass、p680 mandatory review modeを外す。p670 の decode/provenance/file checks は普通の validator。画像候補選択 UI は別保持。|
| p700 narration | p710 grounding, **p720 two-layer review**, p730 TTS, p740 duration fit, p750 audio QA/human handoff | deterministic arc + 5 semantic critics、current hashes、p750 explicit full-run approval | text/schema/TTS candidate/CAS/audio decode/timeline/duration は保持。p720 critic/aggregate/current-pass requirement を外す。p750 の人による candidate/timeline 選択を残すかは UI product decision として分離。|
| p800 video | p810 grounding, **p820 motion evaluator**, p830 requests, p840 generation, **p850 evaluator/exclusions** | p820/p850 5+1、per-item approval/stale gate、quality issues review | motion compiler, frame/reference binding, provider request/output checks を保持。semantic/video reviewer and pass report requirement を外す。人が候補を選ぶ場合の per-item selection は optional UI。|
| p900 render/QA | p910 render inputs, p920 final render, **p930 QA evaluator/runtime summary** | p930 5+1, QA score/pass, final review report | render normalization, ffprobe/decode/audio sync/file existence を保持。production quality reviewer/score/pass reportを必須にしない。公開 publish confirmation は別系統。|

`p110..p930` の全 fixed slot 列は `docs/how-to-run.md:285-294`。runner skill の p680 terminal
要求（全 slot terminal、review/handoff slot の `awaiting_approval` 制限）は
`.codex/skills/toc-immersive-runner/SKILL.md:112-130,234-255` と同じ列を再強制する。
slot を単に `passed` に偽装して残すと、review removal ではなく pseudo-review になるため、
review slot を削除/通常作業へ再定義し、legacy state の値は読み捨てる方針が必要。

## Grounding / audit と ordinary source-reading の境界

- `workflow/stage-grounding.yaml:1-10,11-74,76-149,151-192` は global/stage docs、template、
  input、`requires_approved_input`、required state/manifest phase の readset contract。
  required docs/templates/inputs の解決は通常 source-reading として保持できる。
- `docs/root-pointer-guide.md:182-189`, `docs/how-to-run.md:495-516`,
  `.claude/commands/toc/toc-run.md:27-39`, `.claude/commands/toc/toc-immersive-ride.md:89`,
  `.claude/commands/toc/toc-scene-series.md:59-65`, `.claude/agents/grounding-auditor.md:12-41`,
  `.codex/agents/grounding-auditor.toml:7-36` は `resolve -> audit ->
  stage.*.grounding.status=ready && stage.*.audit.status=passed` を強制する。
- `workflow/state-schema.txt:58-96,97-150,217-256,367-381` と
  `docs/data-contracts.md:117-240,769-815` は `stage.*.audit.*`、grounding report/readset、
  subagent prompt、`artifact.grounding.*` state keys を canonical catalog として持つ。
- 推奨分離: required docs/templates/inputs と実際の artifact 読み順・型/ID検証は保持し、
  audit-only agent、`*.audit.json` の pass requirement、`stage.*.audit.status` を stage開始/完了
  gate にする記述、`build-subagent-audit-prompt` の production 必須化を削除/optional 化する。
  これは readset を読むこと自体の削除ではない。

## Reviewer、critic、aggregator、score の具体契約

### Common evaluator loop

- `docs/data-contracts.md:441-502` — p130/p230/p320/p410b/p410c/p430/p540/p630/p640/p720/
  p820/p850/p930、5 critic、1 aggregator、max 5、`passed|changes_requested`、round artifact
  path、L2 が修正採否。
- `docs/system-architecture.md:67-72,311-374,401-408` — 同じ 5+1/max 5 と p720 semantic
  critics。p720 は deterministic projection と独立5 criticを別契約にしている。
- `docs/how-to-run.md:267-272,347-356,659-669` — loop起動、5+1、`eval.*` summary、p410b/c/p420
  roles、round prompt/report/aggregate path。
- `docs/implementation/agent-roles-and-prompts.md:43-50,216-250` — L2 が5+1を起動し、
  aggregator reportで canonical artifactを修正する supervisor contract。
- `docs/implementation/langgraph-topology.md:18-50` — older duplicate with same loop and retry
  policy。現行正本とともに更新必須。

### p410/p420 semantic reviewers

- `docs/script-creation.md:169-188,337-363` — scene count, dramatic/reveal, duration density,
  visual production, handoff の critic roles、Scene/Cut Blueprint Gate、review pass まで次へ
  進まない。
- `docs/implementation/scene-loop.md:71-111` — 同じ p410 5 critic + aggregator と blocking findings。
- `docs/implementation/cut-loop.md:93-123,135-164` — p420 aggregate gate と reason keys。
- `workflow/script-template.yaml:220-400` — `scene_set_review`, `scene_detail_review`,
  `cut_blueprint_review`, `production_readiness_review` の `review_policy`, `review_loop`,
  `agent_review`、critic assignment/gates/council。
- `workflow/scene-outline-template.yaml:31-65,107-121,179-189,527-534` —
  `scene_count_review_required`, `canonical_event_coverage_matrix`, validator-computed
  `authoring_preflight`、`coverage_review`。preflight/coverageの構造チェックは保持、review flagを外す。
- `workflow/cut-blueprint-template.yaml:1-8,78-120,437-470` — V3 cut contract は構造正本、
  `review` 下の agent/human/triangulation fields は reviewer artifact。contract fields は保持し、
  review blockを任意/削除。
- `workflow/cut-handoff-matrix-template.yaml:73-121`、`workflow/cut-downstream-review-template.yaml:1-90` —
  handoff/triangulation の boolean checks。cross-stage structural validator に再定義できるが、
  `status: passed|changes_requested|waived` や review report の必須性は外す。

### p500/p600 image review

- `docs/implementation/asset-bibles.md:50-72,105-117,119-153` — p540 review agent/critic/
  aggregatorとp570 approved gate。asset plan/reference/output compiler は保持。
- `workflow/asset-plan-template.yaml:9-21,23-63,65-139` — top-level `review_contract`,
  `done_when: human review approved`、各 asset の `review.status`。
- `workflow/p600-scene-image-batch-spec-template.md:90-104` — `review_gate.prompt_review_passed`,
  `continuity_review_passed`, `human_review_required/passed`, `unresolved_findings`。
- `workflow/playbooks/image-generation/reference-consistent-batch.md:10-18,21-42,75-100` —
  review script、`agent_review_ok`, false reason、human exception、rubric list/reason keys。
- `workflow/video-manifest-template.md:108-164,831-872,1194-1215,1331-1343` — request
  materialization review projection、per-cut image review/human review/rubric fields、quality check。
  `workflow/immersive-ride-video-manifest-template.md:135-161,187-210,280-298,374-392` と
  `workflow/immersive-cloud-island-walk-video-manifest-template.md:122-133,200-218` は同型の
  image/narration review comments/fields。
- `workflow/scene-video-manifest-template.md:21-105,316-326,658-666,821-846,897-915,1027-1028`
  — scene-run variantのp720 5 critics、per-cut review, approval audit metadata。
- `docs/implementation/image-prompting.md:219-315` — canonical `image_generation.review`
  field schema; `agent_review_ok`, reason key、rubric/overall score、human override、両false stop。

### p700 narration review

- `workflow/multiagent-immersive-narration-playbook.md:98-139,141-167` — p720 deterministic
  runner + 5 independent app-server semantic critics、critic artifact/aggregate/report/hash、
  p750 current pass + full-run human listen evidence。
- `workflow/immersive-ride-video-manifest-template.md:45-70`,
  `workflow/immersive-cloud-island-walk-video-manifest-template.md:35-60`,
  `workflow/video-manifest-template.md:72-99`, `workflow/scene-video-manifest-template.md:35-60`
  — duplicated `narration_workflow.arc_review`, `semantic_critic_review` (aggregate schema, critics,
  findings, report/json), `final_audio_review` hash/actor fields.
- `docs/implementation/video-integration.md:157-212`, `docs/script-creation.md:534-585` — same
  two-layer p720 and `narration_workflow.*` current hash requirement.
- `workflow/evaluation_criteria.md:37-50` — p720 deterministic/semantic five verdict requirement。

### p800/p900 review and scores

- `workflow/video-manifest-template.md:123-156,1076-1117` — video request `approval_request_flag`,
  per-item review state, approval audit metadata, reject pending/stale approval、quality_issues。
- `docs/video-generation.md:244-282,392-394,472-486` — materialized request approval identity,
  stale/quality issue blocking, review projection。
- `docs/orchestration-and-ops.md:344-358` — QA scores (`accuracy`, `engagement`, `consistency`,
  `overall`, threshold `.75`) と score-based rerun。
- `workflow/evaluation_criteria.md:62-104,106-113` — deterministic/rubric distinction、
  `passed_checks/total_checks` score、`eval_report.json` score/passed、standard final review。
- `workflow/state-schema.txt:402-469` — `eval.*.score`, status/findings, rubric scores for
  research/script/manifest/video/image_prompt/narration; `workflow/state-schema.txt:473-480` QA
  scores and runtime scene review state。
- `docs/data-contracts.md:267-279,521-539` — evaluator summaries, `score` as average overall,
  findings/unresolved entries, narration rubric.

## Supervisor contracts and what must survive

- `docs/system-architecture.md:50-70,260-272,376-425` and
  `docs/data-contracts.md:359-439` — L1 controls bucket order/stop target and only validates
  required artifact existence/state; L2 is bucket single writer for canonical artifact/state/index;
  L3 writes isolated output; `pXXX.supervisor_result.json` has `status`, `completed_slots`,
  `required_artifacts`, `state_keys`, `review_outputs`, `next_bucket`, `blocked_reason`.
- `docs/orchestration-and-ops.md:86-95,194-212` and `docs/how-to-run.md:254-266` — L2 progress
  memo only records L2 invocation; L3 review invocation is intentionally absent; grounding/readset
  and supervisor state keys are recorded.
- `docs/implementation/agent-roles-and-prompts.md:18-69,71-83` — same L1/L2/L3 ownership,
  including “L1 must not read body”, “L3 cannot approve”, and bucket map. Keep single-writer,
  artifact path handoff, state atomicity, and required artifact checks.
- Removal consequence: make `review_outputs` optional/empty or replace it with ordinary output
  inventory; remove “L3 critic/aggregator”, reviewer-specific task packets, and “aggregator decides
  gate close”. Do not remove L2 result/progress, required artifact existence, state/index ownership,
  locks, or source/request identity checks.

## Human review UI and manual selection (related, not equivalent)

- `docs/orchestration-and-ops.md:100-126`, `docs/data-contracts.md:283-357`,
  `docs/how-to-run.md:55-79` — frontend `review_mode` field, standard/preapproved labels,
  create_input persistence, p680 pending/done state. Remove the mode as reviewer switch and its
  pseudo-deterministic report, while deciding separately whether image handoff/status UI remains.
- `docs/implementation/image-prompting.md:124-153,307-315` — human exception reason and
  `human_review.change_requests[]`; preserve manual change input if desired, without requiring an
  agent finding or score.
- `docs/script-creation.md:498-527,586-651`, `docs/implementation/video-integration.md:213-276`
  — `script.md` narration source of truth, human_locked spans, candidate generation/listen, p740
  measured duration, p750 full-run approval. Candidate selection/listen is a product choice and
  should not be conflated with an automated production reviewer.
- `docs/video-generation.md:265-282,329-360,1091-1106` — human change request loop and request
  materialization/approval. Keep explicit user change data and request binding; remove mandatory
  reviewer report/pass dependency.
- `skills/vertical-shorts-creator/SKILL.md:12-24,27-37` — vertical short currently requires
  `review.video.status=approved` and exposes `approve-video`; this is a human final-OK dependency
  and must be updated or explicitly retained as a publishing choice, separately from critic removal.
- `.claude/agents/narration-writer.md:23-41` and `.codex/agents/narration-writer.toml:18-36` —
  human_locked text is protected and conflicts become `changes_requested`; preserve lock/edit
  semantics if manual narration editing remains.

## Workflow templates and playbooks (complete grouped list)

### Active production templates with review contracts

- `workflow/stage-grounding.yaml:1-192` — readset plus approved-input/required-state gate; split.
- `workflow/state-schema.txt:26-57,58-150,151-216,217-346,352-469,496-500` — review/eval/
  grounding/supervisor keys; delete reviewer-only keys and keep ordinary state/storage keys.
- `workflow/evaluation_criteria.md:1-117` — evaluator criteria, p720 five verdicts, score formula,
  eval report/pass; delete reviewer scoring/pass requirements.
- `workflow/story-template.yaml:43-49,80-125,274-289` — `subagent_trace` audit roles,
  candidate score rationale, hybrid approval, `quality_scores`; preserve source/creative boundary
  and optional human safety approval, remove mandatory score/reviewer trace.
- `workflow/script-template.yaml:173-180,182-210,212-400,472-537,972-993` — subagent trace,
  human changes, scene/cut/production review blocks, per-scene review policy/loop/agent status;
  keep scene/cut contracts and human change payload, remove reviewer requirement.
- `workflow/scene-outline-template.yaml:31-65,107-121,133-142,179-189,492-534` — review-required
  scene strategy, human approval flags, validator preflight and coverage booleans; keep deterministic
  preflight/coverage, remove review-required/approved status.
- `workflow/asset-plan-template.yaml:9-21,23-63,65-139` — asset review contract and four
  per-asset review statuses; keep asset identity/generation plan/output fields.
- `workflow/cut-blueprint-template.yaml:1-8,78-120,437-470` — V3 contract plus review and
  triangulation block; keep V3 structural contract, remove reviewer status/pass block.
- `workflow/cut-handoff-matrix-template.yaml:73-121` — handoff and scene-level booleans; retain as
  optional structural checks, remove mandatory review interpretation.
- `workflow/cut-downstream-review-template.yaml:1-90` — p600/p700/p800 triangulation report and
  status; either delete review artifact or retain as a non-gating structural consistency report.
- `workflow/video-manifest-template.md:38-52,72-99,100-164,469-485,852-872,1076-1117,1194-1215,1331-1343`
  — scene acceptance projection, narration workflow, promotion/review fields, coverage, per-item
  image/video/audio review, quality check. Preserve manifest/compiler/request binding; remove
  reviewer/aggregate/pass/score fields and conditions.
- `workflow/immersive-ride-video-manifest-template.md:45-70,135-161,187-210,280-298,374-392`
  and `workflow/immersive-cloud-island-walk-video-manifest-template.md:35-60,122-133,176-218` —
  direct experience templates with p720 5-critic block and per-node review fields.
- `workflow/scene-video-manifest-template.md:21-105,316-326,658-666,821-846,897-915,1027-1028` —
  scene-run manifest duplicate with p720 semantic critics, approval audit metadata, and per-cut review.
- `workflow/p600-scene-image-batch-spec-template.md:90-104` — p600 review gate; retain item/path/
  execution rules, remove review gate from generation prerequisite.
- `workflow/asset-inventory-template.yaml:1-26`, `workflow/scene-evidence-template.md:1-23`,
  `workflow/scene-conte-template.md:1-183`, `workflow/scene-script-template.md:1-76`,
  `workflow/cut-conte-template.md:1-96`, `workflow/visual-value-template.yaml:1-215` — adjacent
  production handoff/authoring templates with no independent 5+1 reviewer contract. Keep their
  ordinary source, identity, and downstream fields; remove only any wording that makes a review
  artifact a prerequisite if later edits add that dependency.

### Active playbooks whose review wording can reintroduce the loop

- `workflow/multiagent-immersive-narration-playbook.md:98-139,141-167` — direct p720 5 critics,
  semantic aggregate, hash/currentness, p750 review. Update/remove phase 4 reviewer execution while
  preserving full-run narration authoring, TTS, candidate/timeline handling.
- `workflow/playbooks/image-generation/reference-consistent-batch.md:10-18,21-42,75-100` —
  direct image review script, reason/rubric/false-pass rules. Keep batch/reference/continuity and
  ordinary prompt checks; remove agent/human approval gate.
- `workflow/playbooks/video-generation/kling.md:35-53,92-103,137-173,223-245` — review-only
  source/digest and `quality_issues` blocking. Keep compiler/provider/request binding; decouple
  review visibility from reviewer invocation.
- `workflow/playbooks/video-generation/first-last-frame-chained.md:18-22,41-50` and
  `workflow/playbooks/scene-production/first-last-frame-continuity.md:6-14` — re-review/re-approve
  after chain frame. Keep rematerialization and frame hash consistency; make review optional.
- `workflow/playbooks/script/visual-value-midroll-pass.md:14-28`,
  `workflow/playbooks/script/philosophical-cloud-island-walkthrough.md:27-36`,
  `workflow/playbooks/script/hero-journey-beat-first.md:15-39` — “quality gate” authoring heuristics.
  Keep content design checks if they are not machine review/pass requirements; remove reviewer wording
  if they become mandatory production gates.
- `workflow/multiagent-immersive-cuts-playbook.md:1-68` — explicitly legacy/non-canonical, no
  current reviewer loop; leave out of deletion and label as legacy compatibility.
- `workflow/multiagent-scene-series-playbook.md:1-50` — simple legacy scene-series scratch/
  single-writer flow; no production critic contract. Keep unless a separate scene-series migration.
- `workflow/review-template.md:1-489` and `workflow/task-template.md:224-226,308-324` — generic
  code review/task templates, not ToC production reviewer contracts; exclude.
- `workflow/research-template.yaml:10-138` and `workflow/research-template.production.yaml:14-188` —
  source confidence/curiosity/completeness/engagement metadata and research material thresholds;
  preserve as source-reading/content metadata unless the product explicitly removes all research
  scoring. They do not require a critic/aggregate pass.

## Skills, agents, commands, and installed copies

### Repo `skills/`

- `skills/toc-research/SKILL.md:8-11` — resolver + grounding-ready requirement; keep reading docs and
  source trace, remove audit/pass prerequisite.
- `skills/toc-scene-design/SKILL.md:8-11` — same for story authoring.
- `skills/toc-image-prompt/SKILL.md:8-11` — same for image prompt authoring; “approved upstream”
  wording should become current upstream/structural input if review is removed.
- `skills/toc-narration/SKILL.md:8-11` — script grounding; keep source alignment, remove audit/pass.
- `skills/toc-video-gen/SKILL.md:8-11` — grounding plus image/narration approval prerequisite;
  remove approval prerequisite, retain manifest/provider/structural checks.
- `skills/vertical-shorts-creator/SKILL.md:12-24` — human final approval prerequisite; related UI,
  not the critic loop. Decide separately.
- `skills/selfhelp-trend-researcher/SKILL.md:77-85` — confidence score/TODO caution for research;
  retain. `skills/folktale-researcher/SKILL.md:21-40,47-69` and
  `skills/era-explainer/SKILL.md:38-74` are source/sensitivity authoring, no reviewer gate.
- `skills/improve-workflow/SKILL.md:5,22-28` and `skills/youtube-studio-upload/SKILL.md:54-92` —
  generic development review / publishing human confirmation; exclude from production reviewer
  deletion.

### Production-specific `.agents/` / `.codex/` / `.claude/`

- `.agents/skills/frontless_review/SKILL.md:10-24,26-33,79-110,124-140` — ToC headless production
  review skill; requires regression report and p400/prompt aggregate artifacts. Delete/update as a
  production-review automation, while preserving route identity/cut_contract/motion separation
  structural checks if still useful.
- `.codex/skills/toc-immersive-runner/SKILL.md:24-69,71-79,83-147,149-167,169-232,234-258` —
  active Codex entrypoint: mandatory semantic reviewer, review-loop materialization, p100-p680
  terminal slots, p680 `review.image`/`gate.image_review`. This is the highest-risk reintroduction
  source; keep runner orchestration and ordinary output/provenance checks, remove review execution,
  review slot list, and mandatory p680 review state.
- `.codex/skills/toc-p500-bootstrap-image-runner/SKILL.md:37-45,47-71,66-83` — bootstrap asset
  cannot be canonical until `review.status=approved` and stops for human review. Keep no-reference
  lane and output import; make promotion based on generated output/optional user selection.
- `.codex/skills/toc-p600-image-runner/SKILL.md:21-53,71-99,108-118` — mostly planner/adapter;
  references “planning/review” and approved cut images but no full reviewer loop. Keep batch/path/
  provider rules, remove approval language only if it remains a blocker.
- `.codex/skills/toc-no-reference-image-runner/SKILL.md:57-82,84-96` — optional `review_status`
  field only; retain no-reference routing and fit checks.
- `.codex/skills/toc-resume-p500/SKILL.md:20-36,61-97,101-136,162-187,191-230` — resume router
  requires strict p400/p650 review/readiness and rematerializes p400 review artifacts. Keep lease,
  provenance, stale quarantine, p650/p500 boundary selection and ordinary validation; remove review
  artifact/pass/currentness as resume blockers.
- `.codex/skills/codex-parallel-image-batch/SKILL.md:109-131` — explicitly delegates “review gates
  before generation” to caller; generic skill is not a deletion target, but callers above must change.
- `.claude/commands/toc/toc-run.md:27-39` — mandatory resolve/audit/pass. Legacy command mirror;
  update if command remains usable.
- `.claude/commands/toc/toc-immersive-ride.md:77-89,100-166` — stage target p100..p900,
  grounding audit, p680/p750 handoff and final `review.video.status=pending`/human approve. Legacy
  compatibility command; remove reviewer/audit prerequisites while preserving stage routing.
- `.claude/commands/toc/toc-scene-series.md:59-71` — grounding/audit pass; legacy command.
- `.claude/commands/toc/toc-world-walk.md:17-21,32-50` — `--review-policy strict|drafts`, p450
  handoff and direct frontend p680 note; update mode/stop semantics.
- `.claude/commands/toc/toc-youtube-thumbnail.md` — no production review contract found; retain.
- `.claude/skills/**` contains the generic vendor/development skills mirrored from
  `.agents/skills/**`; no ToC-specific production review skill was found there. `.agents/skills/**`
  is likewise generic except for `frontless_review` above. Keep these paths out of the production
  reviewer deletion except for explicit ToC references.

### Mirrored role agents (same content, different wrapper/line offsets)

Codex is the active role pack; Claude files are compatibility mirrors. The body differs only by
frontmatter/TOML wrapper and line offsets, so every pair must be synchronized:

| role | Claude mirror | Codex mirror | relevant contracts |
|---|---|---|---|
| research | `.claude/agents/deep-researcher.md:29-50,91-110` | `.codex/agents/deep-researcher.toml:24-45,86-105` | source-count/facts thresholds, curiosity score, grounding audit/pass; keep source gathering, remove audit/pass and production scoring gate. |
| story | `.claude/agents/director.md:25-57` | `.codex/agents/director.toml:20-52` | multi-candidate score selection, hybrid approval, grounding audit/pass; keep source trace/hybrid safety, remove score-driven reviewer requirement. |
| grounding | `.claude/agents/grounding-auditor.md:10-41` | `.codex/agents/grounding-auditor.toml:5-36` | audit-only agent and `grounding.status=ready` + `audit.status=passed`; delete/retire if audit requirement is removed. |
| script | `.claude/agents/immersive-scriptwriter.md:16-29,36-47,61-65` | `.codex/agents/immersive-scriptwriter.toml:11-23,31-41,55-59` | script/image/video grounding audits and manifest authoring; keep authoring/source projection, remove audit gate. |
| narration | `.claude/agents/narration-writer.md:23-41,48-65` | `.codex/agents/narration-writer.toml:18-36,43-61` | human_locked preservation and source/TTS authoring; retain manual lock semantics, remove `changes_requested` as an automated reviewer result if no reviewer remains. |
| visual value | `.claude/agents/visual-value-ideator.md:20-66` | `.codex/agents/visual-value-ideator.toml:20-58` | visual planning/handoff only; no mandatory production reviewer. |
| scene evidence/script | `.claude/agents/scene-evidence-researcher.md:11-48`, `.claude/agents/scene-scriptwriter.md:29-62` | `.codex/agents/scene-evidence-researcher.toml:11-44`, `.codex/agents/scene-scriptwriter.toml:29-58` | ordinary research/source and scene authoring; retain. |
| series | `.claude/agents/series-planner.md:11-36` | `.codex/agents/series-planner.toml:11-31` | extraction/planning only; retain. |

Generic `.claude/agents/{code-reviewer,go-reviewer,database-reviewer,security-reviewer,build-error-resolver,planner,...}`
and corresponding `.codex/agents/*.toml` are software-development tooling, not ToC production
reviewers. Exclude them explicitly. `.claude/worktrees/**` is a separate checkout and was excluded.

### Repo-external installed stage skill copies

These are real regular files, not symlinks, and are outside the writable repo scope. They currently
match the short repo skills and retain old grounding/approval wording:

- `/Users/kantaro/.codex/skills/toc-research/SKILL.md:8-11` — grounding-ready before writing.
- `/Users/kantaro/.codex/skills/toc-scene-design/SKILL.md:8-11` — grounding-ready before writing.
- `/Users/kantaro/.codex/skills/toc-narration/SKILL.md:8-11` — grounding-ready before writing.
- `/Users/kantaro/.codex/skills/toc-image-prompt/SKILL.md:8-11` — grounding-ready before writing.
- `/Users/kantaro/.codex/skills/toc-video-gen/SKILL.md:8-11` — grounding-ready plus image/narration
  approvals before video generation.

They must be synchronized/reinstalled after the repo contract changes; do not edit them as part of
this report task.

## Reintroduction risks / search sentinels

After implementation, search the current checkout and installed copies for these exact families;
ordinary `review_only` metadata and structural validation should be reviewed by context, not blindly
deleted:

1. `review_mode`, `preapproved`, `deterministic_preapproval`, `runtime.review_policy`,
   `gate.*_review`, `review.*.status`, `agent_review_ok`, `human_review_ok`, `rubric_scores`,
   `overall_score`, `eval.*.score`.
2. `critic_1`..`critic_5`, `5 critic`, `aggregat(ed|or)`, `max_rounds: 5`,
   `evaluator-improvement`, `semantic_critic_review`, `narration_workflow.arc_review`.
3. `stage.*.audit.status=passed`, `audit-stage-grounding.py`, `build-subagent-audit-prompt.py`,
   `*.audit.json`, `review_outputs`, `reviewed_entries`, `review-integrity`, `review currentness`.
4. Review-only artifact names: `*_review.md`, `aggregated_review.md`,
   `logs/review/semantic/`, `logs/review/*judgment*`, `logs/eval/*/round_*`, and state keys
   `eval.<stage>.loop.*`.
5. Human UI blockers that are intentionally separate: `human_locked`, candidate listen/select,
   `human_change_requests[]`, explicit hybridization approval, p750 timeline approval, publish
   confirmation. Verify whether each remains user-facing before removing.

The most likely stale-copy order is: root guide → system/data/orchestration docs → script/image/
narration/video implementation docs → workflow state/evaluation/templates → Codex runner/resume →
Claude command/agent mirrors → installed `/Users/kantaro/.codex/skills` copies. Updating only
`preapproved` behavior leaves the same reviewer/audit contract active through the standard path.
