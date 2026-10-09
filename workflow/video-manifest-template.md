# 動画マニフェスト: テンプレート

新規source_first_v2は `docs/implementation/visual-planning.md` を参照。下記amplification/expressive例はv1専用。
v2はmetadataの版・source_visual_value bindingと、sceneのsource_story_scene_id・visual_notesをscriptから保持する。

以下は単一の機械可読YAML例。sourceからscene/cut/audio/image/videoへ投影する。
`manifest_phase: skeleton`は設計、`production`は実行用requestがmaterializeされた状態。
既存物語ではコメントのadaptation markerを有効化し、source valueの参照を一方向に保持する。
レビュー文書や点数・承認証跡を生成条件にしない。

```yaml
manifest_phase: skeleton|production
video_metadata:
  # adaptation_value_contract: "required_v1"
  topic: <topic>
  source_story: output/<topic>_<timestamp>/story.md
  source_script: output/<topic>_<timestamp>/script.md
  source_visual_value: output/<topic>_<timestamp>/visual_value.md
  created_at: <ISO8601>
  target_duration_seconds: 300
  estimated_duration_seconds: 300
  duration_seconds: 300
  experience: cinematic_story|cloud_island_walk|world_walk
  source_run: null
  aspect_ratio: '16:9'
  resolution: 1280x720
  time: ''
  scene_time_of_day_contract: required_v1
  scene_time_of_day_visual_basis_contract: required_v1
source_bindings:
  story:
    path: story.md
    sha256: sha256:<hash>
  script:
    path: script.md
    sha256: sha256:<hash>
  visual_value:
    path: visual_value.md
    sha256: sha256:<hash>
  asset_plan:
    path: asset_plan.md
    sha256: sha256:<hash>
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
assets:
  character_bible:
  - character_id: character_01
    reference_images:
    - assets/characters/character_01_front.png
    fixed_prompts: []
    source_refs: []
    variants: []
  object_bible: []
  location_bible: []
  style_guide:
    visual_style: 実写映画調、自然な映画照明、実物セット感
    reference_images: []
    forbidden:
    - 画面内テキスト
    - 字幕
    - ロゴ
    - ウォーターマーク
audio_story_plan:
  schema_version: audio_story_plan_v1
  authoring_status: draft|authored
  audience_promise: ''
  narrator_bible:
    relationship_to_story: witness|companion|historian|limited_observer|omniscient
    knowledge_boundary: []
  scene_arcs: []
  silence_budget:
    purpose: ''
    protected_moments: []
  continuous_full_draft: ''
narration_spans:
- span_id: ns_001
  source_cut_ids: []
  text: ''
  tts_text: ''
  story_job: first_question|causal_bridge|payoff|reaction|aftertaste
  tts_generation_group_id: ''
narration_authoring:
  schema_version: narration_authoring_v1
  status: missing|draft|human_locked|silent
  revision: 0
  text_hash: sha256:<hash>
  tts_hash: sha256:<hash>
  source: author|user
  updated_at: ''
  updated_by: ''
scenes:
- scene_id: 1
  time_of_day: 朝
  time_of_day_visual_basis: 低い自然光、長い影、穏やかな色温度
  scene_intent:
    story_purpose: ''
    dramatic_question: ''
    value_shift:
      from: ''
      to: ''
      visible_evidence: []
    causal_turn: ''
    audience_information: []
    withheld_information: []
    reveal_constraints: []
    visual_thesis: ''
    handoff_to_next_scene: ''
    scene_value_amplification:
      schema_version: scene_value_amplification_v1
      source_value_refs: []
      why_this_scene_matters: ''
      audience_state_before: ''
      audience_state_after: ''
      cinematic_gain:
        performance: ''
        blocking_and_space: ''
        camera_and_composition: ''
        edit_and_rhythm: ''
        sound: ''
      iconic_moment_target: ''
      must_preserve_story_facts: []
      must_not_reduce_to: []
      success_evidence: []
      emotional_contradiction: ''
  scene_event:
    schema_version: scene_event_v1
    event_logline: ''
    start_situation: ''
    source_story_beat_ids: []
    event_sequence:
    - beat_id: scene_01_beat_01
      beat_function: custom
      source_story_beat_ids: []
      what_happens: ''
      visible_action: ''
      visible_reaction: ''
      immediate_consequence: ''
      required_visual_evidence: []
    turning_event:
      source_event_beat_id: scene_01_beat_01
      irreversible_change: ''
    end_situation: ''
    forbidden_event_changes: []
  location:
    mode: single|sequence
    sequence: []
    segments: []
  cuts:
  - cut_id: 1
    cut_status: active|deleted
    source_event_contract:
      primary_event_beat_id: scene_01_beat_01
      source_event_beat_ids:
      - scene_01_beat_01
      event_beat_function: custom
      event_time_position: before_trigger
      event_facts_to_preserve: []
      event_facts_not_to_invent: []
      allowed_reveal_info_ids: []
      forbidden_reveal_info_ids: []
    cut_contract:
      schema_version: '3.0'
      expressive_contract:
        schema_version: cut_expressive_contract_v1
        source_value_refs: []
        scene_amplification_ref: scene1.scene_intent.scene_value_amplification
        audience_experience_delta: ''
        expressive_function: recognition|withhold|pressure|release|contrast|reaction|reframe|afterimage|spectacle|transition
        performance_beat: ''
        visual_pressure: ''
        attention_shift: ''
        edit_trigger: ''
        sound_function: ''
        emotional_afterimage: ''
        must_not_reduce_to: []
      intent_budget:
        primary_intent: ''
        assigned_obligation_ids: []
      viewer_contract:
        target_beat: ''
        screen_question: ''
        audience_knowledge_delta: ''
        causal_proof: ''
        visual_evidence: []
        required_roles: []
        must_show: []
        must_avoid: []
      first_frame_contract:
        imageable: true
        source_event_beat_id: scene_01_beat_01
        event_time_position: before_trigger
        event_fact_visible_in_still: ''
        not_yet_happened_in_still: []
        first_frame_brief: ''
      motion_contract:
        source_event_beat_id: scene_01_beat_01
        starts_from_first_frame: true
        motion_brief: ''
        end_state: ''
        must_not_add: []
      narration_contract:
        schema_version: narration_contract_v2
        source_event_beat_ids:
        - scene_01_beat_01
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
        prompt: ''
        negative_prompt: ''
        sha256: sha256:<prompt hash>
        source_digest: sha256:<source hash>
        provider_request_binding:
          generation_job_id: JOB_001
          item_id: scene_01_cut_01
          turn_id: turn_001
          reference_sha256s: {}
          destination: assets/scenes/scene_01_cut_01.png
      request_revision: 0
      output: ''
      output_sha256: sha256:<hash>
    video_generation:
      tool: kling_3_0
      mode: image_to_video
      first_frame: assets/scenes/scene_01_cut_01.png
      last_frame: ''
      duration_seconds: 8
      api_prompt_payload:
        policy_version: video_api_prompt_v1
        compiler_version: conditional_video_prompt_compiler_v5
        projection_registry_version: video_prompt_projection_registry_v5
        provider: kling_3_0
        prompt: ''
        negative_prompt: ''
        sha256: sha256:<prompt hash>
        source_digest: sha256:<source hash>
        provider_request_binding:
          generation_job_id: JOB_001
          item_id: scene_01_cut_01
          turn_id: turn_001
          first_frame: assets/scenes/scene_01_cut_01.png
          last_frame: ''
          references: []
          reference_roles: []
          reference_content_sha256: {}
          destination: assets/video/scene_01_cut_01.mp4
      request_revision: 0
      output: ''
      output_sha256: sha256:<hash>
  render_units:
  - unit_id: 1
    source_cut_ids:
    - 1
    video_generation:
      duration_seconds: 8
      first_frame: assets/scenes/scene_01_cut_01.png
      last_frame: ''
      prompt: ''
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

実行前に型・ID参照・実ファイル・request/provenanceの整合を確認する。
providerは保存済みのpayloadを読み、生成時に自由文から再構築しない。
render_unitsは各scene内に置き、元cutの順序と時間を保持する。
画像・音声の候補選択、試聴、編集は任意のユーザー操作として利用できる。

新規p400の撮影拡張は `cinematic_direction.json.film_language` を正本とし、
cutの `cinematic_contract.execution` とimageの `first_frame_visual_plan.film_language`へ投影する。
`video_generation.native_audio` は `mode: off|natural_sound|dialogue_and_sound`、
`sound_events: []`、`dialogue: []` を持つ。台詞のspeaker/source_quote/source_beat_idsは
[撮影方針契約](../docs/implementation/cinematic-language.md)に従う。旧manifestの未指定はoffとして読む。
