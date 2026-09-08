from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import image_gen_app
from server.app import app
from toc.narration_revision import apply_authoring_update


def _write_run(root: Path) -> Path:
    run_dir = root / "output" / "sample_run"
    run_dir.mkdir(parents=True)
    (run_dir / "state.txt").write_text(
        "status=SCRIPT\nslot.p710.status=done\nslot.p720.status=pending\nslot.p730.status=pending\n"
        "slot.p740.status=pending\n",
        encoding="utf-8",
    )
    (run_dir / "script.md").write_text(
        """# Script

```yaml
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        narration: ""
        tts_text: ""
```
""",
        encoding="utf-8",
    )
    (run_dir / "video_manifest.md").write_text(
        """```yaml
video_metadata:
  target_duration_seconds: 300
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          output: assets/scenes/scene1_cut1.png
        video_generation:
          duration_seconds: 8
        audio:
          narration:
            text: ""
            tts_text: ""
            tool: elevenlabs
            output: ""
            authoring_status: missing
```
""",
        encoding="utf-8",
    )
    return run_dir


def _manifest(run_dir: Path) -> dict[str, Any]:
    text = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
    return yaml.safe_load(image_gen_app._extract_manifest_yaml_text(text)) or {}


def _script(run_dir: Path) -> dict[str, Any]:
    text = (run_dir / "script.md").read_text(encoding="utf-8")
    return yaml.safe_load(image_gen_app._extract_manifest_yaml_text(text)) or {}


def _post(client: TestClient, path: str, payload: dict[str, Any]):
    response = client.post(path, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_frontend_text_save_updates_script_source_of_truth_before_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = _write_run(root)
        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch("server.image_gen_app.ROOT", root):
            with TestClient(app) as client:
                result = _post(
                    client,
                    "/api/image-gen/narration-text/save",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "text": "浦島太郎は、帰る決意をします。",
                        "tts_text": "うらしまたろうは、かえる けついを します。",
                        "tool": "elevenlabs",
                        "authoring_status": "human_locked",
                        "expected_revision": 0,
                    },
                )

        script_cut = _script(run_dir)["scenes"][0]["cuts"][0]
        latest_manifest = _manifest(run_dir)
        narration = latest_manifest["scenes"][0]["cuts"][0]["audio"]["narration"]

    assert result["item"]["revision"]["number"] == 1
    assert script_cut["narration"] == "浦島太郎は、帰る決意をします。"
    assert script_cut["tts_text"] == "うらしまたろうは、かえる けついを します。"
    assert "human_review" not in script_cut
    assert script_cut["narration_authoring"]["semantic_hash"] == narration["revision"]["text_hash"]
    assert narration["text"] == script_cut["narration"]
    assert narration["tts_text"] == script_cut["tts_text"]
    assert narration["authoring_status"] == "human_locked"


def test_frontend_text_save_rejects_stale_revision() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_run(root)
        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch("server.image_gen_app.ROOT", root):
            with TestClient(app) as client:
                payload = {
                    "run_id": "sample_run",
                    "item_id": "scene1_cut1",
                    "text": "最初の文面です。",
                    "tts_text": "さいしょの ぶんめんです。",
                    "tool": "elevenlabs",
                    "authoring_status": "draft",
                    "expected_revision": 0,
                }
                assert client.post("/api/image-gen/narration-text/save", json=payload).status_code == 200
                conflict = client.post(
                    "/api/image-gen/narration-text/save",
                    json={**payload, "text": "古いタブからの変更です。"},
                )

    assert conflict.status_code == 409


def test_narration_mutations_require_explicit_compare_and_swap_inputs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_run(root)
        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch("server.image_gen_app.ROOT", root):
            with TestClient(app) as client:
                save = client.post(
                    "/api/image-gen/narration-text/save",
                    json={
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "text": "revision必須です。",
                        "tts_text": "りびじょん ひっすです。",
                        "tool": "elevenlabs",
                        "authoring_status": "draft",
                    },
                )
                generate = client.post(
                    "/api/image-gen/narration-generate",
                    json={
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "tool": "elevenlabs",
                    },
                )
                silent = client.post(
                    "/api/image-gen/narration-silent-ok",
                    json={
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "reason": "意図的な無音",
                    },
                )

    assert save.status_code == 422
    assert generate.status_code == 422
    assert silent.status_code == 422


