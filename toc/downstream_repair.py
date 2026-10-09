"""Stage-local diagnostics and bounded patches for downstream authoring.

The shared decoder and RepairSession remain owned by the common/p200 pipeline.
No fallback here can replay a creative prompt or replace an entire document.
"""
from copy import deepcopy
import json
import hashlib
import re

from toc.json_syntax_repair import decode_json_object_with_repair
from toc.production_repair import digest, RepairExhausted
from toc.visual_planning_contract import _pointer, story_scenes


class SyntaxRepairExhausted(RepairExhausted):
    """Syntax-only edits exhausted their durable budget; authoring is not retried."""


class UnscopedRepairError(RuntimeError):
    """A validator finding needs a precise adapter before automatic editing."""


def _escape(value):
    return str(value).replace('~', '~0').replace('/', '~1')


def _valid(value, schema):
    kind = schema.get('type')
    if kind == 'string' and not isinstance(value, str): return False
    if kind == 'object' and not isinstance(value, dict): return False
    if kind == 'array' and not isinstance(value, list): return False
    if kind == 'integer' and (type(value) is not int): return False
    if 'enum' in schema and value not in schema['enum']: return False
    if isinstance(value, str) and schema.get('minLength', 0) and not value.strip(): return False
    if type(value) is int and not schema.get('minimum', value) <= value <= schema.get('maximum', value): return False
    if isinstance(value, list):
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', len(value)): return False
        if 'items' in schema and not all(_valid(v, schema['items']) for v in value): return False
    return True


TEXT = {'type': 'string', 'minLength': 1}
STRINGS = {'type': 'array', 'items': TEXT}


class Diagnostics:
    def __init__(self, document):
        self.document, self.items = document, []

    def add(self, path, expected, *, code='field_invalid', candidates=(), kind='field'):
        try:
            value, missing = _pointer(self.document, path), False
        except (KeyError, IndexError):
            value, missing = None, True
        if any(d['path'] == path for d in self.items): return
        self.items.append({'path': path, 'current_value': deepcopy(value), 'missing': missing,
            'expected': expected, 'reference_candidates': deepcopy(list(candidates)), 'code': code, 'kind': kind})

    def check(self, path, schema, candidates=()):
        try:
            value = _pointer(self.document, path)
        except (KeyError, IndexError):
            self.add(path, schema, candidates=candidates, code='required'); return False
        if not _valid(value, schema):
            # Only the invalid array element may change when the container is sound.
            outer = {k: v for k, v in schema.items() if k != 'items'}
            if isinstance(value, list) and _valid(value, outer) and 'items' in schema:
                for i in range(len(value)):
                    self.check(f'{path}/{i}', schema['items'], candidates)
            else:
                self.add(path, schema, candidates=candidates)
            return False
        return True

    def refs(self, path, records, *, many=False, nonempty=False, removable=False):
        candidates = [{**(record if isinstance(record, dict) else {'meaning': record}), 'id': key}
                      for key, record in records.items()]
        schema = {'type': 'string', 'enum': list(records)}
        if many:
            schema = {'type': 'array', 'items': schema, 'minItems': int(nonempty)}
        valid = self.check(path, schema, candidates)
        if many and removable:
            for issue in self.items:
                if re.fullmatch(re.escape(path)+r'/[0-9]+', issue['path']):
                    issue['allow_remove'] = True
                    issue['minimum_remaining_items'] = int(nonempty)
        return valid


def visual_diagnostics(doc, story, research):
    from toc.b_roll import FIELDS, TECHNIQUES, validate_boundary
    from toc.production_diagnostics import AuthoringValidationError
    d = Diagnostics(doc)
    source = story_scenes(story)
    rows = doc.get('scene_visual_values')
    if not isinstance(rows, list):
        d.add('/scene_visual_values', {'type': 'array'}, code='visual_value.scenes_invalid')
        return d.items
    # Missing rows can be appended individually without re-emitting healthy rows.
    if len(rows) > len(source):
        raise UnscopedRepairError('visual_value: extra scene rows require explicit identity resolution')
    for i, scene in enumerate(source):
        p = f'/scene_visual_values/{i}'
        if i >= len(rows):
            d.add(p, {'type': 'object'}, code='visual_value.scene_coverage_or_order')
            continue
        if not d.check(p, {'type': 'object'}): continue
        selector = rows[i].get('scene_selector')
        if selector != scene['scene_id'] and selector in [s['scene_id'] for s in source]:
            raise UnscopedRepairError('visual_value scene order/duplicate identity requires a scoped reorder')
        d.refs(p+'/scene_selector', {str(scene['scene_id']): scene})
        d.check(p+'/notes', STRINGS)
        if not d.check(p+'/boundary_b_roll', {'type': 'object'}): continue
        boundary = rows[i]['boundary_b_roll']
        d.check(p+'/boundary_b_roll/reason', TEXT)
        if not d.check(p+'/boundary_b_roll/cuts', {'type': 'array', 'maxItems': 2}): continue
        for j, cut in enumerate(boundary['cuts']):
            cp = f'{p}/boundary_b_roll/cuts/{j}'
            if not d.check(cp, {'type': 'object'}): continue
            d.check(cp+'/technique', {'type': 'string', 'enum': sorted(TECHNIQUES)})
            for field in FIELDS: d.check(cp+'/'+field, TEXT)
            beats = scene.get('event_sequence', [])
            if beats: d.refs(cp+'/source_event_beat_id', {beats[-1]['beat_id']: beats[-1]})
            location = scene.get('location') or {}
            name = ((location.get('sequence') or [location.get('name')])[-1]
                    if isinstance(location, dict) else location)
            if name: d.refs(cp+'/location', {name: {'name': name}})
            if not any(x['path'].startswith(cp+'/') for x in d.items):
                try:
                    validate_boundary({'reason': 'check', 'cuts': [cut]}, beat_ids=[b['beat_id'] for b in beats])
                except AuthoringValidationError as exc:
                    if 'visible_person_instruction' in str(exc):
                        d.add(cp, {'type': 'object'}, code=str(exc), kind='semantic')
                    else:
                        raise UnscopedRepairError(str(exc)) from exc
    if 'global_visual_identity' in doc and d.check('/global_visual_identity', {'type': 'object'}):
        d.check('/global_visual_identity/notes', STRINGS)
    if 'continuity_notes' in doc and d.check('/continuity_notes', {'type': 'array'}):
        for i, item in enumerate(doc['continuity_notes']):
            p = f'/continuity_notes/{i}'
            if not d.check(p, {'type': 'object'}): continue
            d.check(p+'/note', TEXT)
            d.refs(p+'/scene_selectors', {str(s['scene_id']): s for s in source}, many=True, nonempty=True)
            if not d.check(p+'/source_refs', {'type': 'array', 'minItems': 1}): continue
            for j, ref in enumerate(item['source_refs']):
                rp = f'{p}/source_refs/{j}'
                if not d.check(rp, {'type': 'object'}): continue
                if not d.refs(rp+'/source', {'story': {}, 'research': {}}): continue
                if not d.check(rp+'/pointer', TEXT): continue
                root = {'story': story, 'research': research}[ref['source']]
                try: _pointer(root, ref['pointer'])
                except (KeyError, IndexError, ValueError, TypeError):
                    records = pointer_records(root)
                    d.refs(rp+'/pointer', records)
    if 'visual_value_metadata' in doc and d.check('/visual_value_metadata', {'type': 'object'}):
        if 'visual_planning_contract' in doc['visual_value_metadata']:
            from toc.visual_planning_contract import VISUAL_PLANNING_CONTRACT
            d.refs('/visual_value_metadata/visual_planning_contract', {VISUAL_PLANNING_CONTRACT: {'meaning': 'current contract'}})
    return d.items


def pointer_records(document, path=''):
    records = {}
    if path: records[path] = {'value': document}
    if isinstance(document, dict):
        for key, value in document.items(): records.update(pointer_records(value, path+'/'+_escape(key)))
    elif isinstance(document, list):
        for i, value in enumerate(document): records.update(pointer_records(value, path+'/'+str(i)))
    return records


def direction_diagnostics(row, source, resources, previous=None):
    from toc.p400_authoring import EVENT_POSITIONS, _reveal_ids
    d = Diagnostics(row)
    d.refs('/scene_id', {str(source['scene_id']): source})
    for key in ('direction', 'visual_plan_application', 'entry_connection', 'exit_connection'):
        d.check('/'+key, TEXT)
    d.check('/asset_requests', {'type': 'array'})
    if not d.check('/cuts', {'type': 'array', 'minItems': 1}): return d.items
    beats = {b['beat_id']: b for b in source.get('event_sequence', [])}
    location = source.get('location') or {}
    names = [location.get('name'), *(location.get('sequence') or [])] if isinstance(location, dict) else [location]
    registries = deepcopy(resources)
    for request in row.get('asset_requests', []) if isinstance(row.get('asset_requests'), list) else []:
        if isinstance(request, dict) and request.get('kind') in ('character', 'object', 'location') and isinstance(request.get('request_id'), str):
            registries.setdefault({'character': 'characters', 'object': 'objects', 'location': 'locations'}[request['kind']], {})['request:'+request['request_id']] = request
    used = set()
    available_reveals = _reveal_ids(source.get('start_state', {}))
    for i, cut in enumerate(row['cuts']):
        p = f'/cuts/{i}'
        if not d.check(p, {'type': 'object'}): continue
        if d.check(p+'/cut_id', TEXT):
            if cut['cut_id'] in used: d.add(p+'/cut_id', TEXT, code='duplicate_cut_id')
            used.add(cut['cut_id'])
        for field in ('purpose', 'cut_function', 'duration_reason', 'primary_subject', 'first_frame_brief',
                      'motion_brief', 'motion_end_state', 'audio_intent', 'edit_reason', 'start_state_id', 'end_state_id'):
            d.check(p+'/'+field, TEXT)
        d.refs(p+'/source_beat_ids', beats, many=True, nonempty=True)
        refs = cut.get('source_beat_ids')
        if isinstance(refs, list) and all(isinstance(b, str) and b in beats for b in refs):
            d.refs(p+'/primary_beat_id', {b: beats[b] for b in refs})
        else: d.check(p+'/primary_beat_id', TEXT)
        d.check(p+'/duration_seconds', {'type': 'integer', 'minimum': 1, 'maximum': 60})
        d.refs(p+'/location_id', {k: v for k, v in registries.get('locations', {}).items() if v.get('name') in names})
        scope = resources.get('scene_assets', {}).get(str(source['scene_id']))
        for field, group in (('character_ids', 'characters'), ('object_ids', 'objects')):
            records = registries.get(group, {})
            if scope is not None:
                records = {k: v for k, v in records.items() if k in scope.get(field, []) or k not in resources.get(group, {})}
            d.refs(p+'/'+field, records, many=True)
            for issue in d.items:
                if (re.fullmatch(re.escape(p+'/'+field)+r'/[0-9]+', issue['path'])
                        and (not isinstance(issue['current_value'], str) or issue['current_value'] not in registries.get(group, {}))):
                    issue['allow_remove'] = True
        for field, enums in [('cut_role', ['main', 'sub']), ('event_time_position', sorted(EVENT_POSITIONS)),
            ('progression_mode', ['sequential_state_progression', 'suspended_moment']),
            ('narration_role', ['setup', 'fact', 'emotion', 'contrast', 'aftertaste', 'silent'])]:
            d.check(p+'/'+field, {'type': 'string', 'enum': enums})
        for field in ('start_state_facts', 'end_state_facts'):
            if d.check(p+'/'+field, {'type': 'object'}):
                if not cut[field]: d.add(p+'/'+field, {'type': 'object'}, code='state_facts_required')
                for key in cut[field]: d.check(p+'/'+field+'/'+_escape(key), TEXT)
        if isinstance(cut.get('start_state_facts'), dict):
            d.refs(p+'/visible_state_keys', cut['start_state_facts'], many=True, nonempty=True)
        else: d.check(p+'/visible_state_keys', STRINGS)
        if d.check(p+'/camera', {'type': 'object'}):
            for field in ('framing', 'movement', 'composition', 'light', 'focus'): d.check(p+'/camera/'+field, TEXT)
        if d.check(p+'/narration', {'type': 'string'}) and not cut['narration'].strip():
            d.check(p+'/silence_reason', TEXT)
        assigned = [beats[b] for b in refs if isinstance(b, str) and b in beats] if isinstance(refs, list) else []
        allowed = available_reveals | _reveal_ids(assigned)
        d.refs(p+'/allowed_reveal_info_ids', {k: {'source_beats': assigned} for k in sorted(allowed)}, many=True, removable=True)
        permitted = {v for beat in assigned for v in beat.get('allowed_new_reveal_elements', []) if isinstance(v, str)}
        d.refs(p+'/allowed_new_reveal_elements', {k: {'source_beats': assigned} for k in sorted(permitted)}, many=True, removable=True)
        if cut.get('cut_role') == 'main': available_reveals.update(_reveal_ids(assigned))
        if i == 0 and isinstance(source.get('start_state', {}).get('state_id'), str):
            d.refs(p+'/start_state_id', {source['start_state']['state_id']: source['start_state']})
        if i == len(row['cuts'])-1 and isinstance(source.get('end_state', {}).get('state_id'), str):
            d.refs(p+'/end_state_id', {source['end_state']['state_id']: source['end_state']})
        if d.check(p+'/continuity', {'type': 'object'}):
            d.check(p+'/continuity/connection', TEXT)
            d.check(p+'/continuity/previous_end_state', {'type': 'string'})
            d.check(p+'/continuity/mode', {'type': 'string', 'enum': ['scene_entry'] if i == 0 else ['continuous', 'ellipsis']})
            if cut['continuity'].get('mode') == 'ellipsis': d.check(p+'/continuity/ellipsis_reason', TEXT)
            expected = row['cuts'][i-1].get('cut_id') if i and isinstance(row['cuts'][i-1], dict) else ''
            if isinstance(expected, str): d.refs(p+'/continuity/previous_cut_id', {expected: {'meaning': 'previous cut'}})
    return d.items


