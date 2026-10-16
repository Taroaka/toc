"""Resolve source-grounded p420 asset requests; no model call or narrative fallback."""
from copy import deepcopy
import hashlib
import json
import re
import unicodedata

from toc.visual_planning_contract import _pointer, story_scenes
from toc.asset_state_variants import state_variant_output_path
from toc.cast_design import appearance_contract_from_design, validate_cast_design

ASSET_RESOLUTION_CONTRACT = 'source_asset_requests_v1'
KINDS = {'character': ('characters', 'character_ids'), 'object': ('objects', 'object_ids'), 'location': ('locations', 'location_id')}
_REQUEST_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z')


def _text(value):
    return isinstance(value, str) and bool(value.strip())


class AssetRequestValidationError(ValueError):
    def __init__(self, reason, *, path=''):
        super().__init__('asset_request:' + reason)
        self.reason, self.path = reason, path


def _fail(reason):
    raise AssetRequestValidationError(reason)


def _source_text(ref, documents, *, allow_physical_symbol=False):
    if not isinstance(ref, dict) or ref.get('source') not in ('story', 'research') or not isinstance(ref.get('pointer'), str):
        _fail('source_reference_invalid')
    pointer = ref['pointer']
    physical_symbol = False
    match = re.fullmatch(r'/story_materials/symbols_and_themes/(\d+)/item', pointer)
    if allow_physical_symbol and ref['source'] == 'research' and match:
        try:
            record = documents['research']['story_materials']['symbols_and_themes'][int(match[1])]
            physical_symbol = isinstance(record, dict) and record.get('kind') == 'object'
        except (KeyError, IndexError, TypeError):
            pass
    if not pointer.startswith('/') or (not physical_symbol and any(token in pointer.split('/') for token in ('symbols_and_themes', 'theme', 'motifs', 'visual_notes'))):
        _fail('physical_source_required')
    try:
        value = _pointer(documents[ref['source']], pointer)
    except (KeyError, IndexError, ValueError, TypeError):
        _fail('source_pointer_unresolved')
    if not _text(value):
        _fail('source_pointer_must_address_text')
    return value


def _evidence_rank(ref, *, scene, scene_index, documents):
    """Bind evidence to this scene's events, rather than any matching book passage."""
    root = '/script/scenes' if isinstance(documents['story'].get('script'), dict) else '/scenes'
    if ref['source'] == 'story':
        prefix = f'{root}/{scene_index}/'
        if not ref['pointer'].startswith(prefix):
            _fail('evidence_outside_source_scene')
        tail = ref['pointer'][len(prefix):]
        match = re.match(r'event_sequence/(\d+)/', tail)
        if match:
            return int(match[1])
        if tail.startswith('location/'):
            return 0
        if re.fullmatch(r'start_state/objects/\d+(?:/name)?', tail):
            return 0
        _fail('evidence_must_address_event_or_location')
    match = re.match(r'/story_materials/chronological_events/(\d+)/', ref['pointer'])
    if not match:
        _fail('research_evidence_must_address_scene_event')
    try:
        event = documents['research']['story_materials']['chronological_events'][int(match[1])]
        ranks = [i for i, beat in enumerate(scene['event_sequence']) if event['event_id'] in beat.get('source_event_ids', [])]
    except (KeyError, IndexError, TypeError):
        ranks = []
    if not ranks:
        _fail('evidence_outside_source_scene')
    return min(ranks)


def _opening_object_evidence(scene, scene_index, name, documents):
    """Corroborate presence only from this scene's explicit opening objects."""
    state = scene.get('start_state')
    objects = state.get('objects') if isinstance(state, dict) else None
    if not isinstance(objects, list):
        return None
    root = '/script/scenes' if isinstance(documents['story'].get('script'), dict) else '/scenes'
    matches = []
    for index, item in enumerate(objects):
        text = item.get('name') if isinstance(item, dict) else item
        if isinstance(text, str) and name in text:
            suffix = '/name' if isinstance(item, dict) else ''
            matches.append({'source': 'story', 'pointer': f'{root}/{scene_index}/start_state/objects/{index}{suffix}', 'quote': text})
    return matches[0] if len(matches) == 1 else None