def test_frontend_idempotent_save_keeps_revision_and_artifacts_unchanged() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = _write_run(root)
        payload = {
            "run_id": "sample_run",
            "item_id": "scene1_cut1",
            "text": "同じ文面です。",
            "tts_text": "おなじ ぶんめんです。",
            "tool": "elevenlabs",
            "authoring_status": "human_locked",
            "expected_revision": 0,
        }
        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch("server.image_gen_app.ROOT", root):
            with TestClient(app) as client:
                first = _post(client, "/api/image-gen/narration-text/save", payload)
                script_before = (run_dir / "script.md").read_text(encoding="utf-8")
                manifest_before = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
                second = _post(
                    client,
                    "/api/image-gen/narration-text/save",
                    {**payload, "expected_revision": first["item"]["revision"]["number"]},
                )

        assert second["item"]["revision"]["number"] == 1
        assert (run_dir / "script.md").read_text(encoding="utf-8") == script_before
        assert (run_dir / "video_manifest.md").read_text(encoding="utf-8") == manifest_before


def test_frontend_save_does_not_overwrite_newer_script_source_of_truth() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = _write_run(root)
        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch("server.image_gen_app.ROOT", root):
            with TestClient(app) as client:
                first = _post(
                    client,
                    "/api/image-gen/narration-text/save",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "text": "フロントで保存した原稿です。",
                        "tts_text": "ふろんとで ほぞんした げんこうです。",
                        "tool": "elevenlabs",
                        "authoring_status": "draft",
                        "expected_revision": 0,
                    },
                )
                script_text, script_data = image_gen_app.load_structured_document(run_dir / "script.md")
                script_cut = script_data["scenes"][0]["cuts"][0]
                script_cut["narration"] = "agentが先に更新した正本です。"
                script_cut["tts_text"] = "えーじぇんとが さきに こうしんした せいほんです。"
                image_gen_app._write_manifest_data(run_dir / "script.md", script_text, script_data)
                stale_save = client.post(
                    "/api/image-gen/narration-text/save",
                    json={
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "text": "古いフロント原稿で上書き",
                        "tts_text": "ふるい ふろんとげんこうで うわがき",
                        "tool": "elevenlabs",
                        "authoring_status": "draft",
                        "expected_revision": first["item"]["revision"]["number"],
                    },
                )

        current_script = _script(run_dir)["scenes"][0]["cuts"][0]

    assert stale_save.status_code == 409
    assert current_script["narration"] == "agentが先に更新した正本です。"


def test_generation_rejects_output_path_traversal_before_provider_call() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_run(root)
        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch("server.image_gen_app.ROOT", root):
            with TestClient(app) as client:
                saved = _post(
                    client,
                    "/api/image-gen/narration-text/save",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "text": "安全な文面です。",
                        "tts_text": "あんぜんな ぶんめんです。",
                        "tool": "elevenlabs",
                        "authoring_status": "human_locked",
                        "expected_revision": 0,
                    },
                )
                revision = saved["item"]["revision"]
                rejected = client.post(
                    "/api/image-gen/narration-generate",
                    json={
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "tool": "elevenlabs",
                        "output": "../../outside.mp3",
                        "expected_revision": revision["number"],
                        "expected_tts_hash": revision["tts_hash"],
                    },
                )

    assert rejected.status_code == 400


def test_generation_success_creates_candidate_without_audio_or_human_approval() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = _write_run(root)

        async def fake_generate(run: Path, req: image_gen_app.NarrationGenerateItem) -> dict[str, Any]:
            output = image_gen_app.resolve_run_relative(run, str(req.output))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"candidate-audio")
            return {
                "itemId": req.item_id,
                "status": "completed",
                "path": str(req.output),
                "durationSeconds": 9.2,
                "debugLog": "logs/providers/narration/fake.json",
                "source": req.tool,
            }

        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch("server.image_gen_app.ROOT", root), patch(
            "server.image_gen_app._generate_narration_one", fake_generate
        ):
            with TestClient(app) as client:
                saved = _post(
                    client,
                    "/api/image-gen/narration-text/save",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "text": "帰る決意をします。",
                        "tts_text": "かえる けついを します。",
                        "tool": "elevenlabs",
                        "authoring_status": "human_locked",
                        "expected_revision": 0,
                    },
                )
                revision = saved["item"]["revision"]
                generated = _post(
                    client,
                    "/api/image-gen/narration-generate",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "tool": "elevenlabs",
                        "expected_revision": revision["number"],
                        "expected_tts_hash": revision["tts_hash"],
                    },
                )

        latest_manifest = _manifest(run_dir)
        narration = latest_manifest["scenes"][0]["cuts"][0]["audio"]["narration"]
        snapshot_exists = (run_dir / "logs/providers/narration/generation_requests/latest.json").is_file()
        request_snapshot = json.loads(
            (run_dir / "logs/providers/narration/generation_requests/latest.json").read_text(encoding="utf-8")
        )

    assert generated["item"]["status"] == "candidate"
    assert generated["item"]["candidateId"]
    assert "/candidates/" in str(generated["item"]["path"])
    assert narration["status"] == "audio_ready"
    assert narration["output"]
    assert "review" not in narration
    assert narration["audio_selection"]["status"] == "selected"
    assert narration["candidates"][0]["status"] == "candidate"
    assert snapshot_exists
    assert request_snapshot["items"][0]["provider_request"]["effective_delivery_hash"].startswith("sha256:")
    assert request_snapshot["items"][0]["provider_request"]["model_id"]