def asset_request_diagnostics(row, story, research, resources):
    """Reference and shape diagnostics before the deterministic asset resolver."""
    from toc.p420_assets import KINDS
    d = Diagnostics(row)
    if not d.check('/asset_requests', {'type': 'array'}): return d.items
    cut_records = {c['cut_id']: c for c in row.get('cuts', []) if isinstance(c, dict) and isinstance(c.get('cut_id'), str)}
    ids = set()
    documents = {'story': story, 'research': research}
    source = next((s for s in story_scenes(story) if s['scene_id'] == row.get('scene_id')), {})
    roles = {r for beat in source.get('event_sequence', []) for r in (beat.get('required_roles') or beat.get('participants') or beat.get('character_ids') or []) if isinstance(r, str)}
    for i, request in enumerate(row['asset_requests']):
        p = f'/asset_requests/{i}'
        if not d.check(p, {'type': 'object'}): continue
        if d.check(p+'/request_id', TEXT):
            rid = request['request_id']
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', rid) or rid in ids:
                d.add(p+'/request_id', TEXT, code='request_id_invalid_or_duplicate')
            ids.add(rid)
        kind_valid = d.check(p+'/kind', {'type': 'string', 'enum': list(KINDS)})
        d.check(p+'/name', TEXT)
        d.refs(p+'/used_in_cuts', cut_records, many=True, nonempty=True)
        refs = []
        if d.check(p+'/source_entity', {'type': 'object'}): refs.append((p+'/source_entity', request['source_entity'], False))
        if d.check(p+'/source_evidence', {'type': 'array', 'minItems': 1}):
            for j, ref in enumerate(request['source_evidence']):
                rp = f'{p}/source_evidence/{j}'
                if d.check(rp, {'type': 'object'}): refs.append((rp, ref, True))
        for rp, ref, evidence in refs:
            if not d.refs(rp+'/source', {'story': {}, 'research': {}}): continue
            if evidence: d.check(rp+'/quote', TEXT)
            if d.check(rp+'/pointer', TEXT):
                records = {k: v for k, v in pointer_records(documents[ref['source']]).items() if isinstance(v['value'], str) and v['value'].strip()}
                d.refs(rp+'/pointer', records)
        if kind_valid:
            records = resources.get(KINDS[request['kind']][0], {})
            if 'existing_asset_id' in request:
                d.refs(p+'/existing_asset_id', {'': {'meaning': 'create source-grounded identity'}, **records})
            if 'distinct_from_asset_ids' in request: d.refs(p+'/distinct_from_asset_ids', records, many=True)
        if request.get('source_role_id'):
            d.refs(p+'/source_role_id', {role: {'scene': source} for role in roles})
    return d.items


