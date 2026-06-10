# Cut Conte Template v3.0

Use this template after p420 cut contracts are approved.

## Scene

- scene_id:
- scene_selector:
- dramatic_question:
- value_shift:
- causal_turn:
- handoff_to_next_scene:

## Coverage Plan

- coverage_strategy: reverse_from_scene_event
- source_schema_version: scene_event_v1
- min_cut_count:
- event_beat_inventory:
- candidate_function_labels:
- cut_assignments:
- scene_event_sequence:
- visual_evidence_to_show:
- causal_turn_cut_selector:
- handoff_cut_selector:

## Cut Cards

### scene1_cut1

- cut_function:
- target_beat:
- screen_question:
- audience_knowledge_delta:
- causal_proof:
- visual_evidence:
- required_roles:
- source_event_contract:
  - primary_event_beat_id:
  - source_event_beat_ids:
  - event_beat_function:
  - event_time_position:
  - event_facts_to_preserve:
  - event_facts_not_to_invent:
- anti_redundancy_key:
- visual_proof:
- first_frame_brief:
- static_first_frame_rule:
- action_completion_state:
- motion_brief:
- narrative_position:
- voice_function:
- visual_distance_policy:
- pronunciation_targets:
- narration_role:
- silence_reason:
- event_context_for_cut:
  - derived_from: scene_event.event_sequence + cut_contract.source_event_contract
  - editable: false
- receives_from_previous:
- delivers_to_next:

#### Frame Design

- foreground:
- midground:
- background:
- subject_priority:
- camera_intent:
- lighting_intent:
- screen_direction:

#### Continuity

- start_state:
- end_state:
- carry_forward_to_next_cut:
- continuity_risks:

#### Downstream Handoff

- p500_asset:
- p600_image:
- p700_narration:
- p800_video:
