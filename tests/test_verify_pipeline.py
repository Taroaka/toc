import json
import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot

VERIFY_SCRIPT_PATH = REPO_ROOT / "scripts" / "verify-pipeline.py"
SPEC = importlib.util.spec_from_file_location("verify_pipeline", VERIFY_SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFY_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY_MODULE)


ORCHESTRATION_BUCKET_TERMINAL_SLOTS = {
    "p100": "p130",
    "p200": "p230",
    "p300": "p330",
    "p400": "p450",
    "p500": "p570",
    "p600": "p680",
    "p700": "p750",
    "p800": "p850",
    "p900": "p930",
}

ORCHESTRATION_REQUIRED_ARTIFACT_FIXTURES: dict[str, dict[str, str | bytes]] = {
    "p100": {"research.md": "# Research\n\n```yaml\ntopic: \"fixture\"\n```\n"},
    "p200": {"story.md": "# Story\n\n```yaml\nscript:\n  scenes: []\n```\n"},
    "p300": {"visual_value.md": "# Visual Value\n\n```yaml\nscene_visual_values: []\n```\n"},
    "p400": {
        "script.md": "# Script\n\nfixture\n",
        "video_manifest.md": "```yaml\nvideo_metadata:\n  topic: \"fixture\"\nscenes: []\n```\n",
    },
    "p500": {
        "asset_inventory.md": "```yaml\nasset_inventory:\n  items: []\n```\n",
        "asset_plan.md": "```yaml\nassets:\n  characters: []\n```\n",
    },
    "p600": {"image_generation_requests.md": "# Image Generation Requests\n\nfixture\n"},
    "p700": {"narration_text_review.md": "# Narration Text Review\n\nfixture\n"},
    "p800": {"video_manifest.md": "```yaml\nvideo_metadata:\n  topic: \"fixture\"\nscenes: []\n```\n"},
    "p900": {"video.mp4": b"placeholder"},
}


def _ensure_fixture_artifact(path: Path, value: str | bytes) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value, encoding="utf-8")


def _orchestration_bucket_terminal_slot(bucket: str, target: str) -> str:
    bucket_number = int(bucket.removeprefix("p"))
    target_number = int(target.removeprefix("p"))
    if bucket_number <= target_number <= bucket_number + 99:
        return target
    return ORCHESTRATION_BUCKET_TERMINAL_SLOTS[bucket]


def _write_photo_like_test_png(path: Path, *, width: int = 320, height: int = 180) -> None:
    import math

    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height))
    pixels = [
        (
            max(0, min(255, int(80 + 50 * math.sin(x / 13) + 30 * math.sin((x + y) / 21) + y * 0.4) + ((x * 17 + y * 31) % 23) - 11)),
            max(0, min(255, int(90 + 40 * math.sin(y / 9) + 20 * math.cos(x / 17) + x * 0.1) + ((x * 17 + y * 31) % 23) - 11)),
            max(0, min(255, int(100 + 50 * math.cos((x - y) / 19) + 30 * (1 - y / height)) + ((x * 17 + y * 31) % 23) - 11)),
        )
        for y in range(height)
        for x in range(width)
    ]
    image.putdata(pixels)
    draw = ImageDraw.Draw(image, "RGBA")
    for index in range(20):
        x = (index * 37) % width
        y = (index * 23) % height
        draw.rectangle(
            (x, y, min(width, x + 30 + (index % 5) * 8), min(height, y + 20 + (index % 7) * 5)),
            fill=(80 + index * 5, 60 + index * 3, 50 + index * 2, 90),
        )
    for index in range(8):
        x = (index * 53) % width
        y = (index * 31) % height
        draw.ellipse((x, y, min(width, x + 25), min(height, y + 40)), fill=(180, 160, 130, 120))
    image.save(path)


