from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
import pytest
import yaml
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server import cut_direction_api as service
from server import image_gen_app as api
from server.app import app as server_app
from toc.visual_planning_contract import source_binding


def _plan(duration: float = 4) -> dict:
    return {
        "schema_version": "shot_direction_v1",
        "intent": "注意を足元の動きへ移す",
        "shots": [
            {
                "shot_id": "a",
                "start_seconds": 0,
                "duration_seconds": duration,
                "intent": "歩みを見せる",
                "initial_view": {
                    "description": "作業者の靴と裾が見える",
                    "subjects": [
                        {
                            "entity_id": "keeper",
                            "kind": "character",
                            "member_id": None,
                            "visible_parts": ["足", "裾"],
                            "view": "画面の左から右へ歩く",
                        }
                    ],
                    "framing": "足元の寄り",
                    "composition": "床から低く撮る",
                    "focus": "靴と床",
                    "state_source": None,
                },
                "motion": "作業者が歩き続ける",
                "camera": {"movement": "固定", "angle": None, "lens_mm": None, "focus_change": None},
                "performance": [
                    {
                        "actor_id": "keeper",
                        "member_id": None,
                        "target_id": None,
                        "objective": "立ち去る",
                        "emotion": None,
                        "basis": "source_action",
                        "behavior": "足を止めず歩く",
                        "trigger": None,
                    }
                ],
                "events": [],
                "end_view": None,
                "end_state": "足元が画角から抜ける",
            }
        ],
    }


def _fixture(tmp_path: Path) -> tuple[Path, dict, bytes, bytes]:
    root = tmp_path / "output" / "direction_run"
    for directory in (
        "assets/scenes",
        "assets/characters",
        "assets/locations",
        "logs/orchestration",
    ):
        (root / directory).mkdir(parents=True, exist_ok=True)
    for relative, color in (
        ("assets/scenes/scene10_cut01.png", "red"),
        ("assets/scenes/scene10_cut02.png", "blue"),
        ("assets/characters/keeper.png", "green"),
        ("assets/characters/visitor.png", "yellow"),
        ("assets/locations/room.png", "black"),
    ):
        Image.new("RGB", (16, 9), color).save(root / relative)

    resources = {
        "characters": {
            "keeper": {"name": "作業者", "references": ["assets/characters/keeper.png"]},
            "visitor": {"name": "訪問者", "references": ["assets/characters/visitor.png"]},
        },
        "objects": {},
        "locations": {"room": {"name": "作業場", "references": ["assets/locations/room.png"]}},
    }
    direction = {"resources": resources, "scenes": []}
    direction_raw = json.dumps(direction, ensure_ascii=False).encode("utf-8")
    (root / "cinematic_direction.json").write_bytes(direction_raw)
    story_raw = b"""scenes:
  - scene_id: '10'
    title: Source scene
    cuts:
      - cut_id: authored-cut
        description: Source action.
"""
    script_raw = b"""scenes:
  - scene_id: '10'
    title: Script scene
    cuts:
      - cut_id: authored-cut
        narration: Do not change this line.
"""
    (root / "story.md").write_bytes(story_raw)
    (root / "script.md").write_bytes(script_raw)

    original_audio = {"narration": {"tool": "elevenlabs", "text": "採用済みの語り", "output": "assets/audio/one.mp3", "duration_seconds": 3.5}}
    source_contract = {
        "cut_role": "main",
        "viewer_contract": {"dramatic_job": "観察する"},
        "source_event_contract": {"source_event_beat_ids": ["beat_a"]},
        "first_frame_contract": {"first_frame_brief": "Original source fact."},
        "motion_contract": {"motion_brief": "Original source motion."},
        "continuity_contract": {
            "character_ids": ["keeper", "visitor"],
            "object_ids": [],
            "location_ids": ["room"],
            "must_preserve": ["靴の状態"],
        },
        "cinematic_contract": {"camera": {"light": "窓明かり"}},
        "narration_contract": {"text": "採用済みの語り"},
        "asset_dependency": {
            "character_ids_required": ["keeper", "visitor"],
            "object_ids_required": [],
            "location_ids_required": ["room"],
        },
    }
    source_image = {
        "character_ids": ["keeper", "visitor"],
        "object_ids": [],
        "location_ids": ["room"],
        "output": "assets/scenes/scene10_cut01.png",
    }
    selected_cut = {
        "cut_id": "01",
        "selector": "scene10_cut01",
        "authored_cut_id": "authored-cut",
        "duration_seconds": 4,
        "target_duration_seconds": 4,
        "cut_contract": source_contract,
        "audio": copy.deepcopy(original_audio),
        "image_generation": source_image,
        "video_generation": {"duration_seconds": 4, "output": "assets/scenes/scene10_cut01.mp4", "prompt_authoring_source": "Original motion."},
    }
    other_cut = {
        "cut_id": "02",
        "selector": "scene10_cut02",
        "duration_seconds": 2,
        "image_generation": {"output": "assets/scenes/scene10_cut02.png"},
        "video_generation": {"duration_seconds": 2, "output": "assets/scenes/scene10_cut02.mp4"},
        "audio": {"narration": {"text": "Other cut narration"}},
    }
    manifest = {
        "video_metadata": {
            "cinematic_direction_contract": "cinematic_direction_v1",
            "source_cinematic_direction": source_binding("cinematic_direction.json", direction_raw),
            "time": "current era",
        },
        "resources": resources,
        "scenes": [{"scene_id": "10", "title": "Scene title", "time_of_day": "evening", "cuts": [selected_cut, other_cut]}],
    }
    (root / "video_manifest.md").write_text(
        "# Manifest\n\n```yaml\n" + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False) + "```\n",
        encoding="utf-8",
    )
    (root / "state.txt").write_text("status=P650\n", encoding="utf-8")
    (root / "image_generation_requests.md").write_text("old request file", encoding="utf-8")
    (root / "image_generation_request_snapshot.json").write_text('{"old":true}\n', encoding="utf-8")
    return root, manifest, story_raw, script_raw


