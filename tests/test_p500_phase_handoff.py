import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def module():
    path = Path(__file__).resolve().parents[1] / 'scripts/resume-from-p500.py'
    spec = importlib.util.spec_from_file_location('p500_phase_handoff_cli', path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_verified_skeleton_is_promoted_without_losing_content(tmp_path):
    cli = module()
    path = tmp_path / 'video_manifest.md'
    path.write_text('# Manifest\n\n```yaml\nmanifest_phase: skeleton\nscenes: [{scene_id: 1}]\n```\n\nKeep notes.\n')
    before = cli._load_resume_structured_document(tmp_path, 'video_manifest.md')[1]
    def validate(root):
        assert root == tmp_path
        assert 'manifest_phase: skeleton' in path.read_text()
    frontend = SimpleNamespace(_require_fresh_p400_readiness=Mock(side_effect=validate))
    cli._promote_resumed_manifest(frontend, tmp_path)
    after = cli._load_resume_structured_document(tmp_path, 'video_manifest.md')[1]
    assert after == {**before, 'manifest_phase': 'production'}
    assert path.read_text().endswith('Keep notes.\n')
    frontend._require_fresh_p400_readiness.assert_called_once_with(tmp_path)


def test_invalid_skeleton_is_not_promoted(tmp_path):
    cli = module()
    path = tmp_path / 'video_manifest.md'
    original = '```yaml\nmanifest_phase: skeleton\nscenes: []\n```\n'
    path.write_text(original)
    frontend = SimpleNamespace(_require_fresh_p400_readiness=Mock(side_effect=ValueError('invalid structure')))
    with pytest.raises(ValueError, match='invalid structure'):
        cli._promote_resumed_manifest(frontend, tmp_path)
    assert path.read_text() == original


@pytest.mark.parametrize('phase', ['production', 'unknown'])
def test_other_phases_are_not_rewritten(tmp_path, phase):
    cli = module()
    path = tmp_path / 'video_manifest.md'
    original = f'```yaml\nmanifest_phase: {phase}\nscenes: []\n```\n'
    path.write_text(original)
    frontend = SimpleNamespace(_require_fresh_p400_readiness=Mock())
    if phase == 'unknown':
        with pytest.raises(cli.P500ResumeError, match='manifest phase'):
            cli._promote_resumed_manifest(frontend, tmp_path)
    else:
        cli._promote_resumed_manifest(frontend, tmp_path)
    assert path.read_text() == original
    frontend._require_fresh_p400_readiness.assert_not_called()


def test_materialization_promotes_before_request_generation(tmp_path, monkeypatch):
    cli = module()
    path = tmp_path / 'video_manifest.md'
    path.write_text('```yaml\nmanifest_phase: skeleton\nscenes: [{scene_id: 1}]\n```\n')
    manifest = cli._load_resume_structured_document(tmp_path, 'video_manifest.md')[1]
    monkeypatch.setattr(cli, '_resume_profile', lambda *a, **k: ({}, manifest))
    monkeypatch.setattr(cli, '_resolve_resume_mode_contract', lambda **k: {})
    monkeypatch.setattr(cli, '_preflight_world_walk_reference_restore', lambda **k: ([], {}, None))
    monkeypatch.setattr(cli, '_restore_world_walk_source_references', lambda *a, **k: [])
    monkeypatch.setattr(cli, '_recompile_resumed_image_prompt_payloads', lambda *a: [])
    monkeypatch.setattr(cli, '_resume_state_updates', lambda **k: {})
    events = []
    def requests(root):
        assert cli._load_resume_structured_document(root, 'video_manifest.md')[1]['manifest_phase'] == 'production'
        assert 'validate' in events
        events.append('requests')
    frontend = SimpleNamespace(
        _now_iso=lambda: '2026-10-02T12:00:00+09:00',
        _build_asset_artifacts_from_manifest=lambda **k: ({}, {}),
        _md_yaml=lambda title, data: '```yaml\n{}\n```\n',
        _prepare_authoring_grounding=lambda root: events.append('grounding'),
        _require_fresh_p400_readiness=lambda root: events.append('validate'),
        _write_asset_request_files=lambda *a: None,
        _materialize_standard_request_files=requests,
    )
    cli.materialize_from_p500(frontend, run_dir=tmp_path, topic='sample', source='sample', stop_target='p650')
    assert events == ['grounding', 'validate', 'grounding', 'requests', 'grounding']
