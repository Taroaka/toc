# Data Contracts (MVP)

この文書は、ToC の authoring、materialization、generation、render をつなぐ最小の正本契約を定義する。
制作は `authoring → structural validation → generation` の順で進む。品質を採点する
agent、critic、aggregator、合格証明、必須の人間承認 artifact は契約に含めない。

## 0. Core Terms / Glossary

- `scene`: 物語全体の中で不可逆な変化を起こす劇的単位。`dramatic_question`、
  `value_shift`、`causal_turn`、画面で読める `visible_evidence`、次 scene への
  `handoff_chain` を持つ。
- `cut`: scene を一つの画、短い動き、反応、間、transition、または narration beat として
  実装する単位。`cut_contract` が cut の正本である。
- `asset`: 複数 scene/cut で再利用する character、object、location、または still。
- `manifest`: provider に渡す実行可能な scene/cut/audio/image/video 契約。
- `structural validation`: schema、型、ID、参照、順序、request binding、ファイル、decode、
  duration、provenance を確認する処理。これは content quality score を計算しない。
- `human choice`: candidate 選択、listening、編集、change request、hybridization、公開など、
  ユーザーが任意に行う操作。保存された choice は新しい request revision になる。

標準 production order:

```text
research → story → visual_value → script → asset →
scene_implementation/image → narration/audio → video → render → qa
```

## 1. State schema

State は `output/<topic>_<timestamp>/state.txt` に append-only delta event として保存する。
`state.current.json`、`run_status.json`、`p000_index.md` はこの履歴から作る derived view であり、
第二の正本ではない。

```text
# toc.state.delta.v1 {event envelope JSON}
timestamp=ISO8601
slot.p410.status=in_progress
artifact.script=script.md
---
```

storage rules:

- 一つの transaction の変更は一つの atomic delta event にする。
- 同じ key は最後の committed value が current である。
- state writer は shared store/lock API を使う。過去 event を削除、置換、truncate しない。
- derived view が欠落・stale・破損したら canonical log を replay する。
- resume は downstream state を新しい delta で stale/pending にし、履歴を巻き戻さない。
- state に source/request/provider hashes、artifact paths、ordinary validation result、runtime
  error を記録できる。production content score や certificate は要求しない。

最小 state key catalog:

```text
job_id=JOB_YYYY-MM-DD_0001
topic=string
status=INIT|RESEARCH|STORY|SCRIPT|ASSET|IMAGE|NARRATION|VIDEO|RENDER|QA|DONE
stage.<name>.status=pending|in_progress|done|failed|skipped|awaiting_user_choice
stage.<name>.started_at=ISO8601
stage.<name>.finished_at=ISO8601
stage.<name>.grounding.status=ready|missing_docs|missing_inputs
stage.<name>.grounding.report=logs/grounding/<stage>.json
stage.<name>.readset.report=logs/grounding/<stage>.readset.json
stage.<name>.source_digest=sha256:<hex>
stage.<name>.artifact_digest=sha256:<hex>
slot.pXXX.status=pending|in_progress|done|failed|skipped|blocked|awaiting_user_choice
slot.pXXX.requirement=required|optional
slot.pXXX.skip_reason=string
slot.pXXX.note=string
request.<item_id>.revision=string
request.<item_id>.digest=sha256:<hex>
request.<item_id>.status=materialized|submitted|generated|stale|failed
output.<item_id>.path=run-relative/path
output.<item_id>.sha256=sha256:<hex>
output.<item_id>.provenance_status=matched|mismatched|missing
human_choice.<id>.status=selected|edited|deferred
human_choice.<id>.actor=string
human_choice.<id>.at=ISO8601
publication.status=pending|authorized|published|failed
```

## 2. Create input

Frontend and CLI create save the exact source and request identity before authoring. Resume uses
this input instead of inferring from generated artifacts.

```json
{
  "schema_version": "toc.create_input.v1",
  "topic": "string",
  "source": "exact source text",
  "source_sha256": "sha256:<utf8 source hash>",
  "experience": "cinematic_story",
  "source_run": null,
  "target_duration_seconds": 300
}
```

`topic` and `source` are non-empty strings. `source_sha256` hashes the exact UTF-8 bytes.
`experience` is `cinematic_story|world_walk`; a `world_walk` source references a repo-relative
existing run. `target_duration_seconds` is an integer from 300 through 1200, defaulting to 300.
Unknown fields are preserved in a raw input record but never used as a hidden generation policy.

## 3. Artifact paths

```text
output/<topic>_<timestamp>/
  research.md
  story.md
  visual_value.md
  script.md
  video_manifest.md
  asset_inventory.md
  asset_plan.md
  assets/
  audio/
  video.mp4
  state.txt
  p000_index.md
  logs/grounding/
  logs/orchestration/
```

