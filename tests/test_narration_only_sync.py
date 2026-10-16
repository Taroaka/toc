from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import subprocess
import sys

import yaml

from toc.harness import load_structured_document
from toc.narration_continuity import tts_continuity_contexts
from toc.narration_revision import (
    apply_authoring_update,
    approve_audio_candidate,
    prepare_audio_candidate,
    record_audio_candidate_result,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sync-narration-from-script.py"
SPEC = importlib.util.spec_from_file_location("sync_narration_only", SCRIPT_PATH)
assert SPEC and SPEC.loader
SYNC_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SYNC_MODULE
SPEC.loader.exec_module(SYNC_MODULE)


def _write_document(path: Path, data: dict) -> None:
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000)
    path.write_text(f"# Document\n\n```yaml\n{body}```\n", encoding="utf-8")


def _read_document(path: Path) -> dict:
    _, data = load_structured_document(path)
    assert isinstance(data, dict)
    return data


def _without_narration(manifest: dict) -> dict:
    """Keep every manifest field except the explicitly narration-owned projection."""

    value = deepcopy(manifest)
    for key in ("audio_story_plan", "narration_spans", "narration_workflow"):
        value.pop(key, None)
    for scene in value.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        for cut in scene.get("cuts", []):
            if not isinstance(cut, dict):
                continue
            audio = cut.get("audio")
            if not isinstance(audio, dict):
                continue
            audio.pop("narration", None)
            if not audio:
                cut.pop("audio", None)
    return value


def _find_cut(data: dict, scene_id: str, cut_id: str) -> dict:
    for scene in data["scenes"]:
        if str(scene.get("scene_id")) == scene_id:
            for cut in scene.get("cuts", []):
                if str(cut.get("cut_id")) == cut_id:
                    return cut
    raise AssertionError(f"missing {scene_id}/{cut_id}")


def _script_cut(text: str, tts_text: str, status: str = "human_locked") -> dict:
    return {
        "cut_id": 1,
        "narration": text,
        "tts_text": tts_text,
        "narration_authoring": {"schema_version": "narration_authoring_v1", "status": status},
        "visual_beat": "script visual change that must not project",
        "cut_contract": {"a_roll_or_b_roll": "b_roll", "target_beat": "visual change"},
        "human_review": {
            "status": "approved",
            "approved_narration": text,
            "approved_tts_text": tts_text,
            "approved_visual_beat": "approved visual change that must not project",
            "approved_image_notes": ["new visual note"],
            "approved_video_notes": ["new motion note"],
        },
    }


def _base_manifest(text: str = "旧原稿です。", tts_text: str = "ふるい げんこうです。") -> dict:
    return {
        "manifest_phase": "production",
        "video_metadata": {"topic": "Example", "time": "before"},
        "human_change_requests": [{"request_id": "manifest-owned-request", "normalized_actions": []}],
        "assets": {
            "character_bible": [{"character_id": "lead", "reference_images": ["assets/characters/lead.png"]}],
            "object_bible": [{"object_id": "key", "reference_images": ["assets/objects/key.png"]}],
            "location_bible": [{"location_id": "shore", "reference_images": ["assets/locations/shore.png"]}],
        },
        "audio_story_plan": {
            "schema_version": "audio_story_plan_v1",
            "audience_promise": "old promise",
            "continuous_full_draft": text,
        },
        "narration_spans": [
            {
                "span_id": "ns_001",
                "source_cut_ids": ["scene1_cut1"],
                "story_job": "causal_bridge",
                "audio_visual_relation": "complement",
                "tts_generation_group_id": "run_voice",
                "text": text,
                "tts_text": tts_text,
            }
        ],
        "narration_workflow": {
            "schema_version": "narration_run_workflow_v1",
            "final_audio_review": {"status": "approved", "approved_audio_set_hash": "old-hash"},
        },
        "scenes": [
            {
                "scene_id": 1,
                "scene_summary": "manifest scene summary",
                "story_visual": "manifest story visual",
                "time_of_day": "night",
                "implementation_trace": {"source_request_ids": ["manifest-visual-request"]},
                "cuts": [
                    {
                        "cut_id": 1,
                        "output": "assets/scenes/scene1_cut1.png",
                        "cut_contract": {
                            "a_roll_or_b_roll": "a_roll",
                            "target_beat": "manifest target",
                            "must_show": ["manifest object"],
                        },
                        "scene_contract": {"target_beat": "old scene contract"},
                        "image_generation": {
                            "output": "assets/scenes/scene1_cut1.png",
                            "prompt": "manifest image prompt",
                            "rationale": "manifest image rationale",
                            "character_ids": ["lead"],
                            "object_ids": ["key"],
                            "location_ids": ["shore"],
                            "reference_asset_ids": ["lead_reference"],
                            "api_prompt_payload": {"shot_design_contract": {"shot_size": "wide"}},
                        },
                        "still_assets": [
                            {
                                "asset_id": "still_primary",
                                "output": "assets/scenes/scene1_cut1.png",
                                "reference_asset_ids": ["lead_reference"],
                            }
                        ],
                        "video_generation": {
                            "output": "assets/videos/scene1_cut1.mp4",
                            "motion_prompt": "manifest motion prompt",
                            "first_frame": "assets/scenes/scene1_cut1.png",
                            "direction_notes": ["approved manifest direction"],
                        },
                        "audio": {
                            "narration": {
                                "tool": "elevenlabs",
                                "text": text,
                                "tts_text": tts_text,
                                "authoring_status": "human_locked",
                            },
                            "bgm": {"output": "assets/audio/music.mp3", "volume": 0.2},
                            "sound_effects": [{"output": "assets/audio/wave.wav", "volume": 0.5}],
                        },
                        "text_overlay": {"text": "manifest subtitle"},
                    }
                ],
                "render_units": [{"unit_id": 1, "source_cut_ids": [1], "output": "assets/videos/render.mp4"}],
            }
        ],
    }


