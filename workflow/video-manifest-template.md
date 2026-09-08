# 動画マニフェスト: テンプレート

`video_manifest.md` は scene/cut/audio/image/video の execution source である。
`manifest_phase: skeleton` は p450 の構造、`manifest_phase: production` は p500 以後の
materialized request/output を表す。生成は authoring → structural validation → provider execution
の順で進む。

## 1. Metadata

```yaml
manifest_phase: skeleton|production
video_metadata:
  topic: "<topic>"
  # Existing-story runs uncomment this marker and project the value lineage one way.
  # adaptation_value_contract: "required_v1"
  source_story: "output/<topic>_<timestamp>/story.md"
  source_script: "output/<topic>_<timestamp>/script.md"
  source_visual_value: "output/<topic>_<timestamp>/visual_value.md"
  created_at: "<ISO8601>"
  target_duration_seconds: 300
  estimated_duration_seconds: 300
  duration_seconds: 300
  experience: cinematic_story|cloud_island_walk|world_walk
  source_run: null
  aspect_ratio: "16:9"
  resolution: "1280x720"
  time: ""
  scene_time_of_day_contract: required_v1
  scene_time_of_day_visual_basis_contract: required_v1
```

Fields are one-way projections from source artifacts. Unknown source facts are not invented in the
manifest.

## 2. Source and request identity

```yaml
source_bindings:
  story: {path: story.md, sha256: sha256:<hash>}
  script: {path: script.md, sha256: sha256:<hash>}
  visual_value: {path: visual_value.md, sha256: sha256:<hash>}
  asset_plan: {path: asset_plan.md, sha256: sha256:<hash>}
  source_digest: sha256:<normalized source hash>

request_materialization:
  image:
    provider_prompt_path: scenes[].cuts[].image_generation.api_prompt_payload.prompt
    execution_snapshot: image_generation_request_snapshot.json
    immutable_after_materialization: true
  video:
    provider_prompt_path: scenes[].cuts[].video_generation.api_prompt_payload.prompt
    execution_snapshot: video_generation_request_snapshot.json
    immutable_after_materialization: true
```

A request snapshot stores exact prompt, negative prompt, source digest, provider/model/mode/settings,
first/last frames, ordered references/roles, reference content hashes, destination, and revision. The
provider reads the saved payload; it never rebuilds a request from free text.

## 3. Assets

```yaml
assets:
  character_bible:
    - character_id: character_01
      reference_images: [assets/characters/character_01_front.png]
      fixed_prompts: []
      source_refs: []
      variants: []
  object_bible: []
  location_bible: []
  style_guide:
    visual_style: 実写映画調、自然な映画照明、実物セット感
    reference_images: []
    forbidden: [画面内テキスト, 字幕, ロゴ, ウォーターマーク]
```

Reusable identity is defined once and referenced by stable IDs. Each reference path exists, is an
allowed image type, and is hashed before an image/video request is submitted.

## 4. Audio story and narration

```yaml
audio_story_plan:
  schema_version: audio_story_plan_v1
  authoring_status: draft|authored
  audience_promise: ""
  narrator_bible:
    relationship_to_story: witness|companion|historian|limited_observer|omniscient
    knowledge_boundary: []
  scene_arcs: []
  silence_budget:
    purpose: ""
    protected_moments: []
  continuous_full_draft: ""

narration_spans:
  - span_id: ns_001
    source_cut_ids: []
    text: ""
    tts_text: ""
    story_job: first_question|causal_bridge|payoff|reaction|aftertaste
    tts_generation_group_id: ""

narration_authoring:
  schema_version: narration_authoring_v1
  status: missing|draft|human_locked|silent
  revision: 0
  text_hash: sha256:<hash>
  tts_hash: sha256:<hash>
  source: author|user
  updated_at: ""
  updated_by: ""
```

`script.md` is the language source. `narration` is readable text and `tts_text` is the
ElevenLabs provider string. Candidate listening, selection, and editing are optional user actions.
Intentional silence requires a reason and duration. TTS output is accepted only after decode and
measured duration checks.

## 5. Scenes and cuts

