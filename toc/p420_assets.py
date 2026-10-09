"""Resolve source-grounded p420 asset requests; no model call or narrative fallback."""
from copy import deepcopy
import hashlib
import json
import re
import unicodedata

from toc.visual_planning_contract import _pointer, story_scenes

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


def _source_text(ref, documents):
    if not isinstance(ref, dict) or ref.get('source') not in ('story', 'research') or not isinstance(ref.get('pointer'), str):
        _fail('source_reference_invalid')
    pointer = ref['pointer']
    if not pointer.startswith('/') or any(token in pointer.split('/') for token in ('symbols_and_themes', 'theme', 'motifs', 'visual_notes')):
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
                entity_text = _source_text(entity, documents)
                if name not in entity_text:
                    _fail('name_not_in_source_entity')
                used = request.get('used_in_cuts')
                if not isinstance(used, list) or not used or any(not isinstance(cid, str) or cid not in cut_by_id for cid in used) or len(set(used)) != len(used):
                    _fail('used_in_cuts_invalid')
                evidence = request.get('source_evidence')
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
                if not any(name in ref['quote'] for ref in evidence):
                    _fail('name_not_in_usage_evidence')
                beat_ranks = {b['beat_id']: i for i, b in enumerate(source['event_sequence'])}
                for cid in used:
                    assigned = cut_by_id[cid].get('source_beat_ids')
                    if not isinstance(assigned, list) or not assigned or any(b not in beat_ranks for b in assigned):
                        _fail('cut_source_beats_invalid')
                    if min(evidence_ranks) > min(beat_ranks[b] for b in assigned):
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
                    if not resource.get('source_identity') and unicodedata.normalize('NFKC', resource.get('name', '')).strip() == normalized_name}
                if not existing and not ambiguous_existing <= set(distinct):
                    _fail('existing_candidate_requires_explicit_choice')
                if existing:
                    entry = resources[group].get(existing)
                    if not entry or unicodedata.normalize('NFKC', entry.get('name', '')).strip() != normalized_name:
                        _fail('existing_asset_unknown_or_name_mismatch')
                    if entry.get('source_identity') and entry['source_identity'] != identity:
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
    return errors