def _attach_approved_audio(narration: dict, *, tts_context_hash: str, output: str) -> None:
    apply_authoring_update(
        narration,
        text=str(narration["text"]),
        tts_text=str(narration["tts_text"]),
        tool="elevenlabs",
        authoring_status="human_locked",
        source="test",
        expected_revision=0,
        now="2026-10-16T10:00:00+09:00",
    )
    revision_number = int(narration["revision"]["number"] or 0)
    snapshot = prepare_audio_candidate(
        narration,
        candidate_id="candidate-old",
        output=output,
        expected_revision=revision_number,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-10-16T10:00:01+09:00",
        provider_request={"tts_continuity_hash": tts_context_hash},
    )
    record_audio_candidate_result(
        narration,
        snapshot=snapshot,
        succeeded=True,
        duration_seconds=2.5,
        output_sha256="sha256:" + "a" * 64,
        now="2026-10-16T10:00:02+09:00",
    )
    approve_audio_candidate(
        narration,
        candidate_id="candidate-old",
        expected_revision=revision_number,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-10-16T10:00:03+09:00",
    )


def test_api_narration_only_projects_flat_and_nested_narration_without_visual_changes(tmp_path: Path) -> None:
    script_path = tmp_path / "script.md"
    manifest_path = tmp_path / "video_manifest.md"
    media_path = tmp_path / "assets" / "scenes" / "scene1_cut1.png"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"existing image bytes")

    script_cut = _script_cut("新しい正本です。", "あたらしい せいほんです。")
    script_cut["elevenlabs_prompt"] = {
        "spoken_context": "語り手は一拍置いて告げます。",
        "voice_tags": ["calm"],
        "spoken_body": "あたらしい せいほんです。",
        "stability_profile": "",
    }
    silent_cut = {
        "cut_id": 2,
        "audio": {
            "narration": {
                "text": "",
                "tts_text": "",
                "tool": "silent",
                "authoring_status": "silent",
                "silence_contract": {"intentional": True, "reason": "scripted pause"},
            }
        },
    }
    script = {
        "script_metadata": {
            "time": "script time must not project",
            "elevenlabs": {
                "provider": "elevenlabs",
                "model_id": "eleven_v3",
                "voice_id": "script-voice-id",
                "voice_name": "Script voice",
                "default_stability_profile": "natural",
            },
        },
        "human_change_requests": [
            {
                "request_id": "visual-only-request",
                "normalized_actions": [
                    {
                        "action": "update_visual_beat",
                        "target": {"scene_id": 1, "cut_id": 1},
                        "payload": {"visual_beat": "must remain unapplied"},
                    }
                ],
            }
        ],
        "audio_story_plan": {"schema_version": "audio_story_plan_v1", "audience_promise": "new promise"},
        "narration_spans": [
            {
                "span_id": "ns_001",
                "source_cut_ids": ["scene1_cut1"],
                "story_job": "causal_bridge",
                "audio_visual_relation": "complement",
                "tts_generation_group_id": "run_voice",
                "text": "新しい正本です。",
                "tts_text": "あたらしい せいほんです。",
            }
        ],
        "scenes": [{"scene_id": 1, "scene_summary": "script summary must not project", "time_of_day": "dawn", "cuts": [script_cut, silent_cut]}],
    }
    expected_script = deepcopy(script)
    SYNC_MODULE.reconcile_audio_story_text(expected_script)
    manifest = _base_manifest()
    # Keep an extra cut to verify the script-only silence mapping and inventory.
    _find_cut(manifest, "1", "1")["cut_contract"]["custom_visual_constraint"] = "unchanged"
    _find_cut(manifest, "1", "1")["audio"]["narration"]["tts_text"] = "old tts"
    _find_cut(manifest, "1", "1")["video_generation"]["clip_sha256"] = "sha256:video"
    manifest["scenes"][0]["cuts"].append({"cut_id": 2, "output": "assets/scenes/scene1_cut2.png", "image_generation": {"prompt": "second cut"}})
    _write_document(script_path, script)
    _write_document(manifest_path, manifest)
    before_manifest = _read_document(manifest_path)
    before_media = media_path.read_bytes()

    result = SYNC_MODULE.sync_narration(
        script_path=script_path,
        manifest_path=manifest_path,
        narration_only=True,
        assume_run_lock_held=True,
    )

    after = _read_document(manifest_path)
    assert result[0] > 0
    assert _without_narration(after) == _without_narration(before_manifest)
    assert [str(cut["cut_id"]) for cut in after["scenes"][0]["cuts"]] == ["1", "2"]
    assert after["audio_story_plan"] == expected_script["audio_story_plan"]
    assert after["narration_spans"] == expected_script["narration_spans"]

    voiced = _find_cut(after, "1", "1")["audio"]["narration"]
    assert voiced["text"] == "新しい正本です。"
    assert voiced["tts_text"] == "あたらしい せいほんです。"
    assert voiced["authoring_status"] == "human_locked"
    assert voiced["voice_id"] == "script-voice-id"
    assert voiced["voice_name"] == "Script voice"
    assert voiced["model_id"] == "eleven_v4"
    assert voiced["elevenlabs_prompt"]["stability_profile"] == "natural"
    assert voiced["source_binding"]["script_selector"] == "scene1_cut1"
    assert voiced["source_binding"]["visual_grounding_hash"].startswith("sha256:")

    silent = _find_cut(after, "1", "2")["audio"]["narration"]
    assert silent["text"] == ""
    assert silent["tts_text"] == ""
    assert silent["tool"] == "silent"
    assert silent["authoring_status"] == "silent"
    assert silent["silence_contract"] == {"intentional": True, "reason": "scripted pause"}
    assert not (tmp_path / ".locks").exists()
    assert media_path.read_bytes() == before_media


