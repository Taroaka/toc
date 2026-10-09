"""Exercise the actual authoring orchestrator with deterministic author/provider seams."""
from collections import Counter
from pathlib import Path

import pytest

from test_source_first_research import runner
from test_toc_immersive_frontend_run import write_test_llm_story
from test_p400_cinematic_author import write_test_cinematic_direction
from story_profile_fixture import _story_profile, _build_research
from toc.visual_planning_contract import bind_visual_value
from toc.production_repair import handoff_session
from toc.production_diagnostics import AuthoringValidationError


def setup_authors(m, root, failure):
    calls = Counter()
    research = _build_research('sample', 'sample', '2026-09-26', _story_profile('sample', 'sample'))
    def research_author(**kwargs):
        calls['research'] += 1
        (root / 'research.md').write_text(m._md_yaml('research', research))
    def story_author(**kwargs):
        calls['story'] += 1
        if calls['story'] > 1:
            context = handoff_session(root, 'p220').pending('handoff')
            assert context and 'previous_output' in context and context['errors']
        write_test_llm_story(**kwargs)
        if failure == 'story' and calls['story'] == 1:
            doc = m.load_structured_document(root / 'story.md')[1]
            doc['script']['scenes'][0]['time_of_day_visual_basis'] = '暗い'
            (root / 'story.md').write_text(m._md_yaml('story', doc))
    def visual_author(*, run_dir):
        calls['visual'] += 1
        story = m.load_structured_document(root / 'story.md')[1]
        raw = {key: (root / f'{key}.md').read_bytes() for key in ('research', 'story')}
        doc = bind_visual_value({'scene_visual_values': [{'scene_selector': row['scene_id'], 'notes': []}
            for row in story['script']['scenes']]}, raw)
        if failure == 'visual' and calls['visual'] == 1:
            doc['scene_visual_values'].pop()
        elif failure == 'visual':
            assert 'scene_coverage' in str(handoff_session(root, 'p330').pending('handoff'))
        (root / 'visual_value.md').write_text(m._md_yaml('visual', doc))
    def cinematic_author(**kwargs):
        calls['cinematic'] += 1
        if failure == 'projection' and calls['cinematic'] > 1:
            assert 'drawable_prompt' in str(handoff_session(root, 'p420').pending('handoff'))
        write_test_cinematic_direction(**kwargs)
    if failure == 'projection':
        original = m._build_script_and_manifest
        def build(*args, **kwargs):
            calls['projection'] += 1
            if calls['projection'] == 1:
                raise AuthoringValidationError('drawable_prompt_unresolved_alternative:または')
            return original(*args, **kwargs)
        m._build_script_and_manifest = build
    return calls, dict(research_author_runner=research_author, story_author_runner=story_author,
        visual_value_author_runner=visual_author, cinematic_author_runner=cinematic_author)


@pytest.mark.parametrize('failure', ['story', 'visual', 'projection'])
def test_one_create_repairs_and_reaches_p450_without_restarting_upstream(tmp_path, failure):
    m = runner()
    calls, authors = setup_authors(m, tmp_path, failure)
    m.materialize_run('sample', 'sample', tmp_path, 'p450', **authors)
    assert calls['research'] == 1
    assert calls['story'] == (2 if failure == 'story' else 1)
    assert calls['visual'] == (2 if failure == 'visual' else 1)
    assert calls['cinematic'] == (2 if failure == 'projection' else 1)
    assert (tmp_path / 'video_manifest.md').is_file()
    state = (tmp_path / 'state.txt').read_text()
    assert 'runtime.repair.phase=repairing' in state
    assert 'status=FAILED' not in state


def test_creation_reaches_p680_with_author_and_image_repair(tmp_path, monkeypatch):
    import asyncio
    import hashlib
    from PIL import Image
    from server import image_gen_app as app
    from server.codex_app_server import ImageGenerationResult
    from unittest.mock import AsyncMock
    m = runner()
    root = tmp_path / 'output' / 'auto_repair'
    root.mkdir(parents=True)
    calls, authors = setup_authors(m, root, 'projection')
    generated = tmp_path / 'provider.png'
    Image.new('RGB', (64, 64), (40, 80, 120)).save(generated)
    attempts = Counter()
    class Provider:
        def __init__(self, **kwargs): pass
        async def start(self): pass
        async def stop(self): pass
        async def generate_image(self, **kwargs):
            item_id = str(kwargs['item_id'])
            attempts[item_id] += 1
            saved = None if len(attempts) == 1 and attempts[item_id] == 1 else generated
            return ImageGenerationResult(saved_path=saved, revised_prompt=None, status='completed', transcript=[],
                source='app_server', provenance_authoritative=True, turn_id=f'turn-{item_id}-{attempts[item_id]}',
                generation_job_id=str(kwargs['generation_job_id']), item_id=item_id,
                prompt_sha256=hashlib.sha256(str(kwargs['prompt']).encode()).hexdigest(),
                reference_sha256s=[hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in kwargs['reference_images']],
                image_generation_item_id=f'image-{item_id}', image_generation_item_count=1,
                destination=str(kwargs['output_path']), provenance_policy='request_bound_v2')
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, 'create_codex_app_server_client', Provider)
    job_updates = AsyncMock()
    monkeypatch.setattr(app, '_set_create_job', job_updates)
    monkeypatch.setattr(app, '_sync_process_current_process', AsyncMock())
    async def cli_helper(**kwargs):
        m.materialize_run('sample', 'sample', root, 'p680', **authors)
        m.prepare_grounding(root)
        assert await app._generate_create_images('job', run_id=root.name)
    monkeypatch.setattr(app, '_run_toc_immersive_frontend_cli_helper', cli_helper)
    asyncio.run(app._run_create_job('job', title='sample', source='sample', run_id=root.name))
    patches = [call.args[1] for call in job_updates.call_args_list]
    assert any(patch.get('status') == 'completed' for patch in patches), patches
    assert all(patch.get('status') != 'failed' for patch in patches), patches
    app._validate_frontend_create_run(root.name)
    assert calls['cinematic'] == 2
    assert list(attempts.values()).count(2) == 1
    assert all(n in {1, 2} for n in attempts.values())
    assert 'slot.p680.status=done' in (root / 'state.txt').read_text()
