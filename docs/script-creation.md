# Script Creation System

source_first_v2 の cut 設計は、story の authored `event_sequence` 順を保持する。
各 visible beat は既定で1 cut。複数cutへ分解する場合は beat の `cut_transitions[]`
に `transition_id`、`first_frame_brief`、`motion_brief`、`motion_end_state` を明示する。
同じbeatの分割は連続して配置し、別beatへ進んだ後に前のbeatを再割当しない。
`source_event_ids` は research の元IDを、`source_transition_id` は分割IDを
script/manifest の `cut_contract.source_event_contract` まで保持する。
coverage matrix は明示されたID参照から作り、語句一致・比例配分・固定beat位置で
欠落を補完しない。`must_be_seen: false` のbeatはinventoryに残しcutを要求しない。
尺が既存provider上限へ収まらない場合、定型動作を追加せず執筆側で必要な分割を作る。

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

## ナレーションの語り口と読み

執筆前に [標準の語り口・音声タグ・単語の修正](implementation/narration-prompting.md#標準の語り口音声タグ単語の修正) を読む。
日本語の語りは、ですます調・落ち着いた温かい声・分かりやすい単語を既定にし、音声タグと読みをTTS本文へ反映する。
runの `narration_style.json` があれば、承認された話者・語り口・用語修正を引き継ぐ。

## Source と creative boundary

史実、数値、固有名詞、文献差分、伝承バリエーションは source reference とともに保持する。
演出、dialogue、心理、visual metaphor は creative addition として記録する。矛盾する source
variant を一つの scene/settings に混成する場合は、ユーザーの明示した hybridization choice と
selected source IDs を run artifact に保存する。

## p400 Cinematic Scene Design Contract

新規制作は [p400 Cinematic Authoring](implementation/p400-cinematic-authoring.md) を優先する。
LLMが全編・前後sceneとp300の演出を読み、scene単位でcut列・カメラ・音・尺を執筆する。
`cinematic_direction.json` がp400の演出の正本。コードは参照と状態の受渡しを検証・投影する。
以下の旧形式の必須解釈や例文を、新経路の定型演出として補完しない。

`source_first_v2` runでは [映像設計契約](implementation/visual-planning.md) を優先する。
scene/event/stateはstoryから直接引き継ぎ、runtime sceneとsource sceneの対応を保存する。
下記のdramatic question、value shift、causal turn等は作品で必要なときの設計項目であり、
新規v2で全sceneに非空の葛藤・反転・不可逆な変化を追加する条件ではない。
原作の状態を維持するsceneも許可する。source/ID/順序/reveal/handoff検証は引き続き必須。

p400 は story の各部分を、観客が映像で経験できる行為と状態へ翻訳する。変化がある場合は
その原因と結果を具体化し、変化しない場面はその持続を保つ。時間を均等に割るためだけに
場面や感情の反転を増やさない。

ナレーションでは既存の `audio_story_plan.open_loops[].payoff_type: intentional_unresolved` を
尊重する。意図的に未解決の問いに、教訓・和解・恒久的な改心を補わない。人物が誠実に語る
自己説明はその人物の発言として扱い、観察事実や意図的な嘘と混同しない。
`scene_intent.visual_notes` は執筆背景として渡し、その指示文自体を読み上げない。
silent、human_locked、原稿からspan/cut/TTSへの同期契約は維持する。

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

The scene validator checks source references, concrete visual evidence, unique IDs, valid locations,
and a valid next-scene handoff. Questions, value shifts and causal turns are authored only when the scene needs them. Plan duration
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

人物を出さず空気感・余韻・scene接続を担うBロールは `cut_role: sub` とし、
[人物を出さないBロールの設計](implementation/b-roll-design.md) に従う。
mainで必須の出来事を成立させ、subの被写体・技法・音・前後の接続をcut設計時に確定する。
末尾1〜2cutの固定枠にはせず、前scene末尾と次scene冒頭を一組として必要性を判断する。

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

ToC のナレーションは全編を通して第三者視点（三人称）に固定する。語り手は物語の外から
人物・出来事・状況を語り、登場人物になりきった一人称や、視聴者を物語の当事者にする
二人称へ切り替えない。登場人物の台詞・明示された引用内の人称は原文に従い、ナレーションの
視点とは区別する。第三者視点でも、source の根拠、人物の知識境界、観客への開示順は守る。
この方針を通し原稿、`narration_spans[]`、`narration`、`tts_text` に一貫して適用する。

Write a continuous spoken draft first, then split it into `narration_spans[]` anchored to one or more
cuts. Preserve canonical cut order. A visual-only cut may use an explicit silence contract with a reason
and duration. Never add narration merely to fill target duration.

B-roll (`cut_contract.a_roll_or_b_roll: b_roll`) may omit narration and subtitles independently.
Leave `narration`/`tts_text` empty and omit a voiced `narration_tool` when no speech is intended; do not
invent spoken text, voice tags, or subtitles to satisfy a per-cut quota. Authored speech and subtitles
remain optional choices and must be preserved. Existing manifest shot-design B-roll projections are
also recognized; see `docs/implementation/video-integration.md` for the runtime and timing contract.

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

## 終幕の焦点と観客の余韻

終幕では、出来事の後始末に加え、観客が最後に誰の何を感じて見終えるかを設計する。
主人公の物語では、脇役の事情を整理した後に、主人公または中心となる関係へ感情の焦点を戻す。
最後の主要cutで、冒頭から何が変わったかを表情、距離、触れ合い、行動などの具体的な画で受け取れるようにする。
群像劇など別の人物を最後に置く構成は、その人物が結末の主題を担う理由を明示する。
作品に合う納得と満足、感動を intended affect として狙い、観客の実際の感情を保証するとは書かない。

- 最後の2〜3cutを続けて読み、中心人物や中心関係が脇役の説明に埋もれていないか確認する。
- 結末に必要な出来事が成立した後は、語りで幸福や教訓を繰り返さず、画面と間、後工程の音楽に余地を残す。
- 人物を見届けることが終幕の責務ならmainとして設計する。末尾に人物なしBロールを必ず置く規則にはしない。
- 同じ寄りの画を3枚並べず、行動→応答→関係を見届ける画のように各cutの役割を分ける。
- 作品が意図した未解決や悲劇も保持する。原作にない後日談を加える場合は、ユーザーの追加意図と創作範囲を記録する。

音声のフロント試聴と最終合成は `docs/implementation/video-integration.md` の「ナレーション音量・試聴・合成の共通処理」に従う。Codex専用のtmpスクリプトへ音量・間の処理を閉じ込めず、`toc.narration_audio` を共通利用する。
