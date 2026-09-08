# Cut Authoring (p420)

p420 は scene event を viewer-facing cut contracts へ変換する authoring stage である。入力は
source-grounded script.md、scene event、scene intent、visual-value handoff。出力は
cut_blueprint、coverage plan、p450 skeleton manifest への materialization input。

## Outcome

各 production scene が次を満たす。

- scene_cut_coverage_plan が authored event beats と distinct visual obligations を cut に割り当てる
- 各 cut が cut_contract.source_event_contract で source beat を参照する
- one viewer-facing intent、screen question、causal proof、visible evidence、role coverage がある
- first-frame still の開始状態と p800 motion の終端が concrete である
- narration role または explicit silence contract と downstream handoff がある
- scene/cut/event IDs と ordered selectors が一意で解決する

## Cut count

```text
by_distinct_obligations = count(unique obligation_id)
by_event_beats = count(unique event_beat_id where must_be_seen is not false)
selected = max(by_distinct_obligations, by_event_beats)
```

importance、target duration、固定 seconds-per-cut は count の根拠にしない。同じ事実を証明
する obligation は一つにまとめ、別の visible responsibility がある場合だけ cut を増やす。
尺は cut duration、narration、intentional silence、scene 配分、provider capability で調整する。

## p420a Coverage planning

```yaml
scene_cut_coverage_plan:
  coverage_strategy: reverse_from_scene_event
  source_schema_version: scene_event_v1
  event_beat_inventory:
    - beat_id: scene_01_beat_01
      beat_function: custom
      must_be_seen: true
      assigned_cut_ids: [scene_01_cut_01]
  scene_obligations:
    - obligation_id: scene_01_obligation_01
      source: causal_turn
      evidence: "visible proof"
      assigned_cut_ids: [scene_01_cut_01]
  cut_assignments:
    - cut_selector: scene_01_cut_01
      obligation_ids: [scene_01_obligation_01]
      event_assignment:
        source_event_contract:
          primary_event_beat_id: scene_01_beat_01
          source_event_beat_ids: [scene_01_beat_01]
      target_beat: "visible turn"
```

Inventory rows must preserve every authored beat ID exactly once and in order. Assignment rows may omit
must_be_seen: false beats. All referenced selectors and IDs are checked before manifest materialization.

## p420b Cut contract drafting

```yaml
cut_contract:
  schema_version: "3.0"
  source_event_contract:
    primary_event_beat_id: scene_01_beat_01
    source_event_beat_ids: [scene_01_beat_01]
    event_beat_function: custom
    event_time_position: before_trigger
    event_facts_to_preserve: []
    event_facts_not_to_invent: []
    allowed_reveal_info_ids: []
    forbidden_reveal_info_ids: []
  intent_budget:
    primary_intent: ""
    assigned_obligation_ids: []
  viewer_contract:
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
    event_fact_visible_in_still: ""
    not_yet_happened_in_still: []
  motion_contract:
    starts_from_first_frame: true
    source_event_beat_id: scene_01_beat_01
    motion_brief: ""
    end_state: ""
    must_not_add: []
  narration_contract:
    schema_version: narration_contract_v2
    source_event_beat_ids: [scene_01_beat_01]
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

The cut_contract is a design object, not provider prompt text. scene_contract may remain as a legacy
read alias but is never a completion signal.

## p420c Structural checks

- source beat IDs, obligation IDs, cut selectors, asset IDs, and handoff selectors are unique and valid
- event inventory equals the authored ordered event sequence
- each must-see beat has a cut assignment and each cut has one primary intent
- first-frame visible state is imageable and does not show a future event
- motion starts from the first frame and does not add an unlisted character, object, location, or reveal
- narration stays inside its event boundary or carries an explicit silence reason and duration
- duration and provider capability are valid
- script and skeleton manifest selectors are exactly equal

A failed check identifies the artifact and selector to edit. After the owner updates the contract,
rerun checks and materialize p450. Do not write a synthetic pass field.

## p420d Handoff matrix

For every cut, record what arrives from the preceding cut, what is delivered to the next cut, and which
asset/image/narration/video fields consume it. Use exact IDs and source hashes.

## p420e Manifest materialization

p450 writes video_manifest.md.scenes[].cuts[] from the checked cut contracts. It copies canonical
contracts and request placeholders, then stores a manifest/source digest. p500 and later stages compile
provider payloads from this manifest.

## References

- docs/script-creation.md
- docs/implementation/scene-loop.md
- docs/data-contracts.md
- workflow/scene-outline-template.yaml
- workflow/cut-blueprint-template.yaml

