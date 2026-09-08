# 没入型ライド: 動画マニフェストテンプレ（run root）

`/toc-immersive-ride` の `output/<topic>_<timestamp>/video_manifest.md` 用。
共通 schema は `workflow/video-manifest-template.md`、provider prompt は
`docs/implementation/video-prompting.md` を参照する。

```yaml
manifest_phase: skeleton|production
video_metadata:
  topic: "<topic>"
  source_story: "output/<topic>_<timestamp>/story.md"
  source_script: "output/<topic>_<timestamp>/script.md"
  created_at: ISO8601
  target_duration_seconds: 300
  duration_seconds: 0
  experience: cinematic_story
  aspect_ratio: "16:9"
  resolution: "1280x720"
  frame_rate: 24

source_bindings:
  story: {path: story.md, sha256: sha256:<hash>}
  script: {path: script.md, sha256: sha256:<hash>}
  visual_value: {path: visual_value.md, sha256: sha256:<hash>}
  source_digest: sha256:<hash>

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

assets:
  character_bible:
    - character_id: protagonist
      reference_images:
        - assets/characters/protagonist_front.png
        - assets/characters/protagonist_side.png
        - assets/characters/protagonist_back.png
      fixed_prompts: []
      variants: []
      source_refs: []
  object_bible: []
  location_bible: []
  style_guide:
    visual_style: 実写、シネマティック、実物セット感
    forbidden: [画面内テキスト, 字幕, ウォーターマーク, ロゴ]
    reference_images: []

scenes:
  - scene_id: 0
    kind: character_reference
    reference_id: protagonist_front_ref
    image_generation:
      tool: codex_builtin_image
      character_ids: [protagonist]
      object_ids: []
      references: []
      prompt: "全身の人物参照。頭からつま先まで、実写、クリーンな背景。"
      output: assets/characters/protagonist_front.png
  - scene_id: 10
    kind: story_scene
    timestamp: "00:00-00:08"
    time_of_day: ""
    time_of_day_visual_basis: ""
    location_mode: single|sequence
    location_sequence: []
    location_segments: []
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
      - cut_id: scene10_cut01
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
            visual_evidence: []
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
            sha256: sha256:<hash>
            source_digest: sha256:<hash>
            provider_request_binding:
              generation_job_id: JOB_001
              item_id: scene10_cut01
              turn_id: turn_001
              reference_sha256s: {}
              destination: assets/scenes/scene10_cut01.png
          request_revision: 0
          output: assets/scenes/scene10_cut01.png
        video_generation:
          tool: kling_3_0
          mode: image_to_video
          first_frame: assets/scenes/scene10_cut01.png
          last_frame: ""
          duration_seconds: 8
          api_prompt_payload:
            policy_version: video_api_prompt_v1
            compiler_version: conditional_video_prompt_compiler_v5
            projection_registry_version: video_prompt_projection_registry_v5
            prompt: ""
            negative_prompt: ""
            sha256: sha256:<hash>
            source_digest: sha256:<hash>
            provider_request_binding:
              generation_job_id: JOB_001
              item_id: scene10_cut01
              turn_id: turn_001
              first_frame: assets/scenes/scene10_cut01.png
              last_frame: ""
              references: []
              reference_roles: []
              reference_content_sha256: {}
              destination: assets/video/scene10_cut01.mp4
          request_revision: 0
          output: assets/video/scene10_cut01.mp4
        audio:
          narration:
            text: ""
            tts_text: ""
            authoring_status: missing
            tool: elevenlabs
            span_refs: []
            silence_contract:
              intentional: false
              duration_seconds: 0
              reason: ""

render_units: []
human_choices: []
validation:
  schema: pending|passed|failed
  references: pending|passed|failed
  requests: pending|passed|failed
  outputs: pending|passed|failed
  provenance: pending|passed|failed
  errors: []
```

Rules:

- scene 0 is an optional reference asset; story scenes use manifest order and stable IDs.
- p400 creates scene/cut contracts and skeleton shape; p500/p600/p700/p800 materialize provider requests.
- all prompts, references, outputs, and request revisions are ordinary structural/provenance inputs.
- candidate selection, listening, and editing are optional user actions under `human_choices[]`.