def test_elevenlabs_generation_uses_the_frozen_effective_delivery() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output = root / "voice.mp3"
        alias_path = root / "aliases.tsv"
        alias_path.write_text("surface\treading\n", encoding="utf-8")
        request = image_gen_app.NarrationGenerateItem(
            item_id="scene1_cut1",
            tool="elevenlabs",
            expected_revision=1,
            expected_tts_hash="sha256:" + "1" * 64,
            voice_id="voice-manifest",
            model_id="model-manifest",
            voice_settings={"stability": 0.25},
            output_format="mp3_44100_192",
            language_code="ja",
            pronunciation_dictionary_locators=[
                {"pronunciation_dictionary_id": "dict-1", "version_id": "version-1"}
            ],
            pronunciation_alias_path=str(alias_path),
            pronunciation_alias_source="aliases.tsv",
            pronunciation_alias_sha256="sha256:" + "2" * 64,
            effective_delivery_hash="sha256:" + "3" * 64,
            tts_generation_group_id="scene1_flow",
            previous_text="ひとつ前の語りです。",
            next_text="次の語りです。",
        )
        config_calls: list[dict[str, Any]] = []
        tts_calls: list[dict[str, Any]] = []

        def fake_config(**kwargs: Any) -> object:
            config_calls.append(kwargs)
            return object()

        class FakeClient:
            def __init__(self, _config: object):
                pass

            def tts(self, **kwargs: Any) -> bytes:
                tts_calls.append(kwargs)
                return b"audio"

        with patch("toc.providers.elevenlabs.ElevenLabsConfig.from_env", side_effect=fake_config), patch(
            "toc.providers.elevenlabs.ElevenLabsClient", FakeClient
        ):
            image_gen_app._generate_elevenlabs_audio(output, "語りです。", request)
        written = output.read_bytes()

    assert written == b"audio"
    assert config_calls[0]["voice_id"] == "voice-manifest"
    assert config_calls[0]["model_id"] == "model-manifest"
    assert tts_calls[0]["voice_settings"] == {"stability": 0.25}
    assert tts_calls[0]["pronunciation_dictionary_locators"][0]["pronunciation_dictionary_id"] == "dict-1"
    assert tts_calls[0]["previous_text"] == "ひとつ前の語りです。"
    assert tts_calls[0]["next_text"] == "次の語りです。"


def test_tts_context_uses_adjacent_cut_text_in_the_same_generation_group() -> None:
    manifest = {
        "scenes": [
            {
                "scene_id": 1,
                "cuts": [
                    {
                        "cut_id": index,
                        "audio": {
                            "narration": {
                                "tool": "elevenlabs",
                                "tts_text": text,
                                "span_refs": [
                                    {
                                        "span_id": f"ns_{index:03d}",
                                        "tts_generation_group_id": group,
                                    }
                                ],
                            }
                        },
                    }
                    for index, text, group in (
                        (1, "最初の語りです。", "story_flow"),
                        (2, "中央の語りです。", "story_flow"),
                        (3, "別の声のまとまりです。", "other_flow"),
                        (4, "最後の語りです。", "story_flow"),
                    )
                ],
            }
        ]
    }
    manifest["narration_spans"] = [
        {
            "span_id": f"ns_{index:03d}",
            "source_cut_ids": [f"scene1_cut{index}"],
            "audio_visual_relation": "complement",
            "tts_generation_group_id": group,
        }
        for index, group in ((1, "story_flow"), (2, "story_flow"), (3, "other_flow"), (4, "story_flow"))
    ]

    contexts = image_gen_app._narration_tts_context_by_selector(manifest)

    assert contexts["scene1_cut1"]["previous_text"] == ""
    assert contexts["scene1_cut1"]["next_text"] == "中央の語りです。"
    assert contexts["scene1_cut2"]["previous_text"] == "最初の語りです。"
    assert contexts["scene1_cut2"]["next_text"] == "最後の語りです。"
    assert contexts["scene1_cut4"]["previous_text"] == "中央の語りです。"
    assert contexts["scene1_cut4"]["next_text"] == ""