Run reports and inventories are ordinary execution summaries. They are optional and never act as
content certificates.

## 4. Fixed p-slot workflow

Coarse buckets remain p100 through p900. The following slots are active:

| Bucket | Slots | Responsibility |
| --- | --- | --- |
| p100 | p110, p120 | source context and research authoring |
| p200 | p210, p220 | source context and story authoring |
| p300 | p310, p330 | visual value authoring and handoff |
| p400 | p410, p420, p440, p450 | scene/cut authoring, supplied user edits, skeleton manifest |
| p500 | p510, p520, p530, p550, p560, p570 | asset source context, inventory, plan, requests, generation, continuity checks |
| p600 | p610, p620, p650, p660, p670, p680 | image source context, prompt/request authoring, readiness, generation, output checks, optional selection |
| p700 | p710, p730, p740, p750 | narration authoring, TTS, measured duration, optional listening/selection |
| p800 | p810, p830, p840 | motion authoring, requests, video generation |
| p900 | p910, p920 | render inputs and final render/output checks |

Retired production slots are `p130`, `p230`, `p320`, `p430`, `p435`, `p540`, `p630`, `p640`,
`p720`, `p820`, `p850`, and `p930`. Current runs do not create those slots or synthesize a
replacement `passed` value. Legacy state entries with those names are historical input only.

Coarse target resolution:

```text
p100 → p120   p200 → p220   p300 → p330   p400 → p450   p500 → p570
p600 → p680   p700 → p750   p800 → p840   p900 → p920
```

Slot completion means the owning author/materializer and ordinary validators finished. A slot may
be `awaiting_user_choice` only when an optional user selection is explicitly part of the chosen UI
flow; generation itself never waits for a production quality verdict.

## 5. Stage boundaries

### Research and story

Research records source passages, facts, uncertainty, provenance, and candidate material. Story
authoring turns those inputs into a source-grounded causal sequence. Both stages preserve source IDs
and creative additions; a human must explicitly authorize hybridization when contradictory source
variants are intentionally combined.

### Visual value and script

`visual_value.md` records visual identity, anchors, reusable asset candidates, regeneration risks,
and downstream handoff. `script.md` owns scene intent, event sequence, cut blueprints, narration
contract, and optional user change requests. `video_manifest.md` begins as
`manifest_phase: skeleton` and is materialized from script selectors.

`p410` and `p420` are authoring slots. The scene/cut contract is checked structurally before asset,
image, audio, or video generation.

### Asset and image

`asset_inventory.md` and `asset_plan.md` define reusable identity and reference inputs. Asset and
image requests are immutable snapshots containing the exact prompt, settings, references, source
digest, and destination. Generated files are accepted only when their request-bound provenance
matches the snapshot.

### Narration and video

Narration uses `script.md` as the text source, records TTS text separately, and measures generated
audio duration. Users may listen to and select among candidates or edit text; the selected revision
is revalidated before provider execution. Video uses the compiled motion payload, ordered frame and
reference bindings, and provider capability limits. No quality score or pass field is required.

### Render and QA

Render normalizes video/audio streams, checks file existence and decode, and measures final duration
and synchronization. QA records ordinary runtime and file findings. Publication authorization is a
separate explicit user action.

## 6. Scene event and cut contracts

`scene_event` explains what happens; `scene_intent` explains why the scene exists;
`cut_contract` explains how it is shown.

```yaml
scene_event:
  schema_version: scene_event_v1
  event_logline: ""
  start_situation: ""
  source_story_beat_ids: []
  event_sequence:
    - beat_id: scene1_event_01
      beat_function: custom
      source_story_beat_ids: []
      what_happens: ""
      visible_action: ""
      visible_reaction: ""
      immediate_consequence: ""
      required_visual_evidence: []
      story_information_revealed_ids: []
  turning_event:
    source_event_beat_id: scene1_event_01
    irreversible_change: ""
  end_situation: ""
  forbidden_event_changes: []
```

Structural checks require non-empty unique beat IDs, valid source references, a valid turning event,
ordered event coverage, and no provider-specific fields in `scene_event`.