def test_narration_only_stales_old_audio_after_text_change_and_keeps_media_bytes(tmp_path: Path) -> None:
    script_path = tmp_path / "script.md"
    manifest_path = tmp_path / "video_manifest.md"
    audio_path = tmp_path / "assets" / "audio" / "old.mp3"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"previous generated audio")

    script_cut = _script_cut("更新後の正本です。", "こうしんごの せいほんです。")
    script = {
        "narration_spans": [
            {
                "span_id": "ns_001",
                "source_cut_ids": ["scene1_cut1"],
                "story_job": "causal_bridge",
                "audio_visual_relation": "complement",
                "tts_generation_group_id": "run_voice",
                "text": "更新後の正本です。",
                "tts_text": "こうしんごの せいほんです。",
            }
        ],
        "audio_story_plan": {"continuous_full_draft": "更新後の正本です。"},
        "scenes": [{"scene_id": 1, "cuts": [script_cut]}],
    }
    manifest = _base_manifest()
    cut = _find_cut(manifest, "1", "1")
    cut["audio"]["narration"].update({"output": "assets/audio/old.mp3", "status": "audio_ready"})
    manifest["narration_spans"] = deepcopy(script["narration_spans"])
    manifest["audio_story_plan"] = deepcopy(script["audio_story_plan"])
    current_context = tts_continuity_contexts(manifest)["scene1_cut1"]["tts_continuity_hash"]
    _attach_approved_audio(cut["audio"]["narration"], tts_context_hash=current_context, output="assets/audio/old.mp3")
    _write_document(script_path, script)
    _write_document(manifest_path, manifest)
    before = _read_document(manifest_path)
    before_audio = audio_path.read_bytes()

    SYNC_MODULE.sync_narration(script_path=script_path, manifest_path=manifest_path, narration_only=True)

    after = _read_document(manifest_path)
    assert _without_narration(after) == _without_narration(before)
    narration = _find_cut(after, "1", "1")["audio"]["narration"]
    assert narration["text"] == "更新後の正本です。"
    assert narration["output"] == ""
    assert narration["generation"]["status"] == "stale"
    assert narration["audio_selection"]["status"] == "unselected"
    candidate = narration["candidates"][0]
    assert candidate["status"] == "stale"
    assert candidate["output"] == "assets/audio/old.mp3"
    assert audio_path.read_bytes() == before_audio


