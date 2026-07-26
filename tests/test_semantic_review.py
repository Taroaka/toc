import json
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toc.semantic_review import (
    FOUNDATION_SEMANTIC_CRITERIA,
    LEGACY_SEMANTIC_REVIEW_INPUT_SCHEMA,
    SEMANTIC_REVIEW_INPUT_SCHEMA,
    SEMANTIC_REVIEW_STAGES,
    check_image_prompt_judgment,
    check_semantic_review,
    parse_judgment_report_status,
    safe_semantic_write_text,
    semantic_review_currentness_issues,
    semantic_review_input_digest,
    semantic_review_relpaths,
    semantic_review_scope_binding_sha256,
    semantic_review_sources_are_current,
)
from toc.semantic_review_loop import (
    SEMANTIC_REVIEW_PRODUCER_TARGETS,
    _semantic_collection_excerpt,
    semantic_repair_relpaths,
    semantic_repair_timeout_seconds,
    scene_detail_review_concurrency,
    scene_detail_transport_retry_attempts,
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
    report = "status: {status}\nreviewed_entries: [scene10_cut01]\nblocked_entries: []\nfailed_selectors: []\nfindings: []\nnotes: []\n".format(status=status)
    if placeholder:
        report = "# Image Prompt Judgment Review\n\n- status: `pending`\n\n## Findings\n\n- `...`\n"
    (review_dir / "image_prompt.judgment.md").write_text(report, encoding="utf-8")


def write_generic_pack(
    run_dir: Path,
    stage: str,
    *,
    status: str = "passed",
    entry_count: int = 1,
    reviewed_entries: list[str] | None = None,
    blocked_entries: list[str] | None = None,
    failed_selectors: list[str] | None = None,
    include_foundation_criteria: bool = True,
) -> None:
    paths = semantic_review_relpaths(stage)
    entry_ids = [f"{stage}:entry:{index + 1}" for index in range(entry_count)]
    reviewed = entry_ids if reviewed_entries is None else reviewed_entries
    source_path = run_dir / f"{stage}_semantic_source.md"
    source_path.write_text(f"# {stage} semantic source\n", encoding="utf-8")
    collection_path = run_dir / paths["collection"]
    prompt_path = run_dir / paths["prompt"]
    scope_path = run_dir / paths["scope"]
    report_path = run_dir / paths["report"]
    collection_path.parent.mkdir(parents=True, exist_ok=True)
    collection_path.write_text(f"{stage} collection\n", encoding="utf-8")
    prompt_path.write_text(f"{stage} prompt\n", encoding="utf-8")
    source_digests = [
        {
            "path": source_path.relative_to(run_dir).as_posix(),
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        }
    ]
    scope = {
        "stage": stage,
        "entry_count": entry_count,
        "entry_ids": entry_ids,
        "review_scope": "all_entries",
        "source_artifacts": [source_path.relative_to(run_dir).as_posix()],
        "semantic_review_input_schema": SEMANTIC_REVIEW_INPUT_SCHEMA,
        "source_artifact_digests": source_digests,
        "collection_sha256": hashlib.sha256(collection_path.read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
        "artifacts": {
            "collection": paths["collection"].as_posix(),
            "scope": paths["scope"].as_posix(),
            "prompt": paths["prompt"].as_posix(),
            "report": paths["report"].as_posix(),
        },
    }
    scope_binding_sha256 = semantic_review_scope_binding_sha256(scope)
    digest = semantic_review_input_digest(
        stage=stage,
        entry_ids=entry_ids,
        collection_sha256=scope["collection_sha256"],
        prompt_sha256=scope["prompt_sha256"],
        source_artifact_digests=source_digests,
        scope_binding_sha256=scope_binding_sha256,
    )
    scope["scope_binding_sha256"] = scope_binding_sha256
    scope["semantic_review_input_digest"] = digest
    scope_path.write_text(json.dumps(scope, ensure_ascii=False) + "\n", encoding="utf-8")
    criteria_results = [
        {
            "criterion_id": criterion_id,
            "status": "passed",
            "evidence": f"{stage}.md:{criterion_id}",
        }
        for criterion_id in FOUNDATION_SEMANTIC_CRITERIA.get(stage, ())
    ]
    criteria_line = (
        "criteria_results_json: " + json.dumps(criteria_results, ensure_ascii=False)
        if include_foundation_criteria and stage in FOUNDATION_SEMANTIC_CRITERIA
        else ""
    )
    report_path.write_text(
        "\n".join(
            [
                f"status: {status}",
                f"semantic_review_input_digest: {digest}",
                f"reviewed_entries: [{', '.join(reviewed)}]",
                f"blocked_entries: [{', '.join(blocked_entries or [])}]",
                f"failed_selectors: [{', '.join(failed_selectors or [])}]",
                criteria_line,
                "findings: []",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_digest_bound_pack(run_dir: Path, stage: str = "asset_plan") -> tuple[Path, Path]:
    paths = semantic_review_relpaths(stage)
    source_path = run_dir / "asset_plan.md"
    source_path.write_text("# Asset plan\n\nrevision one\n", encoding="utf-8")
    collection_path = run_dir / paths["collection"]
    prompt_path = run_dir / paths["prompt"]
    scope_path = run_dir / paths["scope"]
    report_path = run_dir / paths["report"]
    collection_path.parent.mkdir(parents=True, exist_ok=True)
    collection_path.write_text("# Collection\n\n## asset_plan:entry:1\n", encoding="utf-8")
    prompt_path.write_text("review current asset plan\n", encoding="utf-8")
    source_artifact_digests = [
        {
            "path": "asset_plan.md",
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        }
    ]
    scope = {
        "stage": stage,
        "entry_count": 1,
        "entry_ids": ["asset_plan:entry:1"],
        "review_scope": "all_entries",
        "source_artifacts": ["asset_plan.md"],
        "semantic_review_input_schema": SEMANTIC_REVIEW_INPUT_SCHEMA,
        "source_artifact_digests": source_artifact_digests,
        "collection_sha256": hashlib.sha256(collection_path.read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
        "artifacts": {
            "collection": paths["collection"].as_posix(),
            "scope": paths["scope"].as_posix(),
            "prompt": paths["prompt"].as_posix(),
            "report": paths["report"].as_posix(),
        },
    }
    scope_binding_sha256 = semantic_review_scope_binding_sha256(scope)
    digest = semantic_review_input_digest(
        stage=stage,
        entry_ids=["asset_plan:entry:1"],
        collection_sha256=scope["collection_sha256"],
        prompt_sha256=scope["prompt_sha256"],
        source_artifact_digests=source_artifact_digests,
        scope_binding_sha256=scope_binding_sha256,
    )
    scope["scope_binding_sha256"] = scope_binding_sha256
    scope["semantic_review_input_digest"] = digest
    scope_path.write_text(
        json.dumps(scope, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        "\n".join(
            [
                "status: passed",
                f"semantic_review_input_digest: {digest}",
                "reviewed_entries: [asset_plan:entry:1]",
                "blocked_entries: []",
                "failed_selectors: []",
                "findings: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return source_path, report_path


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

    def test_foundation_semantic_review_requires_exact_scope_coverage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(
                run_dir,
                "research",
                entry_count=2,
                reviewed_entries=["research:entry:1"],
            )

            result = check_semantic_review(run_dir, "research")

            self.assertFalse(result.passed)
            self.assertTrue(any("reviewed_entries coverage" in error for error in result.errors))

    def test_every_semantic_stage_requires_exact_scope_coverage(self) -> None:
        non_foundation_stages = sorted(SEMANTIC_REVIEW_STAGES - set(FOUNDATION_SEMANTIC_CRITERIA))
        for stage in non_foundation_stages:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
                run_dir = Path(td)
                write_generic_pack(
                    run_dir,
                    stage,
                    entry_count=2,
                    reviewed_entries=[f"{stage}:entry:1"],
                )

                result = check_semantic_review(run_dir, stage)

                self.assertFalse(result.passed)
                self.assertTrue(any("reviewed_entries coverage" in error for error in result.errors))

    def test_passed_report_rejects_blocked_entries_and_failed_selectors_for_every_stage(self) -> None:
        for stage in sorted(SEMANTIC_REVIEW_STAGES):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
                run_dir = Path(td)
                entry_id = f"{stage}:entry:1"
                write_generic_pack(
                    run_dir,
                    stage,
                    blocked_entries=[entry_id],
                    failed_selectors=[entry_id],
                )

                result = check_semantic_review(run_dir, stage)

                self.assertFalse(result.passed)
                self.assertIn("passed semantic review must have empty blocked_entries", result.errors)
                self.assertIn("passed semantic review must have empty failed_selectors", result.errors)

    def test_scope_entry_count_must_equal_exact_entry_ids(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(run_dir, "asset_plan", entry_count=2)
            scope_path = run_dir / semantic_review_relpaths("asset_plan")["scope"]
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            scope["entry_count"] = 1
            scope_path.write_text(json.dumps(scope) + "\n", encoding="utf-8")

            result = check_semantic_review(run_dir, "asset_plan")

            self.assertFalse(result.passed)
            self.assertTrue(any("entry_count must match" in error for error in result.errors))

    def test_digest_bound_currentness_rejects_content_change_with_preserved_mtime(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            source_path, _report_path = write_digest_bound_pack(run_dir)
            original_stat = source_path.stat()

            self.assertTrue(semantic_review_sources_are_current(run_dir, "asset_plan"))

            source_path.write_text("# Asset plan\n\nrevision two\n", encoding="utf-8")
            os.utime(
                source_path,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
            )

            issues = semantic_review_currentness_issues(run_dir, "asset_plan")
            self.assertFalse(semantic_review_sources_are_current(run_dir, "asset_plan"))
            self.assertTrue(any("SHA-256 mismatch" in issue for issue in issues), issues)

    def test_digest_bound_currentness_rejects_unsafe_source_and_unbound_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            _source_path, report_path = write_digest_bound_pack(run_dir)
            scope_path = run_dir / semantic_review_relpaths("asset_plan")["scope"]

            report_path.write_text(
                report_path.read_text(encoding="utf-8").replace(
                    "semantic_review_input_digest: sha256:",
                    "semantic_review_input_digest: sha256:stale-",
                ),
                encoding="utf-8",
            )
            self.assertTrue(
                any(
                    "report semantic_review_input_digest does not match" in issue
                    for issue in semantic_review_currentness_issues(run_dir, "asset_plan")
                )
            )

            write_digest_bound_pack(run_dir)
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            scope["source_artifacts"] = ["../asset_plan.md"]
            scope["source_artifact_digests"][0]["path"] = "../asset_plan.md"
            scope_path.write_text(json.dumps(scope) + "\n", encoding="utf-8")

            self.assertTrue(
                any(
                    "safe run-relative path" in issue
                    for issue in semantic_review_currentness_issues(run_dir, "asset_plan")
                )
            )

    def test_digest_metadata_cannot_be_removed_to_downgrade_to_legacy_currentness(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_digest_bound_pack(run_dir)
            scope_path = run_dir / semantic_review_relpaths("asset_plan")["scope"]
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            for field in (
                "semantic_review_input_schema",
                "source_artifact_digests",
                "collection_sha256",
                "prompt_sha256",
                "scope_binding_sha256",
                "semantic_review_input_digest",
            ):
                scope.pop(field, None)
            scope_path.write_text(json.dumps(scope) + "\n", encoding="utf-8")

            issues = semantic_review_currentness_issues(run_dir, "asset_plan")

            self.assertTrue(any("incomplete digest metadata" in issue for issue in issues), issues)

    def test_duplicate_machine_fields_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_digest_bound_pack(run_dir)
            report_path = run_dir / semantic_review_relpaths("asset_plan")["report"]
            report_path.write_text(
                report_path.read_text(encoding="utf-8")
                + "status: failed\n"
                + "semantic_review_input_digest: sha256:duplicate\n",
                encoding="utf-8",
            )

            result = check_semantic_review(run_dir, "asset_plan")

            self.assertFalse(result.passed)
            self.assertTrue(any("exactly one status" in error for error in result.errors), result.errors)
            self.assertTrue(
                any("exactly one semantic_review_input_digest" in error for error in result.errors),
                result.errors,
            )

    def test_safe_semantic_write_rejects_run_local_symlink_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td, tempfile.TemporaryDirectory(
            prefix="semantic_review_outside_"
        ) as outside_td:
            run_dir = Path(td)
            outside = Path(outside_td)
            (run_dir / "logs").symlink_to(outside, target_is_directory=True)
            target = outside / "report.md"

            with self.assertRaisesRegex(ValueError, "symlink|escapes run directory"):
                safe_semantic_write_text(run_dir, run_dir / "logs" / "report.md", "unsafe\n")

            self.assertFalse(target.exists())

    def test_legacy_currentness_falls_back_to_safe_source_mtime(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(run_dir, "asset_plan")
            source_path = run_dir / "asset_plan.md"
            source_path.write_text("# legacy source\n", encoding="utf-8")
            scope_path = run_dir / semantic_review_relpaths("asset_plan")["scope"]
            scope = {
                "stage": "asset_plan",
                "entry_count": 1,
                "entry_ids": ["asset_plan:entry:1"],
                "source_artifacts": ["asset_plan.md"],
                "semantic_review_input_schema": LEGACY_SEMANTIC_REVIEW_INPUT_SCHEMA,
            }
            scope_path.write_text(json.dumps(scope) + "\n", encoding="utf-8")
            report_path = run_dir / semantic_review_relpaths("asset_plan")["report"]
            report_path.touch()

            self.assertTrue(semantic_review_sources_are_current(run_dir, "asset_plan"))

            report_mtime = report_path.stat().st_mtime_ns
            os.utime(source_path, ns=(report_mtime + 1, report_mtime + 1))

            self.assertFalse(semantic_review_sources_are_current(run_dir, "asset_plan"))

    def test_foundation_semantic_review_passes_with_exact_scope_coverage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(run_dir, "story", entry_count=2)

            result = check_semantic_review(run_dir, "story")

            self.assertTrue(result.passed, result.errors)

    def test_foundation_semantic_review_rejects_pass_without_criterion_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(
                run_dir,
                "research",
                include_foundation_criteria=False,
            )

            result = check_semantic_review(run_dir, "research")

            self.assertFalse(result.passed)
            self.assertTrue(any("criteria_results_json" in error for error in result.errors))

    def test_foundation_semantic_review_rejects_missing_or_empty_criterion_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(run_dir, "story")
            report_path = run_dir / semantic_review_relpaths("story")["report"]
            report = report_path.read_text(encoding="utf-8")
            criteria = [
                {
                    "criterion_id": criterion_id,
                    "status": "passed",
                    "evidence": f"story.md:{criterion_id}",
                }
                for criterion_id in FOUNDATION_SEMANTIC_CRITERIA["story"][:-1]
            ]
            criteria[0]["evidence"] = ""
            report_path.write_text(
                report.replace(
                    next(line for line in report.splitlines() if line.startswith("criteria_results_json:")),
                    "criteria_results_json: " + json.dumps(criteria, ensure_ascii=False),
                ),
                encoding="utf-8",
            )

            result = check_semantic_review(run_dir, "story")

            self.assertFalse(result.passed)
            self.assertTrue(any("criterion_ids" in error for error in result.errors))
            self.assertTrue(any("non-empty evidence" in error for error in result.errors))

    def test_foundation_semantic_review_rejects_pass_when_any_criterion_failed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(run_dir, "research")
            report_path = run_dir / semantic_review_relpaths("research")["report"]
            report = report_path.read_text(encoding="utf-8")
            report_path.write_text(
                report.replace('"status": "passed"', '"status": "failed"', 1),
                encoding="utf-8",
            )

            result = check_semantic_review(run_dir, "research")

            self.assertFalse(result.passed)
            self.assertTrue(any("every criterion status" in error for error in result.errors))

    def test_image_prompt_prefers_generic_pack_when_present(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_review_pack(run_dir, status="failed")
            write_generic_pack(run_dir, "image_prompt", status="passed")

            result = check_image_prompt_judgment(run_dir)

            self.assertTrue(result.passed)

    def test_image_prompt_rejects_legacy_pass_when_canonical_review_is_pending(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_review_pack(run_dir, status="passed")
            write_generic_pack(run_dir, "image_prompt", status="pending")

            result = check_image_prompt_judgment(run_dir)

            self.assertFalse(result.passed)
            self.assertEqual(result.status, "pending")

    def test_image_prompt_does_not_fall_back_when_canonical_pack_is_partial(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_review_pack(run_dir, status="passed")
            canonical_scope = run_dir / semantic_review_relpaths("image_prompt")["scope"]
            canonical_scope.parent.mkdir(parents=True, exist_ok=True)
            canonical_scope.write_text("{}\n", encoding="utf-8")

            result = check_image_prompt_judgment(run_dir)

            self.assertFalse(result.passed)
            self.assertTrue(any("missing semantic review" in error for error in result.errors), result.errors)

    def test_all_semantic_stages_have_producer_repair_targets(self) -> None:
        self.assertEqual(SEMANTIC_REVIEW_STAGES, set(SEMANTIC_REVIEW_PRODUCER_TARGETS))
        self.assertTrue({"research", "story"}.issubset(SEMANTIC_REVIEW_STAGES))

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

    def test_image_prompt_repair_edits_visual_plan_then_recompiles_derived_requests(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(run_dir, "image_prompt", status="failed")

            paths = write_semantic_repair_prompt(
                run_dir,
                "image_prompt",
                round_number=1,
                max_attempts=2,
                errors=("positive and negative prompt instructions conflict",),
            )
            prompt = paths["prompt"].read_text(encoding="utf-8")

            self.assertIn("first_frame_visual_plan", prompt)
            self.assertIn("include / omit / add / replace", prompt)
            self.assertIn("Do not hand-edit `api_prompt_payload.prompt`", prompt)
            self.assertIn("image_generation_requests.md", prompt)
            self.assertIn("image_generation_request_snapshot.json", prompt)
            self.assertIn("orchestrator", prompt)
            self.assertIn("scene.time_of_day", prompt)
            self.assertIn("sky brightness", prompt)
            self.assertIn("shadows", prompt)
            self.assertIn("artificial lighting", prompt)
            self.assertIn("separately from `video_metadata.time`", prompt)
            self.assertIn("time_of_day_contract_declared", prompt)
            self.assertIn("time_of_day_status", prompt)
            self.assertIn("undeclared legacy artifact", prompt)

    def test_video_motion_repair_edits_canonical_motion_and_reference_roles_then_recompiles(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            write_generic_pack(run_dir, "video_motion", status="failed")

            paths = write_semantic_repair_prompt(
                run_dir,
                "video_motion",
                round_number=1,
                max_attempts=2,
                errors=("video motion is abstract and duplicates another cut",),
            )
            prompt = paths["prompt"].read_text(encoding="utf-8")

            self.assertIn("Video Motion Repair Boundary", prompt)
            self.assertIn("cut_contract.motion_contract", prompt)
            self.assertIn("continuity_contract", prompt)
            self.assertIn("video_input_contract.reference_roles", prompt)
            self.assertIn("include / omit / add / replace", prompt)
            self.assertIn("Do not hand-edit `api_prompt_payload.prompt`", prompt)
            self.assertIn("video_generation_requests.md", prompt)
            self.assertIn("recompile", prompt)

    def test_scene_stage_repairs_keep_daypart_separate_from_historical_time(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            for stage in ("scene_set", "scene_detail", "cut_blueprint"):
                write_generic_pack(run_dir, stage, status="failed")
                paths = write_semantic_repair_prompt(
                    run_dir,
                    stage,
                    round_number=1,
                    max_attempts=2,
                    errors=("scene daypart mismatch",),
                )
                prompt = paths["prompt"].read_text(encoding="utf-8")
                self.assertIn("Scene Time-of-Day Repair Boundary", prompt)
                self.assertIn("time_of_day_contract_declared", prompt)
                self.assertIn("time_of_day_status", prompt)
                self.assertIn("script_metadata.time", prompt)
                self.assertIn("sky brightness", prompt)
                self.assertIn("artificial light", prompt)

    def test_foundation_repair_prompt_requires_structured_round_trip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            (run_dir / "research.md").write_text("# Research\n\n```yaml\ntopic: test\n```\n", encoding="utf-8")
            write_generic_pack(run_dir, "research", status="failed")

            paths = write_semantic_repair_prompt(
                run_dir,
                "research",
                round_number=1,
                max_attempts=2,
                errors=("research foundation failed",),
            )
            prompt = paths["prompt"].read_text(encoding="utf-8")

            self.assertIn("fenced YAML", prompt)
            self.assertIn("load_structured_document", prompt)
            self.assertIn("Do not delegate", prompt)

    def test_story_repair_restores_scene_daypart_at_the_story_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            (run_dir / "story.md").write_text("# Story\n\n```yaml\nstory_metadata:\n  time: ''\nscript:\n  scenes: []\n```\n", encoding="utf-8")
            write_generic_pack(run_dir, "story", status="failed")

            paths = write_semantic_repair_prompt(
                run_dir,
                "story",
                round_number=1,
                max_attempts=2,
                errors=("scene_time_of_day_missing",),
            )
            prompt = paths["prompt"].read_text(encoding="utf-8")

            self.assertIn("story scene `time_of_day`", prompt)
            self.assertIn("open, non-empty string", prompt)
            self.assertIn("do not infer it from location or image-prompt prose", prompt)
            self.assertIn("historical `story_metadata.time`", prompt)
            self.assertIn("location.mode: sequence", prompt)
            self.assertIn("every ordered `location.sequence[]` item", prompt)
            self.assertIn("Do not invent a transition", prompt)

    def test_semantic_repair_defaults_to_two_review_attempts(self) -> None:
        with patch.dict("os.environ", {"TOC_SEMANTIC_REVIEW_MAX_ATTEMPTS": ""}):
            self.assertEqual(semantic_review_max_attempts(), 2)

    def test_semantic_review_timeout_default_allows_long_contextless_reviews(self) -> None:
        with patch.dict("os.environ", {"TOC_SEMANTIC_REVIEW_TIMEOUT_SECONDS": ""}):
            self.assertEqual(semantic_review_timeout_seconds(), 1800)

    def test_semantic_repair_timeout_default_allows_long_producer_repairs(self) -> None:
        with patch.dict("os.environ", {"TOC_SEMANTIC_REPAIR_TIMEOUT_SECONDS": ""}):
            self.assertEqual(semantic_repair_timeout_seconds(), 1800)

    def test_scene_detail_review_concurrency_defaults_to_six(self) -> None:
        with patch.dict("os.environ", {"TOC_SCENE_DETAIL_REVIEW_CONCURRENCY": ""}):
            self.assertEqual(scene_detail_review_concurrency(), 6)

    def test_scene_detail_review_concurrency_uses_env_with_floor(self) -> None:
        with patch.dict("os.environ", {"TOC_SCENE_DETAIL_REVIEW_CONCURRENCY": "3"}):
            self.assertEqual(scene_detail_review_concurrency(), 3)
        with patch.dict("os.environ", {"TOC_SCENE_DETAIL_REVIEW_CONCURRENCY": "0"}):
            self.assertEqual(scene_detail_review_concurrency(), 1)
        with patch.dict("os.environ", {"TOC_SCENE_DETAIL_REVIEW_CONCURRENCY": "bad"}):
            self.assertEqual(scene_detail_review_concurrency(), 6)

    def test_scene_detail_transport_retry_attempts_defaults_to_three(self) -> None:
        with patch.dict("os.environ", {"TOC_SCENE_DETAIL_TRANSPORT_RETRY_ATTEMPTS": ""}):
            self.assertEqual(scene_detail_transport_retry_attempts(), 3)

    def test_scene_detail_transport_retry_attempts_uses_env_with_floor(self) -> None:
        with patch.dict("os.environ", {"TOC_SCENE_DETAIL_TRANSPORT_RETRY_ATTEMPTS": "2"}):
            self.assertEqual(scene_detail_transport_retry_attempts(), 2)
        with patch.dict("os.environ", {"TOC_SCENE_DETAIL_TRANSPORT_RETRY_ATTEMPTS": "0"}):
            self.assertEqual(scene_detail_transport_retry_attempts(), 1)
        with patch.dict("os.environ", {"TOC_SCENE_DETAIL_TRANSPORT_RETRY_ATTEMPTS": "bad"}):
            self.assertEqual(scene_detail_transport_retry_attempts(), 3)

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

    def test_semantic_repair_prompt_targets_inline_failed_selectors(self) -> None:
        collection = """# Semantic Review Collection: scene_set

## scene:10

failed scene ten text

## scene:20

failed scene twenty text

## scene:40

passed scene forty text
"""
        report = """status: failed
reviewed_entries: [scene:10, scene:20, scene:40]
blocked_entries: [scene:10]
failed_selectors: [scene20]
reason_keys: [semantic_contract_missing]
"""

        excerpt = _semantic_collection_excerpt(collection, report)

        self.assertIn("failed scene ten text", excerpt)
        self.assertIn("failed scene twenty text", excerpt)
        self.assertNotIn("passed scene forty text", excerpt)

    def test_write_semantic_repair_prompt_lists_inline_failed_selectors(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_review_") as td:
            run_dir = Path(td)
            paths = semantic_review_relpaths("scene_set")
            (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
            (run_dir / paths["collection"]).write_text(
                "# Semantic Review Collection: scene_set\n\n## scene:10\n\nfailed ten\n\n## scene:40\n\npassed forty\n",
                encoding="utf-8",
            )
            (run_dir / paths["scope"]).write_text(json.dumps({"entry_count": 2}, ensure_ascii=False) + "\n", encoding="utf-8")
            (run_dir / paths["prompt"]).write_text("# prompt\n", encoding="utf-8")
            (run_dir / paths["report"]).write_text(
                "status: failed\nblocked_entries: [scene:10]\nfailed_selectors: [scene10]\n",
                encoding="utf-8",
            )

            repair_paths = write_semantic_repair_prompt(
                run_dir,
                "scene_set",
                round_number=1,
                max_attempts=5,
                errors=("semantic review status must be passed, got failed",),
            )
            prompt = repair_paths["prompt"].read_text(encoding="utf-8")

        self.assertIn("## Target Failed Selectors", prompt)
        self.assertIn("- `scene:10`", prompt)
        self.assertIn("- `scene10`", prompt)
        self.assertIn("failed ten", prompt)
        self.assertNotIn("passed forty", prompt)


if __name__ == "__main__":
    unittest.main()
