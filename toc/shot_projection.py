"""Shared still/video projection of authored shots, with parent audio intact."""
from copy import deepcopy
import hashlib
import json
import math
import re

from toc.image_prompt_compiler import compile_image_api_prompt_v2
from toc.shot_direction import normalize_shot_plan, parent_duration_seconds, SCHEMA


def _ids(parent, kind):
    contract = parent.get('cut_contract') or {}
    dependency = contract.get('asset_dependency') or {}
    return list(dependency.get(kind + '_ids_required') or
                (contract.get('continuity_contract') or {}).get(kind + '_ids') or
                (parent.get('image_generation') or {}).get(kind + '_ids') or [])


def _unique(values):
    return list(dict.fromkeys(values))


def project_cut_shots(parent_cut, plan, resources, *, story_time='', time_of_day=''):
    """Return a new manifest cut. No media/files/narration are written here."""
    parent = deepcopy(parent_cut)
    characters, objects, locations = (_ids(parent, k) for k in ('character', 'object', 'location'))
    duration = parent_duration_seconds(parent)
    plan = normalize_shot_plan(plan, character_ids=characters, object_ids=objects, duration_seconds=duration)
    revision = hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True,
                                        separators=(',', ':')).encode()).hexdigest()[:12]
    parent_contract = parent.get('cut_contract') or {}
    source_image = parent.get('image_generation') or {}
    source_video = parent.get('video_generation') or {}
    selector = parent.get('selector')
    if not isinstance(selector, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', selector):
        raise ValueError('shot_direction:parent_selector_required')
    names = {aid: entry.get('name') for group in ('characters', 'objects', 'locations')
             for aid, entry in resources.get(group, {}).items()}
    for kind, ids in (('characters', characters), ('objects', objects), ('locations', locations)):
        if any(not names.get(aid) or aid not in resources.get(kind, {}) for aid in ids):
            raise ValueError('shot_direction:unresolved_resource:' + kind)
    result_image = (source_video.get('result_frame') or {}).get('image_generation') or {}
    light = ((parent_contract.get('cinematic_contract') or {}).get('camera') or {}).get('light') or ''

    def identity(subject):
        aid, member = subject['entity_id'], subject['member_id']
        if member:
            entry = resources[subject['kind'] + 's'][aid]
            members = entry.get('members') or []
            row = next((m for m in members if isinstance(m, dict) and m.get('member_id') == member), None)
            if row is None:
                raise ValueError('shot_direction:member_reference_unresolved:' + aid + '/' + member)
            return str(row.get('name') or member)
        return names[aid]

    def state_image_at(changed):
        combined = deepcopy(source_image)
        combined_plan = combined.setdefault('first_frame_visual_plan', {})
        final_plan = result_image.get('first_frame_visual_plan') or {}
        bindings = combined_plan.setdefault('reference_binding', {})
        for kind in ('character', 'object', 'location'):
            key = kind + '_references'
            current = [r for r in bindings.get(key, []) if r.get('target_' + kind + '_id') not in changed]
            current.extend(deepcopy(r) for r in (final_plan.get('reference_binding') or {}).get(key, [])
                           if r.get('target_' + kind + '_id') in changed)
            bindings[key] = current
            combined[kind + '_variant_ids'] = _unique([*(source_image.get(kind + '_variant_ids') or []),
                                                       *(result_image.get(kind + '_variant_ids') or [])])
        gate = combined_plan.setdefault('character_state_gate', {})
        gate['character_states'] = [r for r in gate.get('character_states', []) if r.get('character_id') not in changed]
        gate['character_states'].extend(deepcopy(r) for r in (final_plan.get('character_state_gate') or {}).get('character_states', [])
                                        if r.get('character_id') in changed)
        return combined

    def image_for(view, output, *, changed, anchor=None, camera=None):
        if view.get('state_source') == 'result' and not changed:
            raise ValueError('shot_direction:result_state_used_before_transition')
        if view.get('state_source') == 'start' and any(s['entity_id'] in changed for s in view['subjects']):
            raise ValueError('shot_direction:start_state_reset_after_transition')
        state_image = state_image_at(changed)
        state_plan = state_image.get('first_frame_visual_plan') or {}
        source_bindings = state_plan.get('reference_binding') or {}
        old_states = (state_plan.get('character_state_gate') or {}).get('character_states') or []
        old_state_by_id = {r.get('character_id'): r for r in old_states if isinstance(r, dict)}
        visible = {k: _unique(s['entity_id'] for s in view['subjects'] if s['kind'] == k)
                   for k in ('character', 'object')}
        bindings, refs = {}, []
        for kind, ids in [('character', visible['character']), ('object', visible['object']), ('location', locations)]:
            rows = []
            for aid in ids:
                existing = [r for r in source_bindings.get(kind + '_references', [])
                            if isinstance(r, dict) and r.get('target_' + kind + '_id') == aid]
                paths = _unique([*resources[kind + 's'][aid].get('references', []),
                                 *(r.get('path') for r in existing if r.get('path'))])
                if not paths:
                    raise ValueError('shot_direction:identity_reference_missing:' + aid)
                for path in paths:
                    if not isinstance(path, str) or not path.startswith('assets/') or '..' in path.split('/') or any(c in path for c in '\r\n`\\'):
                        raise ValueError('shot_direction:unsafe_reference_path')
                    rows.append({'path': path, 'target_' + kind + '_id': aid,
                                 'target_' + kind + '_name': names[aid]})
                    refs.append(path)
            bindings[kind + '_references'] = rows
        if anchor:
            bindings['scene_references'] = [{'path': anchor, 'role': 'spatial_continuity_anchor'}]
            refs.append(anchor)
        visible_lines = [identity(s) + '：' + s['view'] +
                         ('。見える部分は' + '、'.join(s['visible_parts']) if s['visible_parts'] else '')
                         for s in view['subjects']]
        states = []
        for aid in visible['character']:
            row = old_state_by_id.get(aid)
            if row:
                states.append(deepcopy(row))
            elif (resources['characters'][aid].get('appearance_continuity') or {}).get('costume_state'):
                states.append({'character_id': aid, 'character_name': names[aid],
                               'appearance_continuity': deepcopy(resources['characters'][aid]['appearance_continuity'])})
        visual_plan = {
            'schema_version': 'first_frame_visual_plan_v1', 'cut_role': 'main' if visible['character'] else 'sub',
            'shot_direction_contract': SCHEMA,
            'source_grounding': {'character_ids': visible['character']},
            'temporal_boundary': {'event_fact_visible_in_still': view['description'], 'not_yet_happened_in_still': []},
            'subject_binding': {'primary_subject': {'name': view['description']}},
            'character_state_gate': {'pose': '\n'.join(visible_lines), 'character_states': states},
            'object_visibility_gate': {'objects': [{'object_id': aid, 'name': names[aid],
                'object_state': '\n'.join(s['view'] for s in view['subjects'] if s['entity_id'] == aid)} for aid in visible['object']]},
            'reference_binding': bindings,
            'spatial_composition': {'foreground': view['composition'], 'midground': view['description'],
                'background': '背景はこの画角に収まる範囲だけ。参照画像の全景を再現しない',
                'shot_size': view['framing'], 'focus_intent': view['focus'] or ''},
            'scene_material_pack': {'light_source': light},
            'source_preservation_constraints': [],
        }
        if camera and camera.get('angle'):
            visual_plan['spatial_composition']['camera_angle'] = camera['angle']
        if camera and camera.get('lens_mm') is not None:
            visual_plan['spatial_composition']['camera_angle'] = '。'.join(filter(None, [
                visual_plan['spatial_composition'].get('camera_angle'), f"焦点距離{camera['lens_mm']}mmの見え方"]))
        if visible_lines:
            visual_plan['source_preservation_constraints'] = ['この画で描く範囲：' + '。'.join(visible_lines),
                '参照は同一性と見える衣装の状態に使う。画角の外の顔・身体・道具を追加して全景に戻さない']
        if (source_image.get('first_frame_visual_plan') or {}).get('film_language'):
            visual_plan['film_language'] = deepcopy(source_image['first_frame_visual_plan']['film_language'])
        payload = compile_image_api_prompt_v2(first_frame_visual_plan=visual_plan,
            character_ids=visible['character'], object_ids=visible['object'], location_ids=locations,
            reference_images=_unique(refs), story_time=story_time, scene_time_of_day=time_of_day)
        from toc.asset_state_variants import state_variant_output_path
        variants = {kind + '_variant_ids': [variant for variant in state_image.get(kind + '_variant_ids', [])
            if any(state_variant_output_path(kind, aid, variant) in refs
                   for aid in (locations if kind == 'location' else visible[kind]))]
            for kind in ('character', 'object', 'location')}
        return {'tool': source_image.get('tool', 'codex_builtin_image'),
            'character_ids': visible['character'], 'object_ids': visible['object'], 'location_ids': locations,
            **variants,
            'asset_type': 'scene_still', 'references': _unique(refs), 'reference_count': len(_unique(refs)),
            'first_frame_visual_plan': visual_plan, 'api_prompt_payload': payload,
            'output': output, 'aspect_ratio': source_image.get('aspect_ratio', '16:9'),
            'image_size': source_image.get('image_size', '1K')}

    shots = []
    changed_entities, previous_end = set(), None
    for shot in plan['shots']:
        sid = selector + '_shot' + shot['shot_id']
        output_stem = sid + '_' + revision
        initial_ids = {s['entity_id'] for s in shot['initial_view']['subjects']}
        end_ids = {s['entity_id'] for s in (shot['end_view'] or {}).get('subjects', [])}
        revealed = {aid for event in shot['events'] if event['kind'] in ('enter_frame', 'camera_reveal', 'transform') for aid in event['entity_ids']}
        transitions = {aid for e in shot['events'] if e['kind'] == 'transform' for aid in e['entity_ids']}
        if transitions and (not result_image or not shot['end_view'] or not (source_video.get('result_state_reference') or {}).get('required')):
            raise ValueError('shot_direction:source_bound_transformation_result_required')
        if transitions:
            from toc.asset_state_variants import normalize_state_variant_bindings, state_variant_output_path
            result_refs = normalize_state_variant_bindings(source_video['result_state_reference'], strict=True)
            source_beats = set((parent_contract.get('source_event_contract') or {}).get('source_event_beat_ids', []))
            for aid in transitions:
                kind = 'character' if aid in characters else 'object'
                matching = [r for r in result_refs if r.get('asset_id') == aid and r.get('entity_type') == kind]
                if len(matching) != 1:
                    raise ValueError('shot_direction:transformed_entity_result_reference_missing_or_ambiguous:' + aid)
                ref = matching[0]
                consumers = ref.get('consumer_source_event_beat_ids') or []
                if not ref.get('transition_id') or not consumers or not set(consumers) <= source_beats:
                    raise ValueError('shot_direction:transformation_source_binding_invalid:' + aid)
                path = state_variant_output_path(kind, aid, ref.get('variant_id', ''))
                bound = (result_image.get('first_frame_visual_plan') or {}).get('reference_binding') or {}
                if (path not in result_image.get('references', [])
                        or ref.get('variant_id') not in result_image.get(kind + '_variant_ids', [])
                        or not any(r.get('path') == path and r.get('target_' + kind + '_id') == aid
                                   for r in bound.get(kind + '_references', []))):
                    raise ValueError('shot_direction:transformed_entity_result_reference_unbound:' + aid)
        if shot['initial_view'].get('state_source') == 'previous_end' and previous_end is None:
            raise ValueError('shot_direction:previous_end_reference_missing')
        next_state = changed_entities | transitions
        if revealed - initial_ids - end_ids:
            raise ValueError('shot_direction:later_identity_reference_unencodable:' + ','.join(sorted(revealed - initial_ids - end_ids)))
        if shot['duration_seconds'] > 15:
            raise ValueError('shot_direction:split_shot_required_for_provider_duration')
        image = image_for(shot['initial_view'], f'assets/scenes/{output_stem}.png', changed=changed_entities,
                          anchor=previous_end, camera=shot['camera'])
        contract = deepcopy(parent_contract)
        participants = initial_ids | end_ids | {aid for e in shot['events'] for aid in e['entity_ids']}
        contract['cut_role'] = 'main'  # Editorial role does not forbid a hand/foot/partial person.
        contract['editorial_role'] = parent_contract.get('cut_role', 'main')
        contract['shot_direction'] = {'schema_version': SCHEMA, 'shot': deepcopy(shot), 'parent_selector': selector}
        contract['asset_dependency'] = {'character_ids_required': [i for i in characters if i in participants],
                                      'object_ids_required': [i for i in objects if i in participants],
                                      'location_ids_required': locations}
        visible_brief = shot['initial_view']['description']
        contract.setdefault('first_frame_contract', {}).update(first_frame_brief=visible_brief,
            event_fact_visible_in_still=visible_brief, must_include=[visible_brief],
            visible_start_state={'spatial_state': visible_brief})
        lines = [shot['motion']]
        for perf in shot['performance']:
            subject = identity({'entity_id': perf['actor_id'], 'member_id': perf['member_id'], 'kind': 'character'})
            target = '（相手：' + names[perf['target_id']] + '）' if perf['target_id'] else ''
            lines.append(subject + target + '：' + (perf['trigger'] + '。' if perf['trigger'] else '') + perf['behavior'])
        for event in shot['events']:
            lines.append('、'.join(names[i] for i in event['entity_ids']) + '：' +
                         (event['trigger'] + '。' if event['trigger'] else '') + event['description'])
        motion = '\n'.join(lines)
        contract.setdefault('motion_contract', {}).update(motion_brief=motion, subject_motion=motion,
            camera_motion=shot['camera']['movement'], start_from_visible_state=visible_brief,
            end_state=shot['end_state'], end_frame_brief=shot['end_state'],
            allowed_new_reveal_elements=[names[i] for i in sorted(revealed - initial_ids)])
        # Future event prose is validation context, not provider instructions.
        source_contract = contract.get('source_event_contract') or {}
        future_facts = {row.get('what_happens') for row in source_contract.get('future_event_boundaries', []) if isinstance(row, dict)}
        contract['motion_contract']['must_not_add'] = [line for line in contract['motion_contract'].get('must_not_add', [])
                                                      if line not in future_facts]
        contract['first_frame_contract']['not_yet_happened_in_still'] = []
        camera = {'framing': shot['initial_view']['framing'], 'composition': shot['initial_view']['composition'],
                  'focus': shot['initial_view']['focus'] or '', 'movement': shot['camera']['movement'], 'light': light}
        cinema = contract.setdefault('cinematic_contract', {})
        cinema.update(camera=camera, camera_intent=shot['intent'])
        execution = deepcopy(cinema.get('execution') or {})
        for key in ('performance', 'staging', 'geometry', 'cast_context'):
            execution.pop(key, None)
        contexts = [names[p['actor_id']] + '：' + '、'.join(x for x in (p['objective'], p['emotion']) if x)
                    for p in shot['performance'] if p['objective'] or p['emotion']]
        execution.update(schema_version='cinematic_execution_v1',
            focus={'initial': shot['initial_view']['focus'] or '', 'change': shot['camera']['focus_change'] or ''},
            performance={'action': '', 'observable_reaction': '\n'.join(contexts), 'timing': ''})
        if execution.get('film_language', {}).get('fields'):
            execution['film_language']['fields']['camera'] = shot['camera']['movement']
        cinema['execution'] = execution
        contract.setdefault('viewer_contract', {}).update(target_beat=shot['intent'], dramatic_job=shot['intent'],
            required_roles=image['character_ids'], must_show=[visible_brief], done_when=[shot['end_state']])
        generation = {'tool': 'higgsfield', 'model': 'kling-video/v3.0/std/image-to-video',
            'duration_seconds': max(3, math.ceil(shot['duration_seconds'])), 'first_frame': image['output'],
            'motion_prompt': motion, 'output': f'assets/scenes/{output_stem}.mp4',
            'native_audio': {'mode': 'off', 'sound_events': [], 'dialogue': []}}
        if shot['end_view']:
            end_image = image_for(shot['end_view'], f'assets/scenes/{output_stem}_result.png', changed=next_state,
                                  anchor=image['output'], camera=shot['camera'])
            generation.update(last_frame=end_image['output'], result_frame={'output': end_image['output'], 'image_generation': end_image})
            if shot['end_view'].get('state_source') != 'start':
                from toc.asset_state_variants import normalize_state_variant_bindings
                state_refs = [r for r in normalize_state_variant_bindings(source_video.get('result_state_reference') or {})
                              if r.get('asset_id') in next_state and (r.get('asset_id') in end_ids or r.get('entity_type') == 'location')]
                if state_refs:
                    generation['result_state_reference'] = {'required': True, 'state_variant_refs': deepcopy(state_refs)}
        shots.append({'shot_id': shot['shot_id'], 'selector': sid, 'parent_selector': selector,
            'start_seconds': shot['start_seconds'], 'duration_seconds': shot['duration_seconds'],
            'cut_contract': contract, 'image_generation': image, 'video_generation': generation})
        changed_entities = next_state
        previous_end = generation.get('last_frame')
    parent['shot_plan'] = plan
    parent['shots'] = shots
    parent['image_generation'] = deepcopy(shots[0]['image_generation'])
    return parent
