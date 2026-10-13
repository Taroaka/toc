from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from server import image_gen_app
from toc.shot_timeline import validate_projected_shot_schedule


SCRIPT_PATH = REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"
SPEC = importlib.util.spec_from_file_location("generate_assets_shot_runtime", SCRIPT_PATH)
assert SPEC and SPEC.loader
GENERATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GENERATOR
SPEC.loader.exec_module(GENERATOR)


def shot_manifest() -> dict:
    shots = [
        {
            "shot_id": "s01",
            "start_seconds": 0,
            "duration_seconds": 1.25,
            "cut_contract": {"purpose": "open"},
            "image_generation": {
                "tool": "codex_builtin_image",
                "prompt": "Opening frame",
                "output": "assets/scenes/scene3_cut2_shots01.png",
            },
            "video_generation": {
                "tool": "kling_3_0",
                "duration_seconds": 3,
                "prompt_authoring_source": "The camera eases forward.",
                "first_frame": "assets/scenes/scene3_cut2_shots01.png",
                "output": "assets/scenes/scene3_cut2_shots01.mp4",
            },
        },
        {
            "shot_id": "s02",
            "start_seconds": 1.25,
            "duration_seconds": 1.75,
            "cut_contract": {"purpose": "hold"},
            "image_generation": {
                "tool": "codex_builtin_image",
                "prompt": "Held frame",
                "output": "assets/scenes/scene3_cut2_shots02.png",
            },
            "video_generation": {
                "tool": "kling_3_0",
                "duration_seconds": 3,
                "prompt_authoring_source": "The character remains still.",
                "first_frame": "assets/scenes/scene3_cut2_shots02.png",
                "output": "assets/scenes/scene3_cut2_shots02.mp4",
            },
        },
    ]
    parent = {
        "cut_id": "2",
        "duration_seconds": 3,
        "shot_plan": {
            "schema_version": "shot_direction_v1",
            "intent": "A short action then a held reaction.",
            "shots": shots,
        },
        "shots": shots,
        # The legacy cut target remains an alias of the first shot image.
        "image_generation": {"output": shots[0]["image_generation"]["output"]},
        "video_generation": {"duration_seconds": 3},
        "audio": {"narration": {"text": "One parent narration."}},
    }
    return {"scenes": [{"scene_id": "3", "cuts": [parent]}]}


def test_server_shot_targets_preserve_parent_cut_and_keep_shot_ids() -> None:
    manifest = shot_manifest()

    parents = image_gen_app._manifest_scene_targets(manifest)
    shots = image_gen_app._manifest_shot_targets(manifest)
    videos = image_gen_app._manifest_video_targets(manifest)

    assert [target["selector"] for target in parents] == ["scene3_cut2"]
    assert [target["selector"] for target in shots] == [
        "scene3_cut2_shots01",
        "scene3_cut2_shots02",
    ]
    assert [target["selector"] for target in videos] == [
        "scene3_cut2_shots01",
        "scene3_cut2_shots02",
    ]
    assert [target["timeline_duration_seconds"] for target in videos] == [1.25, 1.75]
    assert [target["cut"]["video_generation"]["duration_seconds"] for target in videos] == [3, 3]
    assert parents[0]["cut"]["audio"]["narration"]["text"] == "One parent narration."


def test_image_targets_replace_parent_alias_with_unique_shot_images() -> None:
    targets = image_gen_app._manifest_image_targets(shot_manifest())

    assert [target["selector"] for target in targets] == [
        "scene3_cut2_shots01",
        "scene3_cut2_shots02",
    ]
    assert len({target["image_generation"]["output"] for target in targets}) == 2


def test_shot_video_items_expose_child_model_and_timeline(tmp_path: Path) -> None:
    manifest = shot_manifest()
    for shot in manifest["scenes"][0]["cuts"][0]["shots"]:
        shot["video_generation"].update(
            tool="higgsfield",
            model="kling-video/v3.0/std/image-to-video",
        )

    items = image_gen_app._manifest_video_items(tmp_path, manifest)

    assert [item["id"] for item in items] == [
        "scene3_cut2_shots01",
        "scene3_cut2_shots02",
    ]
    assert [item["videoModel"] for item in items] == [
        "kling-video/v3.0/std/image-to-video",
        "kling-video/v3.0/std/image-to-video",
    ]
    assert [item["videoQuality"] for item in items] == [None, None]
    assert [item["timelineDurationSeconds"] for item in items] == [1.25, 1.75]
    assert [item["providerDurationSeconds"] for item in items] == [3, 3]
    assert all(item["hasShots"] is True for item in items)