def _append_app_server_image_provenance(run_dir: Path, destination: str, *, item_id: str = "item", source: str = "app_server") -> None:
    log_dir = run_dir / "logs" / "app_server" / "image_gen"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{item_id}.json"
    payload = {
        "itemId": item_id,
        "candidateIndex": 1,
        "kind": "test",
        "destination": destination,
        "references": [],
        "prompt": "実写映画風。画面内テキストなし。",
        "promptLength": 16,
        "promptSha256": "test",
        "status": "completed",
        "savedPath": f"/tmp/{Path(destination).name}",
        "source": source,
        "revisedPrompt": None,
        "error": None,
        "transcript": [],
        "debugLog": log_path.relative_to(run_dir).as_posix(),
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    index_path = run_dir / "logs" / "image_generation_prompts.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a", encoding="utf-8") as index_file:
        index_file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_vector_like_test_png(path: Path, *, width: int = 768, height: int = 384) -> None:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), (236, 231, 222))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, height * 2 // 3, width, height), fill=(96, 80, 68))
    draw.ellipse((width // 3, height // 8, width * 2 // 3, height * 5 // 6), fill=(64, 88, 104))
    draw.rectangle((width * 7 // 16, height // 2, width * 9 // 16, height * 5 // 6), fill=(220, 220, 214))
    image.save(path)


def _write_noise_masked_vector_like_test_png(path: Path, *, width: int = 1280, height: int = 720) -> None:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), (54, 48, 42))
    pixels = []
    for y in range(height):
        for x in range(width):
            noise = ((x * 37 + y * 53) % 85) - 42
            pixels.append(
                (
                    max(0, min(255, 54 + noise)),
                    max(0, min(255, 48 + noise)),
                    max(0, min(255, 42 + noise)),
                )
            )
    image.putdata(pixels)
    draw = ImageDraw.Draw(image, "RGBA")
    for x in range(-200, width + 200, 320):
        draw.line((x, height, x + 480, 0), fill=(190, 186, 170, 95), width=8)
    for y in range(80, height, 95):
        draw.line((0, y, width, y), fill=(160, 150, 132, 70), width=2)
    draw.ellipse((width // 3, height // 4, width // 3 + 70, height // 4 + 70), fill=(190, 187, 172, 230))
    draw.rectangle((width // 3 - 30, height // 4 + 65, width // 3 + 100, height // 2 + 140), fill=(170, 168, 150, 220))
    draw.line((width // 3 - 25, height // 2, width // 3 - 90, height // 2 + 90), fill=(210, 205, 190, 240), width=10)
    draw.line((width // 3 + 95, height // 2, width // 3 + 160, height // 2 + 90), fill=(210, 205, 190, 240), width=10)
    draw.line((width // 3 + 5, height // 2 + 140, width // 3 - 25, height // 2 + 230), fill=(28, 26, 24, 230), width=10)
    draw.line((width // 3 + 70, height // 2 + 140, width // 3 + 110, height // 2 + 230), fill=(28, 26, 24, 230), width=10)
    image.save(path)


def _write_detailed_cel_vector_like_test_png(path: Path, *, width: int = 1280, height: int = 720) -> None:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), (96, 125, 150))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        draw.line((0, y, width, y), fill=(80 + y // 12, 110 + y // 18, 145 + y // 20))
    draw.rectangle((0, height * 2 // 3, width, height), fill=(70, 95, 80))
    draw.polygon([(420, 170), (550, 120), (690, 190), (650, 430), (455, 430)], fill=(210, 195, 160), outline=(25, 25, 25))
    draw.ellipse((490, 80, 610, 205), fill=(235, 190, 160), outline=(20, 20, 20), width=5)
    draw.rectangle((450, 420, 510, 610), fill=(70, 55, 45), outline=(20, 20, 20), width=5)
    draw.rectangle((600, 420, 665, 610), fill=(70, 55, 45), outline=(20, 20, 20), width=5)
    draw.polygon([(210, 310), (330, 230), (430, 330), (350, 390)], fill=(180, 170, 120), outline=(30, 30, 30))
    image.save(path)


def _good_story_yaml(topic: str = "桃太郎", scene_count: int = 20) -> str:
    scene_lines: list[str] = []
    for i in range(1, scene_count + 1):
        scene_lines.extend(
            [
                f"    - scene_id: {i}",
                "      phase: \"development\"",
                f"      purpose: \"Scene {i} の物語上の役割を明確にする\"",
                f"      conflict: \"Scene {i} の内的または外的な葛藤\"",
                f"      turn: \"Scene {i} で状況や認識が変わる\"",
                "      affect:",
                "        label_hint: \"curiosity\"",
                "        audience_job: \"hook\"",
                f"      visualizable_action: \"Scene {i} で画面化できる人物行動と状態変化\"",
                f"      grounding_note: \"Scene {i} の骨格は research refs に基づき、心理描写は演出補完として扱う\"",
                f"      narration: \"{topic} の scene {i} を語る\"",
                f"      visual: \"Scene {i} の視覚要素\"",
                f"      research_refs: [\"research.story_baseline.beat_sheet[{i - 1}]\"]",
            ]
        )
    return "\n".join(
        [
            "```yaml",
            "selection:",
            "  candidates:",
            "    - candidate_id: \"A\"",
            f"      logline: \"{topic} の王道案\"",
            "      why_it_scores: [\"clear\"]",
            "      requires_hybridization_approval: false",
            "    - candidate_id: \"B\"",
            f"      logline: \"{topic} の別視点案\"",
            "      why_it_scores: [\"fresh\"]",
            "      requires_hybridization_approval: false",
            "  chosen_candidate_id: \"A\"",
            f"  rationale: \"{scene_count} scene の展開に最も安定して接続できる\"",
            "hybridization:",
            "  approval_status: \"not_needed\"",
            "script:",
            "  scenes:",
            *scene_lines,
            "```",
            "",
        ]
    )


def _good_research_yaml(topic: str = "桃太郎") -> str:
    return "\n".join(
        [
            "```yaml",
            f"topic: \"{topic}\"",
            "story_baseline:",
            "  canonical_synopsis:",
            f"    one_liner: \"{topic} の旅\"",
            f"    short_summary: \"{topic} が選択と葛藤を通じて変化する。\"",
            "    beat_sheet:",
            *[
                f"      - beat: \"Beat {i}\"\n        scene_ids: [{i}]\n        confidence: 0.9\n        sources: [\"S1\"]"
                for i in range(1, 21)
            ],
            "sources:",
            *[
                f"  - source_id: \"S{i}\"\n    title: \"Source {i}\"\n    url: \"https://example.com/{i}\"\n    type: \"primary\"\n    reliability: \"high\"\n    accessed_at: \"2099-01-01T00:00:00+09:00\"\n    notes: \"\""
                for i in range(1, 13)
            ],
            "conflicts:",
            "  - conflict_id: \"C1\"",
            f"    topic: \"採用する{topic}像\"",
            "    accounts:",
            "      - account_id: \"A\"",
            "        claim: \"英雄譚として扱う\"",
            "        sources: [\"S1\"]",
            "        confidence: 0.9",
            "      - account_id: \"B\"",
            "        claim: \"教訓譚として扱う\"",
            "        sources: [\"S2\"]",
            "        confidence: 0.8",
            "    impact_on_story: \"p200 の候補比較に使う\"",
            "    selection_notes:",
            "      recommended_choice: \"both_separated\"",
            "      rationale: \"候補比較で分けて扱える\"",
            "source_passages:",
            "  - passage_id: \"P1\"",
            "    source_id: \"S1\"",
            "    passage: \"Passage 1\"",
            "    evidence_note: \"Evidence 1\"",
            "    confidence: 0.9",
            "facts:",
            "  items:",
            *[
                f"    - fact_id: \"F{i}\"\n      claim: \"Fact {i}\"\n      kind: \"plot\"\n      confidence: 0.9\n      verification: \"verified\"\n      sources: [\"S1\"]\n      notes: \"\""
                for i in range(1, 11)
            ],
            "handoff_to_story:",
            f"  recommended_focus: [\"{topic} の選択\"]",
            "  must_preserve: [\"出典に基づく出来事\"]",
            "  avoid_overstating: [\"未検証の起源\"]",
            "  selection_questions_for_p200: [\"どの葛藤を中心にするか\"]",
            "metadata:",
            "  confidence_score: 0.9",
            "```",
            "",
        ]
    )


def _good_visual_value_yaml(topic: str = "桃太郎", scene_count: int = 20) -> str:
    scene_values: list[str] = []
    for i in range(1, scene_count + 1):
        scene_values.extend(
            [
                f"  - scene_selector: \"scene{i:02d}\"",
                f"    story_function: \"Scene {i} の役割\"",
                f"    visual_value: \"Scene {i} で観客に理解させる画の価値\"",
                f"    must_show: [\"Scene {i} の主要視覚要素\"]",
                "    must_avoid: [\"画面内テキスト\"]",
                f"    emotional_payload: \"Scene {i} の感情到達点\"",
                f"    continuity_hooks: [\"Scene {i} の継続要素\"]",
                f"    p400_script_notes: [\"Scene {i} の視覚価値を台本へ残す\"]",
            ]
        )
    return "\n".join(
        [
            "```yaml",
            "visual_value_metadata:",
            f"  topic: \"{topic}\"",
            "  purpose: \"p300 visual planning source of truth\"",
            "global_visual_identity:",
            "  visual_style: \"実写的で一貫した画作り\"",
            "  camera_principles: [\"物語価値が読める構図を優先する\"]",
            "  forbidden: [\"text overlay\", \"watermark\", \"logo\", \"subtitles\"]",
            "scene_visual_values:",
            *scene_values,
            "anchor_cut_candidates:",
            "  - selector: \"scene01_cut01\"",
            "    proposed_still_mode: \"generate_still\"",
            "    anchor_role: \"character_anchor\"",
            "    why_anchor_needed: \"人物同一性を固定するため\"",
            "    reuse_targets: [\"scene02_cut01\"]",
            "asset_bible_candidates:",
            "  characters:",
            "    - asset_id: \"protagonist\"",
            "      story_purpose: \"主人公\"",
            "      fixed_identity: [\"年齢感と衣装\"]",
            "      candidate_reference_views: [\"front\"]",
            "      used_by_selectors: [\"scene01_cut01\"]",
            "      p500_handoff: \"人物 bible で固定する\"",
            "reference_strategy:",
            "  required_reference_assets:",
            "    - asset_id: \"protagonist\"",
            "      reference_type: \"character_reference\"",
            "      required_before_stage: \"p500\"",
            "      reason: \"人物同一性を固定するため\"",
            "regeneration_risks:",
            "  - risk_id: \"risk_01\"",
            "    affected_selectors: [\"scene01_cut01\"]",
            "    failure_mode: \"人物の見た目がぶれる\"",
            "    prevention_rule: \"参照を固定する\"",
            "    owner_stage: \"p500\"",
            "handoff_to_p400_p500_p600_p700:",
            "  p400_script:",
            "    must_preserve: [\"視覚価値\"]",
            "    must_not_do: [\"未承認の新規主筋を追加しない\"]",
            "  p500_asset:",
            "    must_create_or_review: [\"protagonist\"]",
            "    review_focus: [\"同一性\"]",
            "  p600_scene_implementation:",
            "    must_materialize: [\"anchor_cut_candidates\"]",
            "    review_focus: [\"p300 の意図と矛盾しない\"]",
            "  p700_narration:",
            "    must_preserve: [\"視覚と矛盾しない語り\"]",
            "    review_focus: [\"説明しすぎない\"]",
            "```",
            "",
        ]
    )


def _run_grounding(run_dir: Path, stage: str, *, flow: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "resolve-stage-grounding.py"),
            "--stage",
            stage,
            "--run-dir",
            str(run_dir),
            "--flow",
            flow,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _write_l2_orchestration_artifacts(run_dir: Path, *, stage_target: str = "p930") -> None:
    target = VERIFY_MODULE.normalize_stage_target(stage_target)
    buckets = VERIFY_MODULE._required_orchestration_buckets(target)
    orchestration_dir = run_dir / "logs" / "orchestration"
    orchestration_dir.mkdir(parents=True, exist_ok=True)
    state_updates = {
        "artifact.l2_supervisor_progress": "logs/orchestration/l2_supervisor_progress.md",
    }
    lines = [
        "# L2 Supervisor Progress",
        "",
        "Only L2 P-Bucket Supervisor invocations are recorded here. L3 task/review agents are intentionally omitted.",
        "",
        "| at | bucket | supervisor | event | stop_slot | result | note |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for bucket in buckets:
        result_path = f"logs/orchestration/{bucket}.supervisor_result.json"
        terminal_slot = _orchestration_bucket_terminal_slot(bucket, target)
        required_artifacts = []
        for artifact_path, fixture_value in ORCHESTRATION_REQUIRED_ARTIFACT_FIXTURES[bucket].items():
            _ensure_fixture_artifact(run_dir / artifact_path, fixture_value)
            required_artifacts.append({"path": artifact_path, "exists": True, "status": "ready"})
        state_updates[f"orchestration.{bucket}.supervisor.progress"] = "logs/orchestration/l2_supervisor_progress.md"
        state_updates[f"orchestration.{bucket}.supervisor.call_status"] = "returned"
        state_updates[f"orchestration.{bucket}.supervisor.status"] = "done"
        state_updates[f"orchestration.{bucket}.supervisor.invoked_at"] = "2099-01-01T00:00:00+09:00"
        state_updates[f"orchestration.{bucket}.supervisor.last_event_at"] = "2099-01-01T00:00:01+09:00"
        state_updates[f"orchestration.{bucket}.supervisor.finished_at"] = "2099-01-01T00:00:01+09:00"
        state_updates[f"orchestration.{bucket}.supervisor.stop_slot"] = target
        state_updates[f"orchestration.{bucket}.supervisor.result"] = result_path
        state_updates[f"slot.{terminal_slot}.status"] = "done"
        lines.append(f"| 2099-01-01T00:00:00+09:00 | {bucket} | {bucket} P-Bucket Supervisor | invoked | {target} | - | test fixture |")
        lines.append(f"| 2099-01-01T00:00:01+09:00 | {bucket} | {bucket} P-Bucket Supervisor | returned | {target} | {result_path} | test fixture |")
        result_state_keys = {
            f"orchestration.{bucket}.supervisor.call_status": "returned",
            f"orchestration.{bucket}.supervisor.status": "done",
            f"orchestration.{bucket}.supervisor.result": result_path,
            f"slot.{terminal_slot}.status": "done",
        }
        (orchestration_dir / f"{bucket}.supervisor_result.json").write_text(
            json.dumps(
                {
                    "bucket": bucket,
                    "status": "done",
                    "completed_slots": [terminal_slot],
                    "required_artifacts": required_artifacts,
                    "state_keys": result_state_keys,
                    "review_outputs": [],
                    "next_bucket": None,
                    "blocked_reason": None,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    (orchestration_dir / "l2_supervisor_progress.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    append_state_snapshot(run_dir / "state.txt", state_updates)


def _resolve_ready_grounding(run_dir: Path, *, flow: str) -> None:
    _write_l2_orchestration_artifacts(run_dir)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.story.status": "approved",
            "review.image.status": "approved",
            "review.narration.status": "approved",
            "review.duration_fit.status": "passed",
            "eval.p400_readiness.status": "approved",
        },
    )
    for stage in ["research", "story", "script", "manifest", "asset", "scene_implementation", "narration", "video_generation"]:
        result = _run_grounding(run_dir, stage, flow=flow)
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)


def _resolve_ready_p300_grounding(run_dir: Path, *, flow: str) -> None:
    _write_l2_orchestration_artifacts(run_dir, stage_target="p330")
    for stage in ["research", "story", "visual_value"]:
        result = _run_grounding(run_dir, stage, flow=flow)
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)


def _write_ready_grounding_artifacts(run_dir: Path, stage: str = "asset") -> None:
    grounding_dir = run_dir / "logs" / "grounding"
    grounding_dir.mkdir(parents=True, exist_ok=True)
    (grounding_dir / f"{stage}.json").write_text(json.dumps({"status": "ready"}), encoding="utf-8")
    (grounding_dir / f"{stage}.readset.json").write_text(json.dumps({"verified_before_edit": True}), encoding="utf-8")
    (grounding_dir / f"{stage}.audit.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
    append_state_snapshot(
        run_dir / "state.txt",
        {
            f"stage.{stage}.grounding.status": "ready",
            f"stage.{stage}.grounding.report": f"logs/grounding/{stage}.json",
            f"stage.{stage}.readset.report": f"logs/grounding/{stage}.readset.json",
            f"stage.{stage}.audit.status": "passed",
            f"stage.{stage}.audit.report": f"logs/grounding/{stage}.audit.json",
        },
    )


def _good_asset_inventory_yaml() -> str:
    return """```yaml
asset_inventory:
  source_artifacts: ["story.md", "script.md", "video_manifest.md"]
  coverage_scope:
    characters: ["桃太郎"]
    story_specific_items: ["きびだんご"]
    locations: ["村道"]
    setpieces: ["鬼ヶ島"]
    reusable_stills: []
  items:
    - item_id: "momotaro_seed"
      category: "character"
      source_script_selectors: ["scene10_cut1"]
      story_purpose: "主人公の基準参照"
      reusable_reason: "主人公の visual identity を固定する"
      recommended_asset_type: "character_reference"
```
"""


def _good_asset_plan_yaml() -> str:
    return """```yaml
asset_plan_metadata:
  topic: "桃太郎"
  source_story: "story.md"
  source_script: "script.md"
  created_at: "2099-01-01T00:00:00+09:00"
  purpose: "reusable asset design before cut image generation"
review_contract:
  must_cover:
    - "登場人物、物語固有のアイテム、使われる場所を網羅する"
  must_avoid:
    - "production metadata in p550 prompt"
  done_when:
    - "human review approved"
assets:
  characters:
    - asset_id: "momotaro_seed"
      asset_type: "character_reference"
      source_script_selectors: ["scene10_cut1"]
      story_purpose: "主人公の基準参照"
      visual_spec:
        identity: ["少年、旅装束、赤い鉢巻"]
        fixed_details: ["全身が見える", "素朴な着物"]
        must_avoid: ["現代服"]
      generation_plan:
        output_dir: "assets/characters"
        output: "assets/characters/momotaro_seed.png"
        required_views: ["front", "side", "back"]
        view_requirements: "full-body front/side/back three-view reference"
        execution_lane: "bootstrap_builtin"
        bootstrap_allowed: true
        bootstrap_reason: "no_reference_seed"
        reference_inputs: []
        derived_from_asset_id: ""
      creation_status: "created"
      existing_outputs: ["assets/characters/momotaro_seed.png"]
      review:
        status: "approved"
        notes: "approved for p600 continuity"
  objects: []
  locations: []
  reusable_stills: []
```
"""


def _write_downstream_generation_artifacts(run_dir: Path) -> None:
    (run_dir / "asset_inventory.md").write_text(_good_asset_inventory_yaml(), encoding="utf-8")
    (run_dir / "asset_plan.md").write_text(_good_asset_plan_yaml(), encoding="utf-8")
    (run_dir / "asset_generation_requests.md").write_text(
        """# Asset Generation Requests

## momotaro_seed

- tool: `codex_builtin_image`
- asset_id: `momotaro_seed`
- asset_type: `character_reference`
- execution_lane: `bootstrap_builtin`
- reference_count: `0`
- review_status: `approved`
- creation_status: `created`
- source_script_selectors:
  - `scene10_cut1`
- required_views:
  - `front`
  - `side`
  - `back`
- output: `assets/characters/momotaro_seed.png`
- references: `[]`

```text
桃太郎の全身キャラクター参照。正面、側面、背面の3面図。赤い鉢巻、素朴な旅装束、同じ体格と顔立ちを保つ。
```
""",
        encoding="utf-8",
    )
    (run_dir / "image_generation_requests.md").write_text("# Image Generation Requests\n\nrequest body\n", encoding="utf-8")
    (run_dir / "narration_text_review.md").write_text("# Narration Text Review\n\napproved\n", encoding="utf-8")
    (run_dir / "asset_generation_manifest.md").write_text(
        """```yaml
asset_generation_manifest:
  items:
    - asset_id: "momotaro_seed"
      asset_type: "character_reference"
      status: "created"
      output: "assets/characters/momotaro_seed.png"
      execution_lane: "bootstrap_builtin"
      reference_count: 0
```
""",
        encoding="utf-8",
    )
    (run_dir / "assets" / "characters").mkdir(parents=True, exist_ok=True)
    _write_photo_like_test_png(run_dir / "assets" / "characters" / "momotaro_seed.png")
    _append_app_server_image_provenance(run_dir, "assets/characters/momotaro_seed.png", item_id="momotaro_seed")
    (run_dir / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "audio").mkdir(parents=True, exist_ok=True)


def _write_image_request(run_dir: Path, *, selector: str, output: str, reference: str = "assets/characters/momotaro_seed.png") -> None:
    (run_dir / "image_generation_requests.md").write_text(
        f"""# Image Generation Requests

## {selector}

- tool: `codex_builtin_image`
- selector: `{selector}`
- execution_lane: `standard`
- reference_count: `1`
- output: `{output}`
- references:
  - `momotaro_seed`: `{reference}`

```text
実写映画風。人物、場所、光、衣装、背景を具体的に見せる。画面内テキストなし。
```
""",
        encoding="utf-8",
    )


def _write_image_requests_from_manifest(run_dir: Path, *, reference: str = "assets/characters/momotaro_seed.png") -> None:
    manifest_text = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
    outputs = re.findall(r'output:\s*"?(assets/scenes/[^"\n]+?\.png)"?\s*$', manifest_text, flags=re.MULTILINE)
    sections = ["# Image Generation Requests", ""]
    for index, output in enumerate(outputs, start=1):
        selector = Path(output).stem
        _append_app_server_image_provenance(run_dir, output, item_id=selector)
        sections.extend(
            [
                f"## {selector}",
                "",
                "- tool: `codex_builtin_image`",
                f"- selector: `{selector}`",
                "- execution_lane: `standard`",
                "- reference_count: `1`",
                f"- output: `{output}`",
                "- references:",
                f"  - `momotaro_seed`: `{reference}`",
                "",
                "```text",
                f"実写映画風。{selector} の人物、場所、光、衣装、背景を具体的に見せる。画面内テキストなし。",
                "```",
                "",
            ]
        )
    (run_dir / "image_generation_requests.md").write_text("\n".join(sections), encoding="utf-8")


def _write_p400_review_artifacts(run_dir: Path) -> None:
    reports = {
        "scene_set_review.md": "status: passed\n\nscene set approved.\n",
        "scene_detail_review.md": "status: passed\n\nscene detail approved.\n",
        "cut_blueprint_review.md": "status: passed\n\ncut blueprint approved.\n",
        "script_review.md": "status: passed\n\nscript approved.\n",
        "production_readiness_review.md": "\n".join(
            [
                "status: passed",
                "",
                "Structure: approved.",
                "Duration: target duration is covered by production cut durations.",
                "Quality: approved.",
                "## Design Owner Patch Brief",
                "",
                "No changes.",
            ]
        )
        + "\n",
    }
    for name, text in reports.items():
        (run_dir / name).write_text(text, encoding="utf-8")
    for stage in ("scene_set", "scene_detail", "cut_blueprint", "script", "production_readiness"):
        round_dir = run_dir / "logs" / "eval" / stage / "round_01"
        round_dir.mkdir(parents=True, exist_ok=True)
        for idx in range(1, 6):
            (round_dir / f"critic_{idx}.md").write_text("- status: passed\n", encoding="utf-8")
        heading = "Design Owner Patch Brief" if stage == "production_readiness" else "Generator Patch Brief"
        (round_dir / "aggregated_review.md").write_text(
            f"- status: passed\n\n## Blocking Findings\n\n[]\n\n## Recommended Changes\n\n[]\n\n## Rejected Suggestions\n\n[]\n\n## {heading}\n\nNo changes.\n\n## Round Summary\n\npassed\n",
            encoding="utf-8",
        )


def _write_verify_ready_p400_pair(run_dir: Path, *, topic: str = "桃太郎", silent: bool = False) -> None:
    scene_count = 10
    cut_duration = 15
    script_lines = [
        "```yaml",
        "evaluation_contract:",
        "  target_arc: \"opening\"",
        f"  must_cover: [\"{topic}\"]",
        "  must_avoid: []",
        "scene_set_review: {status: \"approved\"}",
        "scene_detail_review: {status: \"approved\"}",
        "cut_blueprint_review: {status: \"approved\"}",
        "script:",
        "  scenes:",
    ]
    manifest_lines = [
        "```yaml",
        "manifest_phase: production",
        "video_metadata:",
        f"  topic: \"{topic}\"",
        "  experience: \"cinematic_story\"",
        "  target_duration_seconds: 300",
        "scenes:",
    ]
    for scene_idx in range(1, scene_count + 1):
        terminal = scene_idx == scene_count
        script_lines.extend(
            [
                f"    - scene_id: {scene_idx}",
                "      phase: \"opening\"",
                "      importance: \"medium\"",
                f"      summary: \"{topic}が進む。十分な長さの本文です。十分な長さの本文です。\"",
                "      target_duration_seconds: 30",
                "      estimated_duration_seconds: 30",
                ("      terminal_resolution: \"物語が締まる\"" if terminal else "      handoff_to_next_scene: \"次の場面へつながる\""),
                "      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, next_scene_connection_checked: true}",
                "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                "      scene_intent:",
                "        story_purpose: \"進行\"",
                f"        audience_information: [\"{topic}\"]",
                "        withheld_information: []",
                "        reveal_constraints: []",
                "        affect_transition: \"前進\"",
                "        visual_value_source: \"none\"",
                "        production_risks: []",
                "        handoff_notes: {p500_asset: [], p600_image: [], p700_narration: [], p800_video: []}",
                "      agent_review: {status: \"passed\"}",
                "      cuts:",
            ]
        )
        manifest_lines.extend([f"  - scene_id: {scene_idx}", "    cuts:"])
        for cut_idx in range(1, 4):
            selector = f"scene{scene_idx}_cut{cut_idx}"
            image_output = f"assets/scenes/{selector}.png"
            audio_output = f"assets/audio/{selector}.mp3"
            script_lines.extend(
                [
                    f"        - cut_id: {cut_idx}",
                    f"          selector: \"{selector}\"",
                    "          cut_blueprint:",
                    "            cut_role: \"main\"",
                    "            duration_intent: \"standard\"",
                    f"            target_beat: \"{topic}\"",
                    f"            must_show: [\"{topic}\"]",
                    "            must_avoid: []",
                    f"            done_when: [\"{topic}が見える\"]",
                    f"            visual_beat: \"{topic}が進む\"",
                    "            narration_role: \"setup\"",
                    "            asset_dependency_hint: {character_ids: [\"momotaro_seed\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                ]
            )
            narration = "tool: \"silent\"\n            text: \"\"\n            tts_text: \"\"\n            silence_contract: {intentional: true, kind: \"visual_value_hold\", confirmed_by_human: true, reason: \"映像で見せる\"}" if silent and scene_idx == 1 and cut_idx == 1 else f"tool: \"elevenlabs\"\n            text: \"{topic}が進む。\""
            manifest_lines.extend(
                [
                    f"      - cut_id: {cut_idx}",
                    f"        selector: \"{selector}\"",
                    f"        scene_contract: {{target_beat: \"{topic}\", must_show: [\"{topic}\"], must_avoid: [], done_when: [\"{topic}が見える\"]}}",
                    "        image_generation:",
                    f"          prompt: \"画面内テキストなし。{topic}が朝の石畳の道を進む。手前に草の露、横に古い木柵、奥に低い山並み、斜めから入る柔らかな朝日、衣服の布目、足元の影、旅立ち前の緊張した表情が実写映画風に具体的に見える。\"",
                    "          character_ids: [\"momotaro_seed\"]",
                    "          object_ids: []",
                    f"          output: \"{image_output}\"",
                    "        video_generation:",
                    f"          duration_seconds: {cut_duration}",
                    "          motion_prompt: \"前へ進む。\"",
                    "        audio:",
                    "          narration:",
                    *[f"            {line.strip()}" for line in narration.splitlines()],
                    f"            output: \"{audio_output}\"",
                ]
            )
            _write_photo_like_test_png(run_dir / image_output)
            (run_dir / audio_output).parent.mkdir(parents=True, exist_ok=True)
            (run_dir / audio_output).write_bytes(b"audio")
    script_lines.extend(["```", ""])
    manifest_lines.extend(["```", ""])
    (run_dir / "script.md").write_text("\n".join(script_lines), encoding="utf-8")
    (run_dir / "video_manifest.md").write_text("\n".join(manifest_lines), encoding="utf-8")
    _write_p400_review_artifacts(run_dir)


def _write_basic_image_stage_artifacts(run_dir: Path, *, output: str = "assets/scenes/scene10.png", reference: str = "assets/characters/momotaro_seed.png") -> None:
    (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=IMAGE\n---\n", encoding="utf-8")
    _write_ready_grounding_artifacts(run_dir, "scene_implementation")
    (run_dir / "video_manifest.md").write_text(
        f"""```yaml
video_metadata:
  topic: "桃太郎"
  experience: "cinematic_story"
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        cut_role: "main"
        image_generation:
          tool: "codex_builtin_image"
          character_ids: ["momotaro_seed"]
          object_ids: []
          prompt: |
            実写映画風の森の道。画面内テキストなし。
          output: "{output}"
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 8
          output: "assets/scenes/scene10.mp4"
        audio:
          narration:
            text: "桃太郎が歩く。"
            tool: "elevenlabs"
            output: "assets/audio/scene10.mp3"
```""",
        encoding="utf-8",
    )
    (run_dir / "image_generation_requests.md").write_text(
        f"""# Image Generation Requests

## scene10_cut1

- tool: `codex_builtin_image`
- selector: `scene10_cut1`
- execution_lane: `standard`
- reference_count: `1`
- output: `{output}`
- references:
  - `momotaro_seed`: `{reference}`

```text
実写映画風。桃太郎が森の道を歩く一枚目のフレーム。画面内テキストなし。
```
""",
        encoding="utf-8",
    )
    _append_app_server_image_provenance(run_dir, output, item_id="scene10_cut1")
    if reference == "assets/characters/momotaro_seed.png":
        _append_app_server_image_provenance(run_dir, reference, item_id="momotaro_seed")


class TestVerifyPipeline(unittest.TestCase):
    def test_story_check_accepts_dense_story_without_author_score_hint(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_story_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0010"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "story.md").write_text(_good_story_yaml("桃太郎"), encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_story(run_dir, "fast")
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertTrue(checks["story.candidates"])
            self.assertTrue(checks["story.scene_purpose"])
            self.assertTrue(checks["story.scene_grounding_note"])

    def test_story_check_accepts_compact_dense_grounded_story(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_story_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0012"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "story.md").write_text(_good_story_yaml("桃太郎", scene_count=8), encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_story(run_dir, "fast")
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertTrue(checks["story.scenes"])

    def test_research_check_accepts_compact_grounded_pack(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_research_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0013"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "research.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "topic: \"桃太郎\"",
                        "story_baseline:",
                        "  canonical_synopsis:",
                        "    short_summary: \"桃から生まれた主人公が仲間と鬼退治へ向かう話を、主要転換が分かる厚みで整理する。\"",
                        "sources:",
                        "  - source_id: \"S1\"",
                        "    title: \"Primary source\"",
                        "    url: \"https://example.com/primary\"",
                        "source_passages:",
                    ]
                    + [
                        f"  - passage_id: \"P{i}\"\n    source_id: \"S1\"\n    passage: \"Passage {i}\"\n    evidence_note: \"Evidence {i}\"\n    confidence: 0.9"
                        for i in range(1, 6)
                    ]
                    + [
                        "conflicts:",
                        "  - conflict_id: \"C1\"",
                        "    topic: \"採用する物語軸\"",
                        "    accounts: []",
                        "handoff_to_story:",
                        "  recommended_focus: [\"主人公の選択\"]",
                        "  must_preserve: [\"根拠のある出来事\"]",
                        "metadata:",
                        "  confidence_score: 0.9",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            stage, _ = VERIFY_MODULE.check_research(run_dir, "fast")
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertTrue(checks["research.sources"])
            self.assertTrue(checks["research.chronological_events"])
            self.assertTrue(checks["research.facts"])

    def test_story_check_fails_when_scene_required_field_missing(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_story_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0011"
            run_dir.mkdir(parents=True, exist_ok=True)
            story = _good_story_yaml("桃太郎").replace("      conflict: \"Scene 7 の内的または外的な葛藤\"\n", "", 1)
            (run_dir / "story.md").write_text(story, encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_story(run_dir, "fast")
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["story.scene_conflict"])
            self.assertIn("7", stage["details"]["missing_conflict_scene_ids"])

    def test_verify_pipeline_p300_validates_visual_value_without_p400_artifacts(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_p300_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0300"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=STORY\n---\n", encoding="utf-8")
            (run_dir / "research.md").write_text(_good_research_yaml("桃太郎"), encoding="utf-8")
            (run_dir / "story.md").write_text(_good_story_yaml("桃太郎"), encoding="utf-8")
            (run_dir / "visual_value.md").write_text(_good_visual_value_yaml("桃太郎"), encoding="utf-8")
            _resolve_ready_p300_grounding(run_dir, flow="immersive")

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "verify-pipeline.py"),
                    "--run-dir",
                    str(run_dir),
                    "--flow",
                    "immersive",
                    "--profile",
                    "fast",
                    "--stage-target",
                    "p300",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads((run_dir / "eval_report.json").read_text(encoding="utf-8"))
            self.assertTrue(payload["overall"]["passed"], msg=payload)
            self.assertEqual(payload["stage_target"], "p330")
            self.assertEqual(set(payload["stages"]), {"orchestration", "research", "story", "visual_value"})
            self.assertEqual(payload["stages"]["orchestration"]["details"]["required_buckets"], ["p100", "p200", "p300"])
            self.assertFalse((run_dir / "script.md").exists())
            self.assertFalse((run_dir / "video_manifest.md").exists())

    def test_check_orchestration_accepts_l2_progress_result_and_terminal_state(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_orchestration_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0090"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_l2_orchestration_artifacts(run_dir, stage_target="p300")

            stage, updates = VERIFY_MODULE.check_orchestration(run_dir, stage_target="p330")
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertTrue(stage["passed"])
            self.assertTrue(checks["orchestration.progress_memo"])
            self.assertTrue(checks["orchestration.l2_invoked"])
            self.assertTrue(checks["orchestration.state_terminal"])
            self.assertTrue(checks["orchestration.supervisor_results"])
            self.assertEqual(stage["details"]["required_buckets"], ["p100", "p200", "p300"])
            self.assertEqual(updates["eval.orchestration.score"], "1.0000")

    def test_check_orchestration_fails_without_l2_progress_memo(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_orchestration_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0091"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\n---\n", encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_orchestration(run_dir, stage_target="p130")
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(stage["passed"])
            self.assertFalse(checks["orchestration.progress_memo"])
            self.assertFalse(checks["orchestration.l2_invoked"])
            self.assertFalse(checks["orchestration.state_terminal"])
            self.assertFalse(checks["orchestration.supervisor_results"])

    def test_check_orchestration_fails_when_l2_result_is_not_done(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_orchestration_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0092"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_l2_orchestration_artifacts(run_dir, stage_target="p100")
            result_path = run_dir / "logs" / "orchestration" / "p100.supervisor_result.json"
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            payload["status"] = "blocked"
            result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_orchestration(run_dir, stage_target="p130")
            checks = {check["id"]: check for check in stage["checks"]}

            self.assertFalse(stage["passed"])
            self.assertFalse(checks["orchestration.supervisor_results"]["passed"])
            self.assertIn("p100:result_status_not_done", checks["orchestration.supervisor_results"]["message"])

    def test_check_orchestration_fails_when_required_artifact_is_missing(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_orchestration_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0094"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_l2_orchestration_artifacts(run_dir, stage_target="p100")
            (run_dir / "research.md").unlink()

            stage, _ = VERIFY_MODULE.check_orchestration(run_dir, stage_target="p130")
            checks = {check["id"]: check for check in stage["checks"]}

            self.assertFalse(stage["passed"])
            self.assertFalse(checks["orchestration.supervisor_results"]["passed"])
            self.assertIn("p100:required_artifact_not_found:research.md", checks["orchestration.supervisor_results"]["message"])

    def test_check_orchestration_fails_when_completed_slot_is_outside_bucket(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_orchestration_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0095"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_l2_orchestration_artifacts(run_dir, stage_target="p100")
            result_path = run_dir / "logs" / "orchestration" / "p100.supervisor_result.json"
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            payload["completed_slots"] = ["p330"]
            result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_orchestration(run_dir, stage_target="p130")
            checks = {check["id"]: check for check in stage["checks"]}

            self.assertFalse(stage["passed"])
            self.assertFalse(checks["orchestration.supervisor_results"]["passed"])
            self.assertIn("p100:completed_slots_outside_bucket", checks["orchestration.supervisor_results"]["message"])

    def test_check_orchestration_fails_when_completed_slot_is_not_terminal_in_state(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_orchestration_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0096"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_l2_orchestration_artifacts(run_dir, stage_target="p100")
            append_state_snapshot(run_dir / "state.txt", {"slot.p130.status": "pending"})

            stage, _ = VERIFY_MODULE.check_orchestration(run_dir, stage_target="p130")
            checks = {check["id"]: check for check in stage["checks"]}

            self.assertFalse(stage["passed"])
            self.assertFalse(checks["orchestration.supervisor_results"]["passed"])
            self.assertIn("p100:completed_slots_not_terminal", checks["orchestration.supervisor_results"]["message"])

    def test_check_orchestration_fails_when_result_state_key_mismatches_state(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_orchestration_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0097"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_l2_orchestration_artifacts(run_dir, stage_target="p100")
            result_path = run_dir / "logs" / "orchestration" / "p100.supervisor_result.json"
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            payload["state_keys"]["slot.p130.status"] = "awaiting_approval"
            result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_orchestration(run_dir, stage_target="p130")
            checks = {check["id"]: check for check in stage["checks"]}

            self.assertFalse(stage["passed"])
            self.assertFalse(checks["orchestration.supervisor_results"]["passed"])
            self.assertIn("p100:state_key_mismatch:slot.p130.status", checks["orchestration.supervisor_results"]["message"])

    def test_check_orchestration_only_requires_buckets_up_to_stage_target(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_orchestration_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0093"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_l2_orchestration_artifacts(run_dir, stage_target="p300")

            stage, _ = VERIFY_MODULE.check_orchestration(run_dir, stage_target="p330")

            self.assertTrue(stage["passed"], msg=stage)
            self.assertEqual(stage["details"]["required_buckets"], ["p100", "p200", "p300"])
            self.assertFalse((run_dir / "logs" / "orchestration" / "p400.supervisor_result.json").exists())

    def test_verify_pipeline_normalizes_big_stage_targets_to_handoff_slots(self) -> None:
        cases = {
            "p100": "p130",
            "100": "p130",
            "p300": "p330",
            "300": "p330",
            "p400": "p450",
            "400": "p450",
            "p700": "p750",
            "700": "p750",
            "p900": "p930",
            "900": "p930",
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(VERIFY_MODULE.normalize_stage_target(raw), expected)

    def test_verify_pipeline_keeps_fine_slot_targets_exact(self) -> None:
        for slot in ("p110", "p130", "p310", "p320", "p330", "p450", "p750", "p930"):
            with self.subTest(slot=slot):
                self.assertEqual(VERIFY_MODULE.normalize_stage_target(slot), slot)

    def test_verify_pipeline_stage_targets_p400_and_default_include_visual_value(self) -> None:
        self.assertIn("visual_value", VERIFY_MODULE.STAGE_TARGETS["p450"])
        self.assertIn("visual_value", VERIFY_MODULE.STAGE_TARGETS[VERIFY_MODULE.normalize_stage_target(None)])

    def test_verify_pipeline_stage_targets_follow_downstream_order(self) -> None:
        self.assertIn("asset", VERIFY_MODULE.STAGE_TARGETS["p570"])
        self.assertNotIn("image", VERIFY_MODULE.STAGE_TARGETS["p570"])
        self.assertIn("image", VERIFY_MODULE.STAGE_TARGETS["p680"])
        self.assertNotIn("narration", VERIFY_MODULE.STAGE_TARGETS["p680"])
        self.assertIn("narration", VERIFY_MODULE.STAGE_TARGETS["p750"])
        self.assertNotIn("video", VERIFY_MODULE.STAGE_TARGETS["p750"])
        self.assertIn("video", VERIFY_MODULE.STAGE_TARGETS["p930"])

    def test_check_asset_accepts_complete_asset_contract(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_asset_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0500"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=ASSET\n---\n", encoding="utf-8")
            _write_ready_grounding_artifacts(run_dir, "asset")
            _write_downstream_generation_artifacts(run_dir)

            stage, _ = VERIFY_MODULE.check_asset(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertTrue(stage["passed"])
            self.assertTrue(checks["asset.asset_inventory"])
            self.assertTrue(checks["asset.inventory_schema"])
            self.assertTrue(checks["asset.inventory_no_todo"])
            self.assertTrue(checks["asset.plan_structured"])
            self.assertTrue(checks["asset.character_three_views"])
            self.assertTrue(checks["asset.review_approved"])
            self.assertTrue(checks["asset.request_metadata"])
            self.assertTrue(checks["asset.request_prompt_no_production_meta"])
            self.assertTrue(checks["asset.generation_provenance_app_server"])
            self.assertTrue(checks["asset.visual_not_vector_like"])

    def test_check_asset_rejects_vector_like_generated_asset_output(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_asset_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0507"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=ASSET\n---\n", encoding="utf-8")
            _write_ready_grounding_artifacts(run_dir, "asset")
            _write_downstream_generation_artifacts(run_dir)
            _write_vector_like_test_png(run_dir / "assets" / "characters" / "momotaro_seed.png")

            stage, _ = VERIFY_MODULE.check_asset(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["asset.visual_not_vector_like"])
            self.assertIn("asset_visual_quality_issues", stage["details"])
            self.assertIn("vector-like", "\n".join(stage["details"]["asset_visual_quality_issues"]))

    def test_check_image_accepts_photo_like_scene_and_reference(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_image_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0600"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_basic_image_stage_artifacts(run_dir)
            _write_photo_like_test_png(run_dir / "assets" / "scenes" / "scene10.png")
            _write_photo_like_test_png(run_dir / "assets" / "characters" / "momotaro_seed.png")

            stage, _ = VERIFY_MODULE.check_image(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertTrue(checks["image.visual_not_vector_like"])
            self.assertTrue(checks["image.references_not_vector_like"])
            self.assertTrue(checks["image.generation_provenance_app_server"])
            self.assertTrue(checks["image.request_lane_consistency"])
            self.assertNotIn("image_regeneration_plan", stage["details"])

    def test_check_image_rejects_local_raster_provenance_even_when_png_is_complex(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_image_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0607"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_basic_image_stage_artifacts(run_dir)
            _write_photo_like_test_png(run_dir / "assets" / "scenes" / "scene10.png")
            _write_photo_like_test_png(run_dir / "assets" / "characters" / "momotaro_seed.png")
            (run_dir / "logs" / "image_generation_prompts.jsonl").unlink()
            _append_app_server_image_provenance(
                run_dir,
                "assets/scenes/scene10.png",
                item_id="scene10_cut1",
                source="local_raster_generation_after_app_server_permission_failure",
            )
            _append_app_server_image_provenance(run_dir, "assets/characters/momotaro_seed.png", item_id="momotaro_seed")

            stage, _ = VERIFY_MODULE.check_image(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["image.generation_provenance_app_server"])
            self.assertIn("local raster fallback", "\n".join(stage["details"]["image_generation_provenance_failures"]))

    def test_check_image_rejects_no_reference_standard_lane(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_image_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0603"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_basic_image_stage_artifacts(run_dir)
            _write_photo_like_test_png(run_dir / "assets" / "scenes" / "scene10.png")
            request_path = run_dir / "image_generation_requests.md"
            request_text = request_path.read_text(encoding="utf-8")
            request_text = request_text.replace("- reference_count: `1`", "- reference_count: `0`")
            request_text = request_text.replace("- references:\n  - `momotaro_seed`: `assets/characters/momotaro_seed.png`", "- references: `[]`")
            request_path.write_text(request_text, encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_image(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["image.request_lane_consistency"])
            self.assertIn("execution_lane standard mismatches reference_count 0", "\n".join(stage["details"]["image_request_lane_failures"]))

    def test_check_image_rejects_vector_like_scene_and_routes_to_p600_when_references_are_raster(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_image_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0601"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_basic_image_stage_artifacts(run_dir)
            _write_vector_like_test_png(run_dir / "assets" / "scenes" / "scene10.png")
            _write_photo_like_test_png(run_dir / "assets" / "characters" / "momotaro_seed.png")

            stage, _ = VERIFY_MODULE.check_image(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["image.visual_not_vector_like"])
            self.assertTrue(checks["image.references_not_vector_like"])
            self.assertEqual(stage["details"]["image_regeneration_plan"][0]["action"], "regenerate_p600_scene")

    def test_check_image_rejects_noise_masked_vector_like_scene(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_image_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0604"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_basic_image_stage_artifacts(run_dir)
            _write_noise_masked_vector_like_test_png(run_dir / "assets" / "scenes" / "scene10.png")
            _write_photo_like_test_png(run_dir / "assets" / "characters" / "momotaro_seed.png")

            stage, _ = VERIFY_MODULE.check_image(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["image.visual_not_vector_like"])
            self.assertTrue(checks["image.references_not_vector_like"])
            self.assertIn("vector-like", "\n".join(stage["details"]["image_visual_quality_issues"]))
            self.assertEqual(stage["details"]["image_regeneration_plan"][0]["action"], "regenerate_p600_scene")

    def test_check_image_rejects_detailed_cel_vector_like_scene(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_image_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0605"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_basic_image_stage_artifacts(run_dir)
            _write_detailed_cel_vector_like_test_png(run_dir / "assets" / "scenes" / "scene10.png")
            _write_photo_like_test_png(run_dir / "assets" / "characters" / "momotaro_seed.png")

            stage, _ = VERIFY_MODULE.check_image(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["image.visual_not_vector_like"])
            self.assertTrue(checks["image.references_not_vector_like"])
            self.assertIn("vector-like", "\n".join(stage["details"]["image_visual_quality_issues"]))

    def test_check_image_rejects_uninspected_manifest_output(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_image_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0606"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_basic_image_stage_artifacts(run_dir, output="assets/scenes/manifest_only.png")
            request_path = run_dir / "image_generation_requests.md"
            request_path.write_text(
                request_path.read_text(encoding="utf-8").replace("assets/scenes/manifest_only.png", "assets/scenes/request_only.png"),
                encoding="utf-8",
            )
            _write_photo_like_test_png(run_dir / "assets" / "scenes" / "manifest_only.png")
            _write_photo_like_test_png(run_dir / "assets" / "scenes" / "request_only.png")
            _write_photo_like_test_png(run_dir / "assets" / "characters" / "momotaro_seed.png")

            stage, _ = VERIFY_MODULE.check_image(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["image.visual_outputs_inspected"])
            self.assertFalse(checks["image.visual_not_vector_like"])
            self.assertIn("assets/scenes/manifest_only.png", stage["details"]["uninspected_image_outputs"])

    def test_check_asset_rejects_noise_masked_vector_like_asset(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_asset_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0508"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=ASSET\n---\n", encoding="utf-8")
            _write_ready_grounding_artifacts(run_dir, "asset")
            _write_downstream_generation_artifacts(run_dir)
            _write_noise_masked_vector_like_test_png(run_dir / "assets" / "characters" / "momotaro_seed.png")

            stage, _ = VERIFY_MODULE.check_asset(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["asset.visual_not_vector_like"])
            self.assertIn("vector-like", "\n".join(stage["details"]["asset_visual_quality_issues"]))

    def test_check_image_rejects_vector_like_reference_and_routes_to_p500(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_image_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0602"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_basic_image_stage_artifacts(run_dir)
            _write_vector_like_test_png(run_dir / "assets" / "scenes" / "scene10.png")
            _write_vector_like_test_png(run_dir / "assets" / "characters" / "momotaro_seed.png")

            stage, _ = VERIFY_MODULE.check_image(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["image.visual_not_vector_like"])
            self.assertFalse(checks["image.references_not_vector_like"])
            self.assertEqual(stage["details"]["image_regeneration_plan"][0]["action"], "regenerate_p500_reference_first")
            self.assertIn("assets/characters/momotaro_seed.png", stage["details"]["image_regeneration_plan"][0]["vector_like_references"])

    def test_check_asset_rejects_incomplete_asset_contract(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_asset_") as td:
            run_dir = Path(td) / "out" / "cinderella_20990101_0501"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=シンデレラ\nstatus=ASSET\n---\n", encoding="utf-8")
            _write_ready_grounding_artifacts(run_dir, "asset")
            (run_dir / "asset_plan.md").write_text(
                """```yaml
assets:
  characters:
    - asset_id: "cinderella_work"
      asset_type: "character_reference"
      source_script_selectors: ["scene10_cut1"]
      story_purpose: "灰の台所のシンデレラ"
      visual_spec:
        identity: ["灰をかぶった仕事着"]
      generation_plan:
        output_dir: "assets/characters"
        required_views: ["front"]
        execution_lane: "standard"
        bootstrap_allowed: false
        reference_inputs: []
      creation_status: "planned"
      existing_outputs: []
      review:
        status: "pending"
```
""",
                encoding="utf-8",
            )
            (run_dir / "asset_generation_requests.md").write_text(
                """# Asset Generation Requests

## cinderella_work

- asset_id: `cinderella_work`
- output: `assets/characters/cinderella_work.png`

```text
物語「シンデレラ」の scene10。scene10_cut1 のための画像。
```
""",
                encoding="utf-8",
            )
            (run_dir / "asset_generation_manifest.md").write_text("```yaml\nasset_generation_manifest:\n  items: []\n```\n", encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_asset(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(stage["passed"])
            self.assertFalse(checks["asset.asset_inventory"])
            self.assertFalse(checks["asset.inventory_schema"])
            self.assertFalse(checks["asset.character_three_views"])
            self.assertFalse(checks["asset.review_approved"])
            self.assertFalse(checks["asset.output_files"])
            self.assertFalse(checks["asset.request_metadata"])
            self.assertFalse(checks["asset.request_prompt_no_production_meta"])

    def test_check_asset_accepts_review_status_dotted_request_metadata(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_asset_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0502"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=ASSET\n---\n", encoding="utf-8")
            _write_ready_grounding_artifacts(run_dir, "asset")
            _write_downstream_generation_artifacts(run_dir)
            request_path = run_dir / "asset_generation_requests.md"
            request_path.write_text(
                request_path.read_text(encoding="utf-8").replace("- review_status: `approved`", "- review.status: `approved`"),
                encoding="utf-8",
            )

            stage, _ = VERIFY_MODULE.check_asset(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertTrue(checks["asset.request_metadata"], msg=stage["details"])

    def test_check_asset_accepts_selector_based_manifest_item(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_asset_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0506"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=ASSET\n---\n", encoding="utf-8")
            _write_ready_grounding_artifacts(run_dir, "asset")
            _write_downstream_generation_artifacts(run_dir)
            manifest_path = run_dir / "asset_generation_manifest.md"
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8").replace('asset_id: "momotaro_seed"', 'selector: "momotaro_seed"'),
                encoding="utf-8",
            )

            stage, _ = VERIFY_MODULE.check_asset(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertTrue(checks["asset.manifest_items"], msg=stage["details"])

    def test_check_asset_rejects_inventory_template_placeholders(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_asset_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0503"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=ASSET\n---\n", encoding="utf-8")
            _write_ready_grounding_artifacts(run_dir, "asset")
            _write_downstream_generation_artifacts(run_dir)
            (run_dir / "asset_inventory.md").write_text(_good_asset_inventory_yaml().replace("主人公の基準参照", "REPLACE_ME: purpose"), encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_asset(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["asset.inventory_no_todo"])

    def test_check_asset_rejects_inventory_missing_story_purpose(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_asset_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0504"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=ASSET\n---\n", encoding="utf-8")
            _write_ready_grounding_artifacts(run_dir, "asset")
            _write_downstream_generation_artifacts(run_dir)
            (run_dir / "asset_inventory.md").write_text(_good_asset_inventory_yaml().replace('      story_purpose: "主人公の基準参照"\n', ""), encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_asset(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["asset.inventory_schema"])

    def test_check_asset_rejects_no_reference_standard_lane(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_asset_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0505"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=ASSET\n---\n", encoding="utf-8")
            _write_ready_grounding_artifacts(run_dir, "asset")
            _write_downstream_generation_artifacts(run_dir)
            plan_path = run_dir / "asset_plan.md"
            plan_path.write_text(plan_path.read_text(encoding="utf-8").replace('execution_lane: "bootstrap_builtin"', 'execution_lane: "standard"'), encoding="utf-8")
            request_path = run_dir / "asset_generation_requests.md"
            request_path.write_text(request_path.read_text(encoding="utf-8").replace("- execution_lane: `bootstrap_builtin`", "- execution_lane: `standard`"), encoding="utf-8")

            stage, _ = VERIFY_MODULE.check_asset(run_dir)
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertFalse(checks["asset.lane_consistency"])
            self.assertFalse(checks["asset.request_metadata"])

    def test_verify_pipeline_p300_accepts_major_scene_visual_value_coverage(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_p300_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0302"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=STORY\n---\n", encoding="utf-8")
            (run_dir / "research.md").write_text(_good_research_yaml("桃太郎"), encoding="utf-8")
            (run_dir / "story.md").write_text(_good_story_yaml("桃太郎", scene_count=20), encoding="utf-8")
            (run_dir / "visual_value.md").write_text(_good_visual_value_yaml("桃太郎", scene_count=8), encoding="utf-8")
            _resolve_ready_p300_grounding(run_dir, flow="immersive")

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "verify-pipeline.py"),
                    "--run-dir",
                    str(run_dir),
                    "--flow",
                    "immersive",
                    "--profile",
                    "fast",
                    "--stage-target",
                    "p300",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads((run_dir / "eval_report.json").read_text(encoding="utf-8"))
            checks = {check["id"]: check for check in payload["stages"]["visual_value"]["checks"]}
            self.assertTrue(checks["visual_value.scene_coverage"]["passed"])

    def test_verify_pipeline_p300_rejects_template_placeholders(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_p300_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0303"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=STORY\n---\n", encoding="utf-8")
            (run_dir / "research.md").write_text(_good_research_yaml("桃太郎"), encoding="utf-8")
            (run_dir / "story.md").write_text(_good_story_yaml("桃太郎"), encoding="utf-8")
            (run_dir / "visual_value.md").write_text(
                _good_visual_value_yaml("桃太郎").replace("topic: \"桃太郎\"", "topic: \"REPLACE_ME_TOPIC\""),
                encoding="utf-8",
            )
            _resolve_ready_p300_grounding(run_dir, flow="immersive")

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "verify-pipeline.py"),
                    "--run-dir",
                    str(run_dir),
                    "--flow",
                    "immersive",
                    "--profile",
                    "fast",
                    "--stage-target",
                    "p300",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertNotEqual(result.returncode, 0)
            payload = json.loads((run_dir / "eval_report.json").read_text(encoding="utf-8"))
            checks = {check["id"]: check for check in payload["stages"]["visual_value"]["checks"]}
            self.assertFalse(checks["visual_value.no_template_placeholders"]["passed"])

    def test_verify_pipeline_p300_slots_reject_production_prompts(self) -> None:
        import tempfile

        for stage_target in ("p300", "p310", "p320", "p330"):
            with self.subTest(stage_target=stage_target), tempfile.TemporaryDirectory(prefix="toc_verify_p300_") as td:
                run_dir = Path(td) / "out" / "momotaro_20990101_0301"
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "state.txt").write_text("topic=桃太郎\nstatus=STORY\n---\n", encoding="utf-8")
                (run_dir / "research.md").write_text(_good_research_yaml("桃太郎"), encoding="utf-8")
                (run_dir / "story.md").write_text(_good_story_yaml("桃太郎"), encoding="utf-8")
                (run_dir / "visual_value.md").write_text(_good_visual_value_yaml("桃太郎"), encoding="utf-8")
                (run_dir / "video_manifest.md").write_text(
                    "\n".join(
                        [
                            "```yaml",
                            "manifest_phase: production",
                            "scenes:",
                            "  - scene_id: 1",
                            "    cuts:",
                            "      - cut_id: 1",
                            "        image_generation:",
                            "          prompt: \"本番画像生成プロンプト\"",
                            "        video_generation:",
                            "          motion_prompt: \"本番動画生成プロンプト\"",
                            "```",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                _resolve_ready_p300_grounding(run_dir, flow="immersive")

                result = subprocess.run(
                    [
                        sys.executable,
                        str(REPO_ROOT / "scripts" / "verify-pipeline.py"),
                        "--run-dir",
                        str(run_dir),
                        "--flow",
                        "immersive",
                        "--profile",
                        "fast",
                        "--p-slot",
                        stage_target,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    cwd=REPO_ROOT,
                )

                self.assertNotEqual(result.returncode, 0)
                payload = json.loads((run_dir / "eval_report.json").read_text(encoding="utf-8"))
                checks = {check["id"]: check for check in payload["stages"]["visual_value"]["checks"]}
                self.assertFalse(checks["visual_value.no_p300_production_artifacts"]["passed"])

    def test_verify_pipeline_p300_rejects_production_artifact_files(self) -> None:
        import tempfile

        cases = [
            ("asset_generation_requests.md", "asset_generation_requests.md", lambda run_dir: (run_dir / "asset_generation_requests.md").write_text("requests\n", encoding="utf-8")),
            ("video.mp4", "video.mp4", lambda run_dir: (run_dir / "video.mp4").write_bytes(b"placeholder")),
            ("shorts", "shorts", lambda run_dir: (run_dir / "shorts" / "short01.mp4").write_bytes(b"placeholder")),
            ("scene-series render", "scenes/scene01/video.mp4", lambda run_dir: (run_dir / "scenes" / "scene01" / "video.mp4").write_bytes(b"placeholder")),
        ]
        for label, expected_issue, write_artifact in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory(prefix="toc_verify_p300_artifact_") as td:
                run_dir = Path(td) / "out" / "momotaro_20990101_0304"
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "visual_value.md").write_text(_good_visual_value_yaml("桃太郎"), encoding="utf-8")
                if label == "shorts":
                    (run_dir / "shorts").mkdir(parents=True, exist_ok=True)
                if label == "scene-series render":
                    (run_dir / "scenes" / "scene01").mkdir(parents=True, exist_ok=True)
                write_artifact(run_dir)

                stage, _ = VERIFY_MODULE.check_visual_value(run_dir, "fast")

                checks = {check["id"]: check for check in stage["checks"]}
                self.assertFalse(checks["visual_value.no_p300_production_artifacts"]["passed"])
                self.assertIn(expected_issue, stage["details"]["p300_production_artifact_issues"])

    def test_verify_pipeline_fast_generates_reports(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "timestamp=2099-01-01T00:00:00+09:00",
                        "job_id=JOB_2099-01-01_000000",
                        "topic=桃太郎",
                        "status=DONE",
                        "runtime.stage=done",
                        "runtime.render.status=success",
                        "review.video.status=pending",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            (run_dir / "research.md").write_text(
                "\n".join(
                    [
                        "# Research",
                        "",
                        "```yaml",
                        "topic: \"桃太郎\"",
                        "story_baseline:",
                        "  canonical_synopsis:",
                        "    one_liner: \"桃太郎の旅\"",
                        "    short_summary: \"桃から生まれた主人公が仲間と鬼退治へ向かう。\"",
                        "    beat_sheet:",
                    ]
                    + [f"      - beat: \"Beat {i}\"\n        scene_ids: [{i}]\n        confidence: 0.9\n        sources: [\"S1\"]" for i in range(1, 21)]
                    + [
                        "sources:",
                    ]
                    + [
                        f"  - source_id: \"S{i}\"\n    title: \"Source {i}\"\n    url: \"https://example.com/{i}\"\n    type: \"primary\"\n    reliability: \"high\"\n    accessed_at: \"2099-01-01T00:00:00+09:00\"\n    notes: \"\""
                        for i in range(1, 13)
                    ]
                    + [
                        "conflicts:",
                        "  - conflict_id: \"C1\"",
                        "    topic: \"採用する桃太郎像\"",
                        "    accounts:",
                        "      - account_id: \"A\"",
                        "        claim: \"英雄譚として扱う\"",
                        "        sources: [\"S1\"]",
                        "        confidence: 0.9",
                        "      - account_id: \"B\"",
                        "        claim: \"教訓譚として扱う\"",
                        "        sources: [\"S2\"]",
                        "        confidence: 0.8",
                        "    impact_on_story: \"p200 の候補比較に使う\"",
                        "    selection_notes:",
                        "      recommended_choice: \"both_separated\"",
                        "      rationale: \"候補比較で分けて扱える\"",
                        "source_passages:",
                    ]
                    + [
                        f"  - passage_id: \"P{i}\"\n    source_id: \"S1\"\n    passage: \"Passage {i}\"\n    evidence_note: \"Evidence {i}\"\n    confidence: 0.9"
                        for i in range(1, 3)
                    ]
                    + [
                        "facts:",
                        "  items:",
                    ]
                    + [
                        f"    - fact_id: \"F{i}\"\n      claim: \"Fact {i}\"\n      kind: \"plot\"\n      confidence: 0.9\n      verification: \"verified\"\n      sources: [\"S1\"]\n      notes: \"\""
                        for i in range(1, 11)
                    ]
                    + [
                        "handoff_to_story:",
                        "  recommended_focus: [\"桃太郎の選択\"]",
                        "  must_preserve: [\"出典に基づく出来事\"]",
                        "  avoid_overstating: [\"未検証の起源\"]",
                        "  selection_questions_for_p200: [\"どの葛藤を中心にするか\"]",
                        "metadata:",
                        "  confidence_score: 0.9",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            (run_dir / "story.md").write_text(_good_story_yaml("桃太郎"), encoding="utf-8")
            (run_dir / "visual_value.md").write_text(_good_visual_value_yaml("桃太郎"), encoding="utf-8")

            (run_dir / "script.md").write_text(
                "# Script\n\n桃太郎が出発し、犬と猿と雉を仲間にし、鬼ヶ島へ向かい、戦いの後に宝を持ち帰るまでを具体的に描く台本です。"
                "各カットで誰が見え、何を話し、どの感情で次へつなぐかを明示しています。\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "video_metadata:",
                        "  topic: \"桃太郎\"",
                        "  experience: \"cinematic_story\"",
                        "scenes:",
                        "  - scene_id: 10",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        cut_role: \"main\"",
                        "        image_generation:",
                        "          tool: \"codex_builtin_image\"",
                        "          character_ids: []",
                        "          object_ids: []",
                        "          prompt: |",
                        "            画面内テキストなし。",
                        "          output: \"assets/scenes/scene10.png\"",
                        "        video_generation:",
                        "          tool: \"kling_3_0\"",
                        "          duration_seconds: 8",
                        "          output: \"assets/scenes/scene10.mp4\"",
                        "        audio:",
                        "          narration:",
                        "            text: \"桃太郎が出発する。\"",
                        "            tool: \"elevenlabs\"",
                        "            output: \"assets/audio/scene10.mp3\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            _write_verify_ready_p400_pair(run_dir, topic="桃太郎")
            _write_downstream_generation_artifacts(run_dir)
            _write_image_requests_from_manifest(run_dir)
            _write_photo_like_test_png(run_dir / "assets" / "scenes" / "scene10.png")
            (run_dir / "assets" / "audio" / "scene10.mp3").write_bytes(b"audio")
            (run_dir / "video.mp4").write_bytes(b"placeholder")
            _resolve_ready_p300_grounding(run_dir, flow="immersive")
            _resolve_ready_grounding(run_dir, flow="immersive")

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "verify-pipeline.py"),
                    "--run-dir",
                    str(run_dir),
                    "--flow",
                    "immersive",
                    "--profile",
                    "fast",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue((run_dir / "eval_report.json").exists())
            self.assertTrue((run_dir / "run_report.md").exists())
            payload = json.loads((run_dir / "eval_report.json").read_text(encoding="utf-8"))
            self.assertIn("overall", payload)
            self.assertTrue(payload["overall"]["passed"])

    def test_verify_pipeline_standard_allows_silent_cut(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_") as td:
            run_dir = Path(td) / "out" / "urashimataro_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "timestamp=2099-01-01T00:00:00+09:00",
                        "job_id=JOB_2099-01-01_000001",
                        "topic=浦島太郎",
                        "status=DONE",
                        "runtime.stage=done",
                        "runtime.render.status=success",
                        "review.video.status=pending",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            (run_dir / "research.md").write_text(
                "\n".join(
                    [
                        "# Research",
                        "",
                        "```yaml",
                        "topic: \"浦島太郎\"",
                        "story_baseline:",
                        "  canonical_synopsis:",
                        "    one_liner: \"浦島太郎の旅\"",
                        "    short_summary: \"浦島太郎が海辺から竜宮城へ入り、異界の魅力を体験したあと地上へ戻る。\"",
                        "    beat_sheet:",
                    ]
                    + [f"      - beat: \"Beat {i}\"\n        scene_ids: [{i}]\n        confidence: 0.9\n        sources: [\"S1\"]" for i in range(1, 21)]
                    + [
                        "scene_plan:",
                        "  min_scene_count: 20",
                        "  scenes:",
                    ]
                    + [
                        f"    - scene_id: {i}\n      role: \"development\"\n      beat_summary: \"Scene {i}\"\n      desired_emotion: \"curiosity\"\n      key_visuals: [\"Visual {i}\"]\n      key_dialogue_or_voiceover: \"Voice {i}\"\n      continuity_requirements:\n        from_prev: \"\"\n        to_next: \"\""
                        for i in range(1, 21)
                    ]
                    + [
                        "sources:",
                    ]
                    + [
                        f"  - source_id: \"S{i}\"\n    title: \"Source {i}\"\n    url: \"https://example.com/{i}\"\n    type: \"primary\"\n    reliability: \"high\"\n    accessed_at: \"2099-01-01T00:00:00+09:00\"\n    notes: \"\""
                        for i in range(1, 13)
                    ]
                    + [
                        "conflicts:",
                        "  - conflict_id: \"C1\"",
                        "    topic: \"採用する浦島太郎像\"",
                        "    accounts:",
                        "      - account_id: \"A\"",
                        "        claim: \"時間断絶譚として扱う\"",
                        "        sources: [\"S1\"]",
                        "        confidence: 0.9",
                        "      - account_id: \"B\"",
                        "        claim: \"約束破りの教訓譚として扱う\"",
                        "        sources: [\"S2\"]",
                        "        confidence: 0.8",
                        "    impact_on_story: \"p200 の候補比較に使う\"",
                        "    selection_notes:",
                        "      recommended_choice: \"both_separated\"",
                        "      rationale: \"候補比較で分けて扱える\"",
                        "source_passages:",
                    ]
                    + [
                        f"  - passage_id: \"P{i}\"\n    source_id: \"S1\"\n    passage: \"Passage {i}\"\n    evidence_note: \"Evidence {i}\"\n    confidence: 0.9"
                        for i in range(1, 3)
                    ]
                    + [
                        "facts:",
                        "  items:",
                    ]
                    + [
                        f"    - fact_id: \"F{i}\"\n      claim: \"Fact {i}\"\n      kind: \"plot\"\n      confidence: 0.9\n      verification: \"verified\"\n      sources: [\"S1\"]\n      notes: \"\""
                        for i in range(1, 11)
                    ]
                    + [
                        "handoff_to_story:",
                        "  recommended_focus: [\"浦島太郎の帰還不能\"]",
                        "  must_preserve: [\"時間断絶\"]",
                        "  avoid_overstating: [\"未検証の起源\"]",
                        "  selection_questions_for_p200: [\"どの版を採用するか\"]",
                        "metadata:",
                        "  confidence_score: 0.9",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "story.md").write_text(_good_story_yaml("浦島太郎"), encoding="utf-8")
            (run_dir / "visual_value.md").write_text(_good_visual_value_yaml("浦島太郎"), encoding="utf-8")
            (run_dir / "script.md").write_text(
                "# Script\n\n浦島太郎が海辺から異界へ入り、竜宮城の魅力を体験したあと、乙姫に出会うまでを描く台本です。"
                "この版では、中盤に無音の視覚報酬カットを入れ、竜宮城の内部を複数の短い探索カットで見せます。"
                "各カットで何を見せ、どの感情で次へつなぐかを明記しています。\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "video_metadata:",
                        "  topic: \"浦島太郎\"",
                        "  experience: \"cinematic_story\"",
                        "scenes:",
                        "  - scene_id: 40",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        cut_role: \"sub\"",
                        "        image_generation:",
                        "          tool: \"codex_builtin_image\"",
                        "          character_ids: []",
                        "          object_ids: [\"ryugu_palace\"]",
                        "          prompt: |",
                        "            画面内テキストなし。",
                        "          output: \"assets/scenes/scene40_1.png\"",
                        "        video_generation:",
                        "          tool: \"kling_3_0\"",
                        "          duration_seconds: 4",
                        "          output: \"assets/scenes/scene40_1.mp4\"",
                        "        audio:",
                        "          narration:",
                        "            tool: \"silent\"",
                        "            text: \"\"",
                        "            tts_text: \"\"",
                        "            silence_contract:",
                        "              intentional: true",
                        "              kind: \"visual_value_hold\"",
                        "              confirmed_by_human: true",
                        "              reason: \"映像で見せる価値が大きい追加カット\"",
                        "            output: \"assets/audio/scene40_1.mp3\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            _write_verify_ready_p400_pair(run_dir, topic="浦島太郎", silent=True)
            _write_downstream_generation_artifacts(run_dir)
            _write_image_requests_from_manifest(run_dir)
            _write_photo_like_test_png(run_dir / "assets" / "scenes" / "scene40_1.png")
            (run_dir / "assets" / "audio" / "scene40_1.mp3").write_bytes(b"audio")
            (run_dir / "video.mp4").write_bytes(b"placeholder")
            _resolve_ready_p300_grounding(run_dir, flow="immersive")
            _resolve_ready_grounding(run_dir, flow="immersive")

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "verify-pipeline.py"),
                    "--run-dir",
                    str(run_dir),
                    "--flow",
                    "immersive",
                    "--profile",
                    "standard",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads((run_dir / "eval_report.json").read_text(encoding="utf-8"))
            self.assertTrue(payload["overall"]["passed"], msg=payload)

    def test_verify_pipeline_standard_rejects_silent_cut_without_contract(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_") as td:
            run_dir = Path(td) / "out" / "urashimataro_20990101_0001"
            run_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "timestamp=2099-01-01T00:00:00+09:00",
                        "job_id=JOB_2099-01-01_000001",
                        "topic=浦島太郎",
                        "status=DONE",
                        "runtime.stage=done",
                        "runtime.render.status=success",
                        "review.video.status=pending",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "research.md").write_text("```yaml\ntopic: \"浦島太郎\"\nstory_baseline:\n  canonical_synopsis:\n    one_liner: \"浦島太郎\"\n    short_summary: \"summary\"\n    beat_sheet:\n      - beat: \"b\"\n        scene_ids: [1]\n        confidence: 0.9\n        sources: [\"S1\"]\nscene_plan:\n  min_scene_count: 1\n  scenes:\n    - scene_id: 1\n      role: \"opening\"\n      beat_summary: \"b\"\n      desired_emotion: \"c\"\n      key_visuals: [\"v\"]\n      key_dialogue_or_voiceover: \"k\"\n      continuity_requirements:\n        from_prev: \"\"\n        to_next: \"\"\nsources:\n  - source_id: \"S1\"\n    title: \"s\"\n    url: \"https://example.com\"\n    type: \"primary\"\n    reliability: \"high\"\n    accessed_at: \"2099-01-01T00:00:00+09:00\"\n    notes: \"\"\nconflicts: []\nmetadata:\n  confidence_score: 0.9\n```\n", encoding="utf-8")
            (run_dir / "story.md").write_text(_good_story_yaml("浦島太郎"), encoding="utf-8")
            (run_dir / "script.md").write_text("# Script\n\nok", encoding="utf-8")
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "video_metadata:",
                        "  topic: \"浦島太郎\"",
                        "  experience: \"cinematic_story\"",
                        "scenes:",
                        "  - scene_id: 40",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        cut_role: \"sub\"",
                        "        image_generation:",
                        "          tool: \"codex_builtin_image\"",
                        "          character_ids: []",
                        "          object_ids: [\"ryugu_palace\"]",
                        "          prompt: |",
                        "            画面内テキストなし。",
                        "          output: \"assets/scenes/scene40_1.png\"",
                        "        video_generation:",
                        "          tool: \"kling_3_0\"",
                        "          duration_seconds: 4",
                        "          output: \"assets/scenes/scene40_1.mp4\"",
                        "        audio:",
                        "          narration:",
                        "            tool: \"silent\"",
                        "            text: \"\"",
                        "            output: \"assets/audio/scene40_1.mp3\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "video.mp4").write_bytes(b"placeholder")
            _resolve_ready_grounding(run_dir, flow="immersive")

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "verify-pipeline.py"),
                    "--run-dir",
                    str(run_dir),
                    "--flow",
                    "immersive",
                    "--profile",
                    "standard",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertNotEqual(result.returncode, 0)

    def test_verify_pipeline_fails_when_grounding_readset_missing(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_verify_") as td:
            run_dir = Path(td) / "out" / "momotaro_20990101_0009"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "timestamp=2099-01-01T00:00:00+09:00",
                        "job_id=JOB_2099-01-01_000009",
                        "topic=桃太郎",
                        "status=DONE",
                        "runtime.stage=done",
                        "runtime.render.status=success",
                        "review.video.status=pending",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "research.md").write_text("```yaml\ntopic: \"桃太郎\"\nstory_baseline:\n  canonical_synopsis:\n    one_liner: \"桃太郎\"\n    short_summary: \"summary\"\n    beat_sheet:\n      - beat: \"b1\"\n        scene_ids: [1]\n        confidence: 0.9\n        sources: [\"S1\"]\nscene_plan:\n  min_scene_count: 1\n  scenes:\n    - scene_id: 1\n      role: \"opening\"\n      beat_summary: \"b\"\n      desired_emotion: \"c\"\n      key_visuals: [\"v\"]\n      key_dialogue_or_voiceover: \"k\"\n      continuity_requirements:\n        from_prev: \"\"\n        to_next: \"\"\nsources:\n  - source_id: \"S1\"\n    title: \"s\"\n    url: \"https://example.com\"\n    type: \"primary\"\n    reliability: \"high\"\n    accessed_at: \"2099-01-01T00:00:00+09:00\"\n    notes: \"\"\nconflicts: []\nmetadata:\n  confidence_score: 0.9\n```\n", encoding="utf-8")
            (run_dir / "story.md").write_text(_good_story_yaml("桃太郎"), encoding="utf-8")
            (run_dir / "script.md").write_text("# Script\n\n十分な長さの script 本文です。十分な長さの script 本文です。\n", encoding="utf-8")
            (run_dir / "video_manifest.md").write_text("```yaml\nvideo_metadata:\n  topic: \"桃太郎\"\n  experience: \"cinematic_story\"\nscenes:\n  - scene_id: 1\n    cuts:\n      - cut_id: 1\n        cut_role: \"main\"\n        image_generation:\n          tool: \"codex_builtin_image\"\n          character_ids: []\n          object_ids: []\n          prompt: |\n            画面内テキストなし。\n          output: \"assets/scenes/scene01.png\"\n        video_generation:\n          tool: \"kling_3_0\"\n          duration_seconds: 5\n          output: \"assets/scenes/scene01.mp4\"\n        audio:\n          narration:\n            text: \"桃太郎が歩く。\"\n            tool: \"elevenlabs\"\n            output: \"assets/audio/scene01.mp3\"\n```\n", encoding="utf-8")
            _write_downstream_generation_artifacts(run_dir)
            _write_image_request(run_dir, selector="scene01_cut1", output="assets/scenes/scene01.png")
            _write_photo_like_test_png(run_dir / "assets" / "scenes" / "scene01.png")
            (run_dir / "assets" / "audio" / "scene01.mp3").write_bytes(b"audio")
            (run_dir / "video.mp4").write_bytes(b"placeholder")
            _resolve_ready_grounding(run_dir, flow="immersive")
            (run_dir / "logs" / "grounding" / "script.readset.json").unlink()

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "verify-pipeline.py"),
                    "--run-dir",
                    str(run_dir),
                    "--flow",
                    "immersive",
                    "--profile",
                    "fast",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
