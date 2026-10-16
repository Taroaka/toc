import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from toc.image_adoption import adopt_generated_image, has_current_image_adoption
from toc.image_request_snapshot import materialize_request_snapshot, write_request_snapshot_atomic


def fixture(root):
    (root / 'image_generation_requests.md').write_text('# requests\n')
    source = root / 'assets/scenes/source.png'
    source.parent.mkdir(parents=True)
    Image.new('RGB', (64, 36), (60, 80, 100)).save(source)
    snapshot = materialize_request_snapshot(root, kind='scene', source_artifact='image_generation_requests.md',
        items=[{'item_id': item, 'destination': f'assets/scenes/{item}.png', 'prompt': item + ' scene',
                'prompt_policy_version': 'image_api_prompt_v2', 'compiler_version': 'compiler-test',
                'source_digest': hashlib.sha256(item.encode()).hexdigest(), 'references': []}
               for item in ('source', 'target')])
    write_request_snapshot_atomic(root / 'image_generation_request_snapshot.json', snapshot, run_dir=root)
    item = snapshot.item('source'); sha = hashlib.sha256(source.read_bytes()).hexdigest()
    log = root / 'logs/app_server/image_gen/20260101_000000_native.json'
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({'status': 'completed', 'source': 'app_server', 'itemId': item.item_id,
        'kind': 'scene', 'destination': item.destination, 'outputSha256': sha, 'apiPromptPolicyVersion': item.prompt_policy_version,
        'provenance': {'policy': 'request_bound_v2', 'authoritative': True, 'source': 'app_server',
            'itemId': item.item_id, 'destination': item.destination, 'generationJobId': 'job', 'turnId': 'turn',
            'imageGenerationItemId': 'image', 'imageGenerationItemCount': 1, 'savedPath': '/original/provider.png',
            'outputSha256': sha, 'promptSha256': item.prompt_sha256, 'referenceSha256s': [],
            'requestDigest': item.request_digest, 'compilerVersion': item.compiler_version, 'sourceDigest': item.source_digest}}))
    return snapshot, sha, log


def adopt(root, snapshot, sha, **overrides):
    kwargs = dict(kind='scene', item_id='target', source_kind='scene', source_item_id='source',
        expected_revision=snapshot.request_revision, expected_request_digest=snapshot.item('target').request_digest,
        expected_source_sha256=sha, authorization='Use an existing generated image as replacement.',
        reason='The selected image shows the required resulting state.')
    kwargs.update(overrides)
    return adopt_generated_image(root, **kwargs)


def valid(root, snapshot):
    item = snapshot.item('target')
    return has_current_image_adoption(root, item_id=item.item_id, destination=root / item.destination,
        prompt_sha256=item.prompt_sha256, reference_sha256s=[], request_digest=item.request_digest,
        compiler_version=item.compiler_version, source_digest=item.source_digest)


def test_adoption_is_distinct_from_native_generation_and_idempotent(tmp_path):
    snapshot, sha, log = fixture(tmp_path)
    before = (tmp_path / snapshot.item('source').destination).read_bytes()
    result = adopt(tmp_path, snapshot, sha)
    assert valid(tmp_path, snapshot)
    assert (tmp_path / snapshot.item('source').destination).read_bytes() == before
    assert (tmp_path / snapshot.item('target').destination).read_bytes() == before
    receipt = json.loads((tmp_path / result['receipt']).read_text())
    assert receipt['source'] == 'user_approved_reuse'
    assert receipt['source_binding']['item_id'] == 'source'
    assert receipt['target_binding']['item_id'] == 'target'
    assert receipt['source_receipt'] == log.relative_to(tmp_path).as_posix()
    assert adopt(tmp_path, snapshot, sha)['receipt'] == result['receipt']


@pytest.mark.parametrize('fault', ['source_hash', 'revision', 'digest', 'authorization', 'source_receipt', 'existing_output', 'symlink'])
def test_adoption_rejects_stale_unbound_or_unsafe_inputs(tmp_path, fault):
    snapshot, sha, log = fixture(tmp_path)
    kwargs = {}
    target = tmp_path / snapshot.item('target').destination
    if fault == 'source_hash': kwargs['expected_source_sha256'] = '0' * 64
    elif fault == 'revision': kwargs['expected_revision'] = '0' * 64
    elif fault == 'digest': kwargs['expected_request_digest'] = '0' * 64
    elif fault == 'authorization': kwargs['authorization'] = ''
    elif fault == 'source_receipt': log.unlink()
    elif fault == 'existing_output': target.write_bytes(b'keep this output')
    else: target.symlink_to(tmp_path / snapshot.item('source').destination)
    with pytest.raises((ValueError, FileNotFoundError)):
        adopt(tmp_path, snapshot, sha, **kwargs)
    if fault == 'existing_output': assert target.read_bytes() == b'keep this output'
    assert not valid(tmp_path, snapshot)


