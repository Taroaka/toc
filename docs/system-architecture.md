# System Architecture (MVP)

This document captures the architecture decisions for the MVP and the path to
future cloud deployment. It corresponds to todo item 1 in `todo.txt`.

## Scope and assumptions

- Orchestration uses LangGraph.
- MVP is single-user, local-first.
- Input: story title. Output: artifacts under `output/<topic>_<timestamp>/`.
- External model providers are optional; mock providers are acceptable for MVP.

## Decision summary

| Area | Decision | Rationale |
| --- | --- | --- |
| Deployment mode | Local-only MVP | Fast iteration, zero infra |
| Execution model | L1 Run Orchestrator + L2 P-Bucket Supervisors + L3 task/review agents | Keeps the run gate-driven while moving long stage context out of the L1 context |
| Storage | Filesystem object store + PostgreSQL metadata DB | Durable metadata |
| Job queue | In-process async queue | Simple and sufficient for MVP |
| State management | Append-only `state.txt` in project folder (no DB checkpoints) | Human-readable recovery |
| Providers | LLM via LangChain; image=Codex built-in image generation (`codex_builtin_image` / gpt-image-2); video=Kling 3.0 (default) / Seedance (alt); TTS=ElevenLabs（Veo is disabled for safety） | Avoid vendor lock-in |
| API boundary | Codex-primary assistant command (Claude Code slash command compatible) | Keep surface area small |
| Review policy | Decide at run start and persist in `state.txt` | Stage grounding and orchestrators must share one approval contract |
| Authoring review slots | Maximum-5-round evaluator-improvement loop with 5 critics + 1 aggregator per round | Keep authoring quality gates reproducible inside the owning p-bucket supervisor |

## Component diagram

```mermaid
graph TD
  AC[Assistant Command: Codex primary / Claude compatible] --> ORCH[LangGraph Orchestrator]
  ORCH --> L1[L1 Run Orchestrator]
  L1 --> L2[P-Bucket Supervisor p100-p900]
  L2 --> L3[Task / Review Agents]
  L3 --> WORKERS[Workers]
  WORKERS --> PROVIDERS[Image/Video/TTS/LLM Providers]
  ORCH --> META[Metadata DB (PostgreSQL)]
  ORCH --> STATE[State File (state.txt)]
  PROVIDERS --> OBJ[Object Store (filesystem)]
  OBJ --> ARTIFACTS[Artifacts: research/story/script/video]
```

## Deployment mode

- MVP: local-only, Codex 主軸の assistant command で起動（Claude Code slash command 互換も維持）。
- Future: containerized deployment with dev/staging/prod environments.

## Execution model

- Single-node orchestrator runs the LangGraph, but run authorship is split by p-bucket.
- L1 Run Orchestrator owns bucket order, stop target, human approval boundaries, and bucket completion validation.
- L2 P-Bucket Supervisor owns one `p100` bucket at a time and is the single writer for that bucket's canonical artifacts, `state.txt` slot updates, and `p000_index.md` refresh.
- L3 task/review agents run under the active L2 supervisor and write only isolated reports, scratch outputs, review artifacts, or generated media requested by the supervisor.
- Long-running tasks executed via in-process worker pool (async + process/thread).
- Concurrency default: 2 workers; configurable via `config/system.yaml`.
- Parallelism policy (MVP):
  - Core flow is sequential and gate-driven.
  - Production order is fixed as:
    - `RESEARCH -> STORY -> VISUAL_PLANNING -> SCRIPT -> ASSET -> SCENE_IMPLEMENTATION -> NARRATION -> VIDEO -> RENDER_QA`
  - L1 never reads the body of bucket output artifacts to decide the next bucket. It checks `logs/orchestration/pXXX.supervisor_result.json`, required artifact existence, and terminal slot state only.
  - Parallelism is allowed only inside a stage whose upstream gate is already complete.
    - `ASSET`: recurring still generation can run in parallel.
    - `SCENE_IMPLEMENTATION`: image generation can fan out per cut after manifest is `production`.
    - `VIDEO`: clip generation can fan out after still inputs and duration gates are complete.
  - Authoring-after review slots use bounded review parallelism:
    - each round launches 5 independent critic agents against the same artifact/readset
    - 1 aggregator agent merges critic findings into the round gate result
    - maximum 5 rounds; unresolved findings after round 5 require human review or explicit override

