# 没入型: 雲上の島を歩く体験（cloud_island_walk）マニフェストテンプレ

`/toc-immersive-ride --experience cloud_island_walk` 用。共通 contract は
`workflow/video-manifest-template.md`、entrypoint は
`docs/implementation/immersive-ride-entrypoint.md` を参照する。

```yaml
manifest_phase: skeleton|production
video_metadata:
  topic: "<topic>"
  source_story: "output/<topic>_<timestamp>/story.md"
  source_script: "output/<topic>_<timestamp>/script.md"
  created_at: ISO8601
  target_duration_seconds: 300
  duration_seconds: 0
  experience: cloud_island_walk
  aspect_ratio: "16:9"
  resolution: "1280x720"
  frame_rate: 24
  time: ""

source_bindings:
  story: {path: story.md, sha256: sha256:<hash>}
  script: {path: script.md, sha256: sha256:<hash>}
  visual_value: {path: visual_value.md, sha256: sha256:<hash>}
  source_digest: sha256:<hash>

assets:
  character_bible: []
  object_bible: []
  location_bible: []
  style_guide:
    visual_style: "実写、シネマティック、実物セット感"
    forbidden: [画面内テキスト, 字幕, ウォーターマーク, ロゴ, 自撮り]
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
  - scene_id: 10
    zone_id: zone_01
    timestamp: "00:00-00:08"
    time_of_day: ""
    visual_metaphor: ""
    path_or_bridge: ""
    anchor_object_id: ""
    image_generation:
      tool: codex_builtin_image
      character_ids: []
      object_ids: []
      references: []
      prompt: ""
      output: assets/scenes/scene10.png
    video_generation:
      tool: kling_3_0
      mode: image_to_video
      duration_seconds: 8
      first_frame: assets/scenes/scene10.png
      last_frame: ""
      motion_prompt: ""
      output: assets/video/scene10.mp4
    audio:
      narration:
        authoring_status: missing
        text: ""
        tts_text: ""
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
  source_refs: pending|passed|failed
  requests: pending|passed|failed
  outputs: pending|passed|failed
  provenance: pending|passed|failed
  errors: []
```

Cloud island rules:

- Zone、path、bridge、anchor object を物理 metaphor として設計し、文字で概念を説明しない。
- 一人称歩行を使う場合は水平線、カメラ高、前進方向を scene 間で continuity contract に記録する。
- 同じ anchor/asset の reference bytes、request snapshot、output provenance を保持する。
- scene/cut IDs は manifest 順で処理し、固定 scene 数や尺だけで filler scene を作らない。
- candidate selection、listening、editing は optional user actions として `human_choices[]` に保存する。

