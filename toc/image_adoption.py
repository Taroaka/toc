"""Explicit reuse of a generated image; never impersonates provider generation."""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import time

from PIL import Image

from scripts.world_walk_source import directory_identity_nofollow, read_regular_file_nofollow
from toc.image_request_snapshot import load_request_snapshot, current_reference_sha256s
from toc.run_root_binding import bind_run_root, write_run_file_text
from toc.runtime_locks import sync_file_lock

SCHEMA = 'toc.image_adoption.v1'
OPERATION = 'user_approved_image_reuse'
SNAPSHOTS = {'scene': 'image_generation_request_snapshot.json', 'asset': 'asset_generation_request_snapshot.json'}
LOG_DIR = 'logs/app_server/image_gen'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read(root, relative):
    return read_regular_file_nofollow(root, relative)


def _relative(root, value):
    path = Path(str(value or ''))
    if path.is_absolute():
        path = path.relative_to(root)
    if not path.parts or '..' in path.parts:
        raise ValueError('unsafe adoption path')
    return path.as_posix()


def _snapshot(root, kind):
    if kind not in SNAPSHOTS:
        raise ValueError('invalid image request kind')
    return load_request_snapshot(root / SNAPSHOTS[kind], run_dir=root, verify_references=True)


def _binding(root, item):
    return {'item_id': item.item_id, 'kind': item.kind, 'destination': item.destination,
        'prompt_sha256': item.prompt_sha256, 'reference_sha256s': list(current_reference_sha256s(root, item)),
        'request_digest': item.request_digest, 'compiler_version': item.compiler_version,
        'source_digest': item.source_digest}


def _logs(root):
    for path in sorted((root / LOG_DIR).glob('*.json'), reverse=True):
        relative = path.relative_to(root).as_posix()
        try:
            raw = _read(root, relative)
            value = json.loads(raw)
            if isinstance(value, dict):
                yield relative, raw, value
        except (OSError, ValueError):
            continue


def _owns(root, payload, item_id, destination):
    try:
        return payload.get('itemId') == item_id and _relative(root, payload.get('destination')) == destination
    except ValueError:
        return False


def _invalidated(payload):
    return (payload.get('provenanceInvalidation') is True
        and payload.get('operation') == 'candidate_insertion' and payload.get('status') == 'invalidated')


def _native_matches(root, payload, item, output_sha):
    if not isinstance(payload, dict):
        return False
    p = payload.get('provenance') or {}
    if not isinstance(p, dict) or not _owns(root, payload, item.item_id, item.destination):
        return False
    if (payload.get('status') not in ('completed', 'succeeded') or payload.get('source') != 'app_server'
            or payload.get('kind') != item.kind or payload.get('apiPromptPolicyVersion') != item.prompt_policy_version
            or p.get('policy') != 'request_bound_v2' or p.get('authoritative') is not True
            or p.get('itemId') != item.item_id or p.get('source') != 'app_server'):
        return False
    if any(not isinstance(p.get(k), str) or not p[k] for k in ('generationJobId', 'turnId', 'imageGenerationItemId', 'savedPath')):
        return False
    if p.get('imageGenerationItemCount') != 1 or _relative(root, p.get('destination')) != item.destination:
        return False
    expected = {'outputSha256': output_sha, 'promptSha256': item.prompt_sha256,
        'referenceSha256s': list(current_reference_sha256s(root, item)),
        'requestDigest': item.request_digest, 'compilerVersion': item.compiler_version, 'sourceDigest': item.source_digest}
    return payload.get('outputSha256') == output_sha and all(p.get(k) == v for k, v in expected.items())


def _native_receipt(root, item, output_sha):
    for relative, raw, payload in _logs(root):
        if not _owns(root, payload, item.item_id, item.destination):
            continue
        if _invalidated(payload):
            return None
        try:
            if _native_matches(root, payload, item, output_sha):
                return relative, _sha(raw)
        except (OSError, ValueError, TypeError):
            continue
    return None


