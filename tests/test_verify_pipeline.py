import json
import importlib.util
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


def _good_story_yaml(topic: str = "桃太郎") -> str:
    scene_lines: list[str] = []
    for i in range(1, 21):
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
            "  rationale: \"20 scene の展開に最も安定して接続できる\"",
            "hybridization:",
            "  approval_status: \"not_needed\"",
            "script:",
            "  scenes:",
            *scene_lines,
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


def _resolve_ready_grounding(run_dir: Path, *, flow: str) -> None:
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.story.status": "approved",
            "review.image.status": "approved",
            "review.narration.status": "approved",
            "review.duration_fit.status": "passed",
        },
    )
    for stage in ["research", "story", "script", "image_prompt", "video_generation"]:
        result = _run_grounding(run_dir, stage, flow=flow)
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)


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
                        "          tool: \"google_nanobanana_2\"",
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
                        "          tool: \"google_nanobanana_2\"",
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
                        "          tool: \"google_nanobanana_2\"",
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
            (run_dir / "video_manifest.md").write_text("```yaml\nvideo_metadata:\n  topic: \"桃太郎\"\n  experience: \"cinematic_story\"\nscenes:\n  - scene_id: 1\n    cuts:\n      - cut_id: 1\n        cut_role: \"main\"\n        image_generation:\n          tool: \"google_nanobanana_2\"\n          character_ids: []\n          object_ids: []\n          prompt: |\n            画面内テキストなし。\n          output: \"assets/scenes/scene01.png\"\n        video_generation:\n          tool: \"kling_3_0\"\n          duration_seconds: 5\n          output: \"assets/scenes/scene01.mp4\"\n        audio:\n          narration:\n            text: \"桃太郎が歩く。\"\n            tool: \"elevenlabs\"\n            output: \"assets/audio/scene01.mp3\"\n```\n", encoding="utf-8")
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
