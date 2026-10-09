"""Project authored beats into cuts without inventing or recycling plot events."""
from copy import deepcopy


def authored_cut_plan(scene_event: dict, *, scene_id: int, location_name: str,
                      protagonist: str, character_names: dict | None = None) -> dict:
    sequence = scene_event.get('event_sequence')
    if not isinstance(sequence, list) or not sequence:
        raise ValueError('authored event_sequence is missing')
    cuts, inventory, assignments = [], [], []
    seen_beats = set()
    for beat in sequence:
        if not isinstance(beat, dict):
            raise ValueError('authored beat must be an object')
        beat_id = beat.get('beat_id')
        if not isinstance(beat_id, str) or not beat_id.strip() or beat_id in seen_beats:
            raise ValueError('authored beat_id is missing or duplicated')
        seen_beats.add(beat_id)
        source_ids = beat.get('source_event_ids')
        if (not isinstance(source_ids, list) or not source_ids
                or any(not isinstance(value, str) or not value.strip() for value in source_ids)
                or len(source_ids) != len(set(source_ids))):
            raise ValueError(f'{beat_id}: invalid source_event_ids')
        must_be_seen = beat.get('must_be_seen', True)
        if not isinstance(must_be_seen, bool):
            raise ValueError('must_be_seen must be boolean')
        evidence = deepcopy(beat.get('required_visual_evidence', []))
        row = dict(beat_id=beat_id, beat_function=beat.get('beat_function', ''),
                   what_happens=beat.get('what_happens', ''),
                   required_visual_evidence=evidence, must_be_seen=must_be_seen,
                   assigned_cut_ids=[])
        inventory.append(row)
        if not must_be_seen:
            continue
        transitions = beat.get('cut_transitions', [None])
        if not isinstance(transitions, list) or not transitions:
            raise ValueError(f'{beat_id}: cut_transitions must be a nonempty list')
        transition_ids = set()
        for transition in transitions:
            if transition is not None:
                if not isinstance(transition, dict) or any(
                    not isinstance(transition.get(k), str) or not transition[k].strip()
                    for k in ('transition_id', 'first_frame_brief', 'motion_brief', 'motion_end_state')
                ):
                    raise ValueError(f'{beat_id}: invalid cut transition')
                if transition['transition_id'] in transition_ids:
                    raise ValueError(f'{beat_id}: duplicate transition_id')
                transition_ids.add(transition['transition_id'])
            elif 'cut_transitions' in beat:
                raise ValueError(f'{beat_id}: invalid cut transition')
            local = {**beat, **(transition or {})}
            concrete = beat.get('concrete_event') or {}
            state = local.get('visible_character_state') or {}
            start = local.get('first_frame_brief') or state.get('posture') or local.get('visible_action')
            motion = local.get('motion_brief') or local.get('visible_action')
            end = local.get('motion_end_state') or local.get('immediate_consequence')
            if not all(isinstance(v, str) and v.strip() for v in (start, motion, end)):
                raise ValueError(f'{beat_id}: missing drawable start/motion/end')
            roles = deepcopy(beat.get('required_roles', beat.get('participants', [])))
            subject = str(local.get('primary_subject') or concrete.get('primary_subject')
                          or (character_names or {}).get(roles[0] if roles else '', '')
                          or protagonist)
            location = str(local.get('location') or concrete.get('where') or location_name)
            transition_id = str((transition or {}).get('transition_id') or beat_id)
            obligation_id = f'event:{beat_id}:{transition_id}'
            selector = f'scene{scene_id}_cut{len(cuts)+1:02d}'
            cut = dict(
                obligation_id=obligation_id, source='scene_event.event_sequence',
                primary_event_beat_id=beat_id, source_event_beat_ids=[beat_id],
                source_event_ids=deepcopy(source_ids),
                source_transition_id=transition_id,
                event_beat_function=beat.get('beat_function', 'event'),
                event_time_position='before_trigger', cut_function=beat.get('beat_function', 'event'),
                target_beat=beat.get('what_happens', ''),
                screen_question=beat.get('screen_question', ''),
                dramatic_job=beat.get('what_happens', ''),
                visual_proof=start, first_frame_brief=start,
                motion_brief=motion, motion_end_state=end, done_when=end,
                must_show_extra=deepcopy(local.get('required_visual_evidence', evidence)),
                visual_evidence=deepcopy(local.get('required_visual_evidence', evidence)),
                foreground=local.get('foreground', ''), midground=subject, background=location,
                screen_direction=local.get('screen_direction', ''),
                narration=local.get('narration', ''), required_roles=roles,
                visible_character_ids=roles, primary_subject_name=subject,
                visible_character_state=deepcopy(state), visible_character_state_source='beat_override',
                audience_knowledge_delta=local.get('audience_knowledge_delta', ''),
                causal_proof=local.get('visible_reaction', ''),
                anti_redundancy_key=obligation_id,
                static_first_frame_rule='開始時点の状態だけを描く',
            )
            cuts.append(cut)
            row['assigned_cut_ids'].append(selector)
            assignments.append(dict(cut_index=len(cuts), cut_selector=selector,
                obligation_id=obligation_id, obligation_ids=[obligation_id],
                cut_function=cut['cut_function'], source=cut['source'],
                target_beat=cut['target_beat'], visual_proof=start,
                event_assignment={'source_event_contract': {
                    'primary_event_beat_id': beat_id, 'source_event_beat_ids': [beat_id],
                    'source_event_ids': deepcopy(cut['source_event_ids']),
                    'source_transition_id': transition_id}},
                required_roles=roles, anti_redundancy_key=obligation_id))
    if not cuts:
        raise ValueError('scene has no visible authored beat')
    count = len(cuts)
    return {'cuts': cuts, 'coverage_plan': {
        'coverage_strategy': 'reverse_from_scene_event', 'source_schema_version': 'scene_event_v1',
        'min_cut_count': {'by_distinct_semantic_obligations': count,
                         'by_event_beats': sum(r['must_be_seen'] for r in inventory),
                         'selected': count, 'by_importance': 0, 'by_duration': 0},
        'minimum_cut_count': count, 'selected_cut_count': count,
        'event_beat_inventory': inventory, 'cut_assignments': assignments,
        'scene_obligations': [dict(obligation_id=c['obligation_id'], source=c['source'],
            evidence=c['visual_proof'], assigned_cut_ids=[a['cut_selector']])
            for c, a in zip(cuts, assignments)],
        'knowledge_assignments': [], 'unassigned_obligations': [],
        'overloaded_cuts': [], 'duplicate_meaning_risks': [],
        'cut_count_reason': 'authored visible beats and explicit ordered transitions',
    }}
