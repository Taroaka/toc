# Image Prompting（Codex built-in image / cross-model）

Image stage は source-grounded scene/cut contract を、描画可能な first-frame image prompt と
request-bound generation input に変換する。制作は authoring → structural validation →
generation で進む。画像の aesthetic quality を別 worker が採点したり、承認証跡を要求したり
しない。

## 1. 結論（最短の型）

```text
scene_event + cut_contract + asset/reference IDs
  → first_frame_visual_plan
  → drawable_prompt_ir
  → image_generation.api_prompt_payload
  → immutable request snapshot
  → Codex built-in image generation
  → file/decode/provenance validation
```

- provider に渡すのは `api_prompt_payload.prompt` と request settings だけ。
- design metadata、scene/cut IDs、path、hash、future motion、narration text は prompt 本文へ出さない。
- `character_ids: []`、`object_ids: []`、`references: []` は必要なときに明示し、空の optional group
  は placeholder で埋めない。
- first frame は動作の直前に画面で読める state。motion brief、camera move、action completion
  は image prompt へ混ぜない。
- 生成 output は request-bound provenance が一致したものだけ canonical destination へ copy する。

## 2. Source priority

1. current `video_manifest.md.scenes[].cuts[].cut_contract`
2. `scene_event` と `first_frame_contract`
3. `asset_plan.md` の stable character/object/location identity
4. `visual_value.md` の visual identity、anchor、reference strategy
5. `script.md` の visual beat と human change request projection
6. legacy free text（canonical field がない場合だけ）

source が conflict する場合は canonical owner を編集し、prompt text 側で隠れている conflict
を解決しない。hybridization は user の明示選択として source IDs とともに保存する。

## 3. First-frame visual plan

```yaml
first_frame_visual_plan:
  schema_version: first_frame_visual_plan_v1
  editable: false
  source_grounding:
    scene_id: scene_01
    cut_id: scene_01_cut_01
    source_event_beat_id: scene_01_beat_01
    character_ids: []
    object_ids: []
    location_id: ""
    visible_action: ""
    visible_reaction: ""
    event_facts_to_preserve: []
    event_facts_not_to_invent: []
  temporal_boundary:
    event_time_position: before_trigger
    action_completion_state: pre_action
    event_fact_visible_in_still: ""
    not_yet_happened_in_still: []
    one_visible_moment_rule: true
  subject_binding:
    primary_subject: {}
    secondary_subjects: []
    background_subjects: []
  reference_binding:
    character_references: []
    object_references: []
    location_references: []
  character_state:
    pose: ""
    gaze: ""
    expression: ""
    hand_position: ""
    foot_position: ""
    costume_state: ""
  object_visibility:
    objects: []
  spatial_composition:
    foreground: ""
    midground: ""
    background: ""
    subject_priority_order: []
    frame_edge_handoff: ""
  scene_material:
    story_time: ""
    time_of_day: ""
    light_source: ""
    dominant_materials: []
  motion_affordance:
    movable_subjects: []
    must_not_resolve_in_image: []
    must_stop_before_event_beat_ids: []
  prompt_policy:
    render_only_drawable_information: true
    exclude_design_metadata: true
    exclude_future_motion: true
```

The plan is derived from the scene/cut contract. It describes what is currently visible, not a
summary of the whole scene and not a video action list.

## 4. Drawable Prompt IR

```yaml
drawable_prompt_ir:
  schema_version: drawable_prompt_ir_v1
  dependencies:
    character_ids: []
    object_ids: []
    location_ids: []
    references: []
    story_time: ""
    time_of_day: ""
    required_groups: [style, current_moment, constraints]
  included_fragments:
    - group: style
      text: "実写映画調、自然な映画照明、実物セットの質感。"
    - group: current_moment
      text: "画面に見える人物・場所・状態と一つの行為。"
    - group: constraints
      text: "画面内文字、字幕、ロゴ、透かし、不要な人物や物を入れない。"
  omitted_groups: []
```

Canonical group order is `style → story_time (when present) → time_of_day (when present) →
references → current_moment → primary_subject → characters → objects → location → composition →
light_material → current_state_delta → constraints`. Every included fragment appears exactly in
the compiled prompt. Empty dependencies are omitted.

