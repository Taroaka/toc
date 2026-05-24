import json
import tempfile
import unittest
from pathlib import Path

from toc.semantic_review import check_image_prompt_judgment, check_semantic_review, parse_judgment_report_status, semantic_review_relpaths


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


if __name__ == "__main__":
    unittest.main()