def _install_test_materializer(monkeypatch, run: Path, *, fail: bool = False) -> list[str]:
    called: list[str] = []

    async def materialize(run_id: str) -> None:
        called.append(run_id)
        (run / "image_generation_requests.md").write_text("new shot request file", encoding="utf-8")
        (run / "image_generation_request_snapshot.json").write_text('{"shot":true}\n', encoding="utf-8")
        if fail:
            raise RuntimeError("test shot target is unsupported")

    def load_items(_root: Path, kind: str):
        assert kind == "scene"
        _path, _text, data = api._read_manifest_data(run)
        return [SimpleNamespace(id=row["selector"]) for row in api._manifest_image_targets(data)]

    def load_snapshot(_path: Path, *, run_dir: Path, verify_references: bool):
        assert run_dir == run
        assert verify_references is False
        _manifest_path, _manifest_text, data = api._read_manifest_data(run)
        return SimpleNamespace(
            kind="scene",
            items=[SimpleNamespace(item_id=row["selector"]) for row in api._manifest_image_targets(data)],
        )

    monkeypatch.setattr(api, "_materialize_scene_requests", materialize, raising=False)
    monkeypatch.setattr(api, "load_request_items", load_items)
    monkeypatch.setattr(api, "load_request_snapshot", load_snapshot)
    monkeypatch.setattr(api, "append_state_snapshot", lambda _path, updates: updates)
    monkeypatch.setattr(api, "_invalidate_p600_supervisor_result", lambda *_args, **_kwargs: None)
    return called


def test_get_cut_direction_returns_legacy_cut_dto_and_canonical_manifest_revision(tmp_path, monkeypatch):
    root, manifest, _story, _script = _fixture(tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)

    result = service.read_dto(root)

    assert result["runId"] == "direction_run"
    assert result["revision"] == service.manifest_revision(manifest)
    assert result["scenes"][0]["title"] == "Scene title"
    cut = result["scenes"][0]["cuts"][0]
    assert cut == {
        "id": "scene10_cut1",
        "cutId": "01",
        "intent": "Original motion.",
        "durationSeconds": 4.0,
        "narrationDurationSeconds": 3.5,
        "thumbnailPath": "assets/scenes/scene10_cut01.png",
        "plan": None,
        "shots": [],
        "source": "legacy",
    }