def test_narration_only_retains_current_audio_when_canonical_narration_is_unchanged(tmp_path: Path) -> None:
    script_path = tmp_path / "script.md"
    manifest_path = tmp_path / "video_manifest.md"
    audio_path = tmp_path / "assets" / "audio" / "kept.mp3"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"approved audio remains")

    text = "同じ正本です。"
    tts_text = "おなじ せいほんです。"
    script_cut = _script_cut(text, tts_text)
    script = {
        "audio_story_plan": {"continuous_full_draft": text},
        "narration_spans": [
            {
                "span_id": "ns_001",
                "source_cut_ids": ["scene1_cut1"],
                "story_job": "causal_bridge",
                "audio_visual_relation": "complement",
                "tts_generation_group_id": "run_voice",
                "text": text,
                "tts_text": tts_text,
            }
        ],
        "scenes": [{"scene_id": 1, "cuts": [script_cut]}],
    }
    manifest = _base_manifest(text, tts_text)
    cut = _find_cut(manifest, "1", "1")
    cut["audio"]["narration"].update({"text": text, "tts_text": tts_text, "output": "assets/audio/kept.mp3"})
    manifest["audio_story_plan"] = deepcopy(script["audio_story_plan"])
    manifest["narration_spans"] = deepcopy(script["narration_spans"])
    context_hash = tts_continuity_contexts(manifest)["scene1_cut1"]["tts_continuity_hash"]
    _attach_approved_audio(cut["audio"]["narration"], tts_context_hash=context_hash, output="assets/audio/kept.mp3")
    _write_document(script_path, script)
    _write_document(manifest_path, manifest)
    before = _read_document(manifest_path)

    SYNC_MODULE.sync_narration(script_path=script_path, manifest_path=manifest_path, narration_only=True)

    after = _read_document(manifest_path)
    assert _without_narration(after) == _without_narration(before)
    narration = _find_cut(after, "1", "1")["audio"]["narration"]
    assert narration["output"] == "assets/audio/kept.mp3"
    assert narration["audio_selection"]["status"] == "selected"
    assert narration["candidates"][0]["status"] == "selected"
    assert audio_path.read_bytes() == b"approved audio remains"


def test_narration_only_reconciles_stale_nested_script_audio_from_flat_fields(tmp_path: Path) -> None:
    script_path = tmp_path / "script.md"
    manifest_path = tmp_path / "video_manifest.md"
    text = "フラット正本の新しい語りです。"
    tts_text = "ふらっと せいほんの あたらしい かたりです。"
    cut = _script_cut(text, tts_text)
    cut["narration_tool"] = "elevenlabs"
    cut["audio"] = {
        "narration": {
            "text": "古いネスト本文です。",
            "tts_text": "ふるい ねすとほんぶんです。",
            "tool": "silent",
            "authoring_status": "draft",
            "voice_settings": {"stability": 0.7},
            "delivery_note": "keep this nested delivery metadata",
        }
    }
    script = {
        "audio_story_plan": {"continuous_full_draft": "古いネスト本文です。"},
        "narration_spans": [
            {
                "span_id": "ns_001",
                "source_cut_ids": ["scene1_cut1"],
                "story_job": "causal_bridge",
                "audio_visual_relation": "complement",
                "tts_generation_group_id": "run_voice",
                "text": "古いネスト本文です。",
                "tts_text": "ふるい ねすとほんぶんです。",
            }
        ],
        "scenes": [{"scene_id": 1, "cuts": [cut]}],
    }
    manifest = _base_manifest()
    _write_document(script_path, script)
    _write_document(manifest_path, manifest)
    before = _read_document(manifest_path)

    SYNC_MODULE.sync_narration(script_path=script_path, manifest_path=manifest_path, narration_only=True)

    after = _read_document(manifest_path)
    saved_script = _read_document(script_path)
    assert _without_narration(after) == _without_narration(before)
    assert after["audio_story_plan"]["continuous_full_draft"] == text
    assert after["narration_spans"][0]["text"] == text
    assert after["narration_spans"][0]["tts_text"] == tts_text
    manifest_narration = _find_cut(after, "1", "1")["audio"]["narration"]
    assert manifest_narration["text"] == text
    assert manifest_narration["tts_text"] == tts_text
    saved_nested = _find_cut(saved_script, "1", "1")["audio"]["narration"]
    assert saved_nested["text"] == text
    assert saved_nested["tts_text"] == tts_text
    assert saved_nested["tool"] == "elevenlabs"
    assert saved_nested["authoring_status"] == "draft"
    assert saved_nested["voice_settings"] == {"stability": 0.7}
    assert saved_nested["delivery_note"] == "keep this nested delivery metadata"


