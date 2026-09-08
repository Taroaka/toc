# ToC Pointer Guide

## North Star

- ToC is a spec-first repository. Canonical contracts live in `docs/`, `workflow/`, and
  `scripts/`.
- Production follows direct authoring, ordinary structural validation, and generation. A
  production author owns the artifact it creates; no critic, evaluator, aggregator, or
  quality-score pass is required between stages.
- Structural validation still fails closed for malformed data, missing references, invalid
  selectors, mismatched request/provider data, missing files, decode failures, and provenance
  drift.
- Candidate selection, listening, image editing, narration editing, and other user choices are
  optional product actions. Hybridizing contradictory source material and publishing are explicit
  user decisions and are kept separate from generation.
- Codex is the normal operator. Claude Code is a backup/accelerator.

## Repo Scope

### Image and video generation

Research, story, script, asset, image, narration, video, render, and ordinary output validation
are defined in `docs/video-generation.md` and the stage documents listed below.

### Marketing

Public site, LP, digital acquisition, SNS distribution, lead generation, and reaction analysis
belong under `marketing/README.md` and are separate from story/video production.

## Entrypoints

- `/toc-run`
- `/toc-scene-series`
- `/toc-immersive-ride`
- `/toc-world-walk`

Execution details are in `docs/how-to-run.md`.

## Server Roles

`server/` contains the local FastAPI layers:

- LINE routes live in `server/line_app.py` and processing lives in `server/line_bot.py`.
- Image-generation routes live in `server/image_gen_app.py`; parser, candidate, archive, and
  repository operations live in `server/image_gen.py`.
- `server/app.py` is the shared middleware/static/router entrypoint.

`/image_gen` and `/api/*` require `TOC_SERVER_TOKEN` unless local validation explicitly sets
`TOC_SERVER_AUTH_DISABLED=1`.

Frontend create runs the same backend production path as the command line: source reading,
authoring, structural validation, asset/reference/request materialization, image/audio/video
generation, and file/provenance checks. The frontend route does not build a reduced scaffold or
invent a separate contract.

The shared Codex runtime boundary is `server/codex_app_server.py`. It records executable,
writable runtime, model, network, and output-root diagnostics. Transport/setup failures stay
runtime failures and are not turned into content verdicts.

## Read Next

- Terms: `docs/data-contracts.md` (`Core Terms / Glossary`)
- Research: `docs/information-gathering.md`
- Affect design: `docs/affect-design.md`
- Story: `docs/story-creation.md`
- Adaptation value: `docs/adaptation-value-amplification.md`
- Script: `docs/script-creation.md`
- Video: `docs/video-generation.md`
- Video prompt compiler: `docs/implementation/video-prompting.md`
- Web UI/brand: `server/web/docs/brand-design/README.md`
- Marketing: `marketing/README.md`
- Operations and publishing: `docs/orchestration-and-ops.md`
- Agent tooling: `docs/implementation/assistant-tooling.md`
- Roles: `docs/implementation/agent-roles-and-prompts.md`
- State and artifact contracts: `docs/data-contracts.md`
- ADRs: `docs/adr/`

## Templates / Contracts

- `workflow/research-template.yaml`
- `workflow/research-template.production.yaml`
- `workflow/story-template.yaml`
- `workflow/video-manifest-template.md`
- `workflow/stage-grounding.yaml`
- `workflow/state-schema.txt`
- `workflow/evaluation_criteria.md`
- `workflow/evals/golden-topics.yaml`

`stage-grounding.yaml` defines required source documents, templates, and inputs. Its resolver is
an input/readset helper; a generated certificate or agent verdict is not a production input.

## State and artifacts

- Human-facing navigation: `output/<topic>_<timestamp>/p000_index.md`
- Canonical append-only state: `output/<topic>_<timestamp>/state.txt`
- Derived current state: `output/<topic>_<timestamp>/state.current.json`
- Derived run projection: `output/<topic>_<timestamp>/run_status.json`
- Stage source/readset data: `output/<topic>_<timestamp>/logs/grounding/`
- Orchestration progress/result: `output/<topic>_<timestamp>/logs/orchestration/`
- Generated research, story, script, manifest, media, and ordinary validation data: the run root

