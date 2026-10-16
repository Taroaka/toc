import json

import pytest

from server.cut_direction_api import _read_direction
from toc.shot_projection import project_cut_shots
from toc.p400_authoring import _cast_design_artifact_binding
from toc.visual_planning_contract import source_binding
from test_cast_design import whole_cast_fixture
from test_cut_direction_api import _plan


def fixture(root, change=None):
    resources, cast = whole_cast_fixture()
    if change:
        change(resources, cast)
    direction = {'resources': resources, 'cast_design': cast,
                 'metadata': {'source_bindings': cast['source_bindings']}}
    direction['metadata']['cast_design_binding'] = _cast_design_artifact_binding(
        cast['source_bindings'], resources, cast, cast['reference_identity_bindings'])
    raw = json.dumps(direction).encode()
    (root / 'cinematic_direction.json').write_bytes(raw)
    manifest = {'video_metadata': {'cinematic_direction_contract': 'cinematic_direction_v1',
                'source_cinematic_direction': source_binding('cinematic_direction.json', raw)}}
    return direction, raw, manifest


def test_declared_cast_members_reach_shot_projection_without_mutating_source(tmp_path):
    original, raw, manifest = fixture(tmp_path)
    resources, direction, returned = _read_direction(tmp_path, manifest)
    assert resources['characters']['siblings']['members'][0]['name'] == 'older sibling'
    assert resources['characters']['siblings']['subject_contract']['member_ids'] == ['elder', 'younger']
    assert resources['characters']['siblings']['references'] == original['resources']['characters']['siblings']['references']
    assert direction == original and returned == raw
    resources['characters']['siblings']['members'][0]['name'] = 'caller mutation'
    assert direction == original and (tmp_path / 'cinematic_direction.json').read_bytes() == raw


def test_cast_member_mapping_preserves_existing_reference_fields(tmp_path):
    def add(resources, cast):
        resources['characters']['siblings']['members'] = [{'member_id': 'elder', 'references': ['assets/characters/elder.png']}]
    _, _, manifest = fixture(tmp_path, add)
    resources, _, _ = _read_direction(tmp_path, manifest)
    assert resources['characters']['siblings']['members'][0]['references'] == ['assets/characters/elder.png']


def test_unknown_member_is_still_rejected_by_shot_projection(tmp_path):
    _, _, manifest = fixture(tmp_path)
    resources, _, _ = _read_direction(tmp_path, manifest)
    plan = _plan()
    plan['shots'][0]['initial_view']['subjects'][0].update(entity_id='siblings', member_id='invented')
    plan['shots'][0]['performance'][0].update(actor_id='siblings', member_id='invented')
    parent = {'selector': 'scene10_cut01', 'video_generation': {'duration_seconds': 4},
              'cut_contract': {'asset_dependency': {'character_ids_required': ['siblings']}}}
    with pytest.raises(ValueError, match='member_reference_unresolved'):
        project_cut_shots(parent, plan, resources)


@pytest.mark.parametrize('fault', ['duplicate_member', 'stale_source', 'stale_bytes', 'stale_cast_binding'])
def test_invalid_cast_or_direction_binding_cannot_supply_member_names(tmp_path, fault):
    def corrupt(resources, cast):
        if fault == 'duplicate_member':
            cast['characters']['siblings']['members'][1]['member_id'] = 'elder'
    _, raw, manifest = fixture(tmp_path, corrupt)
    if fault in {'stale_source', 'stale_cast_binding'}:
        direction = json.loads(raw)
        if fault == 'stale_source':
            direction['metadata']['source_bindings'] = {'research': 'changed'}
        else:
            direction['metadata']['cast_design_binding'] = 'stale'
        raw = json.dumps(direction).encode()
        (tmp_path / 'cinematic_direction.json').write_bytes(raw)
        manifest['video_metadata']['source_cinematic_direction'] = source_binding('cinematic_direction.json', raw)
    if fault == 'stale_bytes':
        (tmp_path / 'cinematic_direction.json').write_bytes(raw + b' ')
    with pytest.raises(ValueError):
        _read_direction(tmp_path, manifest)