```yaml
cut_contract:
  schema_version: "3.0"
  source_event_contract:
    primary_event_beat_id: scene1_event_01
    source_event_beat_ids: [scene1_event_01]
    event_facts_to_preserve: []
    event_facts_not_to_invent: []
    allowed_reveal_info_ids: []
    forbidden_reveal_info_ids: []
  cut_function: custom
  intent_budget:
    primary_intent: ""
    assigned_obligation_ids: []
  viewer_contract:
    screen_question: ""
    visual_evidence: []
    must_show: []
    must_avoid: []
  first_frame_contract:
    imageable: true
    source_event_beat_id: scene1_event_01
    not_yet_happened_in_still: []
  motion_contract:
    starts_from_first_frame: true
    source_event_beat_id: scene1_event_01
    motion_brief: ""
    end_state: ""
    must_not_add: []
  narration_contract:
    schema_version: narration_contract_v2
    source_event_beat_ids: [scene1_event_01]
    allowed_info_ids: []
    forbidden_info_ids: []
    must_not_caption_visible_action: true
  asset_dependency:
    character_ids_required: []
    object_ids_required: []
    location_ids_required: []
  downstream_handoff:
    p500_asset: {required_asset_ids: []}
    p600_image: {reference_requirements: []}
    p700_narration: {narration_requirements: []}
    p800_video: {motion_requirements: []}
```

The validator checks exact source beat references, one primary intent, first-frame imageability,
motion boundaries, narration event boundaries, asset IDs, and downstream selector closure. It does
not ask another agent to judge whether the prose is good.

## 7. Image and video prompt contracts

Image generation uses the one-way compiler:

```text
scene_event + cut_contract + asset references
  → first_frame_visual_plan
  → drawable_prompt_ir
  → image_generation.api_prompt_payload
  → immutable request snapshot
```

The provider receives only the compiled prompt and bound execution options. Design metadata,
internal IDs, hashes, and future motion are excluded from provider prose. Empty optional groups are
omitted rather than filled with placeholders.

```yaml
image_generation:
  character_ids: []
  object_ids: []
  references: []
  api_prompt_payload:
    policy_version: image_api_prompt_v2
    compiler_version: conditional_drawable_prompt_compiler_v3
    prompt: "exact provider-facing prompt"
    sha256: sha256:<prompt hash>
    source_digest: sha256:<compiler source hash>
    provider_request_binding:
      duration_seconds: 0
      quality: 1080p
      aspect_ratio: "16:9"
      references: []
      reference_content_sha256: {}
```

Video generation uses `video_prompt_projection_registry_v5` and
`conditional_video_prompt_compiler_v5` to create a saved `video_api_prompt_v1` payload. The payload
contains exact prompt/negative prompt hashes, provider settings, first/last frame bindings, ordered
reference roles, source digest, and execution options. Current canonical design is recompiled before
provider execution; any drift makes the request stale.

## 8. Request, file, and provenance checks

Each generated item binds:

```text
generation_job_id + item_id + turn_id + prompt_sha256 + reference_sha256s
  + saved_path + destination
```

The binding is stored before the provider call and checked again before copying output. Existing
files may be reused only when bytes and the complete binding match. A failed regeneration leaves a
previous valid file untouched. Resume regenerates only missing or stale items and quarantines stale
outputs in the run's resume directory.

Ordinary failure conditions include malformed YAML/JSON, duplicate or unknown IDs, missing source or
reference paths, invalid provider settings, request hash drift, missing output, decode failure,
duration outside provider capability, and audio/video stream incompatibility. These are processing
errors and remain independent of human choices.

## 9. Asset and manifest boundaries

`asset_plan.md` owns reusable asset identity, visual specification, reference inputs, and output
paths. `video_manifest.md` owns scene/cut execution, image/audio/video payloads, and request IDs.
`script.md` owns story meaning, scene intent, event order, cut intent, and narration source text.
Downstream artifacts project these fields one way and do not invent a second authoring root.

`video_manifest.md` may contain `render_units[]` when several ordered cuts share one provider clip.
Each unit lists source cut IDs exactly once, preserves their contracts, and has a provider-capability
valid duration. Render units do not double-count their source cuts.

## 10. Human choices, hybridization, and publication

Candidate selection, listening, image editing, narration editing, and explicit change requests are
optional. A selected/edited candidate becomes the current request revision and must pass ordinary
structural and provenance checks before generation.

Contradictory source variants may be hybridized only after the user explicitly authorizes that
choice; the authorization and selected source IDs are stored in the run artifact. Publishing also
requires an explicit user action. Neither action is represented as an automated quality pass.

## 11. Supervisor handoff

The L2 bucket owner writes `logs/orchestration/pXXX.supervisor_result.json`:

```json
{
  "bucket": "p400",
  "status": "done",
  "completed_slots": ["p410", "p420", "p450"],
  "required_artifacts": [{"path": "script.md", "exists": true}],
  "state_keys": {"stage.script.status": "done"},
  "output_inventory": ["script.md", "video_manifest.md"],
  "next_bucket": "p500",
  "blocked_reason": null
}
```

L1 checks the result, required paths, state, and ordinary validator result. It does not need a
critic report, aggregate report, score, or approval certificate to start the next bucket.