def test_draft_preview_stays_current_when_same_text_is_locked_during_generation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = _write_run(root)

        async def fake_generate(run: Path, req: image_gen_app.NarrationGenerateItem) -> dict[str, Any]:
            output = image_gen_app.resolve_run_relative(run, str(req.output))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"preview-audio")
            image_gen_app._save_frontend_narration_text(
                run,
                image_gen_app.NarrationTextSaveRequest(
                    run_id="sample_run",
                    item_id=req.item_id,
                    text=str(req.text),
                    tts_text=str(req.tts_text),
                    tool=req.tool,
                    authoring_status="human_locked",
                    expected_revision=1,
                ),
            )
            return {
                "itemId": req.item_id,
                "status": "completed",
                "path": str(req.output),
                "durationSeconds": 6.5,
                "debugLog": "logs/providers/narration/fake.json",
                "source": req.tool,
            }

        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch(
            "server.image_gen_app.ROOT", root
        ), patch("server.image_gen_app._generate_narration_one", fake_generate), patch(
            "server.image_gen_app._narration_duration_readiness",
            return_value={"audioReady": False},
        ):
            with TestClient(app) as client:
                saved = _post(
                    client,
                    "/api/image-gen/narration-text/save",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "text": "先に試聴する文面です。",
                        "tts_text": "さきに しちょうする ぶんめんです。",
                        "tool": "elevenlabs",
                        "authoring_status": "draft",
                        "expected_revision": 0,
                    },
                )
                first_revision = saved["item"]["revision"]
                generated = _post(
                    client,
                    "/api/image-gen/narration-generate",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "tool": "elevenlabs",
                        "expected_revision": first_revision["number"],
                        "expected_tts_hash": first_revision["tts_hash"],
                    },
                )
                current = generated["item"]
                approved = _post(
                    client,
                    "/api/image-gen/narration-audio/approve",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "candidate_id": current["candidateId"],
                        "expected_revision": 2,
                        "expected_tts_hash": first_revision["tts_hash"],
                    },
                )

        narration = _manifest(run_dir)["scenes"][0]["cuts"][0]["audio"]["narration"]

    assert generated["item"]["status"] == "candidate"
    assert generated["item"]["requestRevision"] == 1
    assert narration["revision"]["number"] == 2
    assert narration["authoring_status"] == "human_locked"
    assert approved["item"]["audioSelection"]["status"] == "selected"


def test_generation_completion_after_new_edit_is_stale_and_does_not_win() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = _write_run(root)

        async def fake_generate(run: Path, req: image_gen_app.NarrationGenerateItem) -> dict[str, Any]:
            output = image_gen_app.resolve_run_relative(run, str(req.output))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"stale-audio")
            manifest_path, original, data = image_gen_app._read_manifest_data(run)
            target = image_gen_app._target_by_item_id(data, req.item_id)
            assert target is not None
            narration = target["cut"]["audio"]["narration"]
            apply_authoring_update(
                narration,
                text="生成中に確定された新しい文面です。",
                tts_text="せいせいちゅうに かくていされた あたらしい ぶんめんです。",
                tool="elevenlabs",
                authoring_status="human_locked",
                source="frontend",
                expected_revision=1,
                now="2026-07-11T12:00:00+09:00",
            )
            image_gen_app._write_manifest_data(manifest_path, original, data)
            return {
                "itemId": req.item_id,
                "status": "completed",
                "path": str(req.output),
                "durationSeconds": 6.5,
                "debugLog": "logs/providers/narration/fake.json",
                "source": req.tool,
            }

        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch("server.image_gen_app.ROOT", root), patch(
            "server.image_gen_app._generate_narration_one", fake_generate
        ):
            with TestClient(app) as client:
                saved = _post(
                    client,
                    "/api/image-gen/narration-text/save",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "text": "古い文面です。",
                        "tts_text": "ふるい ぶんめんです。",
                        "tool": "elevenlabs",
                        "authoring_status": "human_locked",
                        "expected_revision": 0,
                    },
                )
                revision = saved["item"]["revision"]
                generated = _post(
                    client,
                    "/api/image-gen/narration-generate",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "tool": "elevenlabs",
                        "expected_revision": revision["number"],
                        "expected_tts_hash": revision["tts_hash"],
                    },
                )

        narration = _manifest(run_dir)["scenes"][0]["cuts"][0]["audio"]["narration"]

    assert generated["item"]["status"] == "stale"
    assert narration["revision"]["number"] == 2
    assert narration["output"] == ""
    assert narration["candidates"][0]["status"] == "stale"
    assert narration["audio_selection"]["status"] == "unselected"


