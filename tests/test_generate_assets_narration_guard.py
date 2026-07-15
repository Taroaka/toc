from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"
SPEC = importlib.util.spec_from_file_location("generate_assets_narration_guard", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_detects_revision_aware_cut_narration() -> None:
    yaml_text = """
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        audio:
          narration:
            revision:
              schema_version: narration_revision_v1
"""

    assert MODULE._manifest_has_revision_aware_narration(yaml_text) is True


def test_legacy_narration_does_not_trigger_revision_audio_guard() -> None:
    yaml_text = """
scenes:
  - scene_id: 1
    audio:
      narration:
        text: legacy
"""

    assert MODULE._manifest_has_revision_aware_narration(yaml_text) is False


def test_detects_scene_level_revision_when_cuts_array_is_empty() -> None:
    yaml_text = """
scenes:
  - scene_id: 1
    cuts: []
    audio:
      narration:
        revision:
          schema_version: narration_revision_v1
"""

    assert MODULE._manifest_has_revision_aware_narration(yaml_text) is True


def test_deleted_or_reference_revision_does_not_trigger_audio_guard() -> None:
    yaml_text = """
scenes:
  - scene_id: 0
    kind: character_reference
    audio:
      narration:
        revision:
          schema_version: narration_revision_v1
  - scene_id: 1
    cuts:
      - cut_id: 1
        status: deleted
        audio:
          narration:
            revision:
              schema_version: narration_revision_v1
      - cut_id: 2
        scene_kind: location_reference
        audio:
          narration:
            revision:
              schema_version: narration_revision_v1
      - cut_id: 3
        audio:
          narration:
            text: legacy active narration
"""

    assert MODULE._manifest_has_revision_aware_narration(yaml_text) is False


def test_video_render_targets_reject_reversed_canonical_cut_order() -> None:
    yaml_text = """
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
      - cut_id: 2
    render_units:
      - unit_id: 1
        source_cut_ids: [2]
        video_generation:
          output: assets/videos/scene1_cut2.mp4
      - unit_id: 2
        source_cut_ids: [1]
        video_generation:
          output: assets/videos/scene1_cut1.mp4
"""
    _, _, scenes = MODULE.parse_manifest_yaml_full(yaml_text)
    manifest = MODULE.yaml.safe_load(yaml_text)

    with pytest.raises(SystemExit, match="must follow canonical active cut order"):
        MODULE._build_video_render_targets(manifest=manifest, scenes=scenes)


def test_video_render_targets_reject_shared_reference_render_unit() -> None:
    yaml_text = """
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
    render_units:
      - unit_id: 1
        source_cut_ids: [1]
        image_generation:
          output: assets/characters/reference-unit.png
        video_generation:
          output: assets/videos/reference-unit.mp4
"""
    _, _, scenes = MODULE.parse_manifest_yaml_full(yaml_text)
    manifest = MODULE.yaml.safe_load(yaml_text)

    with pytest.raises(SystemExit, match="deleted/reference render_units are not supported"):
        MODULE._build_video_render_targets(manifest=manifest, scenes=scenes)
