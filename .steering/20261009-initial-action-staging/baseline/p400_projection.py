"""Project an authored cinematic cut list, without choosing shots or rewriting prose."""
from copy import deepcopy
import json

from toc.image_prompt_compiler import compile_image_api_prompt_v2
from toc.p400_authoring import CONTRACT
from toc.production_diagnostics import AuthoringValidationError
from toc.cut_context_packet import materialize_cut_context_packet
from toc.cinematic_language import execution_from_cut

NO_PEOPLE = '人物、顔、身体、手足、影、人物の反射を画面に入れない'


def _prose(value):
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [line for item in value for line in _prose(item)]
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=False)] if value else []
    return []


def project_scene(direction, *, source_scene, scene_id, resources, scene_intent, scene_event,
                  scene_generation, acceptance_draft, acceptance_binding, previous_selector='', next_selector='', story_time='', film_language=None):
    script_cuts, manifest_cuts = [], []
    beats = {b['beat_id']: b for b in scene_event['event_sequence']}
    all_ids = list(beats)
    preservation = source_scene.get('preservation') or {}
    reveal = source_scene.get('reveal_contract') or {}
    preserve = _prose(preservation.get('must_not_change'))
    forbidden = list(dict.fromkeys(_prose(preservation.get('must_not_show'))
        + _prose(reveal.get('must_not_show')) + _prose(scene_event.get('forbidden_event_changes'))))
    inventory = {bid: {'beat_id': bid, 'beat_function': b.get('beat_function', 'custom'),
        'what_happens': b['what_happens'], 'must_be_seen': b.get('must_be_seen', True),
        'assigned_cut_ids': [], 'required_visual_evidence': deepcopy(b.get('required_visual_evidence', []))}
        for bid, b in beats.items()}
    assignments = []
    total = len(direction['cuts'])
    for index, authored in enumerate(direction['cuts'], 1):
        cut = deepcopy(authored)
        selector = f'scene{scene_id}_cut{index:02d}'
        duration, refs, primary = cut['duration_seconds'], cut['source_beat_ids'], cut['primary_beat_id']
        location = resources['locations'][cut['location_id']]
        chars, objects = cut['character_ids'], cut['object_ids']
        first, motion, end, camera = cut['first_frame_brief'], cut['motion_brief'], cut['motion_end_state'], cut['camera']
        visible_facts = [f'{key}: {cut["start_state_facts"][key]}' for key in cut['visible_state_keys']]
        references = list(dict.fromkeys(path for group, ids in (
            ('characters', chars), ('objects', objects), ('locations', [cut['location_id']]))
            for aid in ids for path in resources[group][aid]['references']))
        rank = max(all_ids.index(bid) for bid in refs)
        future = all_ids[rank + 1:]
        future_facts = [beats[bid]['what_happens'] for bid in future]
        evidence = list(dict.fromkeys(x for bid in refs for x in beats[bid].get('required_visual_evidence', [])))
        source_events = list(dict.fromkeys(x for bid in refs for x in beats[bid].get('source_event_ids', [])))
        must_avoid = ['画面内テキスト', '字幕', 'ロゴ', *forbidden] + ([NO_PEOPLE] if cut['cut_role'] == 'sub' else [])
        before = cut['continuity']['previous_end_state']
        previous = f'scene{scene_id}_cut{index-1:02d}' if index > 1 else previous_selector
        following = f'scene{scene_id}_cut{index+1:02d}' if index < total else next_selector
        contract = {
            'schema_version': '3.0', 'visual_planning_contract': 'source_first_v2',
            'cinematic_direction_contract': CONTRACT, 'authored_cut_id': cut['cut_id'],
            'cut_role': cut['cut_role'], 'cut_function': cut['cut_function'],
            'source_event_contract': {'primary_event_beat_id': primary, 'source_event_beat_ids': refs,
                'source_event_ids': source_events, 'event_beat_function': beats[primary].get('beat_function', 'custom'),
                'event_time_position': cut['event_time_position'], 'source_event_summary': beats[primary]['what_happens'],
                'source_concrete_events': [deepcopy(beats[b].get('concrete_event', {})) for b in refs],
                'event_facts_to_preserve': [beats[b]['what_happens'] for b in refs],
                'event_facts_not_to_invent': forbidden, 'source_preservation': deepcopy(preservation),
                'source_reveal_contract': deepcopy(reveal), 'future_event_boundaries': [{'beat_id': bid, 'what_happens': beats[bid]['what_happens']} for bid in future],
                'allowed_reveal_info_ids': cut['allowed_reveal_info_ids'], 'forbidden_reveal_info_ids': future},
            'viewer_contract': {'target_beat': cut['purpose'], 'screen_question': cut.get('screen_question', ''),
                'dramatic_job': cut['purpose'], 'visual_evidence': evidence, 'required_roles': chars,
                'must_show': [first], 'must_avoid': must_avoid, 'done_when': [end],
                'audience_knowledge_boundary': {'scene_start': deepcopy(source_scene.get('start_state', {})),
                    'scene_end': deepcopy(source_scene.get('end_state', {}))}},
            'cinematic_contract': {'camera_intent': cut['purpose'], 'subject_priority': {'primary': cut['primary_subject']},
                'screen_geography': {'foreground': camera['composition'], 'midground': first, 'background': location['name']},
                'camera': camera},
            'first_frame_contract': {'imageable': True, 'source_event_beat_id': primary,
                'event_time_position': cut['event_time_position'], 'first_frame_brief': first, 'event_fact_visible_in_still': first,
                'not_yet_happened_in_still': [*future_facts, *forbidden], 'visible_start_state': {'spatial_state': first, 'state_id': cut['start_state_id'],
                    'facts': deepcopy(cut['start_state_facts']), 'visible_fact_keys': cut['visible_state_keys']},
                'must_include': [first], 'must_avoid': must_avoid},
            'motion_contract': {'source_event_beat_id': primary, 'starts_from_first_frame': True,
                'motion_brief': motion, 'subject_motion': motion, 'camera_motion': camera['movement'],
                'start_from_visible_state': first, 'end_state': end, 'end_frame_brief': end,
                'allowed_new_reveal_elements': cut['allowed_new_reveal_elements'],
                'must_not_advance_to_event_beat_ids': future, 'must_not_add': [*must_avoid, *future_facts], 'must_preserve': preserve},
            'continuity_contract': {'location_ids': [cut['location_id']], 'character_ids': chars, 'object_ids': objects,
                'start_state': {'state_id': cut['start_state_id'], 'spatial_state': first, 'facts': deepcopy(cut['start_state_facts'])},
                'end_state': {'state_id': cut['end_state_id'], 'spatial_state': end, 'facts': deepcopy(cut['end_state_facts'])}, 'must_preserve': preserve,
                'previous_end_state': before, 'connection': cut['continuity']['connection'],
                'mode': cut['continuity']['mode'], 'ellipsis_reason': cut['continuity'].get('ellipsis_reason', ''),
                'carry_forward_to_next_cut': [end]},
            'cut_state_progression': {'policy_version': 'cut_state_progression_v1',
                'progression_mode': cut['progression_mode'], 'state_after_previous_cut': before,
                'state_visible_in_first_frame': first, 'must_not_advance_beyond': end},
            'cut_handoff': {'receives_from_previous': {'anchor_type': 'none' if not previous else 'state',
                'expected_previous_cut_selector': previous, 'visible_or_audible_form': cut['continuity']['connection'],
                'mode': cut['continuity']['mode'], 'ellipsis_reason': cut['continuity'].get('ellipsis_reason', '')},
                'delivers_to_next': {'anchor_type': 'terminal' if not following else 'state',
                'expected_next_cut_selector': following, 'visible_or_audible_form': end}},
            'narration_contract': {'schema_version': 'narration_contract_v2', 'role': cut['narration_role'],
                'target_function': cut['audio_intent'], 'source_event_beat_ids': refs,
                'allowed_info_ids': cut['allowed_reveal_info_ids'], 'forbidden_info_ids': future,
                'text': cut['narration'], 'tts_text': cut['narration'], 'silence_reason': cut.get('silence_reason', '')},
            'rhythm_contract': {'expected_duration_seconds': duration, 'duration_reason': cut['duration_reason'],
                'cut_out_reason': cut['edit_reason'], 'audio_visual_sync_point': cut['audio_intent']},
            'asset_dependency': {'character_ids_required': chars, 'object_ids_required': objects,
                'location_ids_required': [cut['location_id']]},
            'intent_budget': {'primary_intent': cut['purpose'], 'assigned_obligation_ids': [cut['cut_id']]},
            'downstream_handoff': {'p600_image': {'prompt_requirements': [first, camera['framing'], camera['composition'], camera['light'], camera['focus']]},
                'p700_narration': {'narration_requirements': [cut['audio_intent']], 'role': cut['narration_role']},
                'p800_video': {'motion_requirements': [motion, camera['movement']], 'last_frame_or_end_state': end}},
        }
        plan = {'schema_version': 'first_frame_visual_plan_v1', 'cut_role': cut['cut_role'],
            'source_grounding': {'source_event_beat_id': primary, 'character_ids': chars, 'location_id': cut['location_id']},
            'temporal_boundary': {'event_fact_visible_in_still': first, 'not_yet_happened_in_still': [*future_facts, *forbidden]},
            'subject_binding': {'primary_subject': {'name': cut['primary_subject']},
                'secondary_subjects': [{'id': aid, 'name': resources['characters'][aid]['name']} for aid in chars], 'background_subjects': []},
            'character_state_gate': {'pose': first, 'character_states': [
                {'character_id': aid, 'character_name': resources['characters'][aid]['name'],
                 'appearance_continuity': deepcopy(resources['characters'][aid]['appearance_continuity'])}
                for aid in chars if resources['characters'][aid].get('appearance_continuity', {}).get('costume_state')]} if chars else {},
            'object_visibility_gate': {'objects': [{'object_id': aid, 'name': resources['objects'][aid]['name'],
                'object_state': first} for aid in objects]},
            'reference_binding': {f'{kind}_references': [
                {'path': path, f'target_{kind}_id': aid, f'target_{kind}_name': resources[group][aid]['name']} for aid in ids for path in resources[group][aid]['references']]
                for kind, group, ids in [('character', 'characters', chars), ('object', 'objects', objects), ('location', 'locations', [cut['location_id']])]},
            'spatial_composition': {'foreground': camera['composition'], 'midground': first, 'background': location['name'],
                'shot_size': camera['framing'], 'focus_intent': camera['focus']},
            'scene_material_pack': {'light_source': camera['light']},
            'source_preservation_constraints': preserve, 'authored_visible_state_facts': visible_facts,
            'scene_state_progression': {'progression_mode': cut['progression_mode']},
        }
        execution = None
        if film_language or 'execution' in cut:
            execution = execution_from_cut(cut, film=film_language,
                scene_overrides=direction.get('film_language_overrides'), resources=resources,
                source_beats=scene_event.get('event_sequence', []))
            contract['cinematic_contract']['execution'] = execution
            plan['film_language'] = deepcopy(execution.get('film_language', {}))
            if execution.get('geometry'):
                plan['geometry'] = deepcopy(execution['geometry'])
            if execution['focus'].get('initial'):
                plan['spatial_composition']['focus_intent'] = execution['focus']['initial']
        try:
            payload = compile_image_api_prompt_v2(first_frame_visual_plan=plan, character_ids=chars, object_ids=objects,
                location_ids=[cut['location_id']], reference_images=references, story_time=story_time,
                scene_time_of_day=source_scene.get('time_of_day', ''))
        except AuthoringValidationError as exc:
            raise AuthoringValidationError('cinematic_cut:' + json.dumps({
                'scene_id': direction['scene_id'], 'cut_index': index-1, 'reason': str(exc)},
                ensure_ascii=False), target=selector) from exc

        narration = {'tool': 'elevenlabs' if cut['narration'].strip() else 'silent', 'text': cut['narration'],
            'tts_text': cut['narration'], 'output': f'assets/audio/{selector}.mp3'}
        if not cut['narration'].strip():
            silence = {'intentional': True, 'confirmed_by_human': False, 'source': CONTRACT,
                'reason': cut['silence_reason'], 'duration_seconds': duration}
            narration.update(authoring_status='silent', silence_contract=silence)
            contract['narration_contract']['silence_contract'] = deepcopy(silence)
        base = {'cut_id': f'{index:02d}', 'selector': selector, 'authored_cut_id': cut['cut_id'],
                'cut_contract': contract, 'audio': {'narration': narration}}
        script_cut = deepcopy(base)
        script_cut.update(target_duration_seconds=duration, estimated_duration_seconds=duration,
            narration_authoring={'status': 'draft' if cut['narration'].strip() else 'silent'},
            cut_blueprint={'cut_role': cut['cut_role'], 'cut_function': cut['cut_function'],
                'target_beat': cut['purpose'], 'first_frame_brief': first, 'motion_brief': motion,
                'motion_end_state': end, 'duration_intent': cut['duration_reason'], 'camera': camera,
                'source_event_contract': deepcopy(contract['source_event_contract'])})
        manifest_cut = deepcopy(base)
        manifest_cut.update(duration_seconds=duration, target_duration_seconds=duration,
            still_image_plan={'mode': 'generate_still', 'generation_status': 'missing', 'prompt_source': 'image_generation.api_prompt_payload.prompt'},
            image_generation={'tool': 'codex_builtin_image', 'character_ids': chars, 'object_ids': objects,
                'location_ids': [cut['location_id']], 'asset_type': 'scene_still', 'references': references,
                'reference_count': len(references), 'first_frame_visual_plan': plan, 'api_prompt_payload': payload,
                'output': f'assets/scenes/{selector}.png', 'aspect_ratio': '16:9', 'image_size': '1K'},
            video_generation={'tool': 'kling_3_0_omni', 'duration_seconds': duration,
                'first_frame': f'assets/scenes/{selector}.png', 'motion_prompt': motion, 'output': f'assets/scenes/{selector}.mp4'})
        if execution:
            native = deepcopy(execution['native_audio'])
            manifest_cut['video_generation']['native_audio'] = native
            if native['mode'] != 'off':
                manifest_cut['video_generation']['tool'] = 'higgsfield'
        script_cuts.append(script_cut); manifest_cuts.append(manifest_cut)
        for bid in refs:
            inventory[bid]['assigned_cut_ids'].append(selector)
        assignments.append({'cut_selector': selector, 'obligation_id': cut['cut_id'], 'cut_function': cut['cut_function'],
            'source': 'cinematic_direction', 'event_assignment': {'source_event_contract': deepcopy(contract['source_event_contract'])}})
    count = len(script_cuts)
    common = {'scene_id': scene_id, 'source_story_scene_id': source_scene['scene_id'],
        'canonical_scene_index': source_scene.get('canonical_scene_index'),
        'time_of_day': source_scene.get('time_of_day'), 'time_of_day_visual_basis': source_scene.get('time_of_day_visual_basis'),
        'research_refs': deepcopy(source_scene.get('research_refs', [])),
        'target_duration_seconds': source_scene['target_duration_seconds'],
        'estimated_duration_seconds': sum(c['duration_seconds'] for c in direction['cuts']),
        'scene_intent': deepcopy(scene_intent), 'scene_event': deepcopy(scene_event),
        'scene_generation': deepcopy(scene_generation), 'cinematic_direction': deepcopy(direction),
        'scene_cut_coverage_plan': {'coverage_strategy': 'authored_cinematic_direction',
            'min_cut_count': {'selected': count}, 'selected_cut_count': count, 'minimum_cut_count': count,
            'event_beat_inventory': list(inventory.values()), 'cut_assignments': assignments,
            'cut_count_reason': direction['direction']},
        'scene_state_progression_plan': {'progression_mode': ('suspended_moment' if all(c['progression_mode'] == 'suspended_moment' for c in direction['cuts']) else 'sequential_state_progression'),
            'cut_progression_map': [deepcopy(c['cut_contract']['cut_state_progression']) for c in script_cuts]},
        'handoff_to_next_scene': direction['exit_connection']}
    script_scene = {**deepcopy(common), 'scene_acceptance_draft': deepcopy(acceptance_draft), 'cuts': script_cuts}
    manifest_scene = {**deepcopy(common), 'scene_acceptance_binding': deepcopy(acceptance_binding), 'cuts': manifest_cuts}
    manifest_scene['duration_seconds'] = common['estimated_duration_seconds']
    for scene in (script_scene, manifest_scene):
        for index, cut in enumerate(scene['cuts']):
            materialize_cut_context_packet(scene, cut,
                previous_cut=scene['cuts'][index - 1] if index else None,
                next_cut=scene['cuts'][index + 1] if index + 1 < count else None)
    return script_scene, manifest_scene