def asset_reference_context(row, story, research):
    """Return the actual evidence for asset decisions without an entire research document."""
    records = []
    documents = {'story': story, 'research': research}
    for request in row.get('asset_requests', []) if isinstance(row.get('asset_requests'), list) else []:
        if not isinstance(request, dict): continue
        evidence = request.get('source_evidence')
        refs = [request.get('source_entity'), *(evidence if isinstance(evidence, list) else [])]
        for ref in refs:
            if not isinstance(ref, dict): continue
            try:
                value = _pointer(documents[ref['source']], ref['pointer'])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            record = {'source': ref['source'], 'pointer': ref['pointer'], 'value': value}
            if record not in records: records.append(record)
    return records


def projection_diagnostics(row, source, resources, *, story_time='', authored_row=None):
    """Use the real image compiler; map only known prose findings to their cut."""
    from toc.p400_projection import project_scene
    from toc.production_diagnostics import AuthoringValidationError
    try:
        project_scene(row, source_scene=source, scene_id=1, resources=resources,
            scene_intent={}, scene_event=source, scene_generation={}, acceptance_draft={},
            acceptance_binding={}, story_time=story_time)
    except AuthoringValidationError as exc:
        message = str(exc)
        if not message.startswith('cinematic_cut:'):
            raise
        issue = json.loads(message.removeprefix('cinematic_cut:'))
        reason = issue['reason']
        if reason == 'drawable_prompt_current_moment_missing':
            # The compiler may reject nonempty prose containing internal scene/cut
            # references. Only that authored frame description needs correction.
            d = Diagnostics(authored_row if authored_row is not None else row)
            d.add('/cuts/'+str(issue['cut_index'])+'/first_frame_brief',
                {**TEXT, 'description': 'Describe the concrete visible starting frame without internal scene/cut references.'},
                code=reason, kind='semantic')
            return d.items
        semantic_codes = ('drawable_prompt_time_of_day_conflict:', 'drawable_prompt_unresolved_alternative:',
            'drawable_prompt_sequential_overview:', 'drawable_prompt_abstract_placeholder:',
            'drawable_prompt_broken_japanese_join:')
        if not reason.startswith(semantic_codes):
            raise UnscopedRepairError(message) from exc
        d = Diagnostics(authored_row if authored_row is not None else row)
        d.add('/cuts/'+str(issue['cut_index']), {'type': 'object'}, code=reason, kind='semantic')
        return d.items
    return []