## Storage strategy

- Object storage (artifacts): filesystem at `output/`.
- Metadata DB: PostgreSQL (local or managed).
- Paths are configured in `config/system.yaml`.

## Job queue / executor

- In-process queue with worker pool.
- Tasks are stage-scoped (RESEARCH, STORY, SCRIPT, NARRATION, ASSET, SCENE_IMPLEMENTATION, VIDEO, RENDER, QA).
- Retry logic is handled at the LangGraph edge level (future task).

## Task granularity (MVP)

- Base unit is a stage task aligned to LangGraph nodes:
  - `RESEARCH` → produces `research.md`
  - `STORY` → produces `story.md`
  - `SCRIPT` → produces `script.md` and a production skeleton `video_manifest.md`
  - `ASSET` → produces reusable recurring still assets
  - `SCENE_IMPLEMENTATION` → produces the production manifest and scene still outputs
  - `NARRATION` → produces reviewed TTS audio and confirmed runtime duration
  - `VIDEO` → produces motion clips
  - `RENDER` → produces `video.mp4`
  - `QA` → produces final review outputs
- Scene-level tasks exist inside `SCRIPT`, `SCENE_IMPLEMENTATION`, and `VIDEO`:
  - `SCRIPT` subtask: draft one scene and narration beat from the approved story plan.
  - `SCENE_IMPLEMENTATION` subtask: implement one approved scene/cut into production prompt fields.
  - `VIDEO` subtask: generate motion clips for an approved scene/cut.
- Asset-level tasks are split by stage:
  - `ASSET`: character/object/location reference stills.
  - `SCENE_IMPLEMENTATION`: cut still generation.
  - `NARRATION`: TTS generation and duration fit checks.
  - `VIDEO`: clip generation.
- Granularity principles:
  - Keep core flow sequential and gate-driven.
  - Only split tasks where outputs are independently verifiable.
  - Retries should target the smallest failing unit (scene or asset), not the whole job.

## State management

- 状態は `output/<topic>_<timestamp>/state.txt` に **追記型** で記録する。
- 最新ブロックが現在状態、過去ブロックをコピーして擬似的にロールバック可能。
- run 進行は固定の `p100` 〜 `p900` slot contract で管理する。
  - slot の意味は全 story で共通で、story ごとの差分は `slot.pXXX.status` / `slot.pXXX.requirement` / `slot.pXXX.skip_reason` / `slot.pXXX.note` で表す。
  - `p000_index.md` はこの固定 contract を run progress の source of truth として要約する。
- review 要否も run 開始時に固定する。
  - `review.policy.story=required|optional`
  - `review.policy.image=required|optional`
  - `review.policy.narration=required|optional`
- stage grounding は上記 policy を読んで、承認を必須にするかどうかを決める。
- audio runtime は TTS 実行後の実尺を正本にし、`cinematic_story` は既定で 300 秒以上を target とする。
  - target 未満なら scene / narration stretch review prompt を生成して停止し、人レビューへは進めない。
- production order は asset/image-first を採用する。
  - `script` で scene / narration draft を確定したあと、`video_manifest.md` はまず `manifest_phase: skeleton` で materialize する。
  - その後に `asset -> scene implementation / image -> narration -> video -> render -> qa` の順で進める。
  - 理由は、asset と scene image を先に確定し、実際の visual に合わせて narration と video を仕上げるため。
- したがって「script draft までは人承認なしで進める」のような運用差分は、prompt の解釈ではなく run 初期 state で表現する。
- チャット起点の stage 実行も同じ state / grounding 契約の上で扱う。
  - `resolve-stage-grounding.py` で contract を解決
  - `audit-stage-grounding.py` で readset を監査
  - `logs/grounding/<stage>.readset.json` を「読むべき対象の正本」とする
  - これにより slash command とチャット実行の前提を揃える
- authoring 直後の review slot は、単発 review ではなく最大 5 round の evaluator-improvement loop とする。
  - 1 round は 5 critic agents + 1 aggregator で構成する
  - critic / aggregator は `state.txt`、`p000_index.md`、canonical artifact を直接編集しない
  - 担当 L2 P-Bucket Supervisor が aggregator report を読み、採用する修正だけを担当 bucket の canonical artifact に反映する
  - round 5 後も `changes_requested` の場合は `eval.<stage>.loop.status=changes_requested` で停止し、人間 review / override を待つ

