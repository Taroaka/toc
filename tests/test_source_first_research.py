"""Regression tests: research must never receive a preselected story."""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def runner():
    spec = importlib.util.spec_from_file_location('source_first_runner', ROOT / 'scripts/toc-immersive-frontend-run.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_initial_profile_contains_no_narrative_decisions():
    m = runner()
    for seed in ('one', 'two'):
        profile = m._story_profile('作品名', '作品名', seed)
        for field in ('events', 'summary', 'motifs', 'places', 'scene_titles', 'artifact_name', 'protagonist_name'):
            assert not profile.get(field), (field, profile.get(field))
    assert not hasattr(m, 'RUN_VARIANTS')
    assert not hasattr(m, '_run_variant')
    assert not hasattr(m, '_build_research')


def test_research_failure_stops_before_story_or_synthetic_output(tmp_path):
    m = runner()
    source = 'ユーザーの原文。\n改行と空白をそのまま渡す。  \n'
    calls = []
    def research_author(**kwargs):
        calls.append(kwargs)
        assert not (tmp_path / 'research.md').exists()
        assert set(kwargs) == {'run_dir', 'topic', 'source', 'target_duration_seconds'}
        raise RuntimeError('research retrieval unavailable')
    story_author = Mock()
    with pytest.raises(RuntimeError, match='research retrieval unavailable'):
        m.materialize_run('作品名', source, tmp_path, 'p680', research_author_runner=research_author, story_author_runner=story_author)
    assert calls[0]['source'] == source
    story_author.assert_not_called()
    assert not (tmp_path / 'research.md').exists()
    assert not (tmp_path / 'script.md').exists()


def test_research_projection_uses_supplied_material_only():
    m = runner()
    research = {'story_materials': {
        'canonical_story_dump': '橋の修復を巡る物語。',
        'chronological_events': [{'event_id': 'E9', 'event': '橋を修復する。'}],
        'characters': [{'character_id': 'protagonist', 'name': '修理工', 'role': '主人公'}],
        'setting': {'places': ['川岸'], 'time_or_era': '近代'},
        'symbols_and_themes': [{'item_id': 'O1', 'kind': 'object', 'item': '修理道具', 'meaning': '技術を継ぐ'}],
    }, 'source_passages': []}
    p = m._profile_from_research(m._story_profile('作品名', '作品名'), research)
    assert p['events'] == ['橋を修復する。']
    assert p['places'] == ['川岸']
    assert p['artifact_name'] == '修理道具'
    assert p['protagonist_name'] == '修理工'
    assert p['summary'] == '橋の修復を巡る物語。'
    assert p['motifs'] == ['修理道具']


def test_authored_research_reaches_story_without_synthetic_replacement(tmp_path):
    import json
    from test_research_author import document
    m = runner()
    authored = document()
    authored['metadata'] = {'target_duration_seconds': 300, 'duration_plan': m.build_duration_plan(300).to_dict()}
    def research_author(**kwargs):
        (tmp_path / 'research.md').write_text(m._md_yaml('authored research', authored))
    def story_author(**kwargs):
        assert m.load_structured_document(tmp_path / 'research.md')[1] == authored
        raise RuntimeError('story boundary reached')
    with pytest.raises(RuntimeError, match='story boundary reached'):
        m.materialize_run('作品名', '作品名', tmp_path, 'p680', research_author_runner=research_author, story_author_runner=story_author)
    state = json.loads((tmp_path / 'run_status.json').read_text())['state_flat']
    assert state['slot.p120.status'] == 'done'
    assert not (tmp_path / 'script.md').exists()


@pytest.mark.parametrize('authored', [{}, {'story_materials': {}}, {'topic': 'different', 'metadata': {'target_duration_seconds': 999}}])
def test_research_without_content_or_duration_contract_reaches_story(tmp_path, authored):
    m = runner()
    story = Mock(side_effect=RuntimeError('story boundary reached'))
    def research_author(**kwargs):
        (tmp_path / 'research.md').write_text(m._md_yaml('authored', authored))
    with pytest.raises(RuntimeError, match='story boundary reached'):
        m.materialize_run('作品名', '作品名', tmp_path, 'p680', research_author_runner=research_author, story_author_runner=story)
    story.assert_called_once()
    assert 'slot.p120.status=done' in (tmp_path / 'state.txt').read_text()


def test_research_subprocess_receives_exact_source_file(tmp_path):
    from unittest.mock import patch
    m = runner();(tmp_path / 'logs/orchestration').mkdir(parents=True)
    source = '原文の $記号 と改行\n末尾の空白  '
    with patch.object(m, '_run_materialization_subprocess') as call:
        m._author_research_with_codex(run_dir=tmp_path, topic='作品名', source=source, target_duration_seconds=600)
    argv = call.call_args.args[1]
    assert argv[1].endswith('author-research-with-codex.py')
    path = Path(argv[argv.index('--source-file') + 1])
    assert path.read_text() == source
    assert source not in argv


def test_abstract_research_theme_is_not_a_preselected_prop():
    m = runner()
    research = {'story_materials': {'symbols_and_themes': [{'kind': 'theme', 'item': '自由'}]}}
    p = m._profile_from_research(m._story_profile('作品名', '作品名'), research)
    assert p['artifact_name'] == ''
    assert p['artifact_scene_indices'] == []


@pytest.mark.parametrize('text', ['```yaml\n{}\n```\n', 'LLM-authored research without structured fields'])
def test_pipeline_inspection_does_not_validate_research_content(tmp_path, text):
    from toc.stage_evaluation.pipeline import check_research
    (tmp_path / 'research.md').write_text(text)
    report, _ = check_research(tmp_path)
    assert report['passed'] is True
    assert [check['id'] for check in report['checks']] == ['research.file_exists']