def semantic_direction_diagnostics(row, errors, source=None):
    """Only actual cut findings authorize cut rewrites; never promote all scenes."""
    d = Diagnostics(row)
    semantic = {'source_beat_order_invalid', 'source_start_state_mismatch', 'source_end_state_mismatch',
        'sub_must_be_unpeopled', 'narration_role_text_mismatch', 'reveal_not_authorized',
        'new_reveal_not_authorized', 'previous_end_state_mismatch', 'continuous_start_state_mismatch'}
    for error in errors:
        match = re.search(r':cut\[(\d+)\]:([^:]+)$', error)
        execution_match = re.search(r':cut\[(\d+)\]:(execution_invalid|film_overrides_invalid):', error)
        if execution_match:
            field = 'execution' if execution_match[2] == 'execution_invalid' else 'film_language_overrides'
            d.add(f'/cuts/{execution_match[1]}/{field}', {'type': 'object'}, code=error, kind='semantic')
        elif ':film_overrides_invalid:' in error:
            d.add('/film_language_overrides', {'type': 'object'}, code=error, kind='semantic')
        elif match and match[2] in semantic:
            d.add('/cuts/'+match[1], {'type': 'object'}, code=error, kind='semantic')
        elif ':missing_main_beat_coverage:' in error and source is not None:
            covered = {beat for cut in row['cuts'] if cut.get('cut_role') == 'main' for beat in cut['source_beat_ids']}
            missing = {beat['beat_id'] for beat in source['event_sequence'] if beat.get('must_be_seen', True)} - covered
            relevant = [i for i, cut in enumerate(row['cuts']) if missing.intersection(cut['source_beat_ids'])]
            if not relevant:
                # No existing cut owns the missing event: append one authored cut,
                # then revalidate ordering, timing, and continuity before adoption.
                relevant = [len(row['cuts'])]
            for i in relevant:
                d.add(f'/cuts/{i}', {'type': 'object'}, code=error, kind='semantic')
        elif ':scene_duration_mismatch:' in error:
            # Timing alone does not authorize rewriting the scene's prose or camera.
            for i in range(len(row['cuts'])):
                d.add(f'/cuts/{i}/duration_seconds', {'type': 'integer', 'minimum': 1, 'maximum': 60}, code=error)
        else:
            raise UnscopedRepairError('unscoped downstream diagnostic: '+error)
    return [item for item in d.items if not any(item['path'].startswith(other['path']+'/') for other in d.items if other is not item)]


def _unit_id(base):
    scene_id = base.get('scene_id')
    return scene_id if isinstance(scene_id, str) and scene_id else 'visual_value'


def _encoded_value(expected):
    return expected.get('type') == 'object' or (expected.get('type') == 'array' and expected.get('items', {}).get('type') != 'string')


def patch_schema(diagnostics, base, *, unit_id=None):
    paths = [d['path'] for d in diagnostics]
    if not paths: raise UnscopedRepairError('no authorized repair paths')
    variants = []
    for issue in diagnostics:
        expected = issue['expected']
        value_schema = {'type': 'string'} if _encoded_value(expected) else deepcopy(expected)
        # A registry can legitimately be empty. No valid replacement exists;
        # only an explicitly authorized deletion is offered in that case.
        if value_schema.get('type') == 'array' and value_schema.get('items', {}).get('enum') == []:
            if value_schema.get('minItems', 0):
                raise UnscopedRepairError('no registered reference candidate: '+issue['path'])
            value_schema['items'] = {'type': 'string'}
            value_schema['maxItems'] = 0
        if issue.get('allow_remove'):
            if expected.get('enum') == [] and issue.get('minimum_remaining_items', 1) != 0:
                raise UnscopedRepairError('no registered reference candidate and removal cannot empty the list: '+issue['path'])
            value_schema = ({'type': 'null'} if expected.get('enum') == [] else
                {'anyOf': [value_schema, {'type': 'null'}]})
        elif expected.get('enum') == []:
            raise UnscopedRepairError('no registered reference candidate: '+issue['path'])
        variants.append({'type': 'object', 'additionalProperties': False, 'required': ['path', 'value'],
            'properties': {'path': {'type': 'string', 'enum': [issue['path']]}, 'value': value_schema}})
    return {'type': 'object', 'additionalProperties': False, 'required': ['unit_id', 'base_digest', 'operations'],
        'properties': {'unit_id': {'type': 'string', 'enum': [unit_id if unit_id is not None else _unit_id(base)]},
            'base_digest': {'type': 'string', 'enum': [digest(base)]},
            'operations': {'type': 'array', 'minItems': 1, 'items': {'anyOf': variants}}}}