def _current_adoption(root, expected):
    for relative, _raw, payload in _logs(root):
        if not _owns(root, payload, expected['item_id'], expected['destination']):
            continue
        if _invalidated(payload):
            return None
        if payload.get('operation') != OPERATION:
            continue
        try:
            if (payload.get('schema_version') != SCHEMA or payload.get('source') != 'user_approved_reuse'
                    or payload.get('status') != 'completed' or payload.get('actor') != 'user'
                    or not payload.get('authorization') or not payload.get('reason')):
                return None
            target = payload['target_binding']
            if any(target.get(k) != v for k, v in expected.items()):
                return None
            # Collection revision may change for unrelated items. The complete
            # current per-item binding remains mandatory, like native receipts.
            source = payload['source_binding']
            current = _snapshot(root, source['kind']).item(source['item_id'])
            if source != _binding(root, current) or current.destination == expected['destination']:
                return None
            output_sha = _sha(_read(root, expected['destination']))
            if output_sha != payload['outputSha256'] or output_sha != _sha(_read(root, current.destination)):
                return None
            receipt_path = payload['source_receipt']
            if not receipt_path.startswith(LOG_DIR + '/'):
                return None
            receipt = _read(root, receipt_path)
            if _sha(receipt) != payload['source_receipt_sha256']:
                return None
            if not _native_matches(root, json.loads(receipt), current, output_sha):
                return None
            if not _native_receipt(root, current, output_sha):
                return None
            return {**payload, 'receipt': relative}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
    return None


def has_current_image_adoption(run_dir, *, item_id, destination, prompt_sha256, reference_sha256s,
                               request_revision=None, request_digest=None, compiler_version=None, source_digest=None):
    del request_revision
    root = Path(os.path.abspath(run_dir))
    if not all(isinstance(v, str) and v for v in (request_digest, compiler_version, source_digest)):
        return False
    try:
        return _current_adoption(root, {'item_id': item_id, 'destination': _relative(root, destination),
            'prompt_sha256': prompt_sha256, 'reference_sha256s': list(reference_sha256s),
            'request_digest': request_digest, 'compiler_version': compiler_version, 'source_digest': source_digest}) is not None
    except (OSError, ValueError, TypeError):
        return False


