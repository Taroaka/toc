from __future__ import annotations

import asyncio
import inspect
import json
import shutil
import subprocess
import tempfile
import time
import unittest
import sys
import os
from pathlib import Path
from contextlib import suppress
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
    CodexAppServerTransportError,
    ImageGenerationResult,
    _extract_prompt_from_agent_text,
    classify_codex_transport_error,
    create_codex_app_server_client,
    default_app_server_model,
    find_agent_message_texts,
    find_image_generation_items,
    image_generation_saved_path,
    is_codex_transport_error,
    preflight_codex_backend_network,
    reject_local_raster_image_result,
    wait_for_generated_image_after,
    wait_for_unclaimed_generated_image_after,
)
from server.image_gen_app import (
    _toc_immersive_command,
    _toc_run_command,
    _validate_created_run,
    _validate_frontend_create_run,
    _validate_materialized_p650_run,
    _validate_p650_run,
)
from toc.semantic_review_loop import semantic_repair_relpaths


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


def write_semantic_review_artifacts(run_dir: Path, stage: str, *, entry_count: int = 1) -> None:
    relpaths = image_gen_app.semantic_review_relpaths(stage)
    for key, relpath in relpaths.items():
        path = run_dir / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        if key == "scope":
            path.write_text(
                json.dumps(
                    {
                        "entry_count": entry_count,
                        "selectors": [f"{stage}_entry_{index + 1}" for index in range(entry_count)],
                        "artifacts": {artifact_key: artifact_path.as_posix() for artifact_key, artifact_path in relpaths.items()},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
        elif key == "report":
            path.write_text(
                f"status: passed\nreviewed_entries: [{stage}_entry_1]\nblocked_entries: []\nfindings: []\nnotes: []\n",
                encoding="utf-8",
            )
        elif key == "prompt":
            path.write_text(f"# Semantic Review Prompt\n\nstage: {stage}\n", encoding="utf-8")
        else:
            path.write_text(f"# Semantic Review Collection\n\nstage: {stage}\n", encoding="utf-8")


def write_valid_p650_artifacts(root: Path, run_id: str) -> Path:
    run_dir = root / "output" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "characters").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "characters" / "hero.png").write_bytes(PNG_BYTES)
    image_gen.write_app_server_image_debug_log(
        run_dir=run_dir,
        item_id="hero",
        index=1,
        destination=run_dir / "assets" / "characters" / "hero.png",
        references=[],
        prompt="実写映画風の主人公参照画像。",
        kind="asset",
        result=ImageGenerationResult(
            saved_path=run_dir / "assets" / "characters" / "hero.png",
            revised_prompt=None,
            status="completed",
            transcript=[],
            source="app_server",
        ),
    )
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
      - cut_id: 10-3
        image_generation:
          output: assets/scenes/scene10_cut3.png
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

## scene10_cut3

- tool: `codex_builtin_image`
- execution_lane: `standard`
- reference_count: `1`
- output: `assets/scenes/scene10_cut3.png`
- references:
  - `主人公`: `assets/characters/hero.png`

```text
実写映画風の横長16:9カット。主人公が場面の出口へ向かい、次のsceneへつながる余韻を具体的に描く。
```
""",
        encoding="utf-8",
    )
    (run_dir / "p000_index.md").write_text(
        "# Run Index\n\np650 まで到達した実作業済み run の索引です。現在位置、生成済み成果物、次に必要な確認を十分な本文量で記録します。asset request と scene image request が存在することを確認済みです。\n",
        encoding="utf-8",
    )
    review_dir = run_dir / "logs" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "image_prompt.review_collection.md").write_text(
        "# Image Prompt Judgment Review Collection\n\n件数: `3`\n\n## scene10_cut1\n\n## scene10_cut2\n\n## scene10_cut3\n",
        encoding="utf-8",
    )
    (review_dir / "image_prompt.review_scope.json").write_text(
        json.dumps(
            {
                "entry_count": 3,
                "selectors": ["scene10_cut1", "scene10_cut2", "scene10_cut3"],
                "artifacts": {
                    "collection": "logs/review/image_prompt.review_collection.md",
                    "prompt": "logs/review/image_prompt.judgment_prompt.md",
                    "report": "logs/review/image_prompt.judgment.md",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (review_dir / "image_prompt.judgment_prompt.md").write_text(
        "contextless semantic review prompt\n",
        encoding="utf-8",
    )
    (review_dir / "image_prompt.judgment.md").write_text(
        "status: passed\nreviewed_entries: [scene10_cut1, scene10_cut2, scene10_cut3]\nblocked_entries: []\nfindings: []\nnotes: []\n",
        encoding="utf-8",
    )
    for stage in ("scene_set", "scene_detail", "cut_blueprint", "asset_plan", "asset_output", "image_prompt"):
        write_semantic_review_artifacts(run_dir, stage, entry_count=3 if stage == "image_prompt" else 1)
    return run_dir


def write_valid_p680_artifacts(root: Path, run_id: str) -> Path:
    run_dir = write_valid_p650_artifacts(root, run_id)
    (run_dir / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "scenes" / "scene10_cut1.png").write_bytes(PNG_BYTES)
    (run_dir / "assets" / "scenes" / "scene10_cut2.png").write_bytes(PNG_BYTES)
    (run_dir / "assets" / "scenes" / "scene10_cut3.png").write_bytes(PNG_BYTES)
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
    write_semantic_review_artifacts(run_dir, "scene_image", entry_count=3)
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

    def test_create_run_error_message_preserves_app_server_detail(self) -> None:
        message = image_gen_app._create_run_error_message(
            RuntimeError("stream disconnected before completion: error sending request for url (https://chatgpt.com/backend-api/codex/responses)")
        )

        self.assertIn("画像生成通信が途中で切断", message)
        self.assertIn("stream disconnected", message)

    def test_create_run_error_message_identifies_readonly_codex_state(self) -> None:
        message = image_gen_app._create_run_error_message(
            RuntimeError("failed to initialize sqlite state runtime under /Users/example/.codex: attempt to write a readonly database")
        )

        self.assertIn("状態DBを初期化できませんでした", message)
        self.assertIn("readonly database", message)

    def test_create_run_error_message_identifies_missing_codex_image_auth(self) -> None:
        message = image_gen_app._create_run_error_message(
            RuntimeError("unexpected status 401 Unauthorized: Missing bearer or basic authentication in header")
        )

        self.assertIn("画像生成認証が不足", message)
        self.assertIn("401 Unauthorized", message)

    def test_create_run_error_message_identifies_image_timeout(self) -> None:
        message = image_gen_app._create_run_error_message(TimeoutError())

        self.assertIn("画像生成がタイムアウト", message)

    def test_create_run_error_message_identifies_semantic_failure_after_media_generation(self) -> None:
        message = image_gen_app._create_run_error_message(
            RuntimeError("semantic review failed after media generation: scene_set stream disconnected before completion")
        )

        self.assertIn("semantic QA に失敗", message)
        self.assertIn("asset/scene 画像生成は実行済み", message)

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

    def test_validate_materialized_p650_run_allows_no_generated_assets_or_semantic_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            shutil.rmtree(run_dir / "assets")
            shutil.rmtree(run_dir / "logs" / "review")

            with patch("server.image_gen_app.ROOT", root):
                _validate_materialized_p650_run("桃太郎_20260509_1200")

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
                with self.assertRaisesRegex(RuntimeError, "requires at least 3 cuts"):
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

    def test_validate_frontend_create_run_requires_semantic_review_passed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p680_artifacts(root, "桃太郎_20260509_1200")
            (run_dir / "logs" / "review" / "image_prompt.judgment.md").write_text(
                "# Image Prompt Judgment Review\n\n- status: `pending`\n\n## Findings\n\n- `...`\n",
                encoding="utf-8",
            )
            (run_dir / image_gen_app.semantic_review_relpaths("image_prompt")["report"]).write_text(
                "# Image Prompt Semantic Review\n\n- status: `pending`\n\n## Findings\n\n- `...`\n",
                encoding="utf-8",
            )

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "semantic review incomplete"):
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
            run_id = "桃太郎_20260509_1200"
            (root / "output" / run_id).mkdir(parents=True)
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
                    patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                ):
                    with self.assertRaisesRegex(RuntimeError, "path mismatch"):
                        asyncio.run(image_gen_app._run_toc_skill_helper(topic="桃太郎", source="資料", run_id=run_id))

    def test_run_toc_skill_helper_allows_unsupported_skills_list_and_runs_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            (root / "output" / run_id).mkdir(parents=True)
            skill_path = root / ".codex" / "skills" / "toc-immersive-runner" / "SKILL.md"
            skill_path.parent.mkdir(parents=True)
            skill_path.write_text("---\nname: toc-immersive-runner\n---\n", encoding="utf-8")
            calls: list[dict[str, Any]] = []
            fallback_calls: list[dict[str, Any]] = []

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

            async def fake_frontend_cli_helper(**kwargs):
                fallback_calls.append(kwargs)
                write_valid_p680_artifacts(root, run_id)
                return "fallback completed"

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                    patch("server.image_gen_app._run_toc_immersive_frontend_cli_helper", fake_frontend_cli_helper),
                    patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
                ):
                    asyncio.run(image_gen_app._run_toc_skill_helper(topic="桃太郎", source="鬼ヶ島の資料", run_id=run_id))

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["skill_path"], skill_path)
        payload = json.loads(calls[0]["text"].split("Request JSON:\n", 1)[1])
        self.assertEqual(payload["topic"], "桃太郎")
        self.assertEqual(payload["source"], "鬼ヶ島の資料")
        self.assertEqual(fallback_calls, [{"topic": "桃太郎", "source": "鬼ヶ島の資料", "run_id": run_id, "stop_target": "p680"}])

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

    def test_reject_local_raster_image_result(self) -> None:
        result = ImageGenerationResult(
            saved_path=Path("/tmp/generated.png"),
            revised_prompt=None,
            status="completed",
            transcript=[],
            source="local_raster_generation_after_app_server_permission_failure",
        )

        with self.assertRaisesRegex(CodexAppServerError, "unsupported local raster fallback"):
            reject_local_raster_image_result(result, item_id="scene1")

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

    def test_generate_image_keeps_fallback_watcher_for_item_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            codex_home = root / "codex_home"
            generated = codex_home / "generated_images" / "session" / "generated.png"
            generated.parent.mkdir(parents=True)
            generated.write_bytes(PNG_BYTES)
            client = CodexAppServerClient(cwd=root)
            seen_timeout: list[int] = []

            async def fake_start_thread(**_kwargs):
                return "thread-1"

            async def fake_run_turn(**_kwargs):
                await asyncio.sleep(10)
                return [{"method": "turn/completed", "params": {"turnId": "turn-1"}}]

            async def fake_wait_for_unclaimed(_cutoff_ns, *, root=None, timeout_seconds=300, poll_seconds=1.0):
                seen_timeout.append(timeout_seconds)
                return generated

            client.start_thread = fake_start_thread  # type: ignore[method-assign]
            client.run_turn = fake_run_turn  # type: ignore[method-assign]

            with (
                patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}),
                patch("server.codex_app_server.wait_for_unclaimed_generated_image_after", fake_wait_for_unclaimed),
            ):
                result = asyncio.run(
                    client.generate_image(
                        prompt="prompt",
                        output_path=run_dir / "candidate.png",
                        reference_images=[],
                        item_id="scene1",
                        run_dir=run_dir,
                        timeout_seconds=777,
                    )
                )

        self.assertEqual(seen_timeout, [777])
        self.assertIsNotNone(result.saved_path)
        self.assertEqual(result.saved_path.name, "generated.png")
        self.assertEqual(result.source, "generated_images_early_fallback")

    def test_codex_app_server_uses_default_home_when_env_missing_and_writable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"TMPDIR": tmp}, clear=False), patch("server.codex_app_server._is_writable_directory", return_value=True):
                os.environ.pop("CODEX_HOME", None)
                client = CodexAppServerClient(cwd=Path(tmp))
                env = client._subprocess_env()

        self.assertIn("CODEX_HOME", env)
        self.assertTrue(Path(env["CODEX_HOME"]).is_dir())
        self.assertEqual(env["CODEX_HOME"], str(Path.home() / ".codex"))

    def test_codex_app_server_rejects_silent_fallback_home_when_default_home_unwritable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.dict(os.environ, {"TMPDIR": tmp}, clear=False),
                patch("server.codex_app_server.tempfile.gettempdir", return_value=tmp),
                patch("server.codex_app_server._is_writable_directory", return_value=False),
            ):
                os.environ.pop("CODEX_HOME", None)
                client = CodexAppServerClient(cwd=Path(tmp))
                with self.assertRaisesRegex(CodexAppServerError, "refusing silent fallback"):
                    client._subprocess_env()

    def test_codex_app_server_uses_writable_fallback_home_when_explicitly_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.dict(os.environ, {"TMPDIR": tmp, "TOC_CODEX_HOME_FALLBACK_ALLOWED": "1"}, clear=False),
                patch("server.codex_app_server.tempfile.gettempdir", return_value=tmp),
                patch("server.codex_app_server._is_writable_directory", return_value=False),
            ):
                os.environ.pop("CODEX_HOME", None)
                client = CodexAppServerClient(cwd=Path(tmp))
                env = client._subprocess_env()

        self.assertIn("CODEX_HOME", env)
        self.assertEqual(env["CODEX_HOME"], str(Path(tmp) / "toc-codex-home"))
        self.assertTrue(client.runtime_contract().fallback_used)

    def test_codex_app_server_fallback_home_preserves_portable_auth_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_home = root / "readonly-codex-home"
            source_home.mkdir()
            (source_home / "auth.json").write_text('{"token":"redacted"}', encoding="utf-8")
            (source_home / "config.toml").write_text("model = \"test\"\n", encoding="utf-8")
            (source_home / "browser").mkdir()
            (source_home / "browser" / "config.toml").write_text("enabled = true\n", encoding="utf-8")
            (source_home / "state_5.sqlite").write_text("do not copy", encoding="utf-8")
            (source_home / "generated_images").mkdir()
            (source_home / "generated_images" / "old.png").write_bytes(PNG_BYTES)

            with (
                patch.dict(os.environ, {"CODEX_HOME": str(source_home), "TOC_CODEX_HOME_FALLBACK_ALLOWED": "1"}, clear=False),
                patch("server.codex_app_server.tempfile.gettempdir", return_value=str(root)),
                patch("server.codex_app_server._is_writable_directory", return_value=False),
            ):
                client = CodexAppServerClient(cwd=root)
                env = client._subprocess_env()

            fallback_home = root / "toc-codex-home"

            self.assertEqual(env["CODEX_HOME"], str(fallback_home))
            self.assertEqual((fallback_home / "auth.json").read_text(encoding="utf-8"), '{"token":"redacted"}')
            self.assertEqual((fallback_home / "config.toml").read_text(encoding="utf-8"), 'model = "test"\n')
            self.assertTrue((fallback_home / "browser" / "config.toml").exists())
            self.assertFalse((fallback_home / "state_5.sqlite").exists())
            self.assertFalse((fallback_home / "generated_images" / "old.png").exists())

    def test_generate_image_fallback_uses_effective_writable_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            generated_dir = root / "toc-codex-home" / "generated_images" / "session"
            generated_dir.mkdir(parents=True)
            client = CodexAppServerClient(cwd=root)

            async def fake_start_thread(**_kwargs):
                return "thread-1"

            async def fake_run_turn(**_kwargs):
                (generated_dir / "generated.png").write_bytes(PNG_BYTES)
                return [{"method": "turn/completed", "params": {"turnId": "turn-1"}}]

            client.start_thread = fake_start_thread  # type: ignore[method-assign]
            client.run_turn = fake_run_turn  # type: ignore[method-assign]

            with patch.dict(os.environ, {"CODEX_HOME": str(root / "toc-codex-home")}, clear=True):
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
        self.assertEqual(result.saved_path, generated_dir / "generated.png")
        self.assertEqual(result.source, "generated_images_fallback")

    def test_codex_transport_error_classification(self) -> None:
        self.assertEqual(
            classify_codex_transport_error("failed to lookup address information: nodename nor servname provided"),
            "dns_resolution_failed",
        )
        self.assertEqual(
            classify_codex_transport_error("stream disconnected before completion: https://chatgpt.com/backend-api/codex/responses"),
            "backend_stream_disconnected",
        )
        self.assertEqual(
            classify_codex_transport_error("Codex app-server CODEX_HOME is not writable; refusing silent fallback"),
            "runtime_environment_failed",
        )
        self.assertTrue(is_codex_transport_error(CodexAppServerTransportError("turn timed out")))

    def test_codex_backend_network_preflight_dns_failure_is_transport_error(self) -> None:
        with (
            patch("server.codex_app_server._network_preflight_cache", {}),
            patch("server.codex_app_server.socket.getaddrinfo", side_effect=OSError("nodename nor servname provided")),
        ):
            with self.assertRaises(CodexAppServerTransportError) as raised:
                preflight_codex_backend_network(timeout_seconds=0.1)

        self.assertEqual(raised.exception.diagnostics["transportErrorKind"], "dns_resolution_failed")
        self.assertEqual(raised.exception.diagnostics["networkPreflight"]["dns"]["status"], "failed")

    def test_codex_backend_network_preflight_accepts_reachable_http_error(self) -> None:
        class FakeResponse:
            status = 405

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with (
            patch("server.codex_app_server._network_preflight_cache", {}),
            patch("server.codex_app_server.socket.getaddrinfo", return_value=[(None, None, None, "", ("127.0.0.1", 443))]),
            patch("server.codex_app_server.urllib.request.urlopen", return_value=FakeResponse()),
        ):
            result = preflight_codex_backend_network(timeout_seconds=0.1)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["dns"]["status"], "passed")
        self.assertEqual(result["https"]["status"], "passed")

    def test_codex_run_turn_timeout_is_total_deadline_not_idle_deadline(self) -> None:
        async def run_case() -> float:
            client = CodexAppServerClient(cwd=Path.cwd())

            async def fake_request(method, _params):
                self.assertEqual(method, "turn/start")
                return {"turn": {"id": "turn-1"}}

            async def feed_notifications():
                for _ in range(20):
                    await client._notifications.put({"method": "item/agentMessage/delta", "params": {"turnId": "turn-1"}})
                    await asyncio.sleep(0.1)

            client.request = fake_request  # type: ignore[method-assign]
            feeder = asyncio.create_task(feed_notifications())
            started = time.monotonic()
            with self.assertRaises(CodexAppServerTransportError):
                await client.run_turn(thread_id="thread-1", text="hello", timeout_seconds=1)
            feeder.cancel()
            with suppress(asyncio.CancelledError):
                await feeder
            return time.monotonic() - started

        elapsed = asyncio.run(run_case())
        self.assertLess(elapsed, 2.5)

    def test_codex_app_server_direct_instantiation_guard_for_runtime_callers(self) -> None:
        root = Path(__file__).resolve().parents[1]
        checked_files = [root / "server" / "image_gen_app.py", root / "scripts" / "run-semantic-review.py", root / "scripts" / "generate-assets-from-manifest.py"]
        offenders = []
        for path in checked_files:
            if "CodexAppServerClient(" in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(root).as_posix())
        self.assertEqual(offenders, [])

    def test_frontend_create_job_does_not_use_nested_app_server_skill(self) -> None:
        source = inspect.getsource(image_gen_app._run_create_job)
        self.assertIn("_run_toc_immersive_frontend_cli_helper", source)
        self.assertNotIn("_run_toc_skill_helper_until_stop_target", source)

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

    def test_codex_bin_can_be_overridden_for_app_server(self) -> None:
        with patch.dict(os.environ, {"TOC_CODEX_BIN": "/opt/homebrew/bin/codex"}):
            client = CodexAppServerClient(cwd=Path("/tmp"))

        self.assertEqual(client.codex_bin, "/opt/homebrew/bin/codex")

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

    def test_toc_skill_helper_waits_for_p680_skill_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            events: list[str] = []

            async def fake_toc_skill_helper(*, topic, source=None, run_id, stop_target="p680"):
                events.append("started")
                write_valid_p680_artifacts(root, run_id)
                await asyncio.sleep(0.02)
                events.append("completed")

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.CREATE_SKILL_STOP_POLL_SECONDS", 0.01),
                patch("server.image_gen_app._run_toc_skill_helper", fake_toc_skill_helper),
                patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
            ):
                asyncio.run(
                    image_gen_app._run_toc_skill_helper_until_stop_target(
                        topic="桃太郎",
                        source="桃太郎",
                        run_id=run_id,
                        stop_target="p680",
                    )
                )

            state = image_gen_app.parse_state_file(root / "output" / run_id / "state.txt")

        self.assertEqual(events, ["started", "completed"])
        self.assertNotIn("runtime.app_server_skill.stop_detected", state)

    def test_create_run_endpoint_uses_title_as_blank_source_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls: list[dict[str, object]] = []
            events: list[tuple[str, str | None]] = []

            async def fake_frontend_cli_helper(**kwargs):
                calls.append(kwargs)
                events.append(("cli", str(kwargs["stop_target"])))
                write_valid_p680_artifacts(root, str(kwargs["run_id"]))
                return "created with images"

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
                    patch("server.image_gen_app._run_toc_immersive_frontend_cli_helper", fake_frontend_cli_helper),
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
        self.assertEqual(
            calls,
            [
                {
                    "topic": "桃太郎",
                    "source": "桃太郎",
                    "run_id": "桃太郎_20260509_1200",
                    "stop_target": "p680",
                }
            ],
        )
        self.assertEqual(events, [("cli", "p680")])
        generate_images.assert_not_awaited()
        upgrade_prompts.assert_not_awaited()
        validate_review.assert_not_called()
        rebuild_index.assert_not_awaited()

    def test_create_run_endpoint_can_disable_image_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli_calls: list[dict[str, object]] = []

            async def fake_frontend_cli_helper(**kwargs):
                cli_calls.append(kwargs)
                write_valid_p650_artifacts(root, str(kwargs["run_id"]))
                return "materialized without images"

            skill_helper = AsyncMock()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen.time.strftime", return_value="20260509_1200"),
                    patch("server.image_gen_app._run_toc_skill_helper_until_stop_target", skill_helper),
                    patch("server.image_gen_app._run_toc_immersive_frontend_cli_helper", fake_frontend_cli_helper),
                    patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
                ):
                    with TestClient(app) as client:
                        create_response = client.post(
                            "/api/image-gen/runs/create",
                            json={"title": "シンデレラ", "source": "シンデレラ", "generate_images": False},
                        )
                        create_payload = create_response.json()
                        final_payload = self._poll_create_job(client, create_payload["jobId"])

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(final_payload["status"], "completed")
        skill_helper.assert_not_awaited()
        self.assertEqual(
            cli_calls,
            [
                {
                    "topic": "シンデレラ",
                    "source": "シンデレラ",
                    "run_id": "シンデレラ_20260509_1200",
                    "stop_target": "p680",
                    "materialize_only": True,
                }
            ],
        )

    def test_create_run_endpoint_passes_title_and_nonblank_source_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls: list[dict[str, object]] = []
            events: list[tuple[str, str | None]] = []

            async def fake_frontend_cli_helper(**kwargs):
                calls.append(kwargs)
                events.append(("cli", str(kwargs["stop_target"])))
                write_valid_p680_artifacts(root, str(kwargs["run_id"]))
                return "created with images"

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
                    patch("server.image_gen_app._run_toc_immersive_frontend_cli_helper", fake_frontend_cli_helper),
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
        self.assertEqual(
            calls,
            [
                {
                    "topic": "桃太郎",
                    "source": "鬼ヶ島の資料",
                    "run_id": "桃太郎_20260509_1200",
                    "stop_target": "p680",
                }
            ],
        )
        self.assertEqual(events, [("cli", "p680")])
        generate_images.assert_not_awaited()
        upgrade_prompts.assert_not_awaited()
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
                    patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                    patch("server.image_gen_app._validate_p560_asset_quality", validate_asset_gate),
                    patch("server.image_gen_app._run_semantic_review", AsyncMock()),
                ):
                    asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            scene_exists = (run_dir / "assets/scenes/scene10_cut1.png").exists()

        self.assertTrue(scene_exists)
        self.assertEqual(generated, [("scene10_cut1", ["hero.png"]), ("scene10_cut2", ["hero.png"]), ("scene10_cut3", ["hero.png"])])
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
                    patch("server.image_gen_app._run_semantic_review", AsyncMock()),
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
                    patch("server.image_gen_app._run_semantic_review", AsyncMock()),
                ):
                    result = asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = (run_dir / "state.txt").read_text(encoding="utf-8")

        self.assertFalse(result)
        self.assertEqual(generated_kinds, ["asset"] * 10 + ["scene"])
        self.assertEqual(repair_prompts.await_count, 9)
        self.assertIn("review.asset_visual_gate.status=needs_frontend_review", state)
        self.assertIn("review.asset_visual_gate.attempts=10", state)

    def test_generate_create_images_continues_media_generation_when_semantic_review_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            generated_kinds: list[str] = []
            mark_ready = Mock()

            async def fake_generate_request_outputs(*, run_dir: Path, kind: str) -> None:
                generated_kinds.append(kind)

            async def fake_run_semantic_review(job_id: str, *, run_dir: Path, stage: str) -> None:
                if stage in {"scene_set", "image_prompt"}:
                    raise RuntimeError(f"{stage} semantic review failed")
                slot = image_gen_app.SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
                if slot:
                    image_gen_app.append_state_snapshot(
                        run_dir / "state.txt",
                        {
                            f"slot.{slot}.status": "done",
                            f"slot.{slot}.note": f"contextless semantic {stage} review passed",
                        },
                    )

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._generate_request_outputs", fake_generate_request_outputs),
                    patch("server.image_gen_app._validate_p560_asset_quality", Mock()),
                    patch("server.image_gen_app._run_semantic_review", fake_run_semantic_review),
                    patch("server.image_gen_app._mark_image_generation_review_ready", mark_ready),
                ):
                    with self.assertRaisesRegex(RuntimeError, "semantic review failed after media generation"):
                        asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(generated_kinds, ["asset", "scene"])
        self.assertEqual(state["review.image.status"], "needs_semantic_review")
        self.assertEqual(state["runtime.stage"], "semantic_review_failed_after_media_generation")
        self.assertEqual(state["slot.p410.status"], "failed")
        self.assertEqual(state["slot.p640.status"], "failed")
        self.assertEqual(state["slot.p660.status"], "done")
        self.assertEqual(state["slot.p670.status"], "failed")
        self.assertEqual(state["slot.p680.status"], "pending")
        mark_ready.assert_not_called()

    def test_semantic_review_failure_invokes_producer_repair_then_rereviews(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            review_turns = 0
            repair_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text("# collection\n\nscene meaning under review\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(json.dumps({"entry_count": 1}, ensure_ascii=False) + "\n", encoding="utf-8")
                (run_dir / paths["prompt"]).write_text("# review prompt\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    nonlocal review_turns, repair_turns
                    if "Semantic QA Producer Repair" in text:
                        repair_turns += 1
                        repair_paths = semantic_repair_relpaths(stage, 1)
                        (run_dir / repair_paths["report"]).write_text("status: done\nchanged_artifacts: [script.md]\n", encoding="utf-8")
                        return None
                    review_turns += 1
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    status = "failed" if review_turns == 1 else "passed"
                    (run_dir / paths["report"]).write_text(f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: []\nfindings: []\n", encoding="utf-8")
                    return None

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
            ):
                asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            raw_state = (run_dir / "state.txt").read_text(encoding="utf-8")
            repair_paths = semantic_repair_relpaths(stage, 1)
            repair_prompt_exists = (run_dir / repair_paths["prompt"]).exists()
            repair_report_exists = (run_dir / repair_paths["report"]).exists()

        self.assertEqual(review_turns, 2)
        self.assertEqual(repair_turns, 1)
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.repair.status"], "done")
        self.assertEqual(state["slot.p410.status"], "done")
        self.assertIn("review.semantic.scene_set.loop.status=repairing", raw_state)
        self.assertIn("review.semantic.scene_set.repair.status=in_progress", raw_state)
        self.assertTrue(repair_prompt_exists)
        self.assertTrue(repair_report_exists)

    def test_semantic_review_reuses_non_stale_passed_report_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "asset_plan"
            source_path = run_dir / "asset_plan.md"
            source_path.write_text("# asset plan\n\nmeaningful source\n", encoding="utf-8")
            paths = image_gen_app.semantic_review_relpaths(stage)
            (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
            (run_dir / paths["collection"]).write_text("# collection\n", encoding="utf-8")
            (run_dir / paths["scope"]).write_text(
                json.dumps({"entry_count": 1, "source_artifacts": ["asset_plan.md"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (run_dir / paths["prompt"]).write_text("# prompt\n", encoding="utf-8")
            (run_dir / paths["report"]).write_text(
                "status: passed\nreviewed_entries: [asset_1]\nblocked_entries: []\nfindings: []\n",
                encoding="utf-8",
            )

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run") as build_pack,
                patch("server.image_gen_app.create_codex_app_server_client") as create_client,
            ):
                asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        build_pack.assert_not_called()
        create_client.assert_not_called()
        self.assertEqual(state["review.semantic.asset_plan.status"], "passed")
        self.assertEqual(state["review.semantic.asset_plan.loop.status"], "passed")
        self.assertEqual(state["review.semantic.asset_plan.loop.attempt"], "0")
        self.assertEqual(state["review.semantic.asset_plan.reuse.status"], "reused_passed_report")
        self.assertEqual(state["slot.p540.status"], "done")

    def test_semantic_review_does_not_reuse_stale_passed_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "asset_plan"
            source_path = run_dir / "asset_plan.md"
            source_path.write_text("# asset plan\n\nold source\n", encoding="utf-8")
            paths = image_gen_app.semantic_review_relpaths(stage)
            (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
            (run_dir / paths["collection"]).write_text("# collection\n", encoding="utf-8")
            (run_dir / paths["scope"]).write_text(
                json.dumps({"entry_count": 1, "source_artifacts": ["asset_plan.md"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (run_dir / paths["prompt"]).write_text("# prompt\n", encoding="utf-8")
            (run_dir / paths["report"]).write_text(
                "status: passed\nreviewed_entries: [asset_1]\nblocked_entries: []\nfindings: []\n",
                encoding="utf-8",
            )
            time.sleep(0.01)
            source_path.write_text("# asset plan\n\nupdated source\n", encoding="utf-8")
            review_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                (run_dir / paths["collection"]).write_text("# rebuilt collection\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(
                    json.dumps({"entry_count": 1, "source_artifacts": ["asset_plan.md"]}, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                (run_dir / paths["prompt"]).write_text("# rebuilt prompt\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, **_kwargs):
                    nonlocal review_turns
                    review_turns += 1
                    (run_dir / paths["report"]).write_text(
                        "status: passed\nreviewed_entries: [asset_1]\nblocked_entries: []\nfindings: []\n",
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
            ):
                asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(review_turns, 1)
        self.assertEqual(state["review.semantic.asset_plan.status"], "passed")
        self.assertNotIn("review.semantic.asset_plan.reuse.status", state)

    def test_semantic_review_repeats_repair_until_later_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            review_turns = 0
            repair_rounds: list[int] = []

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text("# collection\n\nscene meaning under review\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(json.dumps({"entry_count": 1}, ensure_ascii=False) + "\n", encoding="utf-8")
                (run_dir / paths["prompt"]).write_text("# review prompt\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    nonlocal review_turns
                    if "Semantic QA Producer Repair" in text:
                        round_number = 1 if "Repair round: `1`" in text else 2
                        repair_rounds.append(round_number)
                        repair_paths = semantic_repair_relpaths(stage, round_number)
                        (run_dir / repair_paths["report"]).write_text(
                            "status: done\nchanged_artifacts: [script.md, video_manifest.md]\nreviewer_findings_addressed: [remaining semantic drift]\n",
                            encoding="utf-8",
                        )
                        return None
                    review_turns += 1
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    status = "passed" if review_turns == 3 else "failed"
                    findings = "[]" if status == "passed" else "[remaining semantic drift]"
                    (run_dir / paths["report"]).write_text(
                        f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: []\nfindings: {findings}\n",
                        encoding="utf-8",
                    )
                    return None

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
            ):
                asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=5))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(review_turns, 3)
        self.assertEqual(repair_rounds, [1, 2])
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.repair.status"], "done")
        self.assertEqual(state["slot.p410.status"], "done")

    def test_semantic_review_transport_failure_does_not_invoke_producer_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            review_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text("# collection\n\nscene meaning under review\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(json.dumps({"entry_count": 1}, ensure_ascii=False) + "\n", encoding="utf-8")
                (run_dir / paths["prompt"]).write_text("# review prompt\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, **_kwargs):
                    nonlocal review_turns
                    review_turns += 1
                    raise CodexAppServerTransportError(
                        "stream disconnected before completion: error sending request for url (https://chatgpt.com/backend-api/codex/responses)"
                    )

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
            ):
                with self.assertRaisesRegex(CodexAppServerTransportError, "stream disconnected"):
                    asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            repair_paths = semantic_repair_relpaths(stage, 1)
            repair_prompt_exists = (run_dir / repair_paths["prompt"]).exists()

        self.assertEqual(review_turns, 1)
        self.assertEqual(state["review.semantic.scene_set.transport.status"], "failed")
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "blocked_transport")
        self.assertFalse(repair_prompt_exists)

    def test_semantic_review_hard_timeout_blocks_as_transport(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"

            async def never_finishes(*_args, **_kwargs):
                await asyncio.Event().wait()

            with (
                patch("server.image_gen_app._run_semantic_review_once", never_finishes),
                patch("server.image_gen_app._semantic_review_once_hard_timeout_seconds", lambda: 0.01),
            ):
                with self.assertRaisesRegex(CodexAppServerTransportError, "timed out"):
                    asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(state["review.semantic.scene_set.loop.status"], "blocked_transport")
        self.assertEqual(state["review.semantic.scene_set.transport.status"], "failed")
        self.assertEqual(state["review.semantic.scene_set.transport.error_kind"], "timeout")
        self.assertEqual(state["runtime.app_server.transport.status"], "failed")

    def test_semantic_review_repair_transport_failure_blocks_without_semantic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            review_turns = 0
            repair_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text("# collection\n\nscene meaning under review\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(json.dumps({"entry_count": 1}, ensure_ascii=False) + "\n", encoding="utf-8")
                (run_dir / paths["prompt"]).write_text("# review prompt\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    nonlocal review_turns, repair_turns
                    if "Semantic QA Producer Repair" in text:
                        repair_turns += 1
                        raise CodexAppServerTransportError("turn timed out")
                    review_turns += 1
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    (run_dir / paths["report"]).write_text(
                        "status: failed\nreviewed_entries: [scene_1]\nblocked_entries: [scene_1]\nfindings:\n  - wrong meaning\n",
                        encoding="utf-8",
                    )
                    return None

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
            ):
                with self.assertRaisesRegex(CodexAppServerTransportError, "turn timed out"):
                    asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(review_turns, 1)
        self.assertEqual(repair_turns, 1)
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "blocked_transport")
        self.assertEqual(state["review.semantic.scene_set.repair.status"], "blocked_transport")
        self.assertEqual(state["review.semantic.scene_set.repair.transport.status"], "failed")
        self.assertEqual(state["runtime.app_server.transport.status"], "failed")

    def test_semantic_review_rereviews_after_repair_timeout_when_source_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            (run_dir / "script.md").write_text("# Script\n\nold scene meaning\n", encoding="utf-8")
            review_turns = 0
            repair_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text("# collection\n\nscene meaning under review\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(
                    json.dumps({"entry_count": 1, "source_artifacts": ["script.md"]}, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                (run_dir / paths["prompt"]).write_text("# review prompt\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    nonlocal review_turns, repair_turns
                    if "Semantic QA Producer Repair" in text:
                        repair_turns += 1
                        (run_dir / "script.md").write_text("# Script\n\nrepaired scene meaning\n", encoding="utf-8")
                        raise CodexAppServerTransportError("turn timed out")
                    review_turns += 1
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    status = "passed" if "repaired scene meaning" in (run_dir / "script.md").read_text(encoding="utf-8") else "failed"
                    (run_dir / paths["report"]).write_text(
                        f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: []\nfindings: []\n",
                        encoding="utf-8",
                    )
                    return None

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
            ):
                asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(review_turns, 2)
        self.assertEqual(repair_turns, 1)
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.repair.status"], "done")
        self.assertEqual(state["review.semantic.scene_set.repair.transport.status"], "salvaged_after_source_artifact_change")
        self.assertEqual(state["review.semantic.scene_set.repair.changed_artifacts_detected"], "script.md")
        self.assertNotIn("runtime.app_server.transport.status", state)

    def test_semantic_review_rereviews_after_repair_hard_timeout_when_source_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            paths = image_gen_app.semantic_review_relpaths(stage)
            (run_dir / paths["scope"]).parent.mkdir(parents=True, exist_ok=True)
            (run_dir / paths["scope"]).write_text(
                json.dumps({"entry_count": 1, "source_artifacts": ["script.md"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text("# Script\n\nold scene meaning\n", encoding="utf-8")
            review_turns = 0
            repair_turns = 0

            async def fake_run_once(*_args, **_kwargs):
                nonlocal review_turns
                review_turns += 1
                if review_turns == 1:
                    return image_gen_app.SemanticReviewStatus(status="failed", entry_count=1, errors=("wrong meaning",))
                return image_gen_app.SemanticReviewStatus(status="passed", entry_count=1, errors=())

            async def slow_repair(*_args, **_kwargs):
                nonlocal repair_turns
                repair_turns += 1
                (run_dir / "script.md").write_text("# Script\n\nrepaired scene meaning\n", encoding="utf-8")
                await asyncio.Event().wait()

            with (
                patch("server.image_gen_app._run_semantic_review_once", fake_run_once),
                patch("server.image_gen_app._run_semantic_review_producer_repair", slow_repair),
                patch("server.image_gen_app._semantic_repair_once_hard_timeout_seconds", lambda: 0.01),
            ):
                asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(review_turns, 2)
        self.assertEqual(repair_turns, 1)
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.repair.status"], "done")
        self.assertEqual(state["review.semantic.scene_set.repair.transport.status"], "salvaged_after_source_artifact_change")
        self.assertEqual(state["review.semantic.scene_set.repair.changed_artifacts_detected"], "script.md")
        self.assertNotIn("runtime.app_server.transport.status", state)

    def test_semantic_review_accepts_completed_repair_report_after_turn_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            review_turns = 0
            repair_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text("# collection\n\nscene meaning under review\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(json.dumps({"entry_count": 1}, ensure_ascii=False) + "\n", encoding="utf-8")
                (run_dir / paths["prompt"]).write_text("# review prompt\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    nonlocal review_turns, repair_turns
                    if "Semantic QA Producer Repair" in text:
                        repair_turns += 1
                        repair_paths = semantic_repair_relpaths(stage, 1)
                        (run_dir / repair_paths["report"]).write_text("status: done\nchanged_artifacts: [script.md]\n", encoding="utf-8")
                        raise CodexAppServerTransportError("turn timed out")
                    review_turns += 1
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    status = "failed" if review_turns == 1 else "passed"
                    (run_dir / paths["report"]).write_text(
                        f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: []\nfindings: []\n",
                        encoding="utf-8",
                    )
                    return None

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
            ):
                asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(review_turns, 2)
        self.assertEqual(repair_turns, 1)
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.repair.status"], "done")
        self.assertEqual(state["review.semantic.scene_set.transport.status"], "passed")
        self.assertNotIn("runtime.app_server.transport.status", state)

    def test_semantic_review_accepts_completed_failed_review_report_after_turn_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            review_turns = 0
            repair_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text("# collection\n\nscene meaning under review\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(json.dumps({"entry_count": 1}, ensure_ascii=False) + "\n", encoding="utf-8")
                (run_dir / paths["prompt"]).write_text("# review prompt\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    nonlocal review_turns, repair_turns
                    if "Semantic QA Producer Repair" in text:
                        repair_turns += 1
                        repair_paths = semantic_repair_relpaths(stage, 1)
                        (run_dir / repair_paths["report"]).write_text("status: done\nchanged_artifacts: [script.md]\n", encoding="utf-8")
                        return None
                    review_turns += 1
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    status = "failed" if review_turns == 1 else "passed"
                    (run_dir / paths["report"]).write_text(
                        f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: []\nfindings: [semantic drift]\n",
                        encoding="utf-8",
                    )
                    if review_turns == 1:
                        raise CodexAppServerTransportError("turn timed out")
                    return None

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
            ):
                asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(review_turns, 2)
        self.assertEqual(repair_turns, 1)
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.repair.status"], "done")
        self.assertEqual(state["review.semantic.scene_set.transport.status"], "passed")

    def test_semantic_review_advances_when_report_finishes_before_turn_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            review_turns = 0
            repair_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text("# collection\n\nscene meaning under review\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(json.dumps({"entry_count": 1}, ensure_ascii=False) + "\n", encoding="utf-8")
                (run_dir / paths["prompt"]).write_text("# review prompt\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    nonlocal review_turns, repair_turns
                    if "Semantic QA Producer Repair" in text:
                        repair_turns += 1
                        repair_paths = semantic_repair_relpaths(stage, 1)
                        (run_dir / repair_paths["report"]).write_text("status: done\nchanged_artifacts: [script.md]\n", encoding="utf-8")
                        await asyncio.Event().wait()
                    review_turns += 1
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    status = "failed" if review_turns == 1 else "passed"
                    (run_dir / paths["report"]).write_text(
                        f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: []\nfindings: [semantic drift]\n",
                        encoding="utf-8",
                    )
                    if review_turns == 1:
                        await asyncio.Event().wait()
                    return None

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                patch("server.image_gen_app.SEMANTIC_TURN_ARTIFACT_POLL_SECONDS", 0.01),
                patch("server.image_gen_app.SEMANTIC_TURN_COMPLETION_GRACE_SECONDS", 0.01),
            ):
                asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(review_turns, 2)
        self.assertEqual(repair_turns, 1)
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.repair.status"], "done")
        self.assertEqual(state["review.semantic.scene_set.transport.status"], "passed")

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
                    patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                    patch("server.image_gen_app._validate_p560_asset_quality", Mock()),
                    patch("server.image_gen_app._run_semantic_review", AsyncMock()),
                ):
                    with self.assertRaisesRegex(RuntimeError, "scene generation group 1 incomplete|did not return an image"):
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
                with patch("server.image_gen_app.ROOT", Path(tmp)), patch("server.image_gen_app.create_codex_app_server_client", FakeClient):
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
                with patch("server.image_gen_app.ROOT", Path(tmp)), patch("server.image_gen_app.create_codex_app_server_client", FakeClient):
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
                with patch("server.image_gen_app.ROOT", Path(tmp)), patch("server.image_gen_app.create_codex_app_server_client", FakeClient):
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
        self.assertIn('"destinationDetails"', log_payload)
        self.assertIn('"referenceDetails"', log_payload)
        self.assertIn('"referenceCount": 0', log_payload)
        self.assertTrue(prompt_log_exists)
        self.assertIn('"prompt": "prompt"', prompt_log_payload)

    def test_create_flow_logs_local_raster_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **_kwargs):
                    return ImageGenerationResult(
                        saved_path=Path("/tmp/local.png"),
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                        source="local_raster_generation_after_app_server_permission_failure",
                    )

            item = image_gen.ImageRequestItem(
                id="scene1_cut1",
                kind="scene",
                asset_type=None,
                tool="codex_builtin_image",
                output="assets/scenes/scene1.png",
                prompt="実写映画風。",
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image=None,
            )

            with (
                patch("server.image_gen_app.ROOT", Path(tmp)),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
            ):
                with self.assertRaisesRegex(CodexAppServerError, "unsupported local raster fallback"):
                    asyncio.run(image_gen_app._generate_request_item_output(run_dir=run_dir, kind="scene", item=item))

            prompt_log = run_dir / "logs" / "image_generation_prompts.jsonl"
            payload = prompt_log.read_text(encoding="utf-8")
            event_payload = (run_dir / "logs" / "app_server" / "events.jsonl").read_text(encoding="utf-8")

        self.assertIn("local_raster_generation_after_app_server_permission_failure", payload)
        self.assertIn("unsupported local raster fallback", payload)
        self.assertIn('"destinationDetails"', payload)
        self.assertIn('"referenceCount": 0', payload)
        self.assertIn('"operation": "request_item_generation"', event_payload)
        self.assertIn('"status": "failed"', event_payload)

    def test_create_flow_retries_transient_codex_image_disconnect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            generated = Path(tmp) / "generated.png"
            generated.write_bytes(PNG_BYTES)

            class FakeClient:
                attempts = 0

                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **_kwargs):
                    type(self).attempts += 1
                    if type(self).attempts == 1:
                        raise CodexAppServerError(
                            "stream disconnected before completion: error sending request for url "
                            "(https://chatgpt.com/backend-api/codex/responses)"
                        )
                    return ImageGenerationResult(
                        saved_path=generated,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                    )

            item = image_gen.ImageRequestItem(
                id="scene1_cut1",
                kind="scene",
                asset_type=None,
                tool="codex_builtin_image",
                output="assets/scenes/scene1.png",
                prompt="実写映画風。",
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image=None,
            )

            with (
                patch("server.image_gen_app.ROOT", Path(tmp)),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
            ):
                asyncio.run(image_gen_app._generate_request_item_output(run_dir=run_dir, kind="scene", item=item))

            event_payload = (run_dir / "logs" / "app_server" / "events.jsonl").read_text(encoding="utf-8")
            output_exists = (run_dir / "assets" / "scenes" / "scene1.png").exists()

        self.assertEqual(FakeClient.attempts, 2)
        self.assertTrue(output_exists)
        self.assertIn('"operation": "request_item_generation_retry"', event_payload)
        self.assertIn('"status": "retrying"', event_payload)

    def test_image_generation_item_timeout_fails_without_hanging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)

            class SlowClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **_kwargs):
                    await asyncio.sleep(5)
                    raise AssertionError("unreachable")

            item = image_gen.ImageRequestItem(
                id="slow_scene",
                kind="scene",
                asset_type=None,
                tool="codex_builtin_image",
                output="assets/scenes/slow_scene.png",
                prompt="実写映画風。",
                references=[],
                reference_count=0,
                execution_lane="standard",
                generation_status=None,
                existing_image=None,
            )

            with (
                patch("server.image_gen_app.ROOT", Path(tmp)),
                patch("server.image_gen_app.create_codex_app_server_client", SlowClient),
                patch("server.image_gen_app.IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS", 0.01),
                patch("server.image_gen_app.IMAGE_GENERATION_ITEM_MAX_ATTEMPTS", 1),
            ):
                with self.assertRaises(TimeoutError):
                    asyncio.run(image_gen_app._generate_request_item_output(run_dir=run_dir, kind="scene", item=item))

            event_payload = (run_dir / "logs" / "app_server" / "events.jsonl").read_text(encoding="utf-8")

        self.assertIn('"operation": "request_item_generation"', event_payload)
        self.assertIn('"status": "failed"', event_payload)

    def test_image_generation_app_server_start_timeout_fails_without_hanging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)

            class SlowStartClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    await asyncio.sleep(5)

                async def stop(self):
                    return None

            item = image_gen.ImageRequestItem(
                id="slow_start_scene",
                kind="scene",
                asset_type=None,
                tool="codex_builtin_image",
                output="assets/scenes/slow_start_scene.png",
                prompt="実写映画風。",
                references=[],
                reference_count=0,
                execution_lane="standard",
                generation_status=None,
                existing_image=None,
            )

            with (
                patch("server.image_gen_app.ROOT", Path(tmp)),
                patch("server.image_gen_app.create_codex_app_server_client", SlowStartClient),
                patch("server.image_gen_app.CODEX_APP_SERVER_START_TIMEOUT_SECONDS", 0.01),
                patch("server.image_gen_app.IMAGE_GENERATION_ITEM_MAX_ATTEMPTS", 1),
            ):
                with self.assertRaises(TimeoutError):
                    asyncio.run(image_gen_app._generate_request_item_output(run_dir=run_dir, kind="scene", item=item))

            event_payload = (run_dir / "logs" / "app_server" / "events.jsonl").read_text(encoding="utf-8")

        self.assertIn('"operation": "request_item_generation"', event_payload)
        self.assertIn('"status": "failed"', event_payload)

    def test_request_generation_is_serialized_per_run_and_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            active = 0
            max_active = 0

            async def fake_unlocked(*, run_dir: Path, kind: str) -> None:
                nonlocal active, max_active
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.05)
                active -= 1

            async def run_two() -> None:
                await asyncio.gather(
                    image_gen_app._generate_request_outputs(run_dir=run_dir, kind="scene"),
                    image_gen_app._generate_request_outputs(run_dir=run_dir, kind="scene"),
                )

            with patch("server.image_gen_app._generate_request_outputs_unlocked", fake_unlocked):
                asyncio.run(run_two())

        self.assertEqual(max_active, 1)

    def test_create_flow_regenerates_existing_output_without_completed_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            destination = run_dir / "assets" / "objects" / "stale.png"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"stale")
            generated = Path(tmp) / "generated.png"
            generated.write_bytes(PNG_BYTES)

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **_kwargs):
                    return ImageGenerationResult(
                        saved_path=generated,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                    )

            item = image_gen.ImageRequestItem(
                id="stale_asset",
                kind="asset",
                asset_type=None,
                tool="codex_builtin_image",
                output="assets/objects/stale.png",
                prompt="実写映画風。",
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image=None,
            )

            with (
                patch("server.image_gen_app.ROOT", Path(tmp)),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
            ):
                asyncio.run(image_gen_app._generate_request_item_output(run_dir=run_dir, kind="asset", item=item))

            event_payload = (run_dir / "logs" / "app_server" / "events.jsonl").read_text(encoding="utf-8")
            destination_bytes = destination.read_bytes()

        self.assertEqual(destination_bytes, PNG_BYTES)
        self.assertIn("removed existing destination without completed app-server provenance", event_payload)
        self.assertIn('"status": "completed"', event_payload)

    def test_create_flow_skips_existing_output_with_completed_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            destination = run_dir / "assets" / "objects" / "done.png"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(PNG_BYTES)
            image_gen.write_app_server_image_debug_log(
                run_dir=run_dir,
                item_id="done_asset",
                index=1,
                destination=destination,
                references=[],
                prompt="実写映画風。",
                kind="asset",
                result=ImageGenerationResult(
                    saved_path=destination,
                    revised_prompt=None,
                    status="completed",
                    transcript=[],
                    source="app_server",
                ),
            )

            class FailingClient:
                def __init__(self, **_kwargs):
                    raise AssertionError("existing provenanced output should be skipped")

            item = image_gen.ImageRequestItem(
                id="done_asset",
                kind="asset",
                asset_type=None,
                tool="codex_builtin_image",
                output="assets/objects/done.png",
                prompt="実写映画風。",
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image=None,
            )

            with (
                patch("server.image_gen_app.ROOT", Path(tmp)),
                patch("server.image_gen_app.create_codex_app_server_client", FailingClient),
            ):
                asyncio.run(image_gen_app._generate_request_item_output(run_dir=run_dir, kind="asset", item=item))

            event_payload = (run_dir / "logs" / "app_server" / "events.jsonl").read_text(encoding="utf-8")
            destination_bytes = destination.read_bytes()

        self.assertEqual(destination_bytes, PNG_BYTES)
        self.assertIn('"reason": "destination already exists"', event_payload)

    def test_create_flow_hands_off_when_asset_prompt_repair_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            calls: list[str] = []

            async def fake_generate_request_outputs(*, run_dir: Path, kind: str) -> None:
                calls.append(kind)

            def fake_validate_p560_asset_quality(_run_dir: Path) -> None:
                raise RuntimeError("p560 bootstrap asset visual gate failed: low detail raster")

            async def fake_repair_bootstrap_asset_prompts(*_args: Any, **_kwargs: Any) -> None:
                raise TimeoutError("repair timed out")

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._generate_request_outputs", fake_generate_request_outputs),
                patch("server.image_gen_app._validate_p560_asset_quality", fake_validate_p560_asset_quality),
                patch("server.image_gen_app._repair_bootstrap_asset_prompts", fake_repair_bootstrap_asset_prompts),
                patch("server.image_gen_app._run_semantic_review", AsyncMock()),
            ):
                result = asyncio.run(image_gen_app._generate_create_images("job-1", run_id="sample_run"))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            event_payload = (run_dir / "logs" / "app_server" / "events.jsonl").read_text(encoding="utf-8")

        self.assertFalse(result)
        self.assertEqual(calls, ["asset", "scene"])
        self.assertEqual(state["review.asset_visual_gate.status"], "needs_frontend_review")
        self.assertEqual(state["review.asset_visual_gate.repair.status"], "failed")
        self.assertEqual(state["slot.p680.status"], "awaiting_approval")
        self.assertIn('"operation": "prompt_repair"', event_payload)
        self.assertIn('"status": "failed"', event_payload)

    def test_request_generation_group_cancels_sibling_items_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "asset_generation_requests.md").write_text(
                """# Asset Generation Requests

## fast_fail

- output: `assets/objects/fast_fail.png`

```text
fail prompt
```

## slow_item

- output: `assets/objects/slow_item.png`

```text
slow prompt
```
""",
                encoding="utf-8",
            )
            slow_cancelled = False

            async def fake_generate_item(*, run_dir: Path, kind: str, item: Any) -> None:
                nonlocal slow_cancelled
                if item.id == "fast_fail":
                    await asyncio.sleep(0.05)
                    raise RuntimeError("fast failure")
                try:
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    slow_cancelled = True
                    raise

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.IMAGE_GENERATION_PARALLELISM", 2),
                patch("server.image_gen_app._generate_request_item_output", fake_generate_item),
                patch.dict(os.environ, {"TOC_IMAGE_GEN_DISABLE_CODEX_APP_SERVER": ""}, clear=False),
            ):
                with self.assertRaisesRegex(RuntimeError, "fast failure"):
                    asyncio.run(image_gen_app._generate_request_outputs(run_dir=run_dir, kind="asset"))

            event_payload = (run_dir / "logs" / "app_server" / "events.jsonl").read_text(encoding="utf-8")

        self.assertTrue(slow_cancelled)
        self.assertIn('"operation": "request_generation_group"', event_payload)
        self.assertIn('"status": "failed"', event_payload)

    def test_request_generation_group_does_not_start_queued_items_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "asset_generation_requests.md").write_text(
                """# Asset Generation Requests

## fast_fail

- output: `assets/objects/fast_fail.png`

```text
fail prompt
```

## slow_item

- output: `assets/objects/slow_item.png`

```text
slow prompt
```

## queued_item

- output: `assets/objects/queued_item.png`

```text
queued prompt
```
""",
                encoding="utf-8",
            )
            started: list[str] = []

            async def fake_generate_item(*, run_dir: Path, kind: str, item: Any) -> None:
                started.append(item.id)
                if item.id == "fast_fail":
                    await asyncio.sleep(0.02)
                    raise RuntimeError("fast failure")
                await asyncio.sleep(1)

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.IMAGE_GENERATION_PARALLELISM", 2),
                patch("server.image_gen_app._generate_request_item_output", fake_generate_item),
                patch.dict(os.environ, {"TOC_IMAGE_GEN_DISABLE_CODEX_APP_SERVER": ""}, clear=False),
            ):
                with self.assertRaisesRegex(RuntimeError, "fast failure"):
                    asyncio.run(image_gen_app._generate_request_outputs(run_dir=run_dir, kind="asset"))

        self.assertIn("fast_fail", started)
        self.assertIn("slow_item", started)
        self.assertNotIn("queued_item", started)

    def test_scene_generation_continues_after_item_failure_for_resume_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## fail_scene

- output: `assets/scenes/fail_scene.png`

```text
fail prompt
```

## good_scene

- output: `assets/scenes/good_scene.png`

```text
good prompt
```
""",
                encoding="utf-8",
            )
            started: list[str] = []

            async def fake_generate_item(*, run_dir: Path, kind: str, item: Any) -> None:
                started.append(item.id)
                if item.id == "fail_scene":
                    raise RuntimeError("scene failure")
                output = image_gen_app.resolve_run_relative(run_dir, item.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(PNG_BYTES)

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.IMAGE_GENERATION_PARALLELISM", 1),
                patch("server.image_gen_app._generate_request_item_output", fake_generate_item),
                patch.dict(os.environ, {"TOC_IMAGE_GEN_CONTINUE_ON_ITEM_ERROR": ""}, clear=False),
            ):
                with self.assertRaisesRegex(RuntimeError, "scene generation group 1 incomplete"):
                    asyncio.run(image_gen_app._generate_request_outputs(run_dir=run_dir, kind="scene"))

            good_exists = (run_dir / "assets" / "scenes" / "good_scene.png").exists()

        self.assertEqual(started, ["fail_scene", "good_scene"])
        self.assertTrue(good_exists)

    def test_prompt_regeneration_failure_writes_app_server_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)

            class FakeClient:
                async def regenerate_prompt(self, **_kwargs):
                    raise CodexAppServerError("prompt regeneration failed")

            with self.assertRaisesRegex(CodexAppServerError, "prompt regeneration failed"):
                asyncio.run(
                    image_gen_app._regenerate_prompt_with_log(
                        FakeClient(),  # type: ignore[arg-type]
                        run_dir=run_dir,
                        item={"id": "scene1"},
                        target="scene",
                        instruction="rewrite",
                        setting_content="setting",
                        operation="prompt_regeneration",
                    )
                )

            events = run_dir / "logs" / "app_server" / "events.jsonl"
            payload = events.read_text(encoding="utf-8")

        self.assertIn('"operation": "prompt_regeneration"', payload)
        self.assertIn('"status": "failed"', payload)
        self.assertIn("prompt regeneration failed", payload)

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
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.create_codex_app_server_client", FakeClient):
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
            scene_folder_exists = (run_dir / "assets" / "scenes" / "scene10_cut4").is_dir()
            audio_folder_exists = (run_dir / "assets" / "audio" / "scene10_cut4").is_dir()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selector"], "scene10_cut4")
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
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.create_codex_app_server_client", FakeClient):
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
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.create_codex_app_server_client", FakeClient):
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
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.create_codex_app_server_client", FakeClient):
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
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.create_codex_app_server_client", FakeClient):
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
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.create_codex_app_server_client", FakeClient):
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
                            parent_run / "assets/test/image_gen_candidates/scene1_cut1/scene1_cut1_candidate_01.png"
                        ).resolve().exists()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(generated_exists)

    def test_insert_bulk_rejects_candidate_when_item_id_does_not_match_output_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "asset_generation_requests.md").write_text(
                """# Asset Generation Requests

## object_alpha_ref

- output: `assets/objects/object_alpha_ref.png`

```text
object alpha
```

## location_beta_ref

- output: `assets/locations/location_beta_ref.png`

```text
location beta
```
""",
                encoding="utf-8",
            )
            candidate = run_dir / "assets/test/image_gen_candidates/object_alpha_ref/object_alpha_ref_candidate_01.png"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(PNG_BYTES)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/insert-bulk",
                            json={
                                "items": [
                                    {
                                        "run_id": "sample_run",
                                        "candidate_path": "assets/test/image_gen_candidates/object_alpha_ref/object_alpha_ref_candidate_01.png",
                                        "output": "assets/locations/location_beta_ref.png",
                                    }
                                ]
                            },
                        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("candidate item mismatch", response.text)

    def test_bulk_generation_flattens_candidates_across_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "parent"
            run_dir.mkdir(parents=True)
            active = 0
            max_active = 0
            calls: list[tuple[str, int]] = []

            async def fake_generate_one(_run_dir: Path, req: Any, index: int) -> dict[str, Any]:
                nonlocal active, max_active
                active += 1
                max_active = max(max_active, active)
                calls.append((req.item_id, index))
                await asyncio.sleep(0.01)
                active -= 1
                return {
                    "index": index,
                    "status": "completed",
                    "path": f"assets/test/image_gen_candidates/{req.item_id}/candidate_{index:02d}.png",
                }

            items = [
                {
                    "run_id": "child",
                    "kind": "asset",
                    "item_id": f"scene{i}_cut1",
                    "prompt": "prompt",
                    "references": [],
                    "candidate_count": 2,
                }
                for i in range(1, 6)
            ]

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app._generate_one", fake_generate_one):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/generate-bulk",
                            json={
                                "run_id": "parent",
                                "kind": "scene",
                                "items": items,
                                "concurrency": 10,
                            },
                        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["results"]), 5)
        self.assertTrue(all(len(result["candidates"]) == 2 for result in body["results"]))
        self.assertEqual(len(calls), 10)
        self.assertEqual(max_active, 10)


if __name__ == "__main__":
    unittest.main()