```yaml
scenes:
  - scene_id: scene_01
    time_of_day: 朝
    time_of_day_visual_basis: "低い自然光、長い影、穏やかな色温度"
    scene_intent:
      story_purpose: ""
      dramatic_question: ""
      value_shift: {from: "", to: "", visible_evidence: []}
      causal_turn: ""
      audience_information: []
      withheld_information: []
      reveal_constraints: []
      visual_thesis: ""
      handoff_to_next_scene: ""
      scene_value_amplification:
        schema_version: scene_value_amplification_v1
        source_value_refs: []
        why_this_scene_matters: ""
        audience_state_before: ""
        audience_state_after: ""
        cinematic_gain:
          performance: ""
          blocking_and_space: ""
          camera_and_composition: ""
          edit_and_rhythm: ""
          sound: ""
        iconic_moment_target: ""
        must_preserve_story_facts: []
        must_not_reduce_to: []
        success_evidence: []
    scene_event:
      schema_version: scene_event_v1
      event_logline: ""
      start_situation: ""
      source_story_beat_ids: []
      event_sequence:
        - beat_id: scene_01_beat_01
          beat_function: custom
          source_story_beat_ids: []
          what_happens: ""
          visible_action: ""
          visible_reaction: ""
          immediate_consequence: ""
          required_visual_evidence: []
      turning_event:
        source_event_beat_id: scene_01_beat_01
        irreversible_change: ""
      end_situation: ""
      forbidden_event_changes: []
    location:
      mode: single|sequence
      sequence: []
      segments: []
    cuts:
      - cut_id: scene_01_cut_01
        cut_status: active|deleted
        source_event_contract:
          primary_event_beat_id: scene_01_beat_01
          source_event_beat_ids: [scene_01_beat_01]
          event_beat_function: custom
          event_time_position: before_trigger
          event_facts_to_preserve: []
          event_facts_not_to_invent: []
          allowed_reveal_info_ids: []
          forbidden_reveal_info_ids: []
        cut_contract:
          schema_version: "3.0"
          expressive_contract:
            schema_version: cut_expressive_contract_v1
            source_value_refs: []
            scene_amplification_ref: scene_01.scene_intent.scene_value_amplification
            audience_experience_delta: ""
            expressive_function: recognition|withhold|pressure|release|contrast|reaction|reframe|afterimage|spectacle|transition
            performance_beat: ""
            visual_pressure: ""
            attention_shift: ""
            edit_trigger: ""
            sound_function: ""
            emotional_afterimage: ""
            must_not_reduce_to: []
          intent_budget:
            primary_intent: ""
            assigned_obligation_ids: []
          viewer_contract:
            target_beat: ""
            screen_question: ""
            audience_knowledge_delta: ""
            causal_proof: ""
            visual_evidence: []
            required_roles: []
            must_show: []
            must_avoid: []
          first_frame_contract:
            imageable: true
            source_event_beat_id: scene_01_beat_01
            event_time_position: before_trigger
            event_fact_visible_in_still: ""
            not_yet_happened_in_still: []
            first_frame_brief: ""
          motion_contract:
            source_event_beat_id: scene_01_beat_01
            starts_from_first_frame: true
            motion_brief: ""
            end_state: ""
            must_not_add: []
          narration_contract:
            schema_version: narration_contract_v2
            source_event_beat_ids: [scene_01_beat_01]
            allowed_info_ids: []
            forbidden_info_ids: []
            must_not_caption_visible_action: true
            narration_event_boundary: same_event_only
          asset_dependency:
            character_ids_required: []
            object_ids_required: []
            location_ids_required: []
          downstream_handoff:
            p500_asset: []
            p600_image: []
            p700_narration: []
            p800_video: []
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
            prompt: ""
            negative_prompt: ""
            sha256: sha256:<prompt hash>
            source_digest: sha256:<source hash>
            provider_request_binding:
              generation_job_id: JOB_001
              item_id: scene_01_cut_01
              turn_id: turn_001
              reference_sha256s: {}
              destination: assets/scenes/scene_01_cut_01.png
          request_revision: 0
          output: ""
          output_sha256: sha256:<hash>
        video_generation:
          tool: kling_3_0
          mode: image_to_video
          first_frame: assets/scenes/scene_01_cut_01.png
          last_frame: ""
          duration_seconds: 8
          api_prompt_payload:
            policy_version: video_api_prompt_v1
            compiler_version: conditional_video_prompt_compiler_v5
            projection_registry_version: video_prompt_projection_registry_v5
            provider: kling_3_0
            prompt: ""
            negative_prompt: ""
            sha256: sha256:<prompt hash>
            source_digest: sha256:<source hash>
            provider_request_binding:
              generation_job_id: JOB_001
              item_id: scene_01_cut_01
              turn_id: turn_001
              first_frame: assets/scenes/scene_01_cut_01.png
              last_frame: ""
              references: []
              reference_roles: []
              reference_content_sha256: {}
              destination: assets/video/scene_01_cut_01.mp4
          request_revision: 0
          output: ""
          output_sha256: sha256:<hash>
```

IDs are unique within the manifest. Scene event beat IDs, location segments, first/last frames,
narration spans, asset dependencies, and request destinations are checked for exact closure.

## 6. Render units

```yaml
render_units:
  - unit_id: scene_01_unit_01
    source_cut_ids: [scene_01_cut_01]
    video_generation:
      duration_seconds: 8
      first_frame: assets/scenes/scene_01_cut_01.png
      last_frame: ""
      prompt: ""
```

A render unit preserves canonical cut order and source contracts. Its duration equals the source cut
duration sum and never double-counts source cuts.

## 7. Validation

```yaml
validation:
  schema: pending|passed|failed
  source_refs: pending|passed|failed
  selectors: pending|passed|failed
  request_bindings: pending|passed|failed
  outputs:
    exists: pending|passed|failed
    decodable: pending|passed|failed
    duration_measured: pending|passed|failed
    streams_compatible: pending|passed|failed
  provenance: pending|passed|failed
  errors: []
  warnings: []
```

Run structural, request, file, media, and provenance validators after each authoring/materialization
stage. A failed check identifies the owning artifact and selector; repair it and rerun the check.

## 8. Optional user actions

`human_choice.*` may record candidate selection, listening, editing, or a change request with actor,
timestamp, selector, and request revision. A selected/edited request is recompiled and revalidated.
Hybridization of contradictory source variants and publication are explicit separate actions.
