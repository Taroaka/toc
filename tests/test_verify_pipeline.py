import json
import subprocess
import sys
import unittest
from pathlib import Path

class TestVerifyPipeline(unittest.TestCase):
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
                        "conflicts: []",
                        "metadata:",
                        "  confidence_score: 0.9",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            (run_dir / "story.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "selection:",
                        "  candidates:",
                        "    - candidate_id: \"A\"",
                        "      logline: \"王道冒険\"",
                        "      why_it_scores: [\"clear\"]",
                        "      score_hint:",
                        "        engagement: 0.9",
                        "        coherence: 0.9",
                        "        production_fit: 0.9",
                        "      requires_hybridization_approval: false",
                        "    - candidate_id: \"B\"",
                        "      logline: \"別視点\"",
                        "      why_it_scores: [\"fresh\"]",
                        "      score_hint:",
                        "        engagement: 0.8",
                        "        coherence: 0.8",
                        "        production_fit: 0.8",
                        "      requires_hybridization_approval: false",
                        "  chosen_candidate_id: \"A\"",
                        "  rationale: \"一番安定している\"",
                        "hybridization:",
                        "  approval_status: \"not_needed\"",
                        "script:",
                        "  scenes:",
                        "    - scene_id: 1",
                        "      phase: \"opening\"",
                        "      narration: \"桃太郎が旅立つ\"",
                        "      visual: \"川辺\"",
                        "      research_refs: [\"research.story_baseline.beat_sheet[0]\"]",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

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
                        "          tool: \"google_nanobanana_pro\"",
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

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/verify-pipeline.py",
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
                        "conflicts: []",
                        "metadata:",
                        "  confidence_score: 0.9",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "story.md").write_text(
                "```yaml\nselection:\n  candidates:\n    - candidate_id: \"A\"\n      logline: \"竜宮城の誘惑\"\n      why_it_scores: [\"visual\"]\n      score_hint:\n        engagement: 0.9\n        coherence: 0.9\n        production_fit: 0.9\n      requires_hybridization_approval: false\n    - candidate_id: \"B\"\n      logline: \"地上の郷愁\"\n      why_it_scores: [\"contrast\"]\n      score_hint:\n        engagement: 0.8\n        coherence: 0.8\n        production_fit: 0.8\n      requires_hybridization_approval: false\n  chosen_candidate_id: \"A\"\n  rationale: \"中盤の価値が強い\"\nhybridization:\n  approval_status: \"not_needed\"\nscript:\n  scenes:\n    - scene_id: 1\n      phase: \"opening\"\n      narration: \"浦島太郎が海へ向かう\"\n      visual: \"浜辺\"\n      research_refs: [\"research.story_baseline.beat_sheet[0]\"]\n```\n",
                encoding="utf-8",
            )
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
                        "          tool: \"google_nanobanana_pro\"",
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

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/verify-pipeline.py",
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
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads((run_dir / "eval_report.json").read_text(encoding="utf-8"))
            self.assertTrue(payload["overall"]["passed"], msg=payload)


if __name__ == "__main__":
    unittest.main()