@pytest.mark.parametrize('fault', ['output', 'source', 'source_receipt', 'invalidation'])
def test_adoption_validation_rechecks_bytes_and_source_provenance(tmp_path, fault):
    snapshot, sha, log = fixture(tmp_path)
    adopt(tmp_path, snapshot, sha)
    if fault == 'output': (tmp_path / snapshot.item('target').destination).write_bytes(b'changed')
    elif fault == 'source': (tmp_path / snapshot.item('source').destination).write_bytes(b'changed')
    elif fault == 'source_receipt': log.write_text('{}')
    else:
        (log.parent / '99999999_invalidation.json').write_text(json.dumps({'itemId': 'target',
            'destination': snapshot.item('target').destination, 'operation': 'candidate_insertion',
            'status': 'invalidated', 'provenanceInvalidation': True}))
    assert not valid(tmp_path, snapshot)


def test_server_and_pipeline_accept_adoption_without_claiming_native_generation(tmp_path):
    import importlib.util
    from server import image_gen_app as api
    spec = importlib.util.spec_from_file_location('verify_adoption', Path(__file__).parents[1] / 'scripts/verify-pipeline.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    snapshot, sha, _ = fixture(tmp_path)
    item = snapshot.item('target')
    request = dict(item_id=item.item_id, destination=tmp_path / item.destination,
        prompt_sha256=item.prompt_sha256, reference_sha256s=[], request_digest=item.request_digest,
        compiler_version=item.compiler_version, source_digest=item.source_digest)
    assert not api._has_current_image_provenance(tmp_path, **request)
    adopt(tmp_path, snapshot, sha)
    assert not api._has_completed_app_server_image_provenance(tmp_path, **request)
    assert api._has_current_image_provenance(tmp_path, **request)
    assert module._strict_snapshot_provenance_failures(tmp_path, kind='scene') == []
    request['request_digest'] = '0' * 64
    assert not api._has_current_image_provenance(tmp_path, **request)


def test_copy_race_does_not_overwrite_new_destination(tmp_path, monkeypatch):
    from server import image_gen_app as api
    snapshot, sha, _ = fixture(tmp_path)
    target = tmp_path / snapshot.item('target').destination
    real_copy = api._copy_saved_image_to_generation_destination_nofollow
    def race(**kwargs):
        target.write_bytes(b'concurrent output')
        return real_copy(**kwargs)
    monkeypatch.setattr(api, '_copy_saved_image_to_generation_destination_nofollow', race)
    with pytest.raises(api._UnsafeGenerationDestinationError):
        adopt(tmp_path, snapshot, sha)
    assert target.read_bytes() == b'concurrent output'
    assert not valid(tmp_path, snapshot)


def test_adoption_completes_both_current_repair_reservations(tmp_path):
    from toc.production_repair import RepairSession
    snapshot, sha, _ = fixture(tmp_path)
    item = snapshot.item('target')
    base = {'item': item.item_id, 'request': item.request_digest}
    sessions = [RepairSession(tmp_path, 'p660', binding=b, budget_group='media')
                for b in (base, {**base, 'prompt': item.prompt})]
    for session in sessions:
        session.feedback(item.item_id, {'output': item.destination}, ['missing output'])
    ledger_before = sessions[0]._read()
    assert len(ledger_before['pending']) == 2
    adopt(tmp_path, snapshot, sha)
    ledger_after = sessions[0]._read()
    assert ledger_after['pending'] == {}
    assert ledger_after['events'] == ledger_before['events']


def test_retry_finishes_receipt_publication_without_regressing_later_progress(tmp_path, monkeypatch):
    from server import image_gen_app as api
    snapshot, sha, _ = fixture(tmp_path)
    append = api.append_state_snapshot
    def fail(*args, **kwargs):
        raise OSError('interrupted after receipt publication')
    monkeypatch.setattr(api, 'append_state_snapshot', fail)
    with pytest.raises(OSError):
        adopt(tmp_path, snapshot, sha)
    assert valid(tmp_path, snapshot)
    monkeypatch.setattr(api, 'append_state_snapshot', append)
    result = adopt(tmp_path, snapshot, sha)
    state = api.parse_state_file(tmp_path / 'state.txt')
    assert state['human_choice.image.target.receipt'] == result['receipt']
    append(tmp_path / 'state.txt', {'slot.p680.status': 'done'})
    before = (tmp_path / 'state.txt').read_bytes()
    assert adopt(tmp_path, snapshot, sha)['receipt'] == result['receipt']
    assert (tmp_path / 'state.txt').read_bytes() == before