def resolve_asset_requests(rows, story, research, base_resources):
    """Return resolved scenes, augmented registry, and deterministic resolution records.

    Can be rerun on saved (already resolved) rows against the original base registry.
    Never infer entity identity from a name alone; new identity is kind+source pointer+name.
    """
    resolved, resources, records = deepcopy(rows), deepcopy(base_resources), []
    documents = {'story': story, 'research': research}
    source_rows = story_scenes(story)
    source_by_id = {s['scene_id']: (i, s) for i, s in enumerate(source_rows)}
    for row in resolved:
        if not isinstance(row, dict) or row.get('scene_id') not in source_by_id:
            _fail('scene_unknown')
        scene_index, source = source_by_id[row['scene_id']]
        cuts = row.get('cuts')
        if not isinstance(cuts, list) or any(not isinstance(c, dict) or not _text(c.get('cut_id')) for c in cuts):
            _fail('cuts_invalid')
        cut_by_id = {c['cut_id']: c for c in cuts}
        if len(cut_by_id) != len(cuts):
            _fail('duplicate_cut_id')
        requests = row.get('asset_requests', [])
        if not isinstance(requests, list):
            _fail('requests_must_be_list')
        aliases = {}
        bindings = []
        for request_index, request in enumerate(requests):
            try:
                if not isinstance(request, dict):
                    _fail('request_must_be_mapping')
                rid, kind, name = request.get('request_id'), request.get('kind'), request.get('name')
                if not isinstance(rid, str) or not _REQUEST_ID.fullmatch(rid) or rid in aliases:
                    _fail('request_id_invalid_or_duplicate')
                if not isinstance(kind, str) or kind not in KINDS or not _text(name):
                    _fail('kind_name_or_description_missing')
                group, field = KINDS[kind]
                entity = request.get('source_entity')
                entity_text = _source_text(entity, documents, allow_physical_symbol=kind == 'object')
                if name not in entity_text:
                    _fail('name_not_in_source_entity')
                used = request.get('used_in_cuts')
                if not isinstance(used, list) or not used or any(not isinstance(cid, str) or cid not in cut_by_id for cid in used) or len(set(used)) != len(used):
                    _fail('used_in_cuts_invalid')
                evidence = deepcopy(request.get('source_evidence'))
                if not isinstance(evidence, list) or not evidence:
                    _fail('source_evidence_required')
                evidence_ranks = []
                for ref in evidence:
                    value = _source_text(ref, documents)
                    if not _text(ref.get('quote')) or ref['quote'] not in value:
                        _fail('source_quote_mismatch')
                    rank = _evidence_rank(ref, scene=source, scene_index=scene_index, documents=documents)
                    if name in ref['quote']:
                        evidence_ranks.append(rank)
                beat_ranks = {b['beat_id']: i for i, b in enumerate(source['event_sequence'])}
                first_use_ranks = []
                for cid in used:
                    assigned = cut_by_id[cid].get('source_beat_ids')
                    if not isinstance(assigned, list) or not assigned or any(b not in beat_ranks for b in assigned):
                        _fail('cut_source_beats_invalid')
                    first_use_ranks.append(min(beat_ranks[b] for b in assigned))
                if kind == 'object' and (not evidence_ranks or min(evidence_ranks) > min(first_use_ranks)):
                    opening = _opening_object_evidence(source, scene_index, name, documents)
                    if opening:
                        evidence.append(opening)
                        evidence_ranks.append(_evidence_rank(opening, scene=source, scene_index=scene_index, documents=documents))
                if not evidence_ranks:
                    _fail('name_not_in_usage_evidence')
                if min(evidence_ranks) > min(first_use_ranks):
                    _fail('evidence_belongs_to_future_beat')
                normalized_name = unicodedata.normalize('NFKC', name).strip()
                identity = {'kind': kind, 'source': entity['source'], 'pointer': entity['pointer'], 'name': normalized_name}
                key = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
                existing = request.get('existing_asset_id', '')
                if not isinstance(existing, str):
                    _fail('existing_asset_id_invalid')
                distinct = request.get('distinct_from_asset_ids', [])
                if not isinstance(distinct, list) or any(not isinstance(a, str) or a not in resources[group] for a in distinct):
                    _fail('distinct_identity_targets_invalid')
                if distinct and (existing or not _text(request.get('distinct_identity_reason'))):
                    _fail('distinct_identity_reason_or_choice_invalid')
                for other in distinct:
                    resource = resources[group][other]
                    if unicodedata.normalize('NFKC', resource.get('name', '')).strip() != normalized_name or resource.get('source_identity') == identity:
                        _fail('distinct_identity_targets_invalid')
                ambiguous_existing = {other for other, resource in resources[group].items()
                    if (not resource.get('source_identity') and unicodedata.normalize('NFKC', resource.get('name', '')).strip() == normalized_name)
                    or (resource.get('source_entity') == entity and other != f'source-{kind}-{key}')}
                if not existing and not ambiguous_existing <= set(distinct):
                    _fail('existing_candidate_requires_explicit_choice')
                if existing:
                    entry = resources[group].get(existing)
                    same_source = bool(entry) and entry.get('source_entity') == entity
                    if entry and entry.get('source_entity') and not same_source:
                        _fail('existing_asset_identity_mismatch')
                    if not entry or (not same_source and unicodedata.normalize('NFKC', entry.get('name', '')).strip() != normalized_name):
                        _fail('existing_asset_unknown_or_name_mismatch')
                    if entry.get('source_identity') and any(
                        entry['source_identity'].get(field) != identity[field]
                        for field in ('kind', 'source', 'pointer')
                    ):
                        _fail('existing_asset_identity_mismatch')
                    aid, created = existing, False
                else:
                    aid = f'source-{kind}-{key}'
                    entry = resources[group].get(aid)
                    created = entry is None
                    if entry and entry.get('source_identity') != identity:
                        _fail('asset_id_collision')
                    if entry is None:
                        entry = {'name': name, 'references': [f'assets/{group}/{aid}.png'],
                            'source_identity': identity, 'source_entity': deepcopy(entity),
                            'source_evidence': deepcopy(evidence), 'reference_description': name}
                        resources[group][aid] = entry
                entry = resources[group][aid]
                entry.setdefault('source_identity', deepcopy(identity))
                entry.setdefault('source_entity', deepcopy(entity))
                all_evidence = entry.setdefault('source_evidence', [])
                for ref in evidence:
                    if ref not in all_evidence:
                        all_evidence.append(deepcopy(ref))
                role = request.get('source_role_id', '')
                if role:
                    roles = {r for beat in source['event_sequence'] for r in (beat.get('required_roles') or beat.get('participants') or beat.get('character_ids') or [])}
                    if kind != 'character' or not isinstance(role, str) or role not in roles:
                        _fail('source_role_invalid')
                    entry = resources[group][aid]
                    role_ids = entry.setdefault('source_role_ids', [])
                    if role not in role_ids:
                        role_ids.append(role)
                aliases[rid] = (field, aid)
                # A missing scene binding is also resolved explicitly, with evidence.
                scope = resources.setdefault('scene_assets', {}).setdefault(row['scene_id'], {
                    'character_ids': list(base_resources.get('characters', {})),
                    'object_ids': list(base_resources.get('objects', {})),
                    'location_ids': list(base_resources.get('locations', {}))})
                scope_field = 'location_ids' if kind == 'location' else field
                scope.setdefault(scope_field, [])
                if aid not in scope[scope_field]:
                    scope[scope_field].append(aid)
                record = {'scene_id': row['scene_id'], 'request_id': rid, 'asset_id': aid,
                    'kind': kind, 'created': created, 'source_identity': identity,
                    'source_evidence': deepcopy(evidence), 'used_in_cuts': list(used)}
                records.append(record); bindings.append((request, field, aid))
            except AssetRequestValidationError as exc:
                raise AssetRequestValidationError(exc.reason, path=f'/asset_requests/{request_index}') from exc
        for cut in cuts:
            for field in ('character_ids', 'object_ids', 'location_id'):
                values = [cut.get(field)] if field == 'location_id' else cut.get(field)
                if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                    _fail('cut_asset_fields_invalid')
                converted = []
                for value in values:
                    if value.startswith('request:'):
                        binding = aliases.get(value.removeprefix('request:'))
                        if not binding or binding[0] != field:
                            _fail('request_reference_unknown_or_wrong_kind')
                        value = binding[1]
                    converted.append(value)
                if len(set(converted)) != len(converted):
                    _fail('duplicate_cut_asset')
                cut[field] = converted[0] if field == 'location_id' else converted
            if isinstance(cut.get('shot_plan'), dict):
                def resolve_shot_ids(value, key=''):
                    if isinstance(value, dict):
                        return {k: resolve_shot_ids(v, k) for k, v in value.items()}
                    if isinstance(value, list):
                        return [resolve_shot_ids(v, key) for v in value]
                    if key in ('entity_id', 'entity_ids', 'actor_id', 'target_id') and isinstance(value, str) and value.startswith('request:'):
                        binding = aliases.get(value.removeprefix('request:'))
                        if not binding:
                            _fail('shot_request_reference_unknown')
                        return binding[1]
                    return value
                cut['shot_plan'] = resolve_shot_ids(cut['shot_plan'])
        for request, field, aid in bindings:
            actual = [c['cut_id'] for c in cuts if aid == c.get(field) or (isinstance(c.get(field), list) and aid in c[field])]
            if set(actual) != set(request['used_in_cuts']):
                _fail('asset_usage_mismatch_or_unused')
    return resolved, resources, records