## Run-Level Supervisor Architecture

ToC run 全体は、OpenAI Agents SDK の orchestration / handoff の考え方に合わせて、所有権を3階層に分ける。これは SDK への全面移行を意味しない。Codex-native 運用でも、長い文脈を L2 supervisor に閉じ込め、L1 は handoff artifact だけを見る。

### L1 Run Orchestrator

- 入力: user request / stop target / `state.txt` / `p000_index.md` / bucket supervisor result
- 出力: 次 bucket の task packet / run-level stop or blocked decision
- 責務:
  - `p100 -> p200 -> ... -> p900` の順序と coarse stop target を解決する
  - 各 bucket の L2 supervisor を fresh context で起動し、完了まで待機する
  - L2 supervisor 起動時に `logs/orchestration/l2_supervisor_progress.md` へ `invoked` event を追記する
    - helper: `python scripts/record-l2-supervisor-progress.py --run-dir <run_dir> --bucket p600 --event invoked --stop-slot p680`
  - L2 supervisor が返った後に、同じ helper で `returned|blocked|failed` と result path を追記する
    - terminal event では `--result logs/orchestration/pXXX.supervisor_result.json` を必ず渡す
  - bucket 完了時は `logs/orchestration/pXXX.supervisor_result.json`、required artifact existence、terminal slot state だけを検証する
  - human review、frontend handoff、hybridization approval を自動承認しない
  - 本文 artifact（例: `research.md`, `story.md`, `script.md`, `video_manifest.md`）を次 bucket 判定のために読まない
- 禁止:
  - L2 の代わりに canonical artifact を統合する
  - L3 critic / aggregator report を直接読み込んで修正判断する
  - bucket 内の未記録会話文脈を次 bucket へ渡す
  - L3 task / review agents の起動履歴を run-level progress memo に膨らませる

### L2 P-Bucket Supervisor

- 入力: L1 task packet / stage readset / upstream artifact paths / bucket stop slot
- 出力: canonical artifact updates / `state.txt` slot updates / `p000_index.md` refresh / `logs/orchestration/pXXX.supervisor_result.json`
- 責務:
  - 担当 bucket 内では single writer として動く
  - `prepare-stage-context.py` または同等の grounding preflight で readset を確定する
  - 必要な L3 task/review agents を起動し、isolated outputs を採否判断する
  - authoring-after review loop の round 管理、修正採否、gate close / human handoff を担当する
  - bucket 最終 slot まで進んだら supervisor result を書き、L1 へ完了を返す
- 禁止:
  - 他 bucket の canonical artifact を編集する
  - L1 に本文 artifact の精読を要求する
  - approval gate を自動承認する

### L3 Task / Review Agents

- 入力: artifact path / readset path /目的 / isolated output path
- 出力: `scratch/`, `logs/`, review artifacts, generated media, or explicit report only
- 責務:
  - research scout、story candidate、visual audit、scene/cut worker、critic、aggregator、grounding auditor、image/video/narration reviewer などを担当する
  - 親会話の未記録文脈に依存しない
  - canonical artifact、`state.txt`、`p000_index.md` を直接編集しない。ただし生成メディアの materialization など、L2 が明示した isolated output は書いてよい

### Bucket Handoff Contract

各 bucket supervisor は完了時に次を満たす。

- L1 が `logs/orchestration/l2_supervisor_progress.md` に L2 supervisor 呼び出しを記録済みである
- `logs/orchestration/pXXX.supervisor_result.json` を書く
- `status` は `done|blocked|failed`
- `completed_slots` に担当 bucket の terminal slot を列挙する
- `required_artifacts` に L1 validator が存在確認すべき artifact を列挙する
- `state_keys` にその bucket が更新した主要 state key を列挙する
- `review_outputs` に review loop / human handoff artifact を列挙する
- `next_bucket` または `blocked_reason` を明示する

L1 validator はこの result と slot state を検証して次 bucket に進む。artifact 本文の品質判断は L2 supervisor と L3 review loop の責務である。

## Fixed P-Slot Contract

変更内容:
- fixed `p-slot` contract を production order に合わせて再編した。
- 後半順序は `p500 asset -> p600 scene/image implementation -> p700 narration/audio -> p800 video -> p900 render` に固定する。
- `p450` を追加し、`video_manifest.md` を production skeleton manifest として先に materialize する。