def test_tampered_candidate_file_cannot_be_approved() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = _write_run(root)

        async def fake_generate(run: Path, req: image_gen_app.NarrationGenerateItem) -> dict[str, Any]:
            output = image_gen_app.resolve_run_relative(run, str(req.output))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"original-candidate")
            return {
                "itemId": req.item_id,
                "status": "completed",
                "path": str(req.output),
                "durationSeconds": 5.0,
                "debugLog": "logs/providers/narration/fake.json",
                "source": req.tool,
            }

        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch(
            "server.image_gen_app.ROOT", root
        ), patch("server.image_gen_app._generate_narration_one", fake_generate):
            with TestClient(app) as client:
                saved = _post(
                    client,
                    "/api/image-gen/narration-text/save",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "text": "改ざんを検知します。",
                        "tts_text": "かいざんを けんちします。",
                        "tool": "elevenlabs",
                        "authoring_status": "human_locked",
                        "expected_revision": 0,
                    },
                )
                revision = saved["item"]["revision"]
                generated = _post(
                    client,
                    "/api/image-gen/narration-generate",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "tool": "elevenlabs",
                        "expected_revision": revision["number"],
                        "expected_tts_hash": revision["tts_hash"],
                    },
                )
                candidate_path = image_gen_app.resolve_run_relative(run_dir, generated["item"]["path"])
                candidate_path.write_bytes(b"tampered-candidate")
                rejected = client.post(
                    "/api/image-gen/narration-audio/approve",
                    json={
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "candidate_id": generated["item"]["candidateId"],
                        "expected_revision": revision["number"],
                        "expected_tts_hash": revision["tts_hash"],
                    },
                )
                candidate_path.write_bytes(b"original-candidate")
                _post(
                    client,
                    "/api/image-gen/narration-audio/approve",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "candidate_id": generated["item"]["candidateId"],
                        "expected_revision": revision["number"],
                        "expected_tts_hash": revision["tts_hash"],
                    },
                )
                candidate_path.write_bytes(b"tampered-after-approval")
                readiness = image_gen_app._narration_audio_readiness(run_dir)

    assert rejected.status_code == 409
    assert readiness["ready"] is False
    assert readiness["missingItems"][0]["reason"] == "audio_file_missing_or_hash_mismatch"


