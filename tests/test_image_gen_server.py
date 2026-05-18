from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
import unittest
import sys
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import yaml
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import image_gen
from server import image_gen_app
from server.app import app
from server.codex_app_server import (
    CodexAppServerClient,
    CodexAppServerError,
    _extract_prompt_from_agent_text,
    default_app_server_model,
    find_agent_message_texts,
    find_image_generation_items,
    image_generation_saved_path,
    wait_for_generated_image_after,
    wait_for_unclaimed_generated_image_after,
)
from server.image_gen_app import _toc_immersive_command, _toc_run_command, _validate_created_run, _validate_frontend_create_run, _validate_p650_run


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"


SAMPLE_REQUESTS = """# Image Generation Requests

## scene1_cut1

- tool: `codex_builtin_image`
- generation_status: `created`
- asset_type: `reusable_still`
- execution_lane: `standard`
- reference_count: `2`
- output: `assets/scenes/scene01_cut01.png`
- references:
  - `人物参照画像1`: `assets/characters/hero.png`
  - `人物参照画像2`: `assets/objects/box.png`

```text
cinematic prompt
line two
```

## scene2_cut1

- tool: `codex_builtin_image`
- reference_count: `0`
- output: `assets/scenes/scene02_cut01.png`
- references: `[]`

```text
no reference prompt
```
"""