## 5. Prompt authoring rules

### 5.1 Current state

Write concrete visible nouns, state, relation, location, material, light, and composition. Replace
abstract words such as “感動的な場面” with a visible action and evidence. Preserve the source event
and forbidden future outcomes.

### 5.2 Subject and references

Use stable asset IDs for recurring character/object/location references. Every referenced file is
run-relative, exists, has an allowed image type, and is hashed before provider execution. Do not add a
scene-specific time-of-day to a reusable asset unless an explicit variant requires it.

### 5.3 First frame boundary

Do not draw the completed action, future reveal, unlisted character, new location, or motion trail in
the first frame. `must_not_add[]` and `not_yet_happened_in_still[]` are structural constraints that
the validator checks.

### 5.4 Language and metadata

Provider-facing prompts are Japanese by default. Tool names, IDs, paths, hashes, source digests,
scene labels, “first frame”, camera metadata, and production instructions stay in metadata. Keep
negative prompt constraints short and concrete.

## 6. Production image request

```yaml
image_generation:
  character_ids: []
  character_variant_ids: []
  object_ids: []
  object_variant_ids: []
  references: []
  api_prompt_payload:
    policy_version: image_api_prompt_v2
    compiler_version: conditional_drawable_prompt_compiler_v3
    provider: codex_builtin_image
    prompt: "exact provider-facing Japanese prompt"
    negative_prompt: "short concrete constraints"
    sha256: sha256:<prompt hash>
    source_digest: sha256:<normalized source hash>
    provider_request_binding:
      generation_job_id: JOB_001
      item_id: scene_01_cut_01
      duration_seconds: 0
      image_size: 1K
      aspect_ratio: "16:9"
      references: []
      reference_content_sha256: {}
      destination: assets/scenes/scene_01_cut_01.png
```

The payload is stored before the provider call. The provider receives no uncompiled JSON/IR fields.

## 7. Request snapshot and execution

```yaml
image_generation_request_snapshot:
  schema_version: image_generation_request_snapshot_v1
  generation_job_id: JOB_001
  item_id: scene_01_cut_01
  turn_id: turn_001
  prompt_sha256: sha256:<prompt hash>
  reference_sha256s: {}
  saved_path: assets/scenes/scene_01_cut_01.png
  destination: assets/scenes/scene_01_cut_01.png
  payload_sha256: sha256:<payload hash>
  source_digest: sha256:<normalized source hash>
```

The snapshot binds the exact prompt, settings, reference bytes, source digest, and destination. On
completion, verify the provider response item ID, turn ID, prompt hash, reference hashes, saved path,
destination, file bytes, image type, and decode. If any tuple member differs, quarantine the result and
retry that item after rematerialization.

## 8. Asset and scene flow

p500 asset planning creates stable reusable IDs and reference files. p600 scene implementation
projects one cut into a first-frame plan and image request. A reusable anchor may be selected instead
of generating a new still when the current bytes and provenance match. Exploratory variants belong in
`assets/test/` and are never silently promoted.

## 9. Human choices

Candidate selection, image editing, and change requests are optional. Store `human_choice.*` with
actor, timestamp, selected candidate/request revision, and edit description. Recompile and rerun
schema, reference, hash, file, decode, and provenance checks after a choice. A user choice is not an
automatic quality result and does not authorize changing source facts or event ownership.

## 10. Ordinary structural checks

Before generation check:

- required fields, types, enum values, and unique IDs
- source event, location, character, object, and selector references
- first-frame state versus motion boundary and reveal constraints
- prompt fragments, source digest, provider binding, and request snapshot equality
- reference path/type/bytes hashes and destination constraints

After generation check file existence, image type, decode, bytes hash, provider response identity, and
request provenance. Failure names the item and owning artifact so the owner can repair only that item.

## 11. References

- `docs/data-contracts.md`
- `docs/implementation/asset-bibles.md`
- `docs/implementation/video-prompting.md`
- `workflow/p600-scene-image-batch-spec-template.md`
- `workflow/video-manifest-template.md`

