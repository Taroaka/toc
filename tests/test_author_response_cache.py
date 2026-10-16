import json
from pathlib import Path

import pytest

from toc.story_author_runtime import STORY_AUTHOR_TRANSPORT_SCHEMA, _sha256_json, _sha256_text


def logged_turn(root):
    folder = root / 'logs/authoring/p400'
    folder.mkdir(parents=True)
    payload = {'result_json': '{"items":[{"name":"本文"]},"kept":true}'}
    response = json.dumps(payload, ensure_ascii=False)
    transcript = [{'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'text': response}}}]
    provenance = {'schema_version': 'story_author_runtime_provenance_v1', 'model': 'gpt-6-astra',
        'thread_id': 'saved-thread', 'cwd': str(root.resolve()), 'sandbox': 'read-only', 'approval_policy': 'never',
        'prompt_sha256': _sha256_text('bound prompt'), 'output_schema_sha256': _sha256_json(STORY_AUTHOR_TRANSPORT_SCHEMA),
        'response_sha256': _sha256_text(response), 'payload_sha256': _sha256_json(payload),
        'transcript_sha256': _sha256_json(transcript)}
    (folder / '0001-provenance-saved.json').write_text(json.dumps(provenance))
    (folder / '0002-transcript-saved.json').write_text(json.dumps(transcript))
    return folder, payload, provenance, transcript


def test_completed_turn_is_replayed_with_original_payload_and_provenance(tmp_path):
    from toc.author_response_cache import replay_recorded_turn
    folder, payload, provenance, transcript = logged_turn(tmp_path)
    result = replay_recorded_turn(tmp_path, Path('logs/authoring/p400'), prompt='bound prompt',
        schema=STORY_AUTHOR_TRANSPORT_SCHEMA, model='gpt-6-astra')
    assert result.payload == payload
    assert result.provenance.as_dict() == provenance
    assert list(result.transcript) == transcript


@pytest.mark.parametrize('change', ['prompt', 'model', 'schema', 'transcript', 'payload_hash', 'cwd'])
def test_changed_request_or_tampered_response_is_not_replayed(tmp_path, change):
    from toc.author_response_cache import replay_recorded_turn
    folder, payload, provenance, transcript = logged_turn(tmp_path)
    prompt, model, schema = 'bound prompt', 'gpt-6-astra', STORY_AUTHOR_TRANSPORT_SCHEMA
    if change == 'prompt': prompt = 'changed prompt'
    if change == 'model': model = 'gpt-6-luna'
    if change == 'schema': schema = {'type': 'object'}
    if change == 'transcript':
        transcript[0]['params']['item']['text'] = '{"result_json":"{}"}'
        (folder / '0002-transcript-saved.json').write_text(json.dumps(transcript))
    if change == 'payload_hash': provenance['payload_sha256'] = 'bad'
    if change == 'cwd': provenance['cwd'] = str(tmp_path.parent)
    (folder / '0001-provenance-saved.json').write_text(json.dumps(provenance))
    assert replay_recorded_turn(tmp_path, Path('logs/authoring/p400'), prompt=prompt, schema=schema, model=model) is None
