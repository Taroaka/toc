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
| Providers | LLM via LangChain; image=Google Nano Banana Pro; video=Kling 3.0 (default) / Seedance (alt); TTS=ElevenLabs（Veo is disabled for safety） | Avoid vendor lock-in |
| API boundary | Claude Code entrypoint (slash command) | Keep surface area small |
| Review policy | Decide at run start and persist in `state.txt` | Stage grounding and orchestrators must share one approval contract |

## Component diagram

```mermaid
graph TD
  CC[Claude Code Slash Command] --> ORCH[LangGraph Orchestrator]
  ORCH --> QUEUE[In-process Job Queue]
  QUEUE --> WORKERS[Workers]
  WORKERS --> PROVIDERS[Image/Video/TTS/LLM Providers]
  ORCH --> META[Metadata DB (PostgreSQL)]
  ORCH --> STATE[State File (state.txt)]
  PROVIDERS --> OBJ[Object Store (filesystem)]
  OBJ --> ARTIFACTS[Artifacts: research/story/script/video]
```

## Deployment mode

- MVP: local-only, Claude Codeで起動（slash command）。
- Future: containerized deployment with dev/staging/prod environments.

## Execution model

- Single-node orchestrator runs the LangGraph.
- Long-running tasks executed via in-process worker pool (async + process/thread).
- Concurrency default: 2 workers; configurable via `config/system.yaml`.
- Parallelism policy (MVP):
  - Core flow (RESEARCH → STORY → SCRIPT → REVIEW) is sequential.
  - Parallelizable points are limited to:
    - Within a single approved scene: generate assets (image, TTS, video) in parallel.
    - After a scene is approved: start that scene's asset generation while the next scene is being drafted/reviewed.

## Storage strategy

- Object storage (artifacts): filesystem at `output/`.
- Metadata DB: PostgreSQL (local or managed).
- Paths are configured in `config/system.yaml`.

## Job queue / executor

- In-process queue with worker pool.
- Tasks are stage-scoped (RESEARCH, STORY, SCRIPT, VIDEO, QA).
- Retry logic is handled at the LangGraph edge level (future task).

## Task granularity (MVP)

- Base unit is a stage task aligned to LangGraph nodes:
  - `RESEARCH` → produces `research.md`
  - `STORY` → produces `story.md`
  - `SCRIPT` → produces `script.md` (scene plan + narration text)
  - `VIDEO` → produces assets + `video.mp4`
  - `QA` → produces review/score + pass/fail
- Scene-level tasks exist only inside `SCRIPT` and `VIDEO`:
  - `SCRIPT` subtask: draft one scene from the approved scene plan.
  - `VIDEO` subtask: generate assets for an approved scene (image, TTS, clip).
- Asset-level tasks exist only inside `VIDEO`:
  - Image, TTS, and clip generation are independent per approved scene.
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
- したがって「script draft までは人承認なしで進める」のような運用差分は、prompt の解釈ではなく run 初期 state で表現する。
- チャット起点の stage 実行も同じ state / grounding 契約の上で扱う。
  - `resolve-stage-grounding.py` で contract を解決
  - `audit-stage-grounding.py` で readset を監査
  - `logs/grounding/<stage>.readset.json` を「読むべき対象の正本」とする
  - これにより slash command とチャット実行の前提を揃える

## Fixed P-Slot Contract

- `p100` ごとに大工程を固定する。
- `p110` 以降の細番号も全作品で固定契約として扱う。
- 作品差分は slot meaning を変えず、`slot.<code>.status` / `slot.<code>.requirement` / `slot.<code>.skip_reason` / `slot.<code>.note` で表す。
- `p000_index.md` は fixed slot contract に基づく run-local source-of-truth とする。

標準 slot:

- `p100`: research
  - `p110`: grounding
  - `p120`: authoring
  - `p130`: review
- `p200`: story
  - `p210`: grounding
  - `p220`: authoring
  - `p230`: review
- `p300`: visual planning
  - `p310`: visual value
  - `p320`: visual planning review
  - `p330`: appendix
- `p400`: script / narration text / human changes
  - `p410`: grounding
  - `p420`: authoring
  - `p430`: review
  - `p440`: human changes / narration sync
- `p500`: asset
  - `p510`: grounding
  - `p520`: reusable asset inventory
  - `p530`: asset plan authoring
  - `p540`: asset review
  - `p550`: asset plan fixes
  - `p560`: asset requests
  - `p570`: asset generation
  - `p580`: asset continuity check
- `p600`: image
  - `p610`: grounding
  - `p620`: manifest / prompt authoring
  - `p630`: hard review
  - `p640`: judgment review
  - `p650`: generation ready
  - `p660`: image generation
  - `p670`: image QA / fix loop
- `p700`: video
  - `p710`: grounding
  - `p720`: motion / video review
  - `p730`: video requests
  - `p740`: video generation
  - `p750`: video review / exclusions
- `p800`: audio
  - `p810`: narration text review
  - `p820`: TTS request / generation
  - `p830`: audio QA
- `p900`: render / QA / runtime
  - `p910`: render inputs
  - `p920`: final render
  - `p930`: QA / runtime summary

## Model/providers

- Provider interfaces for image, video, TTS, and LLM.
- LLM integration uses LangChain.
- Image: Google Nano Banana Pro（Gemini Image / `gemini-3-pro-image-preview`）
- Video: Kling 3.0（default。`video_generation.tool: kling_3_0`）
- Video (omni): Kling 3.0 Omni（`video_generation.tool: kling_3_0_omni`）
- Video (alt): Seedance（BytePlus ModelArk。`video_generation.tool: seedance`）
- Note: Google Veo は安全のためこのリポジトリでは無効化している。
- TTS: ElevenLabs
- Swap providers via configuration without changing orchestration logic.

## API boundaries / module ownership

- MVP: Claude Code の呼び出しが起点（slash command）。
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
