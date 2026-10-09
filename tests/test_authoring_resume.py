from unittest.mock import Mock
import pytest
from test_source_first_research import runner
from test_research_author import document


def test_resume_keeps_research_and_state_after_story_failure(tmp_path):
    m = runner()
    research = document()
    research['metadata'] = {'target_duration_seconds': 300, 'duration_plan': m.build_duration_plan(300).to_dict()}
    def author(**kwargs):
        (tmp_path / 'research.md').write_text(m._md_yaml('research', research))
    failed_story = Mock(side_effect=RuntimeError('story stopped'))
    with pytest.raises(RuntimeError, match='story stopped'):
        m.materialize_run('作品名', '原文\n末尾  ', tmp_path, 'p450', research_author_runner=author, story_author_runner=failed_story)
    history = (tmp_path / 'state.txt').read_bytes()
    research_bytes = (tmp_path / 'research.md').read_bytes()
    forbidden_author = Mock(side_effect=AssertionError('research must be reused'))
    with pytest.raises(RuntimeError, match='story stopped'):
        m.materialize_run('作品名', '原文\n末尾  ', tmp_path, 'p450', resume_authoring=True,
            research_author_runner=forbidden_author, story_author_runner=failed_story)
    forbidden_author.assert_not_called()
    assert failed_story.call_count == 2
    assert (tmp_path / 'research.md').read_bytes() == research_bytes
    assert (tmp_path / 'state.txt').read_bytes().startswith(history)


def test_resume_rejects_changed_request_before_mutation(tmp_path):
    m = runner()
    with pytest.raises(RuntimeError):
        m.materialize_run('作品名', '原文', tmp_path, 'p450',
            research_author_runner=Mock(side_effect=RuntimeError('timeout')))
    history = (tmp_path / 'state.txt').read_bytes()
    with pytest.raises(ValueError, match='saved exact create input'):
        m.materialize_run('作品名', '別の原文', tmp_path, 'p450', resume_authoring=True)
    assert (tmp_path / 'state.txt').read_bytes() == history


def test_first_stage_failure_is_retryable_in_same_run(tmp_path):
    m = runner()
    for resume in (False, True):
        with pytest.raises(RuntimeError, match='provider unavailable'):
            m.materialize_run('作品名', '原文', tmp_path, 'p450', resume_authoring=resume,
                research_author_runner=Mock(side_effect=RuntimeError('provider unavailable')))
    assert (tmp_path / 'state.txt').read_text().count('slot.p120.status=failed') >= 2


def test_completed_stage_drift_selects_authoring_even_when_later_files_exist(tmp_path):
    from toc.authoring_resume import needs_authoring_resume
    from toc.p500_resume import PRESERVED_CANONICAL_FILES
    m = runner()
    with pytest.raises(RuntimeError):
        m.materialize_run('作品名', '原文', tmp_path, 'p450',
            research_author_runner=Mock(side_effect=RuntimeError('timeout')))
    for name in PRESERVED_CANONICAL_FILES:
        if not (tmp_path / name).exists():
            (tmp_path / name).write_text('placeholder')
    assert needs_authoring_resume(tmp_path)