def test_visual_grounding_change_invalidates_audio_until_same_text_is_rebound() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = _write_run(root)

        async def fake_generate(run: Path, req: image_gen_app.NarrationGenerateItem) -> dict[str, Any]:
            output = image_gen_app.resolve_run_relative(run, str(req.output))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"grounded-candidate")
            return {
                "itemId": req.item_id,
                "status": "completed",
                "path": str(req.output),
                "durationSeconds": 5.0,
                "debugLog": "logs/providers/narration/fake.json",
                "source": req.tool,
            }

        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch(
            "server.image_gen_app.ROOT", root
        ), patch("server.image_gen_app._generate_narration_one", fake_generate), patch(
            "server.image_gen_app._narration_duration_readiness",
            return_value={"audioReady": False},
        ):
            with TestClient(app) as client:
                saved = _post(
                    client,
                    "/api/image-gen/narration-text/save",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "text": "画面との関係も正本です。",
                        "tts_text": "がめんとの かんけいも せいほんです。",
                        "tool": "elevenlabs",
                        "authoring_status": "human_locked",
                        "expected_revision": 0,
                    },
                )
                revision = saved["item"]["revision"]
                generated = _post(
                    client,
                    "/api/image-gen/narration-generate",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "tool": "elevenlabs",
                        "expected_revision": revision["number"],
                        "expected_tts_hash": revision["tts_hash"],
                    },
                )
                _post(
                    client,
                    "/api/image-gen/narration-audio/approve",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "candidate_id": generated["item"]["candidateId"],
                        "expected_revision": revision["number"],
                        "expected_tts_hash": revision["tts_hash"],
                    },
                )

                manifest_path, original, data = image_gen_app._read_manifest_data(run_dir)
                data["scenes"][0]["cuts"][0]["image_generation"]["output"] = "assets/scenes/revised.png"
                image_gen_app._write_manifest_data(manifest_path, original, data)
                stale_items = client.get("/api/image-gen/narration-items", params={"run_id": "sample_run"})
                stale_generate = client.post(
                    "/api/image-gen/narration-generate",
                    json={
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "tool": "elevenlabs",
                        "expected_revision": revision["number"],
                        "expected_tts_hash": revision["tts_hash"],
                    },
                )
                rebound = _post(
                    client,
                    "/api/image-gen/narration-text/save",
                    {
                        "run_id": "sample_run",
                        "item_id": "scene1_cut1",
                        "text": "画面との関係も正本です。",
                        "tts_text": "がめんとの かんけいも せいほんです。",
                        "tool": "elevenlabs",
                        "authoring_status": "human_locked",
                        "expected_revision": revision["number"],
                    },
                )

        latest_manifest = _manifest(run_dir)
        narration = latest_manifest["scenes"][0]["cuts"][0]["audio"]["narration"]
        latest_target = image_gen_app._target_by_item_id(latest_manifest, "scene1_cut1")
        assert latest_target is not None
        grounding_current = image_gen_app._narration_grounding_is_current(latest_target, narration)

    assert stale_items.status_code == 200
    assert stale_items.json()["items"][0]["narrationAudioReady"] is False
    assert stale_generate.status_code == 409
    assert rebound["item"]["revision"]["number"] == 2
    assert narration["output"] == ""
    assert narration["candidates"][0]["status"] == "stale"
    assert grounding_current


def test_narration_canonical_targets_exclude_reference_and_deleted_nodes() -> None:
    data = {
        "scenes": [
            {
                "scene_id": 0,
                "image_generation": {"output": "assets/characters/hero.png"},
            },
            {
                "scene_id": 1,
                "cuts": [
                    {"cut_id": 1},
                    {"cut_id": 2, "cut_status": "deleted"},
                    {"cut_id": 3, "kind": "location_reference"},
                ],
            },
            {"scene_id": 2, "status": "deleted"},
            {"scene_id": 3},
        ]
    }

    assert [target["selector"] for target in image_gen_app._manifest_scene_targets(data)] == [
        "scene1_cut1",
        "scene3",
    ]
    assert [
        target["selector"]
        for target in image_gen_app._manifest_scene_targets(data, include_non_renderable=True)
    ] == ["scene0", "scene1_cut1", "scene1_cut2", "scene1_cut3", "scene2", "scene3"]


def test_p740_cut_timeline_synchronizes_render_units_and_detects_later_drift() -> None:
    data = {
        "scenes": [
            {
                "scene_id": 1,
                "cuts": [
                    {"cut_id": 1, "video_generation": {"duration_seconds": 8}, "audio": {"narration": {}}},
                    {"cut_id": 2, "video_generation": {"duration_seconds": 8}, "audio": {"narration": {}}},
                ],
                "render_units": [
                    {
                        "unit_id": 1,
                        "source_cut_ids": ["1", "2"],
                        "video_generation": {"duration_seconds": 16},
                    }
                ],
            }
        ]
    }

    timeline_hash = image_gen_app._apply_narration_timeline(
        data,
        [
            image_gen_app.NarrationTimelineItem(
                item_id="scene1_cut1", video_duration_seconds=10, narration_offset_seconds=0
            ),
            image_gen_app.NarrationTimelineItem(
                item_id="scene1_cut2", video_duration_seconds=12, narration_offset_seconds=1
            ),
        ],
    )

    assert timeline_hash.startswith("sha256:")
    assert data["scenes"][0]["render_units"][0]["video_generation"]["duration_seconds"] == 22
    assert image_gen_app._render_unit_timeline_issues(data) == []

    data["scenes"][0]["render_units"][0]["video_generation"]["duration_seconds"] = 21
    assert "does not match source-cut total 22s" in image_gen_app._render_unit_timeline_issues(data)[0]


