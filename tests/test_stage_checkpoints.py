from pathlib import Path
import pytest

from toc.stage_checkpoints import StageCheckpoints


def test_checkpoint_requires_completed_output_and_current_input(tmp_path):
    (tmp_path / 'input.md').write_text('source')
    checkpoints = StageCheckpoints(tmp_path, {'duration': 300})
    assert not checkpoints.reusable('research', ['input.md'], ['research.md'])
    (tmp_path / 'research.md').write_text('verified research')
    checkpoints.complete('research', ['input.md'], ['research.md'])
    assert checkpoints.reusable('research', ['input.md'], ['research.md'])
    (tmp_path / 'input.md').write_text('changed')
    assert not checkpoints.reusable('research', ['input.md'], ['research.md'])


def test_output_drift_and_configuration_change_invalidate(tmp_path):
    (tmp_path / 'story.md').write_text('story')
    checkpoints = StageCheckpoints(tmp_path, {'duration': 300})
    checkpoints.complete('story', [], ['story.md'])
    assert not StageCheckpoints(tmp_path, {'duration': 600}).reusable('story', [], ['story.md'])
    (tmp_path / 'story.md').write_text('edited')
    assert not checkpoints.reusable('story', [], ['story.md'])


def test_failed_retry_cannot_reuse_previous_receipt(tmp_path):
    (tmp_path / 'research.md').write_text('research')
    checkpoints = StageCheckpoints(tmp_path, {})
    checkpoints.complete('research', [], ['research.md'])
    checkpoints.start('research', [], ['research.md'])
    assert not checkpoints.reusable('research', [], ['research.md'])


def test_checkpoint_rejects_symlinks_and_traversal(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + '-outside')
    outside.write_text('do not read')
    (tmp_path / 'research.md').symlink_to(outside)
    checkpoints = StageCheckpoints(tmp_path, {})
    with pytest.raises((ValueError, OSError)):
        checkpoints.complete('research', [], ['research.md'])
    with pytest.raises(ValueError):
        checkpoints.complete('../escape', [], ['research.md'])


def test_missing_or_corrupt_receipt_does_not_adopt_unverified_files(tmp_path):
    (tmp_path / 'research.md').write_text('unverified')
    checkpoints = StageCheckpoints(tmp_path, {})
    assert not checkpoints.reusable('research', [], ['research.md'])
    checkpoints.start('research', [], ['research.md'])
    (tmp_path / 'logs/checkpoints/research.json').write_text('{')
    assert not checkpoints.reusable('research', [], ['research.md'])