def apply_patch(base, diagnostics, patch, *, unit_id=None):
    if not isinstance(patch, dict) or set(patch) != {'unit_id', 'base_digest', 'operations'} or patch['base_digest'] != digest(base) or patch['unit_id'] != (unit_id if unit_id is not None else _unit_id(base)):
        raise ValueError('patch base digest/shape mismatch')
    ops = patch['operations']
    if not isinstance(ops, list) or not ops: raise ValueError('patch operations required')
    allowed = {d['path']: d for d in diagnostics}
    result, seen, removals = deepcopy(base), [], {}
    minimum_remaining = {}
    for operation in ops:
        if not isinstance(operation, dict) or set(operation) != {'path', 'value'}: raise ValueError('patch operation shape')
        path = operation['path']
        if not isinstance(path, str) or path not in allowed or not path or re.search(r'~(?![01])', path):
            raise ValueError('patch path outside diagnostic scope')
        if any(path == other or path.startswith(other+'/') or other.startswith(path+'/') for other in seen):
            raise ValueError('patch duplicate or overlapping paths')
        seen.append(path)
        diagnostic = allowed[path]
        try:
            current, exists = _pointer(base, path), True
        except (KeyError, IndexError):
            current, exists = None, False
        if exists == diagnostic['missing'] or (exists and current != diagnostic['current_value']):
            raise ValueError('diagnosed field changed before patch')
        value = operation['value']
        if value is None:
            if not diagnostic.get('allow_remove') or diagnostic['missing']:
                raise ValueError('patch removal not authorized')
            parent_path, index = path.rsplit('/', 1)
            parent = _pointer(base, parent_path)
            if not isinstance(parent, list) or not re.fullmatch(r'0|[1-9][0-9]*', index) or int(index) >= len(parent):
                raise ValueError('patch removal must address an original array element')
            if parent[int(index)] != diagnostic['current_value'] or _valid(parent[int(index)], diagnostic['expected']):
                raise ValueError('patch cannot remove a valid or changed reference')
            minimum = diagnostic.get('minimum_remaining_items', 1)
            if type(minimum) is not int or minimum < 0:
                raise ValueError('invalid diagnostic minimum for removal')
            minimum_remaining[parent_path] = max(minimum_remaining.get(parent_path, 0), minimum)
            removals.setdefault(parent_path, []).append(int(index))
            continue
        if _encoded_value(diagnostic['expected']):
            if not isinstance(value, str): raise ValueError('structured patch value must be a JSON string')
            decoded, receipt = decode_json_object_with_repair('{"value":'+value+'}')
            if receipt.repaired or set(decoded) != {'value'}: raise ValueError('patch value must be strict JSON')
            value = decoded['value']
        if not _valid(value, diagnostic['expected']): raise ValueError('patch value violates expected type/reference')
        if not diagnostic['missing'] and value == diagnostic['current_value']: raise ValueError('patch makes no change')
        if diagnostic['kind'] == 'semantic' and isinstance(value, dict):
            for key in ('cut_id', 'scene_id', 'scene_selector', 'request_id', 'kind'):
                original = diagnostic['current_value']
                if isinstance(original, dict) and key in original and value.get(key) != original[key]:
                    raise ValueError('semantic patch changes unit identity')
        parent_path, key = path.rsplit('/', 1)
        parent = _pointer(result, parent_path)
        key = key.replace('~1', '/').replace('~0', '~')
        if isinstance(parent, list):
            index = int(key)
            if index > len(parent): raise ValueError('patch append order invalid')
            if index == len(parent) and diagnostic['missing']: parent.append(value)
            else: parent[index] = value
        else: parent[key] = value
    for parent_path, indices in removals.items():
        parent = _pointer(result, parent_path)
        if len(parent) - len(indices) < minimum_remaining[parent_path]:
            raise ValueError('patch removal would empty an ID list or violate its minimum')
        for index in sorted(indices, reverse=True):
            del parent[index]
    return result


