import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from toc.production_repair import RepairSession, RepairExhausted, author_with_repair


def test_error_and_previous_candidate_are_supplied_to_next_author(tmp_path):
    session = RepairSession(tmp_path, 'p330', binding={'source': 'v1'})
    author = AsyncMock(side_effect=[{'notes': ''}, {'notes': ['fixed']}])
    result = asyncio.run(author_with_repair(session, 'scene-1', author,
        lambda doc: ['notes must be a list'] if not isinstance(doc['notes'], list) else []))
    assert result == {'notes': ['fixed']}
    context = author.call_args_list[1].args[0]
    assert context['previous_output'] == {'notes': ''}
    assert context['errors'] == ['notes must be a list']
    assert session.used() == 1


def test_transport_failure_is_not_repaired(tmp_path):
    author = AsyncMock(side_effect=RuntimeError('offline'))
    with pytest.raises(RuntimeError, match='offline'):
        asyncio.run(author_with_repair(RepairSession(tmp_path, 'p330'), 'x', author, lambda d: []))
    assert author.await_count == 1


def test_budget_persists_on_resume(tmp_path):
    a = RepairSession(tmp_path, 'p330', stage_limit=1)
    a.feedback('x', {}, ['invalid'])
    b = RepairSession(tmp_path, 'p330', stage_limit=1)
    with pytest.raises(RepairExhausted):
        b.feedback('x', {'changed': True}, ['still invalid'])


def test_resume_keeps_previous_feedback(tmp_path):
    a = RepairSession(tmp_path, 'p330', binding={'source': 'v1'})
    previous = a.feedback('x', {'notes': ''}, ['notes invalid'])
    b = RepairSession(tmp_path, 'p330', binding={'source': 'v1'})
    assert b.pending('x') == previous
    assert RepairSession(tmp_path, 'p330', binding={'source': 'v2'}).pending('x') is None


def test_repeated_identical_output_stops(tmp_path):
    session = RepairSession(tmp_path, 'p330')
    session.feedback('x', {}, ['invalid'])
    session.feedback('x', {}, ['invalid'])
    with pytest.raises(RepairExhausted, match='no progress'):
        session.feedback('x', {}, ['invalid'])


def test_repair_log_cannot_follow_symlink(tmp_path):
    outside = tmp_path / 'other'; outside.mkdir()
    (tmp_path / 'logs').symlink_to(outside)
    with pytest.raises(Exception):
        RepairSession(tmp_path, 'p330').feedback('x', {}, ['invalid'])
    assert list(outside.iterdir()) == []


def test_media_budget_is_per_item_and_separate_from_authoring(tmp_path):
    media = RepairSession(tmp_path, 'p660', stage_limit=100, run_limit=100, unit_limit=2, budget_group='media')
    media.feedback('one', {}, ['missing'])
    media.feedback('one', {}, ['missing'])
    with pytest.raises(RepairExhausted):
        media.feedback('one', {}, ['missing'])
    media.feedback('two', {}, ['missing'])
    RepairSession(tmp_path, 'p330', run_limit=1).feedback('draft', {}, ['notes invalid'])


def test_restart_cannot_expand_saved_limits(tmp_path):
    RepairSession(tmp_path, 'p330', stage_limit=1).feedback('x', {}, ['invalid'])
    with pytest.raises(RepairExhausted):
        RepairSession(tmp_path, 'p330', stage_limit=999).feedback('y', {}, ['invalid'])


def test_subprocess_only_decodes_typed_validation_exit(monkeypatch):
    import subprocess
    from toc.production_diagnostics import diagnostic_subprocess_run, AuthoringValidationError
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(38, ['tool'], stderr=json.dumps({
            'schema': 'toc.authoring_error.v1', 'owner_stage': 'p420', 'message': 'drawable_prompt_invalid'}))
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(AuthoringValidationError, match='drawable_prompt_invalid'):
        diagnostic_subprocess_run(['tool'], check=True)
    def transport(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ['tool'], stderr='offline')
    monkeypatch.setattr(subprocess, 'run', transport)
    with pytest.raises(subprocess.CalledProcessError):
        diagnostic_subprocess_run(['tool'], check=True)


def test_cancel_does_not_start_a_repair(tmp_path):
    async def cancelled(context):
        raise asyncio.CancelledError()
    session = RepairSession(tmp_path, 'p330')
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(author_with_repair(session, 'x', cancelled, lambda _: ['invalid']))
    assert session.used() == 0


def test_interrupted_submitted_attempt_is_not_free_on_resume(tmp_path):
    session = RepairSession(tmp_path, 'p330', stage_limit=2)
    session.feedback('x', {'notes': ''}, ['invalid'])
    session.claim('x')
    resumed = RepairSession(tmp_path, 'p330')
    assert resumed.claim('x')['attempt'] == 2
    with pytest.raises(RepairExhausted):
        RepairSession(tmp_path, 'p330').claim('x')