def test_delivery_only_change_invalidates_approved_audio_and_uses_per_cut_settings(tmp_path: Path) -> None:
    script_path = tmp_path / "script.md"
    manifest_path = tmp_path / "video_manifest.md"
    audio_path = tmp_path / "assets" / "audio" / "approved.mp3"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(b"approved bytes stay on disk")
    text = "本文は変わりません。"
    tts_text = "ほんぶんは かわりません。"

    script_cut = _script_cut(text, tts_text)
    script_cut["language_code"] = "ja-JP"
    script_cut["pronunciation_alias_file"] = "config/per-cut-aliases.tsv"
    script = {
        "script_metadata": {
            "elevenlabs": {
                "provider": "elevenlabs",
                "language_code": "en-US",
                "pronunciation_alias_file": "config/global-aliases.tsv",
            }
        },
        "audio_story_plan": {"continuous_full_draft": text},
        "narration_spans": [
            {
                "span_id": "ns_001",
                "source_cut_ids": ["scene1_cut1"],
                "story_job": "causal_bridge",
                "audio_visual_relation": "complement",
                "tts_generation_group_id": "run_voice",
                "text": text,
                "tts_text": tts_text,
            }
        ],
        "scenes": [{"scene_id": 1, "cuts": [script_cut]}],
    }
    manifest = _base_manifest(text, tts_text)
    cut = _find_cut(manifest, "1", "1")
    narration = cut["audio"]["narration"]
    narration.update(
        {
            "text": text,
            "tts_text": tts_text,
            "language_code": "ja",
            "pronunciation_alias_file": "config/old-aliases.tsv",
            "output": "assets/audio/approved.mp3",
        }
    )
    manifest["audio_story_plan"] = deepcopy(script["audio_story_plan"])
    manifest["narration_spans"] = deepcopy(script["narration_spans"])
    context_hash = tts_continuity_contexts(manifest)["scene1_cut1"]["tts_continuity_hash"]
    _attach_approved_audio(narration, tts_context_hash=context_hash, output="assets/audio/approved.mp3")
    _write_document(script_path, script)
    _write_document(manifest_path, manifest)
    before = _read_document(manifest_path)

    SYNC_MODULE.sync_narration(script_path=script_path, manifest_path=manifest_path, narration_only=True)

    after = _read_document(manifest_path)
    assert _without_narration(after) == _without_narration(before)
    narration = _find_cut(after, "1", "1")["audio"]["narration"]
    assert narration["text"] == text
    assert narration["tts_text"] == tts_text
    assert narration["language_code"] == "ja-JP"
    assert narration["pronunciation_alias_file"] == "config/per-cut-aliases.tsv"
    assert narration["output"] == ""
    assert narration["generation"]["status"] == "stale"
    assert narration["audio_selection"]["status"] == "unselected"
    assert narration["candidates"][0]["status"] == "stale"
    assert narration["candidates"][0]["output"] == "assets/audio/approved.mp3"
    assert narration["revision"]["number"] == 1
    assert narration["revision"]["tts_revision"] == 1
    assert narration["source_binding"]["tts_revision"] == 1
    assert narration["source_binding"]["tts_request_hash"] == narration["revision"]["tts_hash"]
    assert after["narration_workflow"]["final_audio_review"]["status"] == "stale"
    assert after["narration_workflow"]["final_audio_review"]["approved_audio_set_hash"] == ""
    assert audio_path.read_bytes() == b"approved bytes stay on disk"


def test_cli_accepts_narration_only_with_assume_run_lock_held(tmp_path: Path) -> None:
    script_path = tmp_path / "script.md"
    manifest_path = tmp_path / "video_manifest.md"
    _write_document(script_path, {"scenes": [{"scene_id": 1, "cuts": [_script_cut("本文です。", "ほんぶんです。")]}]})
    manifest = _base_manifest()
    _write_document(manifest_path, manifest)
    before = _read_document(manifest_path)

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--script",
            str(script_path),
            "--manifest",
            str(manifest_path),
            "--narration-only",
            "--assume-run-lock-held",
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    after = _read_document(manifest_path)
    assert _without_narration(after) == _without_narration(before)
    assert _find_cut(after, "1", "1")["audio"]["narration"]["text"] == "本文です。"
    assert not (tmp_path / ".locks").exists()
