"""Read-only creative inputs for scene preparation, not execution snapshots."""
from copy import deepcopy

from toc.visual_planning_contract import decode_document


_IDENTITY_FIELDS = (
    'scene_id', 'selector', 'authored_cut_id', 'cut_id', 'shot_selector',
    'shot_id', 'event_id', 'beat_id', 'asset_id', 'character_id', 'object_id',
    'location_id', 'resource_id', 'id',
)


def _json_pointer_child(pointer, key):
    return pointer + '/' + str(key).replace('~', '~0').replace('/', '~1')


def _same_json_value(left, right):
    # Python considers True == 1 and False == 0; JSON values of those types
    # are distinct and must not be treated as an exact authoring match.
    return type(left) is type(right) and left == right


def _identity_match(source, candidates, used):
    """Find one corresponding list item using a stable authoring identifier."""
    if not isinstance(source, dict):
        return None
    for field in _IDENTITY_FIELDS:
        value = source.get(field)
        if value is None or isinstance(value, (dict, list)):
            continue
        matches = [
            index for index, candidate in enumerate(candidates)
            if index not in used and isinstance(candidate, dict)
            and field in candidate
            and _same_json_value(value, candidate[field])
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def _compact_exact_equivalences(source, current, source_path, current_path, equivalences):
    """Remove only exact duplicates and record where each value still lives."""
    if isinstance(source, dict) and isinstance(current, dict):
        result = {}
        for key, value in source.items():
            # Keep identity anchors inline even when they are repeated so the
            # sparse source view remains easy to read and cuts stay addressable.
            if key in _IDENTITY_FIELDS or key not in current:
                result[key] = deepcopy(value)
                continue
            source_child = _json_pointer_child(source_path, key)
            current_child = _json_pointer_child(current_path, key)
            if _same_json_value(value, current[key]):
                equivalences.append({
                    'source_json_pointer': source_child,
                    'context_json_pointer': current_child,
                })
                continue
            result[key] = _compact_exact_equivalences(
                value, current[key], source_child, current_child, equivalences,
            )
        return result

    if isinstance(source, list) and isinstance(current, list):
        used = set()
        result = []
        for source_index, value in enumerate(source):
            current_index = _identity_match(value, current, used)
            if current_index is None:
                # Without a stable identifier, positional comparison could
                # hide a value from a different cut or shot. Preserve it whole.
                result.append(deepcopy(value))
                continue
            used.add(current_index)
            result.append(_compact_exact_equivalences(
                value, current[current_index],
                _json_pointer_child(source_path, source_index),
                _json_pointer_child(current_path, current_index), equivalences,
            ))
        return result

    return deepcopy(source)


def _image_view(value, *, authored_plan):
    result = deepcopy(value)
    for key in ('api_prompt_payload', 'debug_prompt_source', 'candidates', 'generation'):
        result.pop(key, None)
    if authored_plan:
        # The complete initial/end views are already in the parent's shot_plan.
        # Keep references and IDs here so attachments remain identifiable.
        result.pop('first_frame_visual_plan', None)
    return result


def _video_view(value, *, authored_plan):
    result = deepcopy(value)
    for key in ('api_prompt_payload', 'video_prompt_ir', 'projection_trace',
                'prompt_compilation', 'debug_prompt_source', 'candidates', 'generation'):
        result.pop(key, None)
    frame = result.get('result_frame')
    if isinstance(frame, dict) and isinstance(frame.get('image_generation'), dict):
        frame['image_generation'] = _image_view(frame['image_generation'], authored_plan=authored_plan)
    return result


def scene_authoring_view(scene):
    """Keep original meaning, timing, narration and shot plans without copies."""
    result = deepcopy(scene)
    for key in ('scene_generation', 'scene_cut_coverage_plan', 'scene_acceptance_binding',
                'scene_acceptance_draft'):
        result.pop(key, None)
    for cut in result.get('cuts', []):
        authored_plan = bool(cut.get('shot_plan'))
        if isinstance(cut.get('image_generation'), dict):
            cut['image_generation'] = _image_view(cut['image_generation'], authored_plan=authored_plan)
        if isinstance(cut.get('video_generation'), dict):
            cut['video_generation'] = _video_view(cut['video_generation'], authored_plan=authored_plan)
        narration = (cut.get('audio') or {}).get('narration')
        if isinstance(narration, dict):
            narration.pop('candidates', None)
        for shot in cut.get('shots', []):
            if authored_plan:
                shot.pop('cut_contract', None)
            if isinstance(shot.get('image_generation'), dict):
                shot['image_generation'] = _image_view(shot['image_generation'], authored_plan=authored_plan)
            if isinstance(shot.get('video_generation'), dict):
                shot['video_generation'] = _video_view(shot['video_generation'], authored_plan=authored_plan)
    return result


def script_authoring_view(raw, scene_id):
    """Retain the selected scene and full-run language/user direction context."""
    document = decode_document(raw)
    scenes = [s for s in document.get('scenes', []) if str(s.get('scene_id')) == str(scene_id)]
    if len(scenes) != 1:
        raise ValueError('video preparation script scene not uniquely found: ' + str(scene_id))
    result = {key: deepcopy(document[key]) for key in (
        'schema_version', 'script_metadata', 'human_change_requests', 'asset_resolutions',
        'audio_story_plan', 'narration_spans') if key in document}
    result['scenes'] = [scene_authoring_view(scenes[0])]
    result['context_scope'] = 'selected script scene; full story and neighboring boundaries supplied separately'
    return result


def compact_script_scene_against_context(script_view, current_scene):
    """Reference exact repeated source fields from the separate current scene.

    The source scene remains a sparse, identity-preserving projection. Every
    omitted source value is listed as an exact JSON Pointer equivalence so the
    author can recover it from the current scene without guessing. Values that
    differ, or lack a stable list-item identity, remain in the source view.
    """
    result = deepcopy(script_view)
    scenes = result.get('scenes')
    if not isinstance(scenes, list) or len(scenes) != 1 or not isinstance(scenes[0], dict):
        return result
    source_scene = scenes[0]
    equivalences = []
    result['scenes'][0] = _compact_exact_equivalences(
        source_scene, current_scene, '/scenes/0', '/scene', equivalences,
    )
    result['selected_scene_equivalence_map'] = equivalences
    result['context_scope'] = (
        'The selected source-script scene is losslessly compacted against '
        'the separate context.scene. Each selected_scene_equivalence_map '
        'entry maps an omitted source_json_pointer to its exact-equal '
        'context_json_pointer; use that context value as the original script '
        'value. All unmapped source values remain verbatim, and scene/cut '
        'identity fields remain inline.'
    )
    return result


def review_source_context(context):
    """The reviewed scene carries protected fields; avoid two more scene copies."""
    result = deepcopy(context)
    result.pop('scene', None)
    result.pop('file_hashes', None)
    result.pop('prepared_image_hashes', None)
    script = (result.get('source_documents') or {}).get('script.md')
    if isinstance(script, dict):
        script.pop('scenes', None)
        script.pop('selected_scene_equivalence_map', None)
        script['context_scope'] = 'global script context; reviewed scene supplied separately'
    return result