def write_valid_p650_artifacts(root: Path, run_id: str) -> Path:
    run_dir = root / "output" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "characters").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "characters" / "hero.png").write_bytes(PNG_BYTES)
    terminal_slots = {
        "p110": "done",
        "p120": "done",
        "p130": "skipped",
        "p210": "done",
        "p220": "done",
        "p230": "skipped",
        "p310": "done",
        "p320": "skipped",
        "p330": "done",
        "p410": "done",
        "p420": "done",
        "p430": "skipped",
        "p440": "skipped",
        "p450": "done",
        "p510": "done",
        "p520": "done",
        "p530": "done",
        "p540": "skipped",
        "p550": "done",
        "p560": "done",
        "p570": "done",
        "p610": "done",
        "p620": "done",
        "p630": "skipped",
        "p640": "skipped",
        "p650": "done",
    }
    (run_dir / "state.txt").write_text(
        "\n".join(
            [
                "status=SCRIPT",
                "runtime.scaffold.content_status=authored",
                *(f"slot.{slot}.status={status}" for slot, status in terminal_slots.items()),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "research.md").write_text(
        "# リサーチ\n\n桃太郎の物語背景、登場人物、舞台、象徴性を整理した実作業済みの調査本文です。映像化に必要な時代感、鬼ヶ島の空間、主人公の動機、視聴者に伝える主題まで含みます。\n",
        encoding="utf-8",
    )
    (run_dir / "story.md").write_text(
        "# 物語\n\n映像化のために起承転結、人物の目的、対立、解決を日本語で具体化した本文です。冒頭の導入から鬼との対峙、帰還後の余韻まで、カット設計へ渡せる密度で書きます。\n",
        encoding="utf-8",
    )
    (run_dir / "visual_value.md").write_text(
        "# 映像設計\n\n画面で価値が出る中盤、参照画像戦略、再生成リスク、後続工程への引き継ぎを記述します。主人公、重要小道具、場所アンカー、色彩、照明、再利用素材の優先順位を明確にします。\n",
        encoding="utf-8",
    )
    (run_dir / "script.md").write_text(
        "# 台本\n\n各シーンのナレーション、カット構成、視覚ビートを日本語で記述した実作業済み台本です。sceneごとの目的、画面の変化、音声の意図、manifestに渡す情報を含みます。\n",
        encoding="utf-8",
    )
    (run_dir / "video_manifest.md").write_text(
        """```yaml
assets:
  character_bible:
    - character_id: hero
      reference_images:
        - assets/characters/hero.png
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 10-1
        image_generation:
          output: assets/scenes/scene10_cut1.png
      - cut_id: 10-2
        image_generation:
          output: assets/scenes/scene10_cut2.png
```
""",
        encoding="utf-8",
    )
    (run_dir / "asset_generation_requests.md").write_text(
        """# Asset Generation Requests

## hero

- tool: `codex_builtin_image`
- execution_lane: `bootstrap_builtin`
- reference_count: `0`
- output: `assets/characters/hero.png`

```text
実写映画風の主人公参照画像。顔、衣装、体格、色彩を後続カットで固定する。
```
""",
        encoding="utf-8",
    )
    (run_dir / "asset_generation_manifest.md").write_text(
        "- hero -> assets/characters/hero.png / bootstrap_builtin / generated reusable character reference for p560 validation and downstream scene prompts\n",
        encoding="utf-8",
    )
    (run_dir / "image_generation_requests.md").write_text(
        """# Image Generation Requests

## scene10_cut1

- tool: `codex_builtin_image`
- execution_lane: `standard`
- reference_count: `1`
- output: `assets/scenes/scene10_cut1.png`
- references:
  - `主人公`: `assets/characters/hero.png`

```text
実写映画風の横長16:9カット。主人公が物語の転換点に立つ。
```

## scene10_cut2

- tool: `codex_builtin_image`
- execution_lane: `standard`
- reference_count: `1`
- output: `assets/scenes/scene10_cut2.png`
- references:
  - `主人公`: `assets/characters/hero.png`

```text
実写映画風の横長16:9カット。主人公が次の行動へ踏み出す瞬間を具体的に描く。
```
""",
        encoding="utf-8",
    )
    (run_dir / "p000_index.md").write_text(
        "# Run Index\n\np650 まで到達した実作業済み run の索引です。現在位置、生成済み成果物、次に必要な確認を十分な本文量で記録します。asset request と scene image request が存在することを確認済みです。\n",
        encoding="utf-8",
    )
    return run_dir


def write_valid_p680_artifacts(root: Path, run_id: str) -> Path:
    run_dir = write_valid_p650_artifacts(root, run_id)
    (run_dir / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "scenes" / "scene10_cut1.png").write_bytes(PNG_BYTES)
    (run_dir / "assets" / "scenes" / "scene10_cut2.png").write_bytes(PNG_BYTES)
    with (run_dir / "state.txt").open("a", encoding="utf-8") as state_file:
        state_file.write(
            "\n".join(
                [
                    "slot.p660.status=done",
                    "slot.p670.status=skipped",
                    "slot.p680.status=awaiting_approval",
                    "review.image.status=pending",
                    "gate.image_review=required",
                    "",
                ]
            )
        )
    (run_dir / "p000_index.md").write_text(
        "# Run Index\n\np680 まで到達した frontend create run の索引です。asset と scene 画像生成が完了し、画像レビューはフロントで承認待ちです。state、request、review gate の状態を確認できます。\n",
        encoding="utf-8",
    )
    return run_dir


class ImageGenParserTests(unittest.TestCase):
    def test_sanitize_run_title_matches_toc_run_folder_rules(self) -> None:
        self.assertEqual(image_gen.sanitize_run_title("桃 太郎/鬼ヶ島!"), "桃_太郎_鬼_島")
        self.assertEqual(image_gen.sanitize_run_title("   "), "topic")

    def test_reserve_run_dir_uses_timestamp_and_serial_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "output" / "桃太郎_20260509_1200"
            existing.mkdir(parents=True)

            run_id, run_dir = image_gen.reserve_run_dir("桃太郎", root=root, timestamp="20260509_1200")

        self.assertEqual(run_id, "桃太郎_20260509_1200_2")
        self.assertEqual(run_dir.name, "桃太郎_20260509_1200_2")

    def test_reserve_run_dir_handles_same_minute_concurrency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def reserve() -> str:
                run_id, _run_dir = image_gen.reserve_run_dir("桃太郎", root=root, timestamp="20260509_1200")
                return run_id

            with ThreadPoolExecutor(max_workers=4) as pool:
                run_ids = list(pool.map(lambda _index: reserve(), range(4)))

        self.assertEqual(len(set(run_ids)), 4)
        self.assertIn("桃太郎_20260509_1200", run_ids)
        self.assertIn("桃太郎_20260509_1200_4", run_ids)

    def test_toc_run_command_quotes_topic_and_run_dir(self) -> None:
        command = _toc_run_command(topic='桃太郎 "鬼"', run_id="桃太郎_20260509_1200")

        self.assertEqual(command, '/toc-run "桃太郎 \\"鬼\\"" --dry-run --review-policy drafts --run-dir "output/桃太郎_20260509_1200"')

    def test_toc_run_command_keeps_source_as_single_quoted_argument(self) -> None:
        topic = '桃太郎\n/other-command --run-dir output/evil \\\\ "quoted"'
        command = _toc_run_command(topic=topic, run_id="桃太郎_20260509_1200")
        encoded_topic = command.removeprefix("/toc-run ").split(" --dry-run ", 1)[0]

        self.assertEqual(json.loads(encoded_topic), topic)
        self.assertIn("--review-policy drafts", command)
        self.assertIn("--run-dir \"output/桃太郎_20260509_1200\"", command)

    def test_toc_immersive_command_invokes_skill_with_frontend_p680_payload(self) -> None:
        topic = '桃太郎\n/other-command "quoted"'
        command = _toc_immersive_command(topic=topic, source="鬼ヶ島の資料", run_id="桃太郎_20260509_1200")

        self.assertIn("Use $toc-immersive-runner.", command)
        self.assertIn("Do not execute or depend on Claude slash commands.", command)
        payload = json.loads(command.split("Request JSON:\n", 1)[1])
        self.assertEqual(payload["topic"], topic)
        self.assertEqual(payload["source"], "鬼ヶ島の資料")
        self.assertEqual(payload["stop_target"], "p680")
        self.assertEqual(payload["experience"], "cinematic_story")
        self.assertEqual(payload["review_policy"], "frontend")
        self.assertEqual(payload["handoff"], "frontend_image_review")
        self.assertEqual(payload["run_dir"], "output/桃太郎_20260509_1200")
        self.assertEqual(payload["required_skill"], "toc-immersive-runner")
        self.assertEqual(payload["expected_skill_path"], ".codex/skills/toc-immersive-runner/SKILL.md")

    def test_toc_immersive_command_can_request_frontend_p650_handoff(self) -> None:
        command = _toc_immersive_command(topic="桃太郎", source="鬼ヶ島の資料", run_id="桃太郎_20260509_1200", stop_target="p650")

        payload = json.loads(command.split("Request JSON:\n", 1)[1])
        self.assertEqual(payload["stop_target"], "p650")
        self.assertIn("Run the canonical p100-p650 frontend-review workflow in one skill invocation.", command)

    def test_validate_created_run_requires_scaffold_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "桃太郎_20260509_1200"
            run_dir.mkdir(parents=True)
            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "state.txt"):
                    _validate_created_run("桃太郎_20260509_1200")

            (run_dir / "state.txt").write_text("status=SCRIPT\n", encoding="utf-8")
            (run_dir / "video_manifest.md").write_text("```yaml\nmanifest_phase: skeleton\n```\n", encoding="utf-8")
            with patch("server.image_gen_app.ROOT", root):
                _validate_created_run("桃太郎_20260509_1200")

    def test_validate_p650_run_accepts_real_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_p650_artifacts(root, "桃太郎_20260509_1200")

            with patch("server.image_gen_app.ROOT", root):
                _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_rejects_single_cut_scenes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            text = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            (run_dir / "video_manifest.md").write_text(
                text.replace(
                    "      - cut_id: 10-2\n        image_generation:\n          output: assets/scenes/scene10_cut2.png\n",
                    "",
                ),
                encoding="utf-8",
            )

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "requires at least 2 cuts"):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_requires_request_for_each_cut(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            text = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")
            (run_dir / "image_generation_requests.md").write_text(text.split("## scene10_cut2", 1)[0], encoding="utf-8")

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "missing scene cut requests"):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_rejects_placeholder_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            (run_dir / "state.txt").write_text(
                "runtime.scaffold.content_status=placeholder\nslot.p120.status=pending\n",
                encoding="utf-8",
            )

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "placeholder|pending"):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_uses_latest_append_only_state_for_scaffold_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            (run_dir / "state.txt").write_text(
                "runtime.scaffold.content_status=placeholder\n"
                "artifact.research.status=scaffold\n"
                "---\n"
                + state,
                encoding="utf-8",
            )
            with (run_dir / "state.txt").open("a", encoding="utf-8") as state_file:
                state_file.write("artifact.research.status=authored\n")

            with patch("server.image_gen_app.ROOT", root):
                _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_requires_asset_generation_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            (run_dir / "asset_generation_manifest.md").unlink()

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "asset_generation_manifest.md"):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_requires_every_fixed_slot_through_p650(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            (run_dir / "state.txt").write_text(state.replace("slot.p410.status=done\n", ""), encoding="utf-8")

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "missing fixed slot states .*p410"):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_rejects_pending_optional_fixed_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            (run_dir / "state.txt").write_text(state.replace("slot.p430.status=skipped", "slot.p430.status=pending"), encoding="utf-8")

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "incomplete fixed slot states .*p430=pending"):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_rejects_awaiting_approval_for_generation_ready_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            (run_dir / "state.txt").write_text(state.replace("slot.p650.status=done", "slot.p650.status=awaiting_approval"), encoding="utf-8")

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "invalid awaiting_approval fixed slots .*p650"):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_allows_awaiting_approval_for_review_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            (run_dir / "state.txt").write_text(state.replace("slot.p430.status=skipped", "slot.p430.status=awaiting_approval"), encoding="utf-8")

            with patch("server.image_gen_app.ROOT", root):
                _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_frontend_create_run_accepts_p680_review_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_p680_artifacts(root, "桃太郎_20260509_1200")

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
            ):
                _validate_frontend_create_run("桃太郎_20260509_1200")

    def test_validate_frontend_create_run_requires_scene_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p680_artifacts(root, "桃太郎_20260509_1200")
            (run_dir / "assets" / "scenes" / "scene10_cut1.png").unlink()

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "scene image generation incomplete"):
                    _validate_frontend_create_run("桃太郎_20260509_1200")

    def test_validate_frontend_create_run_rejects_missing_scene_output_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p680_artifacts(root, "桃太郎_20260509_1200")
            text = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")
            (run_dir / "image_generation_requests.md").write_text(text.replace("- output: `assets/scenes/scene10_cut1.png`\n", ""), encoding="utf-8")

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "missing scene cut requests"):
                    _validate_frontend_create_run("桃太郎_20260509_1200")

    def test_validate_frontend_create_run_rejects_invalid_scene_image_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p680_artifacts(root, "桃太郎_20260509_1200")
            (run_dir / "assets" / "scenes" / "scene10_cut1.png").write_bytes(b"not-png")

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "invalid magic bytes"):
                    _validate_frontend_create_run("桃太郎_20260509_1200")

    def test_run_toc_skill_helper_requires_visible_skill_exact_path_when_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_path = root / ".codex" / "skills" / "toc-immersive-runner" / "SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text("---\nname: toc-immersive-runner\n---\n", encoding="utf-8")

            class FakeClient:
                def __init__(self, *, cwd):
                    self.cwd = cwd

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def list_skills(self, **_kwargs):
                    return [{"name": "toc-immersive-runner", "path": str(root / "other" / "SKILL.md"), "enabled": True}]

                async def run_skill(self, **_kwargs):
                    raise AssertionError("run_skill should not be called")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.CodexAppServerClient", FakeClient),
                ):
                    with self.assertRaisesRegex(RuntimeError, "path mismatch"):
                        asyncio.run(image_gen_app._run_toc_skill_helper(topic="桃太郎", source="資料", run_id="桃太郎_20260509_1200"))

    def test_run_toc_skill_helper_allows_unsupported_skills_list_and_runs_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_path = root / ".codex" / "skills" / "toc-immersive-runner" / "SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text("---\nname: toc-immersive-runner\n---\n", encoding="utf-8")
            calls: list[dict[str, Any]] = []

            class FakeClient:
                def __init__(self, *, cwd):
                    self.cwd = cwd

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def list_skills(self, **_kwargs):
                    raise CodexAppServerError("Method not found: skills/list")

                async def run_skill(self, **kwargs):
                    calls.append(kwargs)
                    return []

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.CodexAppServerClient", FakeClient),
                ):
                    asyncio.run(image_gen_app._run_toc_skill_helper(topic="桃太郎", source="鬼ヶ島の資料", run_id="桃太郎_20260509_1200"))

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["skill_path"], skill_path)
        payload = json.loads(calls[0]["text"].split("Request JSON:\n", 1)[1])
        self.assertEqual(payload["topic"], "桃太郎")
        self.assertEqual(payload["source"], "鬼ヶ島の資料")

    def test_read_run_progress_uses_p000_stage_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "state.txt").write_text(
                "topic=ガリバー旅行記\nstatus=SCRIPT\nruntime.stage=toc_run_scaffolded\ngate.video_review=required\n",
                encoding="utf-8",
            )
            (run_dir / "p000_index.md").write_text(
                """# Run Index

## Stage Table

| P# | Stage | Current State |
| --- | --- | --- |
| `p000` | Run Entrance | `always_available` |
| `p100` | Research | `done` |
| `p200` | Story | `done` |
| `p300` | Visual Planning | `done` |
| `p500` | Asset Stage | `done` |
| `p600` | Scene Implementation / Image Stage | `done` |
| `p800` | Video Stage | `not_started` |

## Fixed Slot Contract

| Slot | Stage | Default Requirement | Purpose | Planned Artifacts |
| --- | --- | --- | --- | --- |
| `p530` | Asset Stage | `optional` | Asset Plan Authoring: author asset_plan.md | `asset_plan.md` |
| `p550` | Asset Stage | `optional` | Asset Requests: materialize asset generation requests and manifests | `asset_generation_requests.md`, `asset_generation_manifest.md` |

### p500 Asset Stage

#### p530 Asset Plan Authoring

- status: `done`
- requirement: `optional`
- purpose: author asset_plan.md

#### p550 Asset Requests

- status: `pending`
- requirement: `optional`
- purpose: materialize asset generation requests and manifests
""",
                encoding="utf-8",
            )

            progress = image_gen.read_run_progress(run_dir)

        self.assertEqual(progress["topic"], "ガリバー旅行記")
        self.assertEqual(progress["currentStage"]["code"], "p550")
        self.assertEqual(progress["doneCount"], 5)
        self.assertEqual(progress["totalCount"], 6)
        self.assertEqual(progress["percent"], 69)
        self.assertEqual(progress["pendingGates"], ["video_review"])
        self.assertEqual(progress["slots"][1]["code"], "p550")
        self.assertEqual(progress["slots"][1]["state"], "pending")
        self.assertIn("asset_generation_requests.md", progress["slots"][1]["plannedArtifacts"])

    def test_read_run_progress_moves_to_scene_requests_after_asset_requests_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "state.txt").write_text("topic=ガリバー旅行記\nstatus=SCRIPT\n", encoding="utf-8")
            (run_dir / "asset_generation_requests.md").write_text("# asset requests\n", encoding="utf-8")
            (run_dir / "p000_index.md").write_text(
                """# Run Index

## Stage Table

| P# | Stage | Current State |
| --- | --- | --- |
| `p000` | Run Entrance | `always_available` |
| `p100` | Research | `done` |
| `p500` | Asset Stage | `done` |
| `p600` | Scene Implementation / Image Stage | `done` |
| `p800` | Video Stage | `not_started` |
""",
                encoding="utf-8",
            )

            progress = image_gen.read_run_progress(run_dir)

        self.assertEqual(progress["currentStage"]["code"], "p650")
        self.assertEqual(progress["percent"], 75)

    def test_find_image_generation_items_handles_app_server_notification_shapes(self) -> None:
        message = {
            "method": "item/completed",
            "params": {
                "item": {
                    "id": "img_1",
                    "type": "imageGeneration",
                    "status": "completed",
                    "savedPath": "/tmp/generated.png",
                    "revisedPrompt": None,
                }
            },
        }

        items = find_image_generation_items(message)

        self.assertEqual(items[0]["savedPath"], "/tmp/generated.png")

    def test_find_image_generation_items_handles_nested_turn_payloads(self) -> None:
        message = {
            "params": {
                "turn": {
                    "items": [
                        {"id": "msg_1", "type": "agentMessage", "text": "done"},
                        {
                            "id": "img_2",
                            "type": "imageGeneration",
                            "status": "completed",
                            "savedPath": "/tmp/generated-2.png",
                        },
                    ]
                }
            }
        }

        items = find_image_generation_items(message)

        self.assertEqual(items[0]["savedPath"], "/tmp/generated-2.png")

    def test_image_generation_saved_path_accepts_app_server_aliases(self) -> None:
        self.assertEqual(image_generation_saved_path({"saved_path": "/tmp/generated.png"}), "/tmp/generated.png")
        self.assertEqual(image_generation_saved_path({"outputPath": "/tmp/output.png"}), "/tmp/output.png")
        self.assertEqual(image_generation_saved_path({"saved": {"path": "/tmp/nested.png"}}), "/tmp/nested.png")

    def test_generate_image_falls_back_to_generated_images_when_saved_path_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            codex_home = root / "codex_home"
            generated_dir = codex_home / "generated_images" / "session"
            generated_dir.mkdir(parents=True)
            client = CodexAppServerClient(cwd=root)

            async def fake_start_thread(**_kwargs):
                return "thread-1"

            async def fake_run_turn(**_kwargs):
                generated = generated_dir / "generated.png"
                generated.write_bytes(PNG_BYTES)
                return [{"method": "turn/completed", "params": {"turnId": "turn-1"}}]

            client.start_thread = fake_start_thread  # type: ignore[method-assign]
            client.run_turn = fake_run_turn  # type: ignore[method-assign]

            with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}):
                result = asyncio.run(
                    client.generate_image(
                        prompt="prompt",
                        output_path=run_dir / "candidate.png",
                        reference_images=[],
                        item_id="scene1",
                        run_dir=run_dir,
                    )
                )

        self.assertIsNotNone(result.saved_path)
        self.assertEqual(result.saved_path.name, "generated.png")
        self.assertEqual(result.source, "generated_images_fallback")

    def test_generate_image_returns_when_generated_image_appears_before_turn_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            codex_home = root / "codex_home"
            generated_dir = codex_home / "generated_images" / "session"
            generated_dir.mkdir(parents=True)
            client = CodexAppServerClient(cwd=root)

            async def fake_start_thread(**_kwargs):
                return "thread-1"

            async def fake_run_turn(**_kwargs):
                await asyncio.sleep(10)
                return [{"method": "turn/completed", "params": {"turnId": "turn-1"}}]

            async def create_generated_image() -> None:
                await asyncio.sleep(0.1)
                (generated_dir / "generated.png").write_bytes(PNG_BYTES)

            client.start_thread = fake_start_thread  # type: ignore[method-assign]
            client.run_turn = fake_run_turn  # type: ignore[method-assign]

            async def run_case():
                asyncio.create_task(create_generated_image())
                with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}):
                    return await asyncio.wait_for(
                        client.generate_image(
                            prompt="prompt",
                            output_path=run_dir / "candidate.png",
                            reference_images=[],
                            item_id="scene1",
                            run_dir=run_dir,
                        ),
                        timeout=3,
                    )

            result = asyncio.run(run_case())

        self.assertIsNotNone(result.saved_path)
        self.assertEqual(result.saved_path.name, "generated.png")
        self.assertEqual(result.source, "generated_images_early_fallback")

    def test_wait_for_generated_image_after_returns_stable_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generated = root / "session" / "generated.png"
            generated.parent.mkdir(parents=True)
            cutoff = 0

            async def run_case() -> Path | None:
                generated.write_bytes(PNG_BYTES)
                return await wait_for_generated_image_after(cutoff, root=root, timeout_seconds=2, poll_seconds=0.1)

            result = asyncio.run(run_case())

        self.assertEqual(result, generated)

    def test_unclaimed_generated_image_wait_assigns_distinct_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "session" / "first.png"
            second = root / "session" / "second.png"
            first.parent.mkdir(parents=True)

            async def run_case() -> tuple[Path | None, Path | None]:
                async def create_files() -> None:
                    await asyncio.sleep(0.1)
                    first.write_bytes(PNG_BYTES)
                    await asyncio.sleep(0.2)
                    second.write_bytes(PNG_BYTES)

                asyncio.create_task(create_files())
                return await asyncio.gather(
                    wait_for_unclaimed_generated_image_after(0, root=root, timeout_seconds=3, poll_seconds=0.1),
                    wait_for_unclaimed_generated_image_after(0, root=root, timeout_seconds=3, poll_seconds=0.1),
                )

            claimed = asyncio.run(run_case())

        self.assertEqual({path.name for path in claimed if path}, {"first.png", "second.png"})

    def test_default_app_server_model_avoids_user_config_model(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(default_app_server_model(), "")

    def test_default_app_server_model_can_be_overridden(self) -> None:
        with patch.dict(os.environ, {"TOC_CODEX_APP_SERVER_MODEL": "gpt-5.4"}):
            self.assertEqual(default_app_server_model(), "gpt-5.4")

    def test_run_turn_raises_on_failed_turn(self) -> None:
        async def run() -> None:
            client = CodexAppServerClient(cwd=Path("/tmp"))

            async def fake_request(_method, _params=None):
                return {"turn": {"id": "turn-1"}}

            client.request = fake_request  # type: ignore[method-assign]
            await client._notifications.put(
                {
                    "method": "turn/completed",
                    "params": {
                        "turnId": "turn-1",
                        "turn": {"id": "turn-1", "status": "failed", "error": {"message": "model unsupported"}},
                    },
                }
            )

            with self.assertRaisesRegex(CodexAppServerError, "model unsupported"):
                await client.run_turn(thread_id="thread-1", text="hello", timeout_seconds=1)

        asyncio.run(run())

    def test_run_turn_fails_fast_on_approval_request(self) -> None:
        async def run() -> None:
            client = CodexAppServerClient(cwd=Path("/tmp"))

            async def fake_request(_method, _params=None):
                return {"turn": {"id": "turn-1"}}

            client.request = fake_request  # type: ignore[method-assign]
            await client._notifications.put({"method": "approval/requested", "params": {"turnId": "turn-1"}})

            with self.assertRaisesRegex(CodexAppServerError, "interactive approval"):
                await client.run_turn(thread_id="thread-1", text="hello", timeout_seconds=1)

        asyncio.run(run())

    def test_run_skill_uses_never_approval_policy_and_skill_item(self) -> None:
        async def run() -> list[tuple[str, dict]]:
            client = CodexAppServerClient(cwd=Path("/repo"))
            calls: list[tuple[str, dict]] = []

            async def fake_request(method, params=None):
                calls.append((method, params or {}))
                if method == "thread/start":
                    return {"thread": {"id": "thread-1"}}
                if method == "turn/start":
                    return {"turn": {"id": "turn-1"}}
                return {}

            client.request = fake_request  # type: ignore[method-assign]
            await client._notifications.put(
                {"method": "turn/completed", "params": {"turnId": "turn-1", "turn": {"id": "turn-1", "status": "completed"}}}
            )
            await client.run_skill(
                text="Use $toc-immersive-runner.",
                skill_path=Path("/repo/.codex/skills/toc-immersive-runner/SKILL.md"),
                cwd=Path("/repo"),
                timeout_seconds=1,
            )
            return calls

        calls = asyncio.run(run())

        self.assertEqual(calls[0][0], "thread/start")
        self.assertEqual(calls[0][1]["approvalPolicy"], "never")
        self.assertEqual(calls[1][0], "turn/start")
        self.assertEqual(
            calls[1][1]["input"],
            [
                {"type": "text", "text": "Use $toc-immersive-runner."},
                {
                    "type": "skill",
                    "name": "toc-immersive-runner",
                    "path": "/repo/.codex/skills/toc-immersive-runner/SKILL.md",
                },
            ],
        )

    def test_find_agent_message_texts_handles_nested_turn_payloads(self) -> None:
        message = {
            "params": {
                "turn": {
                    "items": [
                        {"id": "msg_1", "type": "agentMessage", "text": '{"prompt": "nested prompt"}'},
                    ]
                }
            }
        }

        messages = find_agent_message_texts(message)

        self.assertEqual(messages, ['{"prompt": "nested prompt"}'])

    def test_extract_prompt_from_agent_text_accepts_json_fence(self) -> None:
        prompt = _extract_prompt_from_agent_text('```json\n{"prompt": "new prompt"}\n```')

        self.assertEqual(prompt, "new prompt")

    def test_parse_request_markdown_extracts_prompt_refs_and_lane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "assets/scenes").mkdir(parents=True)
            (run_dir / "assets/scenes/scene01_cut01.png").write_bytes(b"image")

            items = image_gen.parse_request_markdown(SAMPLE_REQUESTS, kind="scene", run_dir=run_dir)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].id, "scene1_cut1")
        self.assertEqual(items[0].asset_type, "reusable_still")
        self.assertEqual(items[0].prompt, "cinematic prompt\nline two")
        self.assertEqual(items[0].references, ["assets/characters/hero.png", "assets/objects/box.png"])
        self.assertEqual(items[0].reference_count, 2)
        self.assertEqual(items[0].execution_lane, "standard")
        self.assertEqual(items[0].existing_image, "assets/scenes/scene01_cut01.png")
        self.assertEqual(items[1].reference_count, 0)
        self.assertEqual(items[1].execution_lane, "bootstrap_builtin")

    def test_parse_request_markdown_extracts_inline_prompt_metadata(self) -> None:
        request_text = """# Image Generation Requests

## scene 10: 灰の台所

- output: `assets/scenes/scene10.png`
- references:
  - `assets/characters/cinderella_work_ref.png`
- prompt: 夜明け前の古い台所。シンデレラが暖炉の灰をかき出す。

## scene 20: 続き

- output: `assets/scenes/scene20.png`
- reference_count: `0`
- prompt: |
  月明かりの庭。
  魔法の変化。
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            items = image_gen.parse_request_markdown(request_text, kind="scene", run_dir=run_dir)

        self.assertEqual(items[0].id, "scene 10: 灰の台所")
        self.assertEqual(items[0].prompt, "夜明け前の古い台所。シンデレラが暖炉の灰をかき出す。")
        self.assertEqual(items[0].references, ["assets/characters/cinderella_work_ref.png"])
        self.assertEqual(items[1].prompt, "|\n月明かりの庭。\n魔法の変化。")
        self.assertEqual(items[1].execution_lane, "bootstrap_builtin")

    def test_parse_asset_request_keeps_output_after_empty_references(self) -> None:
        request_text = """# Asset Generation Requests