修正理由:
- asset と scene image を先に確定し、実際の visual に合わせて narration と video を仕上げる。
- 尺が target 未満のとき、padding で誤魔化さず narration / video の再設計へ戻れるようにするため。

旧仕様との差分:
- 旧仕様では `p500 narration/audio -> p600 asset -> p700 scene implementation -> p800 video` だった。
- 新仕様では asset/image-first に切り替え、narration は video の直前へ移動した。

`visual_value` は p300 visual planning を grounding / state で追跡するための stage key であり、canonical generation stage ではない。canonical p300 done 条件は `docs/data-contracts.md` の "Canonical p300 done 条件" を正本とする。

- `p100` ごとに大工程を固定する。
- `p110` 以降の細番号も全作品で固定契約として扱う。
- 作品差分は slot meaning を変えず、`slot.<code>.status` / `slot.<code>.requirement` / `slot.<code>.skip_reason` / `slot.<code>.note` で表す。
- `p000_index.md` は fixed slot contract に基づく run-local source-of-truth とする。
- slash / stage target で `p100` / `p300` のような 100 番台の coarse p-number を指定した場合は、stage 開始 slot ではなく、対応 stage の human-review handoff slot まで進める。
- coarse stage target resolution:
  - `p100` -> `p130`
  - `p200` -> `p230`
  - `p300` -> `p330`
  - `p400` -> `p450`
  - `p500` -> `p570`
  - `p600` -> `p680`
  - `p700` -> `p750`
  - `p800` -> `p850`
  - `p900` -> `p930`
- 細番号 target（例: `p450`）はその slot を直接指す。

標準 slot:

- `p100`: research
  - `p110`: grounding
  - `p120`: authoring
  - `p130`: evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
- `p200`: story
  - `p210`: grounding
  - `p220`: authoring
  - `p230`: evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
- `p300`: visual planning
  - `p310`: visual value authoring (`visual_value.md`)
  - `p320`: visual planning evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p330`: p400 / p600 / p700 handoff appendix
  - done when: see `docs/data-contracts.md` "Canonical p300 done 条件"
- `p400`: scene/cut design / script / narration text / human changes
  - `p410`: scene completion gate（grounding + scene-set review + per-scene review）
  - `p420`: cut blueprint / script authoring
  - `p430`: evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p435`: production readiness council（Structure / Duration / Quality / Orchestrator は意見側、Design Owner だけが後段設計書を編集）
  - `p440`: human changes / narration sync
  - `p450`: skeleton manifest materialization
- `p500`: asset
  - `p510`: asset grounding
  - `p520`: reusable asset inventory
  - `p530`: asset plan authoring
  - `p540`: asset evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p550`: asset requests
  - `p560`: asset generation
  - `p570`: asset continuity check
- `p600`: scene implementation / image
  - `p610`: scene implementation grounding
  - `p620`: production manifest / prompt authoring
  - `p630`: hard scene evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p640`: judgment evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p650`: generation ready
  - `p660`: image generation
  - `p670`: image QA / fix loop
  - `p680`: image human review handoff
- `p700`: narration / audio runtime
  - `p710`: narration grounding
  - `p720`: narration text evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p730`: TTS request / generation
  - `p740`: duration fit gate
  - `p750`: audio QA / human review handoff
