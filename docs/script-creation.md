# Script Creation System

`docs/story-creation.md` が作る物語を、`docs/video-generation.md` が読める scene/cut、
narration、provider handoff へ変換する。script stage は直接 authoring → ordinary structural
validation → manifest materialization の順に進み、画像・音声・動画 provider は後続 stage が呼ぶ。

## Outcome Contract

入力:

- source-grounded `story.md`
- optional `visual_value.md`
- stage source/readset と `docs/data-contracts.md`

出力:

- `script.md`
- `video_manifest.md`（`manifest_phase: skeleton`）
- scene/cut の source references、handoff、narration contract、optional user changes

完了条件:

- 各 scene が purpose、dramatic question、value shift、causal turn、visible evidence、
  before/after state、handoff を持つ
- 各 cut が一つの viewer-facing intent、event beat ID、first-frame state、motion boundary、
  narration boundary、asset dependency、downstream handoff を持つ
- facts は `story.md` / `research.md` の source IDs に追跡でき、creative additions と区別される
- `script_metadata.time` は物語の歴史的時代、`scenes[].time_of_day` は一日の時間帯として
  story から一方向に投影される
- provider prompt syntax、実行 settings、asset wiring は manifest 側へ渡し、p400 では provider を呼ばない
- structure、IDs、references、selector closure、duration fields、manifest synchronization が
  ordinary validator を通る

## Source と creative boundary

史実、数値、固有名詞、文献差分、伝承バリエーションは source reference とともに保持する。
演出、dialogue、心理、visual metaphor は creative addition として記録する。矛盾する source
variant を一つの scene/settings に混成する場合は、ユーザーの明示した hybridization choice と
selected source IDs を run artifact に保存する。

## p400 Cinematic Scene Design Contract

p400 は story の各部分を、観客が映像で経験できる不可逆な scene へ翻訳する。時間を均等に
割った説明段落は scene にならない。場所、情報、感情、因果、視覚価値のいずれかが変化し、
次 scene の起点を生む必要がある。

### 観客の理解と意味の引き継ぎ