def test_p740_render_units_require_exact_active_cut_coverage() -> None:
    data = {
        "scenes": [
            {
                "scene_id": 1,
                "cuts": [
                    {"cut_id": 1, "video_generation": {"duration_seconds": 8}, "audio": {"narration": {}}},
                    {"cut_id": 2, "video_generation": {"duration_seconds": 8}, "audio": {"narration": {}}},
                ],
                "render_units": [
                    {"unit_id": 1, "source_cut_ids": ["1"], "video_generation": {"duration_seconds": 8}}
                ],
            }
        ]
    }

    with pytest.raises(image_gen_app.NarrationRevisionConflict, match="active cuts missing"):
            image_gen_app._apply_narration_timeline(
            data,
            [
                image_gen_app.NarrationTimelineItem(
                    item_id="scene1_cut1", video_duration_seconds=8, narration_offset_seconds=0
                ),
                image_gen_app.NarrationTimelineItem(
                    item_id="scene1_cut2", video_duration_seconds=8, narration_offset_seconds=0
                ),
            ],
        )


def test_p740_render_units_must_preserve_canonical_cut_order() -> None:
    data = {
        "scenes": [
            {
                "scene_id": 1,
                "cuts": [
                    {"cut_id": 1, "video_generation": {"duration_seconds": 8}, "audio": {"narration": {}}},
                    {"cut_id": 2, "video_generation": {"duration_seconds": 8}, "audio": {"narration": {}}},
                ],
                "render_units": [
                    {
                        "unit_id": 1,
                        "source_cut_ids": ["2", "1"],
                        "video_generation": {"duration_seconds": 16},
                    }
                ],
            }
        ]
    }

    with pytest.raises(image_gen_app.NarrationRevisionConflict, match="canonical cut order"):
            image_gen_app._apply_narration_timeline(
            data,
            [
                image_gen_app.NarrationTimelineItem(
                    item_id="scene1_cut1", video_duration_seconds=8, narration_offset_seconds=0
                ),
                image_gen_app.NarrationTimelineItem(
                    item_id="scene1_cut2", video_duration_seconds=8, narration_offset_seconds=0
                ),
            ],
        )


def test_p740_rejects_unpartitioned_cut_over_video_generation_limit() -> None:
    data = {
        "scenes": [
            {
                "scene_id": 1,
                "cuts": [
                    {
                        "cut_id": 1,
                        "render": {"video_duration_seconds": 61},
                        "video_generation": {"duration_seconds": 61},
                    }
                ],
            }
        ]
    }

    assert "duration 61s is outside" in image_gen_app._render_unit_timeline_issues(data)[0]


def test_p740_revision_aware_spoken_audio_requires_positive_measured_duration() -> None:
    data = {
        "scenes": [
            {
                "scene_id": 1,
                "cuts": [
                    {
                        "cut_id": 1,
                        "video_generation": {"duration_seconds": 8},
                        "audio": {
                            "narration": {
                                "tool": "elevenlabs",
                                "revision": {"schema_version": image_gen_app.REVISION_SCHEMA_VERSION},
                                "audio_review": {"approved_candidate_id": "approved-without-duration"},
                                "candidates": [
                                    {
                                        "candidate_id": "approved-without-duration",
                                        "status": "human_approved",
                                        "duration_seconds": None,
                                    }
                                ],
                            }
                        },
                    }
                ],
            }
        ]
    }

    with pytest.raises(image_gen_app.NarrationRevisionConflict, match="no positive measured duration"):
        image_gen_app._apply_narration_timeline(
            data,
            [
                image_gen_app.NarrationTimelineItem(
                    item_id="scene1_cut1", video_duration_seconds=8, narration_offset_seconds=0
                )
            ],
        )


def test_p740_can_shorten_draft_cut_without_truncating_approved_audio() -> None:
    data = {
        "scenes": [
            {
                "scene_id": 1,
                "cuts": [
                    {
                        "cut_id": 1,
                        "video_generation": {"duration_seconds": 20},
                        "render": {"video_duration_seconds": 20},
                        "audio": {
                            "narration": {
                                "tool": "elevenlabs",
                                "audio_review": {"approved_candidate_id": "approved"},
                                "candidates": [
                                    {
                                        "candidate_id": "approved",
                                        "status": "human_approved",
                                        "duration_seconds": 5.2,
                                    }
                                ],
                            }
                        },
                    }
                ],
            }
        ]
    }

    image_gen_app._apply_narration_timeline(
        data,
        [
            image_gen_app.NarrationTimelineItem(
                item_id="scene1_cut1", video_duration_seconds=6, narration_offset_seconds=0
            )
        ],
    )

    assert data["scenes"][0]["cuts"][0]["video_generation"]["duration_seconds"] == 6
    assert data["scenes"][0]["cuts"][0]["render"]["video_duration_seconds"] == 6