- `p800`: video
  - `p810`: video grounding
  - `p820`: motion / video evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p830`: video requests
  - `p840`: video generation
  - `p850`: video evaluator-improvement review loop / exclusions (max 5 rounds; 5 critics + 1 aggregator per round)
- `p900`: render / QA / runtime
  - `p910`: render inputs
  - `p920`: final render
  - `p930`: QA evaluator-improvement review loop / runtime summary (max 5 rounds; 5 critics + 1 aggregator per round)

## Subagent Orchestration Policy

メインエージェントという単一の巨大 context は使わない。run 全体は L1 Run Orchestrator が順序と handoff を管理し、各 `p100` 番台は L2 P-Bucket Supervisor が bucket single writer として担当する。従来 subagent と呼んでいた細かい作業者は L3 Task / Review Agents として L2 配下に置く。

呼び出し条件:

- stage grounding が `ready`、audit が `passed`
- 入力 artifact が存在し、stage readset に含まれている
- task が scene / cut / review / evidence のように境界分割できる
- 出力先が `scratch/`、`logs/`、review artifact、または明示された isolated path

slot ごとの標準分担:

| Slot | L2 supervisor の所有範囲 | L3 task/review agents に任せてよい作業 |
| --- | --- | --- |
| `p100` research | `research.md` への統合、source trace、slot 更新、supervisor result | research scout / evidence collector / research critic |
| `p200` story | `story.md` 確定、hybridization 承認確認、slot 更新、supervisor result | story candidate / source-vs-creative audit / story critic |
| `p300` visual planning | `visual_value.md` 統合、story との矛盾確認、p400/p500/p600/p700 handoff 確認 | visual-value draft / visual payoff audit / anchor-reference-risk audit |
| `p400` script | `script.md` と skeleton manifest の統合、p400 review loops、slot 更新 | scene draft / narration draft / structure-duration-quality council |
| `p500` asset | asset plan 採用、request 発行、asset generation、canonical asset 更新 | asset brief / coverage review / continuity review / image generation workers |
| `p600` scene implementation | production manifest 統合、scene requests、scene image generation、image handoff | scene/cut prompt rewrite / image prompt judgment / image QA |
| `p700` narration | p710-p750 の bucket single writer。TTS 実行判断、duration gate、manifest 反映、audio handoff | narration review / duration stretch review / TTS workers |
| `p800` video | 採用判定、manifest 更新、除外理由の記録、video handoff | clip generation fan-out / clip review |
| `p900` render / QA | final report 生成、完了判定、run closeout | QA reviewer / runtime summary review |

Authoring-after review loop の標準分担:

- critic agents: 5 agents per round。rubric finding と修正候補を isolated report に出す
- aggregator: 1 agent per round。5 critic reports を統合し、`passed|changes_requested` と unresolved findings を返す
- L2 supervisor: aggregator report を根拠に担当 bucket の canonical artifact を更新し、次 round 実行または gate close を決める
- max rounds: 5。round 5 後の unresolved finding は human review / explicit override に回す

禁止事項:

- `state.txt` を置き換える、または subagent が直接 final status を確定する
- hybridization を自動承認する
- 複数 subagent に `story.md` / `script.md` / `video_manifest.md` を同時編集させる
- 親会話だけにある未記録情報へ依存する
- evidence なしの事実追加を canonical artifact に入れる

統合手順:

1. L2 supervisor が L3 output を読む
2. 担当 bucket の canonical artifact に採用する差分を選ぶ
3. `state.txt` に prompt / output / review summary を append する
4. verifier または stage review を通す
5. finding が残る場合は、修正 task を再度 bounded L3 agent に渡す
6. bucket 完了時に `logs/orchestration/pXXX.supervisor_result.json` を書く

## Model/providers

- Provider interfaces for image, video, TTS, and LLM.
- LLM integration uses LangChain.
- Image: Codex built-in image generation（`codex_builtin_image` / `gpt-image-2`）
- External image providers are disabled for standard repo workflows
- Video: Kling 3.0（default。`video_generation.tool: kling_3_0`）
- Video (omni): Kling 3.0 Omni（`video_generation.tool: kling_3_0_omni`）
- Video (alt): Seedance（BytePlus ModelArk。`video_generation.tool: seedance`）
- Note: Google Veo は安全のためこのリポジトリでは無効化している。
- TTS: ElevenLabs
- Image provider is fixed to Codex built-in image generation for p500 / p600. Video, TTS, and LLM providers can still be swapped through configuration without changing orchestration logic.

## API boundaries / module ownership

- MVP: Codex 主軸の assistant command が起点（Claude Code slash command 互換も維持）。
- CLIやHTTPサーバは対象外（将来拡張）。
- Proposed internal modules:
  - `app/orchestrator`: LangGraph topology and run logic
  - `app/providers`: image/video/tts/llm adapters
  - `app/storage`: object store + metadata DB access
  - `app/queue`: in-process queue + worker pool
  - `app/cli`: CLI entrypoint

## Config source of truth

- `config/system.yaml` defines the defaults for the MVP.
- Environment overrides are expected in later tasks.

## Open questions

- Which cloud provider to standardize on (AWS/GCP/etc.)?
- ElevenLabs の voice/model/output_format の標準（日本語品質/速度/コスト）
- Preferred trade-off: cost vs quality vs latency?
