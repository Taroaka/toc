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
| Execution model | Single-node orchestrator + in-process workers | Lowest complexity for MVP |
| Storage | Filesystem object store + PostgreSQL metadata DB | Durable metadata |
| Job queue | In-process async queue | Simple and sufficient for MVP |
| State management | Append-only `state.txt` in project folder (no DB checkpoints) | Human-readable recovery |
| Providers | LLM via LangChain; image=Google Nano Banana 2 / Gemini 3.1 Flash Image; video=Kling 3.0 (default) / Seedance (alt); TTS=ElevenLabs（Veo is disabled for safety） | Avoid vendor lock-in |
| API boundary | Codex-primary assistant command (Claude Code slash command compatible) | Keep surface area small |
| Review policy | Decide at run start and persist in `state.txt` | Stage grounding and orchestrators must share one approval contract |
| Authoring review slots | Maximum-5-round evaluator-improvement loop with 5 critics + 1 aggregator per round | Keep authoring quality gates reproducible while preserving one canonical writer |

## Component diagram

```mermaid
graph TD
  AC[Assistant Command: Codex primary / Claude compatible] --> ORCH[LangGraph Orchestrator]
  ORCH --> QUEUE[In-process Job Queue]
  QUEUE --> WORKERS[Workers]
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

- Single-node orchestrator runs the LangGraph.
- Long-running tasks executed via in-process worker pool (async + process/thread).
- Concurrency default: 2 workers; configurable via `config/system.yaml`.
- Parallelism policy (MVP):
  - Core flow is sequential and gate-driven.
  - Audio-first production order is fixed as:
    - `RESEARCH -> STORY -> SCRIPT -> NARRATION -> ASSET -> SCENE_IMPLEMENTATION -> VIDEO -> RENDER -> QA`
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
  - `SCRIPT` → produces `script.md` and a narration-ready skeleton `video_manifest.md`
  - `NARRATION` → produces reviewed TTS audio and confirmed runtime duration
  - `ASSET` → produces reusable recurring still assets
  - `SCENE_IMPLEMENTATION` → produces the production manifest and scene still outputs
  - `VIDEO` → produces motion clips
  - `RENDER` → produces `video.mp4`
  - `QA` → produces final review outputs
- Scene-level tasks exist inside `SCRIPT`, `SCENE_IMPLEMENTATION`, and `VIDEO`:
  - `SCRIPT` subtask: draft one scene and narration beat from the approved story plan.
  - `SCENE_IMPLEMENTATION` subtask: implement one approved scene/cut into production prompt fields.
  - `VIDEO` subtask: generate motion clips for an approved scene/cut.
- Asset-level tasks are split by stage:
  - `NARRATION`: TTS generation and duration fit checks.
  - `ASSET`: character/object/location reference stills.
  - `SCENE_IMPLEMENTATION`: cut still generation.
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
- production order は audio-first を採用する。
  - `script` で scene / narration draft を確定したあと、`video_manifest.md` はまず `manifest_phase: skeleton` で materialize する。
  - その後に `narration -> asset -> scene implementation -> video -> render -> qa` の順で進める。
  - 理由は、最終尺を決められる信頼できる runtime 入力が実 TTS 秒数だけだから。asset / scene / video を先に固定すると、後から尺ズレで recut が発生しやすい。
- したがって「script draft までは人承認なしで進める」のような運用差分は、prompt の解釈ではなく run 初期 state で表現する。
- チャット起点の stage 実行も同じ state / grounding 契約の上で扱う。
  - `resolve-stage-grounding.py` で contract を解決
  - `audit-stage-grounding.py` で readset を監査
  - `logs/grounding/<stage>.readset.json` を「読むべき対象の正本」とする
  - これにより slash command とチャット実行の前提を揃える
- authoring 直後の review slot は、単発 review ではなく最大 5 round の evaluator-improvement loop とする。
  - 1 round は 5 critic agents + 1 aggregator で構成する
  - critic / aggregator は `state.txt`、`p000_index.md`、canonical artifact を直接編集しない
  - メインエージェントが aggregator report を読み、採用する修正だけを canonical artifact に反映する
  - round 5 後も `changes_requested` の場合は `eval.<stage>.loop.status=changes_requested` で停止し、人間 review / override を待つ

## Fixed P-Slot Contract

変更内容:
- fixed `p-slot` contract を production order に合わせて再編した。
- 後半順序は `p500 narration/audio -> p600 asset -> p700 scene implementation -> p800 video -> p900 render` に固定する。
- `p450` を追加し、`video_manifest.md` を narration-ready skeleton manifest として先に materialize する。

修正理由:
- 実 TTS 秒数だけが最終尺の正本であり、asset / scene / video をその後ろに置く方が late recut を減らせる。
- 尺が target 未満のとき、padding で誤魔化さず scene / narration の再設計へ戻れるようにするため。

旧仕様との差分:
- 旧仕様では `p500 asset -> p600 image -> p700 video -> p800 audio` だった。
- 新仕様では audio-first に切り替え、asset / scene / video は実尺確定後へ移動した。

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
- `p400`: script / narration text / human changes
  - `p410`: grounding
  - `p420`: authoring
  - `p430`: evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p440`: human changes / narration sync
  - `p450`: skeleton manifest materialization