## cinderella_common

- asset_id: `cinderella_common`
- asset_type: `character_reference`
- tool: `codex_builtin_image`
- execution_lane: `bootstrap_builtin`
- reference_count: `0`
- references: `[]`
- review_status: `approved`
- output: `assets/characters/cinderella_common.png`

```text
実写映画風のキャラクター参照画像。
```

## cinderella_ball_gown

- asset_id: `cinderella_ball_gown`
- asset_type: `character_reference`
- tool: `codex_builtin_image`
- execution_lane: `standard`
- reference_count: `1`
- references:
  - `assets/characters/cinderella_common.png`
- review_status: `approved`
- output: `assets/characters/cinderella_ball_gown.png`

```text
同じ人物の舞踏会衣装。
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "assets/characters").mkdir(parents=True)
            (run_dir / "assets/characters/cinderella_common.png").write_bytes(PNG_BYTES)
            items = image_gen.parse_request_markdown(request_text, kind="asset", run_dir=run_dir)

        self.assertEqual(items[0].output, "assets/characters/cinderella_common.png")
        self.assertEqual(items[0].references, [])
        self.assertEqual(items[0].existing_image, "assets/characters/cinderella_common.png")
        self.assertEqual(items[1].output, "assets/characters/cinderella_ball_gown.png")
        self.assertEqual(items[1].references, ["assets/characters/cinderella_common.png"])

    def test_prompt_setting_markers_read_and_replace_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setting_path = root / "docs/implementation/image-prompting.md"
            setting_path.parent.mkdir(parents=True)
            setting_path.write_text(
                "# Image Prompting\n\n"
                "<!-- image-gen-setting:scene:start -->\n"
                "old scene instruction\n"
                "<!-- image-gen-setting:scene:end -->\n",
                encoding="utf-8",
            )

            current = image_gen.read_prompt_setting("scene", root=root)
            result = image_gen.write_prompt_setting("scene", "new scene instruction", root=root)
            updated_text = setting_path.read_text(encoding="utf-8")

        self.assertEqual(current["content"], "old scene instruction")
        self.assertEqual(result["content"], "new scene instruction")
        self.assertIn("new scene instruction", updated_text)
        self.assertNotIn("old scene instruction", updated_text)

    def test_prompt_setting_replacement_preserves_backslashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setting_path = root / "docs/implementation/image-prompting.md"
            setting_path.parent.mkdir(parents=True)
            setting_path.write_text(
                "<!-- image-gen-setting:scene:start -->\nold\n<!-- image-gen-setting:scene:end -->\n",
                encoding="utf-8",
            )

            result = image_gen.write_prompt_setting("scene", r"keep \1 literally", root=root)

        self.assertEqual(result["content"], r"keep \1 literally")

    def test_update_request_prompts_replaces_only_target_prompt_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "image_generation_requests.md").write_text(SAMPLE_REQUESTS, encoding="utf-8")

            result = image_gen.update_request_prompts(
                run_dir,
                "scene",
                {"scene1_cut1": "updated prompt\nline two"},
            )
            updated = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")

        self.assertEqual(result["updated"], ["scene1_cut1"])
        self.assertEqual(result["missing"], [])
        self.assertIn("updated prompt\nline two", updated)
        self.assertIn("no reference prompt", updated)
        self.assertNotIn("cinematic prompt\nline two", updated)

    def test_update_request_prompts_does_not_cross_into_next_section(self) -> None:
        malformed = """# Image Generation Requests

## scene1_cut1

- output: `assets/scenes/scene01.png`

## scene2_cut1

- output: `assets/scenes/scene02.png`

```text
scene two prompt
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "image_generation_requests.md").write_text(malformed, encoding="utf-8")

            result = image_gen.update_request_prompts(run_dir, "scene", {"scene1_cut1": "must not replace scene two"})
            updated = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")

        self.assertEqual(result["updated"], [])
        self.assertEqual(result["missing"], ["scene1_cut1"])
        self.assertIn("scene two prompt", updated)
        self.assertNotIn("must not replace scene two", updated)

    def test_update_request_prompts_is_atomic_when_any_requested_item_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request_file = run_dir / "image_generation_requests.md"
            request_file.write_text(SAMPLE_REQUESTS, encoding="utf-8")

            result = image_gen.update_request_prompts(
                run_dir,
                "scene",
                {"scene1_cut1": "updated prompt", "missing": "ignored"},
            )
            updated = request_file.read_text(encoding="utf-8")

        self.assertEqual(result["updated"], [])
        self.assertEqual(result["missing"], ["missing"])
        self.assertIn("cinematic prompt\nline two", updated)
        self.assertNotIn("updated prompt", updated)

    def test_reference_options_use_extensionless_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "assets/characters").mkdir(parents=True)
            (run_dir / "assets/characters/hero.png").write_bytes(b"png")
            (run_dir / "assets/characters/hero.txt").write_text("ignore", encoding="utf-8")

            refs = image_gen.list_reference_options(run_dir)

        self.assertEqual([r.path for r in refs], ["assets/characters/hero.png"])
        self.assertEqual([r.label for r in refs], ["hero"])

    def test_list_candidate_items_returns_existing_candidate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            candidate = run_dir / "assets/test/image_gen_candidates/scene1/candidate_01.png"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(PNG_BYTES)

            candidates = image_gen.list_candidate_items(run_dir, "scene1")

        self.assertEqual(candidates[0]["path"], "assets/test/image_gen_candidates/scene1/candidate_01.png")
        self.assertEqual(candidates[0]["status"], "completed")
        self.assertIn("mtimeMs", candidates[0])

    def test_insert_candidate_backs_up_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            candidate = run_dir / "assets/test/image_gen_candidates/scene1/candidate_01.png"
            output = run_dir / "assets/scenes/scene01.png"
            candidate.parent.mkdir(parents=True)
            output.parent.mkdir(parents=True)
            candidate.write_bytes(PNG_BYTES)
            output.write_bytes(b"old")

            result = image_gen.insert_candidate(run_dir, candidate, "assets/scenes/scene01.png")

            self.assertEqual(output.read_bytes(), PNG_BYTES)
            self.assertIsNotNone(result["backup"])
            self.assertTrue((run_dir / str(result["backup"])).exists())

    def test_insert_candidate_rejects_non_candidate_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "assets/scenes/other.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"not a candidate")

            with self.assertRaises(ValueError):
                image_gen.insert_candidate(run_dir, source, "assets/scenes/scene01.png")

    def test_insert_candidate_rejects_non_assets_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            candidate = run_dir / "assets/test/image_gen_candidates/scene1/candidate_01.png"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(PNG_BYTES)

            with self.assertRaises(ValueError):
                image_gen.insert_candidate(run_dir, candidate, "video_manifest.md")