def test_post_projects_only_one_cut_preserves_source_and_audio_and_invalidates_visual_inputs(tmp_path, monkeypatch):
    root, original, story_raw, script_raw = _fixture(tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)
    called = _install_test_materializer(monkeypatch, root)
    state_updates = []
    monkeypatch.setattr(api, "append_state_snapshot", lambda _path, updates: state_updates.append(updates))
    old_output = (root / "assets/scenes/scene10_cut01.png").read_bytes()
    expected = service.manifest_revision(original)

    result = asyncio.run(service.save_cut_direction(service.CutDirectionRequest(
        run_id="direction_run", item_id="scene10_cut1", expected_revision=expected, plan=_plan()
    )))

    _, _, published = api._read_manifest_data(root)
    selected = published["scenes"][0]["cuts"][0]
    untouched = published["scenes"][0]["cuts"][1]
    assert called == ["direction_run"]
    assert result["revision"] == service.manifest_revision(published)
    assert result["scenes"][0]["cuts"][0]["source"] == "shot_direction_v1"
    assert result["scenes"][0]["cuts"][0]["shots"][0]["id"] == "scene10_cut01_shota"
    assert selected["audio"] == original["scenes"][0]["cuts"][0]["audio"]
    assert selected["cut_contract"] == original["scenes"][0]["cuts"][0]["cut_contract"]
    assert selected["shot_direction_override"] == {
        "schema_version": "shot_direction_override_v1",
        "source_direction_binding": original["video_metadata"]["source_cinematic_direction"],
        "authored_cut_id": "authored-cut",
        "plan_sha256": hashlib_sha(selected["shot_plan"]),
    }
    assert untouched == original["scenes"][0]["cuts"][1]
    assert (root / "story.md").read_bytes() == story_raw
    assert (root / "script.md").read_bytes() == script_raw
    assert (root / "assets/scenes/scene10_cut01.png").read_bytes() == old_output
    assert (root / "image_generation_requests.md").read_text() == "new shot request file"
    assert state_updates[-1]["generation.image_prompt.request_freeze.status"] == "draft"
    assert state_updates[-1]["generation.video_prompt.materialization.status"] == "stale"
    assert state_updates[-1]["slot.p830.status"] == "pending"
    assert state_updates[-1]["image_generation.provenance.scene.scene10_cut01_shota.status"] == "invalidated"


def test_effective_render_duration_drives_shot_timeline_without_rewriting_parent_timing(tmp_path, monkeypatch):
    root, original, _story, _script = _fixture(tmp_path)
    selected = original["scenes"][0]["cuts"][0]
    selected["render"] = {"video_duration_seconds": 8}
    selected["video_generation"]["duration_seconds"] = 8
    path, text, manifest = api._read_manifest_data(root)
    manifest["scenes"][0]["cuts"][0]["render"] = {"video_duration_seconds": 8}
    manifest["scenes"][0]["cuts"][0]["video_generation"]["duration_seconds"] = 8
    api._write_manifest_data(path, text, manifest)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)
    _install_test_materializer(monkeypatch, root)
    expected = service.manifest_revision(manifest)

    result = asyncio.run(service.save_cut_direction(service.CutDirectionRequest(
        run_id="direction_run", item_id="scene10_cut1", expected_revision=expected,
        plan=_plan(8),
    )))

    _, _, published = api._read_manifest_data(root)
    cut = published["scenes"][0]["cuts"][0]
    assert cut["duration_seconds"] == 4
    assert cut["target_duration_seconds"] == 4
    assert cut["render"]["video_duration_seconds"] == 8
    assert cut["video_generation"]["duration_seconds"] == 8
    assert cut["shot_plan"]["shots"][0]["duration_seconds"] == 8
    assert result["scenes"][0]["cuts"][0]["durationSeconds"] == 8


