from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"
SPEC = importlib.util.spec_from_file_location("generate_assets_from_manifest", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _make_p400_ready_for_request_preview(run_dir: Path) -> None:
    manifest_path = run_dir / "video_manifest.md"
    data = MODULE.yaml.safe_load(MODULE.extract_yaml_block(manifest_path.read_text(encoding="utf-8"))) if MODULE.yaml is not None else {}
    if not isinstance(data, dict):
        data = {}
    initial_metadata = data.get("video_metadata") if isinstance(data.get("video_metadata"), dict) else {}
    if str(initial_metadata.get("experience") or "").strip().lower().startswith("asset_stage"):
        with (run_dir / "state.txt").open("a", encoding="utf-8") as f:
            f.write("eval.p400_readiness.status=approved\n---\n")
        return
    existing_script = {}
    existing_script_path = run_dir / "script.md"
    if existing_script_path.exists():
        existing_script = MODULE.yaml.safe_load(MODULE.extract_yaml_block(existing_script_path.read_text(encoding="utf-8"))) if MODULE.yaml is not None else {}
        if not isinstance(existing_script, dict):
            existing_script = {}
    existing_cut_lookup = {}
    existing_scenes = existing_script.get("scenes")
    if not existing_scenes and isinstance(existing_script.get("script"), dict):
        existing_scenes = existing_script["script"].get("scenes")
    for existing_scene in existing_scenes if isinstance(existing_scenes, list) else []:
        if not isinstance(existing_scene, dict):
            continue
        for existing_cut in existing_scene.get("cuts", []) if isinstance(existing_scene.get("cuts"), list) else []:
            if isinstance(existing_cut, dict):
                existing_cut_lookup[(str(existing_scene.get("scene_id")), str(existing_cut.get("cut_id")))] = existing_cut
    data["manifest_phase"] = "production"
    metadata = data.setdefault("video_metadata", {})
    if isinstance(metadata, dict):
        metadata.setdefault("topic", "request preview")
        metadata.setdefault("experience", "cinematic_story")
        metadata["target_duration_seconds"] = 300
    scenes = data.setdefault("scenes", [])
    if not isinstance(scenes, list):
        scenes = []
        data["scenes"] = scenes
    if not scenes:
        scenes.append({"scene_id": 1, "cuts": []})

    total_duration = 0
    script_scenes: list[dict] = []
    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("scene_id", scene_index)
        if str(scene.get("kind") or "").strip().lower() in {"reference", "character_reference"}:
            continue
        cuts = scene.setdefault("cuts", [])
        if not isinstance(cuts, list):
            cuts = []
            scene["cuts"] = cuts
        while len([cut for cut in cuts if isinstance(cut, dict) and str(cut.get("cut_status") or "").lower() != "deleted"]) < 2:
            cuts.append(
                {
                    "cut_id": len(cuts) + 1,
                    "scene_contract": {
                        "target_beat": "request preview filler",
                        "must_show": ["request preview"],
                        "must_avoid": [],
                        "done_when": ["request preview cut is present"],
                    },
                    "image_generation": {
                        "tool": "codex_builtin_image",
                        "prompt": "画面内テキストなし。実写映画風の村道、人物、道具、背景、光、足元、空気感が具体的に見える。",
                        "character_ids": [],
                        "object_ids": [],
                        "output": f"assets/scenes/scene{scene_id}_p400_filler_{len(cuts) + 1}.png",
                    },
                    "video_generation": {
                        "tool": "kling_3_0",
                        "duration_seconds": 15,
                        "motion_prompt": "人物がゆっくり前へ進む。",
                        "output": f"assets/videos/scene{scene_id}_p400_filler_{len(cuts) + 1}.mp4",
                    },
                    "audio": {"narration": {"tool": "elevenlabs", "text": "場面が続く。", "output": f"assets/audio/scene{scene_id}_p400_filler_{len(cuts) + 1}.mp3"}},
                }
            )
        script_cuts = []
        for cut_index, cut in enumerate(cuts, start=1):
            if not isinstance(cut, dict) or str(cut.get("cut_status") or "").lower() == "deleted":
                continue
            cut_id = cut.get("cut_id", cut_index)
            video_generation = cut.setdefault("video_generation", {})
            if isinstance(video_generation, dict):
                video_generation["duration_seconds"] = 15
                video_generation.setdefault("motion_prompt", "人物がゆっくり前へ進む。")
                total_duration += 15
            image_generation = cut.setdefault("image_generation", {})
            if isinstance(image_generation, dict):
                image_generation.setdefault("prompt", "画面内テキストなし。実写映画風の具体的な人物、場所、道具、光が見える。")
                image_generation.setdefault("character_ids", [])
                image_generation.setdefault("object_ids", [])
            cut.setdefault(
                "scene_contract",
                {
                    "target_beat": "request preview",
                    "must_show": ["request preview"],
                    "must_avoid": [],
                    "done_when": ["request preview cut is present"],
                },
            )
            contract = cut.get("scene_contract") if isinstance(cut.get("scene_contract"), dict) else {}
            prompt_terms = [str(contract.get("target_beat") or "request preview")]
            prompt_terms.extend(str(item) for item in contract.get("must_show", []) if str(item).strip())
            if isinstance(image_generation, dict):
                current_prompt = str(image_generation.get("prompt") or "")
                image_generation["prompt"] = (
                    current_prompt
                    + " 画面内テキストなし。"
                    + "、".join(prompt_terms)
                    + "、人物、場所、道具、背景、光、足元、空気感が具体的に見える。"
                )
            cut.setdefault("audio", {"narration": {"tool": "elevenlabs", "text": "場面が続く。"}})
            narration = cut.get("audio", {}).get("narration") if isinstance(cut.get("audio"), dict) else None
            request_ids = []
            if isinstance(image_generation, dict):
                request_ids.extend(str(item) for item in image_generation.get("applied_request_ids", []) if str(item).strip())
            if isinstance(video_generation, dict):
                request_ids.extend(str(item) for item in video_generation.get("applied_request_ids", []) if str(item).strip())
            trace = cut.get("implementation_trace") if isinstance(cut.get("implementation_trace"), dict) else {}
            request_ids.extend(str(item) for item in trace.get("source_request_ids", []) if str(item).strip())
            request_ids = list(dict.fromkeys(request_ids))
            if isinstance(narration, dict) and request_ids:
                narration.setdefault("applied_request_ids", request_ids)
            existing_cut = existing_cut_lookup.get((str(scene_id), str(cut_id)), {})
            script_cut = {
                key: value
                for key, value in existing_cut.items()
                if key not in {"cut_blueprint"}
            } if isinstance(existing_cut, dict) else {}
            script_cut.update(
                {
                    "cut_id": cut_id,
                    "selector": cut.get("selector") or f"scene{scene_id}_cut{cut_id}",
                    "cut_blueprint": {
                        "cut_role": "main",
                        "duration_intent": "standard",
                        "target_beat": "request preview",
                        "must_show": ["request preview"],
                        "must_avoid": [],
                        "done_when": ["request preview cut is present"],
                        "visual_beat": "request preview",
                        "narration_role": "setup",
                        "asset_dependency_hint": {"character_ids": [], "object_ids": [], "location_ids": [], "reusable_still_candidates": []},
                    },
                }
            )
            script_cuts.append(
                script_cut
            )
        script_scenes.append(
            {
                "scene_id": scene_id,
                "phase": "development",
                "importance": "medium",
                "summary": "request preview 用の p400 readiness scene。",
                "target_duration_seconds": max(30, len(script_cuts) * 15),
                "estimated_duration_seconds": max(30, len(script_cuts) * 15),
                "handoff_to_next_scene": "次へつながる",
                "terminal_resolution": "preview 完了",
                "coverage_review": {
                    "audience_information_covered": True,
                    "visualizable_action_covered": True,
                    "next_scene_connection_checked": True,
                },
                "agent_review": {"status": "passed"},
                "cuts": script_cuts,
            }
        )

    filler_scene_id = 900
    while total_duration < 300:
        filler_cuts = []
        manifest_cuts = []
        for cut_id in (1, 2):
            total_duration += 15
            manifest_cuts.append(
                {
                    "cut_id": cut_id,
                    "scene_contract": {"target_beat": "filler", "must_show": ["filler"], "must_avoid": [], "done_when": ["filler is visible"]},
                    "image_generation": {
                        "tool": "codex_builtin_image",
                        "prompt": "画面内テキストなし。filler が見える。実写映画風の道、人物、背景、光、空気感、足元の動きが具体的に見える。",
                        "character_ids": [],
                        "object_ids": [],
                        "output": f"assets/scenes/scene{filler_scene_id}_cut{cut_id}.png",
                    },
                    "video_generation": {"tool": "kling_3_0", "duration_seconds": 15, "motion_prompt": "人物が進む。", "output": f"assets/videos/scene{filler_scene_id}_cut{cut_id}.mp4"},
                    "audio": {"narration": {"tool": "elevenlabs", "text": "場面が続く。", "output": f"assets/audio/scene{filler_scene_id}_cut{cut_id}.mp3"}},
                }
            )
            filler_cuts.append(
                {
                    "cut_id": cut_id,
                    "selector": f"scene{filler_scene_id}_cut{cut_id}",
                    "cut_blueprint": {
                        "cut_role": "main",
                        "duration_intent": "standard",
                        "target_beat": "filler",
                        "must_show": ["filler"],
                        "must_avoid": [],
                        "done_when": ["filler is visible"],
                        "visual_beat": "filler",
                        "narration_role": "setup",
                        "asset_dependency_hint": {"character_ids": [], "object_ids": [], "location_ids": [], "reusable_still_candidates": []},
                    },
                }
            )
        scenes.append({"scene_id": filler_scene_id, "cuts": manifest_cuts})
        script_scenes.append(
            {
                "scene_id": filler_scene_id,
                "phase": "development",
                "importance": "medium",
                "summary": "尺を満たす filler scene。",
                "target_duration_seconds": 30,
                "estimated_duration_seconds": 30,
                "handoff_to_next_scene": "次へつながる",
                "terminal_resolution": "preview 完了",
                "coverage_review": {
                    "audience_information_covered": True,
                    "visualizable_action_covered": True,
                    "next_scene_connection_checked": True,
                },
                "agent_review": {"status": "passed"},
                "cuts": filler_cuts,
            }
        )
        filler_scene_id += 1

    manifest_path.write_text("```yaml\n" + MODULE.yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "```\n", encoding="utf-8")
    (run_dir / "script.md").write_text(
        "```yaml\n"
        + MODULE.yaml.safe_dump(
            {
                "scene_set_review": {"status": "approved"},
                "scene_detail_review": {"status": "approved"},
                "cut_blueprint_review": {"status": "approved"},
                "scenes": script_scenes,
                "script": {"scenes": script_scenes},
            },
            allow_unicode=True,
            sort_keys=False,
        )
        + "```\n",
        encoding="utf-8",
    )
    for name in ("scene_set_review.md", "scene_detail_review.md", "cut_blueprint_review.md", "script_review.md"):
        (run_dir / name).write_text("status: passed\n\nreview passed\n", encoding="utf-8")
    (run_dir / "production_readiness_review.md").write_text("status: passed\n\nStructure: ok\nDuration: ok\nQuality: ok\nDesign Owner Patch Brief: ok\n", encoding="utf-8")
    for stage in ("scene_set", "scene_detail", "cut_blueprint", "script", "production_readiness"):
        round_dir = run_dir / "logs" / "eval" / stage / "round_01"
        round_dir.mkdir(parents=True, exist_ok=True)
        for index in range(1, 6):
            (round_dir / f"critic_{index}.md").write_text("status: passed\n\ncritic passed\n", encoding="utf-8")
        patch = "## Design Owner Patch Brief" if stage == "production_readiness" else "## Generator Patch Brief"
        (round_dir / "aggregated_review.md").write_text(
            "status: passed\n\n## Blocking Findings\nnone\n## Recommended Changes\nnone\n## Rejected Suggestions\nnone\n"
            + patch
            + "\nnone\n## Round Summary\npassed\n",
            encoding="utf-8",
        )
    with (run_dir / "state.txt").open("a", encoding="utf-8") as f:
        f.write("eval.p400_readiness.status=approved\n---\n")


class TestRequestPreviewPrompt(unittest.TestCase):
    def test_image_tool_aliases_normalize_to_codex_builtin_image(self) -> None:
        for tool in [
            "google_nanobanana_2",
            "nanobanana_2",
            "gemini_3_1_flash_image",
            "seadream",
            "seedream_4_5",
            "codex_app_server",
            "gpt-image-2",
        ]:
            with self.subTest(tool=tool):
                self.assertEqual(MODULE.normalize_tool_name(tool), "codex_builtin_image")

    def test_generation_requires_p400_readiness_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
manifest_phase: production
video_metadata:
  topic: "かぐや姫"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          tool: "codex_builtin_image"
          prompt: "画面内テキストなし。竹林の朝、光る竹、人物、足元の霧が見える。"
          output: "assets/scenes/scene01_1.png"
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 4
          output: "assets/videos/scene01_1.mp4"
        audio:
          narration:
            tool: "silent"
            text: ""
            tts_text: ""
            silence_contract:
              intentional: true
              kind: "visual_value_hold"
              confirmed_by_human: true
              reason: "draft"
            output: "assets/audio/scene01_1.mp3"
```
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-image-prompt-review",
                    "--skip-narration-review",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("p400 readiness gate is not approved", result.stderr)
            self.assertFalse((tmp_path / "image_generation_requests.md").exists())
            self.assertFalse((tmp_path / "video_generation_requests.md").exists())

    def test_p400_readiness_override_is_read_only_diagnostic_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
manifest_phase: production
video_metadata:
  topic: "かぐや姫"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          tool: "codex_builtin_image"
          prompt: "画面内テキストなし。竹林の朝、光る竹、人物、足元の霧が見える。"
          output: "assets/scenes/scene01_1.png"
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 4
          output: "assets/videos/scene01_1.mp4"
        audio:
          narration:
            tool: "silent"
            text: ""
            tts_text: ""
            silence_contract:
              intentional: true
              kind: "visual_value_hold"
              confirmed_by_human: true
              reason: "draft"
            output: "assets/audio/scene01_1.mp3"
```
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--ignore-p400-readiness-gate",
                    "--dry-run",
                    "--skip-images",
                    "--skip-videos",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                    "--skip-narration-review",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("readiness override diagnostic only", result.stdout)
            self.assertFalse((tmp_path / "image_generation_requests.md").exists())
            self.assertFalse((tmp_path / "asset_generation_requests.md").exists())
            self.assertFalse((tmp_path / "video_generation_requests.md").exists())
            self.assertFalse((tmp_path / "generation_exclusion_report.md").exists())

            materialize_result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--ignore-p400-readiness-gate",
                    "--dry-run",
                    "--skip-images",
                    "--skip-videos",
                    "--skip-audio",
                    "--materialize-request-files-only",
                    "--skip-image-prompt-review",
                    "--skip-narration-review",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(materialize_result.returncode, 0)
            self.assertIn("read-only diagnostics", materialize_result.stderr)
            self.assertFalse((tmp_path / "image_generation_requests.md").exists())
            self.assertFalse((tmp_path / "video_generation_requests.md").exists())
            self.assertFalse((tmp_path / "generation_exclusion_report.md").exists())

    def test_skeleton_manifest_does_not_materialize_scene_or_video_request_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
manifest_phase: skeleton
video_metadata:
  topic: "かぐや姫"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
          generation_status: planned
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene01_1.png"
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 4
          output: "assets/videos/scene01_1.mp4"
        audio:
          narration:
            tool: "silent"
            text: ""
            tts_text: ""
            silence_contract:
              intentional: true
              kind: "visual_value_hold"
              confirmed_by_human: true
              reason: "draft"
            output: "assets/audio/scene01_1.mp3"
```
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--skip-images",
                    "--skip-videos",
                    "--dry-run",
                    "--skip-image-prompt-review",
                    "--skip-narration-review",
                ],
                check=False,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("p400 readiness gate is not approved", result.stderr)
            self.assertFalse((tmp_path / "image_generation_requests.md").exists())
            self.assertFalse((tmp_path / "video_generation_requests.md").exists())
            self.assertFalse((tmp_path / "generation_exclusion_report.md").exists())

    def test_skeleton_manifest_fails_before_scene_review_can_mutate_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            original_manifest = """# Manifest

```yaml
manifest_phase: skeleton
video_metadata:
  topic: "かぐや姫"
scenes:
  - scene_id: 1
    image_generation:
      tool: "codex_builtin_image"
      prompt: "かぐや姫"
      output: "assets/scenes/scene01.png"
    video_generation:
      tool: "kling_3_0"
      duration_seconds: 4
      output: "assets/videos/scene01.mp4"
    audio:
      narration:
        tool: "silent"
        text: ""
        tts_text: ""
        silence_contract:
          intentional: true
          kind: "visual_value_hold"
          confirmed_by_human: true
          reason: "draft"
        output: "assets/audio/scene01.mp3"
```
"""
            manifest_path.write_text(original_manifest, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--skip-videos",
                    "--dry-run",
                    "--image-prompt-review-fix-character-ids",
                    "--skip-narration-review",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("p400 readiness gate is not approved", result.stderr + result.stdout)
            self.assertEqual(manifest_path.read_text(encoding="utf-8"), original_manifest)

    def test_rewrites_stateful_character_asset_wording(self) -> None:
        prompt = """[登場人物]
浦島太郎の参照画像（以後のsceneで一貫性を保つため）。

[小道具 / 舞台装置]
参照画像のため背景小道具は置かない。

[連続性]
後続sceneでも顔立ち、髪型、衣装の形、体格比率を変えないための基準画像にする。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/characters/urashima.png",
            references=[],
            topic="浦島太郎",
        )
        self.assertIn("浦島太郎のキャラクター基準画像。", rewritten)
        self.assertIn("基準画像のため背景小道具は置かない。", rewritten)
        self.assertIn("顔立ち、髪型、衣装の形、体格比率を読み取れる基準画像にする。", rewritten)
        self.assertNotIn("物語「浦島太郎」", rewritten)
        self.assertNotIn("後続scene", rewritten)
        self.assertNotIn("以後のscene", rewritten)
        self.assertNotIn("この cut", rewritten)

    def test_rewrites_reference_usage_for_cut_requests(self) -> None:
        prompt = """[登場人物]
参照画像と完全一致（顔、髪型、衣装、甲羅パターン）。

[小道具 / 舞台装置]
連続性アンカー: 海亀の甲羅の模様、朝の光の方向、波の質感。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene01_cut01.png",
            references=["assets/characters/urashima.png", "assets/characters/turtle.png"],
            topic="浦島太郎",
        )
        self.assertIn("参照画像に写っている顔、髪型、衣装、甲羅パターンをこの場面でも維持する。", rewritten)
        self.assertIn("参照画像に写っている海亀の甲羅の模様、朝の光の方向、波の質感を、この場面の画面内でも維持する。", rewritten)
        self.assertNotIn("この画像は物語", rewritten)
        self.assertNotIn("物語「浦島太郎」", rewritten)
        self.assertNotIn("連続性アンカー", rewritten)
        self.assertNotIn("この cut", rewritten)

    def test_removes_nonvisual_story_scene_metadata_from_request_prompt(self) -> None:
        prompt = """[全体 / 不変条件]
物語「シンデレラ」の scene10。実写映画風、横長16:9。

[シーン]
灰の残る古い台所で、シンデレラが暖炉の灰を掃いている。

[連続性]
scene10 の灰の台所と同じ床。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene10_ash_kitchen.png",
            references=[],
            topic="シンデレラ",
        )
        self.assertIn("灰の残る古い台所", rewritten)
        self.assertIn("シンデレラが暖炉の灰を掃いている", rewritten)
        self.assertNotIn("物語「シンデレラ」", rewritten)
        self.assertNotIn("scene10", rewritten)
        self.assertNotIn("[物語の文脈]", rewritten)

    def test_removes_short_story_context_sentence_from_request_prompt(self) -> None:
        prompt = """[物語の文脈]
この画像は物語「シンデレラ」の一場面。

[シーン]
灰の残る古い台所で、シンデレラが暖炉の灰を掃いている。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene10_ash_kitchen.png",
            references=[],
            topic="シンデレラ",
        )
        self.assertIn("灰の残る古い台所", rewritten)
        self.assertNotIn("この画像は物語", rewritten)
        self.assertNotIn("[物語の文脈]", rewritten)

    def test_removes_first_frame_authoring_metadata_from_request_prompt(self) -> None:
        prompt = """[シーン]
この画像は動画の最初の1フレームとして使う。王宮階段の手前にガラスの靴があり、奥で王子が手を伸ばす直前。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene50_cut01.png",
            references=[],
            topic="シンデレラ",
        )
        self.assertIn("王宮階段の手前にガラスの靴", rewritten)
        self.assertNotIn("最初の1フレーム", rewritten)
        self.assertNotIn("1フレーム目", rewritten)

    def test_removes_stateful_next_cut_language_from_request(self) -> None:
        prompt = """[連続性]
この cut 単体で、太郎が宴の最中に故郷を思い出しはじめたと分かるようにする。次の cut で太郎が帰りたいと言い出しても不自然にならない感情の橋渡しにする。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene08_cut01.png",
            references=["assets/characters/urashima.png"],
            topic="浦島太郎",
        )
        self.assertIn("この画像だけで、太郎が宴の最中に故郷を思い出しはじめたと分かるようにする。", rewritten)
        self.assertNotIn("次の cut", rewritten)
        self.assertNotIn("感情の橋渡し", rewritten)

    def test_drops_reference_section_when_references_are_empty(self) -> None:
        prompt = """[シーン]
海底神殿の奥に、まだ動いていない巨大な砂時計がある。

[参照画像の使い方]
参照画像は使わない。

[禁止]
文字なし。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene03_7_cut01.png",
            references=[],
            topic="浦島太郎",
        )
        self.assertNotIn("[参照画像の使い方]", rewritten)
        self.assertNotIn("参照画像は使わない。", rewritten)

    def test_relabels_reference_paths_in_prompt_body(self) -> None:
        prompt = """[参照画像の使い方]
`assets/characters/urashima.png` は顔立ちの基準として使う。`assets/characters/urashima_refstrip.png` は側面確認に使う。`assets/locations/banquet_hall_main.png` は空間構成の基準として使う。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene07_cut01.png",
            references=[
                "assets/characters/urashima.png",
                "assets/characters/urashima_refstrip.png",
                "assets/locations/banquet_hall_main.png",
            ],
            topic="浦島太郎",
        )
        self.assertIn("人物参照画像1", rewritten)
        self.assertIn("人物参照画像2", rewritten)
        self.assertIn("場所参照画像1", rewritten)
        self.assertNotIn("assets/characters/urashima.png", rewritten)
        self.assertNotIn("assets/locations/banquet_hall_main.png", rewritten)

    def test_materialized_requests_include_reuse_and_bridge_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
          generation_status: created
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene01_1.png"
      - cut_id: 2
        still_image_plan:
          mode: reuse_anchor
          generation_status: recreate
          source: "scene01_cut01"
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p2"
          output: "assets/scenes/scene01_2.png"
      - cut_id: 3
        still_image_plan:
          mode: no_dedicated_still
          source: "motion chain: scene01_cut01 -> scene02_cut01"
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p3"
          output: "assets/scenes/scene01_3.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertTrue((tmp_path / "p000_index.md").exists())
            self.assertIn("## scene1_cut2", request_text)
            self.assertIn("- authoring_role: `video_first_frame_candidate`", request_text)
            self.assertIn("prompt本文には「最初の1フレーム」等を書かず", request_text)
            self.assertIn("- still_mode: `reuse_anchor`", request_text)
            self.assertIn("- generation_status: `recreate`", request_text)
            self.assertIn("- plan_source: `scene01_cut01`", request_text)
            self.assertIn("## scene1_cut3", request_text)
            self.assertIn("- still_mode: `no_dedicated_still`", request_text)
            self.assertIn("motion chain: scene01_cut01 -> scene02_cut01", request_text)

    def test_recreate_archives_existing_image_to_test_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            image_path = tmp_path / "assets" / "scenes" / "scene01_1.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(b"old-image")

            MODULE._archive_existing_image_for_recreate(
                out_path=image_path,
                base_dir=tmp_path,
                test_image_dir="assets/test",
            )

            self.assertFalse(image_path.exists())
            archived = list((tmp_path / "assets" / "test").glob("scene01_1__recreate_backup_*.png"))
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0].read_bytes(), b"old-image")

    def test_resolve_image_reference_paths_uses_archived_self_reference_when_output_was_moved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archived_path = tmp_path / "assets" / "test" / "scene01_cut01__recreate_backup.png"
            archived_path.parent.mkdir(parents=True, exist_ok=True)
            archived_path.write_bytes(b"old-image")

            refs = MODULE._resolve_image_reference_paths(
                base_dir=tmp_path,
                reference_strings=["assets/scenes/scene01_cut01.png"],
                output_ref="assets/scenes/scene01_cut01.png",
                archived_self_reference_path=archived_path,
                test_image_dir="assets/test",
                dry_run=False,
                scene_selector="scene1_cut1",
            )

            self.assertEqual(refs, [archived_path])

    def test_resolve_image_reference_paths_finds_latest_backup_for_missing_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive_dir = tmp_path / "assets" / "test"
            archive_dir.mkdir(parents=True, exist_ok=True)
            older = archive_dir / "scene01_cut01__recreate_backup_20260412_100000.png"
            newer = archive_dir / "scene01_cut01__recreate_backup_20260412_110000.png"
            older.write_bytes(b"old")
            newer.write_bytes(b"new")

            refs = MODULE._resolve_image_reference_paths(
                base_dir=tmp_path,
                reference_strings=["assets/scenes/scene01_cut01.png"],
                output_ref="assets/scenes/scene01_cut01.png",
                archived_self_reference_path=None,
                test_image_dir="assets/test",
                dry_run=False,
                scene_selector="scene1_cut1",
            )

            self.assertEqual(refs, [newer])

    def test_materialized_requests_include_resolved_asset_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            (tmp_path / "assets" / "characters").mkdir(parents=True, exist_ok=True)
            (tmp_path / "assets" / "objects").mkdir(parents=True, exist_ok=True)
            (tmp_path / "assets" / "locations").mkdir(parents=True, exist_ok=True)
            for rel in [
                "assets/characters/urashima.png",
                "assets/objects/tamatebako.png",
                "assets/locations/banquet_hall_main.png",
            ]:
                (tmp_path / rel).write_bytes(b"x")
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
assets:
  character_bible:
    - character_id: urashima
      reference_images: ["assets/characters/urashima.png"]
  object_bible:
    - object_id: tamatebako
      reference_images: ["assets/objects/tamatebako.png"]
      fixed_prompts: ["box"]
  location_bible:
    - location_id: banquet_hall_main
      reference_images: ["assets/locations/banquet_hall_main.png"]
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          character_ids: ["urashima"]
          object_ids: ["tamatebako"]
          location_ids: ["banquet_hall_main"]
          prompt: "p1"
          output: "assets/scenes/scene01_1.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertTrue((tmp_path / "p000_index.md").exists())
            self.assertIn("`人物参照画像1`: `assets/characters/urashima.png`", request_text)
            self.assertIn("`小道具参照画像1`: `assets/objects/tamatebako.png`", request_text)
            self.assertIn("`場所参照画像1`: `assets/locations/banquet_hall_main.png`", request_text)

    def test_asset_generation_requests_include_bootstrap_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
  experience: "asset_stage"
scenes:
  - scene_id: 0
    still_assets:
      - asset_id: "urashima_seed"
        asset_type: "character_reference"
        source_script_selectors: ["scene1_cut1"]
        output: "assets/characters/urashima_seed.png"
        creation_status: "planned"
        generation_plan:
          required_views: ["front", "side", "back"]
        review:
          status: "pending"
        image_generation:
          tool: "codex_builtin_image"
          execution_lane: "bootstrap_builtin"
          bootstrap_allowed: true
          bootstrap_reason: "no_reference_seed"
          prompt: "浦島太郎の seed"
          output: "assets/characters/urashima_seed.png"
          references: []
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "asset_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("- tool: `codex_builtin_image`", request_text)
            self.assertNotIn("google_nanobanana_2", request_text)
            self.assertIn("- asset_id: `urashima_seed`", request_text)
            self.assertIn("- asset_type: `character_reference`", request_text)
            self.assertIn("- execution_lane: `bootstrap_builtin`", request_text)
            self.assertIn("- reference_count: `0`", request_text)
            self.assertIn("- review_status: `pending`", request_text)
            self.assertIn("- creation_status: `planned`", request_text)
            self.assertIn("- authoring_role: `reusable_asset_candidate`", request_text)
            self.assertIn("prompt本文には物語タイトルやscene idを書かず", request_text)
            self.assertNotIn("video_first_frame_candidate", request_text)
            self.assertNotIn("最初の1フレーム", request_text)
            self.assertIn("- bootstrap_allowed: `true`", request_text)
            self.assertIn("- bootstrap_reason: `no_reference_seed`", request_text)
            self.assertIn("- source_script_selectors:", request_text)
            self.assertIn("  - `scene1_cut1`", request_text)
            self.assertIn("- required_views:", request_text)
            self.assertIn("  - `front`", request_text)
            self.assertIn("  - `side`", request_text)
            self.assertIn("  - `back`", request_text)
            self.assertIn("- output: `assets/characters/urashima_seed.png`", request_text)

    def test_image_generation_requests_include_lane_and_reference_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            (tmp_path / "assets" / "characters").mkdir(parents=True, exist_ok=True)
            (tmp_path / "assets" / "characters" / "urashima.png").write_bytes(b"x")
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: "generate_still"
        image_generation:
          tool: "codex_builtin_image"
          prompt: "浜辺の establishing shot"
          references: []
          output: "assets/scenes/scene1_cut1.png"
      - cut_id: 2
        image_generation:
          tool: "codex_builtin_image"
          prompt: "浦島太郎の中景"
          references:
            - "assets/characters/urashima.png"
          output: "assets/scenes/scene1_cut2.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("## scene1_cut1", request_text)
            self.assertIn("## scene1_cut2", request_text)
            self.assertIn("- tool: `codex_builtin_image`", request_text)
            self.assertNotIn("google_nanobanana_2", request_text)
            self.assertIn("- execution_lane: `bootstrap_builtin`", request_text)
            self.assertIn("- reference_count: `0`", request_text)
            self.assertIn("- execution_lane: `standard`", request_text)
            self.assertIn("- reference_count: `1`", request_text)

    def test_generation_keeps_no_reference_requests_on_bootstrap_lane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: "generate_still"
        image_generation:
          tool: "codex_builtin_image"
          prompt: "浜辺の establishing shot"
          references: []
          output: "assets/scenes/scene1_cut1.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--dry-run",
                    "--skip-audio",
                    "--skip-videos",
                    "--skip-image-prompt-review",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("codex_builtin_image", completed.stdout)
            self.assertIn("refs=0", completed.stdout)

    def test_materialized_requests_preserve_explicit_scene_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            (tmp_path / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
            (tmp_path / "assets" / "objects").mkdir(parents=True, exist_ok=True)
            for rel in [
                "assets/scenes/scene01_cut01.png",
                "assets/objects/tamatebako.png",
            ]:
                (tmp_path / rel).write_bytes(b"x")
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
assets:
  object_bible:
    - object_id: tamatebako
      reference_images: ["assets/objects/tamatebako.png"]
      fixed_prompts: ["box"]
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          object_ids: ["tamatebako"]
          references: ["assets/scenes/scene01_cut01.png"]
          prompt: "参照画像1の構図を維持し、玉手箱だけを直す。"
          output: "assets/scenes/scene01_cut01.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("`参照画像1`: `assets/scenes/scene01_cut01.png`", request_text)
            self.assertIn("`小道具参照画像1`: `assets/objects/tamatebako.png`", request_text)

    def test_build_image_scene_dependencies_tracks_inter_scene_refs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          references: ["assets/scenes/scene01_cut01.png"]
          prompt: "p1"
          output: "assets/scenes/scene01_cut01.png"
      - cut_id: 2
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          references: ["assets/scenes/scene01_cut01.png"]
          prompt: "p2"
          output: "assets/scenes/scene01_cut02.png"
      - cut_id: 3
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          references: []
          prompt: "p3"
          output: "assets/scenes/scene01_cut03.png"
```
""",
                encoding="utf-8",
            )

            metadata, guides, scenes = MODULE.parse_manifest_yaml_full(MODULE.extract_yaml_block(manifest_path.read_text(encoding="utf-8")))
            deps = MODULE._build_image_scene_dependencies(scenes)

            self.assertEqual(deps["scene1_cut1"], set())
            self.assertEqual(deps["scene1_cut2"], {"scene1_cut1"})
            self.assertEqual(deps["scene1_cut3"], set())

    def test_materialized_requests_include_source_requests_for_image_and_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
human_change_requests:
  - request_id: "hr-001"
    status: verified
    raw_request: "scene1_cut1 の玉手箱を asset に合わせて直す。"
    resolution_notes: "箱の見た目を黒漆と金意匠に統一"
  - request_id: "hr-002"
    status: verified
    raw_request: "scene1_cut1 の人物を老いた浦島太郎に直す。"
    resolution_notes: ""
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        implementation_trace:
          source_request_ids: ["hr-001", "hr-002"]
          status: implemented
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene01_cut01.png"
          applied_request_ids: ["hr-002", "hr-001"]
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m1"
          output: "assets/videos/scene01_cut01.mp4"
          applied_request_ids: ["hr-001", "hr-002"]
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            image_request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            video_request_text = (tmp_path / "video_generation_requests.md").read_text(encoding="utf-8")

            self.assertIn("- source_requests:", image_request_text)
            self.assertIn("`hr-002`: scene1_cut1 の人物を老いた浦島太郎に直す。", image_request_text)
            self.assertIn(
                "`hr-001`: scene1_cut1 の玉手箱を asset に合わせて直す。 (resolution_notes: 箱の見た目を黒漆と金意匠に統一)",
                image_request_text,
            )
            self.assertLess(image_request_text.index("`hr-002`"), image_request_text.index("`hr-001`"))

            self.assertIn("- source_requests:", video_request_text)
            self.assertIn("`hr-001`: scene1_cut1 の玉手箱を asset に合わせて直す。", video_request_text)
            self.assertRegex(video_request_text, r"- duration_seconds: `\d+`")
            self.assertIn("- aspect_ratio: `9:16`", video_request_text)
            self.assertIn("- resolution: `1080p`", video_request_text)
            self.assertIn("`hr-002`: scene1_cut1 の人物を老いた浦島太郎に直す。", video_request_text)
            self.assertLess(video_request_text.index("`hr-001`"), video_request_text.index("`hr-002`"))

    def test_materialized_requests_omit_source_requests_without_applied_request_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
human_change_requests:
  - request_id: "hr-001"
    status: verified
    raw_request: "scene1_cut1 を直す。"
    resolution_notes: ""
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene01_cut01.png"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m1"
          output: "assets/videos/scene01_cut01.mp4"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            image_request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            video_request_text = (tmp_path / "video_generation_requests.md").read_text(encoding="utf-8")

            self.assertNotIn("- source_requests:", image_request_text)
            self.assertNotIn("- source_requests:", video_request_text)

    def test_materialized_video_requests_support_render_units_with_source_cuts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene03_cut01.png"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m1"
          output: "assets/videos/scene03_cut01.mp4"
        audio:
          narration:
            tool: "elevenlabs"
            text: "n1"
            tts_text: "n1"
            output: "assets/audio/scene03_cut01_narration.mp3"
      - cut_id: 2
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p2"
          output: "assets/scenes/scene03_cut02.png"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m2"
          output: "assets/videos/scene03_cut02.mp4"
        audio:
          narration:
            tool: "elevenlabs"
            text: "n2"
            tts_text: "n2"
            output: "assets/audio/scene03_cut02_narration.mp3"
      - cut_id: 3
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p3"
          output: "assets/scenes/scene03_cut03.png"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m3"
          output: "assets/videos/scene03_cut03.mp4"
        audio:
          narration:
            tool: "elevenlabs"
            text: "n3"
            tts_text: "n3"
            output: "assets/audio/scene03_cut03_narration.mp3"
    render_units:
      - unit_id: 1
        source_cut_ids: [1]
        video_generation:
          tool: "kling_3_0_omni"
          duration_seconds: 8
          first_frame: "assets/scenes/scene03_cut01.png"
          motion_prompt: "unit1"
          output: "assets/videos/scene03_cut01.mp4"
      - unit_id: 2
        source_cut_ids: [2, 3]
        video_generation:
          tool: "kling_3_0_omni"
          duration_seconds: 11
          first_frame: "assets/scenes/scene03_cut02.png"
          motion_prompt: "unit2"
          output: "assets/videos/scene03_cut02.mp4"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            video_request_text = (tmp_path / "video_generation_requests.md").read_text(encoding="utf-8")

            self.assertIn("## scene3_unit1", video_request_text)
            self.assertIn("## scene3_unit2", video_request_text)
            self.assertIn("- source_cuts:", video_request_text)
            self.assertIn("`scene3_cut2`", video_request_text)
            self.assertIn("`scene3_cut3`", video_request_text)
            self.assertNotIn("## scene3_cut3", video_request_text)

    def test_validate_human_change_requests_rejects_unknown_applied_request_ids(self) -> None:
        manifest = {
            "human_change_requests": [
                {
                    "request_id": "hr-001",
                    "status": "verified",
                    "raw_request": "scene1_cut1 を直す。",
                }
            ],
            "scenes": [
                {
                    "scene_id": "1",
                    "cuts": [
                        {
                            "cut_id": "1",
                            "implementation_trace": {
                                "source_request_ids": ["hr-001"],
                                "status": "implemented",
                            },
                            "image_generation": {
                                "tool": "codex_builtin_image",
                                "prompt": "p1",
                                "output": "assets/scenes/scene01_cut01.png",
                                "applied_request_ids": ["hr-999"],
                            },
                        }
                    ],
                }
            ],
        }

        with self.assertRaises(SystemExit) as ctx:
            MODULE.validate_human_change_requests(manifest=manifest, scene_filter=None)

        self.assertIn("unknown human_change_request id(s) in image_generation", str(ctx.exception))

    def test_validate_human_change_requests_rejects_unknown_render_unit_request_ids(self) -> None:
        manifest = {
            "human_change_requests": [
                {
                    "request_id": "hr-001",
                    "status": "verified",
                    "raw_request": "scene3_unit2 を直す。",
                }
            ],
            "scenes": [
                {
                    "scene_id": "3",
                    "cuts": [
                        {"cut_id": "1"},
                        {"cut_id": "2"},
                    ],
                    "render_units": [
                        {
                            "unit_id": "2",
                            "source_cut_ids": ["1", "2"],
                            "video_generation": {
                                "tool": "kling_3_0_omni",
                                "motion_prompt": "m",
                                "output": "assets/videos/scene03_cut02.mp4",
                                "applied_request_ids": ["hr-999"],
                            },
                        }
                    ],
                }
            ],
        }

        with self.assertRaises(SystemExit) as ctx:
            MODULE.validate_human_change_requests(manifest=manifest, scene_filter=None)

        self.assertIn("render_units.video_generation", str(ctx.exception))

    def test_scene7_onward_request_prefers_script_visual_beat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            script_path = tmp_path / "script.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 7
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          prompt: "既存の prompt"
          output: "assets/scenes/scene07_cut01.png"
```
""",
                encoding="utf-8",
            )
            script_path.write_text(
                """# Script

```yaml
scenes:
  - scene_id: 7
    cuts:
      - cut_id: 1
        visual_beat: "宴会エリアで楽しむ他のキャラクターたちに囲まれる中、頭をかかえる浦島太郎。"
        human_review:
          approved_visual_beat: "竜宮城の宴会エリアで楽しむ他のキャラクターたちに囲まれる中、頭をかかえる浦島太郎。"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("[場面の核]", request_text)
            self.assertIn("竜宮城の宴会エリアで楽しむ他のキャラクターたちに囲まれる中、頭をかかえる浦島太郎。", request_text)
            self.assertIn("既存の prompt", request_text)

    def test_deleted_cuts_are_excluded_from_requests_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 6
    cuts:
      - cut_id: 1
        cut_status: deleted
        deletion_reason: "story removal"
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene06_cut01.png"
        audio:
          narration:
            tool: "silent"
            text: ""
            output: "assets/audio/scene06_cut01_narration.mp3"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m1"
          output: "assets/videos/scene06_cut01.mp4"
      - cut_id: 2
        still_image_plan:
          mode: generate_still
          generation_status: created
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p2"
          output: "assets/scenes/scene06_cut02.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertNotIn("scene6_cut1", request_text)
            self.assertIn("scene6_cut2", request_text)
            self.assertTrue((tmp_path / "p000_index.md").exists())

            video_request_text = (tmp_path / "video_generation_requests.md").read_text(encoding="utf-8")
            self.assertNotIn("scene6_cut1", video_request_text)
            self.assertNotIn("scene06_cut01.mp4", video_request_text)

            exclusion_text = (tmp_path / "generation_exclusion_report.md").read_text(encoding="utf-8")
            self.assertIn("scene6_cut1", exclusion_text)
            self.assertIn("story removal", exclusion_text)
            self.assertIn("assets/videos/scene06_cut01.mp4", exclusion_text)
            self.assertIn("assets/audio/scene06_cut01_narration.mp3", exclusion_text)


if __name__ == "__main__":
    unittest.main()
