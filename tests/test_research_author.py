import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from toc.research_author import build_research_prompt, validate_research_document, author_research


def document():
    return {
        'topic': '作品名',
        'story_materials': {
            'canonical_story_dump': '灯台を直す物語。',
            'chronological_events': [{'event_id': 'E1', 'event': '灯台を直す。', 'sources': ['S1']}],
            'characters': [{'character_id': 'protagonist', 'name': '灯台守', 'role': '主人公'}],
            'setting': {'places': ['灯台'], 'time_or_era': ''},
        },
        'source_inventory': [{'source_id': 'S1', 'title': '原文', 'url': 'https://example.org/source'}],
        'source_passages': [{'passage_id': 'P1', 'source_id': 'S1', 'passage': '灯台を直す。'}],
        'handoff_to_story': {'must_preserve': ['灯台を直す。']},
    }


def test_prompt_has_exact_source_and_no_narrative_profile():
    source = '第一行。\n第二行。  '
    prompt = build_research_prompt(topic='作品名', source=source, grounding='canonical research instructions')
    assert json.dumps(source, ensure_ascii=False) in prompt
    assert 'canonical research instructions' in prompt
    assert 'RUN_VARIANTS' not in prompt
    assert '小さな鍵' not in prompt
    assert '信頼度を固定値' in prompt


def test_title_only_requires_retrieved_real_source_not_fake_tradition():
    doc = document()
    assert validate_research_document(doc, topic='作品名', source='作品名', retrieved_urls={'https://example.org/source'}) == []
    assert 'research.external_source_not_retrieved' in validate_research_document(doc, topic='作品名', source='作品名', retrieved_urls=set())
    doc['source_inventory'][0]['url'] = 'request-derived-tradition'
    assert validate_research_document(doc, topic='作品名', source='作品名', retrieved_urls=set())


@pytest.mark.parametrize('change', ['duplicate_event', 'missing_source', 'empty_story', 'empty_passages'])
def test_research_structure_fails_closed(change):
    doc = document()
    if change == 'duplicate_event': doc['story_materials']['chronological_events'] *= 2
    if change == 'missing_source': doc['story_materials']['chronological_events'][0]['sources'] = ['MISSING']
    if change == 'empty_story': doc['story_materials']['canonical_story_dump'] = ''
    if change == 'empty_passages': doc['source_passages'] = []
    assert validate_research_document(doc, topic='作品名', source='作品名', retrieved_urls={'https://example.org/source'})


def test_original_source_evidence_must_match_exact_input():
    doc = document();doc['source_inventory'][0]['url'] = 'request:source'
    assert validate_research_document(doc, topic='作品名', source='灯台を直す。', retrieved_urls=set()) == []
    assert validate_research_document(doc, topic='作品名', source='別の内容。', retrieved_urls=set())


def result(doc):
    return SimpleNamespace(payload={'result_json': json.dumps(doc)}, transcript=({'method': 'item/completed', 'params': {'item': {'type': 'webSearch', 'action': {'type': 'openPage', 'url': 'https://example.org/source'}}}},), provenance=SimpleNamespace(as_dict=lambda: {'model': 'test', 'thread_id': 'test'}))


def test_author_publishes_validated_output_with_technical_duration_only(tmp_path):
    turn = AsyncMock(return_value=result(document()))
    data = asyncio.run(author_research(run_dir=tmp_path, topic='作品名', source='作品名', target_duration_seconds=600, grounding='instructions', client_factory=lambda: None, turn_runner=turn))
    assert (tmp_path / 'research.md').is_file()
    assert data['story_materials'] == document()['story_materials']
    assert data['metadata']['target_duration_seconds'] == 600
    assert 'confidence_score' not in data['metadata']
    assert (tmp_path / 'logs/authoring/research/transcript.json').is_file()


def test_author_failure_does_not_publish_synthetic_research(tmp_path):
    turn = AsyncMock(side_effect=RuntimeError('transport unavailable'))
    with pytest.raises(RuntimeError, match='transport unavailable'):
        asyncio.run(author_research(run_dir=tmp_path, topic='作品名', source='作品名', target_duration_seconds=300, grounding='instructions', client_factory=lambda: None, turn_runner=turn))
    assert not (tmp_path / 'research.md').exists()


def test_invalid_author_result_does_not_replace_existing_research(tmp_path):
    path = tmp_path / 'research.md';path.write_text('previous authored source')
    doc = document();doc['source_inventory'][0]['url'] = 'run-request'
    with pytest.raises(RuntimeError, match='research'):
        asyncio.run(author_research(run_dir=tmp_path, topic='作品名', source='作品名', target_duration_seconds=300, grounding='instructions', client_factory=lambda: None, turn_runner=AsyncMock(return_value=result(doc))))
    assert path.read_text() == 'previous authored source'


def test_claimed_urls_in_final_message_do_not_count_as_retrieval():
    from toc.research_author import retrieved_source_urls
    assert retrieved_source_urls([{'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'text': 'https://example.org/source'}}}]) == set()


def test_research_client_enables_web_search_without_writes():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'scripts/author-research-with-codex.py'
    spec = importlib.util.spec_from_file_location('research_cli', path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    client = SimpleNamespace(start=AsyncMock(), start_thread=AsyncMock(return_value='thread'), run_turn=AsyncMock(return_value=[]), stop=AsyncMock())
    adapter = module.ResearchClient(client)
    async def exercise():
        await adapter.start()
        await adapter.start_thread(sandbox='read-only', approval_policy='never')
        await adapter.run_turn(prompt='test')
        await adapter.stop()
    asyncio.run(exercise())
    client.start_thread.assert_awaited_once_with(sandbox='read-only', approval_policy='never', config={'web_search': 'live'})
    client.stop.assert_awaited_once()


def test_research_publish_rejects_symlinked_log_directory(tmp_path):
    other = tmp_path / 'other';other.mkdir()
    (tmp_path / 'logs').symlink_to(other, target_is_directory=True)
    with pytest.raises(Exception):
        asyncio.run(author_research(run_dir=tmp_path, topic='作品名', source='作品名', target_duration_seconds=300, grounding='instructions', client_factory=lambda: None, turn_runner=AsyncMock(return_value=result(document()))))
    assert not (tmp_path / 'research.md').exists()
    assert list(other.iterdir()) == []


def test_real_grounding_reads_research_docs_without_story_preset(tmp_path):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'scripts/author-research-with-codex.py'
    spec = importlib.util.spec_from_file_location('research_cli_grounding', path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    grounding = module.prepare_grounding(tmp_path)
    assert 'docs/information-gathering.md' in grounding
    assert 'workflow/research-template.production.yaml' in grounding
    assert 'RUN_VARIANTS' not in grounding
    assert 'request-derived-tradition' not in grounding


def test_wrong_topic_and_url_only_input_cannot_be_used_as_original_story():
    doc = document();doc['topic'] = '別の作品'
    assert 'research.topic_mismatch' in validate_research_document(doc, topic='作品名', source='作品名', retrieved_urls={'https://example.org/source'})
    doc = document();doc['source_inventory'][0]['url'] = 'request:source';doc['source_passages'][0]['passage'] = 'https://example.org/source'
    assert validate_research_document(doc, topic='作品名', source='https://example.org/source', retrieved_urls=set())
