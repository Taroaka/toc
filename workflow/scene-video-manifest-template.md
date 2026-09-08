# scene単体: 動画マニフェストテンプレ

`output/<topic>_<timestamp>/scenes/sceneXX/video_manifest.md` 用。scene単体 run でも
p400 scene/cut contract → p600 image request → p700 narration → p800 motion → render の順を守る。
共通 shape は `workflow/video-manifest-template.md` を参照する。

```yaml
manifest_phase: skeleton|production
video_metadata:
  topic: "<topic>"
  source_run: "output/<topic>_<timestamp>/"
  source_scene_script: "output/<topic>_<timestamp>/scenes/sceneXX/script.md"
  created_at: ISO8601
  target_duration_seconds: 30
  duration_seconds: 0
  experience: cinematic_story
  aspect_ratio: "16:9"
  resolution: "1280x720"
  time: ""

source_bindings:
  source_scene_script: {path: scenes/sceneXX/script.md, sha256: sha256:<hash>}
  source_story: {path: story.md, sha256: sha256:<hash>}
  source_digest: sha256:<hash>

scene_generation:
  schema_version: scene_generation_v1
  source_refs: []
  scene_intent: {}
  scene_event:
    schema_version: scene_event_v1
    event_logline: ""
    start_situation: ""
    source_story_beat_ids: []
    event_sequence: []
    turning_event: {source_event_beat_id: "", irreversible_change: ""}
    end_situation: ""
    forbidden_event_changes: []
  scene_cut_coverage_plan:
    event_beat_inventory: []
    scene_obligations: []
    cut_assignments: []

assets:
  character_bible: []
  object_bible: []
  location_bible: []
  style_guide:
    visual_style: "実写映画調、自然な映画照明、実物セット感"
    forbidden: [画面内テキスト, 字幕, ウォーターマーク, ロゴ]
    reference_images: []

audio_story_plan:
  schema_version: audio_story_plan_v1
  authoring_status: draft|authored
  audience_promise: ""
  narrator_bible: {relationship_to_story: "", knowledge_boundary: []}
  scene_arcs: []
  silence_budget: {purpose: "", protected_moments: []}
  continuous_full_draft: ""
narration_spans: []
narration_authoring:
  schema_version: narration_authoring_v1
  status: missing|draft|human_locked|silent
  revision: 0
  text_hash: sha256:<hash>
  tts_hash: sha256:<hash>
  source: author|user

scenes:
  - scene_id: scene_01
    time_of_day: ""
    time_of_day_visual_basis: ""
    location_mode: single|sequence
    location_sequence: []
    location_segments: []
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
    scene_event:
      schema_version: scene_event_v1
      event_logline: ""
      start_situation: ""
      source_story_beat_ids: []
      event_sequence: []
      turning_event: {source_event_beat_id: "", irreversible_change: ""}
      end_situation: ""
      forbidden_event_changes: []
    cuts:
      - cut_id: scene_01_cut_01
        cut_status: active|deleted
        cut_contract:
          schema_version: "3.0"
          source_event_contract:
            primary_event_beat_id: ""
            source_event_beat_ids: []
            event_facts_to_preserve: []
            event_facts_not_to_invent: []
            allowed_reveal_info_ids: []
            forbidden_reveal_info_ids: []
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
            source_event_beat_id: ""
            event_fact_visible_in_still: ""
            not_yet_happened_in_still: []
            first_frame_brief: ""
          motion_contract:
            source_event_beat_id: ""
            starts_from_first_frame: true
            motion_brief: ""
            end_state: ""
            must_not_add: []
          narration_contract:
            schema_version: narration_contract_v2
            source_event_beat_ids: []
            allowed_info_ids: []
            forbidden_info_ids: []
            must_not_caption_visible_action: true
        image_generation:
          tool: codex_builtin_image
          character_ids: []
          object_ids: []
          references: []
          api_prompt_payload:
            policy_version: image_api_prompt_v2
            compiler_version: conditional_drawable_prompt_compiler_v3
            prompt: ""
            negative_prompt: ""
            sha256: sha256:<hash>
            source_digest: sha256:<hash>
            provider_request_binding:
              generation_job_id: JOB_001
              item_id: scene_01_cut_01
              turn_id: turn_001
              reference_sha256s: {}
              destination: assets/scenes/scene_01_cut_01.png
          request_revision: 0
          output: assets/scenes/scene_01_cut_01.png
        audio:
          narration:
            authoring_status: missing|draft|human_locked|silent
            text: ""
            tts_text: ""
            tool: elevenlabs
            span_refs: []
            silence_contract:
              intentional: false
              duration_seconds: 0
              reason: ""
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
            sha256: sha256:<hash>
            source_digest: sha256:<hash>
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
          output: assets/video/scene_01_cut_01.mp4

render_units: []
human_choices: []
validation:
  schema: pending|passed|failed
  source_refs: pending|passed|failed
  selectors: pending|passed|failed
  requests: pending|passed|failed
  outputs: pending|passed|failed
  provenance: pending|passed|failed
  errors: []
```

Rules:

- scene script source IDs and selector order are canonical.
- p400 authoring does not call image/video/TTS providers.
- candidate listening/selection/editing is optional and is saved in human_choices.
- request payload and provider output must pass ordinary hash, file, decode, duration, and provenance checks.