class ImageGenApiTests(unittest.TestCase):
    def setUp(self) -> None:
        image_gen_app._create_jobs.clear()

    def tearDown(self) -> None:
        image_gen_app._create_jobs.clear()

    def _poll_create_job(self, client: TestClient, job_id: str) -> dict:
        payload = {}
        for _ in range(50):
            response = client.get(f"/api/image-gen/runs/create/{job_id}")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            if payload["status"] in {"completed", "failed"}:
                return payload
            time.sleep(0.02)
        self.fail("create job did not finish")

    def test_runs_endpoint_lists_output_folders(self) -> None:
        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
            with TestClient(app) as client:
                response = client.get("/api/image-gen/runs")

        self.assertEqual(response.status_code, 200)
        self.assertIn("runs", response.json())

    def test_api_requires_token_when_not_configured(self) -> None:
        with patch.dict(os.environ, {"TOC_SERVER_TOKEN": "", "TOC_SERVER_AUTH_DISABLED": ""}):
            with TestClient(app) as client:
                response = client.get("/api/image-gen/runs")

        self.assertEqual(response.status_code, 401)

    def test_toc_skill_helper_returns_when_p650_contract_is_reached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            cancelled: list[bool] = []

            async def fake_toc_skill_helper(*, topic, source=None, run_id, stop_target="p680"):
                write_valid_p650_artifacts(root, run_id)
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.append(True)

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.CREATE_SKILL_STOP_POLL_SECONDS", 0.01),
                patch("server.image_gen_app.CREATE_SKILL_CANCEL_TIMEOUT_SECONDS", 0.01),
                patch("server.image_gen_app._run_toc_skill_helper", fake_toc_skill_helper),
            ):
                asyncio.run(
                    image_gen_app._run_toc_skill_helper_until_stop_target(
                        topic="桃太郎",
                        source="桃太郎",
                        run_id=run_id,
                        stop_target="p650",
                    )
                )

            state = image_gen_app.parse_state_file(root / "output" / run_id / "state.txt")

        self.assertEqual(state["runtime.app_server_skill.stop_target"], "p650")
        self.assertEqual(state["runtime.app_server_skill.stop_detected"], "true")
        self.assertEqual(cancelled, [True])

    def test_create_run_endpoint_uses_title_as_blank_source_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls: list[tuple[str, str, str | None, str]] = []
            events: list[tuple[str, str | None]] = []

            async def fake_toc_run_helper(*, topic, source=None, run_id, stop_target="p680"):
                calls.append((topic, run_id, source, stop_target))
                events.append(("skill", stop_target))
                write_valid_p650_artifacts(root, run_id)

            async def fake_upgrade_prompts(_job_id, *, run_id):
                events.append(("upgrade", run_id))

            async def fake_generate_images(_job_id, *, run_id):
                events.append(("generate", run_id))
                write_valid_p680_artifacts(root, run_id)

            generate_images = AsyncMock(side_effect=fake_generate_images)
            upgrade_prompts = AsyncMock(side_effect=fake_upgrade_prompts)
            validate_review = Mock()
            rebuild_index = AsyncMock()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen.time.strftime", return_value="20260509_1200"),
                    patch("server.image_gen_app._run_toc_skill_helper", fake_toc_run_helper),
                    patch("server.image_gen_app._generate_create_images", generate_images),
                    patch("server.image_gen_app._upgrade_initial_request_prompts", upgrade_prompts),
                    patch("server.image_gen_app._validate_image_review_ready", validate_review),
                    patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
                    patch("server.image_gen_app._rebuild_run_index", rebuild_index),
                ):
                    with TestClient(app) as client:
                        create_response = client.post(
                            "/api/image-gen/runs/create",
                            json={"title": "桃太郎", "source": "   "},
                        )
                        create_payload = create_response.json()
                        final_payload = self._poll_create_job(client, create_payload["jobId"])

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_payload["runId"], "桃太郎_20260509_1200")
        self.assertEqual(create_payload["path"], "output/桃太郎_20260509_1200")
        self.assertNotIn("source", create_payload)
        self.assertEqual(final_payload["status"], "completed")
        self.assertEqual(calls, [("桃太郎", "桃太郎_20260509_1200", "桃太郎", "p650")])
        self.assertEqual(events, [("skill", "p650"), ("upgrade", "桃太郎_20260509_1200"), ("generate", "桃太郎_20260509_1200")])
        generate_images.assert_awaited_once()
        upgrade_prompts.assert_awaited_once()
        validate_review.assert_not_called()
        rebuild_index.assert_not_awaited()

    def test_create_run_endpoint_passes_title_and_nonblank_source_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls: list[tuple[str, str, str | None, str]] = []
            events: list[tuple[str, str | None]] = []

            async def fake_toc_run_helper(*, topic, source=None, run_id, stop_target="p680"):
                calls.append((topic, run_id, source, stop_target))
                events.append(("skill", stop_target))
                write_valid_p650_artifacts(root, run_id)

            async def fake_upgrade_prompts(_job_id, *, run_id):
                events.append(("upgrade", run_id))

            async def fake_generate_images(_job_id, *, run_id):
                events.append(("generate", run_id))
                write_valid_p680_artifacts(root, run_id)

            generate_images = AsyncMock(side_effect=fake_generate_images)
            upgrade_prompts = AsyncMock(side_effect=fake_upgrade_prompts)
            validate_review = Mock()
            rebuild_index = AsyncMock()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen.time.strftime", return_value="20260509_1200"),
                    patch("server.image_gen_app._run_toc_skill_helper", fake_toc_run_helper),
                    patch("server.image_gen_app._generate_create_images", generate_images),
                    patch("server.image_gen_app._upgrade_initial_request_prompts", upgrade_prompts),
                    patch("server.image_gen_app._validate_image_review_ready", validate_review),
                    patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
                    patch("server.image_gen_app._rebuild_run_index", rebuild_index),
                ):
                    with TestClient(app) as client:
                        create_response = client.post(
                            "/api/image-gen/runs/create",
                            json={"title": "桃太郎", "source": "鬼ヶ島の資料"},
                        )
                        create_payload = create_response.json()
                        final_payload = self._poll_create_job(client, create_payload["jobId"])

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_payload["runId"], "桃太郎_20260509_1200")
        self.assertEqual(final_payload["status"], "completed")
        self.assertEqual(calls, [("桃太郎", "桃太郎_20260509_1200", "鬼ヶ島の資料", "p650")])
        self.assertEqual(events, [("skill", "p650"), ("upgrade", "桃太郎_20260509_1200"), ("generate", "桃太郎_20260509_1200")])
        generate_images.assert_awaited_once()
        upgrade_prompts.assert_awaited_once()
        validate_review.assert_not_called()
        rebuild_index.assert_not_awaited()

    def test_generate_create_images_writes_scene_outputs_and_review_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            saved = root / "generated.png"
            saved.write_bytes(PNG_BYTES)
            generated: list[tuple[str, list[str]]] = []

            class FakeResult:
                saved_path = saved
                revised_prompt = None
                status = "completed"
                transcript = []
                source = "test"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    generated.append((kwargs["item_id"], [path.name for path in kwargs["reference_images"]]))
                    return FakeResult()

            validate_asset_gate = Mock()
            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.CodexAppServerClient", FakeClient),
                    patch("server.image_gen_app._validate_p560_asset_quality", validate_asset_gate),
                ):
                    asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            scene_exists = (run_dir / "assets/scenes/scene10_cut1.png").exists()

        self.assertTrue(scene_exists)
        self.assertEqual(generated, [("scene10_cut1", ["hero.png"]), ("scene10_cut2", ["hero.png"])])
        validate_asset_gate.assert_called_once()
        self.assertEqual(validate_asset_gate.call_args.args[0].resolve(), run_dir.resolve())
        self.assertIn("slot.p660.status=done", state)
        self.assertIn("slot.p680.status=awaiting_approval", state)
        self.assertIn("review.image.status=pending", state)

    def test_build_generation_groups_layers_reference_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request_file = run_dir / "asset_generation_requests.md"
            request_file.write_text(
                """# Asset Generation Requests

## base_a

- output: `assets/characters/base_a.png`
- references: `[]`

```text
base a prompt
```

## base_b

- output: `assets/characters/base_b.png`
- references: `[]`

```text
base b prompt
```

## variant

- output: `assets/characters/variant.png`
- references:
  - `base`: `assets/characters/base_a.png`

```text
variant prompt
```

## final

- output: `assets/characters/final.png`
- references:
  - `variant`: `assets/characters/variant.png`
  - `base b`: `assets/characters/base_b.png`

```text
final prompt
```
""",
                encoding="utf-8",
            )
            items = image_gen.load_request_items(run_dir, "asset")

            groups = image_gen_app._build_generation_groups(items, run_dir=run_dir, kind="asset")

        self.assertEqual([[item.id for item in group] for group in groups], [["base_a", "base_b"], ["variant"], ["final"]])

    def test_build_generation_groups_rejects_missing_reference_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "asset_generation_requests.md").write_text(
                """# Asset Generation Requests

## orphan

- output: `assets/characters/orphan.png`
- references:
  - `missing`: `assets/characters/missing.png`

```text
orphan prompt
```
""",
                encoding="utf-8",
            )
            items = image_gen.load_request_items(run_dir, "asset")

            with self.assertRaisesRegex(RuntimeError, "asset reference not found"):
                image_gen_app._build_generation_groups(items, run_dir=run_dir, kind="asset")

    def test_build_generation_groups_rejects_reference_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "asset_generation_requests.md").write_text(
                """# Asset Generation Requests

## a

- output: `assets/characters/a.png`
- references:
  - `b`: `assets/characters/b.png`

```text
a prompt
```

## b

- output: `assets/characters/b.png`
- references:
  - `a`: `assets/characters/a.png`

```text
b prompt
```
""",
                encoding="utf-8",
            )
            items = image_gen.load_request_items(run_dir, "asset")

            with self.assertRaisesRegex(RuntimeError, "cyclic reference dependencies"):
                image_gen_app._build_generation_groups(items, run_dir=run_dir, kind="asset")

    def test_generate_request_outputs_runs_same_group_items_in_parallel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "asset_generation_requests.md").write_text(
                """# Asset Generation Requests

## base_a

- output: `assets/characters/base_a.png`
- references: `[]`

```text
base a prompt
```

## base_b

- output: `assets/characters/base_b.png`
- references: `[]`

```text
base b prompt
```
""",
                encoding="utf-8",
            )
            active = 0
            peak = 0
            generated: list[str] = []

            async def fake_generate_item(*, run_dir, kind, item):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0.01)
                output = run_dir / item.output
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(PNG_BYTES)
                generated.append(item.id)
                active -= 1

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app._generate_request_item_output", fake_generate_item):
                    asyncio.run(image_gen_app._generate_request_outputs(run_dir=run_dir, kind="asset"))

        self.assertEqual(set(generated), {"base_a", "base_b"})
        self.assertEqual(peak, 2)

    def test_generate_create_images_retries_bootstrap_assets_until_gate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            write_valid_p650_artifacts(root, run_id)
            generated_kinds: list[str] = []
            repair_prompts = AsyncMock()
            gate = Mock(side_effect=[RuntimeError("bootstrap asset visual gate failed"), RuntimeError("bootstrap asset visual gate failed"), None])

            async def fake_generate_request_outputs(*, run_dir, kind):
                generated_kinds.append(kind)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._generate_request_outputs", fake_generate_request_outputs),
                    patch("server.image_gen_app._validate_p560_asset_quality", gate),
                    patch("server.image_gen_app._repair_bootstrap_asset_prompts", repair_prompts),
                    patch("server.image_gen_app._remove_bootstrap_asset_outputs", Mock()),
                ):
                    result = asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

        self.assertTrue(result)
        self.assertEqual(generated_kinds, ["asset", "asset", "asset", "scene"])
        self.assertEqual(gate.call_count, 3)
        self.assertEqual(repair_prompts.await_count, 2)

    def test_generate_create_images_sends_to_frontend_after_ten_failed_asset_repairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            generated_kinds: list[str] = []
            repair_prompts = AsyncMock()

            async def fake_generate_request_outputs(*, run_dir, kind):
                generated_kinds.append(kind)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._generate_request_outputs", fake_generate_request_outputs),
                    patch("server.image_gen_app._validate_p560_asset_quality", Mock(side_effect=RuntimeError("bootstrap asset visual gate failed"))),
                    patch("server.image_gen_app._repair_bootstrap_asset_prompts", repair_prompts),
                    patch("server.image_gen_app._remove_bootstrap_asset_outputs", Mock()),
                ):
                    result = asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = (run_dir / "state.txt").read_text(encoding="utf-8")

        self.assertFalse(result)
        self.assertEqual(generated_kinds, ["asset"] * 10 + ["scene"])
        self.assertEqual(repair_prompts.await_count, 9)
        self.assertIn("review.asset_visual_gate.status=needs_frontend_review", state)
        self.assertIn("review.asset_visual_gate.attempts=10", state)

    def test_generate_create_images_fails_when_scene_generation_has_no_saved_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            write_valid_p650_artifacts(root, run_id)

            class FakeResult:
                saved_path = None
                revised_prompt = None
                status = "missing"
                transcript = []
                source = "test"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **_kwargs):
                    return FakeResult()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.CodexAppServerClient", FakeClient),
                    patch("server.image_gen_app._validate_p560_asset_quality", Mock()),
                ):
                    with self.assertRaisesRegex(RuntimeError, "did not return an image"):
                        asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

    def test_create_run_endpoint_fails_when_app_server_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "TOC_IMAGE_GEN_DISABLE_CODEX_APP_SERVER": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen.time.strftime", return_value="20260509_1200"),
                ):
                    with TestClient(app) as client:
                        create_response = client.post(
                            "/api/image-gen/runs/create",
                            json={"title": "桃太郎"},
                        )
                        create_payload = create_response.json()
                        final_payload = self._poll_create_job(client, create_payload["jobId"])

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(final_payload["status"], "failed")
        self.assertEqual(final_payload["error"], "ToC作成に失敗しました")

    def test_create_run_helper_creates_scaffold_with_draft_policy(self) -> None:
        run_id = "helper_debug_20260509_1200"
        with patch("server.image_gen_app.ROOT", Path.cwd()):
            output = asyncio.run(image_gen_app._run_toc_run_helper(topic="helper_debug", run_id=run_id))
        run_dir = Path.cwd() / "output" / run_id
        try:
            state = (run_dir / "state.txt").read_text(encoding="utf-8")

            self.assertIn("Run dir:", output)
            self.assertTrue((run_dir / "video_manifest.md").exists())
            self.assertIn("runtime.review_policy=drafts", state)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_create_run_endpoint_reports_failed_when_scaffold_artifacts_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            async def fake_toc_run_helper(**_kwargs):
                return "did not scaffold"

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen.time.strftime", return_value="20260509_1200"),
                    patch("server.image_gen_app._run_toc_skill_helper", fake_toc_run_helper),
                ):
                    with TestClient(app) as client:
                        create_response = client.post(
                            "/api/image-gen/runs/create",
                            json={"title": "桃太郎", "source": "鬼ヶ島"},
                        )
                        create_payload = create_response.json()
                        final_payload = self._poll_create_job(client, create_payload["jobId"])

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(final_payload["status"], "failed")
        self.assertEqual(final_payload["error"], "ToC作成に失敗しました")
        self.assertNotIn("missing state.txt", str(final_payload))
        self.assertFalse((root / "output" / "桃太郎_20260509_1200").exists())

    def test_create_run_endpoint_rejects_blank_title_and_running_job_overflow(self) -> None:
        async def stay_running_briefly(*_args, **_kwargs):
            await asyncio.sleep(0.5)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            async def slow_toc_run_helper(**_kwargs):
                await stay_running_briefly()
                return ""

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.MAX_RUNNING_CREATE_JOBS", 1),
                    patch("server.image_gen_app._run_toc_skill_helper", slow_toc_run_helper),
                ):
                    with TestClient(app) as client:
                        blank_response = client.post("/api/image-gen/runs/create", json={"title": "   "})
                        first_response = client.post("/api/image-gen/runs/create", json={"title": "桃太郎"})
                        overflow_response = client.post("/api/image-gen/runs/create", json={"title": "浦島太郎"})

        self.assertEqual(blank_response.status_code, 400)
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(overflow_response.status_code, 429)

    def test_generate_uses_saved_path_and_does_not_scan_latest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            saved = Path(tmp) / "generated.png"
            saved.write_bytes(PNG_BYTES)

            class FakeResult:
                saved_path = saved
                revised_prompt = None
                status = "completed"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **_kwargs):
                    return FakeResult()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", Path(tmp)), patch("server.image_gen_app.CodexAppServerClient", FakeClient):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/generate",
                            json={
                                "run_id": "sample_run",
                                "kind": "scene",
                                "item_id": "scene1_cut1",
                                "prompt": "prompt",
                                "references": [],
                                "candidate_count": 1,
                            },
                        )

            self.assertEqual(response.status_code, 200)
            path = response.json()["candidates"][0]["path"]
            self.assertEqual((run_dir / path).read_bytes(), PNG_BYTES)

    def test_generate_runs_candidate_count_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            saved = Path(tmp) / "generated.png"
            saved.write_bytes(PNG_BYTES)
            active = 0
            peak = 0

            class FakeResult:
                saved_path = saved
                revised_prompt = None
                status = "completed"
                transcript = []

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **_kwargs):
                    nonlocal active, peak
                    active += 1
                    peak = max(peak, active)
                    await asyncio.sleep(0.05)
                    active -= 1
                    return FakeResult()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", Path(tmp)), patch("server.image_gen_app.CodexAppServerClient", FakeClient):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/generate",
                            json={
                                "run_id": "sample_run",
                                "kind": "scene",
                                "item_id": "scene1_cut1",
                                "prompt": "prompt",
                                "references": [],
                                "candidate_count": 3,
                            },
                        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["candidates"]), 3)
        self.assertGreaterEqual(peak, 2)

    def test_candidates_endpoint_lists_candidate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            candidate = run_dir / "assets/test/image_gen_candidates/scene1/candidate_01.png"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(PNG_BYTES)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.get("/api/image-gen/candidates?run_id=sample_run&item_id=scene1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["candidates"][0]["path"], "assets/test/image_gen_candidates/scene1/candidate_01.png")

    def test_generate_writes_app_server_debug_log_when_saved_path_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)

            class FakeResult:
                saved_path = None
                revised_prompt = "revised"
                status = "completed"
                transcript = [{"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": "done"}}}]

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **_kwargs):
                    return FakeResult()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", Path(tmp)), patch("server.image_gen_app.CodexAppServerClient", FakeClient):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/generate",
                            json={
                                "run_id": "sample_run",
                                "kind": "scene",
                                "item_id": "scene1_cut1",
                                "prompt": "prompt",
                                "references": [],
                                "candidate_count": 1,
                            },
                        )

            candidate = response.json()["candidates"][0]
            log_path = run_dir / candidate["debugLog"]
            log_exists = log_path.exists()
            log_payload = log_path.read_text(encoding="utf-8")
            prompt_log = run_dir / "logs" / "image_generation_prompts.jsonl"
            prompt_log_exists = prompt_log.exists()
            prompt_log_payload = prompt_log.read_text(encoding="utf-8") if prompt_log_exists else ""

        self.assertEqual(response.status_code, 200)
        self.assertEqual(candidate["status"], "failed")
        self.assertTrue(log_exists)
        self.assertIn('"itemId": "scene1_cut1"', log_payload)
        self.assertIn('"prompt": "prompt"', log_payload)
        self.assertIn('"promptSha256"', log_payload)
        self.assertIn('"transcript"', log_payload)
        self.assertTrue(prompt_log_exists)
        self.assertIn('"prompt": "prompt"', prompt_log_payload)

    def test_prompt_settings_api_reads_and_writes_existing_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "docs/implementation/asset-bibles.md"
            doc.parent.mkdir(parents=True)
            doc.write_text(
                "# Asset Bibles\n\n"
                "<!-- image-gen-setting:item:start -->\n"
                "item instruction\n"
                "<!-- image-gen-setting:item:end -->\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        read_response = client.get("/api/image-gen/prompt-settings?target=item")
                        write_response = client.post(
                            "/api/image-gen/prompt-settings",
                            json={"target": "item", "content": "replacement instruction"},
                        )
            updated_doc = doc.read_text(encoding="utf-8")

        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()["content"], "item instruction")
        self.assertEqual(write_response.status_code, 200)
        self.assertEqual(write_response.json()["content"], "replacement instruction")
        self.assertIn("replacement instruction", updated_doc)

    def test_prompt_settings_api_rejects_setting_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "docs/implementation/asset-bibles.md"
            doc.parent.mkdir(parents=True)
            original = "<!-- image-gen-setting:item:start -->\nitem instruction\n<!-- image-gen-setting:item:end -->\n"
            doc.write_text(original, encoding="utf-8")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/prompt-settings",
                            json={"target": "item", "content": "safe\n<!-- image-gen-setting:scene:start -->\nunsafe"},
                        )
            updated_doc = doc.read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(updated_doc, original)

    def test_generate_rejects_escaping_reference_path_before_app_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)

            class FakeClient:
                def __init__(self, **_kwargs):
                    raise AssertionError("client should not start for invalid references")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.CodexAppServerClient", FakeClient):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/generate",
                            json={
                                "run_id": "sample_run",
                                "kind": "scene",
                                "item_id": "scene10_cut1",
                                "prompt": "prompt",
                                "references": ["assets/../private.png"],
                                "candidate_count": 1,
                            },
                        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("must not contain '..'", response.text)

    def test_save_frontend_review_writes_output_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_p650_artifacts(root, "sample_run")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/reviews/draft",
                            json={
                                "run_id": "sample_run",
                                "kind": "scene",
                                "note": "temporary save",
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                        "prompt": "updated image prompt",
                                        "references": ["assets/characters/hero.png"],
                                        "selected_candidate_path": "assets/test/image_gen_candidates/scene10_cut1/candidate_01.png",
                                        "video_prompt": "move slowly",
                                        "video_quality": "1080p",
                                        "video_aspect_ratio": "16:9",
                                        "video_first_reference": "assets/scenes/scene10_cut1.png",
                                        "video_references": ["assets/characters/hero.png"],
                                    }
                                ],
                            },
                        )

            payload = response.json()
            draft_path = root / "output" / "sample_run" / payload["path"]
            draft_text = draft_path.read_text(encoding="utf-8")
            state = (root / "output" / "sample_run" / "state.txt").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("updated image prompt", draft_text)
        self.assertIn("selected_candidate_path", draft_text)
        self.assertIn("review.frontend.scene.status=draft", state)

    def test_frontend_review_rejects_escaping_asset_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/reviews/draft",
                            json={
                                "run_id": "sample_run",
                                "kind": "scene",
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                        "prompt": "prompt",
                                        "references": ["assets/../private.png"],
                                    }
                                ],
                            },
                        )

            review_dir = run_dir / "logs" / "review" / "frontend"
            latest_exists = (review_dir / "scene_draft_latest.json").exists()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(latest_exists)

    def test_frontend_review_rejects_markdown_unsafe_asset_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/reviews/draft",
                            json={
                                "run_id": "sample_run",
                                "kind": "scene",
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/bad`name.png",
                                        "prompt": "prompt",
                                    }
                                ],
                            },
                        )

            latest_exists = (run_dir / "logs" / "review" / "frontend" / "scene_draft_latest.json").exists()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(latest_exists)

    def test_insert_cut_updates_manifest_and_creates_output_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")

            async def noop_materialize(_run_id: str) -> None:
                return None

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._materialize_scene_requests", noop_materialize),
                ):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/cuts/insert",
                            json={
                                "run_id": "sample_run",
                                "anchor_item_id": "scene10_cut1",
                                "position": "after",
                                "cut_name": "新しい接続カット",
                            },
                        )

            manifest = yaml.safe_load(image_gen_app._extract_manifest_yaml_text((run_dir / "video_manifest.md").read_text(encoding="utf-8")))
            scene_folder_exists = (run_dir / "assets" / "scenes" / "scene10_cut3").is_dir()
            audio_folder_exists = (run_dir / "assets" / "audio" / "scene10_cut3").is_dir()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selector"], "scene10_cut3")
        self.assertEqual(manifest["scenes"][0]["cuts"][1]["cut_name"], "新しい接続カット")
        self.assertTrue(scene_folder_exists)
        self.assertTrue(audio_folder_exists)

    def test_insert_cut_rolls_back_manifest_when_materializer_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            manifest_before = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            request_before = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")

            async def fail_materialize(_run_id: str) -> None:
                raise RuntimeError("materialize failed")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._materialize_scene_requests", fail_materialize),
                ):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/cuts/insert",
                            json={
                                "run_id": "sample_run",
                                "anchor_item_id": "scene10_cut1",
                                "position": "after",
                                "cut_name": "失敗する追加",
                            },
                        )

            manifest_after = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            request_after = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(manifest_after, manifest_before)
        self.assertEqual(request_after, request_before)

    def test_create_video_prompts_saves_review_design_and_request_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "note": "create video prompts",
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                        "prompt": "updated still prompt",
                                        "references": ["assets/characters/hero.png"],
                                        "selected_candidate_path": "assets/test/image_gen_candidates/scene10_cut1/candidate_01.png",
                                        "video_prompt": "slow dolly forward",
                                        "video_quality": "720p",
                                        "video_aspect_ratio": "9:16",
                                        "video_duration_seconds": 6,
                                        "video_first_reference": "assets/scenes/scene10_cut1.png",
                                        "video_last_reference": "assets/characters/hero.png",
                                        "video_references": ["assets/characters/hero.png"],
                                        "video_tool": "kling_3_0",
                                    }
                                ],
                            },
                        )

            request_text = (run_dir / "video_generation_requests.md").read_text(encoding="utf-8")
            design_text = (run_dir / "logs" / "review" / "frontend" / "video_prompt_design.md").read_text(encoding="utf-8")
            video_draft_latest_exists = (run_dir / "logs" / "review" / "frontend" / "video_draft_latest.json").exists()
            manifest = yaml.safe_load(image_gen_app._extract_manifest_yaml_text((run_dir / "video_manifest.md").read_text(encoding="utf-8")))
            state = (run_dir / "state.txt").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(video_draft_latest_exists)
        self.assertIn("- quality: `720p`", request_text)
        self.assertIn("- aspect_ratio: `9:16`", request_text)
        self.assertIn("slow dolly forward", request_text)
        self.assertIn("prompt_changed: `true`", design_text)
        self.assertEqual(manifest["scenes"][0]["cuts"][0]["video_generation"]["first_frame"], "assets/scenes/scene10_cut1.png")
        self.assertIn("review.frontend.video.status=saved_for_video_prompt", state)
        self.assertIn("slot.p830.status=awaiting_approval", state)

    def test_create_video_prompts_rejects_unknown_manifest_cut_without_advancing_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "items": [
                                    {
                                        "item_id": "scene99_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene99_cut1.png",
                                        "prompt": "unknown",
                                        "video_prompt": "slow push",
                                        "video_first_reference": "assets/scenes/scene10_cut1.png",
                                    }
                                ],
                            },
                        )

            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            video_requests_exists = (run_dir / "video_generation_requests.md").exists()

        self.assertEqual(response.status_code, 400)
        self.assertIn("video manifest targets not found", response.text)
        self.assertFalse(video_requests_exists)
        self.assertNotIn("slot.p830.status=awaiting_approval", state)

    def test_create_video_prompts_partial_update_preserves_existing_video_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            (run_dir / "video_generation_requests.md").write_text(
                """# Video Generation Requests

## scene20_cut1

- tool: `kling_3_0`
- output: `assets/scenes/scene20_cut1_video.mp4`

```text
keep existing request
```
""",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "replace_all": False,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                        "prompt": "prompt",
                                        "video_prompt": "new scene10 request",
                                        "video_first_reference": "assets/scenes/scene10_cut1.png",
                                    }
                                ],
                            },
                        )

            request_text = (run_dir / "video_generation_requests.md").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("## scene20_cut1", request_text)
        self.assertIn("keep existing request", request_text)
        self.assertIn("## scene10_cut1", request_text)
        self.assertIn("new scene10 request", request_text)

    def test_create_video_prompts_rejects_markdown_code_fence_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                        "prompt": "prompt",
                                        "video_prompt": "before\n```text\nbreak\n```",
                                        "video_first_reference": "assets/scenes/scene10_cut1.png",
                                    }
                                ],
                            },
                        )
            video_requests_exists = (run_dir / "video_generation_requests.md").exists()

        self.assertEqual(response.status_code, 400)
        self.assertIn("must not contain markdown code fences", response.text)
        self.assertFalse(video_requests_exists)

    def test_video_generate_calls_provider_and_does_not_update_request_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            (run_dir / "video_generation_requests.md").write_text("keep existing requests\n", encoding="utf-8")
            manifest_before = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            calls: list[dict[str, Any]] = []

            class FakeKlingClient:
                def __init__(self, _config):
                    pass

                def start_video_generation(self, **kwargs):
                    calls.append(kwargs)
                    return {"data": {"id": f"task-{len(calls)}"}}

                def extract_operation_id(self, response, **_kwargs):
                    return response["data"]["id"]

                def poll_operation(self, **kwargs):
                    return {"status": "succeeded", "data": {"task_result": {"videos": [{"url": f"https://example.test/{kwargs['operation_id_or_url']}.mp4"}]}}}

                def is_failed_operation(self, _operation, **_kwargs):
                    return False

                def extract_video_uri(self, operation, **_kwargs):
                    return operation["data"]["task_result"]["videos"][0]["url"]

                def download_to_file(self, *, uri: str, out_path: Path, **_kwargs):
                    out_path.write_bytes(MP4_BYTES + uri.encode("utf-8"))

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "KLING_API_KEY": "fake-key"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.KlingClient", FakeKlingClient),
                ):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": "slow dolly forward",
                                "first_reference": "assets/characters/hero.png",
                                "quality": "720p",
                                "aspect_ratio": "9:16",
                                "duration_seconds": 6,
                                "tool": "kling_3_0",
                                "candidate_count": 2,
                            },
                        )

            payload = response.json()
            request_text = (run_dir / "video_generation_requests.md").read_text(encoding="utf-8")
            manifest_after = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            first_candidate_exists = (run_dir / payload["candidates"][0]["path"]).is_file()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["candidates"]), 2)
        self.assertTrue(first_candidate_exists)
        self.assertEqual(request_text, "keep existing requests\n")
        self.assertEqual(manifest_after, manifest_before)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["prompt"], "slow dolly forward")
        self.assertEqual(calls[0]["aspect_ratio"], "9:16")
        self.assertEqual(calls[0]["resolution"], "720p")

    def test_video_generate_rejects_invalid_reference_before_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_p650_artifacts(root, "sample_run")

            class FakeKlingClient:
                def __init__(self, *_args, **_kwargs):
                    raise AssertionError("provider must not be constructed for invalid references")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "KLING_API_KEY": "fake-key"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.KlingClient", FakeKlingClient),
                ):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": "slow dolly forward",
                                "first_reference": "../secrets.png",
                                "candidate_count": 1,
                            },
                        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("run-relative", response.text)

    def test_narration_items_reads_manifest_audio_and_video_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            manifest = run_dir / "video_manifest.md"
            manifest.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 10-1
        image_generation:
          output: assets/scenes/scene10_cut1.png
        video_generation:
          tool: kling_3_0
          duration_seconds: 4
          output: assets/scenes/scene10_cut1.mp4
          motion_prompt: slow move
          quality: 720p
          aspect_ratio: 9:16
        audio:
          narration:
            tool: elevenlabs
            text: こんにちは
            tts_text: こんにちは。
            output: assets/audio/scene10_cut1.mp3
```
""",
                encoding="utf-8",
            )
            (run_dir / "assets" / "audio").mkdir(parents=True, exist_ok=True)
            (run_dir / "assets" / "audio" / "scene10_cut1.mp3").write_bytes(b"fake")

            def fake_probe(path: Path) -> float | None:
                return 2.4 if path.suffix == ".mp3" else None

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app._probe_media_duration_seconds", fake_probe):
                    with TestClient(app) as client:
                        response = client.get("/api/image-gen/narration-items", params={"run_id": "sample_run"})

        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["items"][0]["itemId"], "scene10_cut1")
        self.assertEqual(payload["items"][0]["narrationDurationSeconds"], 2.4)
        self.assertEqual(payload["items"][0]["videoPrompt"], "slow move")
        self.assertEqual(payload["items"][0]["videoQuality"], "720p")

    def test_narration_generate_updates_manifest_and_duration_minimum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")

            async def fake_generate_one(_run_dir: Path, req: image_gen_app.NarrationGenerateItem) -> dict[str, Any]:
                return {
                    "itemId": req.item_id,
                    "status": "completed",
                    "path": req.output or "assets/audio/scene10_cut1.mp3",
                    "durationSeconds": 9.2,
                    "debugLog": "logs/providers/narration/fake.json",
                    "source": req.tool,
                }

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app._generate_narration_one", fake_generate_one):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/narration-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "text": "読み上げ本文",
                                "tts_text": "読み上げ本文。",
                                "output": "assets/audio/scene10_cut1.mp3",
                                "tool": "elevenlabs",
                            },
                        )

            data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text((run_dir / "video_manifest.md").read_text(encoding="utf-8")))
            cut = data["scenes"][0]["cuts"][0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(cut["audio"]["narration"]["text"], "読み上げ本文")
        self.assertEqual(cut["audio"]["narration"]["tts_text"], "読み上げ本文。")
        self.assertEqual(cut["video_generation"]["duration_seconds"], 10)

    def test_video_generate_uses_narration_duration_as_minimum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            manifest = run_dir / "video_manifest.md"
            manifest.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 10-1
        image_generation:
          output: assets/scenes/scene10_cut1.png
        video_generation:
          duration_seconds: 4
        audio:
          narration:
            output: assets/audio/scene10_cut1.mp3
```
""",
                encoding="utf-8",
            )
            (run_dir / "assets" / "audio").mkdir(parents=True, exist_ok=True)
            (run_dir / "assets" / "audio" / "scene10_cut1.mp3").write_bytes(b"fake")
            calls: list[dict[str, Any]] = []

            class FakeKlingClient:
                def __init__(self, _config):
                    pass

                def start_video_generation(self, **kwargs):
                    calls.append(kwargs)
                    return {"data": {"id": "task-1"}}

                def extract_operation_id(self, response, **_kwargs):
                    return response["data"]["id"]

                def poll_operation(self, **_kwargs):
                    return {"status": "succeeded", "data": {"task_result": {"videos": [{"url": "https://example.test/video.mp4"}]}}}

                def is_failed_operation(self, _operation, **_kwargs):
                    return False

                def extract_video_uri(self, operation, **_kwargs):
                    return operation["data"]["task_result"]["videos"][0]["url"]

                def download_to_file(self, *, uri: str, out_path: Path, **_kwargs):
                    out_path.write_bytes(MP4_BYTES + uri.encode("utf-8"))

            def fake_probe(path: Path) -> float | None:
                return 9.2 if path.suffix == ".mp3" else None

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "KLING_API_KEY": "fake-key"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.KlingClient", FakeKlingClient),
                    patch("server.image_gen_app._probe_media_duration_seconds", fake_probe),
                ):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": "slow dolly forward",
                                "first_reference": "assets/characters/hero.png",
                                "duration_seconds": 4,
                                "candidate_count": 1,
                            },
                        )

            payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["durationSeconds"], 10)
        self.assertEqual(calls[0]["duration_seconds"], 10)

    def test_render_inputs_freeze_writes_concat_lists_and_manifest_render_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            videos_dir = run_dir / "assets" / "scenes"
            audio_dir = run_dir / "assets" / "audio"
            videos_dir.mkdir(parents=True, exist_ok=True)
            audio_dir.mkdir(parents=True, exist_ok=True)
            (videos_dir / "scene10_cut1.mp4").write_bytes(MP4_BYTES)
            (audio_dir / "scene10_cut1.mp3").write_bytes(b"fake-audio")
            manifest = run_dir / "video_manifest.md"
            manifest.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 10-1
        video_generation:
          output: assets/scenes/scene10_cut1.mp4
          duration_seconds: 4
        audio:
          narration:
            output: assets/audio/scene10_cut1.mp3
