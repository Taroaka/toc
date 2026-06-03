import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toc.semantic_review import SEMANTIC_REVIEW_STAGES, check_image_prompt_judgment, check_semantic_review, parse_judgment_report_status, semantic_review_relpaths
from toc.semantic_review_loop import (
    SEMANTIC_REVIEW_PRODUCER_TARGETS,
    _semantic_collection_excerpt,
    semantic_repair_relpaths,
    semantic_repair_timeout_seconds,
    semantic_review_max_attempts,
    semantic_review_timeout_seconds,
    write_semantic_repair_prompt,
)


def write_review_pack(run_dir: Path, *, status: str = "passed", entry_count: int = 1, placeholder: bool = False) -> None:
    review_dir = run_dir / "logs" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "image_prompt.review_collection.md").write_text("# Collection\n\n## scene10_cut01\n", encoding="utf-8")
    (review_dir / "image_prompt.review_scope.json").write_text(
        json.dumps({"entry_count": entry_count, "selectors": ["scene10_cut01"]}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (review_dir / "image_prompt.judgment_prompt.md").write_text("review prompt\n", encoding="utf-8")
    report = "status: {status}\nreviewed_entries: [scene10_cut01]\nblocked_entries: []\nfindings: []\nnotes: []\n".format(status=status)
    if placeholder:
        report = "# Image Prompt Judgment Review\n\n- status: `pending`\n\n## Findings\n\n- `...`\n"
    (review_dir / "image_prompt.judgment.md").write_text(report, encoding="utf-8")


def write_generic_pack(run_dir: Path, stage: str, *, status: str = "passed", entry_count: int = 1) -> None:
    paths = semantic_review_relpaths(stage)
    for key, rel in paths.items():
        path = run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if key == "scope":
            path.write_text(json.dumps({"entry_count": entry_count}, ensure_ascii=False) + "\n", encoding="utf-8")
        elif key == "report":
            path.write_text(f"status: {status}\nreviewed_entries: [entry]\nblocked_entries: []\nfindings: []\n", encoding="utf-8")
        else:
            path.write_text(f"{stage} {key}\n", encoding="utf-8")


class TestSemanticReview(unittest.TestCase):
    def test_parse_report_status_accepts_plain_and_backtick_lines(self) -> None:
        self.assertEqual(parse_judgment_report_status("status: passed\n"), "passed")
        self.assertEqual(parse_judgment_report_status("- status: `failed`\n"), "failed")

    def test_passes_when_report_status_passed_and_entries_exist(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_review_pack(run_dir)

            result = check_image_prompt_judgment(run_dir)

            self.assertTrue(result.passed)
            self.assertEqual(result.status, "passed")
            self.assertEqual(result.entry_count, 1)

    def test_rejects_missing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            result = check_image_prompt_judgment(Path(td))

            self.assertFalse(result.passed)
            self.assertTrue(any("missing semantic review artifact" in error for error in result.errors))

    def test_rejects_pending_placeholder_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_review_pack(run_dir, status="pending", placeholder=True)

            result = check_image_prompt_judgment(run_dir)

            self.assertFalse(result.passed)
            self.assertTrue(any("template placeholder" in error for error in result.errors))
            self.assertTrue(any("must be passed" in error for error in result.errors))

    def test_rejects_zero_entry_scope(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_review_pack(run_dir, entry_count=0)

            result = check_image_prompt_judgment(run_dir)

            self.assertFalse(result.passed)
            self.assertTrue(any("zero entries" in error for error in result.errors))

    def test_generic_semantic_review_passes_for_stage_pack(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(run_dir, "asset_plan")

            result = check_semantic_review(run_dir, "asset_plan")

            self.assertTrue(result.passed)
            self.assertEqual(result.status, "passed")

    def test_image_prompt_prefers_generic_pack_when_present(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_review_pack(run_dir, status="failed")
            write_generic_pack(run_dir, "image_prompt", status="passed")

            result = check_image_prompt_judgment(run_dir)

            self.assertTrue(result.passed)

    def test_image_prompt_accepts_legacy_pass_when_generic_alias_is_stale_pending(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_review_pack(run_dir, status="passed")
            write_generic_pack(run_dir, "image_prompt", status="pending")

            result = check_image_prompt_judgment(run_dir)

            self.assertTrue(result.passed)
            self.assertEqual(result.status, "passed")

    def test_all_semantic_stages_have_producer_repair_targets(self) -> None:
        self.assertEqual(SEMANTIC_REVIEW_STAGES, set(SEMANTIC_REVIEW_PRODUCER_TARGETS))

    def test_write_semantic_repair_prompt_materializes_prompt_and_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(run_dir, "narration", status="failed")

            paths = write_semantic_repair_prompt(
                run_dir,
                "narration",
                round_number=1,
                max_attempts=3,
                errors=("semantic review status must be passed, got failed",),
            )
            relpaths = semantic_repair_relpaths("narration", 1)

            self.assertEqual(paths["prompt"], run_dir / relpaths["prompt"])
            self.assertEqual(paths["report"], run_dir / relpaths["report"])
            self.assertIn("narration producer", paths["prompt"].read_text(encoding="utf-8"))
            self.assertIn("status: pending", paths["report"].read_text(encoding="utf-8"))

    def test_semantic_repair_defaults_to_five_review_attempts(self) -> None:
        with patch.dict("os.environ", {"TOC_SEMANTIC_REVIEW_MAX_ATTEMPTS": ""}):
            self.assertEqual(semantic_review_max_attempts(), 5)

    def test_semantic_review_timeout_default_allows_long_contextless_reviews(self) -> None:
        with patch.dict("os.environ", {"TOC_SEMANTIC_REVIEW_TIMEOUT_SECONDS": ""}):
            self.assertEqual(semantic_review_timeout_seconds(), 1800)

    def test_semantic_repair_timeout_default_allows_long_producer_repairs(self) -> None:
        with patch.dict("os.environ", {"TOC_SEMANTIC_REPAIR_TIMEOUT_SECONDS": ""}):
            self.assertEqual(semantic_repair_timeout_seconds(), 1800)

    def test_semantic_repair_prompt_forbids_editing_review_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(run_dir, "scene_set", status="failed")

            paths = write_semantic_repair_prompt(
                run_dir,
                "scene_set",
                round_number=2,
                max_attempts=5,
                errors=("semantic review status must be passed, got failed",),
            )
            prompt = paths["prompt"].read_text(encoding="utf-8")

            self.assertIn("This is a real semantic repair, not a bypass", prompt)
            self.assertIn("Do not edit `state.txt`, `run_status.json`, or `p000_index.md`", prompt)
            self.assertIn("Do not edit any `logs/review/semantic/*` files except the producer repair report", prompt)
            self.assertIn("Non-editable state/navigation artifacts", prompt)
            self.assertIn("Treat every `blocked_entries`, `failed_selectors`, `findings`, and `reason_keys` item", prompt)
            self.assertIn("remove contradictory language", prompt)
            self.assertIn("Do not run repo-wide searches", prompt)
            self.assertIn("do not print full artifact files to stdout", prompt)
            self.assertIn("Do not edit passed selectors or unrelated scenes/cuts", prompt)
            self.assertIn("never use broad search-and-replace", prompt)
            self.assertIn("Anchor every edit to the failed selector id", prompt)

    def test_semantic_repair_prompt_targets_failed_collection_sections(self) -> None:
        collection = """# Semantic Review Collection: scene_set

## scene:10

passed scene text

## scene:40

failed scene forty text

## scene:50

failed scene fifty text
"""
        report = """status: failed
failed_selectors:
  - scene40
blocked_entries:
  - scene:50
"""

        excerpt = _semantic_collection_excerpt(collection, report)

        self.assertIn("failed scene forty text", excerpt)
        self.assertIn("failed scene fifty text", excerpt)
        self.assertNotIn("passed scene text", excerpt)


if __name__ == "__main__":
    unittest.main()
