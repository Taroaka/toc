from toc.production_diagnostics import AuthoringValidationError
"""Authored, unpeopled boundary shots; never synthesize a plot or a subject."""
from copy import deepcopy
import re

from toc.image_prompt_compiler import compile_image_api_prompt_v2

POLICY = 'boundary_b_roll_v1'
NO_PEOPLE = '人物、顔、身体、手足、群衆、人影、シルエット、人物の反射・映り込みを一切入れない。'
TECHNIQUES = {'establishing', 'pillow', 'cutaway', 'insert', 'aftermath', 'match', 'environment_hold'}
FIELDS = ('source_event_beat_id', 'location', 'subject', 'first_frame', 'motion', 'end_state', 'foreground', 'background', 'light')


def validate_boundary(value, *, beat_ids):
    if not isinstance(value, dict) or not isinstance(value.get('reason'), str) or not value['reason'].strip():
        raise AuthoringValidationError('b_roll.boundary_reason_missing', owner_stage='p330')
    cuts = value.get('cuts')
    if not isinstance(cuts, list) or len(cuts) > 2:
        raise AuthoringValidationError('b_roll.cuts_invalid', owner_stage='p330')
    for cut in cuts:
        if not isinstance(cut, dict) or cut.get('technique') not in TECHNIQUES:
            raise AuthoringValidationError('b_roll.technique_invalid', owner_stage='p330')
        if any(not isinstance(cut.get(k), str) or not cut[k].strip() for k in FIELDS):
            raise AuthoringValidationError('b_roll.drawable_fields_missing', owner_stage='p330')
        for field in ('subject', 'first_frame', 'motion', 'end_state', 'foreground', 'background'):
            # Reject explicit actor instructions while allowing ordinary absence phrases.
            prose = re.sub(r'(?:人物|人影|人|顔|手足)(?:が|の)?(?:いない|ない|映らない|見えない)', '', cut[field])
            if re.search(r'(?:人物|主人公|登場人物|群衆|誰か|人影|人)(?:が|は|を)|(?:顔|手足|身体|後ろ姿)(?:が|を)', prose):
                raise AuthoringValidationError('b_roll.visible_person_instruction', owner_stage='p330')
        # This implementation appends a hold after the scene's main cuts.
        if not beat_ids or cut['source_event_beat_id'] != beat_ids[-1]:
            raise AuthoringValidationError('b_roll.source_must_be_final_event', owner_stage='p330')
    return cuts


def scene_boundary(profile, source_scene):
    visual = profile.get('visual_planning') or {}
    marker = (visual.get('visual_value_metadata') or {}).get('b_roll_policy')
    if marker is None:
        return []  # Preserve stored runs authored before this contract.
    if marker != POLICY:
        raise AuthoringValidationError('b_roll.policy_invalid', owner_stage='p330')
    rows = [r for r in visual['scene_visual_values'] if str(r['scene_selector']) == str(source_scene['scene_id'])]
    if len(rows) != 1:
        raise AuthoringValidationError('b_roll.scene_binding_invalid', owner_stage='p330')
    return validate_boundary(rows[0].get('boundary_b_roll'), beat_ids=[b['beat_id'] for b in source_scene['event_sequence']])