def extend_asset_bibles(manifest, direction):
    """Put only resolved source assets into the existing p500 bible interface."""
    assets = manifest['assets']
    for kind, (group, _field) in KINDS.items():
        id_key = f'{kind}_id'
        bible = assets.setdefault(f'{kind}_bible', [])
        present = {entry[id_key] for entry in bible}
        for aid, resource in direction['resources'][group].items():
            if aid in present:
                if resource.get('source_identity'):
                    target = next(item for item in bible if item[id_key] == aid)
                    target['source_identity'] = deepcopy(resource['source_identity'])
                    target['source_evidence'] = deepcopy(resource['source_evidence'])
                continue
            if not resource.get('source_identity'):
                _fail('new_bible_asset_without_source_identity')
            name = resource['name']
            description = resource['reference_description']
            entry = {id_key: aid, 'reference_images': list(resource['references']), 'review_aliases': [name],
                'fixed_prompts': [description], 'cinematic': {'role': name, 'visual_subject': description},
                'reuse_contract': {'mode': 'neutral_anchor'}, 'source_identity': deepcopy(resource['source_identity']),
                'source_evidence': deepcopy(resource['source_evidence'])}
            if kind == 'character':
                entry['subject_contract'] = {'identity_scope': 'individual', 'subject_count': 1, 'member_ids': []}
                entry['appearance_contract'] = {}
            elif kind == 'object':
                entry['kind'] = 'setpiece'
            bible.append(entry); present.add(aid)

    cast_design = direction.get('cast_design') if isinstance(direction, dict) else None
    if cast_design is not None:
        issues = validate_cast_design(
            cast_design,
            direction.get('resources', {}),
            expected_source_bindings=direction.get('metadata', {}).get('source_bindings'),
        )
        if issues:
            _fail('cast_design_invalid:' + ';'.join(issues))
        by_id = {entry.get('character_id'): entry for entry in assets.get('character_bible', [])
                 if isinstance(entry, dict)}
        for character_id, record in cast_design['characters'].items():
            target = by_id.get(character_id)
            if target is None:
                _fail('cast_design_character_bible_missing')
            appearance = target.get('appearance_contract')
            appearance = deepcopy(appearance) if isinstance(appearance, dict) else {}
            appearance.update(appearance_contract_from_design(
                record, all_records=cast_design.get('characters', {})))
            target['appearance_contract'] = appearance
            target['subject_contract'] = deepcopy(record['subject_contract'])

    for scene in direction.get('scenes', []) if isinstance(direction, dict) else []:
        if not isinstance(scene, dict):
            continue
        for raw_variant in scene.get('state_variants', []) or []:
            if not isinstance(raw_variant, dict):
                continue
            kind = str(raw_variant.get('entity_type') or '').strip()
            if kind not in KINDS:
                _fail('state_variant_entity_type_invalid')
            group, _field = KINDS[kind]
            asset_id = str(raw_variant.get('asset_id') or '').strip()
            variant_id = str(raw_variant.get('variant_id') or '').strip()
            resource = direction.get('resources', {}).get(group, {}).get(asset_id)
            if not asset_id or not variant_id or not isinstance(resource, dict):
                _fail('state_variant_asset_unknown')
            output = state_variant_output_path(kind, asset_id, variant_id)
            transition = {key: deepcopy(raw_variant.get(key)) for key in (
                'transition_id', 'source_event_beat_ids', 'from_state', 'to_state'
            )}
            state_record = {
                'variant_id': variant_id,
                'reference_images': [output],
                'generation_references': list(resource.get('references') or []),
                'generation_prompt': str(raw_variant.get('generation_prompt') or '').strip(),
                'fixed_prompts': [],
                'state_transition': transition,
            }
            id_key = f'{kind}_id'
            parent = next((item for item in assets[f'{kind}_bible'] if item.get(id_key) == asset_id), None)
            if parent is None:
                _fail('state_variant_parent_bible_missing')
            variants = parent.setdefault('reference_variants', [])
            if not isinstance(variants, list):
                _fail('state_variant_reference_list_invalid')
            existing = next((item for item in variants if isinstance(item, dict) and item.get('variant_id') == variant_id), None)
            if existing is not None and existing != state_record:
                _fail('state_variant_projection_conflict')
            if existing is None:
                variants.append(state_record)