def test_render_freeze_uses_render_unit_video_and_canonical_per_cut_audio() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = _write_run(root)
        manifest_path, original, data = image_gen_app._read_manifest_data(run_dir)
        data["scenes"] = [
            {
                "scene_id": 1,
                "cuts": [
                    {
                        "cut_id": 1,
                        "video_generation": {"duration_seconds": 4},
                        "audio": {
                            "narration": {
                                "tool": "elevenlabs",
                                "output": "assets/audio/scene1_cut1.mp3",
                                "status": "audio_ready",
                                "review": {"status": "approved"},
                            }
                        },
                    },
                    {
                        "cut_id": 2,
                        "video_generation": {"duration_seconds": 6},
                        "audio": {
                            "narration": {
                                "tool": "elevenlabs",
                                "output": "assets/audio/scene1_cut2.mp3",
                                "status": "audio_ready",
                                "review": {"status": "approved"},
                            }
                        },
                    },
                ],
                "render_units": [
                    {
                        "unit_id": 1,
                        "source_cut_ids": ["1", "2"],
                        "video_generation": {
                            "duration_seconds": 10,
                            "output": "assets/scenes/scene1_unit1.mp4",
                        },
                    }
                ],
            }
        ]
        image_gen_app._write_manifest_data(manifest_path, original, data)
        for relative, content in (
            ("assets/audio/scene1_cut1.mp3", b"audio-1"),
            ("assets/audio/scene1_cut2.mp3", b"audio-2"),
            ("assets/scenes/scene1_unit1.mp4", b"video-unit"),
        ):
            path = run_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        prepared_video: list[tuple[str, int]] = []
        prepared_audio: list[tuple[str, int, float]] = []

        def prepare_video(_run: Path, source: Path, item: image_gen_app.RenderInputItem) -> Path:
            prepared_video.append((item.item_id, item.video_duration_seconds))
            return source

        def prepare_audio(_run: Path, source: Path, item: image_gen_app.RenderInputItem) -> Path:
            prepared_audio.append((item.item_id, item.video_duration_seconds, item.narration_offset_seconds))
            return source

        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}), patch(
            "server.image_gen_app.ROOT", root
        ), patch(
            "server.image_gen_app._prepare_render_video_clip", side_effect=prepare_video
        ), patch(
            "server.image_gen_app._prepare_render_narration", side_effect=prepare_audio
        ), patch(
            "server.image_gen_app._probe_media_duration_seconds", return_value=2.0
        ):
            with TestClient(app) as client:
                response = client.post(
                    "/api/image-gen/render-inputs/freeze",
                    json={
                        "run_id": "sample_run",
                        "items": [
                            {
                                "item_id": "scene1_cut1",
                                "video_path": "assets/scenes/ignored_cut1.mp4",
                                "narration_path": "assets/audio/scene1_cut1.mp3",
                                "video_duration_seconds": 4,
                                "narration_offset_seconds": 1,
                            },
                            {
                                "item_id": "scene1_cut2",
                                "video_path": "assets/scenes/ignored_cut2.mp4",
                                "narration_path": "assets/audio/scene1_cut2.mp3",
                                "video_duration_seconds": 6,
                                "narration_offset_seconds": 0,
                            },
                        ],
                        "output": "video.mp4",
                    },
                )
        clip_list = (run_dir / "video_clips.txt").read_text(encoding="utf-8")
        narration_list = (run_dir / "video_narration_list.txt").read_text(encoding="utf-8")

    assert response.status_code == 200, response.text
    assert prepared_video == [("scene1_unit1", 10)]
    assert prepared_audio == [("scene1_cut1", 4, 1.0), ("scene1_cut2", 6, 0.0)]
    assert "scene1_unit1.mp4" in clip_list
    assert "ignored_cut" not in clip_list
    assert narration_list.index("scene1_cut1.mp3") < narration_list.index("scene1_cut2.mp3")