def adopt_generated_image(run_dir, *, kind, item_id, source_kind, source_item_id, expected_revision,
                          expected_request_digest, expected_source_sha256, authorization, reason):
    """User-directed, same-run reuse into a missing or byte-identical output."""
    from server import image_gen_app as api
    root = Path(os.path.abspath(run_dir))
    for value in (authorization, reason):
        if not isinstance(value, str) or not value.strip() or len(value) > 8000:
            raise ValueError('explicit adoption authorization and reason are required')
    identity = directory_identity_nofollow(root)
    with bind_run_root(root, expected_identity=identity) as binding, ExitStack() as locks:
        for name in ('create_resume', 'run_artifacts', 'asset_request_revision', 'scene_request_revision'):
            locks.enter_context(sync_file_lock(root / '.locks' / (name + '.lock'), timeout_seconds=10,
                run_root_descriptor=binding.descriptor, expected_run_root_identity=binding.identity))
        snapshot = _snapshot(root, kind)
        target = snapshot.item(item_id)
        source = _snapshot(root, source_kind).item(source_item_id)
        if snapshot.request_revision != expected_revision or target.request_digest != expected_request_digest:
            raise ValueError('target image request revision conflict')
        if source.destination == target.destination:
            raise ValueError('source and target must be different images')
        data = _read(root, source.destination)
        source_sha = _sha(data)
        if source_sha != expected_source_sha256:
            raise ValueError('source image hash changed')
        from io import BytesIO
        with Image.open(BytesIO(data)) as image:
            image.verify()
        source_receipt = _native_receipt(root, source, source_sha)
        if not source_receipt:
            raise ValueError('source image lacks current native provenance')
        expected = _binding(root, target)
        source_binding = _binding(root, source)
        prior = _current_adoption(root, expected)
        if prior and prior['source_binding'] == source_binding:
            _reconcile_adoption_state(root, target, source, prior['receipt'], prior['adopted_at'])
            return {'status': 'adopted', 'receipt': prior['receipt'], 'output': target.destination, 'sha256': source_sha}
        try:
            existing = _read(root, target.destination)
        except FileNotFoundError:
            existing = None
        if existing is not None and _sha(existing) != source_sha:
            raise ValueError('refusing to overwrite a different existing image')
        if existing is None:
            copied = api._copy_saved_image_to_generation_destination_nofollow(run_dir=root,
                saved_path=root / source.destination, output=target.destination, kind=kind, require_absent=True)
            if copied.output_sha256 != source_sha:
                raise ValueError('source image changed during adoption copy')
        # Verify both requests again before publication. A copied file alone is
        # never an adopted output; interrupted work remains fail-closed.
        if (_snapshot(root, kind).request_revision != expected_revision
                or _binding(root, _snapshot(root, kind).item(item_id)) != expected
                or _binding(root, _snapshot(root, source_kind).item(source_item_id)) != source_binding
                or _sha(_read(root, source_receipt[0])) != source_receipt[1]
                or not _native_receipt(root, source, source_sha)
                or _sha(_read(root, source.destination)) != source_sha
                or _sha(_read(root, target.destination)) != source_sha):
            raise ValueError('image adoption inputs changed before publication')
        receipt = {'schema_version': SCHEMA, 'operation': OPERATION, 'status': 'completed',
            'source': 'user_approved_reuse', 'actor': 'user', 'authorization': authorization, 'reason': reason,
            'itemId': item_id, 'kind': kind, 'destination': target.destination, 'outputSha256': source_sha,
            'target_request_revision': expected_revision, 'target_binding': expected,
            'source_binding': source_binding, 'source_receipt': source_receipt[0],
            'source_receipt_sha256': source_receipt[1], 'adopted_at': api.now_iso()}
        path = f'{LOG_DIR}/{time.strftime("%Y%m%d_%H%M%S")}_{time.time_ns()}_adoption.json'
        write_run_file_text(root, path, json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
        _reconcile_adoption_state(root, target, source, path, receipt['adopted_at'])
        return {'status': 'adopted', 'receipt': path, 'output': target.destination, 'sha256': source_sha}


def _reconcile_adoption_state(root, target, source, receipt_path, adopted_at):
    """Finish a partially published adoption without resetting later progress."""
    from server import image_gen_app as api
    from toc.production_repair import RepairSession

    base = {'item': target.item_id, 'request': target.request_digest}
    # Native generation and its outer output-check repair use distinct keys.
    # Complete only these exact current-item reservations; retain all budgets.
    for repair_binding in (base, {**base, 'prompt': target.prompt}):
        repair = RepairSession(root, 'p560' if target.kind == 'asset' else 'p660',
            binding=repair_binding, stage_limit=100000, run_limit=100000,
            unit_limit=2, budget_group='media')
        repair.complete(target.item_id)
    prefix = f'human_choice.image.{target.item_id}'
    state = api.parse_state_file(root / 'state.txt')
    if state.get(prefix + '.receipt') == receipt_path:
        return
    api.append_state_snapshot(root / 'state.txt', {prefix + '.status': 'selected', prefix + '.actor': 'user',
        prefix + '.at': adopted_at, prefix + '.path': target.destination,
        prefix + '.source_path': source.destination, prefix + '.sha256': _sha(_read(root, target.destination)),
        prefix + '.receipt': receipt_path, 'runtime.stage': 'image_adopted_requires_revalidation',
        'slot.p670.status': 'pending', 'slot.p680.status': 'pending', 'last_error': ''})