def asset_projection_issues(data, direction, *, manifest=False):
    if direction.get('metadata', {}).get('asset_resolution_contract') != ASSET_RESOLUTION_CONTRACT:
        return []
    errors = []
    if data.get('asset_resolutions', []) != direction.get('asset_resolutions', []):
        errors.append('asset_request:resolution_projection_changed')
    if not manifest:
        return errors
    base = direction['base_resources']
    expected = {'assets': {f'{kind}_bible': [{f'{kind}_id': aid} for aid in base[group]]
                          for kind, (group, _field) in KINDS.items()}}
    extend_asset_bibles(expected, direction)
    for kind, (group, _field) in KINDS.items():
        key = f'{kind}_id'
        actual = data.get('assets', {}).get(f'{kind}_bible', [])
        for entry in expected['assets'][f'{kind}_bible']:
            if not direction['resources'][group][entry[key]].get('source_identity'):
                continue
            matches = [item for item in actual if isinstance(item, dict) and item.get(key) == entry[key]]
            if len(matches) != 1 or any(matches[0].get(field) != value for field, value in entry.items()):
                errors.append('asset_request:bible_projection_missing_or_changed:' + entry[key])
    for scene in direction.get('scenes', []) or []:
        if not isinstance(scene, dict):
            continue
        for raw_variant in scene.get('state_variants', []) or []:
            if not isinstance(raw_variant, dict):
                continue
            kind = str(raw_variant.get('entity_type') or '').strip()
            if kind not in KINDS:
                continue
            group, _field = KINDS[kind]
            asset_id = str(raw_variant.get('asset_id') or '').strip()
            variant_id = str(raw_variant.get('variant_id') or '').strip()
            bible = data.get('assets', {}).get(f'{kind}_bible', [])
            parent = next((item for item in bible if isinstance(item, dict) and item.get(f'{kind}_id') == asset_id), None)
            actual = next((item for item in (parent or {}).get('reference_variants', [])
                           if isinstance(item, dict) and item.get('variant_id') == variant_id), None)
            resource = direction.get('resources', {}).get(group, {}).get(asset_id, {})
            expected_variant = {
                'variant_id': variant_id,
                'reference_images': [state_variant_output_path(kind, asset_id, variant_id)],
                'generation_references': list(resource.get('references') or []),
                'generation_prompt': str(raw_variant.get('generation_prompt') or '').strip(),
                'fixed_prompts': [],
                'state_transition': {key: deepcopy(raw_variant.get(key)) for key in (
                    'transition_id', 'source_event_beat_ids', 'from_state', 'to_state'
                )},
            }
            if actual != expected_variant:
                errors.append('asset_request:state_variant_projection_missing_or_changed:' + f'{asset_id}/{variant_id}')
    return errors