def hashlib_sha(value: dict) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def test_bad_unresolved_subject_is_rejected_without_manifest_change(tmp_path, monkeypatch):
    root, original, _story, _script = _fixture(tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)
    _install_test_materializer(monkeypatch, root)
    invalid = _plan()
    invalid["shots"][0]["initial_view"]["subjects"][0]["entity_id"] = "missing_character"
    before = (root / "video_manifest.md").read_bytes()

    with pytest.raises(service.HTTPException) as error:
        asyncio.run(service.save_cut_direction(service.CutDirectionRequest(
            run_id="direction_run", item_id="scene10_cut1",
            expected_revision=service.manifest_revision(original), plan=invalid,
        )))

    assert error.value.status_code == 422
    assert "unknown_entity" in error.value.detail
    assert (root / "video_manifest.md").read_bytes() == before


def test_stale_manifest_revision_returns_409_without_rematerialization(tmp_path, monkeypatch):
    root, _original, _story, _script = _fixture(tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)
    called = _install_test_materializer(monkeypatch, root)
    before = (root / "video_manifest.md").read_bytes()

    with pytest.raises(service.HTTPException) as error:
        asyncio.run(service.save_cut_direction(service.CutDirectionRequest(
            run_id="direction_run", item_id="scene10_cut1",
            expected_revision="0" * 64, plan=_plan(),
        )))

    assert error.value.status_code == 409
    assert "revision is stale" in error.value.detail
    assert called == []
    assert (root / "video_manifest.md").read_bytes() == before


def test_bound_p400_manifest_does_not_fall_back_when_direction_artifact_is_missing(tmp_path, monkeypatch):
    root, original, _story, _script = _fixture(tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)
    (root / "cinematic_direction.json").unlink()
    before = (root / "video_manifest.md").read_bytes()

    with pytest.raises(service.HTTPException) as error:
        asyncio.run(service.save_cut_direction(service.CutDirectionRequest(
            run_id="direction_run", item_id="scene10_cut1",
            expected_revision=service.manifest_revision(original), plan=_plan(),
        )))

    assert error.value.status_code == 409
    assert "refresh p400" in error.value.detail
    assert (root / "video_manifest.md").read_bytes() == before


@pytest.mark.parametrize("stop_mode", ["timeout", "cancel"])
def test_materializer_child_is_reaped_before_api_manifest_rollback(tmp_path, monkeypatch, stop_mode):
    root, original, _story, _script = _fixture(tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)
    monkeypatch.setattr(api, "append_state_snapshot", lambda _path, updates: updates)
    monkeypatch.setattr(api, "_invalidate_p600_supervisor_result", lambda *_args, **_kwargs: None)
    started = root / "helper_started.txt"
    late_write = root / "late_child_write.txt"
    child_code = f"import pathlib,time; time.sleep(.8); pathlib.Path({str(late_write)!r}).write_text('late')"
    helper_code = (
        "import pathlib,subprocess,sys,time; "
        f"pathlib.Path({str(started)!r}).write_text('started'); "
        f"subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
        "time.sleep(20)"
    )

    async def materialize(_run_id: str) -> None:
        await api._run_helper_command("-c", helper_code, timeout=0.15)

    monkeypatch.setattr(api, "_materialize_scene_requests", materialize)
    before_manifest = (root / "video_manifest.md").read_bytes()
    request = service.CutDirectionRequest(
        run_id="direction_run",
        item_id="scene10_cut1",
        expected_revision=service.manifest_revision(original),
        plan=_plan(),
    )

    async def invoke() -> None:
        task = asyncio.create_task(service.save_cut_direction(request))
        deadline = asyncio.get_running_loop().time() + 3
        while not started.exists() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        assert started.exists(), "helper process did not start"
        if stop_mode == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(service.HTTPException) as error:
                await task
            assert error.value.status_code == 409

    asyncio.run(invoke())
    assert (root / "video_manifest.md").read_bytes() == before_manifest
    assert not late_write.exists()


