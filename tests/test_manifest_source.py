import pytest

from toc.manifest_source import ManifestSourceError, manifest_source_sha256


def test_source_hash_ignores_render_overlay_but_detects_authored_change(tmp_path):
    path = tmp_path / "video_manifest.md"
    path.write_text("scenes:\n- scene_id: 1\n  action: walk\n  render_units: []\n")
    original = manifest_source_sha256(path)
    path.write_text("scenes:\n- scene_id: 1\n  action: walk\n  render_units: [{id: new}]\n")
    assert manifest_source_sha256(path) == original
    path.write_text("scenes:\n- scene_id: 1\n  action: run\n  render_units: []\n")
    assert manifest_source_sha256(path) != original


def test_duplicate_source_keys_are_rejected(tmp_path):
    path = tmp_path / "video_manifest.md"
    path.write_text("scenes: []\nscenes: []\n")
    with pytest.raises(ManifestSourceError):
        manifest_source_sha256(path)