def test_parent_narration_dto_exposes_child_targets_without_a_parent_video_request(tmp_path: Path) -> None:
    manifest = shot_manifest()
    parent = manifest["scenes"][0]["cuts"][0]
    parent["video_generation"].update(
        tool="higgsfield",
        model="kling-video/v3.0/std/image-to-video",
        quality="1080p",
    )
    for shot in parent["shots"]:
        shot["video_generation"].update(
            tool="higgsfield",
            model="kling-video/v3.0/std/image-to-video",
            quality="1080p",
        )

    item = image_gen_app._manifest_narration_items(tmp_path, manifest)[0]

    assert item["itemId"] == "scene3_cut2"
    assert item["hasShots"] is True
    assert item["videoModel"] == "kling-video/v3.0/std/image-to-video"
    assert item["videoQuality"] is None
    assert [shot["itemId"] for shot in item["shotTargets"]] == [
        "scene3_cut2_shots01",
        "scene3_cut2_shots02",
    ]
    assert [shot["videoModel"] for shot in item["shotTargets"]] == [
        "kling-video/v3.0/std/image-to-video",
        "kling-video/v3.0/std/image-to-video",
    ]


def test_server_shot_targets_reject_gaps_and_duration_mismatch() -> None:
    manifest = shot_manifest()
    manifest["scenes"][0]["cuts"][0]["shots"][1]["start_seconds"] = 1.5

    with pytest.raises(ValueError, match="contiguous"):
        image_gen_app._manifest_shot_targets(manifest)

    manifest = shot_manifest()
    manifest["scenes"][0]["cuts"][0]["shots"][1]["duration_seconds"] = 2
    with pytest.raises(ValueError, match="sum to parent cut duration"):
        image_gen_app._manifest_shot_targets(manifest)

    manifest = shot_manifest()
    manifest["scenes"][0]["cuts"][0]["render"] = {"video_duration_seconds": 4}
    with pytest.raises(ValueError, match="sum to parent cut duration"):
        image_gen_app._manifest_shot_targets(manifest)


def test_shared_timeline_normalizes_authoring_tolerance_and_checks_higgsfield_kling_model() -> None:
    manifest = shot_manifest()
    cut = manifest["scenes"][0]["cuts"][0]
    cut["shots"][1]["start_seconds"] = 1.2500005
    cut["shots"][0]["video_generation"].update(
        tool="higgsfield",
        model="kling-video/v3.0/std/image-to-video",
    )

    entries = validate_projected_shot_schedule(cut, parent_selector="scene3_cut2")
    assert [entry["start_seconds"] for entry in entries] == [0, 1.25]

    cut["shots"][0]["video_generation"]["duration_seconds"] = 4
    with pytest.raises(ValueError, match="Kling v3 duration_seconds must be 3"):
        validate_projected_shot_schedule(cut, parent_selector="scene3_cut2")


@pytest.mark.parametrize("collision", ["shot_id", "output_path"])
def test_shared_timeline_rejects_case_insensitive_child_collisions(collision: str) -> None:
    manifest = shot_manifest()
    shots = manifest["scenes"][0]["cuts"][0]["shots"]
    if collision == "shot_id":
        shots[1]["shot_id"] = "S01"
    else:
        shots[1]["image_generation"]["output"] = shots[0]["image_generation"]["output"].upper()

    with pytest.raises(ValueError, match="duplicate or invalid shot_id|collides"):
        validate_projected_shot_schedule(
            manifest["scenes"][0]["cuts"][0],
            parent_selector="scene3_cut2",
        )


def test_generator_projects_shot_targets_and_images_without_audio_targets() -> None:
    manifest = shot_manifest()
    yaml_text = GENERATOR.yaml.safe_dump(manifest, sort_keys=False)
    _metadata, _guides, scenes = GENERATOR.parse_manifest_yaml_full(yaml_text)

    image_scenes = GENERATOR._project_shot_image_scenes(manifest=manifest, scenes=scenes)
    video_targets = GENERATOR._build_video_render_targets(manifest=manifest, scenes=scenes)

    assert [scene.selector for scene in image_scenes] == [
        "scene3_cut2_shots01",
        "scene3_cut2_shots02",
    ]
    assert [scene.image_output for scene in image_scenes] == [
        "assets/scenes/scene3_cut2_shots01.png",
        "assets/scenes/scene3_cut2_shots02.png",
    ]
    assert all(scene.narration_output is None for scene in image_scenes)
    assert [target.selector for target in video_targets] == [
        "scene3_cut2_shots01",
        "scene3_cut2_shots02",
    ]
    assert [target.timeline_duration_seconds for target in video_targets] == [1.25, 1.75]
    assert [target.duration_seconds for target in video_targets] == [3, 3]