def materialize_b_roll(spec, *, selector, cut_id, location, duration, story_time, time_of_day, previous_selector):
    """Project a fully authored environmental hold into ordinary cut contracts."""
    loc = location['asset_id']
    if spec['location'] != location['name']:
        raise AuthoringValidationError('b_roll.location_binding_invalid', owner_stage='p330')
    beat = spec['source_event_beat_id']
    first, motion, end = spec['first_frame'], spec['motion'], spec['end_state']
    contract = {
        'schema_version': '3.0', 'cut_role': 'sub', 'cut_function': 'atmosphere',
        'visual_planning_contract': 'source_first_v2', 'b_roll_technique': spec['technique'], 'b_roll_policy': POLICY,
        'source_event_contract': {'primary_event_beat_id': beat, 'source_event_beat_ids': [beat],
            'event_beat_function': 'custom', 'event_time_position': 'consequence',
            'event_facts_to_preserve': [first], 'event_facts_not_to_invent': ['新しい事件や人物'],
            'allowed_reveal_info_ids': [], 'forbidden_reveal_info_ids': []},
        'viewer_contract': {'target_beat': first, 'screen_question': '場の余韻をどう受け止めるか',
            'dramatic_job': '既存の空間を保持する', 'audience_knowledge_delta': '既知の状態を保持',
            'visual_evidence': [first], 'required_roles': [], 'must_show': [spec['subject']], 'must_avoid': [NO_PEOPLE]},
        'cinematic_contract': {'camera_intent': spec['subject'], 'subject_priority': {'primary': spec['subject']},
            'screen_geography': {'foreground': spec['foreground'], 'midground': spec['subject'], 'background': spec['background']}},
        'first_frame_contract': {'imageable': True, 'source_event_beat_id': beat, 'event_time_position': 'consequence',
            'first_frame_brief': first, 'event_fact_visible_in_still': first, 'not_yet_happened_in_still': [],
            'visible_start_state': {'spatial_state': first}, 'must_avoid': [NO_PEOPLE]},
        'motion_contract': {'source_event_beat_id': beat, 'starts_from_first_frame': True,
            'motion_brief': motion, 'environment_motion': motion, 'start_from_visible_state': first,
            'end_state': end, 'allowed_new_reveal_elements': [], 'must_not_advance_to_event_beat_ids': [],
            'must_not_add': [NO_PEOPLE, '新しい事件や場所の変更']},
        'continuity_contract': {'location_ids': [loc], 'character_ids': [], 'object_ids': [],
            'start_state': {'spatial_state': first}, 'end_state': {'spatial_state': end}},
        'narration_contract': {'schema_version': 'narration_contract_v2', 'role': 'silent', 'target_function': 'silence',
            'source_event_beat_ids': [beat], 'allowed_info_ids': [], 'forbidden_info_ids': [],
            'silence_contract': {'reason': '空間の余韻を保持する', 'duration_seconds': duration}},
        'asset_dependency': {'character_ids_required': [], 'object_ids_required': [], 'location_ids_required': [loc]},
        'downstream_handoff': {'p600_image': [first, NO_PEOPLE], 'p800_video': [motion, NO_PEOPLE]},
        'intent_budget': {'primary_intent': '既存空間の余韻', 'assigned_obligation_ids': [selector]},
        'rhythm_contract': {'duration_seconds': duration, 'reason': '環境を受け止める間'},
        'cut_handoff': {
            'receives_from_previous': {'anchor_type': 'none', 'expected_previous_cut_selector': previous_selector, 'visible_or_audible_form': first},
            'delivers_to_next': {'anchor_type': 'terminal', 'expected_next_cut_selector': '', 'visible_or_audible_form': end}},
    }
    refs = [location['output']] if location.get('output') else []
    plan = {
        'schema_version': 'first_frame_visual_plan_v1', 'cut_role': 'sub',
        'source_grounding': {'source_event_beat_id': beat, 'character_ids': [], 'location_id': loc},
        'temporal_boundary': {'event_fact_visible_in_still': first, 'not_yet_happened_in_still': []},
        'subject_binding': {'primary_subject': {'name': spec['subject']}, 'secondary_subjects': [], 'background_subjects': []},
        'reference_binding': {'character_references': [], 'object_references': [],
            'location_references': [{'path': path, 'target_location_id': loc} for path in refs]},
        'spatial_composition': {'foreground': spec['foreground'], 'midground': spec['subject'], 'background': spec['background']},
        'scene_material_pack': {'light_source': spec['light']},
    }
    payload = compile_image_api_prompt_v2(first_frame_visual_plan=plan, location_ids=[loc], reference_images=refs,
        story_time=story_time, scene_time_of_day=time_of_day)
    silence = {'intentional': True, 'confirmed_by_human': False, 'source': POLICY,
        'kind': 'b_roll', 'reason': '人物なしの空間の余韻を保持する', 'duration_seconds': duration}
    narration = {'tool': 'silent', 'text': '', 'tts_text': '', 'authoring_status': 'silent',
        'silence_contract': silence, 'contract_ref': 'cut_contract.narration_contract',
        'output': f'assets/audio/{selector}.mp3'}
    script = {'cut_id': cut_id, 'selector': selector, 'target_duration_seconds': duration,
        'estimated_duration_seconds': duration, 'cut_blueprint': {'cut_role': 'sub', 'first_frame_brief': first, 'motion_brief': motion},
        'narration_authoring': {'status': 'silent'}, 'audio': {'narration': deepcopy(narration)},
        'cut_contract': deepcopy(contract)}
    cut = {'cut_id': cut_id, 'selector': selector, 'duration_seconds': duration, 'cut_contract': contract,
        'still_image_plan': {'mode': 'generate_still', 'generation_status': 'missing', 'prompt_source': 'image_generation.api_prompt_payload.prompt'},
        'image_generation': {'tool': 'codex_builtin_image', 'character_ids': [], 'object_ids': [], 'location_ids': [loc],
            'asset_type': 'scene_still', 'references': refs, 'reference_count': len(refs), 'first_frame_visual_plan': plan,
            'api_prompt_payload': payload, 'output': f'assets/scenes/{selector}.png', 'aspect_ratio': '16:9', 'image_size': '1K'},
        'video_generation': {'tool': 'kling_3_0_omni', 'duration_seconds': duration, 'first_frame': f'assets/scenes/{selector}.png',
            'motion_prompt': motion, 'output': f'assets/scenes/{selector}.mp4'},
        'audio': {'narration': narration}}
    return script, cut