@pytest.mark.parametrize('failure', ['research', 'story', 'visual_value', 'cinematic', 'projection'])
def test_every_authoring_boundary_preserves_completed_predecessors(tmp_path, failure):
    from collections import Counter
    from test_toc_immersive_frontend_run import write_test_llm_story
    from test_p400_cinematic_author import write_test_cinematic_direction
    from story_profile_fixture import _story_profile, _build_research
    from toc.visual_planning_contract import bind_visual_value
    m = runner()
    research = _build_research('sample', 'sample', '2026-09-26', _story_profile('sample', 'sample'))
    for source in research['source_inventory']:
        source['url'] = 'https://example.org/' + source['source_id']
    def write_research(**kwargs):
        (tmp_path / 'research.md').write_text(m._md_yaml('research', research))
    def write_visual(*, run_dir):
        story = m.load_structured_document(run_dir / 'story.md')[1]
        raw = {n: (run_dir / f'{n}.md').read_bytes() for n in ('research', 'story')}
        visual = bind_visual_value({'scene_visual_values': [
            {'scene_selector': row['scene_id'], 'notes': []} for row in story['script']['scenes']]}, raw)
        (run_dir / 'visual_value.md').write_text(m._md_yaml('visual', visual))
    calls = Counter()
    def wrapped(name, function):
        def call(*args, **kwargs):
            calls[name] += 1
            if name == failure and calls[name] == 1:
                raise RuntimeError('injected failure')
            return function(*args, **kwargs)
        return call
    callbacks = dict(research_author_runner=wrapped('research', write_research),
        story_author_runner=wrapped('story', write_test_llm_story),
        visual_value_author_runner=wrapped('visual_value', write_visual),
        cinematic_author_runner=wrapped('cinematic', write_test_cinematic_direction))
    m._build_script_and_manifest = wrapped('projection', m._build_script_and_manifest)
    with pytest.raises(RuntimeError, match='injected failure'):
        m.materialize_run('sample', 'sample', tmp_path, 'p450', **callbacks)
    completed = {name: (tmp_path / name).read_bytes() for name in ('research.md', 'story.md', 'visual_value.md') if (tmp_path / name).is_file()}
    history = (tmp_path / 'state.txt').read_bytes()
    m.materialize_run('sample', 'sample', tmp_path, 'p450', resume_authoring=True, **callbacks)
    assert (tmp_path / 'video_manifest.md').is_file()
    assert (tmp_path / 'state.txt').read_bytes().startswith(history)
    for name, content in completed.items():
        assert (tmp_path / name).read_bytes() == content
    for stage in ('research', 'story', 'visual_value', 'cinematic', 'projection'):
        assert calls[stage] == (2 if stage == failure else 1)


def test_invalid_p400_is_routed_back_to_authoring(tmp_path):
    from toc.authoring_resume import needs_authoring_resume
    from toc.p500_resume import PRESERVED_CANONICAL_FILES
    import hashlib, json
    (tmp_path / 'logs/orchestration').mkdir(parents=True)
    (tmp_path / 'logs/orchestration/create_input.json').write_text(json.dumps({
        'schema_version': 'toc.create_input.v1', 'topic': 'sample', 'source': 'sample',
        'source_sha256': hashlib.sha256(b'sample').hexdigest(), 'source_run': None,
        'experience': 'cinematic_story', 'target_duration_seconds': 300}))
    for path in PRESERVED_CANONICAL_FILES:
        (tmp_path / path).write_text('{}')
    assert needs_authoring_resume(tmp_path)


def test_world_walk_resume_rejects_source_change_before_writes(tmp_path, monkeypatch):
    import hashlib, json
    m = runner(); monkeypatch.setattr(m, 'REPO_ROOT', tmp_path)
    source = tmp_path / 'output/source'; source.mkdir(parents=True)
    (source / 'story.md').write_text('changed source')
    run = tmp_path / 'output/walk'; (run / 'logs/orchestration').mkdir(parents=True)
    (run / 'logs/orchestration/create_input.json').write_text(json.dumps({
        'schema_version': 'toc.create_input.v1', 'topic': 'sample', 'source': 'old source',
        'source_sha256': hashlib.sha256(b'old source').hexdigest(), 'source_run': 'output/source',
        'experience': 'world_walk', 'target_duration_seconds': 300}))
    with pytest.raises(ValueError, match='source changed'):
        m.materialize_run('sample', 'old source', run, 'p450', experience='world_walk',
            source_run=source, resume_authoring=True)
    assert not (run / 'state.txt').exists()


def test_broken_script_routes_to_authoring_even_when_manifest_check_passes(tmp_path, monkeypatch):
    from test_all_stage_resume_api import make_run
    from toc.authoring_resume import needs_authoring_resume
    from toc.p500_resume import PRESERVED_CANONICAL_FILES
    from toc.stage_evaluation import pipeline
    run = make_run(tmp_path)
    for name in PRESERVED_CANONICAL_FILES:
        if not (run / name).exists():
            (run / name).write_text('{}')
    (run / 'script.md').write_text('broken script: [')
    monkeypatch.setattr(pipeline, 'check_manifest_single', lambda *args, **kwargs: ({'passed': True}, {}))
    assert needs_authoring_resume(run)
