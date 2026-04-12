import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build-image-prompt-judgment-review.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import parse_state_file

SPEC = importlib.util.spec_from_file_location("build_image_prompt_judgment_review", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TestBuildImagePromptJudgmentReview(unittest.TestCase):
    def _write_manifest(self, run_dir: Path) -> Path:
        manifest = run_dir / "video_manifest.md"
        manifest.write_text(
            "\n".join(
                [
                    "# Manifest",
                    "",
                    "```yaml",
                    'video_metadata:',
                    '  topic: "テストトピック"',
                    "scenes:",
                    "  - scene_id: 1",
                    "    cuts:",
                    "      - cut_id: 1",
                    "        still_image_plan:",
                    "          mode: generate_still",
                    "          rationale: 参照静止画が必要",
                    "        image_generation:",
                    "          output: assets/scenes/scene01_cut01.png",
                    "          prompt: >-",
                    "            [全体 / 不変条件] 実写、シネマティック。",
                    "            [登場人物] かぐや姫。",
                    "            [小道具 / 舞台装置] 光る竹。",
                    "            [シーン] 竹林で発見の瞬間。",
                    "            [連続性] 次カットでも衣装を維持する。",
                    "            [禁止] ロゴ、字幕。",
                    "          contract:",
                    '            target_focus: "character"',
                    '            must_include: ["かぐや姫", "光る竹"]',
                    '            must_avoid: ["ロゴ"]',
                    '            done_when: ["発見の瞬間が読める"]',
                    "          review:",
                    "            agent_review_ok: true",
                    "            human_review_ok: false",
                    "            agent_review_reason_keys: []",
                    "            agent_review_reason_messages: []",
                    "            overall_score: 0.875",
                    "        audio:",
                    "          narration:",
                    '            text: "竹林で、ひときわ強く光る竹を見つける。"',
                    "```",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return manifest

    def test_build_prompt_includes_review_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_judgment_") as td:
            run_dir = Path(td) / "output" / "kaguya_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = self._write_manifest(run_dir)

            prompt = MODULE.build_judgment_prompt(
                run_dir=run_dir.resolve(),
                manifest_path=manifest_path.resolve(),
                scope_path=(run_dir / "logs" / "review" / "image_prompt.review_scope.json").resolve(),
                collection_path=(run_dir / "logs" / "review" / "image_prompt.review_collection.md").resolve(),
                report_path=(run_dir / "logs" / "review" / "image_prompt.judgment.md").resolve(),
            )

            self.assertIn("contextless, judgment-review subagent for image prompt quality", prompt)
            self.assertIn(str(manifest_path.resolve()), prompt)
            self.assertIn("image_prompt.review_collection.md", prompt)
            self.assertIn("image_prompt.judgment.md", prompt)
            self.assertIn("status: passed|failed", prompt)

    def test_cli_writes_review_pack_and_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_judgment_") as td:
            run_dir = Path(td) / "output" / "kaguya_20990101_0001"
            run_dir.mkdir(parents=True, exist_ok=True)
            self._write_manifest(run_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--run-dir",
                    str(run_dir),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)

            collection_path = run_dir / "logs" / "review" / "image_prompt.review_collection.md"
            scope_path = run_dir / "logs" / "review" / "image_prompt.review_scope.json"
            prompt_path = run_dir / "logs" / "review" / "image_prompt.judgment_prompt.md"
            report_path = run_dir / "logs" / "review" / "image_prompt.judgment.md"

            self.assertTrue(collection_path.exists())
            self.assertTrue(scope_path.exists())
            self.assertTrue(prompt_path.exists())
            self.assertTrue(report_path.exists())

            self.assertIn("## scene01_cut01", collection_path.read_text(encoding="utf-8"))
            self.assertEqual(prompt_path.read_text(encoding="utf-8").strip(), result.stdout.strip())

            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            self.assertEqual(scope["entry_count"], 1)
            self.assertEqual(scope["selectors"], ["scene01_cut01"])
            self.assertEqual(scope["artifacts"]["collection"], "logs/review/image_prompt.review_collection.md")
            self.assertEqual(scope["artifacts"]["prompt"], "logs/review/image_prompt.judgment_prompt.md")
            self.assertEqual(scope["artifacts"]["report"], "logs/review/image_prompt.judgment.md")

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state.get("review.image_prompt.judgment.collection"), "logs/review/image_prompt.review_collection.md")
            self.assertEqual(state.get("review.image_prompt.judgment.scope"), "logs/review/image_prompt.review_scope.json")
            self.assertEqual(state.get("review.image_prompt.judgment.prompt"), "logs/review/image_prompt.judgment_prompt.md")
            self.assertEqual(state.get("review.image_prompt.judgment.report"), "logs/review/image_prompt.judgment.md")
            self.assertEqual(state.get("review.image_prompt.judgment.status"), "pending")
            self.assertEqual(state.get("review.image_prompt.judgment.entry_count"), "1")
            self.assertTrue(state.get("review.image_prompt.judgment.generated_at"))


if __name__ == "__main__":
    unittest.main()