def test_shot_result_frame_is_a_distinct_image_target() -> None:
    manifest = shot_manifest()
    shot = manifest["scenes"][0]["cuts"][0]["shots"][0]
    shot["video_generation"]["last_frame"] = "assets/scenes/scene3_cut2_shots01_result.png"
    shot["video_generation"]["result_frame"] = {
        "output": "assets/scenes/scene3_cut2_shots01_result.png",
        "image_generation": {
            "tool": "codex_builtin_image",
            "prompt": "End frame",
            "output": "assets/scenes/scene3_cut2_shots01_result.png",
        },
    }

    image_targets = image_gen_app._manifest_image_targets(manifest)
    _metadata, _guides, scenes = GENERATOR.parse_manifest_yaml_full(
        GENERATOR.yaml.safe_dump(manifest, sort_keys=False)
    )
    result_specs = GENERATOR._project_shot_result_frame_scenes(
        manifest=manifest,
        scenes=scenes,
    )

    assert [target["selector"] for target in image_targets] == [
        "scene3_cut2_shots01",
        "scene3_cut2_shots01_result_frame",
        "scene3_cut2_shots02",
    ]
    assert [scene.selector for scene in result_specs] == [
        "scene3_cut2_shots01_result_frame",
    ]
    assert result_specs[0].image_output == "assets/scenes/scene3_cut2_shots01_result.png"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("shot_id", "../bad", "shot_id"),
        ("duration_seconds", 0, "positive"),
    ],
)
def test_generator_rejects_invalid_shot_timeline(field: str, value, message: str) -> None:
    manifest = shot_manifest()
    manifest["scenes"][0]["cuts"][0]["shots"][0][field] = value
    yaml_text = GENERATOR.yaml.safe_dump(manifest, sort_keys=False)
    _metadata, _guides, scenes = GENERATOR.parse_manifest_yaml_full(yaml_text)

    with pytest.raises(SystemExit, match=message):
        GENERATOR._build_video_render_targets(manifest=manifest, scenes=scenes)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg/ffprobe required")
def test_render_preparation_trims_provider_clip_to_fractional_shot_timeline(tmp_path: Path) -> None:
    source = tmp_path / "assets/scenes/provider.mp4"
    source.parent.mkdir(parents=True)
    subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:d=3:r=24",
            "-an",
            str(source),
        ],
        check=True,
        capture_output=True,
    )

    prepared = image_gen_app._prepare_render_shot_clip(
        tmp_path,
        source,
        item_id="scene3_cut2_shots01",
        duration_seconds=1.25,
    )

    assert prepared != source
    image_gen_app._require_shot_render_duration(
        prepared,
        expected_seconds=1.25,
        label="scene3_cut2_shots01",
    )


def _write_shot_render_run(run_dir: Path) -> tuple[dict, dict[str, str]]:
    import yaml

    manifest = shot_manifest()
    parent = manifest["scenes"][0]["cuts"][0]
    parent["video_generation"]["output"] = "assets/scenes/legacy_parent.mp4"
    parent["render"] = {"video_duration_seconds": 3, "narration_offset_seconds": 0}
    parent["audio"]["narration"].update(
        tool="elevenlabs",
        output="assets/audio/narration.mp3",
        status="audio_ready",
    )
    media_paths: dict[str, str] = {}
    for shot in parent["shots"]:
        selector = f"scene3_cut2_shot{shot['shot_id']}"
        path = str(shot["video_generation"]["output"])
        target = run_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"provider video bytes")
        media_paths[selector] = path
    audio_path = run_dir / "assets/audio/narration.mp3"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"audio bytes")
    (run_dir / "state.txt").write_text("status=P910\n", encoding="utf-8")
    (run_dir / "video_manifest.md").write_text(
        "```yaml\n" + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False) + "```\n",
        encoding="utf-8",
    )
    return manifest, media_paths