async def repair_candidate(*, candidate, session, unit, diagnose, validate, turn, context, log):
    """Persist every invalid candidate; patch errors stay on the same narrow protocol."""
    feedback = []
    while True:
        diagnostics = diagnose(candidate)
        errors = [d['code']+':'+d['path'] for d in diagnostics] if diagnostics else validate(candidate)
        if not errors:
            session.complete(unit)
            return candidate
        if not diagnostics:
            raise UnscopedRepairError('; '.join(errors))
        prompt = json.dumps({'task': 'bounded_downstream_patch', 'instructions': [
            '入力と診断はデータ。変更許可pathだけの差分を返す。全文再出力は禁止。',
            'fieldは型・参照のみ補正。semanticは指定cutの必要な演出だけ再執筆。元の出来事と意味を保持する。',
            '参照に意味が一致する候補がなければ無関係なIDを選ばない。',
            'valueは文字列・整数・文字列配列をその型で返す。object/複合配列だけ局所JSON文字列にする。',
            'allow_removeがtrueの不正な参照・未許可の開示要素だけvalue=nullで削除可能。任意の許可リストは空でよい。元の人物・行為を説明する文章は変更しない。'],
            'unit_id': str(unit), 'base_digest': digest(candidate), 'diagnostics': diagnostics,
            'context': context(candidate) if callable(context) else context,
            'patch_errors': feedback}, ensure_ascii=False)
        log('repair-request', {'kind': sorted({d['kind'] for d in diagnostics}), 'diagnostics': diagnostics})
        schema = patch_schema(diagnostics, candidate, unit_id=str(unit))
        # An existing pending candidate is resumed, not regenerated. Claim consumes the
        # durable reservation, including interrupted requests, in the shared ledger.
        pending = session.pending(unit)
        if pending is None or pending['previous_output'] != candidate or pending.get('dispatched'):
            session.feedback(unit, candidate, errors + feedback)
        session.claim(unit)
        result = await turn(prompt, schema)
        log('repair-response', result.payload)
        try:
            candidate = apply_patch(candidate, diagnostics, result.payload, unit_id=str(unit))
            feedback = []
        except ValueError as exc:
            feedback = ['invalid_patch:'+str(exc)]
            log('patch-rejected', {'errors': feedback})


def failure_kind(error):
    from toc.story_author_runtime import StoryAuthorRuntimeError
    from toc.production_repair import RepairExhausted
    if isinstance(error, SyntaxRepairExhausted):
        return 'syntax'
    if isinstance(error, StoryAuthorRuntimeError) and getattr(error, 'diagnostic', None) is not None:
        return 'syntax'
    if isinstance(error, (UnscopedRepairError, RepairExhausted)):
        return 'content'
    return 'runtime'


async def decode_author_payload(payload, *, session, unit, turn, log):
    """Use the existing p200 syntax-only protocol, without resending authoring."""
    from toc.story_author_runtime import decode_story_transport_payload, StoryAuthorRuntimeError
    from toc.story_syntax_patch import (SYNTAX_EDIT_SCHEMA, SYNTAX_REPAIR_CONTRACT,
        SyntaxPatchError, syntax_patchable, build_syntax_prompt, apply_syntax_edits)
    try:
        return decode_story_transport_payload(payload,
            on_syntax_repair=lambda receipt: log('syntax-repair', receipt.as_dict()))
    except StoryAuthorRuntimeError as exc:
        raw = payload.get('result_json')
        if not isinstance(raw, str) or exc.diagnostics.get('code') != 'invalid_json' or not syntax_patchable(raw):
            raise
        diagnostic = exc.diagnostics
    syntax_unit = 'syntax-'+unit+'-'+digest(raw)
    previous_patch, patch_error = None, None
    while True:
        candidate = {'raw_json': raw, 'previous_patch': previous_patch}
        pending = session.pending(syntax_unit)
        try:
            if pending is None or pending.get('dispatched'):
                session.feedback(syntax_unit, candidate, ['JSON syntax only: '+str(patch_error or diagnostic)])
            session.claim(syntax_unit)
        except RepairExhausted as exc:
            raise SyntaxRepairExhausted(str(exc)) from exc
        result = await turn(build_syntax_prompt(raw, diagnostic, previous_patch, patch_error), SYNTAX_EDIT_SCHEMA)
        previous_patch = result.payload
        log('syntax-response', previous_patch)
        try:
            fixed = apply_syntax_edits(raw, previous_patch)
        except SyntaxPatchError as exc:
            patch_error = str(exc)
            log('syntax-rejected', {'error': patch_error})
            continue
        document = decode_story_transport_payload({'result_json': fixed})
        log('syntax-repair', {'contract': SYNTAX_REPAIR_CONTRACT, 'kind': 'syntax_patch',
            'before_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'after_sha256': hashlib.sha256(fixed.encode()).hexdigest(), 'edits': previous_patch['edits']})
        session.complete(syntax_unit)
        return document