def test_missing_asset_reference_is_rejected_before_projection_publish(tmp_path, monkeypatch):
    root, original, _story, _script = _fixture(tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)
    _install_test_materializer(monkeypatch, root)
    direction = json.loads((root / "cinematic_direction.json").read_text(encoding="utf-8"))
    direction["resources"]["characters"]["keeper"]["references"] = ["assets/characters/missing.png"]
    raw = json.dumps(direction, ensure_ascii=False).encode("utf-8")
    (root / "cinematic_direction.json").write_bytes(raw)
    original["video_metadata"]["source_cinematic_direction"] = source_binding("cinematic_direction.json", raw)
    manifest_path, text, manifest = api._read_manifest_data(root)
    manifest["video_metadata"]["source_cinematic_direction"] = source_binding("cinematic_direction.json", raw)
    api._write_manifest_data(manifest_path, text, manifest)
    before = (root / "video_manifest.md").read_bytes()

    with pytest.raises(service.HTTPException) as error:
        asyncio.run(service.save_cut_direction(service.CutDirectionRequest(
            run_id="direction_run", item_id="scene10_cut1",
            expected_revision=service.manifest_revision(manifest), plan=_plan(),
        )))

    assert error.value.status_code == 422
    assert "unresolved shot reference" in error.value.detail
    assert (root / "video_manifest.md").read_bytes() == before


def test_request_snapshot_publication_failure_rolls_back_manifest_and_request_files(tmp_path, monkeypatch):
    root, original, _story, _script = _fixture(tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)
    _install_test_materializer(monkeypatch, root, fail=True)
    before_manifest = (root / "video_manifest.md").read_bytes()
    before_requests = (root / "image_generation_requests.md").read_bytes()
    before_snapshot = (root / "image_generation_request_snapshot.json").read_bytes()

    with pytest.raises(service.HTTPException) as error:
        asyncio.run(service.save_cut_direction(service.CutDirectionRequest(
            run_id="direction_run", item_id="scene10_cut1",
            expected_revision=service.manifest_revision(original), plan=_plan(),
        )))

    assert error.value.status_code == 409
    assert "snapshot publication failed" in error.value.detail
    assert (root / "video_manifest.md").read_bytes() == before_manifest
    assert (root / "image_generation_requests.md").read_bytes() == before_requests
    assert (root / "image_generation_request_snapshot.json").read_bytes() == before_snapshot