story で採用された [観客の理解と意味の設計](story-creation.md#観客の理解と意味の設計) を、
既存の scene/cut 記述へ具体化する。`visual_value.md` がない場合は story の意図と根拠から
引き継ぐ。別の計画 block、象徴、反復回数、肯定的な変容を追加義務にしない。

- scene の `start_state / end_state` 内の `audience_knowledge` と `reveal_contract` を引き継ぎ、
  その時点の観客に何が分かり、何はまだ分からないかを保つ。人物の知識とは区別する。
- `scene_intent.value_shift.visible_evidence` と `scene_event.event_sequence[]` の
  `visible_action / required_visual_evidence / audience_knowledge_delta` で、解釈を支える
  行動・関係・状況を具体化する。世界観はその主体の立場から示し、全員の総意へ一般化しない。
- `cut_blueprint.audience_knowledge_delta / visual_evidence`（manifest では
  `cut_contract.viewer_contract.audience_knowledge_delta / visual_evidence`）へ、その cut が理解を更新・補強・維持する具体的な証拠を置く。
  毎 cut の新情報や意味の反転は求めず、scene を割る理由のない追加 cut を作らない。
- 反復を採用した場面では、同じと認識させる要素と、その時点の行動・文脈の違いを分ける。
  映像・音・台詞・ナレーションの分担を決め、説明で未開示の情報や意図的な曖昧さを消さない。
- first frame へ後段の結果を描かない。motion には今回起こる動作、narration には担当する
  情報を渡す。抽象的な象徴の解説や全編の意味の推移を provider prompt に連結しない。

事実・結末・開示順は上流を保ち、表現上の意味を物理的な状態変化や新しい story event と
取り違えない。適用しない作品には、既存の source / event / cut 契約だけを使う。

### Scene Intent Card

```yaml
scene_intent:
  schema_version: scene_intent_v1
  scene_id: scene_01
  story_purpose: "この scene が全体で進める責務"
  dramatic_question: "scene 中に観客が追う問い"
  value_shift:
    from: "開始時の状態"
    to: "終了時の状態"
    visible_evidence: ["画面で読める変化"]
  causal_turn: "次 scene を発生させる不可逆の出来事"
  audience_information: []
  withheld_information: []
  reveal_constraints: []
  affect_transition: "感情の変化"
  character_state:
    start: ""
    end: ""
    visible_behavior: []
  visual_thesis: "この scene を代表する描画可能な一枚の意味"
  spatial_plan:
    location_id: ""
    screen_geography: ""
    continuity_anchors: []
  production_risks: []
  handoff_to_next_scene: "次 scene へ渡す視覚/音/因果アンカー"
  story_specificity:
    non_compressible_beat: ""
    scene_promotion_reason: ""
    unique_scene_responsibility: ""
    actor_forces:
      protagonist: ""
      opposing: []
      helping: []
      observing: []
      pressure_method: ""
    meaning_ladder:
      protagonist_stage: ""
      relationship_stage: ""
      object_or_setpiece_stage: ""
    concrete_handoff:
      incoming_trigger: ""
      outgoing_anchor: ""
      outgoing_pressure: ""
    anti_template_language:
      story_specific_terms: []
      specificity_note: ""
  handoff_chain:
    incoming: {anchor_id: "", anchor_type: "object|sound|gaze|gesture|threat|question|none"}
    outgoing: {anchor_id: "", anchor_type: "object|sound|gaze|gesture|threat|question|terminal", next_scene_selector: ""}
  coverage_checks:
    audience_information_covered: false
    visualizable_action_covered: false
    value_shift_visible: false
    causal_turn_visible: false
    next_scene_connection_checked: false
  handoff_notes:
    p500_asset: []
    p600_image: []
    p700_narration: []
    p800_video: []
```

The scene validator requires a non-empty question, visible value shift, causal turn, source references,
concrete visual evidence, unique IDs, valid locations, and a valid next-scene handoff. Plan duration
fields are advisory; duration arithmetic alone never invents a scene or cut.

### p410 Scene authoring

`p410` creates and integrates scene intent cards. The author reads story source IDs and visual-value
anchors, decides scene ownership and ordering, records withheld/revealed information, and writes
`scene_event.event_sequence[]`. A scene may be added, merged, split, or reordered only when the
source beat and its distinct responsibility justify that operation. Structural checks run after the
author commits the scene set.

### Scene event

```yaml
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
      story_information_revealed_ids: []
  turning_event:
    source_event_beat_id: scene_01_beat_01
    irreversible_change: ""
  end_situation: ""
  offscreen_context: []
  forbidden_event_changes: []
```

Beat IDs are non-empty, unique, ordered, and source-grounded. `beat_function` is an open authoring
key; `setup`, `pressure`, `turn`, `payoff`, `threshold`, and `custom` are examples, not a
required ladder. Provider fields such as camera, prompt, lens, or motion do not belong in this object.

### p420 Cut Blueprint

`p420` turns each scene event into renderable cuts. Cut count follows distinct visual obligations and
must-see event beats, never a fixed seconds-per-cut formula. Keep one primary intent per cut; use a
longer hold, silence, or an existing cut when the same obligation does not justify another cut.

```yaml
cut_blueprint:
  schema_version: cut_blueprint_v1
  cut_id: scene_01_cut_01
  cut_role: main|sub|transition|reaction|visual_payoff
  cut_function: custom
  duration_intent: short|standard|hold
  target_beat: "この cut で伝える一つのこと"
  screen_question: "画面から読む問い"
  dramatic_job: ""
  audience_knowledge_delta: ""
  causal_proof: ""
  visual_evidence: []
  required_roles: []
  source_event_contract:
    primary_event_beat_id: scene_01_beat_01
    source_event_beat_ids: [scene_01_beat_01]
    event_beat_function: custom
    event_time_position: before_trigger
    event_facts_to_preserve: []
    event_facts_not_to_invent: []
    allowed_reveal_info_ids: []
    forbidden_reveal_info_ids: []
  must_show: []
  must_avoid: []
  done_when: []
  visual_beat: ""
  first_frame_brief: ""
  static_first_frame_rule: ""
  motion_brief: ""
  narration_role: setup|fact|emotion|contrast|aftertaste|silent
  voice_function: information|emotion|causality|time|viewpoint|world_rule|contrast|meaning|aftertaste|silence
  visual_distance_policy: stay_close|contextual|meaning_first|silent
  asset_dependency_hint:
    character_ids: []
    object_ids: []
    location_ids: []
    reusable_still_candidates: []
```

Structural validation checks exact event beat inventory, selector uniqueness, source/event reference
integrity, first-frame imageability, motion ceiling, narration boundaries, asset IDs, and handoff
closure. The API prompt is compiled later and is never copied verbatim from this blueprint.

### p440 User changes and sync

Optional user change requests are stored in `script.md.human_change_requests[]`. Each request has a
stable ID, original/current selectors, normalized actions, status, and resolution notes. The p400 owner
applies accepted changes in one transaction, then reruns the structural checks and regenerates the
skeleton manifest. Requests do not grant permission to alter source facts or reveal order without the
explicit hybridization choice where that is required.

```yaml
human_change_requests:
  - request_id: change_001
    created_at: ISO8601
    raw_request: ""
    original_selectors: [scene_01_cut_01]
    current_selectors: [scene_01_cut_01]
    normalized_actions: []
    status: pending|normalized|applied|deferred
    resolution_notes: ""
```

### p450 Skeleton manifest

`p450` materializes `video_manifest.md` with `manifest_phase: skeleton`. It contains scene/cut
selectors, the canonical `cut_contract`, optional legacy `scene_contract` read aliases, asset ID
placeholders, and image/audio/video execution shells. It does not call a provider.

## 1. Narration authoring

`script.md` is the narration source of truth. `narration` is the readable script,
`tts_text` is the provider string, and `elevenlabs_prompt` is its authoring source. p400 records
the role, event boundary, visible overlap rule, and timing intent; p700 later projects the current text
to TTS and measures the generated audio.

### Full-run authoring

Write a continuous spoken draft first, then split it into `narration_spans[]` anchored to one or more
cuts. Preserve canonical cut order. A visual-only cut may use an explicit silence contract with a reason
and duration. Never add narration merely to fill target duration.

```yaml
narration_authoring:
  schema_version: narration_authoring_v1
  status: missing|draft|human_locked|silent
  revision: 0
  text_hash: sha256:<hash>
  tts_hash: sha256:<hash>
  source: author|user
  updated_at: ISO8601
  updated_by: ""
```

Users may listen to candidates, select one, edit text, or defer a choice. These actions are stored as
`human_choice.*`; a changed text/settings revision invalidates the prior TTS candidate and triggers
ordinary hash and provenance checks.

## 2. Responsibilities and handoff

`script.md` owns:

- story meaning, scene intent, event order, source references, reveal constraints
- cut intent, visual evidence, first-frame brief, motion boundary, narration role
- narration text, TTS text, optional user change requests
- asset candidates and downstream handoff notes

`video_manifest.md` owns:

- materialized scene/cut execution records
- asset references and image/video/audio provider settings
- compiled prompt payloads, request snapshots, generated output paths
- render units and ordered source cut IDs

Downstream stages project values one way. They do not create another authoring root or infer facts from
provider output.

## 3. Structural checks before downstream generation

Before p500/p600/p700/p800, run validators for:

- required fields, types, unique scene/cut/beat IDs, and YAML/JSON/Markdown shape
- source, asset, selector, handoff, and location references
- exact event beat inventory and must-see coverage
- first-frame state versus motion start/end state
- narration event boundary and silence contract
- script/manifest selector equality and target duration
- provider capability, request snapshot, prompt hash, ordered references, and source digest

A failed check identifies the owning artifact and selector. The owner edits that artifact, reruns the check,
and then materializes the next request. No separate production verdict or score is required.

## 4. Legacy compatibility

Older short-form templates may contain fields that are ignored by current generation. They are not a
source for new authoring. Current runs use the active slots and contracts in
`docs/data-contracts.md`; old state entries are preserved as history and never synthesized into a
new production slot.
