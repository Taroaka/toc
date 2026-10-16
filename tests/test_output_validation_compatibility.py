import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from test_adaptation_value_contract import _story
from test_verify_pipeline import VERIFY
from toc.adaptation_value_contract import story_adaptation_issues


@pytest.mark.parametrize('field,text_key', [('non_negotiable_events', 'requirement'),
    ('non_negotiable_meanings', 'meaning'), ('iconic_moments', 'moment')])
def test_source_linked_preservation_records_keep_required_text_and_sources(field, text_key):
    story = _story()
    record = {text_key: 'A source-grounded obligation.', 'source_event_refs': ['E1'], 'source_passage_refs': ['P1']}
    story['adaptation_source_contract'][field] = [record]
    assert story_adaptation_issues(story) == []
    for key, value in [(text_key, ''), (text_key, 1), ('source_event_refs', []),
                       ('source_event_refs', 'E1'), ('source_passage_refs', [1])]:
        broken = deepcopy(story)
        broken['adaptation_source_contract'][field][0][key] = value
        assert story_adaptation_issues(broken)


def test_character_state_variant_views_do_not_relax_base_identity_views(tmp_path):
    base = {'asset_id': 'character', 'asset_type': 'character_fullbody', 'source_script_selectors': [],
        'generation_plan': {'required_views': ['single']}}
    parent = {**base, 'asset_id': 'parent', 'generation_plan': {'required_views': ['front', 'side', 'back']}}
    manifest = {'assets': {'character_bible': [{'character_id': 'parent',
        'reference_images': ['assets/characters/parent.png'], 'reference_variants': [{
            'variant_id': 'changed', 'reference_images': ['assets/characters/changed.png'],
            'generation_prompt': 'The same character after the authored change.',
            'state_transition': {'transition_id': 'change', 'source_event_beat_ids': ['E1'],
                'from_state': 'before', 'to_state': 'after'}}]}]},
        'scenes': [{'scene_id': 1, 'scene_event': {'event_sequence': [{'beat_id': 'E1'}]},
            'cuts': [{'cut_id': 1, 'image_generation': {'character_ids': ['parent'], 'character_variant_ids': ['changed']}}]}]}
    (tmp_path / 'video_manifest.md').write_text('```yaml\n' + yaml.safe_dump(manifest) + '```\n')
    def check(entry, *, include_parent=True):
        (tmp_path / 'asset_plan.md').write_text('```yaml\n' + yaml.safe_dump({'assets': [entry, *([parent] if include_parent else [])]}) + '```\n')
        report, _ = VERIFY.check_asset(tmp_path)
        return next(x['passed'] for x in report['checks'] if x['id'] == 'asset.character_views')
    assert not check(base)
    variant = {**base, 'asset_type': 'character_reference', 'asset_id': 'parent__state__changed', 'parent_asset_id': 'parent', 'reference_variant_id': 'changed',
        'reuse_contract': {'mode': 'state_variant', 'derived_from_asset_id': 'parent'}}
    assert check(variant)
    assert not check(variant, include_parent=False)
    assert not check({**variant, 'reference_variant_id': 'unknown'})
    assert not check({**variant, 'asset_id': 'parent'})
    assert not check({**variant, 'parent_asset_id': 'other'})
    assert not check({**variant, 'generation_plan': {'required_views': []}})
    assert check({**base, 'generation_plan': {'required_views': ['front', 'side', 'back']}})


def test_validated_asset_handoff_updates_supervisor_and_only_active_slots(tmp_path):
    from server import image_gen_app as api
    p = tmp_path / 'logs/orchestration/p500.supervisor_result.json'
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({'bucket': 'p500', 'completed_slots': ['p510', 'p540'],
        'state_keys': {'slot.p570.status': 'pending'}}))
    with patch.object(api, '_validate_generated_outputs') as validate:
        api._mark_asset_generation_handoff(tmp_path)
    validate.assert_called_once_with(tmp_path, 'asset')
    data = json.loads(p.read_text())
    assert data['state_keys']['slot.p570.status'] == 'done'
    assert 'p540' not in data['completed_slots']
    assert data['status'] == 'done'


def test_relative_cli_run_path_is_resolved_before_validation(tmp_path, monkeypatch):
    run = tmp_path / 'run'
    run.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('sys.argv', ['verify-pipeline.py', '--run-dir', 'run', '--flow', 'immersive'])
    def check(root, *_):
        assert root == run
        raise RuntimeError('checked before writing reports')
    with patch.object(VERIFY, 'build_report', side_effect=check):
        with pytest.raises(RuntimeError, match='checked before'):
            VERIFY.main()