```
""",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._prepare_render_video_clip", lambda _run_dir, source, _item: source),
                    patch("server.image_gen_app._prepare_render_narration", lambda _run_dir, source, _item: source),
                    patch("server.image_gen_app._probe_media_duration_seconds", lambda path: 3.0 if path.suffix == ".mp3" else None),
                ):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/render-inputs/freeze",
                            json={
                                "run_id": "sample_run",
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "video_path": "assets/scenes/scene10_cut1.mp4",
                                        "narration_path": "assets/audio/scene10_cut1.mp3",
                                        "video_duration_seconds": 6,
                                        "narration_offset_seconds": 1.5,
                                    }
                                ],
                            },
                        )

            data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text((run_dir / "video_manifest.md").read_text(encoding="utf-8")))
            cut = data["scenes"][0]["cuts"][0]
            clips_text = (run_dir / "video_clips.txt").read_text(encoding="utf-8")
            narration_text = (run_dir / "video_narration_list.txt").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("scene10_cut1.mp4", clips_text)
        self.assertIn("scene10_cut1.mp3", narration_text)
        self.assertEqual(cut["render"]["narration_offset_seconds"], 1.5)
        self.assertEqual(cut["video_generation"]["duration_seconds"], 6)

    def test_regenerate_prompts_updates_request_file_after_all_items_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "image_generation_requests.md").write_text(SAMPLE_REQUESTS, encoding="utf-8")
            setting = root / "docs/implementation/image-prompting.md"
            setting.parent.mkdir(parents=True)
            setting.write_text(
                "<!-- image-gen-setting:scene:start -->\nscene rules\n<!-- image-gen-setting:scene:end -->\n",
                encoding="utf-8",
            )

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def regenerate_prompt(self, **kwargs):
                    return f"rewritten {kwargs['item']['id']}"

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.CodexAppServerClient", FakeClient):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/regenerate-prompts",
                            json={
                                "run_id": "sample_run",
                                "target": "scene",
                                "instruction": "make it sharper",
                                "item_ids": ["scene1_cut1", "scene2_cut1"],
                            },
                        )
            updated = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        self.assertIn("rewritten scene1_cut1", updated)
        self.assertIn("rewritten scene2_cut1", updated)

    def test_regenerate_prompts_does_not_update_request_file_when_any_item_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "image_generation_requests.md").write_text(SAMPLE_REQUESTS, encoding="utf-8")
            setting = root / "docs/implementation/image-prompting.md"
            setting.parent.mkdir(parents=True)
            setting.write_text(
                "<!-- image-gen-setting:scene:start -->\nscene rules\n<!-- image-gen-setting:scene:end -->\n",
                encoding="utf-8",
            )

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def regenerate_prompt(self, **kwargs):
                    if kwargs["item"]["id"] == "scene2_cut1":
                        raise RuntimeError("failed")
                    return f"rewritten {kwargs['item']['id']}"

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.CodexAppServerClient", FakeClient):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/regenerate-prompts",
                            json={
                                "run_id": "sample_run",
                                "target": "scene",
                                "instruction": "make it sharper",
                                "item_ids": ["scene1_cut1", "scene2_cut1"],
                            },
                        )
            updated = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 500)
        self.assertIn("cinematic prompt\nline two", updated)

    def test_regenerate_prompts_fails_when_replacement_is_not_atomic(self) -> None:
        malformed = """# Image Generation Requests

## scene1_cut1

- output: `assets/scenes/scene01.png`

## scene2_cut1

- output: `assets/scenes/scene02.png`

```text
scene two prompt
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "image_generation_requests.md").write_text(malformed, encoding="utf-8")
            setting = root / "docs/implementation/image-prompting.md"
            setting.parent.mkdir(parents=True)
            setting.write_text(
                "<!-- image-gen-setting:scene:start -->\nscene rules\n<!-- image-gen-setting:scene:end -->\n",
                encoding="utf-8",
            )

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def regenerate_prompt(self, **kwargs):
                    return f"rewritten {kwargs['item']['id']}"

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.CodexAppServerClient", FakeClient):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/regenerate-prompts",
                            json={
                                "run_id": "sample_run",
                                "target": "scene",
                                "instruction": "make it sharper",
                                "item_ids": ["scene1_cut1", "scene2_cut1"],
                            },
                        )
            updated = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 400)
        self.assertIn("scene two prompt", updated)
        self.assertNotIn("rewritten", updated)

    def test_regenerate_prompts_rejects_unknown_requested_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "image_generation_requests.md").write_text(SAMPLE_REQUESTS, encoding="utf-8")
            setting = root / "docs/implementation/image-prompting.md"
            setting.parent.mkdir(parents=True)
            setting.write_text(
                "<!-- image-gen-setting:scene:start -->\nscene rules\n<!-- image-gen-setting:scene:end -->\n",
                encoding="utf-8",
            )

            class FakeClient:
                pass

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.CodexAppServerClient", FakeClient):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/regenerate-prompts",
                            json={
                                "run_id": "sample_run",
                                "target": "scene",
                                "instruction": "make it sharper",
                                "item_ids": ["scene1_cut1", "missing"],
                            },
                        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("missing", str(response.json()))

    def test_download_zip_rejects_non_candidate_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text("secret", encoding="utf-8")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", Path(tmp)):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/download-zip",
                            json={"run_id": "sample_run", "paths": ["state.txt"]},
                        )

        self.assertEqual(response.status_code, 400)

    def test_download_zip_accepts_candidate_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            candidate = run_dir / "assets/test/image_gen_candidates/scene1/candidate_01.png"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(PNG_BYTES)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", Path(tmp)):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/download-zip",
                            json={
                                "run_id": "sample_run",
                                "paths": ["assets/test/image_gen_candidates/scene1/candidate_01.png"],
                            },
                        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")

    def test_insert_candidate_rejects_invalid_candidate_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            candidate = run_dir / "assets/test/image_gen_candidates/scene1/candidate_01.png"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b"not a png")

            with self.assertRaises(ValueError):
                image_gen.insert_candidate(run_dir, candidate, "assets/scenes/scene01.png")

    def test_api_requires_token_when_configured(self) -> None:
        with patch.dict(os.environ, {"TOC_SERVER_TOKEN": "secret", "TOC_SERVER_AUTH_DISABLED": ""}):
            with TestClient(app) as client:
                blocked = client.get("/api/image-gen/runs")
                allowed = client.get("/api/image-gen/runs", headers={"X-ToC-Local-Token": "secret"})

        self.assertEqual(blocked.status_code, 401)
        self.assertEqual(allowed.status_code, 200)

    def test_invalid_run_id_returns_400(self) -> None:
        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
            with TestClient(app) as client:
                response = client.get("/api/image-gen/requests?run_id=../x&kind=scene")

        self.assertEqual(response.status_code, 400)

    def test_file_endpoint_rejects_non_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "video_manifest.md").write_text("manifest", encoding="utf-8")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", Path(tmp)):
                    with TestClient(app) as client:
                        response = client.get("/api/image-gen/file?run_id=sample_run&path=video_manifest.md")

        self.assertEqual(response.status_code, 400)

    def test_bulk_generation_uses_parent_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent_run = root / "output" / "parent"
            child_run = root / "output" / "child"
            parent_run.mkdir(parents=True)
            child_run.mkdir(parents=True)
            saved = root / "generated.png"
            saved.write_bytes(PNG_BYTES)
            test_case = self

            class FakeResult:
                saved_path = saved
                revised_prompt = None
                status = "completed"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    test_case.assertEqual(kwargs["run_dir"].name, "parent")
                    return FakeResult()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.CodexAppServerClient", FakeClient):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/generate-bulk",
                            json={
                                "run_id": "parent",
                                "kind": "scene",
                                "items": [
                                    {
                                        "run_id": "child",
                                        "kind": "asset",
                                        "item_id": "scene1_cut1",
                                        "prompt": "prompt",
                                        "references": [],
                                        "candidate_count": 1,
                                    }
                                ],
                            },
                        )
                        generated_exists = (
                            parent_run / "assets/test/image_gen_candidates/scene1_cut1/candidate_01.png"
                        ).resolve().exists()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(generated_exists)


if __name__ == "__main__":
    unittest.main()