def test_render_freeze_requires_child_approvals_and_preserves_parent_audio(tmp_path: Path) -> None:
    import yaml

    manifest, media_paths = _write_shot_render_run(tmp_path)
    parent_before = manifest["scenes"][0]["cuts"][0]
    audio_before = parent_before["audio"]
    video_generation_before = parent_before["video_generation"].copy()
    audio_hash_before = image_gen_app._manifest_narration_audio_set_hash(manifest)
    timeline_hash_before = image_gen_app._manifest_narration_timeline_hash(manifest)
    approved = {
        "videos": [
            {
                "item_id": selector,
                "path": path,
                "duration_seconds": duration,
            }
            for selector, path, duration in (
                ("scene3_cut2_shots01", media_paths["scene3_cut2_shots01"], 1.25),
                ("scene3_cut2_shots02", media_paths["scene3_cut2_shots02"], 1.75),
            )
        ]
    }
    request = image_gen_app.RenderFreezeRequest(
        run_id=tmp_path.name,
        output="final.mp4",
        items=[
            image_gen_app.RenderInputItem(
                item_id="scene3_cut2",
                video_path=media_paths["scene3_cut2_shots01"],
                narration_path=None,
                video_duration_seconds=3,
            )
        ],
    )
    prepared_shots: list[tuple[str, float]] = []

    def prepare_shot(_root, source, *, item_id, duration_seconds):
        prepared_shots.append((item_id, duration_seconds))
        return source

    with (
        patch("server.sound_design_api.freeze", return_value={"sound_hash": "sound-v1"}),
        patch.object(image_gen_app._sound_design_api, "video_context", return_value=approved),
        patch.object(image_gen_app, "_prepare_render_shot_clip", side_effect=prepare_shot),
        patch.object(image_gen_app, "_prepare_render_narration", side_effect=lambda _root, source, _item, **_kwargs: source),
        patch.object(image_gen_app, "_probe_media_duration_seconds", return_value=None),
        patch("toc.sound_design.write_json"),
    ):
        result = image_gen_app._freeze_render_inputs(tmp_path, request)

    updated_text = (tmp_path / "video_manifest.md").read_text(encoding="utf-8")
    updated = yaml.safe_load(updated_text.split("```yaml\n", 1)[1].split("```", 1)[0])
    parent_after = updated["scenes"][0]["cuts"][0]
    assert prepared_shots == [
        ("scene3_cut2_shots01", 1.25),
        ("scene3_cut2_shots02", 1.75),
    ]
    assert result["updated"] == ["scene3_cut2"]
    assert parent_after["audio"] == audio_before
    assert parent_after["video_generation"] == video_generation_before
    assert image_gen_app._manifest_narration_audio_set_hash(updated) == audio_hash_before
    assert image_gen_app._manifest_narration_timeline_hash(updated) == timeline_hash_before
    clip_list = (tmp_path / result["clipList"]).read_text(encoding="utf-8")
    assert clip_list.count("file '") == 2


def test_render_freeze_rejects_a_missing_child_video_approval(tmp_path: Path) -> None:
    _manifest, media_paths = _write_shot_render_run(tmp_path)
    approved = {
        "videos": [
            {
                "item_id": "scene3_cut2_shots01",
                "path": media_paths["scene3_cut2_shots01"],
                "duration_seconds": 1.25,
            }
        ]
    }
    manifest_before = (tmp_path / "video_manifest.md").read_bytes()
    request = image_gen_app.RenderFreezeRequest(
        run_id=tmp_path.name,
        output="final.mp4",
        items=[
            image_gen_app.RenderInputItem(
                item_id="scene3_cut2",
                video_path=media_paths["scene3_cut2_shots01"],
                video_duration_seconds=3,
            )
        ],
    )

    with (
        patch("server.sound_design_api.freeze", return_value={"sound_hash": "sound-v1"}),
        patch.object(image_gen_app._sound_design_api, "video_context", return_value=approved),
        patch.object(image_gen_app, "_prepare_render_shot_clip", side_effect=lambda _root, source, **_kwargs: source),
        patch.object(image_gen_app, "_prepare_render_narration", side_effect=lambda _root, source, _item, **_kwargs: source),
        patch.object(image_gen_app, "_probe_media_duration_seconds", return_value=None),
        patch("toc.sound_design.write_json"),
        pytest.raises(ValueError, match="no current p860 video approval"),
    ):
        image_gen_app._freeze_render_inputs(tmp_path, request)

    assert (tmp_path / "video_manifest.md").read_bytes() == manifest_before
