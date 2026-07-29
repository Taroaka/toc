from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import inspect
import json
import re
import shutil
import subprocess
import tempfile
import threading
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
    _read_codex_cli_version,
    classify_codex_transport_error,
    create_codex_app_server_client,
    default_app_server_model,
    find_agent_message_texts,
    find_image_generation_items,
    image_generation_saved_path,
    is_codex_transport_error,
    minimum_app_server_version,
    parse_codex_cli_version,
    preflight_codex_backend_network,
    reject_local_raster_image_result,
    wait_for_generated_image_after,
    wait_for_unclaimed_generated_image_after,
)
from server.image_gen_app import (
    _toc_immersive_command,
    _toc_run_command,
    _toc_world_walk_command,
    _validate_created_run,
    _validate_frontend_create_run,
    _validate_materialized_p650_run,
    _validate_p650_run,
)
from toc.semantic_review import FOUNDATION_SEMANTIC_CRITERIA
from toc.video_provider_capabilities import resolve_video_provider_capabilities
from toc.harness import load_structured_document
from toc.grounding import build_stage_grounding_readset, resolve_stage_grounding
from toc.semantic_review_loop import semantic_repair_relpaths
from toc.review_loop import (
    build_review_input_snapshot,
    review_input_snapshot_issues,
    write_review_input_snapshot,
)
from toc.runtime_locks import FileLockUnavailable, sync_file_lock
from toc.image_request_snapshot import (
    ImageRequestSnapshotError,
    load_request_snapshot,
    materialize_request_snapshot,
    write_request_snapshot_atomic,
)


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
REVIEWABLE_VIDEO_PROMPT = (
    "action: 主人公が画面奥へ一歩進み、右足を床につけて止まる。\n"
    "camera: slow dolly forward"
)


def load_headless_create_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "toc-create-run-headless.py"
    spec = importlib.util.spec_from_file_location("toc_create_run_headless_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_frontend_runner_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "toc-immersive-frontend-run.py"
    spec = importlib.util.spec_from_file_location("toc_immersive_frontend_run_api_integration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_test_png(path: Path, color: tuple[int, int, int] = (120, 80, 40), size: tuple[int, int] = (320, 180)) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


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
    entry_ids = [f"{stage}_entry_{index + 1}" for index in range(entry_count)]
    source_relpath = Path("logs/review/semantic") / f"{stage}.source.md"
    source_path = run_dir / source_relpath
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(f"# Semantic Review Source\n\nstage: {stage}\n", encoding="utf-8")
    for key, relpath in relpaths.items():
        path = run_dir / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        if key == "scope":
            path.write_text(
                json.dumps(
                    {
                        "stage": stage,
                        "entry_count": entry_count,
                        "entry_ids": entry_ids,
                        "selectors": entry_ids,
                        "review_scope": "all_entries",
                        "source_artifacts": [source_relpath.as_posix()],
                        "artifacts": {artifact_key: artifact_path.as_posix() for artifact_key, artifact_path in relpaths.items()},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
        elif key == "report":
            criteria_results = [
                {
                    "criterion_id": criterion_id,
                    "status": "passed",
                    "evidence": f"{stage}.md:{criterion_id}",
                }
                for criterion_id in FOUNDATION_SEMANTIC_CRITERIA.get(stage, ())
            ]
            criteria_line = (
                "criteria_results_json: " + json.dumps(criteria_results, ensure_ascii=False) + "\n"
                if criteria_results
                else ""
            )
            path.write_text(
                f"status: passed\nreviewed_entries: [{', '.join(entry_ids)}]\nblocked_entries: []\n"
                f"failed_selectors: []\n{criteria_line}findings: []\nnotes: []\n",
                encoding="utf-8",
            )
        elif key == "prompt":
            path.write_text(f"# Semantic Review Prompt\n\nstage: {stage}\n", encoding="utf-8")
        else:
            path.write_text(f"# Semantic Review Collection\n\nstage: {stage}\n", encoding="utf-8")
    image_gen_app._refresh_semantic_review_input_digest(
        run_dir=run_dir,
        scope_path=run_dir / relpaths["scope"],
        collection_path=run_dir / relpaths["collection"],
        prompt_path=run_dir / relpaths["prompt"],
        report_path=run_dir / relpaths["report"],
    )


def write_failed_semantic_review_artifacts(
    run_dir: Path,
    stage: str,
    *,
    reviewed_entries: list[str],
    failed_selectors: list[str],
    blocked_entries: list[str],
) -> None:
    """Write a current, fully accounted terminal failure for media routing tests."""

    write_semantic_review_artifacts(
        run_dir,
        stage,
        entry_count=len(reviewed_entries),
    )
    relpaths = image_gen_app.semantic_review_relpaths(stage)
    scope_path = run_dir / relpaths["scope"]
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    scope["entry_count"] = len(reviewed_entries)
    scope["entry_ids"] = reviewed_entries
    scope["selectors"] = reviewed_entries
    if stage == "image_prompt":
        snapshot = load_request_snapshot(
            run_dir / "image_generation_request_snapshot.json",
            run_dir=run_dir,
            verify_references=True,
        )
        scope["request_revision"] = snapshot.request_revision
    scope.pop("source_artifact_digests", None)
    scope_path.write_text(
        json.dumps(scope, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path = run_dir / relpaths["report"]
    report_path.write_text(
        "\n".join(
            [
                "status: failed",
                f"reviewed_entries: [{', '.join(reviewed_entries)}]",
                f"blocked_entries: [{', '.join(blocked_entries)}]",
                f"failed_selectors: [{', '.join(failed_selectors)}]",
                "reason_keys: [scene_detail_obligation_missing]",
                "findings: [localized semantic failure]",
                "notes: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    image_gen_app._refresh_semantic_review_input_digest(
        run_dir=run_dir,
        scope_path=scope_path,
        collection_path=run_dir / relpaths["collection"],
        prompt_path=run_dir / relpaths["prompt"],
        report_path=report_path,
    )


def activate_localized_partial_media_fixture(
    run_dir: Path,
    stage: str,
    *,
    blocked_item_ids: list[str],
    extra_state: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record the exact production state and projection for a localized failure."""

    blocked_values = ", ".join(blocked_item_ids)
    updates = {
        f"review.semantic.{stage}.status": "failed",
        f"review.semantic.{stage}.partial_media_allowed": "true",
        f"review.semantic.{stage}.blocked_image_items": blocked_values,
        f"review.semantic.{stage}.blocked_image_item_count": str(
            len(blocked_item_ids)
        ),
        f"review.semantic.{stage}.localization.status": (
            "localized_to_image_items"
        ),
        f"review.semantic.{stage}.localization.blocked_image_items": (
            blocked_values
        ),
        f"review.semantic.{stage}.localization.validation": "passed",
    }
    if stage == "image_prompt":
        snapshot = load_request_snapshot(
            run_dir / "image_generation_request_snapshot.json",
            run_dir=run_dir,
            verify_references=True,
        )
        updates.update(
            {
                "review.image_prompt.request_freeze.status": "frozen",
                "review.image_prompt.request_freeze.semantic_status": (
                    "localized_failure"
                ),
                "review.image_prompt.request_freeze.request_revision": (
                    snapshot.request_revision
                ),
                (
                    "review.image_prompt.request_freeze."
                    "reviewed_request_revision"
                ): snapshot.request_revision,
            }
        )
    updates.update(extra_state or {})
    image_gen_app.append_state_snapshot(run_dir / "state.txt", updates)
    return image_gen_app._refresh_partial_media_projection_artifact(run_dir)


def bind_semantic_review_to_sources(
    run_dir: Path,
    stage: str,
    source_artifacts: list[str],
) -> None:
    relpaths = image_gen_app.semantic_review_relpaths(stage)
    scope_path = run_dir / relpaths["scope"]
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    scope["source_artifacts"] = source_artifacts
    scope.pop("source_artifact_digests", None)
    scope_path.write_text(
        json.dumps(scope, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    image_gen_app._refresh_semantic_review_input_digest(
        run_dir=run_dir,
        scope_path=scope_path,
        collection_path=run_dir / relpaths["collection"],
        prompt_path=run_dir / relpaths["prompt"],
        report_path=run_dir / relpaths["report"],
    )


def refresh_existing_semantic_review_digest(run_dir: Path, stage: str) -> None:
    relpaths = image_gen_app.semantic_review_relpaths(stage)
    scope_path = run_dir / relpaths["scope"]
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    scope.pop("source_artifact_digests", None)
    scope_path.write_text(
        json.dumps(scope, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    image_gen_app._refresh_semantic_review_input_digest(
        run_dir=run_dir,
        scope_path=scope_path,
        collection_path=run_dir / relpaths["collection"],
        prompt_path=run_dir / relpaths["prompt"],
        report_path=run_dir / relpaths["report"],
    )


def semantic_agent_report_transcript(
    text: str,
    *,
    status: str,
    entry_id: str,
    finding: str = "",
    reason_key: str = "",
) -> list[dict[str, object]]:
    marker = "The pending report path is `"
    report_path = Path(text.split(marker, 1)[1].split("`", 1)[0])
    scope_path = report_path.with_name(
        report_path.name.removesuffix(".report.md") + ".scope.json"
    )
    digest = json.loads(scope_path.read_text(encoding="utf-8"))[
        "semantic_review_input_digest"
    ]
    failed = status == "failed"
    report_text = "\n".join(
        [
            f"status: {status}",
            f"semantic_review_input_digest: {digest}",
            f"reviewed_entries: [{entry_id}]",
            f"blocked_entries: [{entry_id}]" if failed else "blocked_entries: []",
            f"findings: [{finding}]" if finding else "findings: []",
            f"failed_selectors: [{entry_id}]" if failed else "failed_selectors: []",
            f"reason_keys: [{reason_key}]" if reason_key else "reason_keys: []",
        ]
    )
    return [
        {
            "method": "item/completed",
            "params": {"item": {"type": "agentMessage", "text": report_text}},
        }
    ]


def write_valid_p650_artifacts(root: Path, run_id: str) -> Path:
    run_dir = root / "output" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "characters").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "characters" / "hero.png").write_bytes(PNG_BYTES)
    terminal_slots = {
        "p110": "done",
        "p120": "done",
        "p130": "done",
        "p210": "done",
        "p220": "done",
        "p230": "done",
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
      - cut_id: 1
        duration_seconds: 8
        image_generation:
          output: assets/scenes/scene10_cut1.png
      - cut_id: 2
        duration_seconds: 8
        image_generation:
          output: assets/scenes/scene10_cut2.png
      - cut_id: 3
        duration_seconds: 8
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
- prompt_policy_version: `asset_prompt_v1`
- execution_lane: `bootstrap_builtin`
- reference_count: `0`
- output: `assets/characters/hero.png`

```text
実写映画風の主人公参照画像。顔、衣装、体格、色彩を後続カットで固定する。
```
""",
        encoding="utf-8",
    )
    asset_prompt = "実写映画風の主人公参照画像。顔、衣装、体格、色彩を後続カットで固定する。"
    asset_source_digest = hashlib.sha256(b"hero:asset-fixture").hexdigest()
    asset_snapshot = materialize_request_snapshot(
        run_dir,
        kind="asset",
        items=[
            {
                "item_id": "hero",
                "destination": "assets/characters/hero.png",
                "prompt": asset_prompt,
                "prompt_policy_version": "asset_prompt_v1",
                "compiler_version": "test_fixture_v1",
                "source_digest": asset_source_digest,
                "references": [],
            }
        ],
        source_artifact="asset_generation_requests.md",
    )
    write_request_snapshot_atomic(
        run_dir / "asset_generation_request_snapshot.json",
        asset_snapshot,
        run_dir=run_dir,
    )
    asset_snapshot_item = asset_snapshot.item("hero")
    asset_output = run_dir / "assets" / "characters" / "hero.png"
    image_gen.write_app_server_image_debug_log(
        run_dir=run_dir,
        item_id="hero",
        index=1,
        destination=asset_output,
        references=[],
        prompt=asset_prompt,
        kind="asset",
        prompt_policy_version="asset_prompt_v1",
        request_revision=asset_snapshot.request_revision,
        request_digest=asset_snapshot_item.request_digest,
        compiler_version=asset_snapshot_item.compiler_version,
        source_digest=asset_snapshot_item.source_digest,
        result=ImageGenerationResult(
            saved_path=asset_output,
            revised_prompt=None,
            status="completed",
            transcript=[],
            source="app_server",
            generation_job_id="fixture-asset-job",
            item_id="hero",
            turn_id="fixture-asset-turn",
            prompt_sha256=asset_snapshot_item.prompt_sha256,
            reference_sha256s=[],
            image_generation_item_id="fixture-asset-image",
            image_generation_item_count=1,
            destination=str(asset_output),
            provenance_authoritative=True,
            provenance_policy="request_bound_v2",
        ),
    )
    (run_dir / "asset_generation_manifest.md").write_text(
        "- hero -> assets/characters/hero.png / bootstrap_builtin / generated reusable character reference for p560 validation and downstream scene prompts\n",
        encoding="utf-8",
    )
    (run_dir / "image_generation_requests.md").write_text(
        """# Image Generation Requests

## scene10_cut1

- tool: `codex_builtin_image`
- prompt_policy_version: `image_api_prompt_v1`
- execution_lane: `standard`
- reference_count: `1`
- output: `assets/scenes/scene10_cut1.png`
- references:
  - `主人公`: `assets/characters/hero.png`

```api_prompt
実写映画風の横長16:9カット。主人公が物語の転換点に立つ。
```

## scene10_cut2

- tool: `codex_builtin_image`
- prompt_policy_version: `image_api_prompt_v1`
- execution_lane: `standard`
- reference_count: `1`
- output: `assets/scenes/scene10_cut2.png`
- references:
  - `主人公`: `assets/characters/hero.png`

```api_prompt
実写映画風の横長16:9カット。主人公が次の行動へ踏み出す瞬間を具体的に描く。
```

## scene10_cut3

- tool: `codex_builtin_image`
- prompt_policy_version: `image_api_prompt_v1`
- execution_lane: `standard`
- reference_count: `1`
- output: `assets/scenes/scene10_cut3.png`
- references:
  - `主人公`: `assets/characters/hero.png`

```api_prompt
実写映画風の横長16:9カット。主人公が場面の出口へ向かい、次のsceneへつながる余韻を具体的に描く。
```
""",
        encoding="utf-8",
    )
    fixture_prompts = {
        "scene10_cut1": "実写映画風の横長16:9カット。主人公が物語の転換点に立つ。",
        "scene10_cut2": "実写映画風の横長16:9カット。主人公が次の行動へ踏み出す瞬間を具体的に描く。",
        "scene10_cut3": "実写映画風の横長16:9カット。主人公が場面の出口へ向かい、次のsceneへつながる余韻を具体的に描く。",
    }
    scene_snapshot = materialize_request_snapshot(
        run_dir,
        kind="scene",
        items=[
            {
                "item_id": item_id,
                "destination": f"assets/scenes/scene10_cut{index}.png",
                "prompt": prompt,
                "prompt_policy_version": "image_api_prompt_v1",
                "compiler_version": "test_fixture_v1",
                "source_digest": hashlib.sha256(f"{item_id}:fixture".encode()).hexdigest(),
                "references": ["assets/characters/hero.png"],
            }
            for index, (item_id, prompt) in enumerate(fixture_prompts.items(), start=1)
        ],
        source_artifact="image_generation_requests.md",
    )
    write_request_snapshot_atomic(
        run_dir / "image_generation_request_snapshot.json",
        scene_snapshot,
        run_dir=run_dir,
    )
    with (run_dir / "state.txt").open("a", encoding="utf-8") as state_file:
        state_file.write(
            "review.image_prompt.request_freeze.status=frozen\n"
            f"review.image_prompt.request_freeze.request_revision={scene_snapshot.request_revision}\n"
            f"review.image_prompt.request_freeze.reviewed_request_revision={scene_snapshot.request_revision}\n"
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
    for stage in ("research", "story", "scene_set", "scene_detail", "cut_blueprint", "asset_plan", "image_prompt"):
        write_semantic_review_artifacts(run_dir, stage, entry_count=3 if stage == "image_prompt" else 1)
    return run_dir


def refresh_scene_request_snapshot_fixture(run_dir: Path) -> None:
    """Re-freeze a deliberately edited request fixture before reading it."""

    request_path = run_dir / "image_generation_requests.md"
    items = image_gen.parse_request_markdown(
        request_path.read_text(encoding="utf-8"),
        kind="scene",
        run_dir=run_dir,
    )
    snapshot = materialize_request_snapshot(
        run_dir,
        kind="scene",
        items=[
            {
                "item_id": item.id,
                "destination": item.output,
                "prompt": item.prompt,
                "prompt_policy_version": item.prompt_policy_version,
                "compiler_version": "test_fixture_refresh_v1",
                "source_digest": hashlib.sha256(
                    f"{item.id}:{item.prompt}".encode()
                ).hexdigest(),
                "references": list(item.references),
            }
            for item in items
        ],
        source_artifact="image_generation_requests.md",
    )
    write_request_snapshot_atomic(
        run_dir / "image_generation_request_snapshot.json",
        snapshot,
        run_dir=run_dir,
    )
    image_gen_app.append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.image_prompt.request_freeze.status": "frozen",
            "review.image_prompt.request_freeze.request_revision": (
                snapshot.request_revision
            ),
            "review.image_prompt.request_freeze.reviewed_request_revision": (
                snapshot.request_revision
            ),
        },
    )


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
    return run_dir


def mark_manifest_narration_ready(run_dir: Path, *, silent: set[str] | None = None) -> None:
    silent_items = set(silent or set())
    manifest_path = run_dir / "video_manifest.md"
    original_text = manifest_path.read_text(encoding="utf-8")
    data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(original_text)) or {}
    for target in image_gen_app._manifest_scene_targets(data):
        selector = str(target["selector"])
        node = target["cut"]
        audio = node.get("audio") if isinstance(node.get("audio"), dict) else {}
        narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
        if selector in silent_items:
            narration.update(
                {
                    "tool": "silent",
                    "status": "audio_ready",
                    "text": "",
                    "tts_text": "",
                    "output": "",
                    "silence_contract": {
                        "intentional": True,
                        "confirmed_by_human": True,
                        "kind": "intentional_silence",
                        "reason": "test confirmed silence",
                    },
                    "review": {
                        "status": "approved",
                        "human_review_ok": True,
                        "approved_at": "test",
                    },
                }
            )
        else:
            output = str(narration.get("output") or f"assets/audio/{selector}/{selector}_narration.mp3")
            audio_path = image_gen_app.resolve_run_relative(run_dir, output)
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(b"fake-audio-" + selector.encode("utf-8"))
            narration.update(
                {
                    "tool": "elevenlabs",
                    "status": "audio_ready",
                    "text": f"{selector} narration",
                    "tts_text": f"{selector} narration.",
                    "output": output,
                    "review": {
                        "status": "approved",
                        "human_review_ok": True,
                        "approved_at": "test",
                    },
                }
            )
        audio["narration"] = narration
        node["audio"] = audio
    image_gen_app._write_manifest_data(manifest_path, original_text, data)


class ImageGenParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.video_semantic_review_patcher = patch(
            "server.image_gen_app._run_video_prompt_semantic_review_before_approval",
            new_callable=AsyncMock,
        )
        self.video_semantic_review_mock = self.video_semantic_review_patcher.start()
        self.video_semantic_recheck_patcher = patch(
            "server.image_gen_app._assert_video_prompt_semantic_review_is_current",
        )
        self.video_semantic_recheck_mock = (
            self.video_semantic_recheck_patcher.start()
        )

    def tearDown(self) -> None:
        self.video_semantic_recheck_patcher.stop()
        self.video_semantic_review_patcher.stop()

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

    def test_video_grounding_always_includes_the_kling_provider_playbook(self) -> None:
        contract = yaml.safe_load(
            (
                Path(__file__).resolve().parents[1]
                / "workflow"
                / "stage-grounding.yaml"
            ).read_text(encoding="utf-8")
        )
        video_generation = contract["stages"]["video_generation"]
        kling_playbook = "workflow/playbooks/video-generation/kling.md"

        self.assertIn(kling_playbook, video_generation["required_docs"])
        self.assertNotIn(
            kling_playbook,
            video_generation["optional_playbooks"],
        )

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "video_manifest.md").write_text(
                "```yaml\nmanifest_phase: production\n```\n",
                encoding="utf-8",
            )
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "review.policy.image=optional",
                        "review.policy.narration=optional",
                        "eval.p400_readiness.status=approved",
                        "review.duration_fit.status=passed",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            report = resolve_stage_grounding(
                stage="video_generation",
                run_dir=run_dir,
            )
            readset = build_stage_grounding_readset(
                report,
                stage="video_generation",
            )

        self.assertEqual(report["status"], "ready")
        self.assertIn(
            kling_playbook,
            [entry["path"] for entry in readset["stage_docs"]],
        )

    def test_video_prompt_state_schema_documents_revocation_metadata(self) -> None:
        schema = (
            Path(__file__).resolve().parents[1] / "workflow" / "state-schema.txt"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "review.video_prompt.item.<item_id>.revoked_at=<ISO8601-or-empty>",
            schema,
        )
        self.assertIn(
            "review.video_prompt.item.<item_id>.revocation_reason=<reason-or-empty>",
            schema,
        )

    def test_single_cut_video_compile_keeps_scene_visualizable_action_review_only(
        self,
    ) -> None:
        marker = "REVIEW-ONLY-SCENE-OVERVIEW-TOP-LEVEL"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            _path, _text, manifest = image_gen_app._read_manifest_data(run_dir)
            manifest["scenes"][0]["visualizable_action"] = marker
            item = image_gen_app.FrontendReviewItem(
                item_id="scene10_cut1",
                kind="scene",
                video_prompt=REVIEWABLE_VIDEO_PROMPT,
                video_first_reference="assets/characters/hero.png",
            )

            _target, payload = image_gen_app._compile_frontend_video_prompt_payload(
                data=manifest,
                item=item,
                run_dir=run_dir,
            )
            manifest["scenes"][0]["visualizable_action"] = f"{marker}-CHANGED"
            _target, changed_payload = (
                image_gen_app._compile_frontend_video_prompt_payload(
                    data=manifest,
                    item=item,
                    run_dir=run_dir,
                )
            )

        review_sources = payload["projection_review_contract"][
            "review_only_sources"
        ]
        self.assertTrue(
            any(source.get("value") == marker for source in review_sources),
            review_sources,
        )
        self.assertNotIn(marker, payload["prompt"])
        self.assertNotIn(marker, payload["negative_prompt"])
        self.assertNotIn(
            marker,
            json.dumps(payload["video_prompt_ir"], ensure_ascii=False),
        )
        self.assertEqual(changed_payload["prompt"], payload["prompt"])
        self.assertEqual(
            changed_payload["negative_prompt"],
            payload["negative_prompt"],
        )
        self.assertEqual(
            changed_payload["video_prompt_ir"],
            payload["video_prompt_ir"],
        )
        self.assertNotEqual(
            changed_payload["source_digest"],
            payload["source_digest"],
        )

    def test_render_unit_video_compile_keeps_scene_intent_visualizable_action_review_only(
        self,
    ) -> None:
        marker = "REVIEW-ONLY-SCENE-OVERVIEW-NESTED"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            _path, _text, manifest = image_gen_app._read_manifest_data(run_dir)
            scene = manifest["scenes"][0]
            scene["scene_intent"] = {
                "review_only_visualizable_action": marker,
            }
            scene["cuts"] = scene["cuts"][:1]
            scene["cuts"][0]["duration_seconds"] = 8
            scene["render_units"] = [
                {
                    "unit_id": "1",
                    "source_cut_ids": ["1"],
                    "video_generation": {"duration_seconds": 8},
                }
            ]

            _target, payload = image_gen_app._compile_frontend_video_prompt_payload(
                data=manifest,
                item=image_gen_app.FrontendReviewItem(
                    item_id="scene10_unit1",
                    kind="scene",
                    video_prompt=REVIEWABLE_VIDEO_PROMPT,
                    video_first_reference="assets/characters/hero.png",
                ),
                run_dir=run_dir,
            )

        review_sources = payload["projection_review_contract"][
            "review_only_sources"
        ]
        self.assertTrue(
            any(source.get("value") == marker for source in review_sources),
            review_sources,
        )
        self.assertNotIn(marker, payload["prompt"])
        self.assertNotIn(marker, payload["negative_prompt"])
        self.assertNotIn(
            marker,
            json.dumps(payload["video_prompt_ir"], ensure_ascii=False),
        )

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

    def test_toc_world_walk_command_includes_source_run_payload(self) -> None:
        command = _toc_world_walk_command(
            topic="桃太郎の世界観を散歩してみた",
            run_id="桃太郎の世界観を散歩してみた_20260509_1200",
            source_run_id="桃太郎_20260509_1100",
            target_duration_seconds=600,
        )

        payload = json.loads(command.split("Request JSON:\n", 1)[1])
        self.assertEqual(payload["experience"], "world_walk")
        self.assertEqual(payload["source_run"], "output/桃太郎_20260509_1100")
        self.assertEqual(payload["target_duration_seconds"], 600)
        self.assertEqual(payload["run_dir"], "output/桃太郎の世界観を散歩してみた_20260509_1200")
        self.assertEqual(payload["stop_target"], "p680")

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

    def test_validate_p650_run_requires_frozen_scene_request_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            (run_dir / "image_generation_request_snapshot.json").unlink()

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "image_generation_request_snapshot.json"):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_requires_asset_request_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            (run_dir / "asset_generation_request_snapshot.json").unlink()

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "asset_generation_request_snapshot.json",
                ):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_rejects_asset_without_snapshot_bound_provenance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            shutil.rmtree(run_dir / "logs" / "app_server" / "image_gen")

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "strict request-bound provenance",
                ):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_generated_asset_outputs_requires_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_valid_p650_artifacts(Path(tmp), "sample_run")
            (run_dir / "asset_generation_request_snapshot.json").unlink()

            with self.assertRaisesRegex(
                RuntimeError,
                "asset_generation_request_snapshot.json",
            ):
                image_gen_app._validate_generated_outputs(run_dir, "asset")

    def test_validate_p650_run_rejects_draft_freeze_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            with (run_dir / "state.txt").open("a", encoding="utf-8") as state_file:
                state_file.write("review.image_prompt.request_freeze.status=draft\n")

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "request freeze is not frozen"):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_materialized_p650_run_allows_no_assets_after_all_semantic_reviews_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            frozen_scene_snapshot = load_request_snapshot(
                run_dir / "image_generation_request_snapshot.json",
                run_dir=run_dir,
            )
            shutil.rmtree(run_dir / "assets")
            deferred_scene_snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    {
                        "item_id": item.item_id,
                        "destination": item.destination,
                        "prompt": item.prompt,
                        "prompt_policy_version": item.prompt_policy_version,
                        "compiler_version": item.compiler_version,
                        "source_digest": item.source_digest,
                        "references": [reference.path for reference in item.references],
                    }
                    for item in frozen_scene_snapshot.items
                ],
                source_artifact="image_generation_requests.md",
                defer_missing_references=True,
            )
            write_request_snapshot_atomic(
                run_dir / "image_generation_request_snapshot.json",
                deferred_scene_snapshot,
                run_dir=run_dir,
            )
            with (run_dir / "state.txt").open("a", encoding="utf-8") as state_file:
                state_file.write(
                    "slot.p650.status=pending\n"
                    "review.image_prompt.request_freeze.status=reviewed_draft\n"
                    f"review.image_prompt.request_freeze.reviewed_request_revision={deferred_scene_snapshot.request_revision}\n"
                )

            with patch("server.image_gen_app.ROOT", root):
                _validate_materialized_p650_run("桃太郎_20260509_1200")

    def test_validate_materialized_p650_run_rejects_stale_reviewed_draft_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            current_snapshot = load_request_snapshot(
                run_dir / "image_generation_request_snapshot.json",
                run_dir=run_dir,
            )
            with (run_dir / "state.txt").open("a", encoding="utf-8") as state_file:
                state_file.write(
                    "slot.p650.status=pending\n"
                    "review.image_prompt.request_freeze.status=reviewed_draft\n"
                    "review.image_prompt.request_freeze.reviewed_request_revision="
                    + ("0" * len(current_snapshot.request_revision))
                    + "\n"
                )

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "reviewed image prompt request revision is stale",
                ):
                    _validate_materialized_p650_run(run_id)

    def test_validate_materialized_p650_run_rejects_pending_downstream_semantic_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            report_path = run_dir / image_gen_app.semantic_review_relpaths("image_prompt")["report"]
            report_path.write_text(
                "status: pending\nreviewed_entries: []\nblocked_entries: []\nfailed_selectors: []\n",
                encoding="utf-8",
            )
            with (run_dir / "state.txt").open("a", encoding="utf-8") as state_file:
                state_file.write(
                    "slot.p650.status=pending\n"
                    "review.image_prompt.request_freeze.status=reviewed_draft\n"
                )

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, r"semantic review incomplete:.*image_prompt"):
                    _validate_materialized_p650_run("桃太郎_20260509_1200")

    def test_validate_materialized_p650_run_requires_research_and_story_semantic_reviews(self) -> None:
        for stage in ("research", "story"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
                (run_dir / image_gen_app.semantic_review_relpaths(stage)["report"]).unlink()

                with patch("server.image_gen_app.ROOT", root):
                    with self.assertRaisesRegex(RuntimeError, rf"semantic review incomplete:.*{stage}"):
                        _validate_materialized_p650_run("桃太郎_20260509_1200")

    def test_validate_materialized_p650_run_rejects_failed_foundation_semantic_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            report_path = run_dir / image_gen_app.semantic_review_relpaths("story")["report"]
            report_path.write_text(
                "status: failed\nreviewed_entries: [story_entry_1]\nblocked_entries: [story_entry_1]\n"
                "failed_selectors: [story_entry_1]\nfindings: [story foundation is inconsistent]\nnotes: []\n",
                encoding="utf-8",
            )

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, r"semantic review incomplete:.*story"):
                    _validate_materialized_p650_run("桃太郎_20260509_1200")

    def test_manifest_cut_contract_allows_one_semantically_sufficient_cut(self) -> None:
        issues, outputs = image_gen_app._manifest_cut_contract(
            {
                "scenes": [
                    {
                        "scene_id": 10,
                        "scene_cut_coverage_plan": {
                            "min_cut_count": {
                                "by_distinct_semantic_obligations": 1,
                                "by_event_beats": 1,
                                "by_importance": 0,
                                "by_duration": 0,
                                "selected": 1,
                            },
                            "selected_cut_count": 1,
                        },
                        "cuts": [
                            {
                                "cut_id": "10-1",
                                "image_generation": {
                                    "output": "assets/scenes/scene10_cut1.png"
                                },
                            }
                        ],
                    }
                ]
            }
        )

        self.assertEqual(issues, [])
        self.assertEqual(outputs, {"assets/scenes/scene10_cut1.png"})

    def test_manifest_cut_contract_rejects_cut_count_below_semantic_minimum(self) -> None:
        issues, _outputs = image_gen_app._manifest_cut_contract(
            {
                "scenes": [
                    {
                        "scene_id": 10,
                        "scene_cut_coverage_plan": {
                            "min_cut_count": {
                                "by_distinct_semantic_obligations": 2,
                                "by_event_beats": 1,
                                "by_importance": 0,
                                "by_duration": 0,
                                "selected": 2,
                            },
                            "selected_cut_count": 1,
                        },
                        "cuts": [
                            {
                                "cut_id": "10-1",
                                "image_generation": {
                                    "output": "assets/scenes/scene10_cut1.png"
                                },
                            }
                        ],
                    }
                ]
            }
        )

        self.assertTrue(
            any("do not cover semantic minimum 2" in issue for issue in issues),
            issues,
        )

    def test_validate_p650_run_requires_request_for_each_cut(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            text = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")
            (run_dir / "image_generation_requests.md").write_text(text.split("## scene10_cut2", 1)[0], encoding="utf-8")

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(ImageRequestSnapshotError, "source_artifact_sha256 mismatch"):
                    _validate_p650_run("桃太郎_20260509_1200")

    def test_validate_p650_run_rejects_placeholder_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
            with (run_dir / "state.txt").open("a", encoding="utf-8") as state_file:
                state_file.write(
                    "runtime.scaffold.content_status=placeholder\nslot.p120.status=pending\n"
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

    def test_validate_frontend_create_run_uses_terminal_p680_verifier_mode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_p680_artifacts(root, "桃太郎_20260509_1200")
            modes: list[str] = []

            def validate_p680(_run_dir: Path, *, mode: str) -> None:
                modes.append(mode)

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._validate_p680_visual_quality",
                    side_effect=validate_p680,
                ),
            ):
                _validate_frontend_create_run("桃太郎_20260509_1200")

        self.assertEqual(modes, ["terminal"])

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

    def test_validate_p650_run_requires_research_and_story_semantic_reviews(self) -> None:
        for stage in ("research", "story"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                run_dir = write_valid_p650_artifacts(root, "桃太郎_20260509_1200")
                (run_dir / image_gen_app.semantic_review_relpaths(stage)["report"]).unlink()

                with patch("server.image_gen_app.ROOT", root):
                    with self.assertRaisesRegex(RuntimeError, rf"semantic review incomplete:.*{stage}"):
                        _validate_p650_run("桃太郎_20260509_1200")

    def test_semantic_report_can_be_materialized_from_complete_agent_verdict(self) -> None:
        criteria_results = [
            {
                "criterion_id": criterion_id,
                "status": "passed",
                "evidence": f"research.md:{criterion_id}",
            }
            for criterion_id in FOUNDATION_SEMANTIC_CRITERIA["research"]
        ]
        verdict = "\n".join(
            [
                "status: passed",
                "semantic_review_input_digest: sha256:" + ("a" * 64),
                "reviewed_entries: [research_entry_1]",
                "blocked_entries: []",
                "failed_selectors: []",
                "criteria_results_json: " + json.dumps(criteria_results, ensure_ascii=False),
                "findings: []",
                "reason_keys: []",
                "notes: []",
            ]
        )
        transcript = [
            {
                "method": "item/completed",
                "params": {"item": {"type": "agentMessage", "text": verdict}},
            }
        ]

        report = image_gen_app._semantic_report_text_from_transcript(transcript, "research")

        self.assertIsNotNone(report)
        self.assertTrue(report.startswith("status: passed\n"))
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_semantic_review_artifacts(run_dir, "research")
            scope = json.loads(
                (
                    run_dir
                    / image_gen_app.semantic_review_relpaths("research")["scope"]
                ).read_text(encoding="utf-8")
            )
            report = report.replace(
                "sha256:" + ("a" * 64),
                scope["semantic_review_input_digest"],
            )
            (run_dir / image_gen_app.semantic_review_relpaths("research")["report"]).write_text(
                report,
                encoding="utf-8",
            )
            result = image_gen_app.check_semantic_review(run_dir, "research")
        self.assertTrue(result.passed, result.errors)

    def test_semantic_report_can_be_materialized_from_complete_json_agent_verdict(self) -> None:
        verdict = {
            "status": "failed",
            "semantic_review_input_digest": "sha256:" + ("a" * 64),
            "reviewed_entries": ["scene:10", "scene:20"],
            "blocked_entries": ["scene:20"],
            "findings": [
                {
                    "selectors": ["scene20"],
                    "reason_keys": ["semantic_reveal_order_mismatch"],
                    "detail": "scene20 reveals the next scene too early",
                }
            ],
            "failed_selectors": ["scene20"],
            "reason_keys": ["semantic_reveal_order_mismatch"],
            "notes": ["scene10 is usable"],
        }
        transcript = [
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "agentMessage",
                        "phase": "final_answer",
                        "text": json.dumps(verdict, ensure_ascii=False),
                    }
                },
            }
        ]

        report = image_gen_app._semantic_report_text_from_transcript(
            transcript,
            "scene_set",
        )

        self.assertIsNotNone(report)
        self.assertIn("status: failed\n", report)
        self.assertIn(
            "semantic_review_input_digest: sha256:" + ("a" * 64),
            report,
        )
        self.assertIn('reviewed_entries: ["scene:10", "scene:20"]', report)
        self.assertIn('blocked_entries: ["scene:20"]', report)
        self.assertIn('failed_selectors: ["scene20"]', report)
        self.assertIn(
            'reason_keys: ["semantic_reveal_order_mismatch"]',
            report,
        )
        self.assertIn(
            'findings:\n  - {"selectors": ["scene20"], '
            '"reason_keys": ["semantic_reveal_order_mismatch"], '
            '"detail": "scene20 reveals the next scene too early"}',
            report,
        )

    def test_semantic_report_never_uses_commentary_when_explicit_final_is_missing_or_malformed(
        self,
    ) -> None:
        verdict = {
            "status": "passed",
            "semantic_review_input_digest": "sha256:" + ("a" * 64),
            "reviewed_entries": ["scene:10"],
            "blocked_entries": [],
            "findings": [],
            "failed_selectors": [],
            "reason_keys": [],
            "notes": [],
        }
        valid_text = json.dumps(verdict, ensure_ascii=False)
        cases = {
            "explicit_commentary_without_final": [
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "type": "agentMessage",
                            "phase": "commentary",
                            "text": valid_text,
                        }
                    },
                }
            ],
            "explicit_commentary_then_malformed_final": [
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "type": "agentMessage",
                            "phase": "commentary",
                            "text": valid_text,
                        }
                    },
                },
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "type": "agentMessage",
                            "phase": "final_answer",
                            "text": '{"status": "passed"',
                        }
                    },
                },
            ],
            "legacy_message_then_malformed_explicit_final": [
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "type": "agentMessage",
                            "text": valid_text,
                        }
                    },
                },
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "type": "agentMessage",
                            "phase": "final_answer",
                            "text": "not a complete verdict",
                        }
                    },
                },
            ],
        }

        for label, transcript in cases.items():
            with self.subTest(label=label):
                self.assertIsNone(
                    image_gen_app._semantic_report_text_from_transcript(
                        transcript,
                        "scene_set",
                    )
                )

    def test_semantic_report_agent_fallback_rejects_incomplete_chat_message(self) -> None:
        transcript = [
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "agentMessage",
                        "text": "I could not read the artifacts, so no verdict was produced.",
                    }
                },
            }
        ]

        self.assertIsNone(image_gen_app._semantic_report_text_from_transcript(transcript, "research"))

    def test_validate_frontend_create_run_rejects_post_freeze_request_markdown_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p680_artifacts(root, "桃太郎_20260509_1200")
            text = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")
            (run_dir / "image_generation_requests.md").write_text(text.replace("- output: `assets/scenes/scene10_cut1.png`\n", ""), encoding="utf-8")

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(ImageRequestSnapshotError, "source_artifact_sha256 mismatch"):
                    _validate_frontend_create_run("桃太郎_20260509_1200")

    def test_validate_frontend_create_run_rejects_invalid_scene_image_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p680_artifacts(root, "桃太郎_20260509_1200")
            (run_dir / "assets" / "scenes" / "scene10_cut1.png").write_bytes(b"not-png")

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "invalid magic bytes"):
                    _validate_frontend_create_run("桃太郎_20260509_1200")

    def test_materialize_scene_storyboard_video_requests_creates_render_unit_and_request_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            manifest_path = run_dir / "video_manifest.md"
            manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest_data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(manifest_text)) or {}
            review_only_scene_action = "REVIEW-ONLY-STORYBOARD-SCENE-OVERVIEW"
            manifest_data["scenes"][0]["scene_intent"] = {
                "review_only_visualizable_action": review_only_scene_action,
            }
            for cut_index, cut in enumerate(
                manifest_data["scenes"][0]["cuts"],
                start=1,
            ):
                cut["cut_id"] = f"{cut_index:02d}"
                cut["duration_seconds"] = 6
            image_gen_app._write_manifest_data(manifest_path, manifest_text, manifest_data)
            write_test_png(run_dir / "assets" / "scenes" / "scene10_cut1.png", (220, 40, 40))
            write_test_png(run_dir / "assets" / "scenes" / "scene10_cut2.png", (40, 220, 40))
            write_test_png(run_dir / "assets" / "scenes" / "scene10_cut3.png", (40, 40, 220))

            with patch("server.image_gen_app.ROOT", root):
                result = image_gen_app._materialize_scene_storyboard_video_requests(run_id)
                image_gen_app._validate_scene_storyboard_create_run(run_id, strict_visual_quality=False)
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "scripts" / "build-clip-lists.py"),
                    "--manifest",
                    str(run_dir / "video_manifest.md"),
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=Path(__file__).resolve().parents[1],
            )

            data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text((run_dir / "video_manifest.md").read_text(encoding="utf-8")))
            render_units = data["scenes"][0]["render_units"]
            storyboard_paths = [
                run_dir / "assets" / "storyboards" / "scene10_unit1_storyboard.png",
                run_dir / "assets" / "storyboards" / "scene10_unit2_storyboard.png",
            ]
            storyboard_exists = all(path.is_file() for path in storyboard_paths)
            request_text = (run_dir / "video_generation_requests.md").read_text(encoding="utf-8")
            clips_text = (run_dir / "video_clips.txt").read_text(encoding="utf-8")
            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            timeline_issues = image_gen_app._render_unit_timeline_issues(data)

        self.assertEqual(result["unitCount"], 2)
        self.assertTrue(storyboard_exists)
        self.assertEqual(timeline_issues, [])
        self.assertEqual(
            [cut["cut_id"] for cut in data["scenes"][0]["cuts"]],
            ["01", "02", "03"],
        )
        self.assertEqual([unit["unit_id"] for unit in render_units], ["1", "2"])
        self.assertEqual(render_units[0]["source_cut_ids"], ["1", "2"])
        self.assertEqual(render_units[1]["source_cut_ids"], ["3"])
        self.assertEqual(render_units[0]["video_generation"]["duration_seconds"], 12)
        self.assertEqual(render_units[1]["video_generation"]["duration_seconds"], 6)
        self.assertEqual(render_units[0]["storyboard_image"], "assets/storyboards/scene10_unit1_storyboard.png")
        self.assertNotIn("first_frame", render_units[0]["video_generation"])
        self.assertNotIn("input_image", render_units[0]["video_generation"])
        self.assertEqual(
            render_units[0]["video_generation"]["references"],
            [
                "assets/scenes/scene10_cut1.png",
                "assets/storyboards/scene10_unit1_storyboard.png",
            ],
        )
        self.assertEqual(
            render_units[0]["video_input_contract"]["input_mode"],
            "reference_images",
        )
        self.assertEqual(
            render_units[0]["video_generation"]["api_prompt_payload"]["policy_version"],
            "video_api_prompt_v1",
        )
        self.assertEqual(
            render_units[0]["video_generation"]["api_prompt_payload"]["mode"],
            "reference_to_video",
        )
        self.assertEqual(
            render_units[0]["video_generation"]["motion_prompt"],
            render_units[0]["video_generation"]["api_prompt_payload"]["prompt"],
        )
        for unit in render_units:
            payload = unit["video_generation"]["api_prompt_payload"]
            self.assertTrue(
                any(
                    source.get("value") == review_only_scene_action
                    for source in payload["projection_review_contract"][
                        "review_only_sources"
                    ]
                ),
                payload["projection_review_contract"]["review_only_sources"],
            )
            self.assertNotIn(review_only_scene_action, payload["prompt"])
            self.assertNotIn(review_only_scene_action, payload["negative_prompt"])
            self.assertNotIn(
                review_only_scene_action,
                json.dumps(
                    payload["video_prompt_ir"],
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        self.assertIn("## scene10_unit1", request_text)
        self.assertIn("## scene10_unit2", request_text)
        self.assertIn("- duration_seconds: `12`", request_text)
        self.assertIn("- duration_seconds: `6`", request_text)
        self.assertIn("- prompt_policy_version: `video_api_prompt_v1`", request_text)
        self.assertIn("- negative_prompt_sha256: `", request_text)
        self.assertIn("- references_digest: `", request_text)
        self.assertIn("```video_prompt", request_text)
        self.assertIn("```negative_prompt", request_text)
        self.assertIn("一つの連続した映画的な動き", request_text)
        self.assertNotIn("render_unit:", request_text)
        self.assertNotIn("cut_motion_order:", request_text)
        self.assertIn("- storyboard_image: `assets/storyboards/scene10_unit1_storyboard.png`", request_text)
        self.assertIn("- first_frame: ``", request_text)
        self.assertIn("Image 1", request_text)
        self.assertIn("- source_cuts:\n  - `1`\n  - `2`", request_text)
        self.assertIn("- source_cuts:\n  - `3`", request_text)
        self.assertIn("assets/scenes/scene10/scene10_unit1.mp4", clips_text)
        self.assertIn("assets/scenes/scene10/scene10_unit2.mp4", clips_text)
        self.assertEqual(state["runtime.create_mode"], "scene_storyboard")
        self.assertEqual(state["review.frontend.storyboard.status"], "ready")
        self.assertEqual(state["stage.video_generation.status"], "in_progress")
        self.assertEqual(state["slot.p830.status"], "in_progress")
        self.assertEqual(state["review.video_prompt.status"], "pending")
        self.assertEqual(state["gate.video_prompt_review"], "required")
        self.assertEqual(
            state["review.video_prompt.item.scene10_unit1.status"],
            "pending",
        )
        self.assertEqual(
            state["review.video_prompt.item.scene10_unit2.status"],
            "pending",
        )

    def test_storyboard_materializer_rejects_missing_or_invalid_canonical_cut_fields(
        self,
    ) -> None:
        cases = {
            "missing_cut_id": lambda cut: cut.pop("cut_id"),
            "invalid_cut_id": lambda cut: cut.__setitem__("cut_id", "cut-01"),
            "missing_duration": lambda cut: cut.pop("duration_seconds"),
            "invalid_duration": lambda cut: cut.__setitem__(
                "duration_seconds",
                0,
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    run_id = f"storyboard_{label}"
                    run_dir = write_valid_p680_artifacts(root, run_id)
                    for cut_index in range(1, 4):
                        write_test_png(
                            run_dir
                            / "assets"
                            / "scenes"
                            / f"scene10_cut{cut_index}.png"
                        )
                    manifest_path = run_dir / "video_manifest.md"
                    original_text = manifest_path.read_text(encoding="utf-8")
                    manifest = yaml.safe_load(
                        image_gen_app._extract_manifest_yaml_text(original_text)
                    )
                    mutate(manifest["scenes"][0]["cuts"][0])
                    image_gen_app._write_manifest_data(
                        manifest_path,
                        original_text,
                        manifest,
                    )
                    manifest_before = manifest_path.read_bytes()

                    with (
                        patch("server.image_gen_app.ROOT", root),
                        self.assertRaisesRegex(
                            RuntimeError,
                            "cut_id|duration",
                        ),
                    ):
                        image_gen_app._materialize_scene_storyboard_video_requests(
                            run_id
                        )

                    self.assertEqual(
                        manifest_path.read_bytes(),
                        manifest_before,
                    )
                    self.assertFalse(
                        (run_dir / "video_generation_requests.md").is_file()
                    )

    def test_storyboard_transaction_rolls_back_when_review_projection_drifts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "storyboard_projection_drift"
            run_dir = write_valid_p680_artifacts(root, run_id)
            for cut_index in range(1, 4):
                write_test_png(
                    run_dir
                    / "assets"
                    / "scenes"
                    / f"scene10_cut{cut_index}.png"
                )
            manifest_path = run_dir / "video_manifest.md"
            tracked = {
                path: path.read_bytes() if path.is_file() else None
                for path in (
                    manifest_path,
                    run_dir / "video_generation_requests.md",
                    run_dir / "state.txt",
                    run_dir / "run_status.json",
                    run_dir / "p000_index.md",
                )
            }

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.video_manifest_review_projection_sha256",
                    side_effect=("stable", "stable", "drift"),
                ),
                self.assertRaisesRegex(
                    RuntimeError,
                    "review projection changed",
                ),
            ):
                image_gen_app._materialize_scene_storyboard_video_requests(
                    run_id
                )

            for path, before in tracked.items():
                if before is None:
                    self.assertFalse(path.exists(), path)
                else:
                    self.assertEqual(path.read_bytes(), before, path)
            self.assertEqual(
                list(
                    (run_dir / "assets" / "storyboards").glob("*.png")
                ),
                [],
            )

    def test_storyboard_materializer_detaches_aliased_scene_mapping(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "storyboard_scene_alias"
            run_dir = write_valid_p680_artifacts(root, run_id)
            for cut_index in range(1, 4):
                write_test_png(
                    run_dir
                    / "assets"
                    / "scenes"
                    / f"scene10_cut{cut_index}.png"
                )
            manifest_path, original_text, manifest = (
                image_gen_app._read_manifest_data(run_dir)
            )
            manifest["shared_scene"] = manifest["scenes"][0]
            image_gen_app._write_manifest_data(
                manifest_path,
                original_text,
                manifest,
            )
            projection_before = (
                image_gen_app.video_manifest_review_projection_sha256(
                    manifest_path
                )
            )

            with patch("server.image_gen_app.ROOT", root):
                image_gen_app._materialize_scene_storyboard_video_requests(
                    run_id
                )

            _path, _text, materialized = (
                image_gen_app._read_manifest_data(run_dir)
            )
            self.assertNotIn(
                "render_units",
                materialized["shared_scene"],
            )
            self.assertTrue(
                materialized["scenes"][0]["render_units"]
            )
            self.assertEqual(
                image_gen_app.video_manifest_review_projection_sha256(
                    manifest_path
                ),
                projection_before,
            )

    def test_scene_storyboard_p680_finalizer_uses_strict_transaction_order(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "storyboard_finalizer"
            (root / "output" / run_id).mkdir(parents=True)
            events: list[str] = []

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._validate_frontend_create_run",
                    side_effect=lambda *_args, **_kwargs: events.append(
                        "generic"
                    ),
                ),
                patch(
                    "server.image_gen_app._scene_storyboard_materialization_is_current",
                    side_effect=lambda *_args, **_kwargs: (
                        events.append("currentness") or False
                    ),
                ),
                patch(
                    "server.image_gen_app.video_manifest_review_projection_sha256",
                    side_effect=lambda *_args, **_kwargs: (
                        events.append("projection") or "stable"
                    ),
                ),
                patch(
                    "server.image_gen_app._materialize_scene_storyboard_video_requests",
                    side_effect=lambda *_args, **_kwargs: (
                        events.append("materialize")
                        or {"unitCount": 2}
                    ),
                ),
                patch(
                    "server.image_gen_app._validate_scene_storyboard_create_run",
                    side_effect=lambda *_args, **_kwargs: events.append(
                        "specialized"
                    ),
                ),
            ):
                result = image_gen_app._finalize_scene_storyboard_p680(run_id)

            self.assertEqual(
                events,
                [
                    "generic",
                    "currentness",
                    "projection",
                    "materialize",
                    "projection",
                    "specialized",
                    "generic",
                ],
            )
            self.assertEqual(result["unitCount"], 2)
            self.assertFalse(result["alreadyCurrent"])

    def test_scene_storyboard_p680_finalizer_avoids_duplicate_materialization(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "storyboard_finalizer_current"
            (root / "output" / run_id).mkdir(parents=True)
            materialize = Mock()
            generic = Mock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._validate_frontend_create_run",
                    generic,
                ),
                patch(
                    "server.image_gen_app._scene_storyboard_materialization_is_current",
                    return_value=True,
                ),
                patch(
                    "server.image_gen_app._materialize_scene_storyboard_video_requests",
                    materialize,
                ),
            ):
                result = image_gen_app._finalize_scene_storyboard_p680(run_id)

            materialize.assert_not_called()
            self.assertEqual(generic.call_count, 2)
            self.assertTrue(result["alreadyCurrent"])

    def test_scene_storyboard_currentness_rejects_incomplete_or_reordered_cut_ownership(
        self,
    ) -> None:
        mutations = {
            "dropped": lambda units: units.pop(1),
            "reordered": lambda units: units[0].__setitem__(
                "source_cut_ids",
                ["2", "1"],
            ),
            "duplicate": lambda units: units[1].__setitem__(
                "source_cut_ids",
                ["2", "3"],
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    run_id = f"storyboard_currentness_{label}"
                    run_dir = write_valid_p680_artifacts(root, run_id)
                    for cut_index in range(1, 4):
                        write_test_png(
                            run_dir
                            / "assets"
                            / "scenes"
                            / f"scene10_cut{cut_index}.png"
                        )
                    with patch("server.image_gen_app.ROOT", root):
                        image_gen_app._materialize_scene_storyboard_video_requests(
                            run_id
                        )
                        manifest_path, original_text, manifest = (
                            image_gen_app._read_manifest_data(run_dir)
                        )
                        mutate(manifest["scenes"][0]["render_units"])
                        image_gen_app._write_manifest_data(
                            manifest_path,
                            original_text,
                            manifest,
                        )

                        self.assertFalse(
                            image_gen_app._scene_storyboard_materialization_is_current(
                                run_id
                            )
                        )

    def test_scene_storyboard_currentness_recompiles_source_cut_contracts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "storyboard_currentness_contract"
            run_dir = write_valid_p680_artifacts(root, run_id)
            for cut_index in range(1, 4):
                write_test_png(
                    run_dir
                    / "assets"
                    / "scenes"
                    / f"scene10_cut{cut_index}.png"
                )
            with patch("server.image_gen_app.ROOT", root):
                image_gen_app._materialize_scene_storyboard_video_requests(
                    run_id
                )
                self.assertTrue(
                    image_gen_app._scene_storyboard_materialization_is_current(
                        run_id
                    )
                )
                manifest_path, original_text, manifest = (
                    image_gen_app._read_manifest_data(run_dir)
                )
                manifest["scenes"][0]["cuts"][0].setdefault(
                    "cut_contract",
                    {},
                )["reviewed_motion_fact"] = (
                    "changed after storyboard materialization"
                )
                image_gen_app._write_manifest_data(
                    manifest_path,
                    original_text,
                    manifest,
                )

                self.assertFalse(
                    image_gen_app._scene_storyboard_materialization_is_current(
                        run_id
                    )
                )

    def test_storyboard_materialization_rejects_sanitized_scene_selector_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            manifest_path, original_text, manifest = image_gen_app._read_manifest_data(
                run_dir
            )
            first_scene = manifest["scenes"][0]
            first_scene["scene_id"] = "scene/10"
            duplicate_scene = copy.deepcopy(first_scene)
            duplicate_scene["scene_id"] = "scene 10"
            manifest["scenes"].append(duplicate_scene)
            for cut in first_scene["cuts"]:
                write_test_png(run_dir / cut["image_generation"]["output"])
            image_gen_app._write_manifest_data(
                manifest_path,
                original_text,
                manifest,
            )

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "duplicate storyboard scene selector",
                ):
                    image_gen_app._materialize_scene_storyboard_video_requests(
                        run_id
                    )

    def test_storyboard_validator_rejects_request_section_identity_and_binding_tampering(
        self,
    ) -> None:
        mutations = {
            "prefix_collision": lambda text: text.replace(
                "## scene10_unit1\n",
                "## scene10_unit10\n",
                1,
            ),
            "duplicate_section": lambda text: (
                text.rstrip()
                + "\n\n"
                + "\n".join(
                    image_gen_app._split_video_request_sections(text)[1][0][1]
                )
                + "\n"
            ),
            "prompt_body": lambda text: text.replace(
                "一つの連続した映画的な動き",
                "契約にない不正な別の動き",
                1,
            ),
            "references": lambda text: text.replace(
                "- references:\n"
                "  - `assets/scenes/scene10_cut1.png`",
                "- references:\n"
                "  - `assets/scenes/scene10_cut2.png`",
                1,
            ),
            "negative_prompt": lambda text: text.replace(
                "```negative_prompt\n",
                "```negative_prompt\n契約外の不正なnegative指定\n",
                1,
            ),
            "prompt_sha256": lambda text: re.sub(
                r"(?m)^- prompt_sha256: `[^`]+`$",
                "- prompt_sha256: `" + ("0" * 64) + "`",
                text,
                count=1,
            ),
            "references_digest": lambda text: re.sub(
                r"(?m)^- references_digest: `[^`]+`$",
                "- references_digest: `" + ("0" * 64) + "`",
                text,
                count=1,
            ),
            "output": lambda text: re.sub(
                r"(?m)^- output: `[^`]+`$",
                "- output: `assets/scenes/tampered/output.mp4`",
                text,
                count=1,
            ),
            "source_cuts": lambda text: text.replace(
                "- source_cuts:\n  - `1`",
                "- source_cuts:\n  - `999`",
                1,
            ),
            "duplicate_output": lambda text: re.sub(
                r"(?m)(^- output: `[^`]+`$)",
                r"\1\n- output: `assets/scenes/duplicate/output.mp4`",
                text,
                count=1,
            ),
            "duplicate_references": lambda text: re.sub(
                r"(?ms)(^- references:\n(?:  - `[^\n]+`\n?)+)",
                lambda match: (
                    match.group(1)
                    + "- references:\n"
                    + "  - `assets/scenes/scene10_cut1.png`\n"
                ),
                text,
                count=1,
            ),
            "duplicate_video_prompt": lambda text: re.sub(
                r"(?ms)(```video_prompt\n.*?\n```)",
                lambda match: (
                    match.group(1)
                    + "\n\n```video_prompt\n"
                    + "不正な重複prompt\n```"
                ),
                text,
                count=1,
            ),
            "mixed_prompt_types_with_empty_api_prompt": (
                lambda text: re.sub(
                    r"(?ms)(```video_prompt\n.*?\n```)",
                    lambda match: (
                        match.group(1)
                        + "\n\n```api_prompt\n\n```"
                    ),
                    text,
                    count=1,
                )
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    run_id = "桃太郎_20260509_1200"
                    run_dir = write_valid_p680_artifacts(root, run_id)
                    for cut_index in range(1, 4):
                        write_test_png(
                            run_dir
                            / "assets"
                            / "scenes"
                            / f"scene10_cut{cut_index}.png"
                        )
                    with patch("server.image_gen_app.ROOT", root):
                        image_gen_app._materialize_scene_storyboard_video_requests(
                            run_id
                        )
                        request_path = run_dir / "video_generation_requests.md"
                        request_path.write_text(
                            mutate(request_path.read_text(encoding="utf-8")),
                            encoding="utf-8",
                        )
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "storyboard create incomplete",
                        ):
                            image_gen_app._validate_scene_storyboard_create_run(
                                run_id,
                                strict_visual_quality=False,
                            )

    def test_storyboard_validator_rejects_corrupt_or_wrong_size_storyboard_png(
        self,
    ) -> None:
        mutations = {
            "corrupt": lambda path: path.write_bytes(b"not-a-png"),
            "wrong_size": lambda path: write_test_png(
                path,
                size=(320, 180),
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    run_id = "桃太郎_20260509_1200"
                    run_dir = write_valid_p680_artifacts(root, run_id)
                    for cut_index in range(1, 4):
                        write_test_png(
                            run_dir
                            / "assets"
                            / "scenes"
                            / f"scene10_cut{cut_index}.png"
                        )
                    with patch("server.image_gen_app.ROOT", root):
                        result = (
                            image_gen_app._materialize_scene_storyboard_video_requests(
                                run_id
                            )
                        )
                        storyboard = run_dir / result["storyboards"][0]
                        mutate(storyboard)
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "storyboard image",
                        ):
                            image_gen_app._validate_scene_storyboard_create_run(
                                run_id,
                                strict_visual_quality=False,
                            )

    def test_storyboard_materialization_rejects_symlinked_storyboard_root(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            tempfile.TemporaryDirectory() as external_tmp,
        ):
            root = Path(tmp)
            external = Path(external_tmp)
            sentinel = external / "sentinel.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            for cut_index in range(1, 4):
                write_test_png(
                    run_dir
                    / "assets"
                    / "scenes"
                    / f"scene10_cut{cut_index}.png"
                )
            (run_dir / "assets" / "storyboards").symlink_to(
                external,
                target_is_directory=True,
            )

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "storyboard storage path must not be a symlink",
                ):
                    image_gen_app._materialize_scene_storyboard_video_requests(
                        run_id
                    )

            self.assertEqual(
                sentinel.read_text(encoding="utf-8"),
                "preserve",
            )
            self.assertEqual(
                list(external.iterdir()),
                [sentinel],
            )

    def test_storyboard_validator_rejects_manifest_drift_after_request_materialization(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            for cut_index in range(1, 4):
                write_test_png(
                    run_dir
                    / "assets"
                    / "scenes"
                    / f"scene10_cut{cut_index}.png"
                )
            with patch("server.image_gen_app.ROOT", root):
                image_gen_app._materialize_scene_storyboard_video_requests(
                    run_id
                )
                manifest_path, original_text, manifest = (
                    image_gen_app._read_manifest_data(run_dir)
                )
                manifest["scenes"][0]["render_units"][0][
                    "video_generation"
                ]["output"] = "assets/scenes/tampered/output.mp4"
                image_gen_app._write_manifest_data(
                    manifest_path,
                    original_text,
                    manifest,
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "request binding mismatch: output",
                ):
                    image_gen_app._validate_scene_storyboard_create_run(
                        run_id,
                        strict_visual_quality=False,
                    )

    def test_storyboard_materialization_rolls_back_manifest_request_and_images_on_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            for cut_index in range(1, 4):
                write_test_png(
                    run_dir
                    / "assets"
                    / "scenes"
                    / f"scene10_cut{cut_index}.png"
                )
            manifest_path = run_dir / "video_manifest.md"
            request_path = run_dir / "video_generation_requests.md"
            manifest_before = manifest_path.read_bytes()
            request_before = (
                request_path.read_bytes()
                if request_path.is_file()
                else None
            )

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._write_scene_storyboard_video_generation_requests",
                    side_effect=RuntimeError("injected request write failure"),
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected request write failure",
                ):
                    image_gen_app._materialize_scene_storyboard_video_requests(
                        run_id
                    )

            self.assertEqual(manifest_path.read_bytes(), manifest_before)
            if request_before is None:
                self.assertFalse(request_path.exists())
            else:
                self.assertEqual(request_path.read_bytes(), request_before)
            self.assertEqual(
                list((run_dir / "assets" / "storyboards").glob("*.png")),
                [],
            )

    def test_storyboard_materialization_rolls_back_after_later_compose_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            for cut_index in range(1, 4):
                write_test_png(
                    run_dir
                    / "assets"
                    / "scenes"
                    / f"scene10_cut{cut_index}.png"
                )
            preexisting = (
                run_dir
                / "assets"
                / "storyboards"
                / "scene10_unit1_storyboard.png"
            )
            write_test_png(preexisting, (1, 2, 3))
            preexisting_bytes = preexisting.read_bytes()
            manifest_path = run_dir / "video_manifest.md"
            manifest_before = manifest_path.read_bytes()
            original_compose = (
                image_gen_app._compose_storyboard_image
            )
            compose_calls = 0

            def fail_second_compose(*args: Any, **kwargs: Any) -> None:
                nonlocal compose_calls
                compose_calls += 1
                if compose_calls == 2:
                    raise RuntimeError("injected second compose failure")
                original_compose(*args, **kwargs)

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._compose_storyboard_image",
                    side_effect=fail_second_compose,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected second compose failure",
                ):
                    image_gen_app._materialize_scene_storyboard_video_requests(
                        run_id
                    )

            self.assertEqual(manifest_path.read_bytes(), manifest_before)
            self.assertFalse(
                (run_dir / "video_generation_requests.md").exists()
            )
            self.assertEqual(preexisting.read_bytes(), preexisting_bytes)
            self.assertEqual(
                list(
                    (
                        run_dir / "assets" / "storyboards"
                    ).glob("*.png")
                ),
                [preexisting],
            )

    def test_storyboard_materialization_rolls_back_after_state_commit_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            for cut_index in range(1, 4):
                write_test_png(
                    run_dir
                    / "assets"
                    / "scenes"
                    / f"scene10_cut{cut_index}.png"
                )
            tracked = {
                path: path.read_bytes() if path.is_file() else None
                for path in (
                    run_dir / "video_manifest.md",
                    run_dir / "video_generation_requests.md",
                    run_dir / "state.txt",
                    run_dir / "run_status.json",
                    run_dir / "p000_index.md",
                )
            }

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.append_state_snapshot",
                    side_effect=RuntimeError(
                        "injected state commit failure"
                    ),
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected state commit failure",
                ):
                    image_gen_app._materialize_scene_storyboard_video_requests(
                        run_id
                    )

            for path, before in tracked.items():
                if before is None:
                    self.assertFalse(path.exists(), path)
                else:
                    self.assertEqual(path.read_bytes(), before, path)
            self.assertEqual(
                list(
                    (
                        run_dir / "assets" / "storyboards"
                    ).glob("*.png")
                ),
                [],
            )

    def test_storyboard_transaction_marker_recovers_interrupted_commit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            manifest_path = run_dir / "video_manifest.md"
            manifest_before = manifest_path.read_bytes()
            new_storyboard = (
                run_dir
                / "assets"
                / "storyboards"
                / "interrupted_storyboard.png"
            )

            with patch("server.image_gen_app.ROOT", root):
                transaction_dir = (
                    image_gen_app._prepare_storyboard_transaction(
                        run_dir,
                        [
                            "video_manifest.md",
                            "assets/storyboards/interrupted_storyboard.png",
                        ],
                    )
                )
                manifest_path.write_text(
                    "interrupted manifest",
                    encoding="utf-8",
                )
                write_test_png(new_storyboard)

                image_gen_app._recover_storyboard_transaction(run_dir)

            self.assertEqual(
                manifest_path.read_bytes(),
                manifest_before,
            )
            self.assertFalse(new_storyboard.exists())
            self.assertFalse(transaction_dir.exists())

    def test_storyboard_transaction_rejects_traversal_and_symlink_targets(
        self,
    ) -> None:
        self.assertFalse(
            image_gen_app._storyboard_transaction_target_allowed(
                "assets/storyboards/../../assets/characters/hero.png"
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            protected = run_dir / "assets" / "characters" / "hero.png"
            write_test_png(protected)
            protected_bytes = protected.read_bytes()
            storyboard_root = run_dir / "assets" / "storyboards"
            storyboard_root.mkdir(parents=True)
            linked = storyboard_root / "linked.png"
            linked.symlink_to(protected)

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "must not contain symlinks",
                ):
                    image_gen_app._prepare_storyboard_transaction(
                        run_dir,
                        ["assets/storyboards/linked.png"],
                    )

            self.assertEqual(protected.read_bytes(), protected_bytes)
            self.assertTrue(linked.is_symlink())

    def test_storyboard_transaction_recovery_rejects_symlinked_marker(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            tempfile.TemporaryDirectory() as external_tmp,
        ):
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            manifest_path = run_dir / "video_manifest.md"
            manifest_before = manifest_path.read_bytes()
            transaction_dir = (
                run_dir
                / "logs"
                / "transactions"
                / "storyboard_create_pending"
            )
            transaction_dir.mkdir(parents=True)
            external_marker = Path(external_tmp) / "marker.json"
            external_marker.write_text(
                json.dumps(
                    {
                        "schemaVersion": "storyboard_transaction_v1",
                        "targets": [
                            {
                                "path": "video_manifest.md",
                                "existed": False,
                                "backup": "",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (transaction_dir / "marker.json").symlink_to(
                external_marker
            )

            with patch("server.image_gen_app.ROOT", root):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "marker must not be a symlink",
                ):
                    image_gen_app._recover_storyboard_transaction(
                        run_dir
                    )

            self.assertEqual(
                manifest_path.read_bytes(),
                manifest_before,
            )

    def test_storyboard_materialization_preserves_explicit_unit_reveal_authorization(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            manifest_path, original_text, manifest = (
                image_gen_app._read_manifest_data(run_dir)
            )
            scene = manifest["scenes"][0]
            scene["cuts"] = scene["cuts"][:2]
            for index, cut in enumerate(scene["cuts"], start=1):
                cut["cut_id"] = str(index)
                cut["duration_seconds"] = 4
                cut["cut_contract"] = {
                    "motion_contract": {
                        "motion_brief": (
                            "光の中でガラスの靴が現れる"
                            if index == 1
                            else "少女がガラスの靴で一歩進む"
                        ),
                        "end_state": "ガラスの靴を履いた少女が階段前で止まる",
                        **(
                            {"allowed_new_reveal_elements": ["ガラスの靴"]}
                            if index == 1
                            else {}
                        ),
                    }
                }
                write_test_png(
                    run_dir / f"assets/scenes/scene10_cut{index}.png"
                )
            scene["render_units"] = [
                {
                    "unit_id": "1",
                    "source_cut_ids": ["1", "2"],
                    "cut_contract": {
                        "motion_contract": {
                            "motion_brief": "光の中でガラスの靴が現れ、少女が階段前へ一歩進む",
                            "end_state": "ガラスの靴を履いた少女が階段前で止まる",
                            "allowed_new_reveal_elements": ["ガラスの靴"],
                        }
                    },
                }
            ]
            image_gen_app._write_manifest_data(
                manifest_path,
                original_text,
                manifest,
            )

            with patch("server.image_gen_app.ROOT", root):
                result = image_gen_app._materialize_scene_storyboard_video_requests(
                    run_id
                )

            _path, _text, updated = image_gen_app._read_manifest_data(run_dir)
            unit_contract = updated["scenes"][0]["render_units"][0][
                "cut_contract"
            ]

        self.assertEqual(result["unitCount"], 1)
        self.assertEqual(
            unit_contract["motion_contract"]["allowed_new_reveal_elements"],
            ["ガラスの靴"],
        )

    def test_seedance_reference_only_execution_uses_i2v_model(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ARK_SEEDANCE_I2V_MODEL": "seedance-reference-model",
                "ARK_SEEDANCE_T2V_MODEL": "seedance-text-model",
            },
        ):
            options = image_gen_app._server_video_execution_options(
                tool="seedance",
                has_first_frame=False,
                has_reference_images=True,
            )

        self.assertEqual(options["model"], "seedance-reference-model")

    def test_video_provider_capabilities_are_model_and_input_mode_bound(self) -> None:
        default_reference = resolve_video_provider_capabilities(
            tool="seedance",
            input_mode="reference_images",
        )
        known_reference = resolve_video_provider_capabilities(
            tool="seedance",
            model="seedance-1-0-lite-i2v-250428",
            input_mode="reference_to_video",
        )
        unknown_model = resolve_video_provider_capabilities(
            tool="seedance",
            model="seedance-2-experimental",
            input_mode="reference_images",
        )
        kling = resolve_video_provider_capabilities(
            tool="kling_3_0",
            input_mode="image_to_video",
        )

        self.assertEqual(
            (
                default_reference.duration_min_seconds,
                default_reference.duration_max_seconds,
                default_reference.reference_images_min,
                default_reference.reference_images_max,
            ),
            (2, 12, 1, 4),
        )
        self.assertEqual(default_reference, known_reference)
        for alias in (
            "byteplus_seedance",
            "bytedance-seedance",
            "ark_seedance",
            "seadream_video",
        ):
            self.assertEqual(
                resolve_video_provider_capabilities(
                    tool=alias,
                    input_mode="reference_images",
                ),
                default_reference,
            )
        self.assertFalse(unknown_model.supported)
        self.assertIn("no reviewed capability contract", unknown_model.unsupported_reason)
        self.assertEqual(
            (kling.duration_min_seconds, kling.duration_max_seconds),
            (1, 60),
        )
        self.assertEqual(
            resolve_video_provider_capabilities(
                tool="kling-omni",
                input_mode="image_to_video",
            ),
            resolve_video_provider_capabilities(
                tool="kling_3_0_omni",
                input_mode="image_to_video",
            ),
        )
        unsupported_issues = image_gen_app._video_provider_capability_issues(
            label="scene10_unit1",
            tool="seedance",
            model="seedance-2-experimental",
            input_mode="reference_to_video",
            duration_seconds=8,
            reference_count=2,
        )
        self.assertEqual(len(unsupported_issues), 1)
        self.assertIn("no reviewed capability contract", unsupported_issues[0])

    def test_storyboard_partition_preserves_order_and_avoids_subminimum_tail(self) -> None:
        entries = [
            (f"cut-{index}", str(index), {}, duration)
            for index, duration in enumerate((6, 6, 1), start=1)
        ]

        groups = image_gen_app._partition_storyboard_entries(
            entries,
            minimum_duration_seconds=2,
            maximum_duration_seconds=12,
        )

        self.assertEqual(
            [[entry[3] for entry in group] for group in groups],
            [[6], [6, 1]],
        )
        with self.assertRaisesRegex(ValueError, "cannot be partitioned"):
            image_gen_app._partition_storyboard_entries(
                [("cut-1", "1", {}, 1)],
                minimum_duration_seconds=2,
                maximum_duration_seconds=12,
            )

    def test_seedance_reference_render_unit_over_12_seconds_is_hard_rejected(self) -> None:
        first_frame = "assets/scenes/scene10_cut1.png"
        storyboard = "assets/storyboards/scene10_storyboard.png"
        manifest = {
            "scenes": [
                {
                    "scene_id": "10",
                    "cuts": [{"cut_id": "1", "duration_seconds": 13}],
                    "render_units": [
                        {
                            "unit_id": "1",
                            "source_cut_ids": ["1"],
                            "storyboard_image": storyboard,
                            "video_input_contract": {
                                "schema_version": "render_unit_video_input_v1",
                                "input_mode": "reference_images",
                                "required_references": [first_frame, storyboard],
                                "reference_roles": [
                                    {"image_index": 1, "role": "start_state_visual_anchor"},
                                    {"image_index": 2, "role": "ordered_storyboard_sequence_guide"},
                                ],
                            },
                            "video_generation": {
                                "tool": "seedance",
                                "duration_seconds": 13,
                                "references": [first_frame, storyboard],
                            },
                        }
                    ],
                }
            ]
        }

        with self.assertRaisesRegex(
            ValueError,
            r"invalid render-unit timeline:.*2-12s",
        ):
            image_gen_app._manifest_video_targets(manifest)

    def test_seedance_non_render_unit_over_12_seconds_is_timeline_rejected(self) -> None:
        manifest = {
            "scenes": [
                {
                    "scene_id": "10",
                    "cuts": [
                        {
                            "cut_id": "1",
                            "duration_seconds": 13,
                            "video_generation": {
                                "tool": "seedance",
                                "duration_seconds": 13,
                            },
                        }
                    ],
                }
            ]
        }

        with self.assertRaisesRegex(
            ValueError,
            r"invalid render-unit timeline:.*2-12s",
        ):
            image_gen_app._manifest_video_targets(manifest)

    def test_video_target_lookup_resolves_storyboard_render_unit(self) -> None:
        unit = {
            "unit_id": "1",
            "source_cut_ids": ["1"],
            "video_generation": {
                "motion_prompt": "scene motion",
                "duration_seconds": 8,
            },
        }
        manifest = {
            "scenes": [
                {
                    "scene_id": "10",
                    "cuts": [{"cut_id": "1", "duration_seconds": 8}],
                    "render_units": [unit],
                }
            ]
        }

        target = image_gen_app._video_target_by_item_id(
            manifest,
            "scene10_unit1",
        )

        self.assertIsNotNone(target)
        self.assertIs(target["cut"], unit)
        self.assertEqual(target["selector"], "scene10_unit1")

    def test_manifest_video_targets_hard_rejects_invalid_render_unit_ownership(self) -> None:
        base_manifest = {
            "scenes": [
                {
                    "scene_id": "10",
                    "cuts": [
                        {"cut_id": "1", "duration_seconds": 8},
                        {"cut_id": "2", "duration_seconds": 8},
                    ],
                    "render_units": [
                        {
                            "unit_id": "1",
                            "source_cut_ids": ["1", "2"],
                            "video_generation": {"duration_seconds": 16},
                        }
                    ],
                }
            ]
        }
        cases: dict[str, tuple[dict[str, Any], str]] = {}

        missing_sources = json.loads(json.dumps(base_manifest))
        missing_sources["scenes"][0]["render_units"][0]["source_cut_ids"] = []
        cases["missing source list"] = (missing_sources, "non-empty list")

        unknown_source = json.loads(json.dumps(base_manifest))
        unknown_source["scenes"][0]["render_units"][0]["source_cut_ids"] = ["1", "9"]
        cases["unknown source"] = (unknown_source, "unknown or deleted source cut")

        wrong_order = json.loads(json.dumps(base_manifest))
        wrong_order["scenes"][0]["render_units"][0]["source_cut_ids"] = ["2", "1"]
        cases["wrong order"] = (wrong_order, "source-cut order")

        duplicate_owner = json.loads(json.dumps(base_manifest))
        duplicate_owner["scenes"][0]["render_units"] = [
            {
                "unit_id": "1",
                "source_cut_ids": ["1"],
                "video_generation": {"duration_seconds": 8},
            },
            {
                "unit_id": "2",
                "source_cut_ids": ["1", "2"],
                "video_generation": {"duration_seconds": 16},
            },
        ]
        cases["duplicate owner"] = (duplicate_owner, "owned by both")

        missing_coverage = json.loads(json.dumps(base_manifest))
        missing_coverage["scenes"][0]["render_units"][0] = {
            "unit_id": "1",
            "source_cut_ids": ["1"],
            "video_generation": {"duration_seconds": 8},
        }
        cases["missing coverage"] = (missing_coverage, "active cuts missing")

        deleted_source = json.loads(json.dumps(base_manifest))
        deleted_source["scenes"][0]["cuts"][1]["status"] = "deleted"
        cases["deleted source"] = (deleted_source, "unknown or deleted source cut")

        duplicate_cut_id = json.loads(json.dumps(base_manifest))
        duplicate_cut_id["scenes"][0]["cuts"][1]["cut_id"] = "1"
        duplicate_cut_id["scenes"][0]["render_units"][0] = {
            "unit_id": "1",
            "source_cut_ids": ["1"],
            "video_generation": {"duration_seconds": 8},
        }
        cases["duplicate active cut id"] = (duplicate_cut_id, "duplicate active cut id")

        deleted_unit = json.loads(json.dumps(base_manifest))
        deleted_unit["scenes"][0]["render_units"][0]["status"] = "deleted"
        cases["deleted render unit"] = (deleted_unit, "deleted/reference render units")

        for label, (manifest, expected) in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    ValueError,
                    rf"invalid render-unit timeline:.*{expected}",
                ):
                    image_gen_app._manifest_video_targets(manifest)

    def test_invalid_render_unit_ownership_is_rejected_by_video_items_and_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            manifest_path, original, manifest = image_gen_app._read_manifest_data(run_dir)
            for cut in manifest["scenes"][0]["cuts"]:
                cut["duration_seconds"] = 8
            manifest["scenes"][0]["render_units"] = [
                {
                    "unit_id": "1",
                    "source_cut_ids": ["1", "2"],
                    "video_generation": {"duration_seconds": 16},
                }
            ]
            image_gen_app._write_manifest_data(manifest_path, original, manifest)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        video_items = client.get(
                            "/api/image-gen/video-items?run_id=sample_run"
                        )
                        materialize = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "items": [
                                    {
                                        "item_id": "scene10_unit1",
                                        "kind": "scene",
                                        "video_duration_seconds": 16,
                                    }
                                ],
                            },
                        )

        self.assertEqual(video_items.status_code, 400)
        self.assertIn("active cuts missing from render_units", video_items.text)
        self.assertEqual(materialize.status_code, 400)
        self.assertIn("active cuts missing from render_units", materialize.text)

    def test_create_video_prompts_materializes_storyboard_render_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            storyboard_rel = "assets/storyboards/scene10_storyboard.png"
            write_test_png(run_dir / storyboard_rel, (80, 100, 120))
            manifest_path = run_dir / "video_manifest.md"
            original = manifest_path.read_text(encoding="utf-8")
            manifest = yaml.safe_load(
                image_gen_app._extract_manifest_yaml_text(original)
            )
            manifest["scenes"][0]["cuts"] = [manifest["scenes"][0]["cuts"][0]]
            manifest["scenes"][0]["cuts"][0]["duration_seconds"] = 8
            first_frame_rel = "assets/scenes/scene10_cut1.png"
            write_test_png(run_dir / first_frame_rel, (120, 80, 40))
            manifest["scenes"][0]["render_units"] = [
                {
                    "unit_id": "1",
                    "source_cut_ids": ["1"],
                    "storyboard_image": storyboard_rel,
                    "video_input_contract": {
                        "schema_version": "render_unit_video_input_v1",
                        "input_mode": "reference_images",
                        "required_references": [first_frame_rel, storyboard_rel],
                        "reference_roles": [
                            {"image_index": 1, "role": "start_state_visual_anchor"},
                            {"image_index": 2, "role": "ordered_storyboard_sequence_guide"},
                        ],
                    },
                    "video_generation": {
                        "tool": "seedance",
                        "prompt_authoring_source": "場面全体へゆっくり寄る",
                        "motion_prompt": "compatibility prompt",
                        "duration_seconds": 8,
                        "quality": "1080p",
                        "aspect_ratio": "16:9",
                        "references": [first_frame_rel, storyboard_rel],
                        "output": "assets/scenes/scene10/scene10_unit1.mp4",
                    },
                }
            ]
            image_gen_app._write_manifest_data(manifest_path, original, manifest)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "replace_all": False,
                                "items": [
                                    {
                                        "item_id": "scene10_unit1",
                                        "kind": "scene",
                                        "output": first_frame_rel,
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "",
                                        "video_references": [first_frame_rel, storyboard_rel],
                                        "video_duration_seconds": 8,
                                        "video_quality": "1080p",
                                        "video_aspect_ratio": "16:9",
                                        "video_tool": "seedance",
                                    }
                                ],
                            },
                        )

            updated = yaml.safe_load(
                image_gen_app._extract_manifest_yaml_text(
                    manifest_path.read_text(encoding="utf-8")
                )
            )
            unit_video = updated["scenes"][0]["render_units"][0][
                "video_generation"
            ]
            request_text = (run_dir / "video_generation_requests.md").read_text(
                encoding="utf-8"
            )
            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            unit_video["output"],
            "assets/scenes/scene10/scene10_unit1.mp4",
        )
        self.assertIn(
            "- output: `assets/scenes/scene10/scene10_unit1.mp4`",
            request_text,
        )
        self.assertEqual(
            unit_video["api_prompt_payload"]["policy_version"],
            "video_api_prompt_v1",
        )
        self.assertEqual(
            unit_video["api_prompt_payload"]["provider_request_binding"][
                "reference_roles"
            ],
            [
                {"image_index": 1, "role": "start_state_visual_anchor"},
                {
                    "image_index": 2,
                    "role": "ordered_storyboard_sequence_guide",
                },
            ],
        )
        self.assertIn(
            "参照画像1は開始状態の基準",
            unit_video["api_prompt_payload"]["prompt"],
        )
        self.assertEqual(
            state["review.video_prompt.item.scene10_unit1.status"],
            "approved",
        )

    def test_video_items_exposes_render_units_instead_of_ignored_source_cuts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            storyboard_rel = "assets/storyboards/scene10_storyboard.png"
            write_test_png(run_dir / storyboard_rel, (80, 100, 120))
            manifest_path, original, manifest = image_gen_app._read_manifest_data(run_dir)
            for cut in manifest["scenes"][0]["cuts"]:
                cut["duration_seconds"] = 4
            first_frame_rel = "assets/scenes/scene10_cut1.png"
            manifest["scenes"][0]["render_units"] = [
                {
                    "unit_id": "1",
                    "source_cut_ids": ["1", "2", "3"],
                    "storyboard_image": storyboard_rel,
                    "video_input_contract": {
                        "schema_version": "render_unit_video_input_v1",
                        "input_mode": "reference_images",
                        "required_references": [first_frame_rel, storyboard_rel],
                        "reference_roles": [
                            {"image_index": 1, "role": "start_state_visual_anchor"},
                            {"image_index": 2, "role": "ordered_storyboard_sequence_guide"},
                        ],
                    },
                    "video_generation": {
                        "tool": "seedance",
                        "prompt_authoring_source": "場面全体へゆっくり寄る",
                        "duration_seconds": 12,
                        "references": [first_frame_rel, storyboard_rel],
                        "output": "assets/scenes/scene10/scene10_unit1.mp4",
                    },
                }
            ]
            image_gen_app._write_manifest_data(manifest_path, original, manifest)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.get(
                            "/api/image-gen/video-items?run_id=sample_run"
                        )
                        rejected_cut = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                    }
                                ],
                            },
                        )

        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual([item["id"] for item in items], ["scene10_unit1"])
        self.assertTrue(items[0]["isRenderUnit"])
        self.assertEqual(items[0]["sourceCutIds"], ["1", "2", "3"])
        self.assertEqual(items[0]["videoFirstReference"], "")
        self.assertEqual(items[0]["videoInputMode"], "reference_images")
        self.assertEqual(items[0]["videoReferences"], [first_frame_rel, storyboard_rel])
        self.assertEqual(rejected_cut.status_code, 400)
        self.assertIn("video manifest targets not found", rejected_cut.text)

    def test_render_unit_materialization_rejects_duration_different_from_source_cut_total(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            manifest_path, original, manifest = image_gen_app._read_manifest_data(run_dir)
            manifest["scenes"][0]["cuts"] = [manifest["scenes"][0]["cuts"][0]]
            manifest["scenes"][0]["cuts"][0]["duration_seconds"] = 8
            manifest["scenes"][0]["render_units"] = [
                {
                    "unit_id": "1",
                    "source_cut_ids": ["1"],
                    "video_generation": {"duration_seconds": 8},
                }
            ]
            image_gen_app._write_manifest_data(manifest_path, original, manifest)
            item = image_gen_app.FrontendReviewItem(
                item_id="scene10_unit1",
                kind="scene",
                video_duration_seconds=7,
            )

            with self.assertRaisesRegex(
                ValueError,
                "must equal source-cut total 8s",
            ):
                image_gen_app._effective_video_materialization_items(
                    run_dir,
                    [item],
                )

    def test_render_unit_storyboard_input_contract_rejects_edits_and_preserves_omitted_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            manifest_path, original, manifest = image_gen_app._read_manifest_data(run_dir)
            manifest["scenes"][0]["cuts"] = [manifest["scenes"][0]["cuts"][0]]
            manifest["scenes"][0]["cuts"][0]["duration_seconds"] = 8
            first_frame = "assets/scenes/scene10_cut1.png"
            storyboard = "assets/storyboards/scene10_storyboard.png"
            manifest["scenes"][0]["render_units"] = [
                {
                    "unit_id": "1",
                    "source_cut_ids": ["1"],
                    "storyboard_image": storyboard,
                    "video_input_contract": {
                        "schema_version": "render_unit_video_input_v1",
                        "input_mode": "reference_images",
                        "required_references": [first_frame, storyboard],
                        "reference_roles": [
                            {"image_index": 1, "role": "start_state_visual_anchor"},
                            {"image_index": 2, "role": "ordered_storyboard_sequence_guide"},
                        ],
                    },
                    "video_generation": {
                        "tool": "seedance",
                        "duration_seconds": 8,
                        "references": [first_frame, storyboard],
                    },
                }
            ]
            image_gen_app._write_manifest_data(manifest_path, original, manifest)

            preserved = image_gen_app._effective_video_materialization_items(
                run_dir,
                [
                    image_gen_app.FrontendReviewItem(
                        item_id="scene10_unit1",
                        kind="scene",
                        video_duration_seconds=8,
                    )
                ],
            )[0]

            self.assertEqual(preserved.video_first_reference, "")
            self.assertEqual(preserved.video_references, [first_frame, storyboard])
            with self.assertRaisesRegex(ValueError, "must keep first frame empty"):
                image_gen_app._effective_video_materialization_items(
                    run_dir,
                    [
                        image_gen_app.FrontendReviewItem(
                            item_id="scene10_unit1",
                            kind="scene",
                            video_duration_seconds=8,
                            video_first_reference="assets/scenes/replacement.png",
                            video_references=[first_frame, storyboard],
                        )
                    ],
                )
            with self.assertRaisesRegex(ValueError, "must exactly preserve"):
                image_gen_app._effective_video_materialization_items(
                    run_dir,
                    [
                        image_gen_app.FrontendReviewItem(
                            item_id="scene10_unit1",
                            kind="scene",
                            video_duration_seconds=8,
                            video_first_reference="",
                            video_references=[],
                        )
                    ],
                )
            for tampered_references in (
                [storyboard, first_frame],
                [storyboard],
            ):
                with self.subTest(tampered_references=tampered_references):
                    tampered_manifest = json.loads(json.dumps(manifest))
                    tampered_unit = tampered_manifest["scenes"][0][
                        "render_units"
                    ][0]
                    tampered_unit["video_input_contract"][
                        "required_references"
                    ] = tampered_references
                    tampered_unit["video_generation"][
                        "references"
                    ] = tampered_references
                    with self.assertRaisesRegex(
                        ValueError,
                        "ordered first source-cut image and storyboard_image",
                    ):
                        image_gen_app._manifest_video_targets(
                            tampered_manifest
                        )

            for label, mutate, expected in (
                (
                    "missing_roles",
                    lambda contract: contract.pop("reference_roles"),
                    "reference_roles count must equal",
                ),
                (
                    "duplicate_index",
                    lambda contract: contract["reference_roles"][1].update(
                        {"image_index": 1}
                    ),
                    "image_index must be 1-based, consecutive, unique",
                ),
                (
                    "unknown_role",
                    lambda contract: contract["reference_roles"][1].update(
                        {"role": "unknown_role"}
                    ),
                    "unsupported video reference role",
                ),
            ):
                with self.subTest(reference_role_case=label):
                    tampered_manifest = json.loads(json.dumps(manifest))
                    contract = tampered_manifest["scenes"][0]["render_units"][0][
                        "video_input_contract"
                    ]
                    mutate(contract)
                    with self.assertRaisesRegex(ValueError, expected):
                        image_gen_app._manifest_video_targets(
                            tampered_manifest
                        )

    def test_server_render_unit_visual_plan_prefers_unit_then_first_source_cut(self) -> None:
        source_plan = {"subject": "first source cut subject"}
        unit_plan = {"subject": "unit-authored subject"}
        unit = {
            "unit_id": "1",
            "source_cut_ids": ["1"],
            "video_generation": {"duration_seconds": 8},
        }
        manifest = {
            "scenes": [
                {
                    "scene_id": "10",
                    "cuts": [
                        {
                            "cut_id": "1",
                            "duration_seconds": 8,
                            "image_generation": {
                                "first_frame_visual_plan": source_plan,
                            },
                        }
                    ],
                    "render_units": [unit],
                }
            ]
        }
        target = image_gen_app._video_target_by_item_id(manifest, "scene10_unit1")

        self.assertEqual(
            image_gen_app._first_frame_visual_plan_for_server_target(target or {}),
            source_plan,
        )
        unit["image_generation"] = {"first_frame_visual_plan": unit_plan}
        self.assertEqual(
            image_gen_app._first_frame_visual_plan_for_server_target(target or {}),
            unit_plan,
        )

    def test_server_render_unit_contract_passes_explicit_reveal_authorization_to_composer(
        self,
    ) -> None:
        data = {
            "scenes": [
                {
                    "scene_id": "10",
                    "cuts": [
                        {
                            "cut_id": "1",
                            "duration_seconds": 4,
                            "cut_contract": {
                                "motion_contract": {
                                    "motion_brief": "光の中でガラスの靴が現れる",
                                    "allowed_new_reveal_elements": ["ガラスの靴"],
                                }
                            },
                        },
                        {
                            "cut_id": "2",
                            "duration_seconds": 4,
                            "cut_contract": {
                                "motion_contract": {
                                    "motion_brief": "少女が階段前へ一歩進む",
                                    "end_state": "少女が階段前で止まる",
                                }
                            },
                        },
                    ],
                    "render_units": [
                        {
                            "unit_id": "1",
                            "source_cut_ids": ["1", "2"],
                            "cut_contract": {
                                "motion_contract": {
                                    "motion_brief": "ガラスの靴が現れ、少女が階段前へ一歩進む",
                                    "end_state": "ガラスの靴を履いた少女が階段前で止まる",
                                    "allowed_new_reveal_elements": ["ガラスの靴"],
                                }
                            },
                            "video_generation": {"duration_seconds": 8},
                        }
                    ],
                }
            ]
        }
        target = image_gen_app._video_target_by_item_id(
            data,
            "scene10_unit1",
        )

        contract = image_gen_app._video_contract_for_server_target(target or {})

        self.assertEqual(
            contract["motion_contract"]["allowed_new_reveal_elements"],
            ["ガラスの靴"],
        )

    def test_video_materialization_rejects_canonical_render_timeline_duration_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            manifest_path, original, manifest = image_gen_app._read_manifest_data(run_dir)
            cut = manifest["scenes"][0]["cuts"][0]
            cut["render"] = {"video_duration_seconds": 8}
            cut["video_generation"] = {"duration_seconds": 8}
            manifest["narration_workflow"] = {
                "final_audio_review": {
                    "status": "approved",
                    "approved_timeline_hash": image_gen_app._manifest_narration_timeline_hash(
                        manifest
                    ),
                }
            }
            image_gen_app._write_manifest_data(manifest_path, original, manifest)

            with self.assertRaisesRegex(ValueError, "canonical render timeline duration 8s"):
                image_gen_app._effective_video_materialization_items(
                    run_dir,
                    [
                        image_gen_app.FrontendReviewItem(
                            item_id="scene10_cut1",
                            kind="scene",
                            video_duration_seconds=7,
                        )
                    ],
                )
            unchanged = image_gen_app._effective_video_materialization_items(
                run_dir,
                [
                    image_gen_app.FrontendReviewItem(
                        item_id="scene10_cut1",
                        kind="scene",
                        video_duration_seconds=8,
                    )
                ],
            )
            self.assertEqual(unchanged[0].video_duration_seconds, 8)

    def test_unapproved_video_materialization_synchronizes_render_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            item = image_gen_app.FrontendReviewItem(
                item_id="scene10_cut1",
                kind="scene",
                output="assets/scenes/scene10_cut1.png",
                video_prompt="slow dolly forward",
                video_duration_seconds=6,
            )

            effective = image_gen_app._effective_video_materialization_items(run_dir, [item])
            image_gen_app._update_manifest_video_generation(run_dir, effective)
            _path, _original, updated = image_gen_app._read_manifest_data(run_dir)
            cut = updated["scenes"][0]["cuts"][0]

        self.assertEqual(cut["video_generation"]["duration_seconds"], 6)
        self.assertEqual(cut["render"]["video_duration_seconds"], 6)

    def test_render_unit_partial_merge_removes_source_cut_request_and_revokes_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            manifest_path, original, manifest = image_gen_app._read_manifest_data(run_dir)
            for cut in manifest["scenes"][0]["cuts"]:
                cut["duration_seconds"] = 4
            first_frame = "assets/scenes/scene10_cut1.png"
            storyboard = "assets/storyboards/scene10_storyboard.png"
            write_test_png(run_dir / first_frame)
            write_test_png(run_dir / storyboard)
            manifest["scenes"][0]["render_units"] = [
                {
                    "unit_id": "1",
                    "source_cut_ids": ["1", "2", "3"],
                    "storyboard_image": storyboard,
                    "video_input_contract": {
                        "schema_version": "render_unit_video_input_v1",
                        "input_mode": "reference_images",
                        "required_references": [first_frame, storyboard],
                        "reference_roles": [
                            {"image_index": 1, "role": "start_state_visual_anchor"},
                            {"image_index": 2, "role": "ordered_storyboard_sequence_guide"},
                        ],
                    },
                    "video_generation": {
                        "tool": "seedance",
                        "duration_seconds": 12,
                        "references": [first_frame, storyboard],
                    },
                }
            ]
            manifest["scenes"].append(
                {
                    "scene_id": "20",
                    "cuts": [
                        {
                            "cut_id": "1",
                            "duration_seconds": 8,
                            "image_generation": {
                                "output": "assets/scenes/scene20_cut1.png"
                            },
                        }
                    ],
                }
            )
            image_gen_app._write_manifest_data(manifest_path, original, manifest)
            (run_dir / "video_generation_requests.md").write_text(
                "# Video Generation Requests\n\n"
                "## scene10_cut1\n\nlegacy source-cut request\n\n"
                "## scene20_cut1\n\nkeep canonical request\n",
                encoding="utf-8",
            )
            with (run_dir / "state.txt").open("a", encoding="utf-8") as state_file:
                state_file.write(
                    "review.video_prompt.item.scene10_cut1.status=approved\n"
                    "review.video_prompt.item.scene20_cut1.status=approved\n"
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
                                        "item_id": "scene10_unit1",
                                        "kind": "scene",
                                        "output": first_frame,
                                        "video_prompt": "continuous scene motion",
                                        "video_first_reference": "",
                                        "video_references": [first_frame, storyboard],
                                        "video_duration_seconds": 12,
                                        "video_tool": "seedance",
                                    }
                                ],
                            },
                        )

            request_text = (run_dir / "video_generation_requests.md").read_text(
                encoding="utf-8"
            )
            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("## scene10_cut1", request_text)
        self.assertIn("## scene10_unit1", request_text)
        self.assertIn("## scene20_cut1", request_text)
        self.assertEqual(
            state["review.video_prompt.item.scene10_cut1.status"],
            "revoked",
        )
        self.assertEqual(
            state["review.video_prompt.item.scene20_cut1.status"],
            "approved",
        )

    def test_video_stage_approval_requires_full_canonical_item_coverage_not_replace_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            write_test_png(run_dir / "assets/scenes/scene10_cut1.png")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "replace_all": True,
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                        "video_first_reference": "assets/scenes/scene10_cut1.png",
                                        "video_duration_seconds": 8,
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                    }
                                ],
                            },
                        )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(state["slot.p830.status"], "in_progress")
        self.assertEqual(state["stage.video_generation.status"], "in_progress")
        self.assertEqual(state["gate.video_prompt_review"], "required")
        self.assertEqual(
            state["review.video_prompt.status"],
            "partially_approved_for_generation",
        )

    def test_video_prompt_approval_rechecks_semantic_currentness_inside_write_lock(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            output = "assets/scenes/scene10_cut1.png"
            write_test_png(run_dir / output)

            with (
                patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}),
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._assert_video_prompt_semantic_review_is_current",
                    side_effect=ValueError(
                        "video motion semantic review became stale before approval"
                    ),
                ) as recheck,
            ):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/image-gen/video-prompts/create",
                        json={
                            "run_id": "sample_run",
                            "approve_for_generation": True,
                            "items": [
                                {
                                    "item_id": "scene10_cut1",
                                    "kind": "scene",
                                    "output": output,
                                    "video_first_reference": output,
                                    "video_duration_seconds": 8,
                                    "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                }
                            ],
                        },
                    )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("semantic review became stale", response.text)
        self.assertEqual(state["stage.video_generation.status"], "in_progress")
        self.assertEqual(state["slot.p830.status"], "in_progress")
        self.assertEqual(state["review.video_prompt.status"], "pending")
        self.assertEqual(
            state["review.video_prompt.item.scene10_cut1.status"],
            "pending",
        )
        self.assertEqual(recheck.call_count, 1)
        self.assertEqual(recheck.call_args.args[0].resolve(), run_dir.resolve())

    def test_video_stage_approval_completes_for_full_coverage_with_partial_merge_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            items: list[dict[str, Any]] = []
            for index in range(1, 4):
                output = f"assets/scenes/scene10_cut{index}.png"
                write_test_png(run_dir / output)
                items.append(
                    {
                        "item_id": f"scene10_cut{index}",
                        "kind": "scene",
                        "output": output,
                        "video_first_reference": output,
                        "video_duration_seconds": 8,
                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                    }
                )

            state_during_semantic_review: dict[str, str] = {}

            async def observe_materialization_state(*, run_dir: Path) -> None:
                state_during_semantic_review.update(
                    image_gen_app.parse_state_file(run_dir / "state.txt")
                )

            self.video_semantic_review_mock.side_effect = (
                observe_materialization_state
            )

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "replace_all": False,
                                "approve_for_generation": True,
                                "items": items,
                            },
                        )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            state_during_semantic_review["stage.video_generation.status"],
            "in_progress",
        )
        self.assertEqual(
            state_during_semantic_review["slot.p830.status"],
            "in_progress",
        )
        self.assertEqual(
            state_during_semantic_review["review.video_prompt.status"],
            "pending",
        )
        self.assertEqual(
            state_during_semantic_review["gate.video_prompt_review"],
            "required",
        )
        self.assertEqual(state["slot.p830.status"], "done")
        self.assertEqual(state["stage.video_generation.status"], "in_progress")
        self.assertEqual(state["gate.video_prompt_review"], "required")
        self.assertEqual(
            state["review.video_prompt.status"],
            "approved_for_generation",
        )

    def test_video_stage_awaits_human_only_after_all_items_are_materialized_and_semantically_reviewed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            items: list[dict[str, Any]] = []
            for index in range(1, 4):
                output = f"assets/scenes/scene10_cut{index}.png"
                write_test_png(run_dir / output)
                items.append(
                    {
                        "item_id": f"scene10_cut{index}",
                        "kind": "scene",
                        "output": output,
                        "video_first_reference": output,
                        "video_duration_seconds": 8,
                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                    }
                )

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        materialized = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "replace_all": True,
                                "items": items,
                            },
                        )
                        materialized_state = image_gen_app.parse_state_file(
                            run_dir / "state.txt"
                        )
                        approved_one = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "replace_all": False,
                                "approve_for_generation": True,
                                "items": [items[0]],
                            },
                        )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(materialized.status_code, 200, materialized.text)
        self.assertEqual(
            materialized_state["stage.video_generation.status"],
            "in_progress",
        )
        self.assertEqual(materialized_state["slot.p830.status"], "in_progress")
        self.assertEqual(approved_one.status_code, 200, approved_one.text)
        self.assertEqual(state["stage.video_generation.status"], "awaiting_approval")
        self.assertEqual(state["slot.p830.status"], "awaiting_approval")
        self.assertEqual(
            state["review.video_prompt.status"],
            "partially_approved_for_generation",
        )
        self.assertEqual(state["gate.video_prompt_review"], "required")

    def test_video_stage_approval_completes_after_sequential_item_approvals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            items: list[dict[str, Any]] = []
            for index in range(1, 4):
                output = f"assets/scenes/scene10_cut{index}.png"
                write_test_png(run_dir / output)
                items.append(
                    {
                        "item_id": f"scene10_cut{index}",
                        "kind": "scene",
                        "output": output,
                        "video_first_reference": output,
                        "video_duration_seconds": 8,
                        "video_prompt": (
                            f"action: 主人公が画面奥へ{index}歩進み、その場で止まる。\n"
                            "camera: slow dolly forward"
                        ),
                    }
                )

            statuses: list[str] = []
            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        for item in items:
                            response = client.post(
                                "/api/image-gen/video-prompts/create",
                                json={
                                    "run_id": "sample_run",
                                    "replace_all": False,
                                    "approve_for_generation": True,
                                    "items": [item],
                                },
                            )
                            self.assertEqual(response.status_code, 200, response.text)
                            statuses.append(
                                image_gen_app.parse_state_file(
                                    run_dir / "state.txt"
                                )["slot.p830.status"]
                            )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            request_text = (run_dir / "video_generation_requests.md").read_text(
                encoding="utf-8"
            )

        self.assertEqual(statuses, ["in_progress", "in_progress", "done"])
        self.assertEqual(state["review.video_prompt.status"], "approved_for_generation")
        self.assertEqual(state["stage.video_generation.status"], "in_progress")
        self.assertEqual(state["gate.video_prompt_review"], "required")
        for index in range(1, 4):
            self.assertEqual(
                state[f"review.video_prompt.item.scene10_cut{index}.status"],
                "approved",
            )
            self.assertIn(f"## scene10_cut{index}", request_text)

    def test_video_stage_reapproval_of_one_changed_item_keeps_other_current_approvals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            items: list[dict[str, Any]] = []
            for index in range(1, 4):
                output = f"assets/scenes/scene10_cut{index}.png"
                write_test_png(run_dir / output)
                items.append(
                    {
                        "item_id": f"scene10_cut{index}",
                        "kind": "scene",
                        "output": output,
                        "video_first_reference": output,
                        "video_duration_seconds": 8,
                        "video_prompt": f"cut {index} original motion",
                    }
                )

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        initial = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "replace_all": False,
                                "approve_for_generation": True,
                                "items": items,
                            },
                        )
                        changed_item = {
                            **items[2],
                            "video_prompt": "cut 3 revised motion",
                        }
                        revised = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "replace_all": False,
                                "approve_for_generation": True,
                                "items": [changed_item],
                            },
                        )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertEqual(revised.status_code, 200, revised.text)
        self.assertEqual(state["slot.p830.status"], "done")
        self.assertEqual(state["review.video_prompt.status"], "approved_for_generation")
        for index in range(1, 4):
            self.assertEqual(
                state[f"review.video_prompt.item.scene10_cut{index}.status"],
                "approved",
            )

    def test_video_stage_does_not_complete_with_a_stale_retained_item(self) -> None:
        for mutation in (
            "projection_version",
            "canonical_design",
            "nested_ir",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                run_dir = write_valid_p650_artifacts(root, "sample_run")
                items: list[dict[str, Any]] = []
                for index in range(1, 4):
                    output = f"assets/scenes/scene10_cut{index}.png"
                    write_test_png(run_dir / output)
                    items.append(
                        {
                            "item_id": f"scene10_cut{index}",
                            "kind": "scene",
                            "output": output,
                            "video_first_reference": output,
                            "video_duration_seconds": 8,
                            "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                        }
                    )

                with patch.dict(
                    os.environ,
                    {"TOC_SERVER_AUTH_DISABLED": "1"},
                ):
                    with patch("server.image_gen_app.ROOT", root):
                        with TestClient(app) as client:
                            initial = client.post(
                                "/api/image-gen/video-prompts/create",
                                json={
                                    "run_id": "sample_run",
                                    "replace_all": False,
                                    "approve_for_generation": True,
                                    "items": items,
                                },
                            )
                            self.assertEqual(
                                initial.status_code,
                                200,
                                initial.text,
                            )
                            manifest_path = run_dir / "video_manifest.md"
                            manifest_text = manifest_path.read_text(
                                encoding="utf-8"
                            )
                            manifest = yaml.safe_load(
                                image_gen_app._extract_manifest_yaml_text(
                                    manifest_text
                                )
                            )
                            retained_cut = manifest["scenes"][0]["cuts"][1]
                            if mutation == "projection_version":
                                retained_cut["video_generation"][
                                    "api_prompt_payload"
                                ]["projection_registry_version"] = (
                                    "obsolete_projection_registry"
                                )
                            elif mutation == "canonical_design":
                                retained_cut["cut_contract"] = {
                                    "motion_contract": {
                                        "subject_motion": "主人公が左へ二歩進んで振り返る",
                                        "end_state": "主人公が左を向いて止まる",
                                    }
                                }
                            else:
                                retained_cut["video_generation"][
                                    "api_prompt_payload"
                                ]["video_prompt_ir"]["quality_issues"] = [
                                    {
                                        "code": "injected_block",
                                        "blocking": True,
                                    }
                                ]
                            image_gen_app._write_manifest_data(
                                manifest_path,
                                manifest_text,
                                manifest,
                            )
                            reapproved = client.post(
                                "/api/image-gen/video-prompts/create",
                                json={
                                    "run_id": "sample_run",
                                    "replace_all": False,
                                    "approve_for_generation": True,
                                    "items": [items[0]],
                                },
                            )

                state = image_gen_app.parse_state_file(run_dir / "state.txt")

                self.assertEqual(reapproved.status_code, 200, reapproved.text)
                self.assertEqual(state["slot.p830.status"], "in_progress")
                self.assertEqual(
                    state["stage.video_generation.status"],
                    "in_progress",
                )
                self.assertEqual(
                    state["review.video_prompt.status"],
                    "partially_approved_for_generation",
                )
                self.assertEqual(
                    state["review.video_prompt.item.scene10_cut2.status"],
                    "revoked",
                )
                self.assertEqual(state["gate.video_prompt_review"], "required")

    def test_video_prompt_reapproval_clears_prior_revocation_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            output = "assets/scenes/scene10_cut1.png"
            write_test_png(run_dir / output)
            item = {
                "item_id": "scene10_cut1",
                "kind": "scene",
                "output": output,
                "video_first_reference": output,
                "video_duration_seconds": 8,
                "video_prompt": REVIEWABLE_VIDEO_PROMPT,
            }

            with patch.dict(
                os.environ,
                {"TOC_SERVER_AUTH_DISABLED": "1"},
            ):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        materialized = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={"run_id": "sample_run", "items": [item]},
                        )
                        self.assertEqual(
                            materialized.status_code,
                            200,
                            materialized.text,
                        )
                        image_gen_app.append_state_snapshot(
                            run_dir / "state.txt",
                            {
                                "review.video_prompt.item.scene10_cut1.status": (
                                    "revoked"
                                ),
                                "review.video_prompt.item.scene10_cut1.revoked_at": (
                                    "2026-07-20T00:00:00Z"
                                ),
                                "review.video_prompt.item.scene10_cut1.revocation_reason": (
                                    "stale test contract"
                                ),
                            },
                        )
                        reapproved = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [item],
                            },
                        )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(reapproved.status_code, 200, reapproved.text)
        self.assertEqual(
            state["review.video_prompt.item.scene10_cut1.status"],
            "approved",
        )
        self.assertEqual(
            state["review.video_prompt.item.scene10_cut1.revoked_at"],
            "",
        )
        self.assertEqual(
            state["review.video_prompt.item.scene10_cut1.revocation_reason"],
            "",
        )

    def test_create_storyboard_run_endpoint_starts_scene_storyboard_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scheduled: list[dict[str, Any]] = []
            debug_log = Mock()

            def fake_run_create_job(*_args: Any, **kwargs: Any):
                scheduled.append(kwargs)

                async def noop() -> None:
                    return None

                return noop()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "TOC_IMAGE_GEN_PROVENANCE_POLICY": "serial_fallback"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._create_jobs", {}),
                    patch("server.image_gen_app._run_create_job", fake_run_create_job),
                    patch("server.image_gen_app.write_app_server_debug_log", debug_log),
                ):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/runs/create/storyboard",
                            json={"title": "桃太郎", "source": "桃太郎", "target_duration_seconds": 1200},
                        )

            payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["createMode"], "scene_storyboard")
        self.assertEqual(payload["targetDurationSeconds"], 1200)
        self.assertTrue(payload["runId"].startswith("桃太郎_storyboard_"))
        self.assertEqual(payload["path"], f"output/{payload['runId']}")
        self.assertEqual(scheduled[0]["run_id"], payload["runId"])
        self.assertEqual(scheduled[0]["create_mode"], "scene_storyboard")
        self.assertEqual(scheduled[0]["target_duration_seconds"], 1200)
        self.assertTrue(scheduled[0]["generate_images"])
        create_start = next(call for call in debug_log.call_args_list if call.kwargs.get("operation") == "create_job_start")
        self.assertEqual(create_start.kwargs["request"]["targetDurationSeconds"], 1200)

    def test_create_storyboard_run_endpoint_rejects_p650(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            async def noop_create_job(*_args: Any, **_kwargs: Any) -> None:
                return None

            with patch.dict(
                os.environ,
                {
                    "TOC_SERVER_AUTH_DISABLED": "1",
                    "TOC_IMAGE_GEN_PROVENANCE_POLICY": "serial_fallback",
                },
            ):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._create_jobs", {}),
                    patch(
                        "server.image_gen_app._run_create_job",
                        noop_create_job,
                    ),
                ):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/runs/create/storyboard",
                            json={
                                "title": "桃太郎",
                                "source": "桃太郎",
                                "stop_target": "p650",
                            },
                        )

        self.assertEqual(response.status_code, 422)

    def test_run_create_job_defensively_rejects_storyboard_p650(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "scene_storyboard create requires stop_target p680",
        ):
            asyncio.run(
                image_gen_app._run_create_job(
                    "job-id",
                    title="桃太郎",
                    source="桃太郎",
                    run_id="not-created",
                    generate_images=True,
                    create_mode="scene_storyboard",
                    stop_target="p650",
                    target_duration_seconds=300,
                )
            )

    def test_run_create_job_preserves_p570_non_visual_gate_failure_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260728_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            image_gen_app.append_state_snapshot(
                run_dir / "state.txt",
                {
                    "runtime.stage": "p570_non_visual_gate_failed",
                    "runtime.failure.stage": "p570",
                    "runtime.failure.phase": "asset_validation",
                    "runtime.failure.error_kind": "non_visual_validation",
                },
            )
            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._run_execution_leases", {}),
                patch(
                    "server.image_gen_app._acquire_run_execution_lease",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._release_run_execution_lease",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._sync_process_current_process",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._run_toc_immersive_frontend_cli_helper",
                    new=AsyncMock(
                        side_effect=RuntimeError(
                            "p560 asset gate failed: p400.review_loop_integrity"
                        )
                    ),
                ),
                patch(
                    "server.image_gen_app._cleanup_unscaffolded_run",
                    new=Mock(),
                ),
                patch(
                    "server.image_gen_app._set_create_job",
                    new=AsyncMock(),
                ),
            ):
                asyncio.run(
                    image_gen_app._run_create_job(
                        "job-id",
                        title="桃太郎",
                        source="桃太郎",
                        run_id=run_id,
                        generate_images=True,
                        stop_target="p680",
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(
            state["runtime.stage"],
            "p570_non_visual_gate_failed",
        )
        self.assertEqual(state["runtime.create_job.status"], "failed")

    def test_run_create_job_materializes_and_validates_storyboard_before_completed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_storyboard_20260727_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            for cut_index in range(1, 4):
                write_test_png(
                    run_dir
                    / "assets"
                    / "scenes"
                    / f"scene10_cut{cut_index}.png"
                )
            updates: list[dict[str, Any]] = []
            validation_calls: list[tuple[str, bool, bool]] = []
            generic_validator = Mock()
            original_storyboard_validator = (
                image_gen_app._validate_scene_storyboard_create_run
            )

            async def record_update(
                _job_id: str,
                patch_value: dict[str, Any],
            ) -> None:
                updates.append(dict(patch_value))

            def validate_storyboard(
                validated_run_id: str,
                *,
                strict_visual_quality: bool,
                run_dir_override: Path | None = None,
                validate_base: bool = True,
            ) -> None:
                original_storyboard_validator(
                    validated_run_id,
                    strict_visual_quality=False,
                    run_dir_override=run_dir_override,
                    validate_base=validate_base,
                )
                validation_calls.append(
                    (
                        validated_run_id,
                        strict_visual_quality,
                        validate_base,
                    )
                )

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_execution_leases",
                    {},
                ),
                patch(
                    "server.image_gen_app._acquire_run_execution_lease",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._release_run_execution_lease",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._sync_process_current_process",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._run_toc_immersive_frontend_cli_helper",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._set_create_job",
                    side_effect=record_update,
                ),
                patch(
                    "server.image_gen_app._validate_frontend_create_run",
                    generic_validator,
                ),
                patch(
                    "server.image_gen_app._validate_scene_storyboard_create_run",
                    side_effect=validate_storyboard,
                ),
            ):
                asyncio.run(
                    image_gen_app._run_create_job(
                        "job-id",
                        title="桃太郎",
                        source="桃太郎",
                        run_id=run_id,
                        generate_images=True,
                        create_mode="scene_storyboard",
                        stop_target="p680",
                        target_duration_seconds=300,
                    )
                )

            state = image_gen_app.parse_state_file(
                run_dir / "state.txt"
            )
            request_exists = (
                run_dir / "video_generation_requests.md"
            ).is_file()

        self.assertEqual(
            validation_calls,
            [
                (run_id, False, False),
                (run_id, False, False),
                (run_id, True, True),
            ],
        )
        self.assertEqual(generic_validator.call_count, 3)
        self.assertEqual(
            [
                generic_call.kwargs["strict_visual_quality"]
                for generic_call in generic_validator.call_args_list
            ],
            [True, True, False],
        )
        self.assertEqual(updates[-1]["status"], "completed")
        self.assertEqual(updates[-1]["currentProcess"], "p680")
        self.assertEqual(
            state["runtime.create_mode"],
            "scene_storyboard",
        )
        self.assertTrue(request_exists)

    def test_fresh_storyboard_create_uses_common_finalizer_before_terminal_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "fresh_storyboard_order"
            (root / "output" / run_id).mkdir(parents=True)
            events: list[str] = []

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_execution_leases",
                    {},
                ),
                patch(
                    "server.image_gen_app._acquire_run_execution_lease",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._release_run_execution_lease",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._sync_process_current_process",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._run_toc_immersive_frontend_cli_helper",
                    new=AsyncMock(
                        side_effect=lambda **_kwargs: events.append(
                            "generate_images"
                        )
                    ),
                ),
                patch(
                    "server.image_gen_app._finalize_scene_storyboard_p680",
                    side_effect=lambda _run_id: (
                        events.append("storyboard_finalizer")
                        or {"alreadyCurrent": False}
                    ),
                ),
                patch(
                    "server.image_gen_app._validate_created_run",
                    side_effect=lambda _run_id: events.append(
                        "base_validation"
                    ),
                ),
                patch(
                    "server.image_gen_app._validate_scene_storyboard_create_run",
                    side_effect=lambda *_args, **_kwargs: events.append(
                        "terminal_storyboard_validation"
                    ),
                ),
                patch(
                    "server.image_gen_app._set_create_job",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app.write_app_server_debug_log",
                ),
            ):
                asyncio.run(
                    image_gen_app._run_create_job(
                        "job-id",
                        title="桃太郎",
                        source="桃太郎",
                        run_id=run_id,
                        generate_images=True,
                        create_mode="scene_storyboard",
                        stop_target="p680",
                    )
                )

            self.assertEqual(
                events,
                [
                    "generate_images",
                    "storyboard_finalizer",
                    "base_validation",
                    "terminal_storyboard_validation",
                ],
            )

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

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "TOC_IMAGE_GEN_PROVENANCE_POLICY": "serial_fallback"}):
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

    def test_read_run_progress_treats_corrupt_request_snapshot_as_missing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "state.txt").write_text("topic=ガリバー旅行記\nstatus=SCRIPT\n", encoding="utf-8")
            (run_dir / "asset_generation_requests.md").write_text(
                """# Asset Generation Requests

## character_hero

- tool: `codex_builtin_image`
- output: `assets/characters/hero.png`

```text
cinematic character portrait
```
""",
                encoding="utf-8",
            )
            (run_dir / "asset_generation_request_snapshot.json").write_text(
                "{not valid json",
                encoding="utf-8",
            )
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

        self.assertEqual(progress["currentStage"], {"code": "p560", "label": "Asset Generation", "state": "pending"})

    def test_read_run_progress_treats_unreadable_request_markdown_as_missing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "state.txt").write_text("topic=ガリバー旅行記\nstatus=SCRIPT\n", encoding="utf-8")
            (run_dir / "asset_generation_requests.md").write_bytes(b"\xff\xfe\xfa")
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

        self.assertEqual(progress["currentStage"], {"code": "p560", "label": "Asset Generation", "state": "pending"})

    def test_read_run_progress_prefers_latest_failed_slot_state_over_stale_later_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "topic=シンデレラ",
                        "status=FAILED",
                        "runtime.stage=semantic_review_failed_before_media_generation",
                        "slot.p410.status=failed",
                        "slot.p640.status=awaiting_approval",
                        "slot.p650.status=pending",
                        "slot.p660.status=pending",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "asset_generation_requests.md").write_text("# Asset Generation Requests\n", encoding="utf-8")
            (run_dir / "image_generation_requests.md").write_text("# Image Generation Requests\n", encoding="utf-8")
            (run_dir / "p000_index.md").write_text(
                """# Run Index

## Stage Table

| P# | Stage | Current State |
| --- | --- | --- |
| `p000` | Run Entrance | `always_available` |
| `p100` | Research | `done` |
| `p400` | Script / Narration Text / Human Changes | `done` |
| `p600` | Scene Implementation / Image Stage | `awaiting_approval` |
| `p800` | Video Stage | `not_started` |

## Fixed Slot Contract

| Slot | Stage | Default Requirement | Purpose | Planned Artifacts |
| --- | --- | --- | --- | --- |
| `p410` | Script / Narration Text / Human Changes | `required` | Scene Completion | - |
| `p640` | Scene Implementation / Image Stage | `optional` | Judgment Review | - |
| `p650` | Scene Implementation / Image Stage | `optional` | Generation Ready | `image_generation_requests.md` |
| `p660` | Scene Implementation / Image Stage | `optional` | Image Generation | - |

#### p410 Scene Completion

- status: `done`

#### p640 Judgment Review

- status: `awaiting_approval`

#### p650 Generation Ready

- status: `pending`

#### p660 Image Generation

- status: `pending`
""",
                encoding="utf-8",
            )

            progress = image_gen.read_run_progress(run_dir)

        self.assertEqual(progress["currentStage"]["code"], "p410")
        self.assertEqual(progress["currentStage"]["state"], "failed")
        self.assertEqual(next(slot for slot in progress["slots"] if slot["code"] == "p410")["state"], "failed")
        self.assertEqual(next(stage for stage in progress["stages"] if stage["code"] == "p400")["state"], "failed")

    def test_read_run_progress_prefers_latest_in_progress_slot_over_stale_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "topic=シンデレラ",
                        "status=SCRIPT",
                        "runtime.stage=image_prompt_semantic_review",
                        "slot.p410.status=done",
                        "slot.p640.status=in_progress",
                        "slot.p650.status=pending",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "asset_generation_requests.md").write_text("# Asset Generation Requests\n", encoding="utf-8")
            (run_dir / "image_generation_requests.md").write_text("# Image Generation Requests\n", encoding="utf-8")
            (run_dir / "p000_index.md").write_text(
                """# Run Index

## Stage Table

| P# | Stage | Current State |
| --- | --- | --- |
| `p000` | Run Entrance | `always_available` |
| `p100` | Research | `done` |
| `p400` | Script / Narration Text / Human Changes | `done` |
| `p600` | Scene Implementation / Image Stage | `done` |
| `p800` | Video Stage | `not_started` |

## Fixed Slot Contract

| Slot | Stage | Default Requirement | Purpose | Planned Artifacts |
| --- | --- | --- | --- | --- |
| `p410` | Script / Narration Text / Human Changes | `required` | Scene Completion | - |
| `p640` | Scene Implementation / Image Stage | `optional` | Judgment Review | - |
| `p650` | Scene Implementation / Image Stage | `optional` | Generation Ready | `image_generation_requests.md` |

#### p410 Scene Completion

- status: `done`

#### p640 Judgment Review

- status: `awaiting_approval`

#### p650 Generation Ready

- status: `pending`
""",
                encoding="utf-8",
            )

            progress = image_gen.read_run_progress(run_dir)

        self.assertEqual(progress["currentStage"]["code"], "p640")
        self.assertEqual(progress["currentStage"]["state"], "in_progress")
        self.assertEqual(next(slot for slot in progress["slots"] if slot["code"] == "p640")["state"], "in_progress")
        self.assertEqual(next(stage for stage in progress["stages"] if stage["code"] == "p600")["state"], "in_progress")

    def test_read_run_progress_stops_at_pending_frontier_before_stale_later_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "topic=シンデレラ",
                        "status=FAILED",
                        "slot.p660.status=done",
                        "slot.p670.status=pending",
                        "slot.p680.status=failed",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "asset_generation_requests.md").write_text(
                "# Asset Generation Requests\n",
                encoding="utf-8",
            )
            (run_dir / "image_generation_requests.md").write_text(
                "# Image Generation Requests\n",
                encoding="utf-8",
            )
            (run_dir / "p000_index.md").write_text(
                """# Run Index

## Stage Table

| P# | Stage | Current State |
| --- | --- | --- |
| `p000` | Run Entrance | `always_available` |
| `p600` | Scene Implementation / Image Stage | `failed` |
| `p800` | Video Stage | `not_started` |

## Fixed Slot Contract

| Slot | Stage | Default Requirement | Purpose | Planned Artifacts |
| --- | --- | --- | --- | --- |
| `p660` | Scene Implementation / Image Stage | `required` | Image Generation | - |
| `p670` | Scene Implementation / Image Stage | `required` | Image QA | - |
| `p680` | Scene Implementation / Image Stage | `required` | Image Handoff | - |

#### p660 Image Generation

- status: `done`

#### p670 Image QA

- status: `pending`

#### p680 Image Handoff

- status: `failed`
""",
                encoding="utf-8",
            )

            progress = image_gen.read_run_progress(run_dir)

        self.assertEqual(
            progress["currentStage"],
            {"code": "p670", "label": "Image QA", "state": "pending"},
        )

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

    def test_generate_image_request_bound_v2_uses_transcript_saved_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            generated = root / "app_server_saved.png"
            generated.write_bytes(PNG_BYTES)
            reference = run_dir / "ref.png"
            reference.write_bytes(PNG_BYTES)
            client = CodexAppServerClient(cwd=root)

            async def fake_start_thread(**_kwargs):
                return "thread-1"

            async def fake_run_turn(**_kwargs):
                return [
                    {"method": "turn/started", "params": {"turn": {"id": "turn-1"}}},
                    {"id": "image-item-1", "type": "imageGeneration", "savedPath": str(generated), "status": "completed"},
                    {"method": "turn/completed", "params": {"turnId": "turn-1"}},
                ]

            client.start_thread = fake_start_thread  # type: ignore[method-assign]
            client.run_turn = fake_run_turn  # type: ignore[method-assign]

            result = asyncio.run(
                client.generate_image(
                    prompt="prompt",
                    output_path=run_dir / "candidate.png",
                    reference_images=[reference],
                    item_id="scene1",
                    run_dir=run_dir,
                    generation_job_id="job-1",
                    allow_generated_images_fallback=False,
                )
            )

        self.assertEqual(result.saved_path, generated)
        self.assertEqual(result.source, "app_server")
        self.assertEqual(result.generation_job_id, "job-1")
        self.assertEqual(result.item_id, "scene1")
        self.assertEqual(result.turn_id, "turn-1")
        self.assertEqual(result.prompt_sha256, hashlib.sha256(b"prompt").hexdigest())
        self.assertEqual(result.reference_sha256s, [hashlib.sha256(PNG_BYTES).hexdigest()])
        self.assertEqual(result.image_generation_item_id, "image-item-1")
        self.assertEqual(result.image_generation_item_count, 1)
        self.assertTrue(result.provenance_authoritative)

    def test_generate_image_request_bound_v2_rejects_multiple_distinct_image_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            first = root / "first.png"
            second = root / "second.png"
            first.write_bytes(PNG_BYTES)
            second.write_bytes(PNG_BYTES)
            client = CodexAppServerClient(cwd=root)

            async def fake_start_thread(**_kwargs):
                return "thread-1"

            async def fake_run_turn(**_kwargs):
                return [
                    {"method": "turn/started", "params": {"turn": {"id": "turn-1"}}},
                    {"id": "image-a", "type": "imageGeneration", "savedPath": str(first), "status": "completed"},
                    {"id": "image-b", "type": "imageGeneration", "savedPath": str(second), "status": "completed"},
                    {"method": "turn/completed", "params": {"turnId": "turn-1"}},
                ]

            client.start_thread = fake_start_thread  # type: ignore[method-assign]
            client.run_turn = fake_run_turn  # type: ignore[method-assign]

            with self.assertRaisesRegex(CodexAppServerError, "exactly one distinct imageGeneration item"):
                asyncio.run(
                    client.generate_image(
                        prompt="prompt",
                        output_path=run_dir / "candidate.png",
                        reference_images=[],
                        item_id="scene1",
                        run_dir=run_dir,
                        generation_job_id="job-1",
                        allow_generated_images_fallback=False,
                    )
                )

    def test_generate_image_request_bound_v2_deduplicates_repeated_notification_for_same_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            generated = root / "generated.png"
            generated.write_bytes(PNG_BYTES)
            client = CodexAppServerClient(cwd=root)

            async def fake_start_thread(**_kwargs):
                return "thread-1"

            async def fake_run_turn(**_kwargs):
                item = {"id": "image-a", "type": "imageGeneration", "savedPath": str(generated), "status": "completed"}
                return [item, {"method": "item/completed", "params": {"item": dict(item)}}, {"method": "turn/completed", "params": {"turnId": "turn-1"}}]

            client.start_thread = fake_start_thread  # type: ignore[method-assign]
            client.run_turn = fake_run_turn  # type: ignore[method-assign]

            result = asyncio.run(
                client.generate_image(
                    prompt="prompt",
                    output_path=run_dir / "candidate.png",
                    reference_images=[],
                    item_id="scene1",
                    run_dir=run_dir,
                    generation_job_id="job-1",
                    allow_generated_images_fallback=False,
                )
            )

        self.assertEqual(result.saved_path, generated)
        self.assertEqual(result.image_generation_item_id, "image-a")
        self.assertEqual(result.image_generation_item_count, 1)

    def test_generate_image_request_bound_v2_does_not_claim_generated_images_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            codex_home = root / "codex_home"
            generated_dir = codex_home / "generated_images" / "session"
            generated_dir.mkdir(parents=True)
            generated = generated_dir / "generated.png"
            generated.write_bytes(PNG_BYTES)
            client = CodexAppServerClient(cwd=root)

            async def fake_start_thread(**_kwargs):
                return "thread-1"

            async def fake_run_turn(**_kwargs):
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
                        generation_job_id="job-1",
                        allow_generated_images_fallback=False,
                    )
                )

        self.assertIsNone(result.saved_path)
        self.assertEqual(result.source, "app_server")
        self.assertFalse(result.provenance_authoritative)

    def test_codex_app_server_uses_default_home_when_env_missing_and_writable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"TMPDIR": tmp}, clear=False), patch("server.codex_app_server._is_writable_directory", return_value=True):
                os.environ.pop("CODEX_HOME", None)
                client = CodexAppServerClient(cwd=Path(tmp))
                env = client._subprocess_env()

        self.assertIn("CODEX_HOME", env)
        self.assertTrue(Path(env["CODEX_HOME"]).is_dir())
        self.assertEqual(env["CODEX_HOME"], str(Path.home() / ".codex"))

    def test_codex_app_server_discovers_plugin_code_mode_host_when_cli_sibling_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            host = codex_home / "plugins" / ".plugin-appserver" / "codex-code-mode-host"
            host.parent.mkdir(parents=True)
            host.write_bytes(b"host")
            host.chmod(0o755)
            codex_bin = root / "bin" / "codex"
            codex_bin.parent.mkdir()
            codex_bin.write_bytes(b"codex")
            codex_bin.chmod(0o755)

            with (
                patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=True),
                patch("server.codex_app_server.shutil.which", return_value=str(codex_bin)),
            ):
                client = CodexAppServerClient(cwd=root)
                env = client._subprocess_env()

        self.assertEqual(env["CODEX_CODE_MODE_HOST_PATH"], str(host))

    def test_codex_app_server_preserves_explicit_code_mode_host_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            codex_home.mkdir()
            explicit = root / "custom-host"
            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "CODEX_CODE_MODE_HOST_PATH": str(explicit),
                },
                clear=True,
            ):
                client = CodexAppServerClient(cwd=root)
                env = client._subprocess_env()

        self.assertEqual(env["CODEX_CODE_MODE_HOST_PATH"], str(explicit))

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

    def test_frontend_create_cli_helper_persists_stdout_and_stderr_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260606_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            argv: list[str] = []

            class FakeProcess:
                returncode = 0

                async def communicate(self):
                    return b"frontend stdout\n", b"frontend stderr\n"

            async def fake_create_subprocess_exec(*args, **_kwargs):
                argv.extend(str(value) for value in args)
                return FakeProcess()

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.asyncio.create_subprocess_exec", fake_create_subprocess_exec),
            ):
                stdout = asyncio.run(
                    image_gen_app._run_toc_immersive_frontend_cli_helper(
                        topic="桃太郎",
                        source="鬼退治",
                        run_id=run_id,
                        stop_target="p680",
                        target_duration_seconds=1200,
                    )
                )

            self.assertEqual(stdout, "frontend stdout")
            self.assertEqual(argv[argv.index("--target-duration-seconds") + 1], "1200")
            self.assertEqual((run_dir / "logs/frontend_create_cli/stdout.log").read_text(encoding="utf-8"), "frontend stdout\n")
            self.assertEqual((run_dir / "logs/frontend_create_cli/stderr.log").read_text(encoding="utf-8"), "frontend stderr\n")

    def test_frontend_create_cli_helper_passes_world_walk_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "散歩_20260606_1200"
            (root / "output" / run_id).mkdir(parents=True)
            argv: list[str] = []

            class FakeProcess:
                returncode = 0

                async def communicate(self):
                    return b"ok\n", b""

            async def fake_create_subprocess_exec(*args, **_kwargs):
                argv.extend(str(value) for value in args)
                return FakeProcess()

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.asyncio.create_subprocess_exec", fake_create_subprocess_exec),
            ):
                asyncio.run(
                    image_gen_app._run_toc_immersive_frontend_cli_helper(
                        topic="桃太郎の世界観を散歩してみた",
                        run_id=run_id,
                        experience="world_walk",
                        source_run_id="桃太郎_20260606_1100",
                        target_duration_seconds=600,
                    )
                )

        self.assertEqual(argv[argv.index("--experience") + 1], "world_walk")
        self.assertEqual(argv[argv.index("--source-run") + 1], "output/桃太郎_20260606_1100")

    def test_headless_create_route_sends_target_duration(self) -> None:
        module = load_headless_create_module()
        posted_payloads: list[dict[str, Any]] = []

        class FakeResponse:
            def __init__(self, payload: dict[str, Any]):
                self.payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return self.payload

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def post(self, path: str, *, json: dict[str, Any]):
                self.assert_path = path
                posted_payloads.append(json)
                return FakeResponse(
                    {
                        "jobId": "job-1",
                        "runId": "headless-fresh-route-test",
                        "path": "output/headless-fresh-route-test",
                        "status": "running",
                    }
                )

            async def get(self, _path: str):
                return FakeResponse(
                    {
                        "jobId": "job-1",
                        "runId": "headless-fresh-route-test",
                        "path": "output/headless-fresh-route-test",
                        "status": "completed",
                    }
                )

        with patch.object(module.httpx, "AsyncClient", return_value=FakeClient()):
            job = asyncio.run(
                module.create_run_via_frontend_route(
                    title="桃太郎",
                    source="鬼退治",
                    generate_images=False,
                    target_duration_seconds=1200,
                    timeout_seconds=1,
                    poll_interval=0,
                    base_url="http://toc.test",
                )
            )

        self.assertEqual(job["status"], "completed")
        self.assertEqual(posted_payloads[0]["target_duration_seconds"], 1200)

    def test_headless_create_route_uses_storyboard_endpoint_and_contract(self) -> None:
        module = load_headless_create_module()
        posted: list[tuple[str, dict[str, Any]]] = []

        class FakeResponse:
            def __init__(self, payload: dict[str, Any]):
                self.payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return self.payload

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def post(self, path: str, *, json: dict[str, Any]):
                posted.append((path, json))
                return FakeResponse(
                    {
                        "jobId": "storyboard-job",
                        "runId": "headless-storyboard-route-test",
                        "path": "output/headless-storyboard-route-test",
                        "status": "running",
                        "createMode": "scene_storyboard",
                    }
                )

            async def get(self, _path: str):
                return FakeResponse(
                    {
                        "jobId": "storyboard-job",
                        "runId": "headless-storyboard-route-test",
                        "path": "output/headless-storyboard-route-test",
                        "status": "completed",
                        "createMode": "scene_storyboard",
                    }
                )

        with patch.object(module.httpx, "AsyncClient", return_value=FakeClient()):
            job = asyncio.run(
                module.create_run_via_frontend_route(
                    title="桃太郎",
                    source="鬼退治",
                    generate_images=True,
                    create_mode="scene_storyboard",
                    target_duration_seconds=300,
                    timeout_seconds=1,
                    poll_interval=0,
                    base_url="http://toc.test",
                )
            )

        self.assertEqual(job["status"], "completed")
        self.assertEqual(
            posted,
            [
                (
                    "/api/image-gen/runs/create/storyboard",
                    {
                        "title": "桃太郎",
                        "source": "鬼退治",
                        "target_duration_seconds": 300,
                    },
                )
            ],
        )

    def test_headless_storyboard_route_rejects_no_images(self) -> None:
        module = load_headless_create_module()
        with self.assertRaisesRegex(
            ValueError,
            "storyboard create requires image generation",
        ):
            asyncio.run(
                module.create_run_via_frontend_route(
                    title="桃太郎",
                    source="鬼退治",
                    generate_images=False,
                    create_mode="scene_storyboard",
                    target_duration_seconds=300,
                    timeout_seconds=1,
                    poll_interval=0,
                    base_url="http://toc.test",
                )
            )

    def test_headless_create_route_rejects_status_identity_substitution(self) -> None:
        module = load_headless_create_module()

        class FakeResponse:
            def __init__(self, payload: dict[str, Any]):
                self.payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return self.payload

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def post(self, _path: str, *, json: dict[str, Any]):
                return FakeResponse(
                    {
                        "jobId": "job-1",
                        "runId": "run-1",
                        "path": "output/run-1",
                        "status": "running",
                    }
                )

            async def get(self, _path: str):
                return FakeResponse(
                    {
                        "jobId": "job-2",
                        "runId": "run-older",
                        "path": "output/run-older",
                        "status": "completed",
                    }
                )

        with patch.object(module.httpx, "AsyncClient", return_value=FakeClient()):
            with self.assertRaisesRegex(RuntimeError, "jobId"):
                asyncio.run(
                    module.create_run_via_frontend_route(
                        title="桃太郎",
                        source="鬼退治",
                        generate_images=False,
                        target_duration_seconds=300,
                        timeout_seconds=1,
                        poll_interval=0,
                        base_url="http://toc.test",
                    )
                )

    def test_headless_completed_run_path_must_exist_under_output_and_match_run_id(self) -> None:
        module = load_headless_create_module()
        with tempfile.TemporaryDirectory(dir=module.OUTPUT_ROOT) as tmp:
            run_dir = Path(tmp).resolve()
            run_id = run_dir.name
            self.assertEqual(
                module._resolve_completed_run_dir(
                    {
                        "runId": run_id,
                        "path": str(run_dir.relative_to(module.REPO_ROOT)),
                    }
                ),
                run_dir,
            )
            with self.assertRaisesRegex(ValueError, "path/runId mismatch"):
                module._resolve_completed_run_dir(
                    {"runId": "different-run", "path": str(run_dir)}
                )
        with self.assertRaisesRegex(ValueError, "must stay under"):
            module._resolve_completed_run_dir(
                {"runId": "escape", "path": "../escape"}
            )
        with self.assertRaisesRegex(ValueError, "does not exist"):
            module._resolve_completed_run_dir(
                {"runId": "missing-run", "path": "output/missing-run"}
            )
        with tempfile.TemporaryDirectory(dir=module.OUTPUT_ROOT) as parent_tmp:
            nested = Path(parent_tmp) / "nested-run"
            nested.mkdir()
            with self.assertRaisesRegex(ValueError, "path/runId mismatch"):
                module._resolve_completed_run_dir(
                    {"runId": nested.name, "path": str(nested)}
                )

    def test_headless_report_rejects_descendant_symlink_redirection(self) -> None:
        module = load_headless_create_module()
        with tempfile.TemporaryDirectory(prefix="headless_report_run_") as run_tmp, tempfile.TemporaryDirectory(
            prefix="headless_report_external_"
        ) as external_tmp:
            run_dir = Path(run_tmp)
            external_dir = Path(external_tmp)
            sentinel = external_dir / "sentinel.md"
            sentinel.write_text("do not replace", encoding="utf-8")
            (run_dir / "logs").symlink_to(external_dir, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                module._write_report(
                    run_dir=run_dir,
                    job={"jobId": "job", "runId": run_dir.name, "status": "completed"},
                    generate_images=False,
                    assertion_failures=[],
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not replace")

        with tempfile.TemporaryDirectory(prefix="headless_report_file_") as run_tmp, tempfile.TemporaryDirectory(
            prefix="headless_report_target_"
        ) as external_tmp:
            run_dir = Path(run_tmp)
            report_dir = run_dir / "logs" / "regression"
            report_dir.mkdir(parents=True)
            sentinel = Path(external_tmp) / "sentinel.md"
            sentinel.write_text("do not truncate", encoding="utf-8")
            (report_dir / "headless_regression_report.md").symlink_to(sentinel)
            with self.assertRaisesRegex(ValueError, "symlink"):
                module._write_report(
                    run_dir=run_dir,
                    job={"jobId": "job", "runId": run_dir.name, "status": "completed"},
                    generate_images=False,
                    assertion_failures=[],
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not truncate")

    def test_headless_create_requires_initial_identity_and_rejects_replayed_run(self) -> None:
        module = load_headless_create_module()

        class FakeResponse:
            def __init__(self, payload: dict[str, Any]):
                self.payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return self.payload

        class FakeClient:
            def __init__(self, payload: dict[str, Any]):
                self.payload = payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def post(self, _path: str, *, json: dict[str, Any]):
                return FakeResponse(self.payload)

        with patch.object(module.httpx, "AsyncClient", return_value=FakeClient({"jobId": "job-1"})):
            with self.assertRaisesRegex(RuntimeError, "initial runId and path"):
                asyncio.run(
                    module.create_run_via_frontend_route(
                        title="桃太郎",
                        source="鬼退治",
                        generate_images=False,
                        target_duration_seconds=300,
                        timeout_seconds=1,
                        poll_interval=0,
                        base_url="http://toc.test",
                    )
                )

        with tempfile.TemporaryDirectory(dir=module.OUTPUT_ROOT) as existing_tmp:
            existing = Path(existing_tmp)
            payload = {
                "jobId": "job-1",
                "runId": existing.name,
                "path": str(existing.relative_to(module.REPO_ROOT)),
                "status": "running",
            }
            with patch.object(module.httpx, "AsyncClient", return_value=FakeClient(payload)):
                with self.assertRaisesRegex(RuntimeError, "pre-existing"):
                    asyncio.run(
                        module.create_run_via_frontend_route(
                            title="桃太郎",
                            source="鬼退治",
                            generate_images=False,
                            target_duration_seconds=300,
                            timeout_seconds=1,
                            poll_interval=0,
                            base_url="http://toc.test",
                        )
                    )

    def test_headless_cli_passes_target_duration_to_frontend_route(self) -> None:
        module = load_headless_create_module()
        calls: list[dict[str, Any]] = []

        async def fake_create_run(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"jobId": "job-1", "runId": "run-1", "path": "output/run-1", "status": "completed"}

        with (
            patch.object(module, "create_run_via_frontend_route", fake_create_run),
            patch.object(
                module,
                "_resolve_completed_run_dir",
                return_value=Path("output/run-1"),
            ),
            patch.object(module, "_write_report", return_value=Path("report.md")),
            patch.object(
                sys,
                "argv",
                [
                    "toc-create-run-headless.py",
                    "--title",
                    "桃太郎",
                    "--target-duration-seconds",
                    "900",
                    "--assert-profile",
                    "none",
                ],
            ),
        ):
            exit_code = module.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0]["target_duration_seconds"], 900)

    def test_headless_cli_passes_storyboard_mode_to_frontend_route(self) -> None:
        module = load_headless_create_module()
        calls: list[dict[str, Any]] = []

        async def fake_create_run(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {
                "jobId": "job-1",
                "runId": "run-1",
                "path": "output/run-1",
                "status": "completed",
                "createMode": "scene_storyboard",
            }

        with (
            patch.object(
                module,
                "create_run_via_frontend_route",
                fake_create_run,
            ),
            patch.object(
                module,
                "_resolve_completed_run_dir",
                return_value=Path("output/run-1"),
            ),
            patch.object(
                module,
                "_check_storyboard_v1",
                return_value=[],
                create=True,
            ),
            patch.object(
                module,
                "_write_report",
                return_value=Path("report.md"),
            ),
            patch.object(
                sys,
                "argv",
                [
                    "toc-create-run-headless.py",
                    "--title",
                    "桃太郎",
                    "--create-mode",
                    "scene_storyboard",
                    "--assert-profile",
                    "storyboard_v1",
                ],
            ),
        ):
            exit_code = module.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0]["create_mode"], "scene_storyboard")

    def test_headless_storyboard_profile_checks_materialized_contract(self) -> None:
        module = load_headless_create_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_storyboard_20260727_1200"
            run_dir = write_valid_p680_artifacts(root, run_id)
            for cut_index in range(1, 4):
                write_test_png(
                    run_dir
                    / "assets"
                    / "scenes"
                    / f"scene10_cut{cut_index}.png"
                )
            with patch("server.image_gen_app.ROOT", root):
                image_gen_app._materialize_scene_storyboard_video_requests(
                    run_id
                )

            failures = module._check_storyboard_v1(run_dir)

        self.assertEqual(failures, [])

    def test_headless_cut_contract_check_ignores_motion_terms_in_debug_only(self) -> None:
        module = load_headless_create_module()
        with tempfile.TemporaryDirectory(prefix="headless_prompt_boundary_") as tmp:
            run_dir = Path(tmp)
            contract = {
                "cut_function": "setup",
                "viewer_contract": {"target_beat": "beat", "visual_proof": "visible proof"},
                "first_frame_contract": {"first_frame_brief": "still frame"},
                "motion_contract": {"motion_brief": "future movement"},
                "narration_contract": {"role": "emotion"},
                "downstream_handoff": {"p600_image": {}, "p800_video": {}},
            }
            manifest = {"scenes": [{"cuts": [{"selector": "scene10_cut01", "cut_contract": contract}]}]}
            # The generic contract must also accept a semantically complete
            # one-scene story; story-specific scene-count checks belong to a
            # story profile, not cut_contract_v2.
            script = {"scenes": [{"scene_id": 1}]}
            (run_dir / "video_manifest.md").write_text(
                "# Manifest\n\n```yaml\n" + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False) + "```\n",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text(
                "# Script\n\n```yaml\n" + yaml.safe_dump(script, allow_unicode=True, sort_keys=False) + "```\n",
                encoding="utf-8",
            )
            requests_path = run_dir / "image_generation_requests.md"
            requests_path.write_text(
                "\n".join(
                    [
                        "# Requests",
                        "```debug_prompt_source",
                        "derived_from: [cut_contract.motion_contract]",
                        "nonvisual_terms_to_exclude_from_prompt: [motion_brief]",
                        "```",
                        "```api_prompt",
                        "subject: シンデレラ",
                        "visible_action: 灰の台所で手を止める",
                        "```",
                    ]
                ),
                encoding="utf-8",
            )

            clean_failures = module._check_cut_contract_v2(run_dir, generate_images=False)
            requests_path.write_text(
                requests_path.read_text(encoding="utf-8").replace(
                    "visible_action: 灰の台所で手を止める",
                    "motion_brief: 未来の動き",
                ),
                encoding="utf-8",
            )
            leaked_failures = module._check_cut_contract_v2(run_dir, generate_images=False)

        self.assertNotIn(
            "image_generation_requests.md leaks motion_brief/motion_contract into image prompts",
            clean_failures,
        )
        self.assertFalse(
            any("too few scenes" in failure for failure in clean_failures),
            clean_failures,
        )
        self.assertIn(
            "image_generation_requests.md leaks motion_brief/motion_contract into image prompts",
            leaked_failures,
        )

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

    def test_default_app_server_model_uses_latest_approved_model(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(default_app_server_model(), "gpt-5.6-sol")

    def test_default_app_server_model_can_be_overridden(self) -> None:
        with patch.dict(os.environ, {"TOC_CODEX_APP_SERVER_MODEL": "gpt-5.5"}):
            self.assertEqual(default_app_server_model(), "gpt-5.5")

    def test_minimum_app_server_version_defaults_to_upgraded_cli(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(minimum_app_server_version(), "0.144.0")

    def test_minimum_app_server_version_can_be_overridden(self) -> None:
        with patch.dict(os.environ, {"TOC_CODEX_APP_SERVER_MIN_VERSION": "0.150.1"}):
            self.assertEqual(minimum_app_server_version(), "0.150.1")

    def test_parse_codex_cli_version_accepts_release_and_prerelease_output(self) -> None:
        self.assertEqual(parse_codex_cli_version("codex-cli 0.144.0"), "0.144.0")
        self.assertEqual(parse_codex_cli_version("codex-cli 0.144.0-alpha.4"), "0.144.0-alpha.4")
        self.assertEqual(parse_codex_cli_version("codex-cli 0.144.0+build.7"), "0.144.0+build.7")

    def test_parse_codex_cli_version_rejects_unknown_output(self) -> None:
        with self.assertRaisesRegex(CodexAppServerError, "Could not parse Codex CLI version"):
            parse_codex_cli_version("runtime 9.9.9; codex development build")

    def test_read_codex_cli_version_uses_cli_version_command(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["/opt/homebrew/bin/codex", "--version"],
            returncode=0,
            stdout="codex-cli 0.144.0\n",
            stderr="",
        )
        with patch("server.codex_app_server.subprocess.run", return_value=completed) as run:
            version = _read_codex_cli_version("/opt/homebrew/bin/codex")

        self.assertEqual(version, "0.144.0")
        run.assert_called_once_with(
            ["/opt/homebrew/bin/codex", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_read_codex_cli_version_reports_command_failure(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["/broken/codex", "--version"],
            returncode=2,
            stdout="",
            stderr="broken binary",
        )
        with patch("server.codex_app_server.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(CodexAppServerError, "version check failed") as raised:
                _read_codex_cli_version("/broken/codex")

        self.assertEqual(raised.exception.diagnostics["returncode"], 2)
        self.assertEqual(raised.exception.diagnostics["codexVersionOutput"], "broken binary")

    def test_read_codex_cli_version_reports_launch_failure(self) -> None:
        with patch("server.codex_app_server.subprocess.run", side_effect=OSError("permission denied")):
            with self.assertRaisesRegex(CodexAppServerError, "Could not execute Codex CLI version check") as raised:
                _read_codex_cli_version("/broken/codex")

        self.assertEqual(raised.exception.diagnostics["codexBinPath"], "/broken/codex")

    def test_codex_app_server_preflight_rejects_outdated_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = CodexAppServerClient(cwd=Path(tmp))
            with (
                patch.dict(
                    os.environ,
                    {
                        "CODEX_HOME": tmp,
                        "TOC_CODEX_APP_SERVER_PREFLIGHT_NETWORK": "0",
                    },
                    clear=True,
                ),
                patch("server.codex_app_server.shutil.which", return_value="/opt/homebrew/bin/codex"),
                patch("server.codex_app_server._read_codex_cli_version", return_value="0.143.9"),
            ):
                with self.assertRaisesRegex(CodexAppServerError, "requires Codex CLI >= 0.144.0") as raised:
                    client.preflight_runtime()

        self.assertEqual(raised.exception.diagnostics["codexVersion"], "0.143.9")
        self.assertEqual(raised.exception.diagnostics["minimumCodexVersion"], "0.144.0")
        self.assertEqual(raised.exception.diagnostics["model"], "gpt-5.6-sol")

    def test_codex_app_server_preflight_rejects_prerelease_of_stable_minimum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = CodexAppServerClient(cwd=Path(tmp))
            with (
                patch.dict(
                    os.environ,
                    {
                        "CODEX_HOME": tmp,
                        "TOC_CODEX_APP_SERVER_PREFLIGHT_NETWORK": "0",
                    },
                    clear=True,
                ),
                patch("server.codex_app_server.shutil.which", return_value="/Applications/ChatGPT.app/codex"),
                patch("server.codex_app_server._read_codex_cli_version", return_value="0.144.0-alpha.4"),
            ):
                with self.assertRaisesRegex(CodexAppServerError, "requires Codex CLI >= 0.144.0"):
                    client.preflight_runtime()

    def test_codex_app_server_preflight_accepts_build_metadata_for_stable_minimum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = CodexAppServerClient(cwd=Path(tmp))
            with (
                patch.dict(
                    os.environ,
                    {
                        "CODEX_HOME": tmp,
                        "TOC_CODEX_APP_SERVER_PREFLIGHT_NETWORK": "0",
                    },
                    clear=True,
                ),
                patch("server.codex_app_server.shutil.which", return_value="/opt/homebrew/bin/codex"),
                patch("server.codex_app_server._read_codex_cli_version", return_value="0.144.0+build.7"),
            ):
                checks = client.preflight_runtime()

        self.assertEqual(checks["codexVersion"], "0.144.0+build.7")

    def test_codex_app_server_runtime_contract_records_version_and_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = CodexAppServerClient(cwd=Path(tmp))
            with (
                patch.dict(
                    os.environ,
                    {
                        "CODEX_HOME": tmp,
                        "TOC_CODEX_APP_SERVER_PREFLIGHT_NETWORK": "0",
                    },
                    clear=True,
                ),
                patch("server.codex_app_server.shutil.which", return_value="/opt/homebrew/bin/codex"),
                patch("server.codex_app_server._read_codex_cli_version", return_value="0.144.0"),
            ):
                checks = client.preflight_runtime()
                contract = client.runtime_contract().as_dict()

        self.assertEqual(checks["codexVersion"], "0.144.0")
        self.assertEqual(checks["minimumCodexVersion"], "0.144.0")
        self.assertEqual(checks["model"], "gpt-5.6-sol")
        self.assertEqual(contract["codexVersion"], "0.144.0")
        self.assertEqual(contract["minimumCodexVersion"], "0.144.0")
        self.assertEqual(contract["model"], "gpt-5.6-sol")

    def test_start_thread_sends_default_model_and_records_explicit_override(self) -> None:
        async def run(model: str | None, cwd: Path) -> tuple[dict[str, Any], dict[str, Any]]:
            client = CodexAppServerClient(cwd=cwd)
            request_params: dict[str, Any] = {}

            async def fake_request(method, params=None):
                client.preflight_runtime(require_network=False)
                self.assertEqual(method, "thread/start")
                request_params.update(params or {})
                return {"thread": {"id": "thread-1"}}

            client.request = fake_request  # type: ignore[method-assign]
            await client.start_thread(model=model)
            return request_params, client.runtime_contract().as_dict()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("server.codex_app_server.shutil.which", return_value="/opt/homebrew/bin/codex"),
            patch("server.codex_app_server._read_codex_cli_version", return_value="0.144.0"),
        ):
            cwd = Path(tmp)
            with patch.dict(os.environ, {"CODEX_HOME": tmp}, clear=True):
                default_params, _ = asyncio.run(run(None, cwd))
            with patch.dict(
                os.environ,
                {"CODEX_HOME": tmp, "TOC_CODEX_APP_SERVER_MODEL": "gpt-5.6-sol"},
                clear=True,
            ):
                explicit_params, explicit_contract = asyncio.run(run("gpt-5.5", cwd))

        self.assertEqual(default_params["model"], "gpt-5.6-sol")
        self.assertEqual(explicit_params["model"], "gpt-5.5")
        self.assertEqual(explicit_contract["model"], "gpt-5.5")

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

    def test_parse_request_markdown_prefers_api_prompt_over_debug_blocks(self) -> None:
        request_text = """# Image Generation Requests

## scene10_cut1

- output: `assets/scenes/scene10_cut01.png`
- prompt_policy_version: `image_api_prompt_v1`
- references: `[]`

```debug_prompt_source
first_frame_visual_plan:
  source_event_beat_id: scene01_event_setup
```

```text
debug text must not be sent
```

```api_prompt
[shot / 画角]
shot_role: insert
shot_scale: closeup
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            items = image_gen.parse_request_markdown(request_text, kind="scene", run_dir=Path(tmp))

        self.assertEqual(items[0].prompt, "[shot / 画角]\nshot_role: insert\nshot_scale: closeup")
        self.assertEqual(items[0].prompt_policy_version, "image_api_prompt_v1")
        self.assertNotIn("first_frame_visual_plan", items[0].prompt)
        self.assertNotIn("debug text", items[0].prompt)

    def test_parse_request_markdown_fails_v1_when_api_prompt_missing(self) -> None:
        request_text = """# Image Generation Requests

## scene10_cut1

- output: `assets/scenes/scene10_cut01.png`
- prompt_policy_version: `image_api_prompt_v1`

```text
legacy prompt must not be used for v1
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "api_prompt_missing_for_new_prompt_policy"):
                image_gen.parse_request_markdown(request_text, kind="scene", run_dir=Path(tmp))

    def test_image_debug_log_separates_api_prompt_from_debug_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            destination = run_dir / "assets" / "scenes" / "scene10_cut01.png"
            destination.parent.mkdir(parents=True)

            log_path = image_gen.write_app_server_image_debug_log(
                run_dir=run_dir,
                item_id="scene10_cut1",
                index=1,
                destination=destination,
                references=[],
                prompt="[shot / 画角]\nshot_role: insert",
                kind="scene",
                prompt_policy_version="image_api_prompt_v1",
                debug_prompt_source={"first_frame_visual_plan": {"schema_version": "first_frame_visual_plan_v1"}, "send_to_api": False},
            )

            log_text = log_path.read_text(encoding="utf-8")
            payload = json.loads(log_text)

        self.assertEqual(payload["prompt"], "[shot / 画角]\nshot_role: insert")
        self.assertEqual(payload["apiPromptPolicyVersion"], "image_api_prompt_v1")
        self.assertEqual(payload["debugPromptSource"]["send_to_api"], False)
        self.assertNotIn("first_frame_visual_plan", payload["prompt"])

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

    def test_v1_prompt_update_replaces_named_api_prompt_only(self) -> None:
        request_text = """# Image Generation Requests

## scene1_cut1

- prompt_policy_version: `image_api_prompt_v1`
- output: `assets/scenes/scene01.png`

```debug_prompt_source
first_frame_visual_plan:
  visible_moment: keep this debug block
```

```api_prompt
old provider prompt
```

## scene2_cut1

- prompt_policy_version: `image_api_prompt_v1`
- output: `assets/scenes/scene02.png`

```api_prompt
keep scene two
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_requests.md"
            path.write_text(request_text, encoding="utf-8")

            result = image_gen.update_request_prompts(
                run_dir,
                "scene",
                {"scene1_cut1": "new exact provider prompt"},
            )
            updated = path.read_text(encoding="utf-8")

        self.assertEqual(result, {"updated": ["scene1_cut1"], "missing": []})
        self.assertIn("```api_prompt\nnew exact provider prompt\n```", updated)
        self.assertIn("visible_moment: keep this debug block", updated)
        self.assertIn("```api_prompt\nkeep scene two\n```", updated)
        self.assertNotIn("old provider prompt", updated)

    def test_v2_request_loader_uses_matching_snapshot_and_rejects_markdown_drift(self) -> None:
        request_text = """# Image Generation Requests

## scene1_cut1

- tool: `codex_builtin_image`
- prompt_policy_version: `image_api_prompt_v2`
- output: `assets/scenes/scene01.png`
- references: `[]`

```api_prompt
灰色の階段にガラスの靴がある。
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request_path = run_dir / "image_generation_requests.md"
            request_path.write_text(request_text, encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    {
                        "item_id": "scene1_cut1",
                        "destination": "assets/scenes/scene01.png",
                        "prompt": "灰色の階段にガラスの靴がある。",
                        "prompt_policy_version": "image_api_prompt_v2",
                        "compiler_version": "drawable_prompt_compiler_v2",
                        "source_digest": hashlib.sha256(b"first-frame-plan").hexdigest(),
                        "references": [],
                    }
                ],
                source_artifact="image_generation_requests.md",
            )
            write_request_snapshot_atomic(
                run_dir / "image_generation_request_snapshot.json",
                snapshot,
                run_dir=run_dir,
            )

            items = image_gen.load_request_items(run_dir, "scene")
            request_path.write_text(request_text.replace("ガラスの靴", "銀の靴"), encoding="utf-8")
            with self.assertRaisesRegex(ImageRequestSnapshotError, "source_artifact_sha256 mismatch"):
                image_gen.load_request_items(run_dir, "scene")

        self.assertEqual(items[0].prompt, "灰色の階段にガラスの靴がある。")
        self.assertEqual(items[0].request_revision, snapshot.request_revision)
        self.assertEqual(items[0].compiler_version, "drawable_prompt_compiler_v2")

    def test_v2_prompt_update_rejects_direct_edit_and_preserves_snapshot_revision(self) -> None:
        request_text = """# Image Generation Requests

## scene1_cut1

- tool: `codex_builtin_image`
- prompt_policy_version: `image_api_prompt_v2`
- output: `assets/scenes/scene01.png`
- references: `[]`

```api_prompt
old provider prompt
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request_path = run_dir / "image_generation_requests.md"
            request_path.write_text(request_text, encoding="utf-8")
            snapshot_path = run_dir / "image_generation_request_snapshot.json"
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    {
                        "item_id": "scene1_cut1",
                        "destination": "assets/scenes/scene01.png",
                        "prompt": "old provider prompt",
                        "prompt_policy_version": "image_api_prompt_v2",
                        "compiler_version": "drawable_prompt_compiler_v2",
                        "source_digest": hashlib.sha256(b"first-frame-plan").hexdigest(),
                        "references": [],
                    }
                ],
                source_artifact="image_generation_requests.md",
            )
            write_request_snapshot_atomic(snapshot_path, snapshot, run_dir=run_dir)

            original_request_text = request_path.read_text(encoding="utf-8")
            original_snapshot_bytes = snapshot_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "manual_prompt_update_rejected_for_compiled_v2"):
                image_gen.update_request_prompts(
                    run_dir,
                    "scene",
                    {"scene1_cut1": "new exact provider prompt"},
                )
            updated_snapshot = load_request_snapshot(snapshot_path, run_dir=run_dir)
            updated_request_text = request_path.read_text(encoding="utf-8")
            updated_snapshot_bytes = snapshot_path.read_bytes()

        self.assertEqual(updated_request_text, original_request_text)
        self.assertEqual(updated_snapshot_bytes, original_snapshot_bytes)
        self.assertEqual(updated_snapshot.request_revision, snapshot.request_revision)
        self.assertEqual(updated_snapshot.items[0].prompt, "old provider prompt")

    def test_v2_visual_plan_patch_recompiles_without_changing_bindings_or_story_boundary(self) -> None:
        plan = {
            "schema_version": "first_frame_visual_plan_v1",
            "source_grounding": {"source_event_beat_id": "beat-1"},
            "temporal_boundary": {
                "event_fact_visible_in_still": "古い可視瞬間",
                "not_yet_happened_in_still": ["鐘はまだ鳴らない"],
            },
            "subject_binding": {"primary_subject": {"id": "hero-1", "name": "古い主人公"}},
            "reference_binding": {"character_references": ["hero-1"]},
            "character_state_gate": {"costume_state": "古い衣装", "pose": "立つ", "gaze": "扉"},
            "object_visibility_gate": {"objects": []},
            "spatial_composition": {"foreground": "床", "midground": "主人公", "background": "扉"},
            "scene_material_pack": {"light_source": "窓", "light_direction": "左", "dominant_materials": ["木"]},
            "scene_state_progression": {"progression_mode": "suspended_moment"},
        }
        patched, payload = image_gen_app._apply_v2_visual_plan_patch_and_compile(
            plan,
            {
                "event_fact_visible_in_still": "主人公が半分開いた扉へ手を伸ばす",
                "primary_subject_name": "扉へ手を伸ばす主人公",
                "costume_state": "煤けた作業着",
                "foreground": "灰の積もった床",
                "light_source": "細い窓光",
                "dominant_materials": ["灰", "木"],
            },
            character_ids=["hero-1"],
            object_ids=[],
            location_ids=["kitchen-1"],
            references=["assets/characters/hero-1.png"],
            scene_time_of_day="夕方",
        )

        self.assertEqual(patched["source_grounding"], plan["source_grounding"])
        self.assertEqual(patched["reference_binding"], plan["reference_binding"])
        self.assertEqual(patched["subject_binding"]["primary_subject"]["id"], "hero-1")
        self.assertEqual(patched["temporal_boundary"]["not_yet_happened_in_still"], ["鐘はまだ鳴らない"])
        self.assertIn("主人公が半分開いた扉へ手を伸ばす", payload["prompt"])
        self.assertEqual(payload["policy_version"], "image_api_prompt_v2")
        self.assertEqual(payload["drawable_prompt_ir"]["dependencies"]["character_ids"], ["hero-1"])
        self.assertEqual(payload["drawable_prompt_ir"]["dependencies"]["time_of_day"], "夕方")
        self.assertIn("このシーンの時間帯は夕方", payload["prompt"])

    def test_recompile_v2_scene_manifest_updates_plan_and_payload_together(self) -> None:
        plan = {
            "schema_version": "first_frame_visual_plan_v1",
            "source_grounding": {"source_event_beat_id": "beat-1"},
            "temporal_boundary": {
                "event_fact_visible_in_still": "古い瞬間",
                "not_yet_happened_in_still": ["まだ扉を開けない"],
            },
            "subject_binding": {"primary_subject": {"id": "hero-1", "name": "主人公"}},
            "reference_binding": {"character_references": ["hero-1"]},
            "character_state_gate": {"costume_state": "作業着", "pose": "立つ", "gaze": "扉"},
            "object_visibility_gate": {"objects": []},
            "spatial_composition": {"foreground": "床", "midground": "主人公", "background": "扉"},
            "scene_material_pack": {"light_source": "窓", "light_direction": "左", "dominant_materials": ["木"]},
            "scene_state_progression": {"progression_mode": "suspended_moment"},
        }
        _old_plan, old_payload = image_gen_app._apply_v2_visual_plan_patch_and_compile(
            plan,
            {},
            character_ids=["hero-1"],
            object_ids=[],
            location_ids=["room-1"],
            references=["assets/characters/hero-1.png"],
            review_metadata={"shot_design_contract": {"status": "approved"}},
        )
        manifest = {
            "scenes": [
                {
                    "scene_id": "10",
                    "time_of_day": "夜",
                    "cuts": [
                        {
                            "cut_id": "1",
                            "image_generation": {
                                "character_ids": ["hero-1"],
                                "object_ids": [],
                                "location_ids": ["room-1"],
                                "references": ["assets/characters/hero-1.png"],
                                "first_frame_visual_plan": plan,
                                "api_prompt_payload": old_payload,
                            },
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text("```yaml\n" + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False) + "```\n", encoding="utf-8")
            compiled = image_gen_app._recompile_v2_scene_manifest(
                run_dir,
                {
                    "scene10_cut1": {
                        "expected_plan_hash": image_gen_app._json_hash(plan),
                        "patch": {"event_fact_visible_in_still": "主人公が扉へ手を伸ばす"},
                    }
                },
            )
            updated = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(manifest_path.read_text(encoding="utf-8")))

        image_generation = updated["scenes"][0]["cuts"][0]["image_generation"]
        self.assertEqual(
            image_generation["first_frame_visual_plan"]["temporal_boundary"]["event_fact_visible_in_still"],
            "主人公が扉へ手を伸ばす",
        )
        self.assertEqual(image_generation["api_prompt_payload"], compiled["scene10_cut1"])
        self.assertEqual(
            image_generation["api_prompt_payload"]["shot_design_contract"]["shot_role"],
            "character_action",
        )
        self.assertNotIn(
            "status",
            image_generation["api_prompt_payload"]["shot_design_contract"],
        )
        self.assertEqual(
            image_generation["debug_prompt_source"]["first_frame_visual_plan"],
            image_generation["first_frame_visual_plan"],
        )
        self.assertEqual(
            image_generation["api_prompt_payload"]["drawable_prompt_ir"]["dependencies"]["time_of_day"],
            "夜",
        )
        self.assertIn("このシーンの時間帯は夜", image_generation["api_prompt_payload"]["prompt"])

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

    def test_first_image_retention_is_immutable_and_rehydrates_missing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "sample_run"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            first = root / "first.png"
            later = root / "later.png"
            write_test_png(first, color=(10, 20, 30))
            write_test_png(later, color=(200, 210, 220))
            destination = image_gen.candidate_path(run_dir, "scene1", 1)
            first_bytes = first.read_bytes()

            created = image_gen.retain_first_image(
                first,
                root=root,
                run_id=run_id,
                kind="scene",
                item_id="scene1",
                candidate_index=1,
                destination=destination.relative_to(run_dir).as_posix(),
                provenance={"generationJobId": "job-first", "turnId": "turn-first"},
            )
            retained_before = Path(created["imagePath"]).read_bytes()
            repeated = image_gen.retain_first_image(
                later,
                root=root,
                run_id=run_id,
                kind="scene",
                item_id="scene1",
                candidate_index=2,
                destination=image_gen.candidate_path(run_dir, "scene1", 2).relative_to(run_dir).as_posix(),
                provenance={"generationJobId": "job-later", "turnId": "turn-later"},
            )

            shutil.rmtree(run_dir)
            self.assertTrue(Path(created["imagePath"]).is_file())
            run_dir.mkdir(parents=True)
            restored = image_gen.rehydrate_retained_first_image(
                run_dir,
                root=root,
                kind="scene",
                item_id="scene1",
            )
            self.assertIsNotNone(restored)
            assert restored is not None
            restored_name = restored.name
            restored_bytes = restored.read_bytes()

        self.assertTrue(created["created"])
        self.assertFalse(repeated["created"])
        self.assertEqual(Path(created["imagePath"]), Path(repeated["imagePath"]))
        self.assertEqual(retained_before, first_bytes)
        self.assertEqual(restored_name, "scene1_candidate_01.png")
        self.assertEqual(restored_bytes, retained_before)

    def test_archive_only_run_is_listed_and_requests_restore_retained_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "archived_run"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            source = root / "generated.png"
            write_test_png(source, color=(12, 34, 56))
            source_bytes = source.read_bytes()
            destination = image_gen.candidate_path(run_dir, "scene1_cut1", 1)
            image_gen.retain_first_image(
                source,
                root=root,
                run_id=run_id,
                kind="scene",
                item_id="scene1_cut1",
                candidate_index=1,
                destination=destination.relative_to(run_dir).as_posix(),
            )
            shutil.rmtree(run_dir)

            runs = image_gen.list_runs(root)
            with patch("server.image_gen_app.ROOT", root):
                requests_payload = asyncio.run(image_gen_app.api_requests(run_id=run_id, kind="scene"))
                candidates_payload = asyncio.run(
                    image_gen_app.api_candidates(run_id=run_id, item_id="scene1_cut1", kind="scene")
                )

            restored = destination.read_bytes() if destination.is_file() else None

        archived = next(run for run in runs if run["id"] == run_id)
        self.assertTrue(archived["archiveOnly"])
        self.assertTrue(archived["hasSceneRequests"])
        self.assertEqual(requests_payload["items"][0]["id"], "scene1_cut1")
        self.assertEqual(requests_payload["items"][0]["candidates"][0]["path"], destination.relative_to(run_dir).as_posix())
        self.assertEqual(candidates_payload["candidates"][0]["path"], destination.relative_to(run_dir).as_posix())
        self.assertEqual(restored, source_bytes)

    def test_retention_enumeration_rejects_tampered_traversal_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "tampered_run"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            source = root / "generated.png"
            write_test_png(source)
            destination = image_gen.candidate_path(run_dir, "scene1", 1)
            retained = image_gen.retain_first_image(
                source,
                root=root,
                run_id=run_id,
                kind="scene",
                item_id="scene1",
                candidate_index=1,
                destination=destination.relative_to(run_dir).as_posix(),
            )
            receipt = Path(retained["imagePath"]).parent / "receipt.json"
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            payload["destination"] = "../../outside.png"
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            shutil.rmtree(run_dir)

            records = image_gen.list_first_image_retentions(root=root, run_id=run_id)
            restored = image_gen.restore_first_image_retention_run(run_id, root=root)

        self.assertEqual(records, [])
        self.assertIsNone(restored)

    def test_archive_restore_does_not_overwrite_an_unrelated_existing_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "same_name"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            retained_source = root / "retained.png"
            write_test_png(retained_source, color=(10, 20, 30))
            destination = image_gen.candidate_path(run_dir, "scene1", 1)
            image_gen.retain_first_image(
                retained_source,
                root=root,
                run_id=run_id,
                kind="scene",
                item_id="scene1",
                candidate_index=1,
                destination=destination.relative_to(run_dir).as_posix(),
            )
            shutil.rmtree(run_dir)

            run_dir.mkdir(parents=True)
            unrelated = run_dir / "unrelated.txt"
            unrelated.write_text("keep", encoding="utf-8")
            unrelated_candidate = image_gen.candidate_path(run_dir, "scene1", 1)
            write_test_png(unrelated_candidate, color=(220, 210, 200))
            unrelated_bytes = unrelated_candidate.read_bytes()

            restored = image_gen.restore_first_image_retention_run(run_id, root=root)
            unrelated_text_after = unrelated.read_text(encoding="utf-8")
            unrelated_bytes_after = unrelated_candidate.read_bytes()

        self.assertIsNone(restored)
        self.assertEqual(unrelated_text_after, "keep")
        self.assertEqual(unrelated_bytes_after, unrelated_bytes)

    def test_candidate_dir_rejects_dot_segment_item_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            with self.assertRaises(ValueError):
                image_gen.candidate_dir(run_dir, "..")

    def test_candidate_import_never_overwrites_the_first_existing_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            first = run_dir / "assets/test/image_gen_candidates/scene1/candidate_01.png"
            first.parent.mkdir(parents=True)
            write_test_png(first, color=(10, 20, 30))
            first_bytes = first.read_bytes()
            generated = run_dir / "generated.png"
            write_test_png(generated, color=(200, 210, 220))
            generated_bytes = generated.read_bytes()

            imported, actual_index = image_gen.copy_saved_image_to_new_candidate(
                generated,
                run_dir=run_dir,
                item_id="scene1",
                requested_index=1,
            )

            persisted_first = first.read_bytes()
            imported_bytes = imported.read_bytes()

        self.assertEqual(actual_index, 2)
        self.assertEqual(imported.name, "scene1_candidate_02.png")
        self.assertEqual(persisted_first, first_bytes)
        self.assertEqual(imported_bytes, generated_bytes)

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

    def test_api_requests_rehydrates_first_image_retained_outside_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "sample_run"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## scene1

- tool: `codex_builtin_image`
- output: `assets/scenes/scene1.png`
- references: `[]`

```text
scene one
```
""",
                encoding="utf-8",
            )
            source = root / "generated.png"
            write_test_png(source)
            source_bytes = source.read_bytes()
            destination = image_gen.candidate_path(run_dir, "scene1", 1)
            image_gen.retain_first_image(
                source,
                root=root,
                run_id=run_id,
                kind="scene",
                item_id="scene1",
                candidate_index=1,
                destination=destination.relative_to(run_dir).as_posix(),
            )

            with patch("server.image_gen_app.ROOT", root):
                payload = asyncio.run(image_gen_app.api_requests(run_id=run_id, kind="scene"))

            restored = destination.read_bytes() if destination.exists() else None

        self.assertEqual(payload["items"][0]["candidates"][0]["path"], destination.relative_to(run_dir).as_posix())
        self.assertEqual(restored, source_bytes)

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

    def test_insert_candidate_rejects_symlink_canonical_output_without_touching_upload(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            candidate = image_gen.candidate_path(run_dir, "scene01", 1)
            upload = run_dir / "assets/uploads/user.png"
            output = run_dir / "assets/scenes/scene01.png"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(PNG_BYTES)
            upload.parent.mkdir(parents=True)
            upload.write_bytes(PNG_BYTES + b"user-upload")
            original_upload = upload.read_bytes()
            output.parent.mkdir(parents=True)
            output.symlink_to(upload)

            with self.assertRaisesRegex(ValueError, "symlink"):
                image_gen.insert_candidate(
                    run_dir,
                    candidate,
                    "assets/scenes/scene01.png",
                )

            persisted_upload = upload.read_bytes()

        self.assertEqual(persisted_upload, original_upload)


class ImageGenApiTests(unittest.TestCase):
    def test_current_process_stops_at_failed_slot_and_ignores_stale_later_terminals(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "シンデレラ_20260728_2211"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            statuses = {
                "p110": "done",
                "p120": "done",
                "p130": "done",
                "p210": "done",
                "p220": "done",
                "p230": "done",
                "p310": "done",
                "p320": "done",
                "p330": "done",
                "p410": "failed",
                # These terminal values are stale materialization state and must
                # not make the failed run look as though it reached p640.
                "p420": "done",
                "p430": "awaiting_approval",
                "p440": "done",
                "p450": "done",
                "p510": "done",
                "p520": "done",
                "p530": "done",
                "p540": "awaiting_approval",
                "p550": "done",
                "p560": "done",
                "p570": "awaiting_approval",
                "p610": "done",
                "p620": "done",
                "p630": "awaiting_approval",
                "p640": "awaiting_approval",
            }
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        *(f"slot.{slot}.status={status}" for slot, status in statuses.items()),
                        "runtime.failure.stage=scene_set",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with patch("server.image_gen_app.ROOT", root):
                current = image_gen_app._current_process_number_for_run(run_id)

        self.assertEqual(current, 410)

    def test_current_process_uses_explicit_runtime_failure_stage_mapping(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "シンデレラ_20260728_2211"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "slot.p110.status=done",
                        "slot.p120.status=done",
                        "slot.p130.status=done",
                        "slot.p210.status=done",
                        "slot.p220.status=done",
                        "slot.p230.status=done",
                        "slot.p310.status=done",
                        "slot.p320.status=done",
                        "slot.p330.status=done",
                        # A transport failure may record the runtime stage before
                        # its corresponding slot failure snapshot is appended.
                        "runtime.failure.stage=scene_detail",
                        "slot.p640.status=awaiting_approval",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with patch("server.image_gen_app.ROOT", root):
                current = image_gen_app._current_process_number_for_run(run_id)

        self.assertEqual(current, 410)

    def test_current_process_requires_contiguous_terminal_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260728_2211"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "slot.p110.status=done",
                        "slot.p120.status=pending",
                        "slot.p130.status=done",
                        "slot.p640.status=awaiting_approval",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with patch("server.image_gen_app.ROOT", root):
                current = image_gen_app._current_process_number_for_run(run_id)

        self.assertEqual(current, 110)

    def test_current_process_preserves_valid_p650_and_p680_resume_boundaries(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p650_run_id = "桃太郎_20260728_2211"
            p680_run_id = "浦島太郎_20260728_2211"
            for run_id, final_slot, final_status in (
                (p650_run_id, "p650", "done"),
                (p680_run_id, "p680", "awaiting_approval"),
            ):
                run_dir = root / "output" / run_id
                run_dir.mkdir(parents=True)
                final_index = image_gen_app.P680_FIXED_SLOTS.index(final_slot)
                (run_dir / "state.txt").write_text(
                    "\n".join(
                        [
                            *(
                                f"slot.{slot}.status="
                                + (
                                    final_status
                                    if slot == final_slot
                                    else (
                                        "awaiting_approval"
                                        if slot in image_gen_app.SLOT_AWAITING_APPROVAL_ALLOWED
                                        else "done"
                                    )
                                )
                                for slot in image_gen_app.P680_FIXED_SLOTS[: final_index + 1]
                            ),
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

            with patch("server.image_gen_app.ROOT", root):
                p650_current = image_gen_app._current_process_number_for_run(p650_run_id)
                p680_current = image_gen_app._current_process_number_for_run(p680_run_id)

        self.assertEqual(p650_current, 650)
        self.assertEqual(p680_current, 680)

    def test_current_process_ignores_stale_runtime_failure_after_p650_recovery(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260728_2211"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            p650_index = image_gen_app.P680_FIXED_SLOTS.index("p650")
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        *(
                            f"slot.{slot}.status="
                            + (
                                "awaiting_approval"
                                if slot in image_gen_app.SLOT_AWAITING_APPROVAL_ALLOWED
                                else "done"
                            )
                            for slot in image_gen_app.P680_FIXED_SLOTS[: p650_index + 1]
                        ),
                        # state.txt is append-only, so an older failed attempt
                        # can remain after a successful resume.
                        "runtime.failure.stage=scene_detail",
                        "slot.p660.status=pending",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with patch("server.image_gen_app.ROOT", root):
                current = image_gen_app._current_process_number_for_run(run_id)

        self.assertEqual(current, 650)

    def test_current_process_keeps_failed_p680_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260728_2211"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        *(
                            f"slot.{slot}.status="
                            + (
                                "awaiting_approval"
                                if slot in image_gen_app.SLOT_AWAITING_APPROVAL_ALLOWED
                                else "done"
                            )
                            for slot in image_gen_app.P680_FIXED_SLOTS[:-1]
                        ),
                        "slot.p680.status=failed",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            with patch("server.image_gen_app.ROOT", root):
                current = image_gen_app._current_process_number_for_run(run_id)

        self.assertEqual(current, 670)

    def test_video_prompt_currentness_rejects_blocking_compiler_quality_issues(self) -> None:
        item = image_gen_app.FrontendReviewItem(
            item_id="scene10_cut1",
            kind="scene",
        )
        payload = {
            "quality_issues": [
                {
                    "code": "video_motion_abstract_primary",
                    "blocking": True,
                },
                {
                    "code": "non_blocking_note",
                    "blocking": False,
                },
                {
                    "code": "   ",
                    "blocking": True,
                },
            ]
        }
        target = {"cut": {"video_generation": {"api_prompt_payload": payload}}}

        self.assertEqual(
            image_gen_app._blocking_video_prompt_quality_issue_codes(payload),
            [
                "video_motion_abstract_primary",
                "video_motion_blocking_quality_issue",
            ],
        )

        with (
            patch(
                "server.image_gen_app._read_manifest_data",
                return_value=(Path("video_manifest.md"), "", {}),
            ),
            patch(
                "server.image_gen_app._compile_frontend_video_prompt_payload",
                return_value=(target, payload),
            ),
        ):
            with self.assertRaisesRegex(
                ValueError,
                r"scene10_cut1.*video_motion_abstract_primary.*video_motion_blocking_quality_issue",
            ):
                image_gen_app._assert_video_materialization_current_for_approval(
                    Path("."),
                    [item],
                )

    def test_video_prompt_currentness_rejects_obsolete_ir_schema(self) -> None:
        item = image_gen_app.FrontendReviewItem(
            item_id="scene10_cut1",
            kind="scene",
        )
        current_payload = {
            "policy_version": image_gen_app.VIDEO_API_PROMPT_POLICY_VERSION,
            "compiler_version": image_gen_app.VIDEO_PROMPT_COMPILER_VERSION,
            "projection_registry_version": (
                image_gen_app.VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION
            ),
            "prompt": REVIEWABLE_VIDEO_PROMPT,
            "negative_prompt": "",
            "sha256": "prompt-hash",
            "source_digest": "source-digest",
            "provider_request_binding": {},
            "video_prompt_ir": {
                "schema_version": image_gen_app.VIDEO_PROMPT_IR_SCHEMA_VERSION
            },
        }
        stored_payload = json.loads(json.dumps(current_payload))
        stored_payload["video_prompt_ir"]["schema_version"] = (
            "obsolete_video_prompt_ir"
        )
        target = {
            "cut": {
                "video_generation": {"api_prompt_payload": stored_payload}
            }
        }

        with (
            patch(
                "server.image_gen_app._read_manifest_data",
                return_value=(Path("video_manifest.md"), "", {}),
            ),
            patch(
                "server.image_gen_app._compile_frontend_video_prompt_payload",
                return_value=(target, current_payload),
            ),
        ):
            with self.assertRaisesRegex(
                ValueError,
                r"scene10_cut1\.video_prompt_ir\.schema_version",
            ):
                image_gen_app._assert_video_materialization_current_for_approval(
                    Path("."),
                    [item],
                )

    def test_video_generation_endpoints_reject_nested_blocking_quality_issue(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            mark_manifest_narration_ready(run_dir)

            with (
                patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}),
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._require_narration_ready_for_video",
                    return_value={"ready": True},
                ),
            ):
                with TestClient(app) as client:
                    created = client.post(
                        "/api/image-gen/video-prompts/create",
                        json={
                            "run_id": "sample_run",
                            "approve_for_generation": True,
                            "items": [
                                {
                                    "item_id": "scene10_cut1",
                                    "kind": "scene",
                                    "output": "assets/scenes/scene10_cut1.png",
                                    "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                    "video_first_reference": "assets/characters/hero.png",
                                }
                            ],
                        },
                    )
                    self.assertEqual(created.status_code, 200, created.text)

                    manifest = yaml.safe_load(
                        image_gen_app._extract_manifest_yaml_text(
                            (run_dir / "video_manifest.md").read_text(
                                encoding="utf-8"
                            )
                        )
                    )
                    stored_payload = manifest["scenes"][0]["cuts"][0][
                        "video_generation"
                    ]["api_prompt_payload"]
                    blocking_payload = json.loads(json.dumps(stored_payload))
                    blocking_payload["quality_issues"] = []
                    blocking_payload.setdefault("video_prompt_ir", {})[
                        "quality_issues"
                    ] = [
                        {
                            "code": "video_motion_abstract_primary",
                            "blocking": True,
                        }
                    ]
                    request_item = {
                        "item_id": "scene10_cut1",
                        "prompt": REVIEWABLE_VIDEO_PROMPT,
                        "first_reference": "assets/characters/hero.png",
                        "candidate_count": 1,
                    }

                    with (
                        patch(
                            "server.image_gen_app._compile_frontend_video_prompt_payload",
                            return_value=({}, blocking_payload),
                        ),
                        patch(
                            "server.image_gen_app._generate_video_candidates",
                            new_callable=AsyncMock,
                        ) as generate,
                    ):
                        single = client.post(
                            "/api/image-gen/video-generate",
                            json={"run_id": "sample_run", **request_item},
                        )
                        bulk = client.post(
                            "/api/image-gen/video-generate-bulk",
                            json={
                                "run_id": "sample_run",
                                "concurrency": 1,
                                "items": [request_item],
                            },
                        )

                    manifest_path = run_dir / "video_manifest.md"
                    manifest_text = manifest_path.read_text(encoding="utf-8")
                    stored_payload["quality_issues"] = []
                    stored_payload.setdefault("video_prompt_ir", {})[
                        "quality_issues"
                    ] = [
                        {
                            "code": "video_motion_abstract_end_state",
                            "blocking": True,
                        }
                    ]
                    image_gen_app._write_manifest_data(
                        manifest_path,
                        manifest_text,
                        manifest,
                    )
                    with patch(
                        "server.image_gen_app._generate_video_candidates",
                        new_callable=AsyncMock,
                    ) as persisted_generate:
                        persisted = client.post(
                            "/api/image-gen/video-generate",
                            json={"run_id": "sample_run", **request_item},
                        )

            self.assertEqual(single.status_code, 409, single.text)
            self.assertEqual(bulk.status_code, 409, bulk.text)
            self.assertEqual(persisted.status_code, 409, persisted.text)
            self.assertIn("scene10_cut1", single.text)
            self.assertIn("video_motion_abstract_primary", single.text)
            self.assertIn("scene10_cut1", bulk.text)
            self.assertIn("video_motion_abstract_primary", bulk.text)
            self.assertIn("scene10_cut1", persisted.text)
            self.assertIn("video_motion_abstract_end_state", persisted.text)
            generate.assert_not_called()
            persisted_generate.assert_not_called()

    def test_video_generation_endpoints_reject_obsolete_projection_and_ir_versions(
        self,
    ) -> None:
        cases = (
            ("projection_registry_version", "projection_registry_version"),
            ("video_prompt_ir", "video_prompt_ir.schema_version"),
        )
        for mutation, expected_field in cases:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                run_dir = write_valid_p650_artifacts(root, "sample_run")
                mark_manifest_narration_ready(run_dir)

                with (
                    patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}),
                    patch("server.image_gen_app.ROOT", root),
                    patch(
                        "server.image_gen_app._require_narration_ready_for_video",
                        return_value={"ready": True},
                    ),
                ):
                    with TestClient(app) as client:
                        created = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "assets/characters/hero.png",
                                    }
                                ],
                            },
                        )
                        self.assertEqual(created.status_code, 200, created.text)

                        manifest_path = run_dir / "video_manifest.md"
                        manifest_text = manifest_path.read_text(encoding="utf-8")
                        manifest = yaml.safe_load(
                            image_gen_app._extract_manifest_yaml_text(
                                manifest_text
                            )
                        )
                        payload = manifest["scenes"][0]["cuts"][0][
                            "video_generation"
                        ]["api_prompt_payload"]
                        if mutation == "projection_registry_version":
                            payload["projection_registry_version"] = (
                                "obsolete_projection_registry"
                            )
                        else:
                            payload["video_prompt_ir"]["schema_version"] = (
                                "obsolete_video_prompt_ir"
                            )
                        image_gen_app._write_manifest_data(
                            manifest_path,
                            manifest_text,
                            manifest,
                        )
                        request_item = {
                            "item_id": "scene10_cut1",
                            "prompt": REVIEWABLE_VIDEO_PROMPT,
                            "first_reference": "assets/characters/hero.png",
                            "candidate_count": 1,
                        }

                        with patch(
                            "server.image_gen_app._generate_video_candidates",
                            new_callable=AsyncMock,
                        ) as generate:
                            single = client.post(
                                "/api/image-gen/video-generate",
                                json={"run_id": "sample_run", **request_item},
                            )
                            bulk = client.post(
                                "/api/image-gen/video-generate-bulk",
                                json={
                                    "run_id": "sample_run",
                                    "concurrency": 1,
                                    "items": [request_item],
                                },
                            )

                self.assertEqual(single.status_code, 409, single.text)
                self.assertEqual(bulk.status_code, 409, bulk.text)
                self.assertIn(expected_field, single.text)
                self.assertIn(expected_field, bulk.text)
                generate.assert_not_called()

    def setUp(self) -> None:
        image_gen_app._create_jobs.clear()
        self.video_semantic_review_patcher = patch(
            "server.image_gen_app._run_video_prompt_semantic_review_before_approval",
            new_callable=AsyncMock,
        )
        self.video_semantic_review_mock = self.video_semantic_review_patcher.start()
        self.video_semantic_recheck_patcher = patch(
            "server.image_gen_app._assert_video_prompt_semantic_review_is_current",
        )
        self.video_semantic_recheck_mock = (
            self.video_semantic_recheck_patcher.start()
        )

    def tearDown(self) -> None:
        self.video_semantic_recheck_patcher.stop()
        self.video_semantic_review_patcher.stop()
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

    def test_create_run_endpoints_reject_target_duration_outside_supported_range(self) -> None:
        def fake_run_create_job(*_args: Any, **_kwargs: Any):
            async def noop() -> None:
                return None

            return noop()

        for endpoint in ("/api/image-gen/runs/create", "/api/image-gen/runs/create/storyboard"):
            for target_duration_seconds in (299, 1201, "300", 300.0):
                with self.subTest(endpoint=endpoint, target_duration_seconds=target_duration_seconds):
                    with tempfile.TemporaryDirectory() as tmp:
                        with (
                            patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}),
                            patch("server.image_gen_app.ROOT", Path(tmp)),
                            patch("server.image_gen_app._create_jobs", {}),
                            patch("server.image_gen_app._run_create_job", fake_run_create_job),
                        ):
                            with TestClient(app) as client:
                                response = client.post(
                                    endpoint,
                                    json={"title": "桃太郎", "target_duration_seconds": target_duration_seconds},
                                )
                        self.assertEqual(response.status_code, 422)

    def test_runs_endpoint_lists_output_folders(self) -> None:
        with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
            with TestClient(app) as client:
                response = client.get("/api/image-gen/runs")

        self.assertEqual(response.status_code, 200)
        self.assertIn("runs", response.json())

    def test_world_walk_sources_endpoint_lists_only_completed_story_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_p650_artifacts(root, "桃太郎_20260509_1100")
            incomplete = root / "output" / "scratch_20260509_1100"
            (incomplete / "assets").mkdir(parents=True)
            (incomplete / "story.md").write_text("# scaffold\n", encoding="utf-8")

            with (
                patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}),
                patch("server.image_gen_app.ROOT", root),
            ):
                with TestClient(app) as client:
                    response = client.get("/api/image-gen/runs/world-walk-sources")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["sources"],
            [
                {
                    "id": "桃太郎_20260509_1100",
                    "title": "桃太郎",
                    "worldWalkTitle": "桃太郎の世界観を散歩してみた",
                    "path": "output/桃太郎_20260509_1100",
                    "hasAssetRequests": True,
                    "hasSceneRequests": True,
                }
            ],
        )

    def test_create_world_walk_endpoint_uses_existing_job_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_p650_artifacts(root, "桃太郎_20260509_1100")
            scheduled: list[dict[str, Any]] = []

            def fake_world_walk_job(*_args: Any, **kwargs: Any):
                scheduled.append(kwargs)

                async def noop() -> None:
                    return None

                return noop()

            with (
                patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}),
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._create_jobs", {}),
                patch("server.image_gen_app._run_world_walk_create_job", fake_world_walk_job),
                patch("server.image_gen_app._acquire_run_execution_lease", new_callable=AsyncMock),
                patch("server.image_gen_app._create_process_record_best_effort", return_value=None),
            ):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/image-gen/runs/create-world-walk",
                        json={
                            "source_run_id": "桃太郎_20260509_1100",
                            "target_duration_seconds": 600,
                        },
                    )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["createMode"], "world_walk")
        self.assertEqual(payload["sourceRunId"], "桃太郎_20260509_1100")
        self.assertEqual(payload["targetDurationSeconds"], 600)
        self.assertTrue(payload["runId"].startswith("桃太郎の世界観を散歩してみた_"))
        self.assertEqual(scheduled[0]["source_run_id"], "桃太郎_20260509_1100")
        self.assertEqual(scheduled[0]["target_duration_seconds"], 600)

    def test_create_world_walk_endpoint_rejects_invalid_or_incomplete_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            partial = root / "output" / "partial_20260509_1100"
            (partial / "assets").mkdir(parents=True)
            (partial / "story.md").write_text("# Partial\n", encoding="utf-8")

            with (
                patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}),
                patch("server.image_gen_app.ROOT", root),
            ):
                with TestClient(app) as client:
                    escaped = client.post(
                        "/api/image-gen/runs/create-world-walk",
                        json={"source_run_id": "../outside"},
                    )
                    partial_response = client.post(
                        "/api/image-gen/runs/create-world-walk",
                        json={"source_run_id": "partial_20260509_1100"},
                    )

        self.assertEqual(escaped.status_code, 400)
        self.assertEqual(partial_response.status_code, 400)
        self.assertIn("source run is not selectable", partial_response.text)

    def test_world_walk_source_rejects_nested_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "output" / "source_20260509_1100"
            outside = root / "outside-story.md"
            outside.write_text("# outside\n", encoding="utf-8")
            (source / "assets").mkdir(parents=True)
            (source / "story.md").symlink_to(outside)

            with (
                patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}),
                patch("server.image_gen_app.ROOT", root),
            ):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/image-gen/runs/create-world-walk",
                        json={"source_run_id": source.name},
                    )

        self.assertEqual(response.status_code, 400)
        self.assertIn("source run is not selectable", response.text)

    def test_world_walk_create_job_runs_direct_frontend_runner_to_p680(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_p650_artifacts(root, "桃太郎_20260509_1100")
            run_id = "桃太郎の世界観を散歩してみた_20260509_1200"
            (root / "output" / run_id).mkdir(parents=True)
            job_id = "world-walk-job"
            job = {
                "jobId": job_id,
                "runId": run_id,
                "status": "running",
                "message": "フォルダを作成中",
            }

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._create_jobs", {job_id: job}),
                patch(
                    "server.image_gen_app._run_toc_immersive_frontend_cli_helper",
                    new_callable=AsyncMock,
                ) as run_frontend,
                patch(
                    "server.image_gen_app._sync_process_current_process",
                    new_callable=AsyncMock,
                ),
                patch("server.image_gen_app._validate_created_run"),
                patch("server.image_gen_app._validate_frontend_create_run"),
                patch(
                    "server.image_gen_app._acquire_run_execution_lease",
                    new_callable=AsyncMock,
                ),
                patch(
                    "server.image_gen_app._release_run_execution_lease",
                    new_callable=AsyncMock,
                ),
            ):
                asyncio.run(
                    image_gen_app._run_world_walk_create_job(
                        job_id,
                        title="桃太郎の世界観を散歩してみた",
                        source_run_id="桃太郎_20260509_1100",
                        run_id=run_id,
                        target_duration_seconds=600,
                    )
                )

        run_frontend.assert_awaited_once_with(
            topic="桃太郎の世界観を散歩してみた",
            run_id=run_id,
            experience="world_walk",
            source_run_id="桃太郎_20260509_1100",
            target_duration_seconds=600,
        )
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["currentProcess"], "p680")

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
        self.assertEqual(create_payload["targetDurationSeconds"], 300)
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
                    "target_duration_seconds": 300,
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
                    "target_duration_seconds": 300,
                    "materialize_only": True,
                }
            ],
        )

    def test_create_run_endpoint_materializes_1200_second_duration_contract(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        output_root = repo_root / "output"
        output_root.mkdir(exist_ok=True)
        runner = load_frontend_runner_module()

        def write_passing_foundation_review(run_dir: Path, stage: str) -> None:
            write_semantic_review_artifacts(run_dir, stage)

        with tempfile.TemporaryDirectory(prefix="frontend_create_1200_", dir=output_root) as tmp:
            run_dir = Path(tmp)
            run_id = run_dir.name
            helper_calls: list[dict[str, object]] = []
            helper_errors: list[str] = []

            async def write_passing_semantic_review(
                _job_id: str,
                *,
                run_dir: Path,
                stage: str,
                image_prompt_provider_ready: bool = True,
            ) -> None:
                write_passing_foundation_review(run_dir, stage)
                if stage == "image_prompt":
                    image_gen_app.append_state_snapshot(
                        run_dir / "state.txt",
                        {
                            "review.image_prompt.request_freeze.status": (
                                "frozen" if image_prompt_provider_ready else "reviewed_draft"
                            )
                        },
                    )

            async def write_passing_pre_asset_fixed_point(
                _job_id: str,
                *,
                run_dir: Path,
            ) -> None:
                for stage in image_gen_app.PRE_ASSET_SEMANTIC_STAGES:
                    write_passing_foundation_review(run_dir, stage)

            async def materializing_frontend_helper(**kwargs):
                helper_calls.append(kwargs)

                def materialize() -> None:
                    runner.materialize_run(
                        str(kwargs["topic"]),
                        str(kwargs["source"]),
                        run_dir,
                        str(kwargs["stop_target"]),
                        target_duration_seconds=int(kwargs["target_duration_seconds"]),
                        foundation_review_runner=write_passing_foundation_review,
                    )
                    runner.write_run_index(run_dir)

                try:
                    await asyncio.to_thread(materialize)
                    await runner.run_pre_media_semantic_pipeline(
                        run_dir,
                        image_prompt_provider_ready=False,
                    )
                except subprocess.CalledProcessError as exc:
                    helper_errors.append(str(exc.stderr or exc.stdout or exc))
                    raise
                except Exception as exc:
                    helper_errors.append(f"{type(exc).__name__}: {exc}")
                    raise
                return "materialized 1200-second run"

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.reserve_run_dir", return_value=(run_id, run_dir)),
                    patch(
                        "server.image_gen_app._run_toc_immersive_frontend_cli_helper",
                        materializing_frontend_helper,
                    ),
                    patch(
                        "server.image_gen_app._run_semantic_review",
                        side_effect=write_passing_semantic_review,
                    ),
                    patch(
                        "server.image_gen_app._run_pre_asset_semantic_fixed_point",
                        side_effect=write_passing_pre_asset_fixed_point,
                    ),
                    patch("server.image_gen_app._create_process_record_best_effort", return_value=None),
                    patch("server.image_gen_app._update_process_record_best_effort", return_value=None),
                ):
                    with TestClient(app) as client:
                        create_response = client.post(
                            "/api/image-gen/runs/create",
                            json={
                                "title": "シンデレラ",
                                "source": "シンデレラ",
                                "generate_images": False,
                                "target_duration_seconds": 1200,
                            },
                        )
                        create_payload = create_response.json()
                        final_payload: dict[str, Any] = {}
                        deadline = time.monotonic() + (20 * 60)
                        while time.monotonic() < deadline:
                            final_payload = client.get(
                                f"/api/image-gen/runs/create/{create_payload['jobId']}"
                            ).json()
                            if final_payload.get("status") in {"completed", "failed"}:
                                break
                            time.sleep(0.05)
                        else:
                            self.fail("1200-second create integration did not finish within 20 minutes")

            if final_payload.get("status") == "failed":
                events_path = run_dir / "logs" / "app_server" / "events.jsonl"
                if events_path.exists():
                    event_lines = [
                        line for line in events_path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    for line in event_lines:
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if (
                            event.get("operation") == "create_job_step"
                            and event.get("status") == "failed"
                            and event.get("error")
                        ):
                            helper_errors.append(str(event["error"]))
                    if event_lines:
                        helper_errors.append(event_lines[-1])
                state_path = run_dir / "state.txt"
                if state_path.exists():
                    helper_errors.append(
                        "state.last_error="
                        + str(image_gen_app.parse_state_file(state_path).get("last_error") or "")
                    )

            self.assertEqual(
                final_payload.get("status"),
                "completed",
                {"payload": final_payload, "helper_errors": helper_errors},
            )
            _research_text, research = load_structured_document(run_dir / "research.md")
            _story_text, story = load_structured_document(run_dir / "story.md")
            _script_text, script = load_structured_document(run_dir / "script.md")
            _manifest_text, manifest = load_structured_document(run_dir / "video_manifest.md")
            state = image_gen_app.parse_state_file(run_dir / "state.txt")

            self.assertEqual(create_response.status_code, 200)
            self.assertEqual(create_payload["targetDurationSeconds"], 1200)
            self.assertEqual(final_payload.get("status"), "completed", final_payload)
            self.assertEqual(len(helper_calls), 1)
            self.assertEqual(helper_calls[0]["target_duration_seconds"], 1200)
            self.assertTrue(helper_calls[0]["materialize_only"])
            self.assertEqual(state["runtime.target_video_seconds"], "1200")
            self.assertEqual(state["runtime.duration_plan.minimum_scene_count"], "30")
            self.assertNotIn(
                "runtime.duration_plan.minimum_cut_count",
                state,
            )
            self.assertEqual(state["runtime.duration_plan.minimum_narration_seconds"], "840")
            self.assertEqual(research["metadata"]["target_duration_seconds"], 1200)
            self.assertEqual(story["story_metadata"]["target_duration_seconds"], 1200)
            self.assertEqual(script["script_metadata"]["target_duration_seconds"], 1200)
            self.assertEqual(manifest["video_metadata"]["target_duration_seconds"], 1200)
            self.assertGreaterEqual(len(story["script"]["scenes"]), 30)
            self.assertGreaterEqual(len(script["scenes"]), 30)
            self.assertGreaterEqual(len(manifest["scenes"]), 30)
            semantic_minimum_cut_count = 0
            allocated_scene_seconds = 0
            allocated_target_seconds = 0
            for scene in manifest["scenes"]:
                coverage = scene["scene_cut_coverage_plan"]
                minimums = coverage["min_cut_count"]
                semantic_minimum = minimums["selected"]
                obligation_minimum = minimums[
                    "by_distinct_semantic_obligations"
                ]
                event_minimum = minimums["by_event_beats"]
                self.assertIs(type(semantic_minimum), int)
                self.assertIs(type(obligation_minimum), int)
                self.assertIs(type(event_minimum), int)
                self.assertEqual(
                    semantic_minimum,
                    max(obligation_minimum, event_minimum),
                )
                self.assertEqual(
                    coverage["minimum_cut_count"],
                    semantic_minimum,
                )
                self.assertEqual(
                    coverage["selected_cut_count"],
                    len(scene["cuts"]),
                )
                self.assertGreaterEqual(len(scene["cuts"]), semantic_minimum)
                semantic_minimum_cut_count += semantic_minimum

                scene_target_seconds = scene["target_duration_seconds"]
                scene_estimated_seconds = scene["estimated_duration_seconds"]
                self.assertIs(type(scene_target_seconds), int)
                self.assertIs(type(scene_estimated_seconds), int)
                cut_video_seconds: list[int] = []
                for cut in scene["cuts"]:
                    cut_duration_seconds = cut["duration_seconds"]
                    provider_duration_seconds = cut["video_generation"][
                        "duration_seconds"
                    ]
                    self.assertIs(type(cut_duration_seconds), int)
                    self.assertIs(type(provider_duration_seconds), int)
                    self.assertEqual(
                        provider_duration_seconds,
                        cut_duration_seconds,
                    )
                    cut_video_seconds.append(cut_duration_seconds)
                scene_video_seconds = sum(cut_video_seconds)
                self.assertEqual(
                    scene_video_seconds,
                    scene_target_seconds,
                )
                self.assertEqual(
                    scene_estimated_seconds,
                    scene_target_seconds,
                )
                allocated_scene_seconds += scene_video_seconds
                allocated_target_seconds += scene_target_seconds
            self.assertEqual(
                manifest["video_metadata"]["minimum_cut_count"],
                semantic_minimum_cut_count,
            )
            manifest_duration_seconds = manifest["video_metadata"][
                "duration_seconds"
            ]
            self.assertIs(type(manifest_duration_seconds), int)
            self.assertEqual(
                manifest_duration_seconds,
                allocated_scene_seconds,
            )
            self.assertEqual(allocated_scene_seconds, allocated_target_seconds)
            self.assertEqual(manifest_duration_seconds, 1200)
            self.assertGreaterEqual(
                sum(scene["narration_target_seconds"] for scene in story["script"]["scenes"]),
                840,
            )
            self.assertEqual(script["script_metadata"]["minimum_narration_seconds"], 840)
            self.assertEqual(manifest["video_metadata"]["minimum_narration_seconds"], 840)

    def test_create_run_without_images_does_not_complete_without_foundation_semantic_review(self) -> None:
        for missing_stage in ("research", "story"):
            with self.subTest(missing_stage=missing_stage), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)

                async def fake_frontend_cli_helper(**kwargs):
                    run_dir = write_valid_p650_artifacts(root, str(kwargs["run_id"]))
                    report_path = run_dir / image_gen_app.semantic_review_relpaths(missing_stage)["report"]
                    report_path.unlink()
                    return "materialized without images"

                with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                    with (
                        patch("server.image_gen_app.ROOT", root),
                        patch("server.image_gen.time.strftime", return_value="20260509_1200"),
                        patch(
                            "server.image_gen_app._run_toc_immersive_frontend_cli_helper",
                            fake_frontend_cli_helper,
                        ),
                    ):
                        with TestClient(app) as client:
                            create_response = client.post(
                                "/api/image-gen/runs/create",
                                json={
                                    "title": "シンデレラ",
                                    "source": "シンデレラ",
                                    "generate_images": False,
                                },
                            )
                            create_payload = create_response.json()
                            final_payload = self._poll_create_job(client, create_payload["jobId"])

                self.assertEqual(create_response.status_code, 200)
                self.assertEqual(final_payload["status"], "failed")
                self.assertEqual(final_payload["errorCode"], "RuntimeError")

    def test_create_run_without_images_does_not_complete_with_failed_foundation_semantic_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            async def fake_frontend_cli_helper(**kwargs):
                run_dir = write_valid_p650_artifacts(root, str(kwargs["run_id"]))
                report_path = run_dir / image_gen_app.semantic_review_relpaths("story")["report"]
                report_path.write_text(
                    "status: failed\nreviewed_entries: [story_entry_1]\n"
                    "blocked_entries: [story_entry_1]\nfailed_selectors: [story_entry_1]\n"
                    "findings: [story foundation is inconsistent]\nnotes: []\n",
                    encoding="utf-8",
                )
                return "materialized without images"

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen.time.strftime", return_value="20260509_1200"),
                    patch(
                        "server.image_gen_app._run_toc_immersive_frontend_cli_helper",
                        fake_frontend_cli_helper,
                    ),
                ):
                    with TestClient(app) as client:
                        create_response = client.post(
                            "/api/image-gen/runs/create",
                            json={
                                "title": "シンデレラ",
                                "source": "シンデレラ",
                                "generate_images": False,
                            },
                        )
                        create_payload = create_response.json()
                        final_payload = self._poll_create_job(client, create_payload["jobId"])

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(final_payload["status"], "failed")
        self.assertEqual(final_payload["errorCode"], "RuntimeError")

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
                            json={"title": "桃太郎", "source": "鬼ヶ島の資料", "target_duration_seconds": 900},
                        )
                        create_payload = create_response.json()
                        final_payload = self._poll_create_job(client, create_payload["jobId"])

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_payload["runId"], "桃太郎_20260509_1200")
        self.assertEqual(create_payload["targetDurationSeconds"], 900)
        self.assertEqual(final_payload["status"], "completed")
        self.assertEqual(
            calls,
            [
                {
                    "topic": "桃太郎",
                    "source": "鬼ヶ島の資料",
                    "run_id": "桃太郎_20260509_1200",
                    "stop_target": "p680",
                    "target_duration_seconds": 900,
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
                source = "app_server"
                provenance_authoritative = True
                turn_id = "turn-1"

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
            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "TOC_IMAGE_GEN_PROVENANCE_POLICY": "serial_fallback"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                    patch("server.image_gen_app._validate_p560_asset_quality", validate_asset_gate),
                    patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
                    patch("server.image_gen_app._run_semantic_review", AsyncMock()),
                    patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
                ):
                    asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            scene_exists = (run_dir / "assets/scenes/scene10_cut1.png").exists()

        self.assertTrue(scene_exists)
        self.assertEqual(
            generated,
            [
                ("scene10_cut1", ["hero.png"]),
                ("scene10_cut2", ["hero.png"]),
                ("scene10_cut3", ["hero.png"]),
            ],
        )
        validate_asset_gate.assert_called_once()
        self.assertEqual(validate_asset_gate.call_args.args[0].resolve(), run_dir.resolve())
        self.assertIn("slot.p660.status=done", state)
        self.assertIn("slot.p680.status=awaiting_approval", state)
        self.assertIn("review.image.status=pending", state)

    def test_scene_generation_validates_current_revision_outputs_and_visuals_before_p680_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            order: list[str] = []

            def fake_validate_p650(received_run_id: str) -> None:
                self.assertEqual(received_run_id, run_id)
                order.append("p650")

            async def fake_set_create_job(_job_id: str, _updates: dict[str, Any]) -> None:
                order.append("job")

            async def fake_generate(*, run_dir: Path, kind: str) -> None:
                self.assertEqual(kind, "scene")
                order.append("generate")

            def fake_validate_outputs(_run_dir: Path, kind: str) -> None:
                order.append(f"outputs:{kind}")

            def fake_visual_gate(_run_dir: Path) -> None:
                order.append("visual")

            def fake_mark_ready(received_run_id: str) -> None:
                self.assertEqual(received_run_id, run_id)
                order.append("handoff")

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._validate_p650_run", fake_validate_p650),
                patch("server.image_gen_app._set_create_job", fake_set_create_job),
                patch("server.image_gen_app._generate_request_outputs_unlocked", fake_generate),
                patch("server.image_gen_app._validate_generated_outputs", fake_validate_outputs),
                patch("server.image_gen_app._validate_p680_visual_quality", fake_visual_gate),
                patch("server.image_gen_app._mark_image_generation_review_ready", fake_mark_ready),
            ):
                asyncio.run(
                    image_gen_app._generate_scene_outputs_after_p650_preflight(
                        "job-1",
                        run_id=run_id,
                        run_dir=run_dir,
                    )
                )

        self.assertEqual(
            order,
            [
                "p650",
                "job",
                "generate",
                "p650",
                "outputs:asset",
                "outputs:scene",
                "visual",
                "handoff",
            ],
        )

    def test_scene_generation_records_p650_preflight_failure_for_all_validation_exceptions(
        self,
    ) -> None:
        validation_errors = (
            ImageRequestSnapshotError("asset snapshot is stale"),
            ValueError("invalid request destination"),
            OSError("request snapshot is unreadable"),
        )
        for validation_error in validation_errors:
            with (
                self.subTest(error_type=type(validation_error).__name__),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                run_id = "桃太郎_20260509_1200"
                run_dir = write_valid_p650_artifacts(root, run_id)
                provider = AsyncMock()
                mark_ready = Mock()

                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch(
                        "server.image_gen_app._validate_p650_run",
                        side_effect=validation_error,
                    ),
                    patch(
                        "server.image_gen_app._generate_request_outputs_unlocked",
                        provider,
                    ),
                    patch(
                        "server.image_gen_app._mark_image_generation_review_ready",
                        mark_ready,
                    ),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "scene image generation blocked by p650 gate",
                    ):
                        asyncio.run(
                            image_gen_app._generate_scene_outputs_after_p650_preflight(
                                "job-1",
                                run_id=run_id,
                                run_dir=run_dir,
                            )
                        )

                state = image_gen_app.parse_state_file(run_dir / "state.txt")
                provider.assert_not_awaited()
                mark_ready.assert_not_called()
                self.assertEqual(
                    state["runtime.stage"],
                    "p650_gate_failed_before_scene_generation",
                )
                self.assertEqual(state["slot.p660.status"], "pending")
                self.assertEqual(state["slot.p680.status"], "pending")
                self.assertEqual(
                    state["image_generation.blocked_by"],
                    "p650_revision_gate",
                )

    def test_scene_generation_keeps_p680_pending_when_pre_handoff_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            image_gen_app.append_state_snapshot(
                run_dir / "state.txt",
                {"slot.p680.status": "awaiting_approval"},
            )
            mark_ready = Mock()

            async def fake_set_create_job(_job_id: str, _updates: dict[str, Any]) -> None:
                return None

            async def fake_generate(*, run_dir: Path, kind: str) -> None:
                return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._validate_p650_run", Mock()),
                patch("server.image_gen_app._set_create_job", fake_set_create_job),
                patch("server.image_gen_app._generate_request_outputs_unlocked", fake_generate),
                patch("server.image_gen_app._validate_generated_outputs", Mock()),
                patch(
                    "server.image_gen_app._validate_p680_visual_quality",
                    Mock(side_effect=RuntimeError("visual image stage failed")),
                ),
                patch("server.image_gen_app._mark_image_generation_review_ready", mark_ready),
            ):
                with self.assertRaisesRegex(RuntimeError, "visual image stage failed"):
                    asyncio.run(
                        image_gen_app._generate_scene_outputs_after_p650_preflight(
                            "job-1",
                            run_id=run_id,
                            run_dir=run_dir,
                        )
                    )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        mark_ready.assert_not_called()
        self.assertEqual(state["slot.p680.status"], "pending")
        self.assertEqual(state["image_generation.status"], "failed")
        self.assertEqual(state["image_generation.started"], "true")
        self.assertEqual(state["image_generation.blocked_by"], "p680_pre_handoff_gate")

    def test_successful_scene_generation_records_completed_image_generation_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)

            async def fake_set_create_job(_job_id: str, _updates: dict[str, Any]) -> None:
                return None

            async def fake_generate(*, run_dir: Path, kind: str) -> None:
                return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._validate_p650_run", Mock()),
                patch("server.image_gen_app._set_create_job", fake_set_create_job),
                patch("server.image_gen_app._generate_request_outputs_unlocked", fake_generate),
                patch("server.image_gen_app._validate_generated_outputs", Mock()),
                patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
                patch("server.image_gen_app._finalize_p600_supervisor_result", Mock()),
            ):
                asyncio.run(
                    image_gen_app._generate_scene_outputs_after_p650_preflight(
                        "job-1",
                        run_id=run_id,
                        run_dir=run_dir,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(state["slot.p680.status"], "awaiting_approval")
        self.assertEqual(state["image_generation.status"], "completed")
        self.assertEqual(state["image_generation.started"], "true")
        self.assertEqual(state["image_generation.generated_count"], "3")
        self.assertEqual(state["review.semantic.create_scene_media_generated"], "true")

    def test_generate_create_images_continues_unblocked_scenes_on_localized_scene_detail_transport_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            request_path = run_dir / "image_generation_requests.md"
            request_path.write_text(
                request_path.read_text(encoding="utf-8")
                + """

## scene40_cut1

- tool: `codex_builtin_image`
- prompt_policy_version: `image_api_prompt_v1`
- execution_lane: `standard`
- reference_count: `1`
- output: `assets/scenes/scene40_cut1.png`
- references:
  - `主人公`: `assets/characters/hero.png`

```api_prompt
transport blocked scene should not generate.
```
""",
                encoding="utf-8",
            )
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8").replace(
                    "```\n",
                    """  - scene_id: 40
    cuts:
      - cut_id: 1
        duration_seconds: 8
        image_generation:
          output: assets/scenes/scene40_cut1.png
```
""",
                ),
                encoding="utf-8",
            )
            refresh_scene_request_snapshot_fixture(run_dir)
            saved = root / "generated.png"
            saved.write_bytes(PNG_BYTES)
            generated: list[str] = []

            class FakeResult:
                saved_path = saved
                revised_prompt = None
                status = "completed"
                transcript = []
                source = "app_server"
                provenance_authoritative = True
                turn_id = "turn-1"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    generated.append(kwargs["item_id"])
                    return FakeResult()

            async def fake_run_semantic_review(job_id: str, *, run_dir: Path, stage: str) -> None:
                if stage == "scene_detail":
                    write_failed_semantic_review_artifacts(
                        run_dir,
                        stage,
                        reviewed_entries=["scene:10", "scene:40"],
                        failed_selectors=["scene:40"],
                        blocked_entries=["scene:40"],
                    )
                    image_gen_app.append_state_snapshot(
                        run_dir / "state.txt",
                        {
                            "review.semantic.scene_detail.shards.scene_40.transport.status": "failed",
                            "review.semantic.scene_detail.shards.scene_40.transport.error_kind": "timeout",
                            "review.semantic.scene_detail.shards.scene_40.transport.error": "CodexAppServerTransportError: turn timed out",
                        },
                    )
                    raise CodexAppServerTransportError("scene_detail shard transport failed after 3 attempt(s): scene:40")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "TOC_IMAGE_GEN_PROVENANCE_POLICY": "serial_fallback"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                    patch("server.image_gen_app._validate_p560_asset_quality", Mock()),
                    patch("server.image_gen_app._run_semantic_review", fake_run_semantic_review),
                    patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
                    patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
                    patch(
                        "server.image_gen_app._deterministic_image_prompt_hard_gate_errors",
                        return_value=[],
                    ),
                ):
                    asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            scene10_exists = (run_dir / "assets/scenes/scene10_cut1.png").exists()
            scene40_exists = (run_dir / "assets/scenes/scene40_cut1.png").exists()
            with patch("server.image_gen_app.ROOT", root):
                payload = asyncio.run(
                    image_gen_app.api_requests(run_id=run_id, kind="scene")
                )

        self.assertTrue(scene10_exists)
        self.assertFalse(scene40_exists)
        self.assertEqual(
            [item_id for item_id in generated if item_id.startswith("scene")],
            ["scene10_cut1", "scene10_cut2", "scene10_cut3"],
        )
        self.assertEqual(
            state["runtime.stage"],
            "scene_images_partial_ready_for_review",
        )
        self.assertEqual(state["review.semantic.scene_detail.partial_media_allowed"], "true")
        self.assertEqual(state["review.semantic.create_media_generated"], "true")
        self.assertEqual(state["image_generation.status"], "partial")
        self.assertEqual(state["slot.p680.status"], "awaiting_approval")
        self.assertIn("scene40_cut1", state["review.semantic.scene_detail.blocked_image_items"])
        blocked = next(item for item in payload["items"] if item["id"] == "scene40_cut1")
        self.assertEqual(blocked["generationStatus"], "blocked")
        self.assertEqual(blocked["candidates"][0]["status"], "failed")

    def test_generate_create_images_continues_unblocked_scenes_on_localized_scene_detail_semantic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            request_path = run_dir / "image_generation_requests.md"
            request_path.write_text(
                request_path.read_text(encoding="utf-8")
                + """

## scene20_cut1

- tool: `codex_builtin_image`
- prompt_policy_version: `image_api_prompt_v1`
- execution_lane: `standard`
- reference_count: `1`
- output: `assets/scenes/scene20_cut1.png`
- references:
  - `主人公`: `assets/characters/hero.png`

```api_prompt
semantic blocked scene should not generate.
```
""",
                encoding="utf-8",
            )
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8").replace(
                    "```\n",
                    """  - scene_id: 20
    cuts:
      - cut_id: 1
        duration_seconds: 8
        image_generation:
          output: assets/scenes/scene20_cut1.png
```
""",
                ),
                encoding="utf-8",
            )
            refresh_scene_request_snapshot_fixture(run_dir)
            saved = root / "generated.png"
            saved.write_bytes(PNG_BYTES)
            generated: list[str] = []

            class FakeResult:
                saved_path = saved
                revised_prompt = None
                status = "completed"
                transcript = []
                source = "app_server"
                provenance_authoritative = True
                turn_id = "turn-1"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    generated.append(kwargs["item_id"])
                    return FakeResult()

            async def fake_run_semantic_review(job_id: str, *, run_dir: Path, stage: str) -> None:
                if stage == "scene_detail":
                    write_failed_semantic_review_artifacts(
                        run_dir,
                        stage,
                        reviewed_entries=["scene:10", "scene:20"],
                        failed_selectors=["scene:20"],
                        blocked_entries=["scene20_cut1"],
                    )
                    raise RuntimeError("scene_detail semantic review failed after 1 attempt(s)")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "TOC_IMAGE_GEN_PROVENANCE_POLICY": "serial_fallback"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                    patch("server.image_gen_app._validate_p560_asset_quality", Mock()),
                    patch("server.image_gen_app._run_semantic_review", fake_run_semantic_review),
                    patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
                    patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
                    patch(
                        "server.image_gen_app._deterministic_image_prompt_hard_gate_errors",
                        return_value=[],
                    ),
                ):
                    asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            scene10_exists = (run_dir / "assets/scenes/scene10_cut1.png").exists()
            scene20_exists = (run_dir / "assets/scenes/scene20_cut1.png").exists()

        self.assertTrue(scene10_exists)
        self.assertFalse(scene20_exists)
        self.assertEqual(
            [item_id for item_id in generated if item_id.startswith("scene")],
            ["scene10_cut1", "scene10_cut2", "scene10_cut3"],
        )
        self.assertEqual(state["runtime.stage"], "scene_images_partial_ready_for_review")
        self.assertEqual(
            state["review.semantic.create_scene_media_generated"],
            "true",
        )
        self.assertIn("scene20_cut1", state["review.semantic.scene_detail.blocked_image_items"])
        self.assertEqual(state["review.semantic.scene_detail.partial_media_allowed"], "true")
        self.assertEqual(state["slot.p680.status"], "awaiting_approval")

    def test_unmapped_scene_detail_failure_remains_globally_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)

            async def fake_run_semantic_review(
                _job_id: str,
                *,
                run_dir: Path,
                stage: str,
            ) -> None:
                write_failed_semantic_review_artifacts(
                    run_dir,
                    stage,
                    reviewed_entries=["scene:10"],
                    failed_selectors=["unknown_scene"],
                    blocked_entries=["unknown_scene"],
                )
                raise RuntimeError("scene_detail semantic review failed")

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_semantic_review",
                    fake_run_semantic_review,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "semantic review failed before media generation",
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review_for_media_generation(
                            "job-1",
                            run_dir=run_dir,
                            stage="scene_detail",
                        )
                    )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(
            state["review.semantic.scene_detail.partial_media_allowed"],
            "false",
        )
        self.assertEqual(
            state["review.semantic.scene_detail.localization.status"],
            "not_localized",
        )
        self.assertEqual(
            state["runtime.stage"],
            "semantic_review_failed_before_media_generation",
        )

    def test_stale_localized_failure_report_remains_globally_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            write_failed_semantic_review_artifacts(
                run_dir,
                "scene_detail",
                reviewed_entries=["scene:10"],
                failed_selectors=["scene:10"],
                blocked_entries=["scene10_cut1"],
            )
            source_path = (
                run_dir
                / "logs/review/semantic/scene_detail.source.md"
            )
            source_path.write_text(
                source_path.read_text(encoding="utf-8") + "\nstale mutation\n",
                encoding="utf-8",
            )

            async def fake_run_semantic_review(
                _job_id: str,
                *,
                run_dir: Path,
                stage: str,
            ) -> None:
                raise RuntimeError(f"{stage} semantic review failed")

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_semantic_review",
                    fake_run_semantic_review,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "semantic review failed before media generation",
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review_for_media_generation(
                            "job-1",
                            run_dir=run_dir,
                            stage="scene_detail",
                        )
                    )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(
            state["review.semantic.scene_detail.partial_media_allowed"],
            "false",
        )
        self.assertIn(
            "SHA-256 mismatch",
            state["review.semantic.scene_detail.localization.reason"],
        )

    def test_incomplete_reviewed_entry_accounting_remains_globally_blocking(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            stage = "scene_detail"
            write_failed_semantic_review_artifacts(
                run_dir,
                stage,
                reviewed_entries=["scene:10", "scene:20"],
                failed_selectors=["scene:20"],
                blocked_entries=["scene20_cut1"],
            )
            relpaths = image_gen_app.semantic_review_relpaths(stage)
            report_path = run_dir / relpaths["report"]
            report_path.write_text(
                report_path.read_text(encoding="utf-8").replace(
                    "reviewed_entries: [scene:10, scene:20]",
                    "reviewed_entries: [scene:10]",
                ),
                encoding="utf-8",
            )
            image_gen_app._refresh_semantic_review_input_digest(
                run_dir=run_dir,
                scope_path=run_dir / relpaths["scope"],
                collection_path=run_dir / relpaths["collection"],
                prompt_path=run_dir / relpaths["prompt"],
                report_path=report_path,
            )

            async def fake_run_semantic_review(
                _job_id: str,
                *,
                run_dir: Path,
                stage: str,
            ) -> None:
                raise RuntimeError(f"{stage} semantic review failed")

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_semantic_review",
                    fake_run_semantic_review,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "semantic review failed before media generation",
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review_for_media_generation(
                            "job-1",
                            run_dir=run_dir,
                            stage=stage,
                        )
                    )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(
            state["review.semantic.scene_detail.partial_media_allowed"],
            "false",
        )
        self.assertIn(
            "reviewed_entries coverage",
            state["review.semantic.scene_detail.localization.reason"],
        )

    def test_cut_blueprint_failure_localizes_to_one_cut(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)

            async def fake_run_semantic_review(
                _job_id: str,
                *,
                run_dir: Path,
                stage: str,
            ) -> None:
                write_failed_semantic_review_artifacts(
                    run_dir,
                    stage,
                    reviewed_entries=[
                        "cut:scene10_cut01",
                        "cut:scene10_cut02",
                        "cut:scene10_cut03",
                    ],
                    failed_selectors=["scene10_cut2"],
                    blocked_entries=["scene10_cut2"],
                )
                raise RuntimeError("cut_blueprint semantic review failed")

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_semantic_review",
                    fake_run_semantic_review,
                ),
            ):
                failure = asyncio.run(
                    image_gen_app._run_semantic_review_for_media_generation(
                        "job-1",
                        run_dir=run_dir,
                        stage="cut_blueprint",
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertIsNone(failure)
        self.assertEqual(
            state["review.semantic.cut_blueprint.partial_media_allowed"],
            "true",
        )
        self.assertEqual(
            state["review.semantic.cut_blueprint.blocked_image_items"],
            "scene10_cut2",
        )
        self.assertEqual(state["slot.p420.status"], "done")

    def test_api_requests_marks_scene_detail_transport_blocked_items_as_failed_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            request_path = run_dir / "image_generation_requests.md"
            request_path.write_text(
                request_path.read_text(encoding="utf-8")
                + """

## scene40_cut1

- tool: `codex_builtin_image`
- prompt_policy_version: `image_api_prompt_v1`
- execution_lane: `standard`
- reference_count: `1`
- output: `assets/scenes/scene40_cut1.png`

```api_prompt
transport blocked scene should show as failed.
```
""",
                encoding="utf-8",
            )
            refresh_scene_request_snapshot_fixture(run_dir)
            write_failed_semantic_review_artifacts(
                run_dir,
                "scene_detail",
                reviewed_entries=["scene:10", "scene:40"],
                failed_selectors=["scene:40"],
                blocked_entries=["scene:40"],
            )
            activate_localized_partial_media_fixture(
                run_dir,
                "scene_detail",
                blocked_item_ids=["scene40_cut1"],
                extra_state={
                    "review.semantic.scene_detail.shards.scene_40.transport.status": "failed",
                    "review.semantic.scene_detail.shards.scene_40.transport.error_kind": "timeout",
                    "review.semantic.scene_detail.shards.scene_40.transport.error": "CodexAppServerTransportError: turn timed out",
                },
            )

            with patch("server.image_gen_app.ROOT", root):
                payload = asyncio.run(image_gen_app.api_requests(run_id=run_id, kind="scene"))

        blocked = next(item for item in payload["items"] if item["id"] == "scene40_cut1")
        normal = next(item for item in payload["items"] if item["id"] == "scene10_cut1")
        self.assertEqual(blocked["generationStatus"], "blocked")
        self.assertEqual(blocked["candidates"][0]["status"], "failed")
        self.assertIn("scene_detail", blocked["candidates"][0]["error"])
        self.assertIn("image generation skipped", blocked["candidates"][0]["error"])
        self.assertIsNone(normal["generationStatus"])
        self.assertEqual(normal["candidates"], [])

    def test_api_requests_marks_scene_detail_semantic_blocked_items_as_failed_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            request_path = run_dir / "image_generation_requests.md"
            request_path.write_text(
                request_path.read_text(encoding="utf-8")
                + """

## scene20_cut1

- tool: `codex_builtin_image`
- prompt_policy_version: `image_api_prompt_v1`
- execution_lane: `standard`
- reference_count: `1`
- output: `assets/scenes/scene20_cut1.png`

```api_prompt
semantic blocked scene should show as failed.
```
""",
                encoding="utf-8",
            )
            refresh_scene_request_snapshot_fixture(run_dir)
            write_failed_semantic_review_artifacts(
                run_dir,
                "scene_detail",
                reviewed_entries=["scene:10", "scene:20"],
                failed_selectors=["scene:20"],
                blocked_entries=["scene20_cut1"],
            )
            activate_localized_partial_media_fixture(
                run_dir,
                "scene_detail",
                blocked_item_ids=["scene20_cut1"],
                extra_state={
                    "review.semantic.scene_detail.failure.failed_selectors": "scene:20",
                    "review.semantic.scene_detail.failure.blocked_entries": "scene20_cut1",
                    "review.semantic.scene_detail.failure.reason_keys": "scene_detail_obligation_missing",
                },
            )
            retained_candidate = image_gen.candidate_path(run_dir, "scene20_cut1", 1)
            retained_candidate.parent.mkdir(parents=True, exist_ok=True)
            retained_candidate.write_bytes(PNG_BYTES)

            with patch("server.image_gen_app.ROOT", root):
                payload = asyncio.run(image_gen_app.api_requests(run_id=run_id, kind="scene"))

        blocked = next(item for item in payload["items"] if item["id"] == "scene20_cut1")
        normal = next(item for item in payload["items"] if item["id"] == "scene10_cut1")
        self.assertEqual(blocked["generationStatus"], "blocked")
        self.assertEqual(blocked["candidates"][0]["status"], "failed")
        self.assertEqual(
            blocked["candidates"][0]["blocking_stages"],
            ["scene_detail"],
        )
        self.assertEqual(
            blocked["previousCandidates"][0]["path"],
            "assets/test/image_gen_candidates/scene20_cut1/scene20_cut1_candidate_01.png",
        )
        self.assertIsNone(normal["generationStatus"])
        self.assertEqual(normal["candidates"], [])

    def test_passed_semantic_stage_ignores_stale_failure_selectors_and_transport_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            image_gen_app.append_state_snapshot(
                run_dir / "state.txt",
                {
                    "review.semantic.scene_detail.failure.failed_selectors": "scene:10",
                    "review.semantic.scene_detail.failure.blocked_entries": "scene10_cut1",
                    "review.semantic.scene_detail.shards.scene_10.transport.status": "failed",
                    "review.semantic.image_prompt.failure.failed_selectors": "scene10_cut02",
                    "review.semantic.image_prompt.failure.blocked_entries": "scene10_cut02",
                },
            )
            image_gen_app.append_state_snapshot(
                run_dir / "state.txt",
                {
                    "review.semantic.scene_detail.status": "passed",
                    "review.semantic.scene_detail.loop.status": "passed",
                    "review.semantic.image_prompt.status": "passed",
                    "review.semantic.image_prompt.loop.status": "passed",
                },
            )
            items = image_gen_app.load_request_items(run_dir, "scene")

            blocked = image_gen_app._semantic_blocked_image_item_ids(
                run_dir,
                items,
            )

        self.assertEqual(blocked, set())

    def test_generate_create_images_continues_other_cuts_when_image_prompt_review_is_localized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            supervisor_result_path = run_dir / "logs/orchestration/p600.supervisor_result.json"
            supervisor_result_path.parent.mkdir(parents=True, exist_ok=True)
            supervisor_result_path.write_text(
                json.dumps(
                    {
                        "bucket": "p600",
                        "status": "done",
                        "completed_slots": ["p610", "p620", "p630", "p640", "p650"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            saved = root / "generated.png"
            saved.write_bytes(PNG_BYTES)
            generated: list[str] = []

            class FakeResult:
                saved_path = saved
                revised_prompt = None
                status = "completed"
                transcript = []
                source = "app_server"
                provenance_authoritative = True
                turn_id = "turn-1"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    generated.append(kwargs["item_id"])
                    return FakeResult()

            async def fake_run_semantic_review(job_id: str, *, run_dir: Path, stage: str) -> None:
                if stage == "image_prompt":
                    write_failed_semantic_review_artifacts(
                        run_dir,
                        stage,
                        reviewed_entries=[
                            "scene10_cut01",
                            "scene10_cut02",
                            "scene10_cut03",
                        ],
                        failed_selectors=["scene10_cut02"],
                        blocked_entries=["scene10_cut02"],
                    )
                    raise RuntimeError("image_prompt semantic review failed after 1 attempt(s)")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "TOC_IMAGE_GEN_PROVENANCE_POLICY": "serial_fallback"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                    patch("server.image_gen_app._validate_p560_asset_quality", Mock()),
                    patch("server.image_gen_app._run_semantic_review", fake_run_semantic_review),
                    patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
                    patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
                    patch(
                        "server.image_gen_app._deterministic_image_prompt_hard_gate_errors",
                        return_value=[],
                    ),
                ):
                    asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            supervisor_result = json.loads(supervisor_result_path.read_text(encoding="utf-8"))
            scene10_cut1_exists = (run_dir / "assets/scenes/scene10_cut1.png").exists()
            scene10_cut2_exists = (run_dir / "assets/scenes/scene10_cut2.png").exists()
            scene10_cut3_exists = (run_dir / "assets/scenes/scene10_cut3.png").exists()

        self.assertTrue(scene10_cut1_exists)
        self.assertFalse(scene10_cut2_exists)
        self.assertTrue(scene10_cut3_exists)
        self.assertEqual(
            [item_id for item_id in generated if item_id.startswith("scene")],
            ["scene10_cut1", "scene10_cut3"],
        )
        self.assertEqual(state["runtime.stage"], "scene_images_partial_ready_for_review")
        self.assertEqual(state["review.semantic.image_prompt.partial_media_allowed"], "true")
        self.assertEqual(state["review.semantic.create_scene_media_generated"], "true")
        self.assertIn("scene10_cut2", state["review.semantic.image_prompt.blocked_image_items"])
        self.assertEqual(state["review.image_prompt.request_freeze.status"], "frozen")
        self.assertEqual(
            state["review.image_prompt.request_freeze.semantic_status"],
            "localized_failure",
        )
        self.assertEqual(state["slot.p650.status"], "done")
        self.assertEqual(state["orchestration.p600.supervisor.status"], "done")
        self.assertEqual(supervisor_result["status"], "done")

    def test_generate_create_images_blocks_all_scenes_when_asset_plan_review_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            supervisor_result_path = run_dir / "logs/orchestration/p600.supervisor_result.json"
            supervisor_result_path.parent.mkdir(parents=True, exist_ok=True)
            supervisor_result_path.write_text(
                json.dumps(
                    {
                        "bucket": "p600",
                        "status": "done",
                        "completed_slots": ["p610", "p620", "p630", "p640", "p650"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "asset_plan.md").write_text(
                """```yaml
assets:
  - asset_id: story_signature_artifact
    asset_type: object_reference
    source_script_selectors:
      - scene10_cut2
    generation_plan:
      output: assets/objects/story_signature_artifact.png
```
""",
                encoding="utf-8",
            )
            saved = root / "generated.png"
            saved.write_bytes(PNG_BYTES)
            generated: list[str] = []

            class FakeResult:
                saved_path = saved
                revised_prompt = None
                status = "completed"
                transcript = []
                source = "app_server"
                provenance_authoritative = True
                turn_id = "turn-1"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    generated.append(kwargs["item_id"])
                    return FakeResult()

            async def fake_run_semantic_review(job_id: str, *, run_dir: Path, stage: str) -> None:
                if stage == "asset_plan":
                    relpaths = image_gen_app.semantic_review_relpaths(stage)
                    report_path = run_dir / relpaths["report"]
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    report_path.write_text(
                        "\n".join(
                            [
                                "status: failed",
                                "failed_selectors:",
                                "  - story_signature_artifact",
                                "blocked_entries:",
                                "  - story_signature_artifact",
                                "reason_keys:",
                                "  - asset_missing_required_cut_selector",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                    raise RuntimeError("asset_plan semantic review failed after 1 attempt(s)")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "TOC_IMAGE_GEN_PROVENANCE_POLICY": "serial_fallback"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                    patch("server.image_gen_app._validate_p560_asset_quality", Mock()),
                    patch("server.image_gen_app._run_semantic_review", fake_run_semantic_review),
                    patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
                ):
                    with self.assertRaisesRegex(RuntimeError, "semantic review failed before media generation"):
                        asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            supervisor_result = json.loads(supervisor_result_path.read_text(encoding="utf-8"))
            scene10_cut1_exists = (run_dir / "assets/scenes/scene10_cut1.png").exists()
            scene10_cut2_exists = (run_dir / "assets/scenes/scene10_cut2.png").exists()
            scene10_cut3_exists = (run_dir / "assets/scenes/scene10_cut3.png").exists()

        self.assertFalse(scene10_cut1_exists)
        self.assertFalse(scene10_cut2_exists)
        self.assertFalse(scene10_cut3_exists)
        # The asset-plan semantic gate runs before any provider submission.
        self.assertEqual(generated, [])
        self.assertEqual(state["runtime.stage"], "semantic_review_failed_before_media_generation")
        self.assertEqual(state["review.semantic.asset_plan.partial_media_allowed"], "false")
        self.assertEqual(state["review.semantic.create_media_generated"], "false")
        self.assertEqual(state["review.semantic.asset_plan.localization.status"], "not_eligible")
        self.assertNotIn("review.semantic.asset_plan.blocked_image_items", state)
        self.assertEqual(state["review.image_prompt.request_freeze.status"], "draft")
        self.assertEqual(state["review.image_prompt.request_freeze.invalidated_by"], "semantic.asset_plan.failed")
        self.assertEqual(state["slot.p650.status"], "pending")
        self.assertEqual(state["orchestration.p600.supervisor.status"], "invalidated")
        self.assertEqual(state["orchestration.p600.supervisor.invalidated_by"], "semantic.asset_plan.failed")
        self.assertEqual(supervisor_result["status"], "invalidated")
        self.assertEqual(supervisor_result["previous_status"], "done")
        self.assertEqual(supervisor_result["invalidated_by"], "semantic.asset_plan.failed")

    def test_api_requests_marks_image_prompt_blocked_cut_as_failed_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            write_failed_semantic_review_artifacts(
                run_dir,
                "image_prompt",
                reviewed_entries=[
                    "scene10_cut01",
                    "scene10_cut02",
                    "scene10_cut03",
                ],
                failed_selectors=["scene10_cut02"],
                blocked_entries=["scene10_cut02"],
            )
            activate_localized_partial_media_fixture(
                run_dir,
                "image_prompt",
                blocked_item_ids=["scene10_cut2"],
                extra_state={
                    "review.semantic.image_prompt.failure.failed_selectors": "scene10_cut02",
                    "review.semantic.image_prompt.failure.blocked_entries": "scene10_cut02",
                    "review.semantic.image_prompt.failure.reason_keys": "api_prompt_emotion_is_abstract_not_performable",
                },
            )

            with patch("server.image_gen_app.ROOT", root):
                payload = asyncio.run(image_gen_app.api_requests(run_id=run_id, kind="scene"))

        blocked = next(item for item in payload["items"] if item["id"] == "scene10_cut2")
        normal = next(item for item in payload["items"] if item["id"] == "scene10_cut1")
        self.assertEqual(blocked["generationStatus"], "blocked")
        self.assertEqual(blocked["candidates"][0]["status"], "failed")
        self.assertIn("image_prompt", blocked["candidates"][0]["error"])
        self.assertIn("image generation skipped", blocked["candidates"][0]["error"])
        self.assertIsNone(normal["generationStatus"])
        self.assertEqual(normal["candidates"], [])

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

    def test_generate_request_outputs_serializes_same_group_items_for_app_server_fallback(self) -> None:
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

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "TOC_IMAGE_GEN_PROVENANCE_POLICY": "serial_fallback"}):
                with (
                    patch("server.image_gen_app.IMAGE_GENERATION_PARALLELISM", 4),
                    patch("server.image_gen_app._generate_request_item_output", fake_generate_item),
                ):
                    asyncio.run(image_gen_app._generate_request_outputs(run_dir=run_dir, kind="asset"))

            batch_log = next((run_dir / "logs" / "app_server" / "request_generation_batch").glob("*.json"))
            batch_payload = json.loads(batch_log.read_text(encoding="utf-8"))

        self.assertEqual(set(generated), {"base_a", "base_b"})
        self.assertEqual(peak, 1)
        self.assertEqual(batch_payload["request"]["parallelismRequested"], 4)
        self.assertEqual(batch_payload["request"]["parallelismEffective"], 1)
        self.assertEqual(batch_payload["request"]["provenancePolicy"], "serial_fallback")

    def test_generate_request_outputs_uses_request_bound_v2_parallelism_by_default(self) -> None:
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
                await asyncio.sleep(0.03)
                output = run_dir / item.output
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(PNG_BYTES)
                generated.append(item.id)
                active -= 1

            with (
                patch.dict(os.environ, {"TOC_IMAGE_GEN_PROVENANCE_POLICY": "", "TOC_IMAGE_GEN_DISABLE_CODEX_APP_SERVER": ""}, clear=False),
                patch("server.image_gen_app.IMAGE_GENERATION_PARALLELISM", 2),
                patch("server.image_gen_app._generate_request_item_output", fake_generate_item),
            ):
                asyncio.run(image_gen_app._generate_request_outputs(run_dir=run_dir, kind="asset"))

            batch_log = next((run_dir / "logs" / "app_server" / "request_generation_batch").glob("*.json"))
            batch_payload = json.loads(batch_log.read_text(encoding="utf-8"))

        self.assertEqual(set(generated), {"base_a", "base_b"})
        self.assertEqual(peak, 2)
        self.assertEqual(batch_payload["request"]["parallelismRequested"], 2)
        self.assertEqual(batch_payload["request"]["parallelismEffective"], 2)
        self.assertEqual(batch_payload["request"]["provenancePolicy"], "request_bound_v2")

    def test_generate_create_images_retries_bootstrap_assets_until_gate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            write_valid_p650_artifacts(root, run_id)
            generated_kinds: list[str] = []
            repair_prompts = AsyncMock()
            visual_gate_error = image_gen_app.P560AssetGateError(
                "p560 asset gate failed: bootstrap asset is vector-like",
                failed_check_ids=("asset.visual_not_vector_like",),
                retryable_visual_quality=True,
            )
            gate = Mock(
                side_effect=[visual_gate_error, visual_gate_error, None]
            )

            async def fake_generate_request_outputs(*, run_dir, kind):
                generated_kinds.append(kind)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._generate_request_outputs", fake_generate_request_outputs),
                    patch("server.image_gen_app._generate_request_outputs_unlocked", fake_generate_request_outputs),
                    patch("server.image_gen_app._validate_p560_asset_quality", gate),
                    patch("server.image_gen_app._repair_bootstrap_asset_prompts", repair_prompts),
                    patch("server.image_gen_app._remove_bootstrap_asset_outputs", Mock()),
                    patch("server.image_gen_app._run_semantic_review", AsyncMock()),
                    patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
                    patch("server.image_gen_app._validate_generated_outputs", Mock()),
                    patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
                ):
                    result = asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

        self.assertTrue(result)
        self.assertEqual(generated_kinds, ["asset", "asset", "asset", "scene"])
        self.assertEqual(gate.call_count, 3)
        self.assertEqual(repair_prompts.await_count, 2)

    def test_asset_generation_handoff_finalizes_p500_supervisor(self) -> None:
        for asset_quality_passed, terminal_status in (
            (True, "done"),
            (False, "awaiting_approval"),
        ):
            with self.subTest(
                asset_quality_passed=asset_quality_passed
            ), tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                result_path = (
                    run_dir
                    / "logs"
                    / "orchestration"
                    / "p500.supervisor_result.json"
                )
                result_path.parent.mkdir(parents=True)
                result_path.write_text(
                    json.dumps(
                        {
                            "bucket": "p500",
                            "status": "pending",
                            "completed_slots": ["p520", "p530"],
                            "required_artifacts": [],
                            "state_keys": {
                                "slot.p570.status": "pending"
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )

                image_gen_app._mark_asset_generation_handoff(
                    run_dir,
                    asset_quality_passed=asset_quality_passed,
                )

                state = image_gen_app.parse_state_file(
                    run_dir / "state.txt"
                )
                result = json.loads(
                    result_path.read_text(encoding="utf-8")
                )

                self.assertEqual(
                    state["orchestration.p500.supervisor.status"],
                    "done",
                )
                self.assertEqual(result["status"], "done")
                self.assertEqual(
                    result["completed_slots"],
                    [
                        "p520",
                        "p530",
                        "p510",
                        "p540",
                        "p550",
                        "p560",
                        "p570",
                    ],
                )
                self.assertEqual(
                    result["state_keys"]["slot.p570.status"],
                    terminal_status,
                )

    def test_p680_visual_gate_reads_fresh_image_stage_before_handoff(self) -> None:
        cases = {
            "orchestration_pending_image_passed": (
                {
                    "orchestration": {
                        "passed": False,
                        "checks": [
                            {
                                "id": "orchestration.state_terminal",
                                "passed": False,
                                "kind": "rubric",
                                "message": "p680 is intentionally not published yet",
                            }
                        ],
                    },
                    "image": {
                        "passed": True,
                        "checks": [
                            {
                                "id": "image.visual_not_vector_like",
                                "passed": True,
                                "kind": "rubric",
                                "message": "visual quality passed",
                            }
                        ],
                    },
                    "asset": {
                        "passed": True,
                        "checks": [
                            {
                                "id": "asset.generation_provenance_app_server",
                                "passed": True,
                                "kind": "rubric",
                                "message": "asset provenance passed",
                            }
                        ],
                    },
                },
                False,
            ),
            "asset_stage_failed": (
                {
                    "asset": {
                        "passed": False,
                        "checks": [
                            {
                                "id": "asset.generation_provenance_app_server",
                                "passed": False,
                                "kind": "rubric",
                                "message": "asset provenance failed",
                            }
                        ],
                    },
                    "image": {
                        "passed": True,
                        "checks": [],
                    },
                },
                True,
            ),
            "image_checks_empty": (
                {
                    "asset": {
                        "passed": True,
                        "checks": [
                            {
                                "id": "asset.generation_provenance_app_server",
                                "passed": True,
                            }
                        ],
                    },
                    "image": {
                        "passed": True,
                        "checks": [],
                    },
                },
                True,
            ),
            "image_check_missing_result": (
                {
                    "asset": {
                        "passed": True,
                        "checks": [
                            {
                                "id": "asset.generation_provenance_app_server",
                                "passed": True,
                            }
                        ],
                    },
                    "image": {
                        "passed": True,
                        "checks": [
                            {
                                "id": "image.generation_provenance_app_server",
                                "passed": None,
                            }
                        ],
                    },
                },
                True,
            ),
            "image_check_missing_id": (
                {
                    "asset": {
                        "passed": True,
                        "checks": [
                            {
                                "id": "asset.generation_provenance_app_server",
                                "passed": True,
                            }
                        ],
                    },
                    "image": {
                        "passed": True,
                        "checks": [
                            {
                                "id": "",
                                "passed": True,
                            }
                        ],
                    },
                },
                True,
            ),
            "image_stage_missing": (
                {
                    "orchestration": {
                        "passed": False,
                        "checks": [],
                    }
                },
                True,
            ),
        }

        for label, (stages, should_raise) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)

                def fake_verify(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
                    (run_dir / "eval_report.json").write_text(
                        json.dumps(
                            {
                                "run_dir": str(run_dir.resolve()),
                                "stage_target": "p680",
                                "overall": {"passed": False},
                                "stages": stages,
                            },
                            ensure_ascii=False,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    return subprocess.CompletedProcess(
                        [],
                        1,
                        "",
                        "orchestration is not terminal before p680 handoff",
                    )

                with patch("server.image_gen_app.subprocess.run", fake_verify):
                    if should_raise:
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "p680 visual quality gate failed",
                        ):
                            image_gen_app._validate_p680_visual_quality(run_dir)
                    else:
                        image_gen_app._validate_p680_visual_quality(run_dir)

    def test_p680_terminal_gate_requires_successful_complete_verifier_report(
        self,
    ) -> None:
        passing_stages = {
            "orchestration": {
                "passed": True,
                "checks": [],
            },
            "asset": {
                "passed": True,
                "checks": [
                    {
                        "id": "asset.generation_provenance_app_server",
                        "passed": True,
                    }
                ],
            },
            "image": {
                "passed": True,
                "checks": [
                    {
                        "id": "image.generation_provenance_app_server",
                        "passed": True,
                    }
                ],
            },
        }
        cases = {
            "verifier_process_failed": (
                1,
                {"passed": True},
                passing_stages,
                True,
            ),
            "overall_failed": (
                0,
                {"passed": False},
                passing_stages,
                True,
            ),
            "emitted_stage_failed": (
                0,
                {"passed": True},
                {
                    **passing_stages,
                    "orchestration": {
                        "passed": False,
                        "checks": [
                            {
                                "id": "orchestration.state_terminal",
                                "passed": False,
                            }
                        ],
                    },
                },
                True,
            ),
            "all_emitted_stages_passed": (
                0,
                {"passed": True},
                passing_stages,
                False,
            ),
        }

        for label, (returncode, overall, stages, should_raise) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)

                def fake_verify(
                    *_args: Any,
                    **_kwargs: Any,
                ) -> subprocess.CompletedProcess[str]:
                    (run_dir / "eval_report.json").write_text(
                        json.dumps(
                            {
                                "run_dir": str(run_dir.resolve()),
                                "stage_target": "p680",
                                "overall": overall,
                                "stages": stages,
                            },
                            ensure_ascii=False,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    return subprocess.CompletedProcess(
                        [],
                        returncode,
                        "",
                        "terminal verifier failed" if returncode else "",
                    )

                with patch("server.image_gen_app.subprocess.run", fake_verify):
                    if should_raise:
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "p680 terminal verification failed",
                        ):
                            image_gen_app._validate_p680_visual_quality(
                                run_dir,
                                mode="terminal",
                            )
                    else:
                        image_gen_app._validate_p680_visual_quality(
                            run_dir,
                            mode="terminal",
                        )

    def test_p680_gate_rejects_all_failed_checks_including_partial_media(self) -> None:
        for unexpected_visual_failure in (False, True):
            with (
                self.subTest(
                    unexpected_visual_failure=unexpected_visual_failure
                ),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                run_id = "桃太郎_20260509_1200"
                run_dir = write_valid_p650_artifacts(root, run_id)
                write_failed_semantic_review_artifacts(
                    run_dir,
                    "image_prompt",
                    reviewed_entries=[
                        "scene10_cut01",
                        "scene10_cut02",
                        "scene10_cut03",
                    ],
                    failed_selectors=["scene10_cut2"],
                    blocked_entries=["scene10_cut2"],
                )
                image_gen_app.append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        "review.semantic.image_prompt.partial_media_allowed": "true",
                        "review.semantic.image_prompt.blocked_image_items": "scene10_cut2",
                        "review.semantic.image_prompt.blocked_image_item_count": "1",
                        "review.semantic.image_prompt.localization.status": "localized_to_image_items",
                    },
                )

                image_checks = [
                    {
                        "id": "image.output_files",
                        "passed": False,
                    },
                    {
                        "id": "image.generation_provenance_app_server",
                        "passed": False,
                    },
                    {
                        "id": "image.semantic_review_subagent_passed",
                        "passed": False,
                    },
                    {
                        "id": "image.visual_not_vector_like",
                        "passed": not unexpected_visual_failure,
                    },
                ]

                def fake_verify(
                    *_args: Any,
                    **_kwargs: Any,
                ) -> subprocess.CompletedProcess[str]:
                    (run_dir / "eval_report.json").write_text(
                        json.dumps(
                            {
                                "run_dir": str(run_dir.resolve()),
                                "stage_target": "p680",
                                "overall": {
                                    "passed": False,
                                    "failed_stages": ["image"],
                                },
                                "stages": {
                                    "orchestration": {
                                        "passed": True,
                                        "checks": [],
                                    },
                                    "asset": {
                                        "passed": True,
                                        "checks": [
                                            {
                                                "id": "asset.generation_provenance_app_server",
                                                "passed": True,
                                            }
                                        ],
                                    },
                                    "image": {
                                        "passed": False,
                                        "checks": image_checks,
                                    },
                                },
                            },
                            ensure_ascii=False,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    return subprocess.CompletedProcess(
                        [],
                        1,
                        "",
                        "partial image output verification",
                    )

                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch(
                        "server.image_gen_app.subprocess.run",
                        fake_verify,
                    ),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "p680 terminal verification failed",
                    ):
                        image_gen_app._validate_p680_visual_quality(
                            run_dir,
                            mode="terminal",
                        )

    def test_p680_visual_gate_fails_closed_when_existing_report_baseline_is_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "eval_report.json").write_text(
                json.dumps(
                    {
                        "run_dir": str(run_dir.resolve()),
                        "stage_target": "p680",
                        "overall": {"passed": False},
                        "stages": {
                            "orchestration": {
                                "passed": False,
                                "checks": [],
                            },
                            "asset": {
                                "passed": True,
                                "checks": [
                                    {
                                        "id": "asset.generation_provenance_app_server",
                                        "passed": True,
                                    }
                                ],
                            },
                            "image": {
                                "passed": True,
                                "checks": [
                                    {
                                        "id": "image.generation_provenance_app_server",
                                        "passed": True,
                                    }
                                ],
                            },
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            original_sha256 = image_gen_app._file_sha256
            hash_calls = 0

            def flaky_sha256(path: Path) -> str:
                nonlocal hash_calls
                hash_calls += 1
                if hash_calls == 1:
                    raise OSError("baseline read failed")
                return original_sha256(path)

            with (
                patch(
                    "server.image_gen_app.subprocess.run",
                    return_value=subprocess.CompletedProcess(
                        [],
                        1,
                        "",
                        "orchestration is pending",
                    ),
                ),
                patch(
                    "server.image_gen_app._file_sha256",
                    side_effect=flaky_sha256,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "p680 visual quality gate failed",
                ):
                    image_gen_app._validate_p680_visual_quality(run_dir)

    def test_validate_p560_asset_quality_classifies_only_visual_check_failures_as_retryable(self) -> None:
        cases = {
            "visual_only": (
                [
                    {
                        "id": "asset.visual_not_vector_like",
                        "passed": False,
                        "kind": "rubric",
                        "message": "generated asset is vector-like",
                    }
                ],
                True,
                "vector-like or low-detail raster image",
                "hero",
            ),
            "visual_and_provenance": (
                [
                    {
                        "id": "asset.visual_not_vector_like",
                        "passed": False,
                        "kind": "rubric",
                        "message": "generated asset is vector-like",
                    },
                    {
                        "id": "asset.generation_provenance_app_server",
                        "passed": False,
                        "kind": "rubric",
                        "message": "strict provenance is missing",
                    },
                ],
                False,
                "vector-like or low-detail raster image",
                "hero",
            ),
            "visual_with_non_blocking_warning": (
                [
                    {
                        "id": "asset.visual_not_vector_like",
                        "passed": False,
                        "kind": "rubric",
                        "message": "generated asset is vector-like",
                    },
                    {
                        "id": "asset.optional_visual_warning",
                        "passed": False,
                        "kind": "warning",
                        "message": "optional visual observation",
                    },
                ],
                True,
                "vector-like or low-detail raster image",
                "hero",
            ),
            "inspector_unavailable": (
                [
                    {
                        "id": "asset.visual_not_vector_like",
                        "passed": False,
                        "kind": "rubric",
                        "message": "asset inspection failed",
                    }
                ],
                False,
                "Pillow is unavailable",
                "hero",
            ),
            "non_bootstrap_asset": (
                [
                    {
                        "id": "asset.visual_not_vector_like",
                        "passed": False,
                        "kind": "rubric",
                        "message": "generated asset is vector-like",
                    }
                ],
                False,
                "vector-like or low-detail raster image",
                "referenced_asset",
            ),
            "p400_integrity": (
                [
                    {
                        "id": "p400.review_loop_integrity",
                        "passed": False,
                        "kind": "deterministic",
                        "message": "review digest is stale",
                    }
                ],
                False,
                "vector-like or low-detail raster image",
                "hero",
            ),
        }

        for label, (
            failed_checks,
            expected_retryable,
            visual_issue,
            failed_asset_id,
        ) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                eval_report = run_dir / "eval_report.json"
                (run_dir / "asset_generation_requests.md").write_text(
                    """# Asset Generation Requests

## hero

- tool: `codex_builtin_image`
- execution_lane: `bootstrap_builtin`
- reference_count: `0`
- output: `assets/characters/hero.png`

```api_prompt
実写映画風の主人公参照画像。
```
""",
                    encoding="utf-8",
                )

                def fake_verify(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
                    stage_names = (
                        "orchestration",
                        "research",
                        "story",
                        "visual_value",
                        "script",
                        "manifest",
                        "asset",
                    )
                    stages = {
                        stage_name: {
                            "stage": stage_name,
                            "passed": True,
                            "checks": [
                                {
                                    "id": f"{stage_name}.placeholder_pass",
                                    "passed": True,
                                    "kind": "rubric",
                                    "message": "passed",
                                }
                            ],
                            "details": {},
                        }
                        for stage_name in stage_names
                    }
                    stages["asset"] = {
                        "stage": "asset",
                        "passed": False,
                        "checks": failed_checks,
                        "details": {
                            "asset_visual_quality_samples": [
                                {
                                    "asset_id": failed_asset_id,
                                    "path": f"assets/characters/{failed_asset_id}.png",
                                    "issue": visual_issue,
                                }
                            ],
                            "asset_visual_quality_issues": [
                                f"{failed_asset_id}: {visual_issue}"
                            ],
                        },
                    }
                    payload = {
                        "run_dir": str(run_dir.resolve()),
                        "flow": "immersive",
                        "profile": "standard",
                        "stage_target": "p570",
                        "overall": {
                            "passed": False,
                            "failed_stages": ["asset"],
                        },
                        "stages": stages,
                    }
                    eval_report.write_text(
                        json.dumps(payload, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    return subprocess.CompletedProcess([], 1, "", "verification failed")

                with patch("server.image_gen_app.subprocess.run", fake_verify):
                    with self.assertRaises(image_gen_app.P560AssetGateError) as raised:
                        image_gen_app._validate_p560_asset_quality(run_dir)

                self.assertEqual(
                    raised.exception.retryable_visual_quality,
                    expected_retryable,
                )
                self.assertEqual(
                    set(raised.exception.failed_check_ids),
                    {
                        str(check["id"])
                        for check in failed_checks
                        if check.get("kind") != "warning"
                    },
                )

    def test_generate_create_images_fails_closed_on_non_visual_p570_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            image_gen_app.append_state_snapshot(
                run_dir / "state.txt",
                {
                    "slot.p550.status": "pending",
                    "slot.p560.status": "pending",
                    "slot.p570.status": "pending",
                },
            )
            generated_kinds: list[str] = []
            repair_prompts = AsyncMock()

            async def fake_generate_request_outputs(*, run_dir, kind):
                generated_kinds.append(kind)

            gate_error = image_gen_app.P560AssetGateError(
                "p560 asset gate failed: p400.review_loop_integrity",
                failed_check_ids=("p400.review_loop_integrity",),
                retryable_visual_quality=False,
            )
            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._generate_request_outputs", fake_generate_request_outputs),
                    patch("server.image_gen_app._generate_request_outputs_unlocked", fake_generate_request_outputs),
                    patch("server.image_gen_app._validate_p560_asset_quality", Mock(side_effect=gate_error)),
                    patch("server.image_gen_app._repair_bootstrap_asset_prompts", repair_prompts),
                    patch("server.image_gen_app._remove_bootstrap_asset_outputs", Mock()),
                    patch("server.image_gen_app._run_semantic_review", AsyncMock()),
                    patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "p400.review_loop_integrity",
                    ):
                        asyncio.run(
                            image_gen_app._generate_create_images(
                                "job-1",
                                run_id=run_id,
                            )
                        )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(generated_kinds, ["asset"])
        repair_prompts.assert_not_awaited()
        self.assertEqual(
            state["review.asset_visual_gate.status"],
            "blocked_non_visual_validation",
        )
        self.assertEqual(
            state["review.asset_visual_gate.failed_check_ids"],
            "p400.review_loop_integrity",
        )
        self.assertEqual(
            state["runtime.stage"],
            "p570_non_visual_gate_failed",
        )
        self.assertEqual(state["slot.p550.status"], "done")
        self.assertEqual(state["slot.p560.status"], "done")
        self.assertEqual(state["slot.p570.status"], "failed")
        self.assertEqual(state["slot.p660.status"], "pending")
        self.assertEqual(state["slot.p670.status"], "pending")
        self.assertEqual(state["slot.p680.status"], "pending")
        self.assertEqual(
            state["review.semantic.create_scene_media_generated"],
            "false",
        )

    def test_validate_p560_asset_quality_fails_closed_when_existing_report_baseline_is_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report_path = run_dir / "eval_report.json"
            report_path.write_text(
                json.dumps(
                    {
                        "run_dir": str(run_dir.resolve()),
                        "stage_target": "p570",
                        "overall": {"passed": False},
                        "stages": {
                            "asset": {
                                "passed": False,
                                "checks": [
                                    {
                                        "id": "asset.visual_not_vector_like",
                                        "passed": False,
                                        "kind": "rubric",
                                        "message": "stale visual failure",
                                    }
                                ],
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            stale_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()

            with (
                patch(
                    "server.image_gen_app._file_sha256",
                    side_effect=[OSError("baseline read failed"), stale_sha256],
                ),
                patch(
                    "server.image_gen_app.subprocess.run",
                    return_value=subprocess.CompletedProcess(
                        [],
                        1,
                        "",
                        "verifier crashed before rewriting eval report",
                    ),
                ),
            ):
                with self.assertRaises(image_gen_app.P560AssetGateError) as raised:
                    image_gen_app._validate_p560_asset_quality(run_dir)

        self.assertFalse(raised.exception.retryable_visual_quality)
        self.assertEqual(
            raised.exception.failed_check_ids,
            ("eval_report.baseline_unreadable",),
        )

    def test_validate_p560_asset_quality_fails_closed_on_inconsistent_eval_report_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)

            def fake_verify(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
                (run_dir / "eval_report.json").write_text(
                    json.dumps(
                        {
                            "run_dir": str(run_dir.resolve()),
                            "stage_target": "p570",
                            "overall": {"passed": True},
                            "stages": {
                                "asset": {
                                    "passed": False,
                                    "checks": [
                                        {
                                            "id": "asset.visual_not_vector_like",
                                            "passed": False,
                                            "kind": "rubric",
                                            "message": "inconsistent report",
                                        }
                                    ],
                                }
                            },
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess([], 1, "", "verification failed")

            with patch("server.image_gen_app.subprocess.run", fake_verify):
                with self.assertRaises(image_gen_app.P560AssetGateError) as raised:
                    image_gen_app._validate_p560_asset_quality(run_dir)

        self.assertFalse(raised.exception.retryable_visual_quality)
        self.assertEqual(
            raised.exception.failed_check_ids,
            ("eval_report.contract_mismatch",),
        )

    def test_validate_p560_asset_quality_normalizes_verifier_runtime_failures(self) -> None:
        cases = {
            "timeout": (
                subprocess.TimeoutExpired(cmd=["verify-pipeline"], timeout=300),
                "verifier.timeout",
            ),
            "spawn_failed": (
                OSError("python executable unavailable"),
                "verifier.spawn_failed",
            ),
        }
        for label, (verifier_error, expected_check_id) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                with patch(
                    "server.image_gen_app.subprocess.run",
                    side_effect=verifier_error,
                ):
                    with self.assertRaises(
                        image_gen_app.P560AssetGateError
                    ) as raised:
                        image_gen_app._validate_p560_asset_quality(run_dir)

                self.assertFalse(
                    raised.exception.retryable_visual_quality
                )
                self.assertEqual(
                    raised.exception.failed_check_ids,
                    (expected_check_id,),
                )

    def test_generate_create_images_stops_at_p570_after_ten_failed_asset_repairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            generated_kinds: list[str] = []
            repair_prompts = AsyncMock()
            semantic_review = AsyncMock()

            async def fake_generate_request_outputs(*, run_dir, kind):
                generated_kinds.append(kind)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._generate_request_outputs", fake_generate_request_outputs),
                    patch("server.image_gen_app._generate_request_outputs_unlocked", fake_generate_request_outputs),
                    patch(
                        "server.image_gen_app._validate_p560_asset_quality",
                        Mock(
                            side_effect=image_gen_app.P560AssetGateError(
                                "p560 asset gate failed: bootstrap asset is vector-like",
                                failed_check_ids=("asset.visual_not_vector_like",),
                                retryable_visual_quality=True,
                            )
                        ),
                    ),
                    patch("server.image_gen_app._repair_bootstrap_asset_prompts", repair_prompts),
                    patch("server.image_gen_app._remove_bootstrap_asset_outputs", Mock()),
                    patch("server.image_gen_app._run_semantic_review", semantic_review),
                    patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
                ):
                    result = asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertFalse(result)
        self.assertEqual(generated_kinds, ["asset"] * 10)
        self.assertEqual(repair_prompts.await_count, 9)
        # Initial six-stage fixed point plus one complete six-stage
        # re-entry after each of the nine request/snapshot prompt repairs.
        self.assertEqual(semantic_review.await_count, 60)
        self.assertEqual(
            state["review.asset_visual_gate.status"],
            "needs_frontend_review",
        )
        self.assertEqual(state["review.asset_visual_gate.attempts"], "10")
        self.assertEqual(state["slot.p570.status"], "awaiting_approval")
        self.assertEqual(state["slot.p660.status"], "pending")
        self.assertEqual(state["slot.p680.status"], "pending")

    def test_generate_create_images_blocks_media_generation_when_semantic_review_fails(self) -> None:
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
                    patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
                    patch("server.image_gen_app._mark_image_generation_review_ready", mark_ready),
                ):
                    with self.assertRaisesRegex(RuntimeError, "semantic review failed before media generation"):
                        asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(generated_kinds, [])
        self.assertEqual(state["runtime.stage"], "semantic_review_failed_before_media_generation")
        self.assertEqual(state["review.semantic.create_media_generated"], "false")
        self.assertEqual(state["review.semantic.create_blocking_stage"], "scene_set")
        self.assertEqual(state["slot.p410.status"], "failed")
        self.assertEqual(state["slot.p660.status"], "pending")
        self.assertIn("blocked before image generation", state["slot.p660.note"])
        mark_ready.assert_not_called()

    def test_generate_create_images_blocks_media_generation_when_semantic_transport_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "桃太郎_20260509_1200"
            run_dir = write_valid_p650_artifacts(root, run_id)
            supervisor_result_path = run_dir / "logs/orchestration/p600.supervisor_result.json"
            supervisor_result_path.parent.mkdir(parents=True, exist_ok=True)
            supervisor_result_path.write_text(
                json.dumps({"bucket": "p600", "status": "done", "completed_slots": ["p660", "p670", "p680"]}) + "\n",
                encoding="utf-8",
            )
            generated_kinds: list[str] = []
            mark_ready = Mock()

            async def fake_generate_request_outputs(*, run_dir: Path, kind: str) -> None:
                generated_kinds.append(kind)

            async def fake_run_semantic_review(job_id: str, *, run_dir: Path, stage: str) -> None:
                if stage == "scene_set":
                    image_gen_app.append_state_snapshot(
                        run_dir / "state.txt",
                        {
                            "review.semantic.scene_set.repair.status": "in_progress",
                            "review.semantic.scene_set.repair.round": "1",
                            "review.semantic.scene_set.repair.pending.updated_at": "2026-07-12T20:00:00+09:00",
                        },
                    )
                    raise CodexAppServerTransportError("turn timed out")
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
                    patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
                    patch("server.image_gen_app._mark_image_generation_review_ready", mark_ready),
                ):
                    with self.assertRaisesRegex(RuntimeError, "semantic review blocked by Codex app-server transport failure"):
                        asyncio.run(image_gen_app._generate_create_images("job-1", run_id=run_id))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            supervisor_result = json.loads(supervisor_result_path.read_text(encoding="utf-8"))
            transport_logs = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in (run_dir / "logs/app_server/semantic_review").glob("*.json")
            ]
            transport_log = next(
                payload for payload in transport_logs if payload.get("status") == "transport_blocked_before_image_generation"
            )
            create_failure_diagnostics = image_gen_app._create_job_failure_diagnostics(run_dir)

        self.assertEqual(generated_kinds, [])
        self.assertEqual(state["review.semantic.scene_set.transport.status"], "failed")
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "blocked_transport")
        self.assertEqual(state["runtime.stage"], "semantic_review_blocked_transport")
        self.assertEqual(state["runtime.failure.stage"], "scene_set")
        self.assertEqual(state["runtime.failure.phase"], "semantic_producer_repair")
        self.assertEqual(state["runtime.failure.error_kind"], "timeout")
        self.assertEqual(state["image_generation.status"], "not_started")
        self.assertEqual(state["image_generation.started"], "false")
        self.assertEqual(state["image_generation.generated_count"], "0")
        self.assertEqual(state["image_generation.blocked_by"], "semantic.scene_set.semantic_producer_repair")
        self.assertEqual(state["orchestration.p600.supervisor.status"], "invalidated")
        self.assertEqual(state["orchestration.p600.supervisor.invalidated_by"], "semantic.scene_set.transport.timeout")
        self.assertEqual(supervisor_result["status"], "invalidated")
        self.assertEqual(supervisor_result["previous_status"], "done")
        self.assertEqual(supervisor_result["invalidated_by"], "semantic.scene_set.transport.timeout")
        self.assertEqual(transport_log["request"]["stage"], "scene_set")
        self.assertEqual(transport_log["request"]["phase"], "semantic_producer_repair")
        self.assertEqual(transport_log["response"]["imageGenerationStatus"], "not_started")
        self.assertFalse(transport_log["response"]["imageGenerationStarted"])
        self.assertEqual(transport_log["response"]["p600SupervisorStatus"], "invalidated")
        self.assertEqual(create_failure_diagnostics["failureStage"], "scene_set")
        self.assertEqual(create_failure_diagnostics["failurePhase"], "semantic_producer_repair")
        self.assertEqual(create_failure_diagnostics["imageGenerationStatus"], "not_started")
        self.assertEqual(state["slot.p410.status"], "failed")
        self.assertNotIn("review.semantic.create_media_generated", state)
        self.assertEqual(state["slot.p660.status"], "pending")
        self.assertIn("blocked before image generation", state["slot.p660.note"])
        mark_ready.assert_not_called()

    def test_semantic_review_failure_invokes_producer_repair_then_rereviews(self) -> None:
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
                        repair_paths = semantic_repair_relpaths(stage, 1)
                        (run_dir / repair_paths["report"]).write_text("status: done\nchanged_artifacts: [script.md]\n", encoding="utf-8")
                        return None
                    review_turns += 1
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    status = "failed" if review_turns == 1 else "passed"
                    failed_selectors = "[scene_1]" if status == "failed" else "[]"
                    (run_dir / paths["report"]).write_text(
                        f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: {failed_selectors}\nfindings: []\nfailed_selectors: {failed_selectors}\n",
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
            raw_state = (run_dir / "state.txt").read_text(encoding="utf-8")
            repair_paths = semantic_repair_relpaths(stage, 1)
            repair_prompt_exists = (run_dir / repair_paths["prompt"]).exists()
            repair_report_exists = (run_dir / repair_paths["report"]).exists()
            debug_logs = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((run_dir / "logs" / "app_server" / "semantic_review_producer_repair").glob("*.json"))
            ]

        self.assertEqual(review_turns, 2)
        self.assertEqual(repair_turns, 1)
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.repair.status"], "done")
        self.assertEqual(state["slot.p410.status"], "done")
        self.assertIn("review.semantic.scene_set.loop.status=repairing", raw_state)
        self.assertIn("review.semantic.scene_set.repair.status=in_progress", raw_state)
        self.assertIn("review.semantic.scene_set.repair.target_selectors=scene_1", raw_state)
        self.assertEqual(state["review.semantic.scene_set.repair.changed_artifacts_detected"], "script.md")
        self.assertEqual(state["review.semantic.scene_set.repair.report_status"], "done")
        self.assertIn("review.semantic.scene_set.repair.source_fingerprint.before=", raw_state)
        self.assertIn("review.semantic.scene_set.repair.source_fingerprint.after=", raw_state)
        self.assertTrue(repair_prompt_exists)
        self.assertTrue(repair_report_exists)
        started_log = next(log for log in debug_logs if log["status"] == "started")
        completed_log = next(log for log in debug_logs if log["status"] == "completed")
        self.assertEqual(started_log["request"]["targetSelectors"], ["scene_1"])
        self.assertEqual(started_log["request"]["sourceFingerprintBefore"]["artifacts"], ["script.md"])
        self.assertEqual(completed_log["response"]["changedArtifacts"], ["script.md"])
        self.assertEqual(completed_log["response"]["reportStatus"], "done")

    def test_semantic_review_reuses_non_stale_passed_report_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "asset_plan"
            source_path = run_dir / "asset_plan.md"
            source_path.write_text("# asset plan\n\nmeaningful source\n", encoding="utf-8")
            write_semantic_review_artifacts(run_dir, stage)

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

    def test_image_prompt_semantic_review_rejects_request_revision_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "sample_run"
            run_dir = write_valid_p650_artifacts(root, run_id)
            reviewed_revision = load_request_snapshot(
                run_dir / "image_generation_request_snapshot.json",
                run_dir=run_dir,
            ).request_revision
            passed = image_gen_app.SemanticReviewStatus(
                status="passed",
                entry_count=3,
                errors=(),
            )

            async def mutate_request_during_review(*_args, **_kwargs):
                result = image_gen.update_request_prompts(
                    run_dir,
                    "scene",
                    {
                        "scene10_cut1": (
                            "実写映画風の横長16:9カット。レビュー中に変更された別の瞬間。"
                        )
                    },
                )
                self.assertEqual(result["updated"], ["scene10_cut1"])
                current_revision = load_request_snapshot(
                    run_dir / "image_generation_request_snapshot.json",
                    run_dir=run_dir,
                ).request_revision
                self.assertNotEqual(current_revision, reviewed_revision)
                return passed

            freeze_marker = Mock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._prepare_image_prompt_request_revision_for_review",
                    return_value=reviewed_revision,
                ),
                patch(
                    "server.image_gen_app._reusable_passed_semantic_review",
                    return_value=None,
                ),
                patch(
                    "server.image_gen_app._run_semantic_review_once",
                    side_effect=mutate_request_during_review,
                ),
                patch(
                    "server.image_gen_app._mark_image_prompt_request_freeze_done",
                    freeze_marker,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "image prompt request revision changed during semantic review",
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review(
                            "job-1",
                            run_dir=run_dir,
                            stage="image_prompt",
                            max_attempts=1,
                        )
                    )

            freeze_marker.assert_not_called()
            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertNotEqual(state.get("review.semantic.image_prompt.loop.status"), "passed")

    def test_semantic_reviewer_client_is_scrubbed_and_scoped_to_run_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "asset_plan"
            client_kwargs: list[dict[str, Any]] = []
            thread_kwargs: list[dict[str, Any]] = []
            turn_kwargs: list[dict[str, Any]] = []

            def fake_build_pack(cmd, **_kwargs):
                write_semantic_review_artifacts(run_dir, stage)
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["report"]).write_text(
                    "status: pending\nreviewed_entries: []\nblocked_entries: []\nfailed_selectors: []\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **kwargs):
                    client_kwargs.append(kwargs)

                async def start_thread(self, **kwargs):
                    thread_kwargs.append(kwargs)
                    return "thread-1"

                async def run_turn(self, **kwargs):
                    turn_kwargs.append(kwargs)
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    (run_dir / paths["report"]).write_text(
                        "status: passed\nreviewed_entries: [asset_plan_entry_1]\n"
                        "blocked_entries: []\nfailed_selectors: []\nfindings: []\nnotes: []\n",
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage=stage,
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

        self.assertTrue(result.passed, result.errors)
        self.assertEqual(
            client_kwargs,
            [{"cwd": run_dir.resolve(), "scrub_sensitive_env": True}],
        )
        self.assertEqual(
            thread_kwargs,
            [
                {
                    "cwd": run_dir.resolve(),
                    "approval_policy": "never",
                    "sandbox": "read-only",
                }
            ],
        )
        self.assertEqual(turn_kwargs[0]["cwd"], run_dir.resolve())

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
                "status: passed\nreviewed_entries: [asset_1]\nblocked_entries: []\n"
                "failed_selectors: []\nfindings: []\n",
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
                        "status: passed\nreviewed_entries: [asset_1]\nblocked_entries: []\n"
                        "failed_selectors: []\nfindings: []\n",
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
            review_prompts: list[str] = []

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
                    review_prompts.append(text)
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    status = "passed" if review_turns == 3 else "failed"
                    findings = "[]" if status == "passed" else "[remaining semantic drift]"
                    (run_dir / paths["report"]).write_text(
                        f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: []\n"
                        f"failed_selectors: []\nfindings: {findings}\n",
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
                asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=3))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(review_turns, 3)
        self.assertEqual(repair_rounds, [1, 2])
        self.assertNotIn("Final Attempt Review Policy", review_prompts[0])
        self.assertNotIn("Final Attempt Review Policy", review_prompts[1])
        self.assertIn("Final Attempt Review Policy", review_prompts[2])
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.repair.status"], "done")
        self.assertEqual(state["slot.p410.status"], "done")

    def test_semantic_review_explicit_one_attempt_skips_repair_with_state_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            review_prompts: list[str] = []
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
                    nonlocal repair_turns
                    if "Semantic QA Producer Repair" in text:
                        repair_turns += 1
                        return None
                    review_prompts.append(text)
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    (run_dir / paths["report"]).write_text(
                        "status: failed\nreviewed_entries: [scene_1]\nblocked_entries: [scene_1]\n"
                        "failed_selectors: [scene_1]\nfindings: [remaining semantic drift]\n",
                        encoding="utf-8",
                    )
                    return None

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                patch.dict(os.environ, {"TOC_SEMANTIC_REVIEW_MAX_ATTEMPTS": "1"}),
            ):
                with self.assertRaisesRegex(RuntimeError, "failed after 1 attempt"):
                    asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(len(review_prompts), 1)
        self.assertEqual(repair_turns, 0)
        self.assertIn("Final Attempt Review Policy", review_prompts[0])
        self.assertEqual(state["review.semantic.scene_set.loop.max_attempts"], "1")
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "failed")
        self.assertEqual(state["review.semantic.scene_set.repair.skipped"], "true")
        self.assertEqual(state["review.semantic.scene_set.repair.skipped_reason"], "max_attempts_1")

    def test_semantic_review_final_failure_records_report_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            stage = "scene_set"

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text("# collection\n\nscene meaning under review\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 2,
                            "entry_ids": ["scene:10", "scene:20"],
                            "source_artifacts": ["script.md"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
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

                async def run_turn(self, **_kwargs):
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    (run_dir / paths["report"]).write_text(
                        "\n".join(
                            [
                                "status: failed",
                                "reviewed_entries: [scene:10, scene:20]",
                                "blocked_entries: [scene:10]",
                                "failed_selectors: [scene10]",
                                "reason_keys: [semantic_contract_missing, causal_proof_weak]",
                                "findings:",
                                "  - concrete scene meaning is missing",
                                "",
                            ]
                        ),
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
                with self.assertRaisesRegex(RuntimeError, "semantic review failed after 1 attempt"):
                    asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=1))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            final_logs = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((run_dir / "logs" / "app_server" / "semantic_review").glob("*.json"))
                if json.loads(path.read_text(encoding="utf-8")).get("status") == "failed_after_max_attempts"
            ]

        self.assertEqual(state["review.semantic.scene_set.loop.status"], "failed")
        self.assertEqual(state["review.semantic.scene_set.failure.report_status"], "failed")
        self.assertEqual(state["review.semantic.scene_set.failure.failed_selectors"], "scene10")
        self.assertEqual(state["review.semantic.scene_set.failure.blocked_entries"], "scene:10")
        self.assertEqual(state["review.semantic.scene_set.failure.reason_keys"], "semantic_contract_missing, causal_proof_weak")
        self.assertEqual(state["review.semantic.scene_set.repair.skipped"], "true")
        self.assertEqual(state["review.semantic.scene_set.repair.skipped_reason"], "max_attempts_1")
        self.assertEqual(state["slot.p410.note"], "contextless semantic scene_set review failed without repair")
        self.assertEqual(final_logs[-1]["response"]["failedSelectors"], ["scene10"])
        self.assertEqual(final_logs[-1]["response"]["reasonKeys"], ["semantic_contract_missing", "causal_proof_weak"])

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

    def test_semantic_review_retries_missing_output_then_accepts_json_without_repair(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            stage = "scene_set"
            repair = AsyncMock()
            review_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                (run_dir / paths["collection"]).write_text(
                    "# collection\n\nscene meaning under review\n",
                    encoding="utf-8",
                )
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 1,
                            "entry_ids": ["scene:10"],
                            "source_artifacts": ["script.md"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (run_dir / paths["prompt"]).write_text(
                    "# review prompt\n",
                    encoding="utf-8",
                )
                (run_dir / paths["report"]).write_text(
                    "status: pending\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, **_kwargs):
                    nonlocal review_turns
                    review_turns += 1
                    if review_turns == 1:
                        return [
                            {
                                "method": "item/completed",
                                "params": {
                                    "item": {
                                        "type": "agentMessage",
                                        "phase": "final_answer",
                                        "text": (
                                            "Review completed without the "
                                            "required verdict."
                                        ),
                                    }
                                },
                            }
                        ]
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    scope = json.loads(
                        (run_dir / paths["scope"]).read_text(encoding="utf-8")
                    )
                    verdict = {
                        "status": "passed",
                        "semantic_review_input_digest": scope[
                            "semantic_review_input_digest"
                        ],
                        "reviewed_entries": ["scene:10"],
                        "blocked_entries": [],
                        "findings": [],
                        "failed_selectors": [],
                        "reason_keys": [],
                        "notes": [],
                    }
                    return [
                        {
                            "method": "item/completed",
                            "params": {
                                "item": {
                                    "type": "agentMessage",
                                    "phase": "final_answer",
                                    "text": json.dumps(
                                        verdict,
                                        ensure_ascii=False,
                                    ),
                                }
                            },
                        }
                    ]

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
                patch(
                    "server.image_gen_app._run_semantic_review_producer_repair",
                    repair,
                ),
            ):
                asyncio.run(
                    image_gen_app._run_semantic_review(
                        "job-1",
                        run_dir=run_dir,
                        stage=stage,
                        max_attempts=2,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            report_text = (
                run_dir / image_gen_app.semantic_review_relpaths(stage)["report"]
            ).read_text(encoding="utf-8")

        repair.assert_not_awaited()
        self.assertEqual(review_turns, 2)
        self.assertIn("status: passed", report_text)
        self.assertEqual(
            state["review.semantic.scene_set.report.source"],
            "agent_message_transport_fallback",
        )
        self.assertEqual(
            state["review.semantic.scene_set.output_contract.status"],
            "recovered",
        )
        self.assertEqual(
            state["review.semantic.scene_set.output_contract.retry_count"],
            "1",
        )
        self.assertEqual(
            state["review.semantic.scene_set.transport.status"],
            "passed",
        )
        self.assertEqual(
            state["review.semantic.scene_set.loop.status"],
            "passed",
        )

    def test_semantic_review_missing_final_verdict_is_output_contract_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            stage = "scene_set"
            repair = AsyncMock()

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                (run_dir / paths["collection"]).write_text(
                    "# collection\n\nscene meaning under review\n",
                    encoding="utf-8",
                )
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 1,
                            "entry_ids": ["scene:10"],
                            "source_artifacts": ["script.md"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (run_dir / paths["prompt"]).write_text(
                    "# review prompt\n",
                    encoding="utf-8",
                )
                (run_dir / paths["report"]).write_text(
                    "status: pending\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, **_kwargs):
                    return [
                        {
                            "method": "item/completed",
                            "params": {
                                "item": {
                                    "type": "agentMessage",
                                    "phase": "final_answer",
                                    "text": "Review finished, but no report was emitted.",
                                }
                            },
                        }
                    ]

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
                patch(
                    "server.image_gen_app._run_semantic_review_producer_repair",
                    repair,
                ),
            ):
                with self.assertRaisesRegex(
                    CodexAppServerTransportError,
                    "semantic review output contract",
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review(
                            "job-1",
                            run_dir=run_dir,
                            stage=stage,
                            max_attempts=2,
                        )
                    )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        repair.assert_not_awaited()
        self.assertEqual(
            state["review.semantic.scene_set.transport.status"],
            "failed",
        )
        self.assertEqual(
            state["review.semantic.scene_set.transport.error_kind"],
            "output_contract_failed",
        )
        self.assertEqual(
            state["review.semantic.scene_set.loop.status"],
            "blocked_transport",
        )

    def test_semantic_review_does_not_promote_commentary_when_final_answer_is_malformed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            stage = "scene_set"
            repair = AsyncMock()
            review_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                (run_dir / paths["collection"]).write_text(
                    "# collection\n\nscene meaning under review\n",
                    encoding="utf-8",
                )
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 1,
                            "entry_ids": ["scene:10"],
                            "source_artifacts": ["script.md"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (run_dir / paths["prompt"]).write_text(
                    "# review prompt\n",
                    encoding="utf-8",
                )
                (run_dir / paths["report"]).write_text(
                    "status: pending\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, **_kwargs):
                    nonlocal review_turns
                    review_turns += 1
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    scope = json.loads(
                        (run_dir / paths["scope"]).read_text(encoding="utf-8")
                    )
                    verdict = {
                        "status": "passed",
                        "semantic_review_input_digest": scope[
                            "semantic_review_input_digest"
                        ],
                        "reviewed_entries": ["scene:10"],
                        "blocked_entries": [],
                        "findings": [],
                        "failed_selectors": [],
                        "reason_keys": [],
                        "notes": [],
                    }
                    return [
                        {
                            "method": "item/completed",
                            "params": {
                                "item": {
                                    "type": "agentMessage",
                                    "phase": "commentary",
                                    "text": json.dumps(
                                        verdict,
                                        ensure_ascii=False,
                                    ),
                                }
                            },
                        },
                        {
                            "method": "item/completed",
                            "params": {
                                "item": {
                                    "type": "agentMessage",
                                    "phase": "final_answer",
                                    "text": '{"status": "passed"',
                                }
                            },
                        },
                    ]

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
                patch(
                    "server.image_gen_app._run_semantic_review_producer_repair",
                    repair,
                ),
            ):
                with self.assertRaisesRegex(
                    CodexAppServerTransportError,
                    "semantic review output contract",
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review(
                            "job-1",
                            run_dir=run_dir,
                            stage=stage,
                            max_attempts=2,
                        )
                    )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        repair.assert_not_awaited()
        self.assertEqual(review_turns, 2)
        self.assertEqual(
            state["review.semantic.scene_set.transport.error_kind"],
            "output_contract_failed",
        )
        self.assertEqual(
            state["review.semantic.scene_set.loop.status"],
            "blocked_transport",
        )

    def test_semantic_review_wrong_digest_is_output_contract_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            stage = "scene_set"

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                (run_dir / paths["collection"]).write_text(
                    "# collection\n\nscene meaning under review\n",
                    encoding="utf-8",
                )
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 1,
                            "entry_ids": ["scene:10"],
                            "source_artifacts": ["script.md"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (run_dir / paths["prompt"]).write_text(
                    "# review prompt\n",
                    encoding="utf-8",
                )
                (run_dir / paths["report"]).write_text(
                    "status: pending\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, **_kwargs):
                    verdict = {
                        "status": "passed",
                        "semantic_review_input_digest": "sha256:" + ("0" * 64),
                        "reviewed_entries": ["scene:10"],
                        "blocked_entries": [],
                        "findings": [],
                        "failed_selectors": [],
                        "reason_keys": [],
                        "notes": [],
                    }
                    return [
                        {
                            "method": "item/completed",
                            "params": {
                                "item": {
                                    "type": "agentMessage",
                                    "phase": "final_answer",
                                    "text": json.dumps(
                                        verdict,
                                        ensure_ascii=False,
                                    ),
                                }
                            },
                        }
                    ]

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
            ):
                with self.assertRaisesRegex(
                    CodexAppServerTransportError,
                    "semantic review output contract",
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review_once(
                            "job-1",
                            run_dir=run_dir,
                            stage=stage,
                            attempt=1,
                            max_attempts=2,
                            final_attempt=False,
                        )
                    )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(
            state["review.semantic.scene_set.transport.error_kind"],
            "output_contract_failed",
        )
        self.assertEqual(
            state["review.semantic.scene_set.loop.status"],
            "blocked_transport",
        )

    def test_semantic_review_salvages_json_verdict_from_transport_exception_transcript(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            stage = "scene_set"

            def fake_build_pack(cmd, **_kwargs):
                paths = image_gen_app.semantic_review_relpaths(stage)
                (run_dir / paths["collection"]).parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                (run_dir / paths["collection"]).write_text(
                    "# collection\n\nscene meaning under review\n",
                    encoding="utf-8",
                )
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 1,
                            "entry_ids": ["scene:10"],
                            "source_artifacts": ["script.md"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (run_dir / paths["prompt"]).write_text(
                    "# review prompt\n",
                    encoding="utf-8",
                )
                (run_dir / paths["report"]).write_text(
                    "status: pending\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, **_kwargs):
                    paths = image_gen_app.semantic_review_relpaths(stage)
                    scope = json.loads(
                        (run_dir / paths["scope"]).read_text(encoding="utf-8")
                    )
                    verdict = {
                        "status": "passed",
                        "semantic_review_input_digest": scope[
                            "semantic_review_input_digest"
                        ],
                        "reviewed_entries": ["scene:10"],
                        "blocked_entries": [],
                        "findings": [],
                        "failed_selectors": [],
                        "reason_keys": [],
                        "notes": [],
                    }
                    transcript = [
                        {
                            "method": "item/completed",
                            "params": {
                                "item": {
                                    "type": "agentMessage",
                                    "phase": "final_answer",
                                    "text": json.dumps(
                                        verdict,
                                        ensure_ascii=False,
                                    ),
                                }
                            },
                        }
                    ]
                    raise CodexAppServerTransportError(
                        "stream disconnected before turn/completed",
                        transcript=transcript,
                    )

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage=stage,
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertTrue(result.passed, result.errors)
        self.assertEqual(
            state["review.semantic.scene_set.transport.status"],
            "passed",
        )

    def test_semantic_review_no_progress_timeout_blocks_as_transport(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"

            async def never_finishes(*_args, **_kwargs):
                await asyncio.Event().wait()

            with (
                patch("server.image_gen_app._run_semantic_review_once", never_finishes),
                patch("server.image_gen_app._semantic_review_no_progress_timeout_seconds", lambda: 0.01),
                patch("server.image_gen_app.SEMANTIC_TURN_ARTIFACT_POLL_SECONDS", 0.01),
            ):
                with self.assertRaisesRegex(CodexAppServerTransportError, "timed out"):
                    asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(state["review.semantic.scene_set.loop.status"], "blocked_transport")
        self.assertEqual(state["review.semantic.scene_set.transport.status"], "failed")
        self.assertEqual(state["review.semantic.scene_set.transport.error_kind"], "timeout")
        self.assertEqual(state["review.semantic.scene_set.watchdog.status"], "no_progress_timeout")
        self.assertEqual(state["runtime.app_server.transport.status"], "failed")

    def test_semantic_review_progress_resets_no_progress_watchdog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            paths = image_gen_app.semantic_review_relpaths(stage)
            (run_dir / paths["report"]).parent.mkdir(parents=True, exist_ok=True)

            async def progressing_review(*_args, **_kwargs):
                for index in range(4):
                    (run_dir / paths["report"]).write_text(f"status: pending\nprogress: {index}\n", encoding="utf-8")
                    if index < 3:
                        await asyncio.sleep(0.015)
                return image_gen_app.SemanticReviewStatus(status="passed", entry_count=1, errors=())

            with (
                patch("server.image_gen_app._run_semantic_review_once", progressing_review),
                patch("server.image_gen_app._semantic_review_no_progress_timeout_seconds", lambda: 0.03),
                patch("server.image_gen_app.SEMANTIC_TURN_ARTIFACT_POLL_SECONDS", 0.005),
            ):
                asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=1))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.watchdog.status"], "completed")

    def test_scene_detail_semantic_review_runs_per_scene_shards_with_env_concurrency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            stage = "scene_detail"
            paths = image_gen_app.semantic_review_relpaths(stage)
            active_turns = 0
            max_active_turns = 0
            review_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                collection = [
                    "# Semantic Review Collection: scene_detail",
                    "",
                    "## scene:10",
                    "",
                    "```json",
                    json.dumps({"id": "scene:10", "selector": "scene10"}, ensure_ascii=False),
                    "```",
                    "",
                    "## scene:20",
                    "",
                    "```json",
                    json.dumps({"id": "scene:20", "selector": "scene20"}, ensure_ascii=False),
                    "```",
                    "",
                    "## scene:30",
                    "",
                    "```json",
                    json.dumps({"id": "scene:30", "selector": "scene30"}, ensure_ascii=False),
                    "```",
                    "",
                ]
                (run_dir / paths["collection"]).write_text("\n".join(collection), encoding="utf-8")
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 3,
                            "entry_ids": ["scene:10", "scene:20", "scene:30"],
                            "source_artifacts": ["script.md"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
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
                    nonlocal active_turns, max_active_turns, review_turns
                    active_turns += 1
                    max_active_turns = max(max_active_turns, active_turns)
                    review_turns += 1
                    try:
                        await asyncio.sleep(0.02)
                        entry_id = text.split("Review only shard entry `", 1)[1].split("`", 1)[0]
                        return semantic_agent_report_transcript(
                            text,
                            status="passed",
                            entry_id=entry_id,
                        )
                    finally:
                        active_turns -= 1

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                patch.dict(os.environ, {"TOC_SCENE_DETAIL_REVIEW_CONCURRENCY": "2"}),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage=stage,
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            report = (run_dir / paths["report"]).read_text(encoding="utf-8")

        self.assertTrue(result.passed, result.errors)
        self.assertEqual(review_turns, 3)
        self.assertEqual(max_active_turns, 2)
        self.assertEqual(state["review.semantic.scene_detail.shards.concurrency"], "2")
        self.assertEqual(state["review.semantic.scene_detail.shards.count"], "3")
        self.assertEqual(state["review.semantic.scene_detail.shards.status"], "passed")
        self.assertIn("status: passed", report)
        self.assertIn("scene:10", report)
        self.assertIn("scene:20", report)
        self.assertIn("scene:30", report)

    def test_scene_detail_shard_failure_preserves_findings_for_repair_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            stage = "scene_detail"
            paths = image_gen_app.semantic_review_relpaths(stage)

            def fake_build_pack(cmd, **_kwargs):
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text(
                    "\n".join(
                        [
                            "# Semantic Review Collection: scene_detail",
                            "",
                            "## scene:10",
                            "",
                            "```json",
                            json.dumps({"id": "scene:10", "selector": "scene10"}, ensure_ascii=False),
                            "```",
                            "",
                            "## scene:20",
                            "",
                            "```json",
                            json.dumps({"id": "scene:20", "selector": "scene20"}, ensure_ascii=False),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 2,
                            "entry_ids": ["scene:10", "scene:20"],
                            "source_artifacts": ["script.md"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
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
                    entry_id = text.split("Review only shard entry `", 1)[1].split("`", 1)[0]
                    if entry_id == "scene:20":
                        return semantic_agent_report_transcript(
                            text,
                            status="failed",
                            entry_id=entry_id,
                            finding="causal turn is not visible in the scene detail",
                            reason_key="scene_detail_cut_support_weak",
                        )
                    return semantic_agent_report_transcript(
                        text,
                        status="passed",
                        entry_id=entry_id,
                    )

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                patch.dict(os.environ, {"TOC_SCENE_DETAIL_REVIEW_CONCURRENCY": "2"}),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage=stage,
                        attempt=1,
                        max_attempts=2,
                        final_attempt=False,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            report = (run_dir / paths["report"]).read_text(encoding="utf-8")

        self.assertFalse(result.passed)
        self.assertEqual(state["review.semantic.scene_detail.shards.status"], "failed")
        self.assertEqual(state["review.semantic.scene_detail.shards.failed_count"], "1")
        self.assertIn("blocked_entries:\n  - scene:20", report)
        self.assertIn("failed_selectors:\n  - scene:20", report)
        self.assertIn("causal turn is not visible in the scene detail", report)
        self.assertIn("scene_detail_cut_support_weak", report)

    def test_semantic_review_final_attempt_prompt_biases_nonfatal_issues_to_passed(self) -> None:
        prompt = image_gen_app._semantic_review_prompt_for_attempt(
            "# review prompt\n",
            stage="cut_blueprint",
            final_attempt=True,
        )

        self.assertIn("Final Attempt Review Policy", prompt)
        self.assertIn("Use `status: passed` unless you find a fatal defect", prompt)
        self.assertIn("If you pass with reservations", prompt)

    def test_semantic_review_nonfinal_attempt_prompt_is_unchanged(self) -> None:
        base = "# review prompt\n"

        prompt = image_gen_app._semantic_review_prompt_for_attempt(
            base,
            stage="cut_blueprint",
            final_attempt=False,
        )

        self.assertEqual(prompt, base)

    def test_scene_detail_shard_transport_timeout_is_aggregated_for_repair_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            stage = "scene_detail"
            paths = image_gen_app.semantic_review_relpaths(stage)

            def fake_build_pack(cmd, **_kwargs):
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text(
                    "\n".join(
                        [
                            "# Semantic Review Collection: scene_detail",
                            "",
                            "## scene:10",
                            "",
                            "```json",
                            json.dumps({"id": "scene:10", "selector": "scene10"}, ensure_ascii=False),
                            "```",
                            "",
                            "## scene:20",
                            "",
                            "```json",
                            json.dumps({"id": "scene:20", "selector": "scene20"}, ensure_ascii=False),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 2,
                            "entry_ids": ["scene:10", "scene:20"],
                            "source_artifacts": ["script.md"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
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
                    entry_id = text.split("Review only shard entry `", 1)[1].split("`", 1)[0]
                    if entry_id == "scene:20":
                        raise CodexAppServerTransportError("turn timed out")
                    return semantic_agent_report_transcript(
                        text,
                        status="passed",
                        entry_id=entry_id,
                    )

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                patch.dict(
                    os.environ,
                    {
                        "TOC_SCENE_DETAIL_REVIEW_CONCURRENCY": "2",
                        "TOC_SCENE_DETAIL_TRANSPORT_RETRY_ATTEMPTS": "2",
                    },
                ),
            ):
                with self.assertRaisesRegex(CodexAppServerTransportError, "scene_detail shard transport failed"):
                    asyncio.run(
                        image_gen_app._run_semantic_review_once(
                            "job-1",
                            run_dir=run_dir,
                            stage=stage,
                            attempt=1,
                            max_attempts=2,
                            final_attempt=False,
                        )
                    )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            report = (run_dir / paths["report"]).read_text(encoding="utf-8")

        self.assertEqual(state["review.semantic.scene_detail.shards.status"], "failed")
        self.assertEqual(state["review.semantic.scene_detail.shards.failed_count"], "1")
        self.assertEqual(state["review.semantic.scene_detail.shards.scene_20.transport.status"], "failed")
        self.assertEqual(state["review.semantic.scene_detail.shards.scene_20.transport.retry_count"], "1")
        self.assertIn("blocked_entries:\n  - scene:20", report)
        self.assertIn("failed_selectors:\n  - scene:20", report)
        self.assertIn("scene_detail_shard_transport_failed", report)
        self.assertIn("scene_detail shard transport failed before a terminal report", report)

    def test_scene_detail_shard_transport_timeout_retries_only_failed_shard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            stage = "scene_detail"
            paths = image_gen_app.semantic_review_relpaths(stage)
            turn_counts: dict[str, int] = {}

            def fake_build_pack(cmd, **_kwargs):
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text(
                    "\n".join(
                        [
                            "# Semantic Review Collection: scene_detail",
                            "",
                            "## scene:10",
                            "",
                            "```json",
                            json.dumps({"id": "scene:10", "selector": "scene10"}, ensure_ascii=False),
                            "```",
                            "",
                            "## scene:20",
                            "",
                            "```json",
                            json.dumps({"id": "scene:20", "selector": "scene20"}, ensure_ascii=False),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 2,
                            "entry_ids": ["scene:10", "scene:20"],
                            "source_artifacts": ["script.md"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
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
                    entry_id = text.split("Review only shard entry `", 1)[1].split("`", 1)[0]
                    turn_counts[entry_id] = turn_counts.get(entry_id, 0) + 1
                    if entry_id == "scene:20" and turn_counts[entry_id] == 1:
                        raise CodexAppServerTransportError("turn timed out")
                    return semantic_agent_report_transcript(
                        text,
                        status="passed",
                        entry_id=entry_id,
                    )

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                patch.dict(
                    os.environ,
                    {
                        "TOC_SCENE_DETAIL_REVIEW_CONCURRENCY": "2",
                        "TOC_SCENE_DETAIL_TRANSPORT_RETRY_ATTEMPTS": "3",
                    },
                ),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage=stage,
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            report = (run_dir / paths["report"]).read_text(encoding="utf-8")

        self.assertTrue(result.passed, result.errors)
        self.assertEqual(turn_counts, {"scene:10": 1, "scene:20": 2})
        self.assertEqual(state["review.semantic.scene_detail.shards.status"], "passed")
        self.assertEqual(state["review.semantic.scene_detail.shards.failed_count"], "0")
        self.assertEqual(state["review.semantic.scene_detail.shards.scene_20.transport.status"], "recovered")
        self.assertEqual(state["review.semantic.scene_detail.shards.scene_20.transport.retry_count"], "1")
        self.assertIn("status: passed", report)
        self.assertNotIn("scene_detail_shard_transport_failed", report)

    def test_scene_detail_missing_final_verdict_retries_as_output_contract_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text(
                "# script\n",
                encoding="utf-8",
            )
            stage = "scene_detail"
            paths = image_gen_app.semantic_review_relpaths(stage)
            review_turns = 0

            def fake_build_pack(cmd, **_kwargs):
                (run_dir / paths["collection"]).parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                (run_dir / paths["collection"]).write_text(
                    "\n".join(
                        [
                            "# Semantic Review Collection: scene_detail",
                            "",
                            "## scene:10",
                            "",
                            "```json",
                            json.dumps(
                                {
                                    "id": "scene:10",
                                    "selector": "scene10",
                                },
                                ensure_ascii=False,
                            ),
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 1,
                            "entry_ids": ["scene:10"],
                            "source_artifacts": ["script.md"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (run_dir / paths["prompt"]).write_text(
                    "# review prompt\n",
                    encoding="utf-8",
                )
                (run_dir / paths["report"]).write_text(
                    "status: pending\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, **_kwargs):
                    nonlocal review_turns
                    review_turns += 1
                    return [
                        {
                            "method": "item/completed",
                            "params": {
                                "item": {
                                    "type": "agentMessage",
                                    "phase": "final_answer",
                                    "text": "Review completed without a verdict.",
                                }
                            },
                        }
                    ]

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
                patch.dict(
                    os.environ,
                    {
                        "TOC_SCENE_DETAIL_REVIEW_CONCURRENCY": "1",
                        "TOC_SCENE_DETAIL_TRANSPORT_RETRY_ATTEMPTS": "2",
                    },
                ),
            ):
                with self.assertRaisesRegex(
                    CodexAppServerTransportError,
                    "scene_detail shard transport failed",
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review_once(
                            "job-1",
                            run_dir=run_dir,
                            stage=stage,
                            attempt=1,
                            max_attempts=2,
                            final_attempt=False,
                        )
                    )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(review_turns, 2)
        self.assertEqual(
            state[
                "review.semantic.scene_detail.shards.scene_10.transport.error_kind"
            ],
            "output_contract_failed",
        )
        self.assertEqual(
            state[
                "review.semantic.scene_detail.shards.scene_10.transport.retry_count"
            ],
            "1",
        )

    def test_scene_detail_missing_entry_ids_records_shard_state_and_debuggable_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_detail"
            paths = image_gen_app.semantic_review_relpaths(stage)

            def fake_build_pack(cmd, **_kwargs):
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text("# collection\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(
                    json.dumps({"entry_count": 1, "source_artifacts": ["script.md"]}, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                (run_dir / paths["prompt"]).write_text("# review prompt\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch.dict(os.environ, {"TOC_SCENE_DETAIL_REVIEW_CONCURRENCY": "6"}),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage=stage,
                        attempt=1,
                        max_attempts=2,
                        final_attempt=False,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            report = (run_dir / paths["report"]).read_text(encoding="utf-8")

        self.assertFalse(result.passed)
        self.assertEqual(state["review.semantic.scene_detail.shards.status"], "failed")
        self.assertEqual(state["review.semantic.scene_detail.shards.count"], "0")
        self.assertEqual(state["review.semantic.scene_detail.shards.failed_count"], "1")
        self.assertEqual(state["review.semantic.scene_detail.shards.concurrency"], "6")
        self.assertIn("semantic_review_scope_missing_entry_ids", report)
        self.assertIn("scene_detail scope has no entry_ids", report)

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
                        "status: failed\nreviewed_entries: [scene_1]\nblocked_entries: [scene_1]\n"
                        "failed_selectors: [scene_1]\nfindings:\n  - wrong meaning\n",
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
                        f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: []\n"
                        "failed_selectors: []\nfindings: []\n",
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

    def test_semantic_review_rereviews_after_repair_no_progress_timeout_when_source_changed(self) -> None:
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
                patch("server.image_gen_app._semantic_repair_no_progress_timeout_seconds", lambda: 0.01),
                patch("server.image_gen_app.SEMANTIC_TURN_ARTIFACT_POLL_SECONDS", 0.01),
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

    def test_semantic_review_repair_no_progress_timeout_records_debug_context(self) -> None:
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
            (run_dir / "script.md").write_text("# Script\n\nstuck scene meaning\n", encoding="utf-8")

            async def fake_run_once(*_args, **_kwargs):
                return image_gen_app.SemanticReviewStatus(status="failed", entry_count=1, errors=("wrong meaning",))

            async def stuck_repair(*_args, **_kwargs):
                await asyncio.Event().wait()

            with (
                patch("server.image_gen_app._run_semantic_review_once", fake_run_once),
                patch("server.image_gen_app._run_semantic_review_producer_repair", stuck_repair),
                patch("server.image_gen_app._semantic_repair_no_progress_timeout_seconds", lambda: 0.03),
                patch("server.image_gen_app.SEMANTIC_TURN_ARTIFACT_POLL_SECONDS", 0.005),
            ):
                with self.assertRaisesRegex(CodexAppServerTransportError, "producer repair timed out"):
                    asyncio.run(image_gen_app._run_semantic_review("job-1", run_dir=run_dir, stage=stage, max_attempts=2))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            debug_logs = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((run_dir / "logs" / "app_server" / "semantic_review_producer_repair").glob("*.json"))
            ]

        self.assertEqual(state["review.semantic.scene_set.repair.status"], "blocked_transport")
        self.assertEqual(state["review.semantic.scene_set.repair.pending.status"], "no_progress_timeout")
        self.assertEqual(state["review.semantic.scene_set.repair.pending.report_status"], "missing")
        self.assertEqual(state["review.semantic.scene_set.repair.changed_artifacts_detected"], "")
        self.assertEqual(state["review.semantic.scene_set.repair.report_status"], "missing")
        timeout_log = next(log for log in debug_logs if log["status"] == "no_progress_timeout")
        self.assertEqual(timeout_log["response"]["changedArtifacts"], [])
        self.assertEqual(timeout_log["response"]["reportStatus"], "missing")
        self.assertEqual(timeout_log["request"]["sourceFingerprintBefore"]["artifacts"], ["script.md"])

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
                        f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: []\n"
                        "failed_selectors: []\nfindings: []\n",
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
                        f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: []\n"
                        "failed_selectors: []\nfindings: [semantic drift]\n",
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
                        f"status: {status}\nreviewed_entries: [scene_1]\nblocked_entries: []\n"
                        "failed_selectors: []\nfindings: [semantic drift]\n",
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

                async def generate_image(self, **kwargs):
                    return FakeResult()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.create_codex_app_server_client", FakeClient),
                    patch("server.image_gen_app._validate_p560_asset_quality", Mock()),
                    patch("server.image_gen_app._run_semantic_review", AsyncMock()),
                    patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
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
            self.assertTrue((run_dir / "logs/scene_design/scene_event_input.json").exists())
            self.assertIn("Run dir:", (run_dir / "logs/toc_run_cli/stdout.log").read_text(encoding="utf-8"))
            self.assertEqual((run_dir / "logs/toc_run_cli/stderr.log").read_text(encoding="utf-8"), "")
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
                transcript = []
                source = "app_server"
                provenance_authoritative = True
                turn_id = "turn-1"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    return ImageGenerationResult(
                        saved_path=saved,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                        source="app_server",
                        generation_job_id=str(kwargs["generation_job_id"]),
                        item_id=str(kwargs["item_id"]),
                        turn_id="turn-1",
                        prompt_sha256=hashlib.sha256(str(kwargs["prompt"]).encode("utf-8")).hexdigest(),
                        reference_sha256s=[],
                        image_generation_item_id="image-1",
                        image_generation_item_count=1,
                        destination=str(kwargs["output_path"]),
                        provenance_authoritative=True,
                        provenance_policy="request_bound_v2",
                    )

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

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    nonlocal active, peak
                    active += 1
                    peak = max(peak, active)
                    await asyncio.sleep(0.05)
                    active -= 1
                    return ImageGenerationResult(
                        saved_path=saved,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                        source="app_server",
                        generation_job_id=str(kwargs["generation_job_id"]),
                        item_id=str(kwargs["item_id"]),
                        turn_id="turn-1",
                        prompt_sha256=hashlib.sha256(str(kwargs["prompt"]).encode("utf-8")).hexdigest(),
                        reference_sha256s=[],
                        image_generation_item_id=f"image-{Path(kwargs['output_path']).stem}",
                        image_generation_item_count=1,
                        destination=str(kwargs["output_path"]),
                        provenance_authoritative=True,
                        provenance_policy="request_bound_v2",
                    )

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "TOC_IMAGE_GEN_PROVENANCE_POLICY": "request_bound_v2"}):
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
            client_constructor_kwargs: list[dict[str, Any]] = []

            class FakeClient:
                attempts = 0

                def __init__(self, **kwargs):
                    client_constructor_kwargs.append(kwargs)

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
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
                        source="app_server",
                        provenance_authoritative=True,
                        turn_id="turn-1",
                        generation_job_id=str(kwargs["generation_job_id"]),
                        item_id=str(kwargs["item_id"]),
                        prompt_sha256=hashlib.sha256(str(kwargs["prompt"]).encode("utf-8")).hexdigest(),
                        reference_sha256s=[],
                        image_generation_item_id="image-1",
                        image_generation_item_count=1,
                        destination=str(kwargs["output_path"]),
                        provenance_policy="request_bound_v2",
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
        self.assertEqual(
            client_constructor_kwargs,
            [
                {
                    "cwd": run_dir.resolve(),
                    "scrub_sensitive_env": True,
                    "require_chatgpt_account": True,
                    "require_chatgpt_pro": True,
                },
                {
                    "cwd": run_dir.resolve(),
                    "scrub_sensitive_env": True,
                    "require_chatgpt_account": True,
                    "require_chatgpt_pro": True,
                },
            ],
        )
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

    def test_run_execution_lease_rejects_second_job_until_release(self) -> None:
        async def run_case(run_dir: Path) -> None:
            await image_gen_app._acquire_run_execution_lease("job-one", run_dir)
            try:
                with self.assertRaises(FileLockUnavailable):
                    await image_gen_app._acquire_run_execution_lease("job-two", run_dir)
            finally:
                await image_gen_app._release_run_execution_lease("job-one")
            await image_gen_app._acquire_run_execution_lease("job-two", run_dir)
            await image_gen_app._release_run_execution_lease("job-two")

        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(run_case(Path(tmp) / "sample_run"))

    def test_image_resume_preserves_existing_images_for_hash_aware_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            existing = run_dir / "assets" / "scenes" / "scene01.png"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(PNG_BYTES)

            result = image_gen_app._delete_existing_images_for_image_resume(run_dir)

            self.assertTrue(existing.exists())
            self.assertEqual(existing.read_bytes(), PNG_BYTES)

        self.assertEqual(result["deletedCount"], 0)
        self.assertEqual(result["preservedCount"], 1)

    def test_p680_regeneration_classifier_rejects_stale_or_unowned_plan(
        self,
    ) -> None:
        cases = (
            (
                "different_run",
                "/tmp/different-run",
                False,
                "eval_report.json belongs to a different run",
            ),
            (
                "unbound_output",
                None,
                False,
                "regeneration target is not bound to the current requests",
            ),
            (
                "malformed_passed_state",
                None,
                "false",
                "image stage passed state is malformed",
            ),
            (
                "passed_stage_with_regeneration_plan",
                None,
                True,
                "passed image stage contains a regeneration plan",
            ),
        )
        for label, report_run_dir, passed, expected_error in cases:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmp:
                    run_dir = Path(tmp)
                    (run_dir / "eval_report.json").write_text(
                        json.dumps(
                            {
                                "run_dir": (
                                    report_run_dir
                                    if report_run_dir is not None
                                    else str(run_dir.resolve())
                                ),
                                "stage_target": "p680",
                                "stages": {
                                    "image": {
                                        "passed": passed,
                                        "details": {
                                            "image_regeneration_plan": [
                                                {
                                                    "output": "assets/scenes/missing.png",
                                                    "action": "regenerate_p600_scene",
                                                    "vector_like_references": [],
                                                }
                                            ]
                                        },
                                    }
                                },
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )

                    classification = (
                        image_gen_app._classify_p680_regeneration_plan(run_dir)
                    )

                self.assertEqual(classification.targets, {})
                self.assertTrue(
                    any(
                        expected_error in error
                        for error in classification.errors
                    )
                )

    def test_image_resume_refuses_asset_repair_plan_before_deleting_any_outputs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            bad_scene = run_dir / "assets/scenes/bad_scene.png"
            dependent_scene = run_dir / "assets/scenes/dependent_scene.png"
            good_scene = run_dir / "assets/scenes/good_scene.png"
            bad_reference = run_dir / "assets/characters/bad_reference.png"
            unrelated_upload = run_dir / "assets/uploads/unrelated.png"
            for path in (
                bad_scene,
                dependent_scene,
                good_scene,
                bad_reference,
                unrelated_upload,
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(PNG_BYTES)
            (run_dir / "asset_generation_requests.md").write_text(
                """# Asset Generation Requests

## bad_reference

- output: `assets/characters/bad_reference.png`

```text
bad reference
```
""",
                encoding="utf-8",
            )
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## bad_scene

- output: `assets/scenes/bad_scene.png`
- references: `[]`

```text
bad scene
```

## dependent_scene

- output: `assets/scenes/dependent_scene.png`
- references:
  - `人物参照画像1`: `assets/characters/bad_reference.png`
  - `ユーザー参照画像`: `assets/uploads/unrelated.png`

```text
scene using bad reference
```

## good_scene

- output: `assets/scenes/good_scene.png`
- references: `[]`

```text
good scene
```
""",
                encoding="utf-8",
            )
            (run_dir / "eval_report.json").write_text(
                json.dumps(
                    {
                        "run_dir": str(run_dir.resolve()),
                        "stage_target": "p680",
                        "stages": {
                            "image": {
                                "passed": False,
                                "details": {
                                    "image_regeneration_plan": [
                                        {
                                            "selector": "bad_scene",
                                            "output": "assets/scenes/bad_scene.png",
                                            "action": "regenerate_p600_scene",
                                            "vector_like_references": [],
                                        },
                                        {
                                            "selector": "dependent_scene",
                                            "output": "assets/scenes/dependent_scene.png",
                                                "action": "regenerate_p500_reference_first",
                                                "vector_like_references": [
                                                    "assets/characters/bad_reference.png",
                                                ],
                                            },
                                        ]
                                    },
                            }
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = image_gen_app._delete_existing_images_for_image_resume(
                run_dir
            )

            self.assertTrue(bad_scene.exists())
            self.assertTrue(dependent_scene.exists())
            self.assertTrue(bad_reference.exists())
            self.assertTrue(good_scene.exists())
            self.assertTrue(unrelated_upload.exists())
        self.assertEqual(result["deletedCount"], 0)
        self.assertTrue(
            any(
                "canonical p500" in error.lower()
                for error in result["errors"]
            )
        )
        self.assertTrue(result["requiresCanonicalP500"])
        self.assertEqual(
            result["assetTargets"],
            ["assets/characters/bad_reference.png"],
        )
        self.assertEqual(
            set(result["regenerationActions"]),
            {
                "regenerate_p500_reference_first",
                "regenerate_p600_scene",
            },
        )
        self.assertEqual(result["preservedCount"], 5)

    def test_image_resume_deletes_current_scene_only_regeneration_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            bad_scene = run_dir / "assets/scenes/bad_scene.png"
            good_scene = run_dir / "assets/scenes/good_scene.png"
            bad_scene.parent.mkdir(parents=True)
            bad_scene.write_bytes(PNG_BYTES)
            good_scene.write_bytes(PNG_BYTES)
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## bad_scene

- output: `assets/scenes/bad_scene.png`
- references: `[]`

```text
bad scene
```

## good_scene

- output: `assets/scenes/good_scene.png`
- references: `[]`

```text
good scene
```
""",
                encoding="utf-8",
            )
            (run_dir / "eval_report.json").write_text(
                json.dumps(
                    {
                        "run_dir": str(run_dir.resolve()),
                        "stage_target": "p680",
                        "stages": {
                            "image": {
                                "passed": False,
                                "details": {
                                    "image_regeneration_plan": [
                                        {
                                            "output": "assets/scenes/bad_scene.png",
                                            "action": "regenerate_p600_scene",
                                            "vector_like_references": [],
                                        }
                                    ]
                                },
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = image_gen_app._delete_existing_images_for_image_resume(
                run_dir
            )

            self.assertFalse(bad_scene.exists())
            self.assertTrue(good_scene.exists())
        self.assertEqual(result["deleted"], ["assets/scenes/bad_scene.png"])
        self.assertEqual(result["errors"], [])

    def test_image_resume_does_not_follow_scene_output_symlink_to_user_upload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            upload = run_dir / "assets/uploads/user.png"
            output = run_dir / "assets/scenes/bad_scene.png"
            upload.parent.mkdir(parents=True)
            output.parent.mkdir(parents=True)
            upload.write_bytes(PNG_BYTES)
            output.symlink_to(upload)
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## bad_scene

- output: `assets/scenes/bad_scene.png`
- references: `[]`

```text
bad scene
```
""",
                encoding="utf-8",
            )
            (run_dir / "eval_report.json").write_text(
                json.dumps(
                    {
                        "run_dir": str(run_dir.resolve()),
                        "stage_target": "p680",
                        "stages": {
                            "image": {
                                "passed": False,
                                "details": {
                                    "image_regeneration_plan": [
                                        {
                                            "output": "assets/scenes/bad_scene.png",
                                            "action": "regenerate_p600_scene",
                                        }
                                    ]
                                },
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = image_gen_app._delete_existing_images_for_image_resume(run_dir)

            self.assertTrue(output.is_symlink())
            self.assertEqual(upload.read_bytes(), PNG_BYTES)
        self.assertEqual(result["deletedCount"], 0)
        self.assertTrue(any("symlink" in error for error in result["errors"]))

    def test_image_resume_rejects_noncanonical_scene_output_targeting_upload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            upload = run_dir / "assets/uploads/user.png"
            upload.parent.mkdir(parents=True)
            upload.write_bytes(PNG_BYTES)
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## bad_scene

- output: `assets/scenes/../uploads/user.png`
- references: `[]`

```text
bad scene
```
""",
                encoding="utf-8",
            )
            (run_dir / "eval_report.json").write_text(
                json.dumps(
                    {
                        "run_dir": str(run_dir.resolve()),
                        "stage_target": "p680",
                        "stages": {
                            "image": {
                                "passed": False,
                                "details": {
                                    "image_regeneration_plan": [
                                        {
                                            "output": "assets/scenes/../uploads/user.png",
                                            "action": "regenerate_p600_scene",
                                        }
                                    ]
                                },
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = image_gen_app._delete_existing_images_for_image_resume(run_dir)

            self.assertEqual(upload.read_bytes(), PNG_BYTES)
        self.assertEqual(result["deletedCount"], 0)
        self.assertTrue(any("unsafe" in error for error in result["errors"]))

    def test_image_resume_does_not_follow_symlink_output_directory_outside_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            outside = root / "outside"
            run_dir.mkdir()
            outside.mkdir()
            outside_image = outside / "bad_scene.png"
            outside_image.write_bytes(PNG_BYTES)
            assets_dir = run_dir / "assets"
            assets_dir.mkdir()
            (assets_dir / "scenes").symlink_to(outside, target_is_directory=True)
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## bad_scene

- output: `assets/scenes/bad_scene.png`
- references: `[]`

```text
bad scene
```
""",
                encoding="utf-8",
            )
            (run_dir / "eval_report.json").write_text(
                json.dumps(
                    {
                        "run_dir": str(run_dir.resolve()),
                        "stage_target": "p680",
                        "stages": {
                            "image": {
                                "passed": False,
                                "details": {
                                    "image_regeneration_plan": [
                                        {
                                            "output": "assets/scenes/bad_scene.png",
                                            "action": "regenerate_p600_scene",
                                        }
                                    ]
                                },
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = image_gen_app._delete_existing_images_for_image_resume(run_dir)

            self.assertEqual(outside_image.read_bytes(), PNG_BYTES)
        self.assertEqual(result["deletedCount"], 0)
        self.assertTrue(any("unsafe" in error for error in result["errors"]))

    def test_image_resume_never_treats_upload_as_generated_asset_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            upload = run_dir / "assets/uploads/user.png"
            upload.parent.mkdir(parents=True)
            upload.write_bytes(PNG_BYTES)
            (run_dir / "asset_generation_requests.md").write_text(
                """# Asset Generation Requests

## claimed_upload

- output: `assets/uploads/user.png`
- references: `[]`

```text
claimed upload
```
""",
                encoding="utf-8",
            )
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## dependent_scene

- output: `assets/scenes/dependent_scene.png`
- references:
  - `人物参照画像1`: `assets/uploads/user.png`

```text
dependent scene
```
""",
                encoding="utf-8",
            )
            (run_dir / "eval_report.json").write_text(
                json.dumps(
                    {
                        "run_dir": str(run_dir.resolve()),
                        "stage_target": "p680",
                        "stages": {
                            "image": {
                                "passed": False,
                                "details": {
                                    "image_regeneration_plan": [
                                        {
                                            "output": "assets/scenes/dependent_scene.png",
                                            "action": "regenerate_p500_reference_first",
                                            "vector_like_references": [
                                                "assets/uploads/user.png"
                                            ],
                                        }
                                    ]
                                },
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = image_gen_app._delete_existing_images_for_image_resume(run_dir)

            self.assertEqual(upload.read_bytes(), PNG_BYTES)
        self.assertEqual(result["deletedCount"], 0)
        self.assertTrue(any("unsafe" in error for error in result["errors"]))

    def test_serialized_run_write_rejects_symlink_lock_path(self) -> None:
        async def run_case(run_dir: Path) -> None:
            victim = run_dir / "victim.txt"
            victim.write_text("preserve\n", encoding="utf-8")
            lock_dir = run_dir / ".locks"
            lock_dir.mkdir()
            (lock_dir / "scene_request_revision.lock").symlink_to(victim)

            with self.assertRaisesRegex(FileLockUnavailable, "unsafe"):
                async with image_gen_app._serialized_run_write(
                    run_dir,
                    "scene_request_revision",
                ):
                    self.fail("unsafe cross-process lock must not be entered")

            self.assertEqual(victim.read_text(encoding="utf-8"), "preserve\n")

        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(run_case(Path(tmp)))

    def test_request_generation_rejects_symlink_destination_before_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            upload = run_dir / "assets/uploads/user.png"
            destination = run_dir / "assets/scenes/cut.png"
            upload.parent.mkdir(parents=True)
            destination.parent.mkdir(parents=True)
            upload.write_bytes(b"user-upload")
            destination.symlink_to(upload)
            item = image_gen.ImageRequestItem(
                id="cut",
                kind="scene",
                asset_type="scene_still",
                tool="codex_builtin_image",
                output="assets/scenes/cut.png",
                prompt="cinematic scene",
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image="assets/scenes/cut.png",
            )

            with patch(
                "server.image_gen_app.create_codex_app_server_client"
            ) as create_provider:
                with self.assertRaisesRegex(RuntimeError, "unsafe.*symlink"):
                    asyncio.run(
                        image_gen_app._generate_request_item_output_with_slot(
                            run_dir=run_dir,
                            kind="scene",
                            item=item,
                        )
                    )

            self.assertEqual(upload.read_bytes(), b"user-upload")
            self.assertTrue(destination.is_symlink())
        create_provider.assert_not_called()

    def test_request_generation_rejects_symlink_destination_parent_before_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            outside = root / "outside"
            run_dir.mkdir()
            outside.mkdir()
            assets = run_dir / "assets"
            assets.mkdir()
            (assets / "scenes").symlink_to(outside, target_is_directory=True)
            item = image_gen.ImageRequestItem(
                id="cut",
                kind="scene",
                asset_type="scene_still",
                tool="codex_builtin_image",
                output="assets/scenes/cut.png",
                prompt="cinematic scene",
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image=None,
            )

            with patch(
                "server.image_gen_app.create_codex_app_server_client"
            ) as create_provider:
                with self.assertRaisesRegex(RuntimeError, "unsafe.*symlink"):
                    asyncio.run(
                        image_gen_app._generate_request_item_output_with_slot(
                            run_dir=run_dir,
                            kind="scene",
                            item=item,
                        )
                    )

            self.assertFalse((outside / "cut.png").exists())
        create_provider.assert_not_called()

    def test_request_generation_rejects_destination_parent_swap_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            outside = root / "outside"
            scenes = run_dir / "assets" / "scenes"
            detached_scenes = root / "detached-scenes"
            scenes.mkdir(parents=True)
            outside.mkdir()
            outside_destination = outside / "cut.png"
            outside_destination.write_bytes(b"outside-file-must-not-change")
            generated = root / "generated.png"
            generated.write_bytes(PNG_BYTES)
            original_validate = (
                image_gen_app._validate_generation_destination_nofollow
            )
            validation_calls = 0

            def validate_then_swap_parent(
                checked_run_dir: Path,
                value: str,
                *,
                kind: str,
            ) -> tuple[str, Path]:
                nonlocal validation_calls
                result = original_validate(
                    checked_run_dir,
                    value,
                    kind=kind,
                )
                validation_calls += 1
                if validation_calls == 2:
                    scenes.rename(detached_scenes)
                    scenes.symlink_to(outside, target_is_directory=True)
                return result

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    return ImageGenerationResult(
                        saved_path=generated,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                        source="app_server",
                        provenance_authoritative=True,
                        turn_id="turn-1",
                        generation_job_id=str(kwargs["generation_job_id"]),
                        item_id=str(kwargs["item_id"]),
                        prompt_sha256=hashlib.sha256(
                            str(kwargs["prompt"]).encode("utf-8")
                        ).hexdigest(),
                        reference_sha256s=[],
                        image_generation_item_id="image-1",
                        image_generation_item_count=1,
                        destination=str(kwargs["output_path"]),
                        provenance_policy="request_bound_v2",
                    )

            item = image_gen.ImageRequestItem(
                id="cut",
                kind="scene",
                asset_type="scene_still",
                tool="codex_builtin_image",
                output="assets/scenes/cut.png",
                prompt="cinematic scene",
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image=None,
            )

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
                patch(
                    "server.image_gen_app._validate_generation_destination_nofollow",
                    validate_then_swap_parent,
                ),
                patch(
                    "server.image_gen_app.retain_first_image",
                    return_value={"created": True},
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "unsafe.*destination",
                ):
                    asyncio.run(
                        image_gen_app._generate_request_item_output_with_slot(
                            run_dir=run_dir,
                            kind="scene",
                            item=item,
                        )
                    )

            self.assertEqual(
                outside_destination.read_bytes(),
                b"outside-file-must-not-change",
            )
            self.assertFalse((detached_scenes / "cut.png").exists())
            failure_logs = sorted(
                (
                    run_dir
                    / "logs"
                    / "app_server"
                    / "image_gen"
                ).glob("*.json")
            )
            self.assertTrue(failure_logs)
            failure_log = json.loads(
                failure_logs[-1].read_text(encoding="utf-8")
            )
            self.assertIsNone(failure_log["outputSha256"])
            self.assertEqual(
                failure_log["destinationDetails"]["inspectionSkipped"],
                "unsafe_destination",
            )

    def test_provider_failure_after_parent_swap_does_not_inspect_destination(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            outside = root / "outside"
            scenes = run_dir / "assets" / "scenes"
            detached_scenes = root / "detached-scenes"
            scenes.mkdir(parents=True)
            outside.mkdir()
            outside_destination = outside / "cut.png"
            outside_destination.write_bytes(b"outside-file-must-not-read")

            class FailingClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **_kwargs):
                    scenes.rename(detached_scenes)
                    scenes.symlink_to(
                        outside,
                        target_is_directory=True,
                    )
                    raise RuntimeError("provider failed after parent swap")

            item = image_gen.ImageRequestItem(
                id="cut",
                kind="scene",
                asset_type="scene_still",
                tool="codex_builtin_image",
                output="assets/scenes/cut.png",
                prompt="cinematic scene",
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image=None,
            )

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FailingClient,
                ),
                patch(
                    "server.image_gen_app.IMAGE_GENERATION_ITEM_MAX_ATTEMPTS",
                    1,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "provider failed after parent swap",
                ):
                    asyncio.run(
                        image_gen_app._generate_request_item_output_with_slot(
                            run_dir=run_dir,
                            kind="scene",
                            item=item,
                        )
                    )

            failure_logs = sorted(
                (
                    run_dir
                    / "logs"
                    / "app_server"
                    / "image_gen"
                ).glob("*.json")
            )
            self.assertTrue(failure_logs)
            failure_log = json.loads(
                failure_logs[-1].read_text(encoding="utf-8")
            )
            self.assertIsNone(failure_log["outputSha256"])
            self.assertEqual(
                failure_log["destinationDetails"]["inspectionSkipped"],
                "unsafe_destination",
            )
            self.assertEqual(
                outside_destination.read_bytes(),
                b"outside-file-must-not-read",
            )

    def test_success_logging_uses_descriptor_bound_copy_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            outside = root / "outside"
            scenes = run_dir / "assets" / "scenes"
            detached_scenes = root / "detached-scenes"
            scenes.mkdir(parents=True)
            outside.mkdir()
            outside_destination = outside / "cut.png"
            outside_destination.write_bytes(b"outside-file-must-not-read")
            generated = root / "generated.png"
            generated.write_bytes(PNG_BYTES)
            original_copy = (
                image_gen_app
                ._copy_saved_image_to_generation_destination_nofollow
            )

            def copy_then_swap_parent(**kwargs):
                result = original_copy(**kwargs)
                scenes.rename(detached_scenes)
                scenes.symlink_to(
                    outside,
                    target_is_directory=True,
                )
                return result

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    return ImageGenerationResult(
                        saved_path=generated,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                        source="app_server",
                        provenance_authoritative=True,
                        turn_id="turn-1",
                        generation_job_id=str(kwargs["generation_job_id"]),
                        item_id=str(kwargs["item_id"]),
                        prompt_sha256=hashlib.sha256(
                            str(kwargs["prompt"]).encode("utf-8")
                        ).hexdigest(),
                        reference_sha256s=[],
                        image_generation_item_id="image-1",
                        image_generation_item_count=1,
                        destination=str(kwargs["output_path"]),
                        provenance_policy="request_bound_v2",
                    )

            item = image_gen.ImageRequestItem(
                id="cut",
                kind="scene",
                asset_type="scene_still",
                tool="codex_builtin_image",
                output="assets/scenes/cut.png",
                prompt="cinematic scene",
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image=None,
            )

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
                patch(
                    "server.image_gen_app._copy_saved_image_to_generation_destination_nofollow",
                    copy_then_swap_parent,
                ),
                patch(
                    "server.image_gen_app.retain_first_image",
                    return_value={"created": True},
                ),
            ):
                asyncio.run(
                    image_gen_app._generate_request_item_output_with_slot(
                        run_dir=run_dir,
                        kind="scene",
                        item=item,
                    )
                )

            success_logs = sorted(
                (
                    run_dir
                    / "logs"
                    / "app_server"
                    / "image_gen"
                ).glob("*.json")
            )
            self.assertTrue(success_logs)
            success_log = json.loads(
                success_logs[-1].read_text(encoding="utf-8")
            )
            self.assertEqual(
                success_log["outputSha256"],
                hashlib.sha256(PNG_BYTES).hexdigest(),
            )
            self.assertEqual(
                success_log["destinationDetails"]["inspectionSkipped"],
                "descriptor_verified_copy",
            )
            self.assertEqual(
                outside_destination.read_bytes(),
                b"outside-file-must-not-read",
            )
            self.assertEqual(
                (detached_scenes / "cut.png").read_bytes(),
                PNG_BYTES,
            )

    def test_generation_copy_keeps_temp_descriptor_bound_through_commit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            scenes = run_dir / "assets" / "scenes"
            scenes.mkdir(parents=True)
            generated = root / "generated.png"
            generated.write_bytes(PNG_BYTES)
            replacement = root / "replacement.png"
            replacement.write_bytes(PNG_BYTES + b"replacement")
            original_open = os.open
            original_close = os.close
            original_replace = os.replace
            temporary_descriptor: int | None = None
            temporary_name: str | None = None
            temporary_swapped = False

            def track_temporary_open(
                path,
                flags,
                mode=0o777,
                *,
                dir_fd=None,
            ):
                nonlocal temporary_descriptor, temporary_name
                descriptor = original_open(
                    path,
                    flags,
                    mode,
                    dir_fd=dir_fd,
                )
                if (
                    isinstance(path, str)
                    and path.startswith(".toc-image-")
                    and bool(flags & os.O_CREAT)
                ):
                    temporary_descriptor = descriptor
                    temporary_name = path
                return descriptor

            def swap_temporary_after_close(descriptor: int) -> None:
                nonlocal temporary_swapped
                original_close(descriptor)
                if (
                    not temporary_swapped
                    and descriptor == temporary_descriptor
                    and temporary_name is not None
                    and (scenes / temporary_name).exists()
                ):
                    original_replace(
                        replacement,
                        scenes / temporary_name,
                    )
                    temporary_swapped = True

            with (
                patch(
                    "server.image_gen_app.os.open",
                    track_temporary_open,
                ),
                patch(
                    "server.image_gen_app.os.close",
                    swap_temporary_after_close,
                ),
            ):
                receipt = (
                    image_gen_app
                    ._copy_saved_image_to_generation_destination_nofollow(
                        run_dir=run_dir,
                        saved_path=generated,
                        output="assets/scenes/cut.png",
                        kind="scene",
                    )
                )

            destination = scenes / "cut.png"
            self.assertEqual(destination.read_bytes(), PNG_BYTES)
            self.assertEqual(
                receipt.output_sha256,
                hashlib.sha256(destination.read_bytes()).hexdigest(),
            )

    def test_generation_copy_rejects_swapped_temp_name_at_commit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            scenes = run_dir / "assets" / "scenes"
            destination = scenes / "cut.png"
            scenes.mkdir(parents=True)
            destination.write_bytes(b"existing-canonical-bytes")
            generated = root / "generated.png"
            generated.write_bytes(PNG_BYTES)
            replacement_name = ".attacker-replacement.png"
            (scenes / replacement_name).write_bytes(
                PNG_BYTES + b"replacement"
            )
            original_replace = os.replace
            replacements = 0

            def replace_after_temp_name_swap(
                source,
                target,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
            ) -> None:
                nonlocal replacements
                replacements += 1
                if replacements == 1:
                    original_replace(
                        replacement_name,
                        source,
                        src_dir_fd=src_dir_fd,
                        dst_dir_fd=src_dir_fd,
                    )
                original_replace(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            with patch(
                "server.image_gen_app.os.replace",
                replace_after_temp_name_swap,
            ):
                with self.assertRaisesRegex(
                    image_gen_app._UnsafeGenerationDestinationError,
                    "rollback failed.*changed before rollback",
                ):
                    image_gen_app._copy_saved_image_to_generation_destination_nofollow(
                        run_dir=run_dir,
                        saved_path=generated,
                        output="assets/scenes/cut.png",
                        kind="scene",
                    )

            self.assertEqual(
                destination.read_bytes(),
                PNG_BYTES + b"replacement",
            )
            backups = list(
                scenes.glob(".toc-image-backup-*.tmp.png")
            )
            self.assertEqual(len(backups), 1)
            self.assertEqual(
                backups[0].read_bytes(),
                b"existing-canonical-bytes",
            )

    def test_generation_copy_rolls_back_parent_swap_after_precheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            outside = root / "outside"
            scenes = run_dir / "assets" / "scenes"
            detached_scenes = root / "detached-scenes"
            destination = scenes / "cut.png"
            scenes.mkdir(parents=True)
            outside.mkdir()
            destination.write_bytes(b"existing-canonical-bytes")
            outside_destination = outside / "cut.png"
            outside_destination.write_bytes(b"outside-file-must-not-change")
            generated = root / "generated.png"
            generated.write_bytes(PNG_BYTES)
            original_replace = os.replace
            replacements = 0

            def replace_after_parent_swap(*args, **kwargs) -> None:
                nonlocal replacements
                replacements += 1
                if replacements == 1:
                    scenes.rename(detached_scenes)
                    scenes.symlink_to(outside, target_is_directory=True)
                original_replace(*args, **kwargs)

            with patch(
                "server.image_gen_app.os.replace",
                replace_after_parent_swap,
            ):
                with self.assertRaisesRegex(
                    image_gen_app._UnsafeGenerationDestinationError,
                    "parent.*unsafe|parent changed",
                ):
                    image_gen_app._copy_saved_image_to_generation_destination_nofollow(
                        run_dir=run_dir,
                        saved_path=generated,
                        output="assets/scenes/cut.png",
                        kind="scene",
                    )

            self.assertEqual(
                (detached_scenes / "cut.png").read_bytes(),
                b"existing-canonical-bytes",
            )
            self.assertEqual(
                outside_destination.read_bytes(),
                b"outside-file-must-not-change",
            )
            self.assertEqual(
                list(detached_scenes.glob(".toc-image-*")),
                [],
            )

    def test_generation_copy_removes_new_output_after_parent_swap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            outside = root / "outside"
            scenes = run_dir / "assets" / "scenes"
            detached_scenes = root / "detached-scenes"
            scenes.mkdir(parents=True)
            outside.mkdir()
            generated = root / "generated.png"
            generated.write_bytes(PNG_BYTES)
            original_assert_parent = (
                image_gen_app._assert_generation_parent_is_current
            )
            parent_checks = 0

            def assert_parent_then_swap(*args, **kwargs) -> None:
                nonlocal parent_checks
                original_assert_parent(*args, **kwargs)
                parent_checks += 1
                if parent_checks == 1:
                    scenes.rename(detached_scenes)
                    scenes.symlink_to(outside, target_is_directory=True)

            with patch(
                "server.image_gen_app._assert_generation_parent_is_current",
                assert_parent_then_swap,
            ):
                with self.assertRaises(
                    image_gen_app._UnsafeGenerationDestinationError
                ):
                    image_gen_app._copy_saved_image_to_generation_destination_nofollow(
                        run_dir=run_dir,
                        saved_path=generated,
                        output="assets/scenes/cut.png",
                        kind="scene",
                    )

            self.assertFalse((detached_scenes / "cut.png").exists())
            self.assertFalse((outside / "cut.png").exists())
            self.assertEqual(
                list(detached_scenes.glob(".toc-image-*")),
                [],
            )

    def test_generation_copy_preserves_concurrent_leaf_on_rollback_conflict(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            scenes = run_dir / "assets" / "scenes"
            destination = scenes / "cut.png"
            concurrent_leaf = scenes / "concurrent.png"
            scenes.mkdir(parents=True)
            destination.write_bytes(b"existing-canonical-bytes")
            concurrent_leaf.write_bytes(b"concurrent-leaf-bytes")
            generated = root / "generated.png"
            generated.write_bytes(PNG_BYTES)
            original_replace = os.replace
            replacements = 0

            def replace_then_swap_leaf(*args, **kwargs) -> None:
                nonlocal replacements
                replacements += 1
                original_replace(*args, **kwargs)
                if replacements == 1:
                    original_replace(concurrent_leaf, destination)

            with patch(
                "server.image_gen_app.os.replace",
                replace_then_swap_leaf,
            ):
                with self.assertRaisesRegex(
                    image_gen_app._UnsafeGenerationDestinationError,
                    "rollback failed.*changed before rollback",
                ):
                    image_gen_app._copy_saved_image_to_generation_destination_nofollow(
                        run_dir=run_dir,
                        saved_path=generated,
                        output="assets/scenes/cut.png",
                        kind="scene",
                    )

            self.assertEqual(
                destination.read_bytes(),
                b"concurrent-leaf-bytes",
            )
            backups = list(
                scenes.glob(".toc-image-backup-*.tmp.png")
            )
            self.assertEqual(len(backups), 1)
            self.assertEqual(
                backups[0].read_bytes(),
                b"existing-canonical-bytes",
            )

    def test_v2_compiled_prompt_is_not_rewritten_by_generic_quality_upgrade(self) -> None:
        item = image_gen.ImageRequestItem(
            id="scene1_cut1",
            kind="scene",
            asset_type="scene_still",
            tool="codex_builtin_image",
            output="assets/scenes/scene1_cut1.png",
            prompt="灰色の階段にガラスの靴。",
            references=[],
            reference_count=0,
            execution_lane="bootstrap_builtin",
            generation_status=None,
            existing_image=None,
            prompt_policy_version="image_api_prompt_v2",
            compiler_version="drawable_prompt_compiler_v2",
        )

        self.assertFalse(image_gen_app._prompt_needs_quality_upgrade(item))

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

                async def generate_image(self, **kwargs):
                    return ImageGenerationResult(
                        saved_path=generated,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                        source="app_server",
                        provenance_authoritative=True,
                        turn_id="turn-1",
                        generation_job_id=str(kwargs["generation_job_id"]),
                        item_id=str(kwargs["item_id"]),
                        prompt_sha256=hashlib.sha256(str(kwargs["prompt"]).encode("utf-8")).hexdigest(),
                        reference_sha256s=[],
                        image_generation_item_id="image-1",
                        image_generation_item_count=1,
                        destination=str(kwargs["output_path"]),
                        provenance_policy="request_bound_v2",
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
        self.assertIn("existing destination is stale and will be replaced only after successful generation", event_payload)
        self.assertIn('"status": "completed"', event_payload)

    def test_create_flow_keeps_stale_destination_when_regeneration_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            destination = run_dir / "assets" / "objects" / "stale.png"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"stale-but-reviewable")

            class FailingClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **_kwargs):
                    raise RuntimeError("provider unavailable")

            item = image_gen.ImageRequestItem(
                id="stale_asset",
                kind="asset",
                asset_type=None,
                tool="codex_builtin_image",
                output="assets/objects/stale.png",
                prompt="新しい実写映画風プロンプト。",
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image=None,
            )

            with (
                patch("server.image_gen_app.ROOT", Path(tmp)),
                patch("server.image_gen_app.create_codex_app_server_client", FailingClient),
                patch("server.image_gen_app.IMAGE_GENERATION_ITEM_MAX_ATTEMPTS", 1),
            ):
                with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                    asyncio.run(image_gen_app._generate_request_item_output(run_dir=run_dir, kind="asset", item=item))

            preserved = destination.read_bytes()

        self.assertEqual(preserved, b"stale-but-reviewable")

    def test_create_flow_does_not_reuse_provenance_for_different_prompt(self) -> None:
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
                prompt="old prompt",
                kind="asset",
                result=ImageGenerationResult(
                    saved_path=destination,
                    revised_prompt=None,
                    status="completed",
                    transcript=[],
                    source="app_server",
                    prompt_sha256=hashlib.sha256(b"old prompt").hexdigest(),
                    reference_sha256s=[],
                    provenance_authoritative=True,
                    turn_id="turn-old",
                ),
            )
            generated = Path(tmp) / "generated.png"
            generated.write_bytes(PNG_BYTES + b"new")

            class RecordingClient:
                calls = 0

                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    type(self).calls += 1
                    return ImageGenerationResult(
                        saved_path=generated,
                        revised_prompt=kwargs["prompt"],
                        status="completed",
                        transcript=[],
                        source="app_server",
                        prompt_sha256=hashlib.sha256(kwargs["prompt"].encode("utf-8")).hexdigest(),
                        reference_sha256s=[],
                        provenance_authoritative=True,
                        turn_id="turn-new",
                        generation_job_id=str(kwargs["generation_job_id"]),
                        item_id=str(kwargs["item_id"]),
                        image_generation_item_id="image-new",
                        image_generation_item_count=1,
                        destination=str(kwargs["output_path"]),
                        provenance_policy="request_bound_v2",
                    )

            item = image_gen.ImageRequestItem(
                id="done_asset",
                kind="asset",
                asset_type=None,
                tool="codex_builtin_image",
                output="assets/objects/done.png",
                prompt="new prompt",
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image=None,
            )

            with (
                patch("server.image_gen_app.ROOT", Path(tmp)),
                patch("server.image_gen_app.create_codex_app_server_client", RecordingClient),
            ):
                asyncio.run(image_gen_app._generate_request_item_output(run_dir=run_dir, kind="asset", item=item))

            destination_bytes = destination.read_bytes()

        self.assertEqual(RecordingClient.calls, 1)
        self.assertEqual(destination_bytes, PNG_BYTES + b"new")

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
                    turn_id="turn-done",
                    prompt_sha256=hashlib.sha256("実写映画風。".encode("utf-8")).hexdigest(),
                    reference_sha256s=[],
                    image_generation_item_id="image-done",
                    image_generation_item_count=1,
                    provenance_authoritative=True,
                    generation_job_id="job-done",
                    item_id="done_asset",
                    destination=str(destination),
                    provenance_policy="request_bound_v2",
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
                raise image_gen_app.P560AssetGateError(
                    "p560 asset gate failed: low detail raster",
                    failed_check_ids=("asset.visual_not_vector_like",),
                    retryable_visual_quality=True,
                )

            async def fake_repair_bootstrap_asset_prompts(*_args: Any, **_kwargs: Any) -> None:
                raise TimeoutError("repair timed out")

            semantic_review = AsyncMock()
            fixed_point = AsyncMock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._generate_request_outputs", fake_generate_request_outputs),
                patch("server.image_gen_app._generate_request_outputs_unlocked", fake_generate_request_outputs),
                patch("server.image_gen_app._validate_p560_asset_quality", fake_validate_p560_asset_quality),
                patch("server.image_gen_app._repair_bootstrap_asset_prompts", fake_repair_bootstrap_asset_prompts),
                patch(
                    "server.image_gen_app._run_pre_asset_semantic_fixed_point",
                    fixed_point,
                ),
                patch("server.image_gen_app._run_semantic_review", semantic_review),
                patch("server.image_gen_app._validate_pre_asset_provider_gate", Mock()),
                patch("server.image_gen_app._validate_p650_run"),
            ):
                result = asyncio.run(image_gen_app._generate_create_images("job-1", run_id="sample_run"))

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            event_payload = (run_dir / "logs" / "app_server" / "events.jsonl").read_text(encoding="utf-8")

        self.assertFalse(result)
        self.assertEqual(calls, ["asset"])
        fixed_point.assert_awaited_once_with("job-1", run_dir=run_dir.resolve())
        semantic_review.assert_not_awaited()
        self.assertEqual(state["review.asset_visual_gate.status"], "needs_frontend_review")
        self.assertEqual(state["review.asset_visual_gate.repair.status"], "failed")
        self.assertEqual(state["slot.p570.status"], "awaiting_approval")
        self.assertEqual(state["slot.p680.status"], "pending")
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
                patch.dict(os.environ, {"TOC_IMAGE_GEN_DISABLE_CODEX_APP_SERVER": "", "TOC_IMAGE_GEN_PROVENANCE_POLICY": "request_bound_v2"}, clear=False),
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
                patch.dict(os.environ, {"TOC_IMAGE_GEN_DISABLE_CODEX_APP_SERVER": "", "TOC_IMAGE_GEN_PROVENANCE_POLICY": "request_bound_v2"}, clear=False),
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
            snapshot_path = run_dir / "image_generation_request_snapshot.json"
            snapshot_path.write_text('{"original": true}\n', encoding="utf-8")
            snapshot_before = snapshot_path.read_text(encoding="utf-8")

            async def fail_materialize(_run_id: str) -> None:
                (run_dir / "image_generation_requests.md").write_text("partially replaced request\n", encoding="utf-8")
                snapshot_path.write_text('{"partial": true}\n', encoding="utf-8")
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
            snapshot_after = snapshot_path.read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(manifest_after, manifest_before)
        self.assertEqual(request_after, request_before)
        self.assertEqual(snapshot_after, snapshot_before)

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
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_quality": "720p",
                                        "video_aspect_ratio": "9:16",
                                        "video_duration_seconds": 6,
                                        "video_first_reference": "assets/scenes/scene10_cut1.png",
                                        "video_last_reference": "assets/characters/hero.png",
                                        "video_references": [],
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
            expected_references_digest = hashlib.sha256(
                json.dumps(
                    [],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(video_draft_latest_exists)
        self.assertIn("- quality: `720p`", request_text)
        self.assertIn("- aspect_ratio: `9:16`", request_text)
        self.assertIn("- prompt_policy_version: `video_api_prompt_v1`", request_text)
        self.assertIn(
            f"- references_digest: `{expected_references_digest}`",
            request_text,
        )
        self.assertNotIn("slow dolly forward", request_text)
        self.assertIn("slow dolly forward", design_text)
        self.assertIn("単一の連続ショット", request_text)
        self.assertNotIn("updated still prompt", request_text)
        self.assertNotIn("cut_contract:", request_text)
        self.assertIn("prompt_changed: `true`", design_text)
        self.assertEqual(manifest["scenes"][0]["cuts"][0]["video_generation"]["first_frame"], "assets/scenes/scene10_cut1.png")
        self.assertEqual(
            manifest["scenes"][0]["cuts"][0]["video_generation"]["api_prompt_payload"]["policy_version"],
            "video_api_prompt_v1",
        )
        self.assertEqual(
            manifest["scenes"][0]["cuts"][0]["video_generation"]["motion_prompt"],
            manifest["scenes"][0]["cuts"][0]["video_generation"]["api_prompt_payload"]["prompt"],
        )
        self.assertEqual(
            manifest["scenes"][0]["cuts"][0]["video_generation"]["prompt_authoring_source"],
            REVIEWABLE_VIDEO_PROMPT,
        )
        self.assertIn("review.frontend.video.status=saved_for_video_prompt", state)
        self.assertIn("slot.p830.status=in_progress", state)
        self.assertIn("stage.video_generation.status=in_progress", state)
        self.assertIn("review.video_prompt.status=pending", state)
        self.assertIn("gate.video_prompt_review=required", state)
        self.assertIn(
            "review.video_prompt.item.scene10_cut1.status=pending",
            state,
        )

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

    def test_create_video_prompts_rejects_unsupported_kling_auxiliary_references_before_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            (run_dir / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
            (run_dir / "assets" / "scenes" / "scene10_cut1.png").write_bytes(
                PNG_BYTES
            )

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                        "video_prompt": "主人公が一歩進む",
                                        "video_first_reference": "assets/scenes/scene10_cut1.png",
                                        "video_references": [
                                            "assets/characters/hero.png"
                                        ],
                                        "video_tool": "kling_3_0_omni",
                                    }
                                ],
                            },
                        )

            state = (run_dir / "state.txt").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 400)
        self.assertIn("reference image count 1", response.text)
        self.assertIn("outside the kling_3_0_omni image_to_video limit 0-0", response.text)
        self.assertNotIn("review.video_prompt.item.scene10_cut1.status=approved", state)
        self.video_semantic_review_mock.assert_not_awaited()

    def test_create_video_prompts_partial_update_preserves_existing_video_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            (run_dir / "video_generation_requests.md").write_text(
                """# Video Generation Requests

## scene10_cut2

- tool: `kling_3_0`
- output: `assets/scenes/scene10_cut2_video.mp4`

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
                                        "video_prompt": "主人公へゆっくり寄る",
                                        "video_first_reference": "assets/scenes/scene10_cut1.png",
                                    }
                                ],
                            },
                        )

            request_text = (run_dir / "video_generation_requests.md").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("## scene10_cut2", request_text)
        self.assertIn("keep existing request", request_text)
        self.assertIn("## scene10_cut1", request_text)
        self.assertIn("主人公へゆっくり寄る", request_text)

    def test_create_video_prompts_explicitly_clears_existing_last_frame_without_staling_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            manifest_path, original_text, manifest = image_gen_app._read_manifest_data(run_dir)
            manifest["scenes"][0]["cuts"][0]["video_generation"] = {
                "last_frame": "assets/characters/hero.png",
            }
            image_gen_app._write_manifest_data(manifest_path, original_text, manifest)
            request_item = {
                "item_id": "scene10_cut1",
                "kind": "scene",
                "output": "assets/scenes/scene10_cut1.png",
                "video_prompt": "主人公が扉の手前で止まる",
                "video_first_reference": "assets/scenes/scene10_cut1.png",
                "video_last_reference": "",
            }

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={"run_id": "sample_run", "items": [request_item]},
                        )

            _path, _text, current_manifest = image_gen_app._read_manifest_data(run_dir)
            video_generation = current_manifest["scenes"][0]["cuts"][0]["video_generation"]
            _target, recompiled = image_gen_app._compile_frontend_video_prompt_payload(
                data=current_manifest,
                item=image_gen_app.FrontendReviewItem(**request_item),
                run_dir=run_dir,
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("last_frame", video_generation)
        self.assertEqual(video_generation["api_prompt_payload"], recompiled)

    def test_create_video_prompts_does_not_approve_when_video_semantic_review_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            (run_dir / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
            (run_dir / "assets" / "scenes" / "scene10_cut1.png").write_bytes(PNG_BYTES)
            self.video_semantic_review_mock.side_effect = ValueError("semantic rejection")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                        "video_prompt": "主人公が扉の手前で止まる",
                                        "video_first_reference": "assets/scenes/scene10_cut1.png",
                                    }
                                ],
                            },
                        )

            state = (run_dir / "state.txt").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 400)
        self.video_semantic_review_mock.assert_awaited_once()
        self.assertIn("review.video_prompt.item.scene10_cut1.status=pending", state)
        self.assertNotIn("review.video_prompt.item.scene10_cut1.status=approved", state)

    def test_create_video_prompts_serializes_materialization_review_and_approval_per_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            active_reviews = 0
            peak_reviews = 0

            async def controlled_semantic_review(*, run_dir: Path) -> None:
                nonlocal active_reviews, peak_reviews
                active_reviews += 1
                peak_reviews = max(peak_reviews, active_reviews)
                try:
                    await asyncio.sleep(0.05)
                finally:
                    active_reviews -= 1

            self.video_semantic_review_mock.side_effect = controlled_semantic_review
            request_a = image_gen_app.VideoPromptCreateRequest(
                run_id="sample_run",
                approve_for_generation=True,
                items=[
                    image_gen_app.FrontendReviewItem(
                        item_id="scene10_cut1",
                        kind="scene",
                        video_prompt="主人公が左へ一歩進む",
                        video_first_reference="assets/characters/hero.png",
                    )
                ],
            )
            request_b = image_gen_app.VideoPromptCreateRequest(
                run_id="sample_run",
                approve_for_generation=True,
                items=[
                    image_gen_app.FrontendReviewItem(
                        item_id="scene10_cut1",
                        kind="scene",
                        video_prompt="主人公が右へ二歩進む",
                        video_first_reference="assets/characters/hero.png",
                    )
                ],
            )

            async def run_concurrently() -> list[Any]:
                first = asyncio.create_task(
                    image_gen_app.api_create_video_prompts(request_a)
                )
                await asyncio.sleep(0)
                second = asyncio.create_task(
                    image_gen_app.api_create_video_prompts(request_b)
                )
                return list(
                    await asyncio.gather(first, second, return_exceptions=True)
                )

            with patch("server.image_gen_app.ROOT", root):
                results = asyncio.run(run_concurrently())

            _path, _text, manifest = image_gen_app._read_manifest_data(run_dir)
            generation = manifest["scenes"][0]["cuts"][0]["video_generation"]
            current_binding = image_gen_app._reviewed_video_request_binding(
                run_dir, "scene10_cut1"
            )
            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            prefix = image_gen_app._video_prompt_approval_state_prefix(
                "scene10_cut1"
            )

        self.assertEqual(peak_reviews, 1)
        self.assertTrue(all(isinstance(result, dict) for result in results), results)
        self.assertEqual(
            generation["prompt_authoring_source"], "主人公が右へ二歩進む"
        )
        self.assertEqual(
            state[f"{prefix}.request_section_sha256"],
            current_binding["request_section_sha256"],
        )
        self.assertEqual(state[f"{prefix}.status"], "approved")

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

    def test_video_generate_uses_materialized_provider_prompt_and_does_not_rewrite_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            mark_manifest_narration_ready(run_dir)
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

            with patch.dict(
                os.environ,
                {
                    "TOC_SERVER_AUTH_DISABLED": "1",
                    "KLING_API_KEY": "fake-key",
                    "VIDEO_NEGATIVE_PROMPT": "UNREVIEWED_NEGATIVE_PROMPT",
                },
            ):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.KlingClient", FakeKlingClient),
                    patch("server.image_gen_app._require_narration_ready_for_video", return_value={"ready": True}),
                ):
                    with TestClient(app) as client:
                        materialize_response = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "assets/characters/hero.png",
                                        "video_quality": "720p",
                                        "video_aspect_ratio": "9:16",
                                        "video_duration_seconds": 6,
                                        "video_tool": "kling_3_0",
                                    }
                                ],
                            },
                        )
                        request_before_generate = (run_dir / "video_generation_requests.md").read_text(encoding="utf-8")
                        manifest_before_generate = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
                        manifest_data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(manifest_before_generate))
                        expected_provider_prompt = manifest_data["scenes"][0]["cuts"][0]["video_generation"]["api_prompt_payload"]["prompt"]
                        expected_negative_prompt = manifest_data["scenes"][0]["cuts"][0]["video_generation"]["api_prompt_payload"]["negative_prompt"]
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": REVIEWABLE_VIDEO_PROMPT,
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
            provider_debug = json.loads(
                (run_dir / payload["candidates"][0]["debugLog"]).read_text(encoding="utf-8")
            )

        self.assertEqual(materialize_response.status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["candidates"]), 2)
        self.assertTrue(first_candidate_exists)
        self.assertEqual(request_text, request_before_generate)
        self.assertEqual(manifest_after, manifest_before_generate)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["prompt"], expected_provider_prompt)
        self.assertEqual(calls[0]["negative_prompt"], expected_negative_prompt)
        self.assertNotEqual(calls[0]["negative_prompt"], "UNREVIEWED_NEGATIVE_PROMPT")
        self.assertNotIn("slow dolly forward", calls[0]["prompt"])
        self.assertIn("カメラは被写体へゆっくり寄る", calls[0]["prompt"])
        self.assertIn("単一の連続ショット", calls[0]["prompt"])
        self.assertEqual(calls[0]["aspect_ratio"], "9:16")
        self.assertEqual(calls[0]["resolution"], "720p")
        self.assertEqual(provider_debug["prompt"], expected_provider_prompt)
        self.assertEqual(provider_debug["promptPolicyVersion"], "video_api_prompt_v1")
        self.assertEqual(
            provider_debug["promptSha256"],
            hashlib.sha256(expected_provider_prompt.encode("utf-8")).hexdigest(),
        )

    def test_video_provider_debug_log_redacts_signed_media_url_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            destination = run_dir / "assets" / "test" / "candidate.mp4"
            destination.parent.mkdir(parents=True)
            request = image_gen_app.VideoGenerateItem(
                item_id="scene10_cut1",
                prompt="reviewed prompt",
                candidate_count=1,
            )

            log_path = image_gen_app._write_video_generation_debug_log(
                run_dir=run_dir,
                item_id=request.item_id,
                index=1,
                destination=destination,
                request=request,
                provider_result={
                    "task": {
                        "video_url": (
                            "https://signed-cdn.example/clip.mp4"
                            "?signature=secret&token=private#fragment"
                        )
                    }
                },
            )
            log_text = log_path.read_text(encoding="utf-8")
            payload = json.loads(log_text)

        self.assertEqual(
            payload["provider"]["task"]["video_url"],
            "https://signed-cdn.example/clip.mp4",
        )
        self.assertNotIn("secret", log_text)

    def test_video_candidate_from_prior_prompt_revision_is_hidden_and_rejected_for_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            manifest_path, original_text, manifest = image_gen_app._read_manifest_data(
                run_dir
            )
            manifest["scenes"][0]["cuts"] = [manifest["scenes"][0]["cuts"][0]]
            image_gen_app._write_manifest_data(
                manifest_path, original_text, manifest
            )
            mark_manifest_narration_ready(run_dir)

            class FakeKlingClient:
                def __init__(self, _config):
                    pass

                def start_video_generation(self, **_kwargs):
                    return {"data": {"id": "task-a"}}

                def extract_operation_id(self, response, **_kwargs):
                    return response["data"]["id"]

                def poll_operation(self, **_kwargs):
                    return {
                        "status": "succeeded",
                        "data": {
                            "task_result": {
                                "videos": [
                                    {"url": "https://example.test/a.mp4"}
                                ]
                            }
                        },
                    }

                def is_failed_operation(self, _operation, **_kwargs):
                    return False

                def extract_video_uri(self, operation, **_kwargs):
                    return operation["data"]["task_result"]["videos"][0][
                        "url"
                    ]

                def download_to_file(self, *, out_path: Path, **_kwargs):
                    out_path.write_bytes(MP4_BYTES)

            with patch.dict(
                os.environ,
                {"TOC_SERVER_AUTH_DISABLED": "1", "KLING_API_KEY": "fake-key"},
            ):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.KlingClient", FakeKlingClient),
                    patch(
                        "server.image_gen_app._require_narration_ready_for_video",
                        return_value={"ready": True},
                    ),
                    patch(
                        "server.image_gen_app._prepare_render_video_clip",
                        lambda _run_dir, source, _item: source,
                    ),
                    patch(
                        "server.image_gen_app._prepare_render_narration",
                        lambda _run_dir, source, _item: source,
                    ),
                    patch(
                        "server.image_gen_app._probe_media_duration_seconds",
                        lambda _path: None,
                    ),
                ):
                    with TestClient(app) as client:
                        approved_a = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "video_prompt": "主人公が左へ一歩進む",
                                        "video_first_reference": "assets/characters/hero.png",
                                    }
                                ],
                            },
                        )
                        generated_a = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": "主人公が左へ一歩進む",
                                "first_reference": "assets/characters/hero.png",
                                "candidate_count": 1,
                            },
                        )
                        stale_candidate = generated_a.json()["candidates"][0][
                            "path"
                        ]
                        pending_b = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": False,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "video_prompt": "主人公が右へ二歩進む",
                                        "video_first_reference": "assets/characters/hero.png",
                                    }
                                ],
                            },
                        )
                        video_items = client.get(
                            "/api/image-gen/video-items?run_id=sample_run"
                        )
                        _path, _text, current_manifest = (
                            image_gen_app._read_manifest_data(run_dir)
                        )
                        narration_output = current_manifest["scenes"][0]["cuts"][
                            0
                        ]["audio"]["narration"]["output"]
                        render = client.post(
                            "/api/image-gen/render-inputs/freeze",
                            json={
                                "run_id": "sample_run",
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "video_path": stale_candidate,
                                        "narration_path": narration_output,
                                        "video_duration_seconds": 8,
                                    }
                                ],
                            },
                        )

            listed = video_items.json()["items"][0]
            revision_segment = Path(stale_candidate).parts[-2]

        self.assertEqual(approved_a.status_code, 200)
        self.assertEqual(generated_a.status_code, 200)
        self.assertRegex(revision_segment, r"^[0-9a-f]{64}$")
        self.assertEqual(pending_b.status_code, 200)
        self.assertEqual(video_items.status_code, 200)
        self.assertNotEqual(listed["selectedVideoPath"], stale_candidate)
        self.assertFalse(listed["videoExists"])
        self.assertEqual(render.status_code, 400)
        self.assertIn("stale video candidate revision", render.text)

    def test_in_flight_video_candidate_completion_is_marked_stale_after_new_prompt_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            provider_started = threading.Event()
            provider_release = threading.Event()

            def controlled_generation(
                *,
                run_dir: Path,
                request: image_gen_app.VideoGenerateItem,
                index: int,
                destination: Path,
                **_kwargs: Any,
            ) -> dict[str, Any]:
                provider_started.set()
                self.assertTrue(provider_release.wait(timeout=5))
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(MP4_BYTES)
                return {
                    "index": index,
                    "status": "completed",
                    "path": destination.relative_to(run_dir).as_posix(),
                    "debugLog": None,
                    "source": request.tool,
                }

            request_a = image_gen_app.VideoPromptCreateRequest(
                run_id="sample_run",
                approve_for_generation=True,
                items=[
                    image_gen_app.FrontendReviewItem(
                        item_id="scene10_cut1",
                        kind="scene",
                        video_prompt="主人公が左へ一歩進む",
                        video_first_reference="assets/characters/hero.png",
                    )
                ],
            )
            request_b = image_gen_app.VideoPromptCreateRequest(
                run_id="sample_run",
                approve_for_generation=False,
                items=[
                    image_gen_app.FrontendReviewItem(
                        item_id="scene10_cut1",
                        kind="scene",
                        video_prompt="主人公が右へ二歩進む",
                        video_first_reference="assets/characters/hero.png",
                    )
                ],
            )

            async def exercise_stale_completion() -> dict[str, Any]:
                await image_gen_app.api_create_video_prompts(request_a)
                materialized = image_gen_app._materialized_video_generate_item(
                    run_dir=run_dir,
                    request=image_gen_app.VideoGenerateItem(
                        item_id="scene10_cut1",
                        prompt="主人公が左へ一歩進む",
                        first_reference="assets/characters/hero.png",
                        candidate_count=1,
                    ),
                )
                generation = asyncio.create_task(
                    image_gen_app._generate_video_candidates(run_dir, materialized)
                )
                self.assertTrue(
                    await asyncio.to_thread(provider_started.wait, 5)
                )
                await image_gen_app.api_create_video_prompts(request_b)
                provider_release.set()
                return await generation

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._generate_video_file_blocking",
                    controlled_generation,
                ),
            ):
                result = asyncio.run(exercise_stale_completion())
            candidate = result["candidates"][0]
            listed_candidate = image_gen_app._candidate_video_output_for_item(
                run_dir, "scene10_cut1"
            )

        self.assertEqual(candidate["status"], "stale")
        self.assertIsNone(candidate["path"])
        self.assertRegex(
            str(candidate["stalePath"]),
            r"/scene10_cut1/[0-9a-f]{64}/candidate_01\.mp4$",
        )
        self.assertIsNone(listed_candidate)

    def test_video_generate_rejects_exact_but_pending_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            mark_manifest_narration_ready(run_dir)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch(
                        "server.image_gen_app._require_narration_ready_for_video",
                        return_value={"ready": True},
                    ),
                    patch("server.image_gen_app._generate_video_candidates") as generate,
                ):
                    with TestClient(app) as client:
                        created = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "assets/characters/hero.png",
                                    }
                                ],
                            },
                        )
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": REVIEWABLE_VIDEO_PROMPT,
                                "first_reference": "assets/characters/hero.png",
                                "candidate_count": 1,
                            },
                        )

        self.assertEqual(created.status_code, 200)
        self.assertFalse(created.json()["approvedForGeneration"])
        self.assertEqual(response.status_code, 409)
        self.assertIn("not approved", response.text)
        generate.assert_not_called()

    def test_video_generate_rejects_prompt_that_differs_from_materialized_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            mark_manifest_narration_ready(run_dir)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._require_narration_ready_for_video", return_value={"ready": True}),
                    patch("server.image_gen_app._generate_video_candidates") as generate,
                ):
                    with TestClient(app) as client:
                        created = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "output": "assets/scenes/scene10_cut1.png",
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "assets/characters/hero.png",
                                    }
                                ],
                            },
                        )
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": "unreviewed different prompt",
                                "first_reference": "assets/characters/hero.png",
                                "candidate_count": 1,
                            },
                        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(response.status_code, 409)
        self.assertIn("materialized video prompt", response.text)
        generate.assert_not_called()

    def test_video_generate_rejects_materialized_prompt_after_design_dependency_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            mark_manifest_narration_ready(run_dir)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._require_narration_ready_for_video", return_value={"ready": True}),
                    patch("server.image_gen_app._generate_video_candidates") as generate,
                ):
                    with TestClient(app) as client:
                        created = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "assets/characters/hero.png",
                                    }
                                ],
                            },
                        )
                        manifest_path = run_dir / "video_manifest.md"
                        original_text = manifest_path.read_text(encoding="utf-8")
                        manifest_data = yaml.safe_load(
                            image_gen_app._extract_manifest_yaml_text(original_text)
                        )
                        manifest_data["scenes"][0]["time_of_day"] = "夜"
                        image_gen_app._write_manifest_data(
                            manifest_path,
                            original_text,
                            manifest_data,
                        )
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": REVIEWABLE_VIDEO_PROMPT,
                                "first_reference": "assets/characters/hero.png",
                                "candidate_count": 1,
                            },
                        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(response.status_code, 409)
        self.assertIn("materialized video prompt is stale", response.text)
        generate.assert_not_called()

    def test_video_generate_rejects_settings_and_reference_drift_after_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            mark_manifest_narration_ready(run_dir)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._require_narration_ready_for_video", return_value={"ready": True}),
                    patch("server.image_gen_app._generate_video_candidates") as generate,
                ):
                    with TestClient(app) as client:
                        created = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "assets/characters/hero.png",
                                        "video_tool": "seedance",
                                    }
                                ],
                            },
                        )
                        manifest_path = run_dir / "video_manifest.md"
                        original_text = manifest_path.read_text(encoding="utf-8")
                        manifest_data = yaml.safe_load(
                            image_gen_app._extract_manifest_yaml_text(original_text)
                        )
                        video_generation = manifest_data["scenes"][0]["cuts"][0]["video_generation"]
                        video_generation["references"] = ["assets/characters/hero.png"]
                        video_generation["quality"] = "720p"
                        video_generation["aspect_ratio"] = "9:16"
                        image_gen_app._write_manifest_data(
                            manifest_path,
                            original_text,
                            manifest_data,
                        )
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": REVIEWABLE_VIDEO_PROMPT,
                                "first_reference": "assets/characters/hero.png",
                                "references": ["assets/characters/hero.png"],
                                "quality": "720p",
                                "aspect_ratio": "9:16",
                                "tool": "seedance",
                                "candidate_count": 1,
                            },
                        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(response.status_code, 409)
        self.assertIn("stale", response.text)
        generate.assert_not_called()

    def test_video_generate_rejects_provider_model_drift_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            mark_manifest_narration_ready(run_dir)

            with patch.dict(
                os.environ,
                {
                    "TOC_SERVER_AUTH_DISABLED": "1",
                    "KLING_VIDEO_MODEL": "reviewed-model",
                    "KLING_EXTRA_JSON": '{"cfg_scale": 0.4}',
                },
            ):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch(
                        "server.image_gen_app._require_narration_ready_for_video",
                        return_value={"ready": True},
                    ),
                    patch("server.image_gen_app._generate_video_candidates") as generate,
                ):
                    with TestClient(app) as client:
                        created = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "assets/characters/hero.png",
                                    }
                                ],
                            },
                        )
                        os.environ["KLING_VIDEO_MODEL"] = "unreviewed-model"
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": REVIEWABLE_VIDEO_PROMPT,
                                "first_reference": "assets/characters/hero.png",
                                "candidate_count": 1,
                            },
                        )

            manifest = yaml.safe_load(
                image_gen_app._extract_manifest_yaml_text(
                    (run_dir / "video_manifest.md").read_text(encoding="utf-8")
                )
            )
            binding = manifest["scenes"][0]["cuts"][0]["video_generation"][
                "api_prompt_payload"
            ]["provider_request_binding"]

        self.assertEqual(created.status_code, 200)
        self.assertEqual(
            binding["execution_options"]["model"],
            "reviewed-model",
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("stale", response.text)
        generate.assert_not_called()

    def test_video_generate_rejects_tampered_saved_provider_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            mark_manifest_narration_ready(run_dir)

            with patch.dict(
                os.environ,
                {
                    "TOC_SERVER_AUTH_DISABLED": "1",
                    "KLING_VIDEO_MODEL": "reviewed-model",
                },
            ):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch(
                        "server.image_gen_app._require_narration_ready_for_video",
                        return_value={"ready": True},
                    ),
                    patch("server.image_gen_app._generate_video_candidates") as generate,
                ):
                    with TestClient(app) as client:
                        created = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "assets/characters/hero.png",
                                    }
                                ],
                            },
                        )
                        manifest_path = run_dir / "video_manifest.md"
                        original_text = manifest_path.read_text(encoding="utf-8")
                        manifest_data = yaml.safe_load(
                            image_gen_app._extract_manifest_yaml_text(original_text)
                        )
                        binding = manifest_data["scenes"][0]["cuts"][0][
                            "video_generation"
                        ]["api_prompt_payload"]["provider_request_binding"]
                        binding["execution_options"]["model"] = "tampered-model"
                        image_gen_app._write_manifest_data(
                            manifest_path,
                            original_text,
                            manifest_data,
                        )
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": REVIEWABLE_VIDEO_PROMPT,
                                "first_reference": "assets/characters/hero.png",
                                "candidate_count": 1,
                            },
                        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(response.status_code, 409)
        self.assertIn("provider request binding", response.text)
        generate.assert_not_called()

    def test_video_generate_rejects_reference_content_drift_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            mark_manifest_narration_ready(run_dir)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch(
                        "server.image_gen_app._require_narration_ready_for_video",
                        return_value={"ready": True},
                    ),
                    patch("server.image_gen_app._generate_video_candidates") as generate,
                ):
                    with TestClient(app) as client:
                        created = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "assets/characters/hero.png",
                                    }
                                ],
                            },
                        )
                        write_test_png(
                            run_dir / "assets" / "characters" / "hero.png",
                            (1, 2, 3),
                        )
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": REVIEWABLE_VIDEO_PROMPT,
                                "first_reference": "assets/characters/hero.png",
                                "candidate_count": 1,
                            },
                        )

            manifest = yaml.safe_load(
                image_gen_app._extract_manifest_yaml_text(
                    (run_dir / "video_manifest.md").read_text(encoding="utf-8")
                )
            )
            execution_options = manifest["scenes"][0]["cuts"][0][
                "video_generation"
            ]["api_prompt_payload"]["provider_request_binding"][
                "execution_options"
            ]

        self.assertEqual(created.status_code, 200)
        self.assertIn("reference_content_sha256", execution_options)
        self.assertEqual(response.status_code, 409)
        self.assertIn("stale", response.text)
        generate.assert_not_called()

    def test_kling_provider_uses_materialized_execution_options(self) -> None:
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
                return {
                    "status": "succeeded",
                    "data": {
                        "task_result": {
                            "videos": [{"url": "https://example.test/video.mp4"}]
                        }
                    },
                }

            def is_failed_operation(self, _operation, **_kwargs):
                return False

            def extract_video_uri(self, operation, **_kwargs):
                return operation["data"]["task_result"]["videos"][0]["url"]

            def download_to_file(self, *, out_path: Path, **_kwargs):
                out_path.write_bytes(MP4_BYTES)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "candidate.mp4"
            request = image_gen_app.VideoGenerateItem(
                item_id="scene10_cut1",
                prompt="reviewed prompt",
                negative_prompt="reviewed negative",
                provider_execution_options={
                    "backend": "kling",
                    "model": "reviewed-model",
                    "extra_payload": {"cfg_scale": 0.4},
                },
            )
            with (
                patch.dict(
                    os.environ,
                    {"KLING_VIDEO_MODEL": "unreviewed-model", "KLING_API_KEY": "key"},
                ),
                patch("server.image_gen_app.KlingClient", FakeKlingClient),
            ):
                image_gen_app._generate_kling_video_file(
                    request=request,
                    input_image=None,
                    last_frame_image=None,
                    out_path=output,
                )

        self.assertEqual(calls[0]["model"], "reviewed-model")
        self.assertEqual(calls[0]["extra_payload"], {"cfg_scale": 0.4})

    def test_video_provider_receives_hash_checked_private_reference_snapshot(self) -> None:
        captured_input: Path | None = None

        def fake_generate_kling_video_file(
            *,
            request: image_gen_app.VideoGenerateItem,
            input_image: Path | None,
            last_frame_image: Path | None,
            out_path: Path,
        ) -> dict[str, Any]:
            nonlocal captured_input
            self.assertIsNotNone(input_image)
            assert input_image is not None
            captured_input = input_image
            self.assertEqual(input_image.read_bytes(), PNG_BYTES)
            self.assertIsNone(last_frame_image)
            out_path.write_bytes(MP4_BYTES)
            return {"provider": "kling", "model": "reviewed-model"}

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            reference = run_dir / "assets" / "scenes" / "start.png"
            reference.parent.mkdir(parents=True, exist_ok=True)
            reference.write_bytes(PNG_BYTES)
            relative_reference = "assets/scenes/start.png"
            request = image_gen_app.VideoGenerateItem(
                item_id="scene10_cut1",
                prompt="reviewed prompt",
                first_reference=relative_reference,
                provider_execution_options={
                    "backend": "kling",
                    "model": "reviewed-model",
                    "reference_content_sha256": {
                        relative_reference: hashlib.sha256(PNG_BYTES).hexdigest(),
                    },
                },
            )
            destination = run_dir / "assets" / "video" / "candidate.mp4"
            with patch(
                "server.image_gen_app._generate_kling_video_file",
                side_effect=fake_generate_kling_video_file,
            ):
                image_gen_app._generate_video_file_blocking(
                    run_dir=run_dir,
                    request=request,
                    index=1,
                    destination=destination,
                    input_image=reference,
                    last_frame_image=None,
                    reference_images=[],
                )

            self.assertIsNotNone(captured_input)
            assert captured_input is not None
            self.assertNotEqual(captured_input, reference)
            self.assertFalse(captured_input.exists())
            self.assertEqual(destination.read_bytes(), MP4_BYTES)

    def test_video_provider_rejects_reference_bytes_changed_after_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            reference = run_dir / "assets" / "scenes" / "start.png"
            reference.parent.mkdir(parents=True, exist_ok=True)
            reference.write_bytes(b"changed-after-materialization")
            relative_reference = "assets/scenes/start.png"
            request = image_gen_app.VideoGenerateItem(
                item_id="scene10_cut1",
                prompt="reviewed prompt",
                first_reference=relative_reference,
                provider_execution_options={
                    "backend": "kling",
                    "model": "reviewed-model",
                    "reference_content_sha256": {
                        relative_reference: hashlib.sha256(PNG_BYTES).hexdigest(),
                    },
                },
            )

            with (
                patch("server.image_gen_app._generate_kling_video_file") as generate,
                self.assertRaisesRegex(ValueError, "changed before provider submission"),
            ):
                image_gen_app._generate_video_file_blocking(
                    run_dir=run_dir,
                    request=request,
                    index=1,
                    destination=run_dir / "candidate.mp4",
                    input_image=reference,
                    last_frame_image=None,
                    reference_images=[],
                )

            generate.assert_not_called()

    def test_video_generate_rejects_review_artifact_prompt_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            mark_manifest_narration_ready(run_dir)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._require_narration_ready_for_video", return_value={"ready": True}),
                    patch("server.image_gen_app._generate_video_candidates") as generate,
                ):
                    with TestClient(app) as client:
                        created = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "assets/characters/hero.png",
                                    }
                                ],
                            },
                        )
                        request_path = run_dir / "video_generation_requests.md"
                        request_text = request_path.read_text(encoding="utf-8")
                        request_path.write_text(
                            request_text.replace(
                                "[主動作]",
                                "[主動作]\n未承認の別動作。",
                                1,
                            ),
                            encoding="utf-8",
                        )
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": REVIEWABLE_VIDEO_PROMPT,
                                "first_reference": "assets/characters/hero.png",
                                "candidate_count": 1,
                            },
                        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(response.status_code, 409)
        self.assertIn("review", response.text.lower())
        generate.assert_not_called()

    def test_video_generate_rejects_missing_narration_ready_before_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_valid_p650_artifacts(root, "sample_run")

            class FakeKlingClient:
                def __init__(self, *_args, **_kwargs):
                    raise AssertionError("provider must not be constructed before narration is ready")

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
                                "prompt": REVIEWABLE_VIDEO_PROMPT,
                                "first_reference": "assets/characters/hero.png",
                                "candidate_count": 1,
                            },
                        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("requires audio files or silent approvals for all cuts", response.text)

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
                                "prompt": REVIEWABLE_VIDEO_PROMPT,
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

    def test_narration_drafts_create_preserves_existing_review_without_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p680_artifacts(root, "sample_run")
            manifest_path = run_dir / "video_manifest.md"
            original_text = manifest_path.read_text(encoding="utf-8")
            data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(original_text)) or {}
            first_cut = data["scenes"][0]["cuts"][0]
            first_cut["audio"] = {
                "narration": {
                    "status": "review_pending",
                    "text": "既存レビュー中の文面",
                    "tts_text": "既存レビュー中の文面。",
                    "output": "assets/audio/scene10_cut1/custom.mp3",
                }
            }
            image_gen_app._write_manifest_data(manifest_path, original_text, data)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/narration-drafts/create",
                            json={"run_id": "sample_run", "replace": False},
                        )

            updated_data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(manifest_path.read_text(encoding="utf-8")))
            cuts = updated_data["scenes"][0]["cuts"]

        self.assertEqual(response.status_code, 200)
        self.assertIn("scene10_cut1", response.json()["skipped"])
        self.assertEqual(cuts[0]["audio"]["narration"]["text"], "既存レビュー中の文面")
        self.assertEqual(cuts[1]["audio"]["narration"]["status"], "")
        self.assertEqual(cuts[1]["audio"]["narration"]["authoring_status"], "missing")
        self.assertEqual(cuts[1]["audio"]["narration"]["missing_reason"], "p700_narration_not_written_yet")
        self.assertEqual(cuts[1]["audio"]["narration"]["text"], "")
        self.assertEqual(cuts[1]["audio"]["narration"]["tts_text"], "")
        self.assertIn("scene_narration_plan", updated_data["scenes"][0])

    def test_narration_drafts_create_does_not_write_placeholder_text_before_p700(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p680_artifacts(root, "sample_run")
            manifest_path = run_dir / "video_manifest.md"
            original_text = manifest_path.read_text(encoding="utf-8")
            data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(original_text)) or {}
            first_cut = data["scenes"][0]["cuts"][0]
            first_cut["narration_text"] = "先取りしてはいけない簡易文"
            first_cut["cut_contract"] = {
                "schema_version": "cut_contract_v1",
                "narration_contract": {
                    "role": "emotion",
                    "target_function": "主人公の決意を補う",
                    "text": "contractからの仮文も入れない",
                    "tts_text": "contract ttsも入れない",
                },
            }
            image_gen_app._write_manifest_data(manifest_path, original_text, data)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/narration-drafts/create",
                            json={"run_id": "sample_run", "replace": False},
                        )

            updated_data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(manifest_path.read_text(encoding="utf-8")))
            narration = updated_data["scenes"][0]["cuts"][0]["audio"]["narration"]
            state_text = (run_dir / "state.txt").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(narration["authoring_status"], "missing")
        self.assertEqual(narration["missing_reason"], "p700_narration_not_written_yet")
        self.assertEqual(narration["text"], "")
        self.assertEqual(narration["tts_text"], "")
        self.assertEqual(narration["output"], "")
        self.assertEqual(narration["text_draft"], "")
        self.assertEqual(narration["elevenlabs_prompt"]["spoken_body"], "")
        self.assertEqual(narration["elevenlabs_prompt"]["materialized"], "")
        self.assertEqual(narration["review"]["status"], "")
        self.assertIn("runtime.stage=narration_contract_ready_p700_text_missing", state_text)
        self.assertIn("slot.p720.status=pending", state_text)

    def test_narration_drafts_replace_does_not_require_existing_image_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            manifest_path = run_dir / "video_manifest.md"
            original_text = manifest_path.read_text(encoding="utf-8")
            data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(original_text)) or {}
            data["scenes"][0]["cuts"][0]["audio"] = {
                "narration": {
                    "status": "review_pending",
                    "text": "古い文面",
                    "tts_text": "古い文面。",
                }
            }
            image_gen_app._write_manifest_data(manifest_path, original_text, data)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/narration-drafts/create",
                            json={"run_id": "sample_run", "replace": True},
                        )

            updated_data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(manifest_path.read_text(encoding="utf-8")))
            cuts = updated_data["scenes"][0]["cuts"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["skipped"], [])
        self.assertEqual(len(response.json()["updated"]), 3)
        self.assertEqual(cuts[0]["audio"]["narration"]["status"], "")
        self.assertEqual(cuts[0]["audio"]["narration"]["authoring_status"], "missing")
        self.assertEqual(cuts[0]["audio"]["narration"]["missing_reason"], "p700_narration_not_written_yet")
        self.assertEqual(cuts[0]["audio"]["narration"]["text"], "")
        self.assertEqual(cuts[0]["audio"]["narration"]["tts_text"], "")

    def test_narration_generate_creates_unapproved_candidate_without_duration_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            (run_dir / "script.md").write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 10-1
        narration: ""
        tts_text: ""
```
""",
                encoding="utf-8",
            )

            async def fake_generate_one(_run_dir: Path, req: image_gen_app.NarrationGenerateItem) -> dict[str, Any]:
                candidate_path = image_gen_app.resolve_run_relative(_run_dir, str(req.output))
                candidate_path.parent.mkdir(parents=True, exist_ok=True)
                candidate_path.write_bytes(b"candidate-audio")
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
                        saved = client.post(
                            "/api/image-gen/narration-text/save",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "text": "読み上げ本文",
                                "tts_text": "読み上げ本文。",
                                "tool": "elevenlabs",
                                "authoring_status": "human_locked",
                                "expected_revision": 0,
                            },
                        )
                        self.assertEqual(saved.status_code, 200, saved.text)
                        revision = saved.json()["item"]["revision"]
                        response = client.post(
                            "/api/image-gen/narration-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "output": "assets/audio/scene10_cut1.mp3",
                                "tool": "elevenlabs",
                                "expected_revision": revision["number"],
                                "expected_tts_hash": revision["tts_hash"],
                            },
                        )

            data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text((run_dir / "video_manifest.md").read_text(encoding="utf-8")))
            cut = data["scenes"][0]["cuts"][0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"]["status"], "candidate")
        self.assertEqual(cut["audio"]["narration"]["text"], "読み上げ本文")
        self.assertEqual(cut["audio"]["narration"]["tts_text"], "読み上げ本文。")
        self.assertEqual(cut["audio"]["narration"]["output"], "")
        self.assertEqual(cut["audio"]["narration"]["status"], "candidate")
        self.assertFalse(cut["audio"]["narration"]["review"]["human_review_ok"])
        self.assertNotIn("video_generation", cut)

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
            mark_manifest_narration_ready(run_dir)
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
                    patch("server.image_gen_app._require_narration_ready_for_video", return_value={"ready": True}),
                ):
                    with TestClient(app) as client:
                        materialized = client.post(
                            "/api/image-gen/video-prompts/create",
                            json={
                                "run_id": "sample_run",
                                "approve_for_generation": True,
                                "items": [
                                    {
                                        "item_id": "scene10_cut1",
                                        "kind": "scene",
                                        "video_prompt": REVIEWABLE_VIDEO_PROMPT,
                                        "video_first_reference": "assets/characters/hero.png",
                                        "video_duration_seconds": 4,
                                        "video_tool": "kling_3_0",
                                    }
                                ],
                            },
                        )
                        response = client.post(
                            "/api/image-gen/video-generate",
                            json={
                                "run_id": "sample_run",
                                "item_id": "scene10_cut1",
                                "prompt": REVIEWABLE_VIDEO_PROMPT,
                                "first_reference": "assets/characters/hero.png",
                                "duration_seconds": 10,
                                "candidate_count": 1,
                            },
                        )

            payload = response.json()

        self.assertEqual(materialized.status_code, 200)
        self.assertEqual(
            materialized.json()["durationSecondsByItem"]["scene10_cut1"],
            10,
        )
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

    def test_render_inputs_freeze_materializes_confirmed_silence_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            videos_dir = run_dir / "assets" / "scenes"
            videos_dir.mkdir(parents=True, exist_ok=True)
            (videos_dir / "scene10_cut1.mp4").write_bytes(MP4_BYTES)
            manifest_path = run_dir / "video_manifest.md"
            original_text = manifest_path.read_text(encoding="utf-8")
            data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(original_text)) or {}
            data["scenes"][0]["cuts"] = [data["scenes"][0]["cuts"][0]]
            image_gen_app._write_manifest_data(manifest_path, original_text, data)
            mark_manifest_narration_ready(run_dir, silent={"scene10_cut1"})

            def fake_write_silence(path: Path, _duration_seconds: float) -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fake-silence")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app._write_silence_audio", fake_write_silence),
                    patch("server.image_gen_app._prepare_render_video_clip", lambda _run_dir, source, _item: source),
                    patch("server.image_gen_app._prepare_render_narration", lambda _run_dir, source, _item: source),
                    patch("server.image_gen_app._probe_media_duration_seconds", lambda _path: None),
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
                                        "narration_path": None,
                                        "video_duration_seconds": 4,
                                    }
                                ],
                            },
                        )

            updated_data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text(manifest_path.read_text(encoding="utf-8")))
            narration_output = updated_data["scenes"][0]["cuts"][0]["audio"]["narration"]["output"]
            narration_text = (run_dir / "video_narration_list.txt").read_text(encoding="utf-8")
            silent_file_exists = (run_dir / narration_output).is_file()

        self.assertEqual(response.status_code, 200)
        self.assertIn("intentional_silence", narration_output)
        self.assertTrue(silent_file_exists)
        self.assertIn("intentional_silence", narration_text)

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

    def test_regenerate_prompts_recompiles_v2_manifest_request_and_snapshot(self) -> None:
        plan = {
            "schema_version": "first_frame_visual_plan_v1",
            "source_grounding": {"source_event_beat_id": "beat-1"},
            "temporal_boundary": {
                "event_fact_visible_in_still": "古い瞬間",
                "not_yet_happened_in_still": ["扉はまだ開かない"],
            },
            "subject_binding": {"primary_subject": {"id": "", "name": "半分開いた扉"}},
            "reference_binding": {},
            "character_state_gate": {},
            "object_visibility_gate": {"objects": []},
            "spatial_composition": {"foreground": "床", "midground": "扉", "background": "廊下"},
            "scene_material_pack": {"light_source": "窓", "light_direction": "左", "dominant_materials": ["木"]},
            "scene_state_progression": {"progression_mode": "suspended_moment"},
        }
        _plan, payload = image_gen_app._apply_v2_visual_plan_patch_and_compile(
            plan,
            {},
            character_ids=[],
            object_ids=[],
            location_ids=[],
            references=[],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output/sample_run"
            run_dir.mkdir(parents=True)
            manifest = {
                "scenes": [{"scene_id": "10", "cuts": [{"cut_id": "1", "image_generation": {
                    "tool": "codex_builtin_image",
                    "character_ids": [], "object_ids": [], "location_ids": [], "references": [],
                    "output": "assets/scenes/scene10_cut1.png",
                    "first_frame_visual_plan": plan,
                    "api_prompt_payload": payload,
                }}]}]
            }
            (run_dir / "video_manifest.md").write_text(
                "```yaml\n" + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False) + "```\n",
                encoding="utf-8",
            )

            def materialize() -> None:
                data = yaml.safe_load(image_gen_app._extract_manifest_yaml_text((run_dir / "video_manifest.md").read_text(encoding="utf-8")))
                image_generation = data["scenes"][0]["cuts"][0]["image_generation"]
                compiled_payload = image_generation["api_prompt_payload"]
                request_text = "\n".join([
                    "# Image Generation Requests", "", "## scene10_cut1", "",
                    "- tool: `codex_builtin_image`",
                    "- prompt_policy_version: `image_api_prompt_v2`",
                    f"- compiler_version: `{compiled_payload['compiler_version']}`",
                    f"- source_digest: `{compiled_payload['source_digest']}`",
                    "- output: `assets/scenes/scene10_cut1.png`",
                    "- references: `[]`", "", "```api_prompt",
                    compiled_payload["prompt"], "```", "",
                ])
                request_path = run_dir / "image_generation_requests.md"
                request_path.write_text(request_text, encoding="utf-8")
                snapshot = materialize_request_snapshot(
                    run_dir,
                    kind="scene",
                    items=[{
                        "item_id": "scene10_cut1",
                        "destination": "assets/scenes/scene10_cut1.png",
                        "prompt": compiled_payload["prompt"],
                        "prompt_policy_version": "image_api_prompt_v2",
                        "compiler_version": compiled_payload["compiler_version"],
                        "source_digest": compiled_payload["source_digest"],
                        "references": [],
                        "api_prompt_payload": compiled_payload,
                    }],
                    source_artifact="image_generation_requests.md",
                )
                write_request_snapshot_atomic(run_dir / "image_generation_request_snapshot.json", snapshot, run_dir=run_dir)

            materialize()
            setting = root / "docs/implementation/image-prompting.md"
            setting.parent.mkdir(parents=True)
            setting.write_text(
                "<!-- image-gen-setting:scene:start -->\nscene rules\n<!-- image-gen-setting:scene:end -->\n",
                encoding="utf-8",
            )

            class FakeClient:
                async def start(self): return None
                async def stop(self): return None
                async def revise_first_frame_visual_plan(self, **_kwargs):
                    return {"event_fact_visible_in_still": "主人公が半分開いた扉へ手を伸ばす", "light_source": "細い朝日"}

            async def fake_materialize(_run_id: str) -> None:
                materialize()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.create_codex_app_server_client", return_value=FakeClient()),
                    patch("server.image_gen_app._materialize_scene_requests", fake_materialize),
                ):
                    with TestClient(app) as client:
                        response = client.post("/api/image-gen/regenerate-prompts", json={
                            "run_id": "sample_run", "target": "scene", "instruction": "朝日にして", "item_ids": ["scene10_cut1"]
                        })
            updated_manifest = yaml.safe_load(image_gen_app._extract_manifest_yaml_text((run_dir / "video_manifest.md").read_text(encoding="utf-8")))
            updated_snapshot = load_request_snapshot(run_dir / "image_generation_request_snapshot.json", run_dir=run_dir)
            recompile_state = image_gen_app.parse_state_file(run_dir / "state.txt")
            rollback_paths = [
                run_dir / "video_manifest.md",
                run_dir / "image_generation_requests.md",
                run_dir / "image_generation_request_snapshot.json",
            ]
            before_failed_recompile = {path: path.read_bytes() for path in rollback_paths}

            async def fail_materialize(_run_id: str) -> None:
                raise RuntimeError("materializer failed")

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch("server.image_gen_app.create_codex_app_server_client", return_value=FakeClient()),
                    patch("server.image_gen_app._materialize_scene_requests", fail_materialize),
                ):
                    with TestClient(app) as client:
                        failed_response = client.post("/api/image-gen/regenerate-prompts", json={
                            "run_id": "sample_run", "target": "scene", "instruction": "夜にして", "item_ids": ["scene10_cut1"]
                        })
            after_failed_recompile = {path: path.read_bytes() for path in rollback_paths}

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["operation"], "recompiled")
        self.assertEqual(response.json()["prompts"][0]["operation"], "recompiled")
        updated_image_generation = updated_manifest["scenes"][0]["cuts"][0]["image_generation"]
        self.assertEqual(updated_image_generation["first_frame_visual_plan"]["scene_material_pack"]["light_source"], "細い朝日")
        self.assertEqual(updated_snapshot.items[0].prompt, updated_image_generation["api_prompt_payload"]["prompt"])
        self.assertNotEqual(updated_snapshot.items[0].prompt, payload["prompt"])
        self.assertEqual(recompile_state["runtime.stage"], "prompt_recompiled_awaiting_semantic_review")
        self.assertEqual(recompile_state["review.image_prompt.request_freeze.status"], "draft")
        self.assertEqual(recompile_state["slot.p650.status"], "pending")
        self.assertEqual(recompile_state["review.semantic.image_prompt.status"], "pending")
        self.assertEqual(recompile_state["slot.p680.status"], "pending")
        self.assertEqual(failed_response.status_code, 400)
        self.assertEqual(after_failed_recompile, before_failed_recompile)

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
                transcript = []
                source = "app_server"
                provenance_authoritative = True
                turn_id = "turn-1"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    test_case.assertEqual(kwargs["run_dir"].name, "parent")
                    return ImageGenerationResult(
                        saved_path=saved,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                        source="app_server",
                        generation_job_id=str(kwargs["generation_job_id"]),
                        item_id=str(kwargs["item_id"]),
                        turn_id="turn-1",
                        prompt_sha256=hashlib.sha256(str(kwargs["prompt"]).encode("utf-8")).hexdigest(),
                        reference_sha256s=[],
                        image_generation_item_id="image-1",
                        image_generation_item_count=1,
                        destination=str(kwargs["output_path"]),
                        provenance_authoritative=True,
                        provenance_policy="request_bound_v2",
                    )

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
                                        "prompt_policy_version": "image_api_prompt_v1",
                                        "debug_prompt_source": {"send_to_api": False},
                                        "references": [],
                                        "candidate_count": 1,
                                    }
                                ],
                            },
                        )
                        generated_exists = (
                            parent_run / "assets/test/image_gen_candidates/scene1_cut1/scene1_cut1_candidate_01.png"
                        ).resolve().exists()
                        debug_log = response.json()["results"][0]["candidates"][0]["debugLog"]
                        payload = json.loads((parent_run / debug_log).read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(generated_exists)
        self.assertEqual(payload["apiPromptPolicyVersion"], "image_api_prompt_v1")
        self.assertEqual(payload["debugPromptSource"], {"send_to_api": False})

    def test_generate_rejects_v1_missing_api_prompt_before_app_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output" / "parent").mkdir(parents=True)
            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root), patch("server.image_gen_app.create_codex_app_server_client") as create_client:
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/generate",
                            json={
                                "run_id": "parent",
                                "kind": "scene",
                                "item_id": "scene1_cut1",
                                "prompt": "",
                                "prompt_policy_version": "image_api_prompt_v1",
                                "debug_prompt_source": {"send_to_api": False},
                                "references": [],
                                "candidate_count": 1,
                            },
                        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "api_prompt_missing_for_new_prompt_policy")
        create_client.assert_not_called()

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

    def test_insert_bulk_rejects_active_create_resume_lease_without_overwriting_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            output = run_dir / "assets/scenes/scene01.png"
            candidate = image_gen.candidate_path(run_dir, "scene01", 1)
            write_test_png(output, color=(10, 20, 30))
            write_test_png(candidate, color=(200, 210, 220))
            original_bytes = output.read_bytes()

            with sync_file_lock(
                run_dir / ".locks" / "create_resume.lock",
                wait=False,
            ):
                with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                    with patch("server.image_gen_app.ROOT", root):
                        with TestClient(app) as client:
                            response = client.post(
                                "/api/image-gen/insert-bulk",
                                json={
                                    "items": [
                                        {
                                            "run_id": "sample_run",
                                            "candidate_path": candidate.relative_to(
                                                run_dir
                                            ).as_posix(),
                                            "output": output.relative_to(
                                                run_dir
                                            ).as_posix(),
                                        }
                                    ]
                                },
                            )

            persisted_bytes = output.read_bytes()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(persisted_bytes, original_bytes)

    def test_insert_bulk_waits_for_scene_request_revision_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## scene01

- output: `assets/scenes/scene01.png`
- references: `[]`

```text
scene one
```
""",
                encoding="utf-8",
            )
            output = run_dir / "assets/scenes/scene01.png"
            candidate = image_gen.candidate_path(run_dir, "scene01", 1)
            write_test_png(output, color=(10, 20, 30))
            write_test_png(candidate, color=(200, 210, 220))
            original_bytes = output.read_bytes()
            candidate_bytes = candidate.read_bytes()

            def post_insert() -> Any:
                with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                    with patch("server.image_gen_app.ROOT", root):
                        with TestClient(app) as client:
                            return client.post(
                                "/api/image-gen/insert-bulk",
                                json={
                                    "items": [
                                        {
                                            "run_id": "sample_run",
                                            "candidate_path": candidate.relative_to(
                                                run_dir
                                            ).as_posix(),
                                            "output": output.relative_to(
                                                run_dir
                                            ).as_posix(),
                                        }
                                    ]
                                },
                            )

            with ThreadPoolExecutor(max_workers=1) as executor:
                with sync_file_lock(
                    run_dir / ".locks" / "scene_request_revision.lock",
                    wait=False,
                ):
                    future = executor.submit(post_insert)
                    time.sleep(0.1)
                    self.assertFalse(future.done())
                    self.assertEqual(output.read_bytes(), original_bytes)
                response = future.result(timeout=5)

            persisted_bytes = output.read_bytes()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(persisted_bytes, candidate_bytes)

    def test_insert_bulk_preflights_every_item_before_any_canonical_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## scene01

- output: `assets/scenes/scene01.png`
- references: `[]`

```text
scene one
```

## scene02

- output: `assets/scenes/scene02.png`
- references: `[]`

```text
scene two
```
""",
                encoding="utf-8",
            )
            output_one = run_dir / "assets/scenes/scene01.png"
            output_two = run_dir / "assets/scenes/scene02.png"
            candidate_one = image_gen.candidate_path(run_dir, "scene01", 1)
            candidate_two = image_gen.candidate_path(run_dir, "scene02", 1)
            write_test_png(output_one, color=(10, 20, 30))
            write_test_png(output_two, color=(30, 20, 10))
            write_test_png(candidate_one, color=(200, 210, 220))
            candidate_two.parent.mkdir(parents=True)
            candidate_two.write_bytes(b"not-a-png")
            original_one = output_one.read_bytes()
            original_two = output_two.read_bytes()
            state_file = run_dir / "state.txt"
            state_file.write_text(
                "slot.p650.status=done\nslot.p680.status=awaiting_approval\n",
                encoding="utf-8",
            )
            original_state = state_file.read_bytes()

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with patch("server.image_gen_app.ROOT", root):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/insert-bulk",
                            json={
                                "items": [
                                    {
                                        "run_id": "sample_run",
                                        "candidate_path": candidate_one.relative_to(
                                            run_dir
                                        ).as_posix(),
                                        "output": output_one.relative_to(
                                            run_dir
                                        ).as_posix(),
                                    },
                                    {
                                        "run_id": "sample_run",
                                        "candidate_path": candidate_two.relative_to(
                                            run_dir
                                        ).as_posix(),
                                        "output": output_two.relative_to(
                                            run_dir
                                        ).as_posix(),
                                    },
                                ]
                            },
                        )

            persisted_one = output_one.read_bytes()
            persisted_two = output_two.read_bytes()
            persisted_state = state_file.read_bytes()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(persisted_one, original_one)
        self.assertEqual(persisted_two, original_two)
        self.assertEqual(persisted_state, original_state)

    def test_insert_bulk_rolls_back_earlier_output_when_later_copy_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## scene01

- output: `assets/scenes/scene01.png`
- references: `[]`

```text
scene one
```

## scene02

- output: `assets/scenes/scene02.png`
- references: `[]`

```text
scene two
```
""",
                encoding="utf-8",
            )
            outputs = (
                run_dir / "assets/scenes/scene01.png",
                run_dir / "assets/scenes/scene02.png",
            )
            candidates = (
                image_gen.candidate_path(run_dir, "scene01", 1),
                image_gen.candidate_path(run_dir, "scene02", 1),
            )
            for index, output in enumerate(outputs):
                write_test_png(output, color=(10 + index, 20, 30))
                write_test_png(candidates[index], color=(200 + index, 210, 220))
            originals = tuple(output.read_bytes() for output in outputs)
            real_insert = image_gen_app.insert_candidate
            call_count = 0

            def fail_second_insert(
                insert_run_dir: Path,
                candidate: Path,
                output: str,
            ) -> dict[str, str | None]:
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise OSError("synthetic second copy failure")
                return real_insert(insert_run_dir, candidate, output)

            with patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch(
                        "server.image_gen_app.insert_candidate",
                        side_effect=fail_second_insert,
                    ),
                ):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/image-gen/insert-bulk",
                            json={
                                "items": [
                                    {
                                        "run_id": "sample_run",
                                        "candidate_path": candidate.relative_to(
                                            run_dir
                                        ).as_posix(),
                                        "output": output.relative_to(
                                            run_dir
                                        ).as_posix(),
                                    }
                                    for candidate, output in zip(
                                        candidates,
                                        outputs,
                                        strict=True,
                                    )
                                ]
                            },
                        )

            persisted = tuple(output.read_bytes() for output in outputs)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(persisted, originals)
        self.assertEqual(call_count, 2)

    def test_insert_bulk_invalidates_old_provenance_and_p650_p680_for_asset_and_scene_outputs(
        self,
    ) -> None:
        cases = (
            (
                "asset",
                "asset_generation_requests.md",
                "asset_generation_request_snapshot.json",
                "hero_ref",
                "assets/characters/hero_ref.png",
            ),
            (
                "scene",
                "image_generation_requests.md",
                "image_generation_request_snapshot.json",
                "scene01_cut01",
                "assets/scenes/scene01_cut01.png",
            ),
        )
        for kind, request_filename, snapshot_filename, item_id, output_text in cases:
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    run_dir = root / "output" / f"{kind}_run"
                    run_dir.mkdir(parents=True)
                    prompt = f"{kind} cinematic prompt"
                    (run_dir / request_filename).write_text(
                        f"""# {kind.title()} Generation Requests

## {item_id}

- tool: `codex_builtin_image`
- prompt_policy_version: `image_api_prompt_v2`
- output: `{output_text}`
- references: `[]`

```api_prompt
{prompt}
```
""",
                        encoding="utf-8",
                    )
                    source_digest = hashlib.sha256(
                        f"{kind}-source".encode("utf-8")
                    ).hexdigest()
                    snapshot = materialize_request_snapshot(
                        run_dir,
                        kind=kind,
                        items=[
                            {
                                "item_id": item_id,
                                "destination": output_text,
                                "prompt": prompt,
                                "prompt_policy_version": "image_api_prompt_v2",
                                "compiler_version": "conditional_drawable_prompt_compiler_v1",
                                "source_digest": source_digest,
                                "references": [],
                            }
                        ],
                        source_artifact=request_filename,
                    )
                    write_request_snapshot_atomic(
                        run_dir / snapshot_filename,
                        snapshot,
                        run_dir=run_dir,
                    )
                    item = image_gen.load_request_items(run_dir, kind)[0]
                    output = run_dir / output_text
                    candidate = image_gen.candidate_path(run_dir, item_id, 1)
                    # Deliberately preserve the byte hash: a new canonical
                    # insertion must invalidate older provenance even when the
                    # selected candidate happens to be byte-identical.
                    output.parent.mkdir(parents=True)
                    output.write_bytes(PNG_BYTES)
                    candidate.parent.mkdir(parents=True)
                    candidate.write_bytes(PNG_BYTES)
                    result = ImageGenerationResult(
                        saved_path=output,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                        source="app_server",
                        generation_job_id=f"{kind}-job-old",
                        item_id=item_id,
                        turn_id=f"{kind}-turn-old",
                        prompt_sha256=hashlib.sha256(
                            prompt.encode("utf-8")
                        ).hexdigest(),
                        reference_sha256s=[],
                        image_generation_item_id=f"{kind}-image-old",
                        image_generation_item_count=1,
                        destination=str(output),
                        provenance_authoritative=True,
                        provenance_policy="request_bound_v2",
                    )
                    image_gen.write_app_server_image_debug_log(
                        run_dir=run_dir,
                        item_id=item_id,
                        index=1,
                        destination=output,
                        references=[],
                        prompt=prompt,
                        kind=kind,
                        prompt_policy_version="image_api_prompt_v2",
                        request_revision=item.request_revision,
                        request_digest=item.request_digest,
                        compiler_version=item.compiler_version,
                        source_digest=item.source_digest,
                        result=result,
                    )
                    (run_dir / "state.txt").write_text(
                        "\n".join(
                            (
                                "review.image_prompt.request_freeze.status=frozen",
                                f"review.image_prompt.request_freeze.request_revision={item.request_revision}",
                                "slot.p650.status=done",
                                "slot.p660.status=done",
                                "slot.p670.status=skipped",
                                "slot.p680.status=awaiting_approval",
                                "review.image.status=pending",
                                "image_generation.status=completed",
                            )
                        )
                        + "\n",
                        encoding="utf-8",
                    )

                    image_gen_app._validate_generated_outputs(run_dir, kind)
                    with patch.dict(
                        os.environ,
                        {"TOC_SERVER_AUTH_DISABLED": "1"},
                    ):
                        with patch("server.image_gen_app.ROOT", root):
                            with TestClient(app) as client:
                                response = client.post(
                                    "/api/image-gen/insert-bulk",
                                    json={
                                        "items": [
                                            {
                                                "run_id": run_dir.name,
                                                "candidate_path": candidate.relative_to(
                                                    run_dir
                                                ).as_posix(),
                                                "output": output_text,
                                            }
                                        ]
                                    },
                                )
                    state = image_gen_app.parse_state_file(
                        run_dir / "state.txt"
                    )

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response.json()["inserted"][0]["kind"],
                        kind,
                    )
                    self.assertEqual(
                        state["review.image_prompt.request_freeze.status"],
                        "draft",
                    )
                    self.assertEqual(state["status"], "P650")
                    self.assertEqual(
                        state["review.image_prompt.request_freeze.invalidated_by"],
                        "candidate_insertion",
                    )
                    self.assertEqual(state["slot.p650.status"], "pending")
                    self.assertEqual(state["slot.p660.status"], "pending")
                    self.assertEqual(state["slot.p670.status"], "pending")
                    self.assertEqual(state["slot.p680.status"], "pending")
                    self.assertEqual(
                        state["review.semantic.create_scene_media_generated"],
                        "false",
                    )
                    self.assertEqual(
                        state["image_generation.status"],
                        "not_started",
                    )
                    self.assertEqual(
                        state[f"image_generation.provenance.{kind}.{item_id}.status"],
                        "invalidated",
                    )
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "strict request-bound provenance",
                    ):
                        image_gen_app._validate_generated_outputs(run_dir, kind)
                    replacement_result = ImageGenerationResult(
                        saved_path=output,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                        source="app_server",
                        generation_job_id=f"{kind}-job-revalidated",
                        item_id=item_id,
                        turn_id=f"{kind}-turn-revalidated",
                        prompt_sha256=hashlib.sha256(
                            prompt.encode("utf-8")
                        ).hexdigest(),
                        reference_sha256s=[],
                        image_generation_item_id=f"{kind}-image-revalidated",
                        image_generation_item_count=1,
                        destination=str(output),
                        provenance_authoritative=True,
                        provenance_policy="request_bound_v2",
                    )
                    image_gen.write_app_server_image_debug_log(
                        run_dir=run_dir,
                        item_id=item_id,
                        index=2,
                        destination=output,
                        references=[],
                        prompt=prompt,
                        kind=kind,
                        prompt_policy_version="image_api_prompt_v2",
                        request_revision=item.request_revision,
                        request_digest=item.request_digest,
                        compiler_version=item.compiler_version,
                        source_digest=item.source_digest,
                        result=replacement_result,
                    )
                    image_gen_app._validate_generated_outputs(run_dir, kind)

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

    def test_request_bound_result_rejects_missing_provenance_policy(self) -> None:
        destination = Path("/tmp/request-bound-result.png")
        prompt_sha256 = hashlib.sha256(b"prompt").hexdigest()
        result = ImageGenerationResult(
            saved_path=destination,
            revised_prompt=None,
            status="completed",
            transcript=[],
            source="app_server",
            generation_job_id="job-1",
            item_id="scene1_cut1",
            turn_id="turn-1",
            prompt_sha256=prompt_sha256,
            reference_sha256s=[],
            image_generation_item_id="image-1",
            image_generation_item_count=1,
            destination=str(destination),
            provenance_authoritative=True,
            provenance_policy=None,
        )

        with self.assertRaisesRegex(RuntimeError, "provenance_policy"):
            image_gen_app._validate_request_bound_image_result(
                result,
                generation_job_id="job-1",
                item_id="scene1_cut1",
                destination=destination,
                prompt_sha256=prompt_sha256,
                reference_sha256s=[],
            )

    def test_global_serial_fallback_is_exclusive_with_request_bound_slots(self) -> None:
        async def run_case(lock_dir: Path) -> list[str]:
            entered: list[str] = []
            request_bound_ready = asyncio.Event()
            release_request_bound = asyncio.Event()
            serial_entered = asyncio.Event()
            release_serial = asyncio.Event()
            final_request_entered = asyncio.Event()

            async def request_bound(name: str, *, final: bool = False) -> None:
                async with image_gen_app._global_image_generation_slot("request_bound_v2"):
                    entered.append(name)
                    if final:
                        final_request_entered.set()
                        return
                    if len([item for item in entered if item.startswith("request-")]) == 2:
                        request_bound_ready.set()
                    await release_request_bound.wait()

            async def serial() -> None:
                async with image_gen_app._global_image_generation_slot("serial_fallback"):
                    entered.append("serial")
                    serial_entered.set()
                    await release_serial.wait()

            first = asyncio.create_task(request_bound("request-1"))
            second = asyncio.create_task(request_bound("request-2"))
            await asyncio.wait_for(request_bound_ready.wait(), timeout=2)
            serial_task = asyncio.create_task(serial())
            await asyncio.sleep(0.05)
            self.assertFalse(serial_entered.is_set())
            release_request_bound.set()
            await asyncio.wait_for(serial_entered.wait(), timeout=2)
            final_task = asyncio.create_task(request_bound("request-final", final=True))
            await asyncio.sleep(0.05)
            self.assertFalse(final_request_entered.is_set())
            release_serial.set()
            await asyncio.wait_for(final_request_entered.wait(), timeout=2)
            await asyncio.gather(first, second, serial_task, final_task)
            return entered

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("server.image_gen_app.IMAGE_GENERATION_GLOBAL_PARALLELISM", 2),
                patch("server.image_gen_app._image_generation_global_lock_dir", return_value=Path(tmp)),
            ):
                entered = asyncio.run(run_case(Path(tmp)))

        self.assertEqual(set(entered[:2]), {"request-1", "request-2"})
        self.assertEqual(entered[2:], ["serial", "request-final"])

    def test_request_generation_revision_lock_blocks_prompt_snapshot_replacement(self) -> None:
        async def run_case(run_dir: Path) -> None:
            generation_started = asyncio.Event()
            release_generation = asyncio.Event()
            prompt_edit_completed = asyncio.Event()

            async def fake_unlocked(*, run_dir: Path, kind: str) -> None:
                generation_started.set()
                await release_generation.wait()

            async def edit_prompt_snapshot() -> None:
                async with image_gen_app._serialized_run_write(run_dir, "scene_request_revision"):
                    prompt_edit_completed.set()

            with patch("server.image_gen_app._generate_request_outputs_unlocked", fake_unlocked):
                generation = asyncio.create_task(
                    image_gen_app._generate_request_outputs(run_dir=run_dir, kind="scene")
                )
                await asyncio.wait_for(generation_started.wait(), timeout=2)
                edit = asyncio.create_task(edit_prompt_snapshot())
                await asyncio.sleep(0.05)
                self.assertFalse(prompt_edit_completed.is_set())
                release_generation.set()
                await asyncio.gather(generation, edit)
                self.assertTrue(prompt_edit_completed.is_set())

        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(run_case(Path(tmp)))

    def test_p650_preflight_generation_and_review_handoff_share_revision_lock(self) -> None:
        async def run_case(run_dir: Path) -> list[str]:
            order: list[str] = []
            validation_completed = asyncio.Event()
            generation_started = asyncio.Event()
            release_generation = asyncio.Event()
            prompt_edit_entered = asyncio.Event()

            def fake_validate(run_id: str) -> None:
                self.assertEqual(run_id, "sample_run")
                order.append("validate")
                validation_completed.set()

            async def fake_set_create_job(job_id: str, updates: dict[str, Any]) -> None:
                self.assertEqual(job_id, "job-1")
                order.append("job_state")
                # Give the simulated prompt editor a chance to contend for the
                # revision lock immediately after the p650 validation.
                await asyncio.sleep(0.05)

            async def fake_generate_unlocked(*, run_dir: Path, kind: str) -> None:
                self.assertEqual(kind, "scene")
                order.append("provider_submission")
                generation_started.set()
                self.assertFalse(prompt_edit_entered.is_set())
                await release_generation.wait()

            def fake_mark_review_ready(run_id: str) -> None:
                self.assertEqual(run_id, "sample_run")
                self.assertFalse(prompt_edit_entered.is_set())
                order.append("review_handoff")

            async def edit_prompt_snapshot() -> None:
                await validation_completed.wait()
                async with image_gen_app._serialized_run_write(run_dir, "scene_request_revision"):
                    order.append("prompt_edit")
                    prompt_edit_entered.set()

            with (
                patch("server.image_gen_app._validate_p650_run", fake_validate),
                patch("server.image_gen_app._set_create_job", fake_set_create_job),
                patch("server.image_gen_app._generate_request_outputs_unlocked", fake_generate_unlocked),
                patch("server.image_gen_app._validate_generated_outputs", Mock()),
                patch("server.image_gen_app._validate_p680_visual_quality", Mock()),
                patch("server.image_gen_app._mark_image_generation_review_ready", fake_mark_review_ready),
            ):
                generation = asyncio.create_task(
                    image_gen_app._generate_scene_outputs_after_p650_preflight(
                        "job-1",
                        run_id="sample_run",
                        run_dir=run_dir,
                    )
                )
                editor = asyncio.create_task(edit_prompt_snapshot())
                await asyncio.wait_for(generation_started.wait(), timeout=2)
                self.assertFalse(prompt_edit_entered.is_set())
                release_generation.set()
                await asyncio.gather(generation, editor)
            return order

        with tempfile.TemporaryDirectory() as tmp:
            order = asyncio.run(run_case(Path(tmp)))

        self.assertEqual(
            order,
            ["validate", "job_state", "provider_submission", "validate", "review_handoff", "prompt_edit"],
        )

    def test_image_prompt_shard_passed_status_with_blocked_entries_fails_closed(self) -> None:
        async def fake_turn_until_completed(_client: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], bool]:
            report_path = Path(kwargs["report_path"])
            suffix = ".report.md"
            self.assertTrue(report_path.name.endswith(suffix))
            scope_path = report_path.with_name(
                report_path.name[: -len(suffix)] + ".scope.json"
            )
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            input_digest = str(scope["semantic_review_input_digest"])
            report_path.write_text(
                "\n".join(
                    [
                        "status: passed",
                        f"semantic_review_input_digest: {input_digest}",
                        "reviewed_entries: [scene01_cut01, scene01_composite]",
                        "blocked_entries: [scene01_cut01]",
                        "findings: [required drawable evidence is absent]",
                        "failed_selectors: [scene01_cut01]",
                        "reason_keys: [api_prompt_drawable_dependency_missing]",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            return [], False

        class FakeClient:
            async def start_thread(self, **_kwargs: Any) -> str:
                return "thread-1"

            async def stop(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            for source_name in ("story.md", "script.md", "video_manifest.md"):
                (run_dir / source_name).write_text(f"# {source_name}\n", encoding="utf-8")
            builder_path = Path(__file__).resolve().parents[1] / "scripts" / "build-semantic-review-pack.py"
            spec = importlib.util.spec_from_file_location(
                "build_semantic_review_pack_for_blocked_shard_test",
                builder_path,
            )
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader if spec is not None else None)
            assert spec is not None and spec.loader is not None
            builder = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(builder)
            entries = [
                {"selector": "scene01_cut01", "scene_id": "01", "review_scope": "all_entries"},
                {"selector": "scene01_composite", "scene_id": "01", "review_scope": "scene_composite"},
            ]
            with patch.object(builder, "collect_entries", return_value=entries):
                builder.build_pack(run_dir, "image_prompt")
            relpaths = image_gen_app.semantic_review_relpaths("image_prompt")
            canonical_scope = run_dir / relpaths["scope"]
            canonical_report = run_dir / relpaths["report"]
            canonical_scope_payload = json.loads(canonical_scope.read_text(encoding="utf-8"))
            shard = canonical_scope_payload["shards"][0]
            with (
                patch("server.image_gen_app.create_codex_app_server_client", return_value=FakeClient()),
                patch(
                    "server.image_gen_app._run_turn_until_semantic_artifact_completed",
                    fake_turn_until_completed,
                ),
            ):
                result = asyncio.run(
                    image_gen_app._run_image_prompt_scene_shard_review(
                        "job-1",
                        run_dir=run_dir,
                        shard_dir=run_dir / "shards",
                        shard=shard,
                        shard_index=1,
                        total_shards=1,
                        collection_sections={
                            "scene01_cut01": "## scene01_cut01\n",
                            "scene01_composite": "## scene01_composite\n",
                        },
                        canonical_scope_path=canonical_scope,
                        canonical_report_path=canonical_report,
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                        semaphore=asyncio.Semaphore(1),
                        transport_attempt=1,
                        transport_max_attempts=1,
                    )
                )

        self.assertEqual(result["status"], "transport_failed")
        self.assertEqual(result["blocked_entries"], ["scene01_cut01", "scene01_composite"])
        self.assertEqual(result["transport_error_kind"], "output_contract_failed")
        self.assertIn("image_prompt_shard_transport_failed", result["reason_keys"])

    def test_p680_generated_output_rejects_v2_snapshot_without_strict_provenance(self) -> None:
        request_text = """# Image Generation Requests

## scene01_cut01

- tool: `codex_builtin_image`
- prompt_policy_version: `image_api_prompt_v2`
- output: `assets/scenes/scene01_cut01.png`
- references: `[]`

```api_prompt
石造りの回廊に主人公が立っている。
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "image_generation_requests.md").write_text(request_text, encoding="utf-8")
            output = run_dir / "assets" / "scenes" / "scene01_cut01.png"
            output.parent.mkdir(parents=True)
            output.write_bytes(PNG_BYTES)
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    {
                        "item_id": "scene01_cut01",
                        "destination": "assets/scenes/scene01_cut01.png",
                        "prompt": "石造りの回廊に主人公が立っている。",
                        "prompt_policy_version": "image_api_prompt_v2",
                        "compiler_version": "conditional_drawable_prompt_compiler_v1",
                        "source_digest": hashlib.sha256(b"source").hexdigest(),
                        "references": [],
                    }
                ],
                source_artifact="image_generation_requests.md",
            )
            write_request_snapshot_atomic(
                run_dir / "image_generation_request_snapshot.json",
                snapshot,
                run_dir=run_dir,
            )

            with self.assertRaisesRegex(RuntimeError, "strict request-bound provenance"):
                image_gen_app._validate_generated_outputs(run_dir, "scene")

    def test_unchanged_item_reuses_output_after_other_item_changes_snapshot_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            destination = run_dir / "assets" / "scenes" / "scene_b.png"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(PNG_BYTES)
            prompt = "unchanged scene B prompt"
            prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            source_digest = hashlib.sha256(b"scene-b-source").hexdigest()
            request_digest = hashlib.sha256(b"scene-b-request").hexdigest()
            result = ImageGenerationResult(
                saved_path=destination,
                revised_prompt=None,
                status="completed",
                transcript=[],
                source="app_server",
                generation_job_id="job-old",
                item_id="scene_b",
                turn_id="turn-old",
                prompt_sha256=prompt_sha256,
                reference_sha256s=[],
                image_generation_item_id="image-old",
                image_generation_item_count=1,
                destination=str(destination),
                provenance_authoritative=True,
                provenance_policy="request_bound_v2",
            )
            image_gen.write_app_server_image_debug_log(
                run_dir=run_dir,
                item_id="scene_b",
                index=1,
                destination=destination,
                references=[],
                prompt=prompt,
                kind="scene",
                prompt_policy_version="image_api_prompt_v2",
                request_revision="old-global-revision",
                request_digest=request_digest,
                compiler_version="conditional_drawable_prompt_compiler_v1",
                source_digest=source_digest,
                result=result,
            )

            class FailingClient:
                def __init__(self, **_kwargs: Any) -> None:
                    raise AssertionError("unchanged item B must be reused")

            item = image_gen.ImageRequestItem(
                id="scene_b",
                kind="scene",
                asset_type=None,
                tool="codex_builtin_image",
                output="assets/scenes/scene_b.png",
                prompt=prompt,
                references=[],
                reference_count=0,
                execution_lane="bootstrap_builtin",
                generation_status=None,
                existing_image=None,
                prompt_policy_version="image_api_prompt_v2",
                prompt_sha256=prompt_sha256,
                reference_sha256s=[],
                request_revision="new-global-revision-after-scene-a-edit",
                request_digest=request_digest,
                compiler_version="conditional_drawable_prompt_compiler_v1",
                source_digest=source_digest,
            )
            with patch("server.image_gen_app.create_codex_app_server_client", FailingClient):
                asyncio.run(
                    image_gen_app._generate_request_item_output(
                        run_dir=run_dir,
                        kind="scene",
                        item=item,
                    )
                )
            destination_bytes = destination.read_bytes()

        self.assertEqual(destination_bytes, PNG_BYTES)

    def test_candidate_copy_failure_logs_failure_before_any_success_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            saved = root / "generated.png"
            saved.write_bytes(PNG_BYTES)

            class FakeClient:
                async def start(self) -> None:
                    return None

                async def stop(self) -> None:
                    return None

                async def generate_image(self, **kwargs: Any) -> ImageGenerationResult:
                    prompt_sha256 = hashlib.sha256(str(kwargs["prompt"]).encode("utf-8")).hexdigest()
                    return ImageGenerationResult(
                        saved_path=saved,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                        source="app_server",
                        generation_job_id=str(kwargs["generation_job_id"]),
                        item_id=str(kwargs["item_id"]),
                        turn_id="turn-1",
                        prompt_sha256=prompt_sha256,
                        reference_sha256s=[],
                        image_generation_item_id="image-1",
                        image_generation_item_count=1,
                        destination=str(kwargs["output_path"]),
                        provenance_authoritative=True,
                        provenance_policy="request_bound_v2",
                    )

            req = image_gen_app.GenerateRequest(
                run_id="sample_run",
                kind="scene",
                item_id="scene1_cut1",
                prompt="prompt",
                references=[],
                candidate_count=1,
            )
            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.create_codex_app_server_client", return_value=FakeClient()),
                patch("server.image_gen_app.copy_saved_image_to_new_candidate", side_effect=OSError("copy failed")),
                patch.dict(os.environ, {"TOC_IMAGE_GEN_PROVENANCE_POLICY": "request_bound_v2"}),
            ):
                with self.assertRaisesRegex(OSError, "copy failed"):
                    asyncio.run(image_gen_app._generate_one(run_dir, req, 1))

            retained = image_gen.load_first_image_retention(
                root=root,
                run_id="sample_run",
                kind="scene",
                item_id="scene1_cut1",
            )
            retained_bytes = Path(retained["imagePath"]).read_bytes() if retained else None

            image_logs = list((run_dir / "logs" / "app_server" / "image_gen").glob("*.json"))
            image_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in image_logs]
            event_lines = (run_dir / "logs" / "app_server" / "events.jsonl").read_text(encoding="utf-8")

        self.assertTrue(image_payloads)
        self.assertIsNotNone(retained)
        self.assertEqual(retained_bytes, PNG_BYTES)
        self.assertTrue(all(payload["status"] == "failed" for payload in image_payloads))
        self.assertIn("copy failed", event_lines)
        self.assertNotIn('"status": "completed"', event_lines)

    def test_pre_asset_semantic_fixed_point_returns_to_earliest_stale_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            passed = {"research", "story"}
            calls: list[str] = []
            scene_detail_calls = 0

            def is_current(_run_dir: Path, stage: str) -> bool:
                return stage in passed

            async def review(
                _job_id: str,
                *,
                run_dir: Path,
                stage: str,
            ) -> str | None:
                nonlocal scene_detail_calls
                calls.append(stage)
                passed.add(stage)
                if stage == "scene_detail":
                    scene_detail_calls += 1
                    if scene_detail_calls == 1:
                        passed.discard("scene_set")
                return None

            with (
                patch(
                    "server.image_gen_app._semantic_review_stage_is_current_passed",
                    side_effect=is_current,
                    create=True,
                ),
                patch(
                    "server.image_gen_app._run_semantic_review_for_media_generation",
                    side_effect=review,
                ),
            ):
                asyncio.run(
                    image_gen_app._run_pre_asset_semantic_fixed_point(
                        "job-1",
                        run_dir=run_dir,
                    )
                )

        self.assertEqual(
            calls,
            [
                "research",
                "story",
                "scene_set",
                "scene_detail",
                "scene_set",
                "cut_blueprint",
                "asset_plan",
            ],
        )

    def test_non_image_semantic_repair_reconciles_dependencies_in_safe_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            calls: list[str] = []
            for relpath in (
                "research.md",
                "story.md",
                "visual_value.md",
                "script.md",
                "video_manifest.md",
                "asset_inventory.md",
                "asset_plan.md",
            ):
                (run_dir / relpath).write_text(
                    f"# {relpath}\n",
                    encoding="utf-8",
                )

            class FakeFrontend:
                @staticmethod
                def _prepare_authoring_grounding(_run_dir: Path) -> None:
                    calls.append("authoring_grounding")

                @staticmethod
                def _refresh_p400_review_artifacts(_run_dir: Path) -> None:
                    calls.append("p400_reviews")

                @staticmethod
                def _require_fresh_p400_readiness(_run_dir: Path) -> None:
                    calls.append("p400_gate")

                @staticmethod
                def prepare_grounding(_run_dir: Path) -> None:
                    calls.append("downstream_grounding")

                @staticmethod
                def _refresh_downstream_review_artifacts(_run_dir: Path) -> None:
                    calls.append("downstream_reviews")

            def sync(_run_dir: Path) -> None:
                calls.append("request_sync")

            with (
                patch(
                    "server.image_gen_app._load_frontend_review_runner",
                    return_value=FakeFrontend,
                    create=True,
                ),
                patch(
                    "server.image_gen_app._synchronize_image_prompt_repair_outputs",
                    side_effect=sync,
                ),
            ):
                asyncio.run(
                    image_gen_app._reconcile_after_semantic_repair(
                        run_dir,
                        stage="scene_detail",
                        changed_artifacts=["script.md", "video_manifest.md"],
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(
            calls,
            [
                "authoring_grounding",
                "p400_reviews",
                "p400_gate",
                "request_sync",
                "authoring_grounding",
                "p400_reviews",
                "p400_gate",
                "downstream_grounding",
                "downstream_reviews",
                "p400_gate",
            ],
        )
        self.assertEqual(
            state["review.semantic.scene_detail.dependency_sync.status"],
            "done",
        )
        self.assertEqual(state["slot.p650.status"], "pending")
        self.assertEqual(state["slot.p680.status"], "pending")

    def test_image_prompt_manifest_repair_reaches_upstream_fixed_point_before_asset_refresh(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_valid_p650_artifacts(root, "sample_run")
            (run_dir / "asset_inventory.md").write_text(
                "# Asset Inventory\n\nhero\n",
                encoding="utf-8",
            )
            (run_dir / "asset_plan.md").write_text(
                "# Asset Plan\n\nhero\n",
                encoding="utf-8",
            )
            asset_items = image_gen.load_request_items(run_dir, "asset")
            asset_snapshot = materialize_request_snapshot(
                run_dir,
                kind="asset",
                items=[
                    {
                        "item_id": item.id,
                        "destination": item.output,
                        "prompt": item.prompt,
                        "prompt_policy_version": "asset_prompt_v1",
                        "compiler_version": "test_fixture_v1",
                        "source_digest": hashlib.sha256(
                            f"{item.id}:asset".encode()
                        ).hexdigest(),
                        "references": list(item.references),
                    }
                    for item in asset_items
                ],
                source_artifact="asset_generation_requests.md",
            )
            write_request_snapshot_atomic(
                run_dir / "asset_generation_request_snapshot.json",
                asset_snapshot,
                run_dir=run_dir,
            )
            for stage in ("scene_set", "scene_detail", "cut_blueprint"):
                bind_semantic_review_to_sources(
                    run_dir,
                    stage,
                    ["script.md", "video_manifest.md"],
                )
            bind_semantic_review_to_sources(
                run_dir,
                "asset_plan",
                [
                    "video_manifest.md",
                    "asset_generation_requests.md",
                    "asset_generation_request_snapshot.json",
                ],
            )
            write_review_input_snapshot(
                run_dir=run_dir,
                stage="scene_set",
                round_number=1,
                snapshot=build_review_input_snapshot(
                    run_dir=run_dir,
                    stage="scene_set",
                    round_number=1,
                ),
            )

            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8")
                + "\n# image prompt producer changed the canonical manifest\n",
                encoding="utf-8",
            )
            self.assertTrue(
                any(
                    "stale review source sha256" in issue
                    for issue in review_input_snapshot_issues(
                        run_dir=run_dir,
                        stage="scene_set",
                        round_number=1,
                    )
                )
            )
            for stage in (
                "scene_set",
                "scene_detail",
                "cut_blueprint",
                "asset_plan",
            ):
                self.assertFalse(
                    image_gen_app.check_semantic_review(run_dir, stage).passed
                )

            order: list[str] = []
            stale_semantic_stages: list[str] = []
            sync_count = 0

            class FakeFrontend:
                @staticmethod
                def _prepare_authoring_grounding(_run_dir: Path) -> None:
                    order.append("authoring_grounding")

                @staticmethod
                def _refresh_p400_review_artifacts(_run_dir: Path) -> None:
                    order.append("p400_refresh")
                    write_review_input_snapshot(
                        run_dir=run_dir,
                        stage="scene_set",
                        round_number=1,
                        snapshot=build_review_input_snapshot(
                            run_dir=run_dir,
                            stage="scene_set",
                            round_number=1,
                        ),
                    )

                @staticmethod
                def _require_fresh_p400_readiness(_run_dir: Path) -> None:
                    order.append("p400_gate")
                    self.assertFalse(
                        any(
                            "stale review source sha256" in issue
                            for issue in review_input_snapshot_issues(
                                run_dir=run_dir,
                                stage="scene_set",
                                round_number=1,
                            )
                        ),
                        review_input_snapshot_issues(
                            run_dir=run_dir,
                            stage="scene_set",
                            round_number=1,
                        ),
                    )

                @staticmethod
                def prepare_grounding(_run_dir: Path) -> None:
                    order.append("downstream_grounding")

                @staticmethod
                def _refresh_downstream_review_artifacts(
                    _run_dir: Path,
                ) -> None:
                    order.append("downstream_reviews")

            def synchronize(_run_dir: Path) -> None:
                nonlocal sync_count
                sync_count += 1
                order.append(f"sync_{sync_count}")
                image_gen_app.append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        "review.semantic.image_prompt.repair.asset_refresh_required": (
                            "true" if sync_count == 1 else "false"
                        )
                    },
                )

            async def review_stage(
                _job_id: str,
                *,
                run_dir: Path,
                stage: str,
            ) -> str | None:
                if not image_gen_app.check_semantic_review(
                    run_dir,
                    stage,
                ).passed:
                    stale_semantic_stages.append(stage)
                    refresh_existing_semantic_review_digest(run_dir, stage)
                return None

            def provider_gate(_run_dir: Path) -> None:
                order.append("provider_gate")
                self.assertFalse(
                    any(
                        "stale review source sha256" in issue
                        for issue in review_input_snapshot_issues(
                            run_dir=run_dir,
                            stage="scene_set",
                            round_number=1,
                        )
                    ),
                    review_input_snapshot_issues(
                        run_dir=run_dir,
                        stage="scene_set",
                        round_number=1,
                    ),
                )
                for stage in image_gen_app.PRE_ASSET_SEMANTIC_STAGES:
                    self.assertTrue(
                        image_gen_app.check_semantic_review(
                            run_dir,
                            stage,
                        ).passed,
                        stage,
                    )

            async def refresh_assets(_run_dir: Path) -> None:
                order.append("asset_provider")
                self.assertIn("provider_gate", order)
                image_gen_app.append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        "review.semantic.image_prompt.repair.asset_refresh_required": "false"
                    },
                )

            with (
                patch(
                    "server.image_gen_app._load_frontend_review_runner",
                    return_value=FakeFrontend,
                ),
                patch(
                    "server.image_gen_app._synchronize_image_prompt_repair_outputs",
                    side_effect=synchronize,
                ),
                patch(
                    "server.image_gen_app._run_semantic_review_for_media_generation",
                    side_effect=review_stage,
                ),
                patch(
                    "server.image_gen_app._validate_pre_asset_provider_gate",
                    side_effect=provider_gate,
                ),
                patch(
                    "server.image_gen_app._refresh_image_prompt_repair_assets_if_required",
                    side_effect=refresh_assets,
                ),
                patch(
                    "server.image_gen_app._prepare_image_prompt_request_revision_for_review",
                    return_value="review-revision",
                ),
            ):
                asyncio.run(
                    image_gen_app._reconcile_after_semantic_repair(
                        run_dir,
                        stage="image_prompt",
                        changed_artifacts=["video_manifest.md"],
                        job_id="job-1",
                    )
                )

        self.assertEqual(
            stale_semantic_stages,
            ["scene_set", "scene_detail", "cut_blueprint", "asset_plan"],
        )
        self.assertLess(order.index("provider_gate"), order.index("asset_provider"))
        self.assertLess(order.index("p400_refresh"), order.index("provider_gate"))

    def test_p560_prompt_repair_rereviews_real_asset_snapshot_before_next_provider_call(
        self,
    ) -> None:
        class StopAfterSecondAssetSubmission(RuntimeError):
            pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "sample_run"
            run_dir = write_valid_p650_artifacts(root, run_id)
            asset_items = image_gen.load_request_items(run_dir, "asset")
            asset_snapshot = materialize_request_snapshot(
                run_dir,
                kind="asset",
                items=[
                    {
                        "item_id": item.id,
                        "destination": item.output,
                        "prompt": item.prompt,
                        "prompt_policy_version": "asset_prompt_v1",
                        "compiler_version": "test_fixture_v1",
                        "source_digest": hashlib.sha256(
                            f"{item.id}:asset".encode()
                        ).hexdigest(),
                        "references": list(item.references),
                    }
                    for item in asset_items
                ],
                source_artifact="asset_generation_requests.md",
            )
            write_request_snapshot_atomic(
                run_dir / "asset_generation_request_snapshot.json",
                asset_snapshot,
                run_dir=run_dir,
            )
            bind_semantic_review_to_sources(
                run_dir,
                "asset_plan",
                [
                    "asset_generation_requests.md",
                    "asset_generation_request_snapshot.json",
                ],
            )
            self.assertTrue(
                image_gen_app.check_semantic_review(
                    run_dir,
                    "asset_plan",
                ).passed
            )

            provider_calls = 0
            provider_gate_calls = 0
            stale_asset_plan_reviews = 0

            async def generate_outputs(
                *,
                run_dir: Path,
                kind: str,
            ) -> None:
                nonlocal provider_calls
                if kind != "asset":
                    raise AssertionError("scene provider must not be reached")
                provider_calls += 1
                self.assertTrue(
                    image_gen_app.check_semantic_review(
                        run_dir,
                        "asset_plan",
                    ).passed,
                    "asset provider received a request with stale asset_plan evidence",
                )
                if provider_calls == 2:
                    raise StopAfterSecondAssetSubmission

            async def repair_prompts(
                _job_id: str,
                *,
                run_dir: Path,
                failure_detail: str,
                attempt: int,
            ) -> None:
                del failure_detail, attempt
                result = image_gen.update_request_prompts(
                    run_dir,
                    "asset",
                    {
                        "hero": (
                            "修正版の実写映画調の人物参照。自然な肌、布、髪、"
                            "立体的な映画照明を持つ。"
                        )
                    },
                    allow_inline_prompt=True,
                )
                self.assertEqual(result["updated"], ["hero"])
                self.assertFalse(
                    image_gen_app.check_semantic_review(
                        run_dir,
                        "asset_plan",
                    ).passed
                )

            async def review_stage(
                _job_id: str,
                *,
                run_dir: Path,
                stage: str,
            ) -> str | None:
                nonlocal stale_asset_plan_reviews
                if not image_gen_app.check_semantic_review(
                    run_dir,
                    stage,
                ).passed:
                    if stage == "asset_plan":
                        stale_asset_plan_reviews += 1
                    refresh_existing_semantic_review_digest(run_dir, stage)
                return None

            def provider_gate(_run_dir: Path) -> None:
                nonlocal provider_gate_calls
                provider_gate_calls += 1
                self.assertTrue(
                    image_gen_app.check_semantic_review(
                        run_dir,
                        "asset_plan",
                    ).passed
                )

            retryable_error = image_gen_app.P560AssetGateError(
                "p560 asset gate failed: bootstrap asset is vector-like",
                failed_check_ids=("asset.visual_not_vector_like",),
                retryable_visual_quality=True,
            )
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._generate_request_outputs",
                    side_effect=generate_outputs,
                ),
                patch(
                    "server.image_gen_app._run_semantic_review_for_media_generation",
                    side_effect=review_stage,
                ),
                patch(
                    "server.image_gen_app._validate_pre_asset_provider_gate",
                    side_effect=provider_gate,
                ),
                patch(
                    "server.image_gen_app._validate_p560_asset_quality",
                    side_effect=retryable_error,
                ),
                patch(
                    "server.image_gen_app._repair_bootstrap_asset_prompts",
                    side_effect=repair_prompts,
                ),
                patch(
                    "server.image_gen_app._remove_bootstrap_asset_outputs",
                ),
                patch(
                    "server.image_gen_app._set_create_job",
                    new=AsyncMock(),
                ),
            ):
                try:
                    asyncio.run(
                        image_gen_app._generate_create_images(
                            "job-1",
                            run_id=run_id,
                        )
                    )
                except StopAfterSecondAssetSubmission:
                    pass
                else:
                    state = image_gen_app.parse_state_file(
                        run_dir / "state.txt"
                    )
                    self.fail(
                        "second provider submission was not reached: "
                        f"provider_calls={provider_calls}, "
                        f"repair_error={state.get('review.asset_visual_gate.repair.error')}"
                    )

        self.assertEqual(provider_calls, 2)
        self.assertGreaterEqual(provider_gate_calls, 2)
        self.assertEqual(stale_asset_plan_reviews, 1)

    def test_pre_asset_provider_gate_blocks_asset_provider_submission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            generate_outputs = AsyncMock()

            with (
                patch("server.image_gen_app.safe_run_dir", return_value=run_dir),
                patch(
                    "server.image_gen_app._run_pre_asset_semantic_fixed_point",
                    new=AsyncMock(),
                    create=True,
                ),
                patch(
                    "server.image_gen_app._validate_pre_asset_provider_gate",
                    side_effect=RuntimeError("stale p400 review"),
                    create=True,
                ),
                patch(
                    "server.image_gen_app._generate_request_outputs",
                    new=generate_outputs,
                ),
                patch("server.image_gen_app._set_create_job", new=AsyncMock()),
            ):
                with self.assertRaisesRegex(RuntimeError, "stale p400"):
                    asyncio.run(
                        image_gen_app._generate_create_images(
                            "job-1",
                            run_id="sample_run",
                        )
                    )

        generate_outputs.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