Fixed navigation uses the p100 through p900 buckets. Review-only slots are retired; the active
slot contract is authoring, materialization, generation, and ordinary validation.

## Required Workflow

For a non-trivial contract change, record requirements, design, and task list under
`.steering/YYYYMMDD-<title>/` before editing.

For a production stage:

1. Resolve the stage's required documents, templates, and inputs with
   `python scripts/prepare-stage-context.py --stage <stage> --run-dir <run_dir> [--flow <flow>]`.
2. Read the returned source/readset in the order `global_docs -> stage_docs -> templates -> inputs`.
3. Author the canonical artifact with its source IDs, selectors, schema, and handoff fields.
4. Run ordinary structural validators and request/output/provenance checks.
5. Generate or materialize the next artifact only after those checks pass.

The stage resolver may report missing documents or inputs, but production never waits for a
separate certificate. Run `python scripts/validate-slot-contract.py` after changing
the fixed slot contract.

```bash
python scripts/verify-pipeline.py --run-dir output/<topic>_<timestamp> \
  --flow toc-run|scene-series|immersive --profile fast|standard
```

Daily startup:

```bash
scripts/ai/session-bootstrap.sh
```

## Request Intake

For a guide, prompt, or operations-rule change, preserve the requested goal, success criteria,
scope, evidence, and decision rule. Keep general rules free of title-specific people, places,
objects, or scene events; story-specific facts belong in `research.md` and run artifacts.

## Agent Stage Design Docs

| Stage | Canonical docs | Playbooks |
| --- | --- | --- |
| research | `docs/information-gathering.md` | `workflow/playbooks/research/` |
| story | `docs/story-creation.md`, `docs/affect-design.md`, `docs/adaptation-value-amplification.md` | `workflow/playbooks/scene/` |
| script | `docs/script-creation.md`, `docs/adaptation-value-amplification.md` | `workflow/playbooks/script/` |
| narration | `docs/implementation/video-integration.md` | `workflow/playbooks/script/` |
| asset | `docs/implementation/asset-bibles.md` | `workflow/playbooks/image-generation/` |
| scene_implementation | `docs/implementation/image-prompting.md`, `docs/implementation/asset-bibles.md` | `workflow/playbooks/image-generation/` |
| video_generation | `docs/video-generation.md`, `docs/implementation/video-prompting.md`, `docs/adaptation-value-amplification.md` | `workflow/playbooks/video-generation/` |
| render | `docs/implementation/video-integration.md` | `workflow/playbooks/video-generation/` |
| qa | `docs/orchestration-and-ops.md` | `workflow/playbooks/video-generation/` |

Each author reads `docs/system-architecture.md`, its stage document, and the prepared source
context before writing. Agents may parallelize isolated work, but a stage owner remains the
single writer for the canonical artifact, state, and navigation index.

## Chat Stage Protocol

When a user says `進めて`, determine the stage and run directory, prepare the source context,
read the returned source/readset, author the artifact, run structural checks, and report the
result. A source/readset is evidence for what the author may use; it is not a quality certificate.

L1 starts the appropriate L2 bucket supervisor. L2 owns the canonical artifact and append-only
state update. Isolated workers may write temporary or candidate files and never write the canonical
artifact, `state.txt`, or `p000_index.md` directly.

## Hard Rules

- Keep `state.txt` append-only; rebuild derived views from it when needed.
- Hybridization requires explicit user authorization and is never inferred.
- `run_report.md`, when present, is generated from ordinary run data; it is not a required quality
  certificate.
- Keep source IDs, file types, path constraints, locks, request identity, provider settings, and
  output provenance bound through the pipeline.
- Keep marketing references under `marketing/`.
- Keep `AGENTS.md` and `CLAUDE.md` identical pointers. After either changes, run:

```bash
python scripts/validate-pointer-docs.py
```

## Search / Tools

- Files: `rg --files` or `fd`
- Content: `rg`
- Do not use `tree`, `find`, `grep -r`, or `ls -R`.

## Related Runtime Layer

`improve_claude_code/` is a separate operations layer. Its details are in
`docs/implementation/assistant-tooling.md`.