def test_publish_calls_real_manifest_materializer_and_publishes_shot_snapshot(tmp_path, monkeypatch):
    from test_p400_cinematic_author import sample as cinematic_sample
    from toc.p400_authoring import CONTRACT, bind_direction, validate_direction
    from toc.p400_projection import project_scene
    from toc.source_scene_projection import source_scene_event

    root = tmp_path / "output" / "direction_run"
    root.mkdir(parents=True)
    story, source_bytes, resources, authored_scenes = cinematic_sample(root)
    source_scene = story["script"]["scenes"][0]
    story["script"]["scenes"] = [source_scene]
    source_bytes = {**source_bytes, "story": json.dumps(story, ensure_ascii=False).encode("utf-8")}
    for name, content in source_bytes.items():
        (root / f"{name}.md").write_bytes(content)
    for group in ("characters", "objects", "locations"):
        for record in resources[group].values():
            for reference in record.get("references", []):
                path = root / reference
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (16, 9), "green").save(path)
    direction = bind_direction(authored_scenes[:1], source_bytes, resources)
    assert validate_direction(direction, story, resources) == []
    direction_raw = json.dumps(direction, ensure_ascii=False).encode("utf-8")
    (root / "cinematic_direction.json").write_bytes(direction_raw)
    canonical_scene = source_scene_event(
        source_scene, runtime_scene_id=10, location_name=source_scene["location"]["name"]
    )
    script_scene, manifest_scene = project_scene(
        direction["scenes"][0],
        source_scene=source_scene,
        scene_id=10,
        resources=resources,
        scene_intent={},
        scene_event=canonical_scene,
        scene_generation={},
        acceptance_draft={},
        acceptance_binding={},
    )
    binding = source_binding("cinematic_direction.json", direction_raw)
    script = {
        "script_metadata": {
            "cinematic_direction_contract": CONTRACT,
            "source_cinematic_direction": binding,
        },
        "scenes": [script_scene],
    }
    manifest = {
        "manifest_phase": "production",
        "video_metadata": {
            "cinematic_direction_contract": CONTRACT,
            "source_cinematic_direction": binding,
            "time": "",
        },
        "scenes": [manifest_scene],
    }
    (root / "script.md").write_text("```yaml\n" + yaml.safe_dump(script, allow_unicode=True, sort_keys=False) + "```\n", encoding="utf-8")
    (root / "video_manifest.md").write_text("```yaml\n" + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False) + "```\n", encoding="utf-8")
    (root / "state.txt").write_text("status=P650\n", encoding="utf-8")
    target = api._manifest_scene_targets(manifest)[0]
    cut = target["cut"]
    cut["render"] = {"video_duration_seconds": 8}
    cut["video_generation"]["duration_seconds"] = 8
    (root / "video_manifest.md").write_text(
        "```yaml\n" + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False) + "```\n",
        encoding="utf-8",
    )
    duration = 8.0
    actor_id = cut["image_generation"]["character_ids"][0]
    planned_shots = _plan(duration)["shots"]
    planned_shots[0]["initial_view"]["subjects"][0]["entity_id"] = actor_id
    planned_shots[0]["performance"][0]["actor_id"] = actor_id
    plan = {"schema_version": "shot_direction_v1", "intent": "足元の歩みを見せる", "shots": planned_shots}
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)
    monkeypatch.setattr(api, "append_state_snapshot", lambda _path, updates: updates)
    monkeypatch.setattr(api, "_invalidate_p600_supervisor_result", lambda *_args, **_kwargs: None)
    commands: list[list[str]] = []

    async def run_real_helper(*args: str, timeout: int = 1800) -> str:
        command = list(args)
        command[0] = str(REPO_ROOT / "scripts" / "generate-assets-from-manifest.py")
        commands.append(command)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            *command,
            cwd=tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        if process.returncode:
            raise RuntimeError(
                stderr.decode("utf-8", errors="replace")
                or stdout.decode("utf-8", errors="replace")
            )
        return stdout.decode("utf-8", errors="replace")

    monkeypatch.setattr(api, "_run_helper_command", run_real_helper)
    expected = service.manifest_revision(api._read_manifest_data(root)[2])

    result = asyncio.run(service.save_cut_direction(service.CutDirectionRequest(
        run_id="direction_run", item_id=target["selector"], expected_revision=expected, plan=plan
    )))

    published_cut = api._read_manifest_data(root)[2]["scenes"][0]["cuts"][0]
    assert published_cut["duration_seconds"] == cut["duration_seconds"]
    assert published_cut["target_duration_seconds"] == cut["target_duration_seconds"]
    assert published_cut["render"]["video_duration_seconds"] == 8
    assert published_cut["video_generation"]["duration_seconds"] == 8
    assert sum(float(row["duration_seconds"]) for row in published_cut["shot_plan"]["shots"]) == 8
    assert len(commands) == 1
    assert "--materialize-request-files-only" in commands[0]
    assert "--skip-videos" in commands[0]
    assert "--skip-audio" in commands[0]
    assert result["scenes"][0]["cuts"][0]["source"] == "shot_direction_v1"
    snapshot = json.loads((root / "image_generation_request_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["kind"] == "scene"
    request_ids = {item["item_id"] for item in snapshot["items"]}
    shot_ids = {
        row["selector"] for row in api._manifest_shot_targets(api._read_manifest_data(root)[2], parent_selector=target["selector"])
    }
    assert shot_ids <= request_ids
    assert target["selector"] not in request_ids
    assert (root / "video_generation_requests.md").is_file()


def test_instruction_turn_uses_structured_story_author_and_rechecks_sources(tmp_path, monkeypatch):
    root, original, _story, _script = _fixture(tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)
    _install_test_materializer(monkeypatch, root)
    observed = {}

    async def fake_author(prompt: str, _root: Path) -> dict:
        observed["prompt"] = prompt
        return _plan()

    monkeypatch.setattr(service, "author_shot_plan", fake_author)
    result = asyncio.run(service.save_cut_direction(service.CutDirectionRequest(
        run_id="direction_run", item_id="scene10_cut1",
        expected_revision=service.manifest_revision(original),
        instruction="足元だけを見せる構図へ直す",
    )))

    assert result["scenes"][0]["cuts"][0]["source"] == "shot_direction_v1"
    assert "足元だけを見せる構図へ直す" in observed["prompt"]
    assert "Do not change this line." in observed["prompt"]
    assert "SHOT_PLAN_FORMAT" not in observed["prompt"]


def test_author_context_matches_semantic_story_id_and_both_cut_ids(tmp_path, monkeypatch):
    root, _original, _story, _script = _fixture(tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(service, "app", lambda: api)
    story = {
        "scenes": [{
            "scene_id": "semantic_scene",
            "title": "Source scene",
            "cuts": [{"cut_id": "authored-cut", "description": "The source action."}],
        }]
    }
    script = {
        "scenes": [{
            "scene_id": "10",
            "source_story_scene_id": "semantic_scene",
            "title": "Runtime scene",
            "cuts": [{
                "cut_id": "01",
                "authored_cut_id": "authored-cut",
                "narration": "The authored narration.",
            }],
        }]
    }
    (root / "story.md").write_text(yaml.safe_dump(story, allow_unicode=True), encoding="utf-8")
    (root / "script.md").write_text(yaml.safe_dump(script, allow_unicode=True), encoding="utf-8")
    manifest_path, manifest_text, manifest = api._read_manifest_data(root)
    manifest["scenes"][0]["source_story_scene_id"] = "semantic_scene"
    manifest["scenes"][0]["scene_intent"] = {"camera_continuity": "keep the same axis"}
    manifest["scenes"][0]["cuts"][0]["authored_cut_id"] = "authored-cut"
    api._write_manifest_data(manifest_path, manifest_text, manifest)
    target = api._target_by_item_id(manifest, "scene10_cut1")
    direction = {
        "resources": manifest["resources"],
        "scenes": [{
            "scene_id": "semantic_scene",
            "cuts": [{"cut_id": "authored-cut", "direction": "Keep the first frame quiet."}],
        }],
    }

    context = service._cut_authoring_context(
        root=root, data=manifest, target=target, direction=direction
    )
    prompt = json.loads(service.build_author_prompt(context, "足を止めずに歩かせる"))

    assert context["source_story"]["scene"]["scene_id"] == "semantic_scene"
    assert context["source_story"]["cut"]["description"] == "The source action."
    assert context["source_script"]["scene"]["scene_id"] == "10"
    assert context["source_script"]["cut"]["narration"] == "The authored narration."
    assert context["cinematic_direction"]["scene"]["scene_id"] == "semantic_scene"
    assert context["cinematic_direction"]["cut"]["direction"] == "Keep the first frame quiet."
    assert context["neighboring_manifest_cuts"]["scene_intent"]["camera_continuity"] == "keep the same axis"
    assert context["neighboring_manifest_cuts"]["next"]["cut_id"] == "02"
    assert "観察可能な演技や身体動作" in prompt["task"]
    assert "心理・身体状態を追加せず" not in prompt["task"]


def test_cli_run_dir_is_confined_to_output_root(tmp_path, monkeypatch):
    path = REPO_ROOT / "scripts" / "edit-cut-direction.py"
    spec = importlib.util.spec_from_file_location("edit_cut_direction_cli_test", path)
    assert spec and spec.loader
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    run = tmp_path / "output" / "cli_run"
    run.mkdir(parents=True)

    assert cli._run_id(SimpleNamespace(run_id=None, run_dir=run)) == "cli_run"
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="configured output root"):
        cli._run_id(SimpleNamespace(run_id=None, run_dir=outside))


def test_cut_direction_get_route_is_installed_with_existing_server_auth(tmp_path, monkeypatch):
    root, _manifest, _story, _script = _fixture(tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setenv("TOC_SERVER_AUTH_DISABLED", "1")

    with TestClient(server_app) as client:
        response = client.get("/api/image-gen/cut-direction", params={"run_id": "direction_run"})

    assert response.status_code == 200, response.text
    assert response.json()["runId"] == root.name
    assert response.json()["scenes"][0]["cuts"][0]["source"] == "legacy"