- `p500`: narration / audio runtime
  - `p510`: narration grounding
  - `p520`: narration text evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p530`: TTS request / generation
  - `p540`: duration fit gate
  - `p550`: scene stretch review
  - `p560`: narration stretch review
  - `p570`: audio QA / human review handoff
- `p600`: asset
  - `p610`: asset grounding
  - `p620`: reusable asset inventory
  - `p630`: asset plan authoring
  - `p640`: asset evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p650`: asset plan fixes
  - `p660`: asset requests
  - `p670`: asset generation
  - `p680`: asset continuity check
- `p700`: scene implementation
  - `p710`: scene implementation grounding
  - `p720`: production manifest / prompt authoring
  - `p730`: hard scene evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p740`: judgment evaluator-improvement review loop (max 5 rounds; 5 critics + 1 aggregator per round)
  - `p750`: generation ready
  - `p760`: image generation
  - `p770`: image QA / fix loop
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

メインエージェントは run 全体の orchestrator / single writer として振る舞う。subagent は contextless / bounded / artifact-scoped な補助役であり、`state.txt`、`p000_index.md`、canonical artifact の最終更新や承認判断を行わない。

呼び出し条件:

- stage grounding が `ready`、audit が `passed`
- 入力 artifact が存在し、stage readset に含まれている
- task が scene / cut / review / evidence のように境界分割できる
- 出力先が `scratch/`、`logs/`、review artifact、または明示された isolated path

slot ごとの標準分担:

| Slot | subagent に任せてよい作業 | メインエージェントの統合責務 |
| --- | --- | --- |
| `p100` research | research scout / evidence collector | `research.md` への統合、source trace、slot 更新 |
| `p200` story | story candidate / source-vs-creative audit | `story.md` 確定、hybridization 承認確認 |
| `p300` visual planning | visual-value draft / visual payoff audit / anchor-reference-risk audit | `visual_value.md` 統合、story との矛盾確認、p400/p600/p700 handoff 確認 |
| `p400` script | scene draft / narration draft | `script.md` と skeleton manifest の統合 |
| `p500` narration | narration review / duration stretch review | TTS 実行判断、duration gate、manifest 反映 |
| `p600` asset | asset brief / continuity review | asset plan 採用、request 発行、canonical asset 更新 |
| `p700` scene implementation | scene/cut prompt rewrite / image prompt judgment | production manifest 統合、review finding の採否 |
| `p800` video | clip generation fan-out / clip review | 採用判定、manifest 更新、除外理由の記録 |
| `p900` render / QA | QA reviewer / runtime summary review | final report 生成、完了判定、run closeout |

Authoring-after review loop の標準分担:

- critic agents: 5 agents per round。rubric finding と修正候補を isolated report に出す
- aggregator: 1 agent per round。5 critic reports を統合し、`passed|changes_requested` と unresolved findings を返す
- main agent: aggregator report を根拠に canonical artifact を更新し、次 round 実行または gate close を決める
- max rounds: 5。round 5 後の unresolved finding は human review / explicit override に回す

禁止事項:

- `state.txt` を置き換える、または subagent が直接 final status を確定する
- hybridization を自動承認する
- 複数 subagent に `story.md` / `script.md` / `video_manifest.md` を同時編集させる
- 親会話だけにある未記録情報へ依存する
- evidence なしの事実追加を canonical artifact に入れる

統合手順:

1. subagent output を読む
2. canonical artifact に採用する差分を選ぶ
3. `state.txt` に prompt / output / review summary を append する
4. verifier または stage review を通す
5. finding が残る場合は、修正 task を再度 bounded subagent に渡す

## Model/providers

- Provider interfaces for image, video, TTS, and LLM.
- LLM integration uses LangChain.
- Image: Google Nano Banana 2（`google_nanobanana_2`）
- Image (alt): Gemini 3.1 Flash Image（`gemini_3_1_flash_image` / `gemini-3.1-flash-image-preview`）
- Video: Kling 3.0（default。`video_generation.tool: kling_3_0`）
- Video (omni): Kling 3.0 Omni（`video_generation.tool: kling_3_0_omni`）
- Video (alt): Seedance（BytePlus ModelArk。`video_generation.tool: seedance`）
- Note: Google Veo は安全のためこのリポジトリでは無効化している。
- TTS: ElevenLabs
- Swap providers via configuration without changing orchestration logic.

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
