from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, call, patch

import yaml

from server import image_gen_app
from toc.harness import load_structured_document
from toc.image_prompt_compiler import compile_image_api_prompt_v2
from toc.image_request_snapshot import (
    load_request_snapshot,
    materialize_request_snapshot,
    write_request_snapshot_atomic,
)
from toc.semantic_review import (
    SEMANTIC_REVIEW_INPUT_SCHEMA,
    SemanticReviewStatus,
    semantic_review_input_digest,
    semantic_review_scope_binding_sha256,
)


def _plan(moment: str) -> dict[str, object]:
    return {
        "schema_version": "first_frame_visual_plan_v1",
        "temporal_boundary": {
            "event_fact_visible_in_still": moment,
            "not_yet_happened_in_still": [],
        },
        "subject_binding": {"primary_subject": {"name": "旅人"}},
        "character_state_gate": {
            "costume_state": "旅装の麻布の上着",
            "pose": "古い城門へ正対して立つ",
            "gaze": "閉じた門を見上げる",
        },
        "spatial_composition": {
            "foreground": "石畳",
            "midground": "旅人",
            "background": "城門",
            "shot_size": "closeup",
        },
        "scene_material_pack": {
            "light_source": "夕方の斜光",
            "dominant_materials": ["石", "麻布"],
        },
    }


def _write_v2_revision_fixture(
    run_dir: Path,
    *,
    reference: str = "",
    create_reference: bool = False,
) -> dict[str, object]:
    (run_dir / "story.md").write_text("# story\n\n旅人が城門へ向かう物語。\n", encoding="utf-8")
    (run_dir / "script.md").write_text("# script\n\n旅人が閉じた城門を見る。\n", encoding="utf-8")
    plan = _plan("旅人が閉じた城門を見る")
    references = [reference] if reference else []
    payload = compile_image_api_prompt_v2(
        first_frame_visual_plan=plan,
        character_ids=["traveler"],
        location_ids=["castle_gate"],
        reference_images=references,
        story_time="江戸時代",
        scene_time_of_day="夕方",
    )
    manifest = {
        "schema_version": "scene_event_v1",
        "video_metadata": {"time": "江戸時代"},
        "scenes": [
            {
                "scene_id": 1,
                "time_of_day": "夕方",
                "cuts": [
                    {
                        "cut_id": 1,
                        "image_generation": {
                            "output": "assets/scenes/scene1_cut1.png",
                            "character_ids": ["traveler"],
                            "object_ids": [],
                            "location_ids": ["castle_gate"],
                            "references": references,
                            "first_frame_visual_plan": plan,
                            "api_prompt_payload": payload,
                        },
                    }
                ],
            }
        ],
    }
    (run_dir / "video_manifest.md").write_text(
        "# manifest\n\n```yaml\n"
        + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
        + "```\n",
        encoding="utf-8",
    )
    if reference and create_reference:
        reference_path = run_dir / reference
        reference_path.parent.mkdir(parents=True, exist_ok=True)
        reference_path.write_bytes(b"reference-v1")
    reference_lines = (
        ["- references:", f"  - `人物参照画像1`: `{reference}`"]
        if reference
        else ["- references: `[]`"]
    )
    request_text = "\n".join(
        [
            "# Image Generation Requests",
            "",
            "## scene1_cut1",
            "",
            "- tool: `codex_builtin_image`",
            "- prompt_policy_version: `image_api_prompt_v2`",
            "- output: `assets/scenes/scene1_cut1.png`",
            *reference_lines,
            "",
            "```api_prompt",
            str(payload["prompt"]),
            "```",
            "",
        ]
    )
    (run_dir / "image_generation_requests.md").write_text(request_text, encoding="utf-8")
    snapshot = materialize_request_snapshot(
        run_dir,
        kind="scene",
        items=[
            {
                "item_id": "scene1_cut1",
                "destination": "assets/scenes/scene1_cut1.png",
                "prompt": payload["prompt"],
                "prompt_policy_version": payload["policy_version"],
                "compiler_version": payload["compiler_version"],
                "source_digest": payload["source_digest"],
                "references": references,
            }
        ],
        source_artifact="image_generation_requests.md",
        defer_missing_references=bool(reference and not create_reference),
    )
    write_request_snapshot_atomic(
        run_dir / "image_generation_request_snapshot.json",
        snapshot,
        run_dir=run_dir,
    )
    (run_dir / "state.txt").write_text("", encoding="utf-8")
    _write_passing_review_artifacts(run_dir)
    return manifest


def _current_request_revision(run_dir: Path) -> str:
    return load_request_snapshot(
        run_dir / "image_generation_request_snapshot.json",
        run_dir=run_dir,
        verify_references=False,
    ).request_revision


def _write_deterministic_review(
    run_dir: Path,
    *,
    hard_findings: int = 0,
    blocking_hard_findings: int | None = None,
    unresolved_entries: int | None = None,
    reviewed_entries: int = 1,
    hard_finding_details: list[tuple[str, str, str]] | None = None,
    human_review_ok: bool = False,
    human_review_reason: str = "approved exception for this selector",
) -> None:
    details = hard_finding_details or []
    findings = hard_findings or len(details)
    hard_findings = findings
    blocking_findings = (
        hard_findings if blocking_hard_findings is None else blocking_hard_findings
    )
    if unresolved_entries is None:
        unresolved_entries = (
            len({selector for selector, _code, _message in details})
            if blocking_findings
            else 0
        )
    status = "FAIL" if unresolved_entries else ("WARN" if findings else "PASS")
    detail_lines: list[str] = []
    detail_selectors: set[str] = set()
    for selector, code, message in details:
        detail_selectors.add(selector)
        blocking_code = "" if human_review_ok else code
        detail_lines.extend(
            [
                f"## {selector}",
                "",
                f"- output: `assets/scenes/{selector}.png`",
                "- narration: `(silent)`",
                "- overall_score: `0.000`",
                "- rubric_scores: `{}`",
                "- agent_review_ok: `false`",
                f"- human_review_ok: `{'true' if human_review_ok else 'false'}`",
                *(
                    [f"- human_review_reason: `{human_review_reason}`"]
                    if human_review_ok and human_review_reason
                    else []
                ),
                f"- review: `{'WARN' if human_review_ok else 'FAIL'}`",
                f"- agent_review_reason_keys: `{code}`",
                f"- hard_finding_codes: `{code}`",
                f"- blocking_hard_finding_codes: `{blocking_code}`",
                "- soft_finding_codes: ``",
                f"- {code}: {message}",
                "",
            ]
        )
    for cut_number in range(1, reviewed_entries + 1):
        selector = f"scene01_cut{cut_number:02d}"
        if selector in detail_selectors:
            continue
        detail_lines.extend(
            [
                f"## {selector}",
                "",
                f"- output: `assets/scenes/{selector}.png`",
                "- narration: `(silent)`",
                "- overall_score: `1.000`",
                "- rubric_scores: `{}`",
                "- review: `PASS`",
                "",
            ]
        )
    (run_dir / "image_prompt_story_review.md").write_text(
        "\n".join(
            [
                "# Image Prompt Story Review",
                "",
                "- review_format_version: `deterministic_image_prompt_review_v2`",
                f"- manifest: `{run_dir / 'video_manifest.md'}`",
                f"- manifest_sha256: `{image_gen_app._file_sha256(run_dir / 'video_manifest.md') if (run_dir / 'video_manifest.md').is_file() else ''}`",
                f"- story_sha256: `{image_gen_app._file_sha256(run_dir / 'story.md') if (run_dir / 'story.md').is_file() else ''}`",
                f"- script_sha256: `{image_gen_app._file_sha256(run_dir / 'script.md') if (run_dir / 'script.md').is_file() else ''}`",
                f"- status: `{status}`",
                f"- reviewed_entries: `{reviewed_entries}`",
                "- empty_review_scope: `false`",
                f"- entries_with_findings: `{1 if findings else 0}`",
                f"- findings: `{findings}`",
                f"- hard_findings: `{hard_findings}`",
                f"- blocking_hard_findings: `{blocking_findings}`",
                "- soft_findings: `0`",
                f"- unresolved_entries: `{unresolved_entries}`",
                "",
                *detail_lines,
            ]
        ),
        encoding="utf-8",
    )


def _write_passing_review_artifacts(run_dir: Path) -> None:
    _write_deterministic_review(run_dir)
    paths = image_gen_app.semantic_review_relpaths("image_prompt")
    (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / paths["collection"]).write_text("# collection\n\n## scene1_cut1\n", encoding="utf-8")
    source_artifacts = [
        "story.md",
        "script.md",
        "video_manifest.md",
        "image_generation_requests.md",
        "image_generation_request_snapshot.json",
        "image_prompt_story_review.md",
    ]
    collection_path = run_dir / paths["collection"]
    prompt_path = run_dir / paths["prompt"]
    scope_path = run_dir / paths["scope"]
    report_path = run_dir / paths["report"]
    prompt_path.write_text("# prompt\n", encoding="utf-8")
    source_artifact_digests = [
        {
            "path": source,
            "sha256": hashlib.sha256((run_dir / source).read_bytes()).hexdigest(),
        }
        for source in source_artifacts
    ]
    scope = {
        "stage": "image_prompt",
        "entry_count": 1,
        "entry_ids": ["scene1_cut1"],
        "review_scope": "all_entries",
        "request_revision": _current_request_revision(run_dir),
        "source_artifacts": source_artifacts,
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
        stage="image_prompt",
        entry_ids=["scene1_cut1"],
        collection_sha256=scope["collection_sha256"],
        prompt_sha256=scope["prompt_sha256"],
        source_artifact_digests=source_artifact_digests,
        request_revision=scope["request_revision"],
        scope_binding_sha256=scope_binding_sha256,
    )
    scope["scope_binding_sha256"] = scope_binding_sha256
    scope["semantic_review_input_digest"] = digest
    scope_path.write_text(
        json.dumps(scope, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        "status: passed\n"
        + f"semantic_review_input_digest: {digest}\n"
        + "reviewed_entries: [scene1_cut1]\n"
        + "blocked_entries: []\nfindings: []\nfailed_selectors: []\n",
        encoding="utf-8",
    )


class ImagePromptRepairFreezeTests(unittest.TestCase):
    def test_recompile_restores_missing_or_downgraded_v2_payload(self) -> None:
        for broken_payload in (None, {"policy_version": "image_api_prompt_v1", "prompt": "legacy"}):
            with self.subTest(broken_payload=broken_payload), tempfile.TemporaryDirectory(
                prefix="image_prompt_repair_"
            ) as td:
                run_dir = Path(td)
                manifest = _write_v2_revision_fixture(run_dir)
                image_generation = manifest["scenes"][0]["cuts"][0]["image_generation"]
                if broken_payload is None:
                    image_generation.pop("api_prompt_payload")
                else:
                    image_generation["api_prompt_payload"] = broken_payload
                (run_dir / "video_manifest.md").write_text(
                    "# manifest\n\n```yaml\n"
                    + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
                    + "```\n",
                    encoding="utf-8",
                )

                compiled = image_gen_app._recompile_image_prompt_payloads_from_plans(run_dir)
                _, updated = load_structured_document(run_dir / "video_manifest.md")
                payload = updated["scenes"][0]["cuts"][0]["image_generation"]["api_prompt_payload"]

            self.assertEqual(compiled, ["scene1_cut1"])
            self.assertEqual(payload["policy_version"], "image_api_prompt_v2")
            self.assertEqual(payload["drawable_prompt_ir"]["dependencies"]["time_of_day"], "夕方")
            self.assertIn("このシーンの時間帯は夕方", payload["prompt"])

    def test_freeze_binds_exact_manifest_markdown_and_snapshot_revision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            manifest = _write_v2_revision_fixture(run_dir)

            reviewed_revision = _current_request_revision(run_dir)
            image_gen_app._mark_image_prompt_request_freeze_done(
                run_dir,
                expected_request_revision=reviewed_revision,
            )
            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            manifest["scenes"][0]["cuts"][0]["image_generation"]["api_prompt_payload"][
                "prompt"
            ] += " 改変"
            (run_dir / "video_manifest.md").write_text(
                "# manifest\n\n```yaml\n"
                + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
                + "```\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "snapshot/manifest revision mismatch"):
                image_gen_app._mark_image_prompt_request_freeze_done(
                    run_dir,
                    expected_request_revision=reviewed_revision,
                )

        self.assertEqual(state["review.image_prompt.request_freeze.status"], "frozen")
        self.assertTrue(state["review.image_prompt.request_freeze.request_revision"])

    def test_freeze_finalizes_p600_supervisor_result_through_p650(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            _write_v2_revision_fixture(run_dir)
            result_path = run_dir / "logs/orchestration/p600.supervisor_result.json"
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(
                json.dumps(
                    {
                        "bucket": "p600",
                        "status": "pending",
                        "completed_slots": ["p610", "p620"],
                        "required_artifacts": [
                            {"path": "image_generation_requests.md", "exists": True}
                        ],
                        "state_keys": {"slot.p650.status": "pending"},
                        "review_outputs": [],
                        "next_bucket": None,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            image_gen_app._mark_image_prompt_request_freeze_done(
                run_dir,
                expected_request_revision=_current_request_revision(run_dir),
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))
            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            hard_review = (run_dir / "manifest_review.md").read_text(encoding="utf-8")
            judgment_review = (run_dir / "image_prompt_judgment_review.md").read_text(
                encoding="utf-8"
            )
            hard_aggregate = (
                run_dir
                / "logs/eval/scene_implementation_hard/round_01/aggregated_review.md"
            ).read_text(encoding="utf-8")

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["completed_slots"], ["p610", "p620", "p630", "p640", "p650"])
        self.assertEqual(result["state_keys"]["slot.p650.status"], "done")
        self.assertEqual(state["orchestration.p600.supervisor.status"], "done")
        self.assertEqual(state["slot.p630.status"], "done")
        self.assertEqual(state["slot.p640.status"], "done")
        self.assertEqual(state["eval.scene_implementation_hard.loop.status"], "passed")
        self.assertEqual(state["eval.scene_implementation_judgment.loop.status"], "passed")
        self.assertIn("status: approved", hard_review)
        self.assertIn("status: approved", judgment_review)
        self.assertIn("status: passed", hard_aggregate)
        self.assertNotIn("status: pending", hard_review + judgment_review + hard_aggregate)

    def test_freeze_rejects_unresolved_deferred_scene_reference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            _write_v2_revision_fixture(
                run_dir,
                reference="assets/characters/missing_traveler.png",
                create_reference=False,
            )

            with self.assertRaisesRegex(RuntimeError, "unresolved image request reference"):
                image_gen_app._mark_image_prompt_request_freeze_done(
                    run_dir,
                    expected_request_revision=_current_request_revision(run_dir),
                )

    def test_review_preparation_promotes_deferred_reference_and_freeze_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            reference = "assets/characters/traveler.png"
            manifest = _write_v2_revision_fixture(
                run_dir,
                reference=reference,
                create_reference=False,
            )
            reference_path = run_dir / reference
            reference_path.parent.mkdir(parents=True, exist_ok=True)
            reference_path.write_bytes(b"reference-v1")

            with self.assertRaisesRegex(RuntimeError, "unresolved image request reference"):
                image_gen_app._validate_image_prompt_request_revision(
                    run_dir,
                    manifest,
                    require_resolved_references=True,
                    require_compiled_v2=True,
                )

            image_gen_app._prepare_image_prompt_request_revision_for_review(run_dir)
            frozen = load_request_snapshot(
                run_dir / "image_generation_request_snapshot.json",
                run_dir=run_dir,
                verify_references=True,
            )
            bound_reference = frozen.items[0].references[0]
            self.assertFalse(bound_reference.deferred)
            self.assertIsNotNone(bound_reference.sha256)

            # The semantic report must be authored after the provider-ready
            # snapshot. Freeze itself must not rewrite that reviewed source.
            _write_passing_review_artifacts(run_dir)
            snapshot_path = run_dir / "image_generation_request_snapshot.json"
            snapshot_mtime_ns = snapshot_path.stat().st_mtime_ns
            image_gen_app._mark_image_prompt_request_freeze_done(
                run_dir,
                expected_request_revision=_current_request_revision(run_dir),
            )
            self.assertEqual(snapshot_path.stat().st_mtime_ns, snapshot_mtime_ns)
            scope = json.loads(
                (run_dir / image_gen_app.semantic_review_relpaths("image_prompt")["scope"]).read_text(
                    encoding="utf-8"
                )
            )
            report_path = run_dir / image_gen_app.semantic_review_relpaths("image_prompt")["report"]
            self.assertTrue(
                all(
                    (run_dir / source).stat().st_mtime_ns <= report_path.stat().st_mtime_ns
                    for source in scope["source_artifacts"]
                )
            )

            reference_path.write_bytes(b"reference-v2")
            with self.assertRaisesRegex(RuntimeError, "reference sha256 mismatch"):
                image_gen_app._validate_image_prompt_request_revision(
                    run_dir,
                    manifest,
                    require_resolved_references=True,
                    require_compiled_v2=True,
                )

    def test_freeze_rejects_deterministic_hard_finding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            _write_v2_revision_fixture(run_dir)
            _write_deterministic_review(run_dir, hard_findings=1)

            with self.assertRaisesRegex(RuntimeError, "deterministic image prompt review failed"):
                image_gen_app._mark_image_prompt_request_freeze_done(
                    run_dir,
                    expected_request_revision=_current_request_revision(run_dir),
                )

    def test_deterministic_human_override_does_not_fail_server_hard_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            for name in ("story.md", "script.md", "video_manifest.md"):
                (run_dir / name).write_text(f"# {name}\n", encoding="utf-8")
            _write_deterministic_review(
                run_dir,
                blocking_hard_findings=0,
                hard_finding_details=[
                    (
                        "scene01_cut01",
                        "missing_object_id",
                        "approved exception for a missing object dependency.",
                    )
                ],
                human_review_ok=True,
            )

            errors = image_gen_app._deterministic_image_prompt_hard_gate_errors(run_dir)
            details = image_gen_app._deterministic_image_prompt_hard_findings(run_dir)

        self.assertEqual(errors, [])
        self.assertEqual(details, [])

    def test_deterministic_human_override_without_reason_remains_blocking(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            for name in ("story.md", "script.md", "video_manifest.md"):
                (run_dir / name).write_text(f"# {name}\n", encoding="utf-8")
            _write_deterministic_review(
                run_dir,
                blocking_hard_findings=0,
                hard_finding_details=[
                    ("scene01_cut01", "missing_object_id", "unexplained override.")
                ],
                human_review_ok=True,
                human_review_reason="",
            )

            errors = image_gen_app._deterministic_image_prompt_hard_gate_errors(run_dir)

        self.assertTrue(any("human override reason is missing" in error for error in errors))
        self.assertTrue(any("blocking code mismatch" in error for error in errors))

    def test_deterministic_gate_rejects_synthetic_pass_summary_without_sections(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            for name in ("story.md", "script.md", "video_manifest.md"):
                (run_dir / name).write_text(f"# {name}\n", encoding="utf-8")
            (run_dir / "image_prompt_story_review.md").write_text(
                "\n".join(
                    [
                        "# Image Prompt Story Review",
                        "",
                        "- review_format_version: `deterministic_image_prompt_review_v2`",
                        f"- manifest: `{run_dir / 'video_manifest.md'}`",
                        f"- manifest_sha256: `{image_gen_app._file_sha256(run_dir / 'video_manifest.md')}`",
                        f"- story_sha256: `{image_gen_app._file_sha256(run_dir / 'story.md')}`",
                        f"- script_sha256: `{image_gen_app._file_sha256(run_dir / 'script.md')}`",
                        "- status: `PASS`",
                        "- reviewed_entries: `1`",
                        "- empty_review_scope: `false`",
                        "- entries_with_findings: `0`",
                        "- findings: `0`",
                        "- hard_findings: `0`",
                        "- blocking_hard_findings: `0`",
                        "- soft_findings: `0`",
                        "- unresolved_entries: `0`",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            errors = image_gen_app._deterministic_image_prompt_hard_gate_errors(run_dir)

        self.assertTrue(any("section coverage mismatch" in error for error in errors))

    def test_deterministic_gate_rejects_empty_selector_section(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            for name in ("story.md", "script.md", "video_manifest.md"):
                (run_dir / name).write_text(f"# {name}\n", encoding="utf-8")
            _write_deterministic_review(run_dir)
            report_path = run_dir / "image_prompt_story_review.md"
            report_text = report_path.read_text(encoding="utf-8")
            report_path.write_text(
                report_text[: report_text.index("## scene01_cut01")]
                + "## scene01_cut01\n\n",
                encoding="utf-8",
            )

            errors = image_gen_app._deterministic_image_prompt_hard_gate_errors(run_dir)

        self.assertTrue(any("section output is missing" in error for error in errors))
        self.assertTrue(any("section review status is missing" in error for error in errors))

    def test_deterministic_gate_rejects_summary_that_hides_blocking_section_detail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            for name in ("story.md", "script.md", "video_manifest.md"):
                (run_dir / name).write_text(f"# {name}\n", encoding="utf-8")
            _write_deterministic_review(
                run_dir,
                hard_finding_details=[
                    ("scene01_cut01", "missing_object_id", "blocking detail remains visible.")
                ],
            )
            report_path = run_dir / "image_prompt_story_review.md"
            report_path.write_text(
                report_path.read_text(encoding="utf-8")
                .replace("- status: `FAIL`", "- status: `WARN`")
                .replace("- blocking_hard_findings: `1`", "- blocking_hard_findings: `0`")
                .replace("- unresolved_entries: `1`", "- unresolved_entries: `0`")
                .replace(
                    "- blocking_hard_finding_codes: `missing_object_id`",
                    "- blocking_hard_finding_codes: ``",
                ),
                encoding="utf-8",
            )

            errors = image_gen_app._deterministic_image_prompt_hard_gate_errors(run_dir)

        self.assertTrue(any("blocking finding detail mismatch" in error for error in errors))
        self.assertTrue(any("unresolved selector detail mismatch" in error for error in errors))
        self.assertTrue(any("blocking code mismatch" in error for error in errors))

    def test_deterministic_gate_rejects_report_bound_to_a_different_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            for name in ("story.md", "script.md", "video_manifest.md"):
                (run_dir / name).write_text(f"# {name}\n", encoding="utf-8")
            _write_deterministic_review(run_dir)
            other_manifest = run_dir / "other_manifest.md"
            other_manifest.write_text("# unrelated manifest\n", encoding="utf-8")
            report_path = run_dir / "image_prompt_story_review.md"
            report_path.write_text(
                report_path.read_text(encoding="utf-8").replace(
                    f"- manifest: `{run_dir / 'video_manifest.md'}`",
                    f"- manifest: `{other_manifest}`",
                ),
                encoding="utf-8",
            )

            errors = image_gen_app._deterministic_image_prompt_hard_gate_errors(run_dir)

        self.assertTrue(any("different manifest" in error for error in errors))

    def test_partial_or_stale_deterministic_detail_cannot_localize_the_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            for name in ("story.md", "script.md", "video_manifest.md"):
                (run_dir / name).write_text(f"# {name}\n", encoding="utf-8")
            _write_deterministic_review(
                run_dir,
                hard_findings=2,
                blocking_hard_findings=2,
                unresolved_entries=2,
                reviewed_entries=2,
                hard_finding_details=[
                    ("scene01_cut01", "missing_object_id", "only one of two findings is present.")
                ],
            )
            details = image_gen_app._deterministic_image_prompt_hard_findings(run_dir)

            self.assertFalse(
                image_gen_app._deterministic_image_prompt_hard_finding_details_are_complete(
                    run_dir,
                    details,
                    ["scene1_cut1", "scene1_cut2"],
                )
            )

            _write_deterministic_review(
                run_dir,
                hard_finding_details=[
                    ("scene01_cut01", "missing_object_id", "complete but about to become stale.")
                ],
            )
            report_path = run_dir / "image_prompt_story_review.md"
            report_path.write_text(
                report_path.read_text(encoding="utf-8").replace(
                    "- empty_review_scope: `false`",
                    "- empty_review_scope: `true`",
                ),
                encoding="utf-8",
            )
            details = image_gen_app._deterministic_image_prompt_hard_findings(run_dir)
            self.assertFalse(
                image_gen_app._deterministic_image_prompt_hard_finding_details_are_complete(
                    run_dir,
                    details,
                    ["scene1_cut1", "scene1_cut2"],
                )
            )

            _write_deterministic_review(
                run_dir,
                hard_finding_details=[
                    ("scene01_cut01", "missing_object_id", "complete but about to become stale.")
                ],
            )
            (run_dir / "story.md").write_text("# story\n\nnewer source\n", encoding="utf-8")
            details = image_gen_app._deterministic_image_prompt_hard_findings(run_dir)
            self.assertFalse(
                image_gen_app._deterministic_image_prompt_hard_finding_details_are_complete(
                    run_dir,
                    details,
                    ["scene1_cut1", "scene1_cut2"],
                )
            )

    def test_deterministic_selector_normalization_preserves_dotted_cut_boundaries(self) -> None:
        self.assertEqual(
            image_gen_app._canonical_deterministic_image_prompt_selector("scene03_cut02"),
            "scene3_cut2",
        )
        self.assertEqual(
            image_gen_app._canonical_deterministic_image_prompt_selector("scene3_cut2.1"),
            "scene3_cut2.1",
        )
        self.assertNotEqual(
            image_gen_app._canonical_deterministic_image_prompt_selector("scene3_cut2"),
            image_gen_app._canonical_deterministic_image_prompt_selector("scene3_cut2.1"),
        )

    def test_deterministic_hard_finding_is_composed_into_semantic_repair_result(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            for name in ("story.md", "script.md", "video_manifest.md"):
                (run_dir / name).write_text(f"# {name}\n", encoding="utf-8")
            (run_dir / "state.txt").write_text("", encoding="utf-8")
            finding_code = "missing_object_id"
            finding_message = "source requires glass_slipper but object_ids does not include it."
            _write_deterministic_review(
                run_dir,
                reviewed_entries=2,
                # The deterministic renderer zero-pads numeric selectors;
                # semantic scope uses canonical unpadded request ids.
                hard_finding_details=[("scene01_cut01", finding_code, finding_message)],
            )
            paths = image_gen_app.semantic_review_relpaths("image_prompt")

            def build_pack(command: list[str], **_kwargs: object) -> Mock:
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text(
                    "# collection\n\n## scene1_cut1\n\nfailed entry\n\n## scene1_cut2\n\npassed entry\n",
                    encoding="utf-8",
                )
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "entry_count": 2,
                            "entry_ids": ["scene1_cut1", "scene1_cut2"],
                            "source_artifacts": [
                                "story.md",
                                "script.md",
                                "video_manifest.md",
                                "image_prompt_story_review.md",
                            ],
                            "shards": [
                                {
                                    "shard_id": "scene_1",
                                    "scene_id": "1",
                                    "entry_count": 2,
                                    "entry_ids": ["scene1_cut1", "scene1_cut2"],
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (run_dir / paths["prompt"]).write_text("# prompt\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return Mock(returncode=0, stdout="", stderr="", args=command)

            passed_shard = {
                "shard_id": "scene_1",
                "scene_id": "1",
                "entry_ids": ["scene1_cut1", "scene1_cut2"],
                "status": "passed",
                "errors": [],
                "blocked_entries": [],
                "findings": [],
                "reason_keys": [],
            }
            with (
                patch("server.image_gen_app.subprocess.run", side_effect=build_pack),
                patch(
                    "server.image_gen_app._run_image_prompt_scene_shard_review",
                    AsyncMock(return_value=passed_shard),
                ),
            ):
                result = asyncio.run(
                    image_gen_app._run_image_prompt_sharded_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        attempt=1,
                        max_attempts=2,
                        final_attempt=False,
                    )
                )
            report = (run_dir / paths["report"]).read_text(encoding="utf-8")
            repair_paths = image_gen_app.write_semantic_repair_prompt(
                run_dir,
                "image_prompt",
                round_number=1,
                max_attempts=2,
                errors=result.errors,
            )
            repair_prompt = repair_paths["prompt"].read_text(encoding="utf-8")

        self.assertFalse(result.passed)
        self.assertIn("blocked_entries:\n  - scene1_cut1\nfindings:", report)
        self.assertIn(f"scene1_cut1 [{finding_code}]: {finding_message}", report)
        self.assertIn("deterministic_image_prompt_story_review_failed", report)
        self.assertIn("blocking hard finding", report)
        self.assertIn(finding_code, report)
        self.assertIn("- `scene1_cut1`", repair_prompt)
        self.assertIn(f"scene1_cut1 [{finding_code}]: {finding_message}", repair_prompt)
        self.assertNotIn("- `scene1_cut2`", repair_prompt)

    def test_recompile_from_visual_plan_refreshes_review_metadata_debug_plan_and_story_time(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            old_plan = _plan("旅人が閉じた城門を見る")
            old_payload = compile_image_api_prompt_v2(
                first_frame_visual_plan=old_plan,
                character_ids=["traveler"],
                location_ids=["castle_gate"],
                reference_images=["assets/characters/traveler.png"],
                story_time="",
                review_metadata={
                    "shot_design_contract": {
                        "shot_role": "establishing",
                        "shot_scale": "extreme_closeup",
                        "stale": True,
                    },
                    "cut_location_frame_plan": {
                        "location_zone_description": "古い場所",
                        "stale": True,
                    },
                    "cut_visual_delta": {
                        "this_cut_new_information": "古い出来事",
                        "stale": True,
                    },
                    "blocking_and_interaction": {
                        "character_blocking": {"gaze_target": "古い視線先"},
                        "stale": True,
                    },
                    "review_trace": {"source": "semantic_repair"},
                },
            )
            repaired_plan = _plan("旅人が古い鍵を掲げ、閉じた城門を見る")
            repaired_plan["spatial_composition"]["foreground"] = "古い鍵のある石畳"
            repaired_plan["spatial_composition"]["shot_size"] = "medium_wide"
            repaired_plan["character_state_gate"]["gaze"] = "掲げた古い鍵"
            manifest = {
                "video_metadata": {"time": "江戸時代"},
                "scenes": [
                    {
                        "scene_id": 1,
                        "cuts": [
                            {
                                "cut_id": 1,
                                "selector": "scene1_cut1",
                                "image_generation": {
                                    "character_ids": ["traveler"],
                                    "object_ids": [],
                                    "location_ids": ["castle_gate"],
                                    "references": ["assets/characters/traveler.png"],
                                    "first_frame_visual_plan": repaired_plan,
                                    "api_prompt_payload": old_payload,
                                    "debug_prompt_source": {
                                        "first_frame_visual_plan": old_plan,
                                        "api_prompt_payload": {
                                            "policy_version": "image_api_prompt_v2",
                                            "sha256": old_payload["sha256"],
                                        }
                                    },
                                },
                            }
                        ],
                    }
                ],
            }
            (run_dir / "video_manifest.md").write_text(
                "# manifest\n\n```yaml\n"
                + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
                + "```\n",
                encoding="utf-8",
            )

            compiled = image_gen_app._recompile_image_prompt_payloads_from_plans(run_dir)
            _, updated = load_structured_document(run_dir / "video_manifest.md")
            image_generation = updated["scenes"][0]["cuts"][0]["image_generation"]
            payload = image_generation["api_prompt_payload"]

        self.assertEqual(compiled, ["scene1_cut1"])
        self.assertIn("江戸時代", payload["prompt"])
        self.assertIn("古い鍵", payload["prompt"])
        self.assertEqual(payload["shot_design_contract"]["shot_role"], "character_action")
        self.assertEqual(payload["shot_design_contract"]["shot_scale"], "medium_wide")
        self.assertNotIn("stale", payload["shot_design_contract"])
        self.assertEqual(
            payload["cut_location_frame_plan"]["location_zone_description"],
            "古い鍵のある石畳",
        )
        self.assertEqual(
            payload["cut_visual_delta"]["this_cut_new_information"],
            "旅人が古い鍵を掲げ、閉じた城門を見る",
        )
        self.assertEqual(
            payload["blocking_and_interaction"]["character_blocking"]["gaze_target"],
            "掲げた古い鍵",
        )
        self.assertEqual(payload["review_trace"], {"source": "semantic_repair"})
        self.assertEqual(image_generation["debug_prompt_source"]["first_frame_visual_plan"], repaired_plan)
        self.assertNotEqual(payload["sha256"], old_payload["sha256"])

    def test_image_prompt_repair_synchronizes_requests_before_rereview(self) -> None:
        reviewed_revision = "a" * 64
        failed = SemanticReviewStatus(
            status="failed",
            entry_count=1,
            errors=("image prompt failed",),
        )
        passed = SemanticReviewStatus(status="passed", entry_count=1, errors=())
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            with (
                patch(
                    "server.image_gen_app._run_semantic_review_once",
                    AsyncMock(side_effect=[failed, passed]),
                ),
                patch(
                    "server.image_gen_app._run_semantic_review_producer_repair",
                    AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._synchronize_image_prompt_repair_outputs",
                    Mock(),
                ) as synchronize,
                patch(
                    "server.image_gen_app._mark_image_prompt_request_freeze_done",
                    Mock(),
                ) as freeze,
                patch(
                    "server.image_gen_app._prepare_image_prompt_request_revision_for_review",
                    Mock(return_value=reviewed_revision),
                ) as prepare_revision,
                patch(
                    "server.image_gen_app._assert_image_prompt_request_revision_unchanged",
                    Mock(return_value=reviewed_revision),
                ) as assert_revision,
            ):
                asyncio.run(
                    image_gen_app._run_semantic_review(
                        "job-1",
                        run_dir=run_dir,
                        stage="image_prompt",
                        max_attempts=2,
                    )
                )

        synchronize.assert_called_once_with(run_dir)
        self.assertEqual(
            prepare_revision.call_args_list,
            [
                call(run_dir, provider_ready=True),
                call(run_dir, provider_ready=True),
                call(run_dir, provider_ready=True),
            ],
        )
        self.assertEqual(
            assert_revision.call_args_list,
            [
                call(
                    run_dir,
                    expected_request_revision=reviewed_revision,
                    require_resolved_references=True,
                ),
                call(
                    run_dir,
                    expected_request_revision=reviewed_revision,
                    require_resolved_references=True,
                ),
            ],
        )
        freeze.assert_called_once_with(
            run_dir,
            expected_request_revision=reviewed_revision,
        )

    def test_repaired_asset_requests_are_generated_before_scene_images(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            (run_dir / "state.txt").write_text(
                "review.semantic.image_prompt.repair.asset_refresh_required=true\n",
                encoding="utf-8",
            )
            with (
                patch(
                    "server.image_gen_app._generate_request_outputs",
                    AsyncMock(),
                ) as generate,
                patch(
                    "server.image_gen_app._validate_p560_asset_quality",
                    Mock(),
                ) as validate,
            ):
                asyncio.run(
                    image_gen_app._refresh_image_prompt_repair_assets_if_required(run_dir)
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        generate.assert_awaited_once_with(run_dir=run_dir, kind="asset")
        validate.assert_called_once_with(run_dir)
        self.assertEqual(state["review.semantic.image_prompt.repair.asset_refresh.status"], "done")
        self.assertEqual(state["review.semantic.image_prompt.repair.asset_refresh_required"], "false")

    def test_changed_assets_refresh_before_scene_snapshot_is_rebound_for_rereview(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            (run_dir / "state.txt").write_text("", encoding="utf-8")
            order: list[str] = []

            def synchronize(_run_dir: Path) -> None:
                order.append("sync")
                image_gen_app.append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        "review.semantic.image_prompt.repair.asset_refresh_required": (
                            "true" if order.count("sync") == 1 else "false"
                        )
                    },
                )

            async def refresh(_run_dir: Path) -> None:
                order.append("asset_refresh")

            with (
                patch(
                    "server.image_gen_app._synchronize_image_prompt_repair_outputs",
                    Mock(side_effect=synchronize),
                ),
                patch(
                    "server.image_gen_app._refresh_image_prompt_repair_assets_if_required",
                    AsyncMock(side_effect=refresh),
                ),
                patch(
                    "server.image_gen_app._prepare_image_prompt_request_revision_for_review",
                    Mock(),
                ),
            ):
                asyncio.run(
                    image_gen_app._prepare_image_prompt_repair_revision_for_rereview(run_dir)
                )

        self.assertEqual(order, ["sync", "asset_refresh", "sync"])

    def test_sync_materializes_manifest_asset_addition_and_marks_logical_refresh(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            manifest = _write_v2_revision_fixture(
                run_dir,
                reference="assets/characters/traveler.png",
                create_reference=True,
            )
            manifest["assets"] = {
                "character_bible": [
                    {
                        "character_id": "traveler",
                        "reference_images": ["assets/characters/traveler.png"],
                        "fixed_prompts": ["旅人の全身参照"],
                    }
                ]
            }
            (run_dir / "video_manifest.md").write_text(
                "# manifest\n\n```yaml\n"
                + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
                + "```\n",
                encoding="utf-8",
            )
            image_gen_app._write_asset_request_files(run_dir)

            with patch(
                "server.image_gen_app.subprocess.run",
                return_value=Mock(returncode=0, stdout="", stderr=""),
            ):
                image_gen_app._synchronize_image_prompt_repair_outputs(run_dir)
            unchanged_state = image_gen_app.parse_state_file(run_dir / "state.txt")

            manifest["assets"]["character_bible"].append(
                {
                    "character_id": "gatekeeper",
                    "reference_images": ["assets/characters/gatekeeper.png"],
                    "fixed_prompts": ["門番の全身参照"],
                }
            )
            (run_dir / "video_manifest.md").write_text(
                "# manifest\n\n```yaml\n"
                + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
                + "```\n",
                encoding="utf-8",
            )
            with patch(
                "server.image_gen_app.subprocess.run",
                return_value=Mock(returncode=0, stdout="", stderr=""),
            ):
                image_gen_app._synchronize_image_prompt_repair_outputs(run_dir)

            asset_snapshot = image_gen_app.load_request_snapshot(
                run_dir / "asset_generation_request_snapshot.json",
                run_dir=run_dir,
                verify_references=False,
            )
            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertEqual(
            {item.destination for item in asset_snapshot.items},
            {"assets/characters/traveler.png", "assets/characters/gatekeeper.png"},
        )
        self.assertEqual(
            unchanged_state["review.semantic.image_prompt.repair.asset_refresh_required"],
            "false",
        )
        self.assertEqual(
            state["review.semantic.image_prompt.repair.asset_refresh_required"],
            "true",
        )

    def test_existing_asset_bible_change_recompiles_prompt_and_requires_refresh(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            manifest = _write_v2_revision_fixture(run_dir)
            manifest["assets"] = {
                "character_bible": [
                    {
                        "character_id": "traveler",
                        "reference_images": ["assets/characters/traveler.png"],
                        "fixed_prompts": ["麻布の旅装"],
                        "cinematic": {
                            "role": "城門へ来た旅人",
                            "visual_subject": "旅人の全身参照",
                        },
                    }
                ]
            }
            (run_dir / "video_manifest.md").write_text(
                "# manifest\n\n```yaml\n"
                + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
                + "```\n",
                encoding="utf-8",
            )
            image_gen_app._write_asset_request_files(run_dir)
            before = image_gen_app.load_request_snapshot(
                run_dir / "asset_generation_request_snapshot.json",
                run_dir=run_dir,
                verify_references=False,
            ).items[0]

            manifest["assets"]["character_bible"][0]["fixed_prompts"] = [
                "深紅の絹の旅装、金糸の縁取り"
            ]
            (run_dir / "video_manifest.md").write_text(
                "# manifest\n\n```yaml\n"
                + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
                + "```\n",
                encoding="utf-8",
            )
            with patch(
                "server.image_gen_app.subprocess.run",
                return_value=Mock(returncode=0, stdout="", stderr=""),
            ):
                image_gen_app._synchronize_image_prompt_repair_outputs(run_dir)

            after = image_gen_app.load_request_snapshot(
                run_dir / "asset_generation_request_snapshot.json",
                run_dir=run_dir,
                verify_references=False,
            ).items[0]
            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            _, asset_plan = load_structured_document(run_dir / "asset_plan.md")

        self.assertIn("深紅の絹の旅装", after.prompt)
        self.assertNotEqual(after.source_digest, before.source_digest)
        self.assertNotEqual(after.request_digest, before.request_digest)
        self.assertEqual(
            state["review.semantic.image_prompt.repair.asset_refresh_required"],
            "true",
        )
        self.assertEqual(
            asset_plan["assets"][0]["fixed_prompts"],
            ["深紅の絹の旅装、金糸の縁取り"],
        )

    def test_manifest_projection_drops_stale_explicit_asset_prompt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            manifest = _write_v2_revision_fixture(run_dir)
            manifest["assets"] = {
                "character_bible": [
                    {
                        "character_id": "traveler",
                        "reference_images": ["assets/characters/traveler.png"],
                        "fixed_prompts": ["NEW 深紅の絹の旅装"],
                        "cinematic": {"visual_subject": "NEW 旅人の全身参照"},
                    }
                ]
            }
            (run_dir / "video_manifest.md").write_text(
                "# manifest\n\n```yaml\n"
                + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
                + "```\n",
                encoding="utf-8",
            )
            old_plan = {
                "assets": [
                    {
                        "asset_id": "traveler",
                        "asset_type": "character_reference",
                        "generation_prompt": "OLD EXPLICIT PROMPT",
                        "visual_spec": {"subject": "OLD SUBJECT"},
                        "generation_plan": {
                            "output": "assets/characters/traveler.png",
                            "reference_inputs": [],
                        },
                    }
                ]
            }
            (run_dir / "asset_plan.md").write_text(
                "# Asset Plan\n\n```yaml\n"
                + yaml.safe_dump(old_plan, allow_unicode=True, sort_keys=False)
                + "```\n",
                encoding="utf-8",
            )

            entries = image_gen_app._write_asset_request_files(run_dir)
            _, projected = load_structured_document(run_dir / "asset_plan.md")

        self.assertEqual(len(entries), 1)
        self.assertNotIn("OLD EXPLICIT PROMPT", entries[0]["prompt"])
        self.assertIn("NEW 旅人の全身参照", entries[0]["prompt"])
        self.assertIn("NEW 深紅の絹の旅装", entries[0]["prompt"])
        self.assertIn("江戸時代", entries[0]["prompt"])
        self.assertNotIn("generation_prompt", projected["assets"][0])

    def test_asset_selectors_do_not_collide_when_output_stems_match(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            manifest = _write_v2_revision_fixture(run_dir)
            manifest["assets"] = {
                "character_bible": [
                    {
                        "character_id": "hero_character",
                        "reference_images": ["assets/characters/hero.png"],
                        "fixed_prompts": ["主人公の全身参照"],
                    }
                ],
                "object_bible": [
                    {
                        "object_id": "hero_object",
                        "reference_images": ["assets/objects/hero.png"],
                        "fixed_prompts": ["主人公が持つ紋章"],
                    }
                ],
            }
            (run_dir / "video_manifest.md").write_text(
                "# manifest\n\n```yaml\n"
                + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
                + "```\n",
                encoding="utf-8",
            )

            entries = image_gen_app._write_asset_request_files(run_dir)
            snapshot = image_gen_app.load_request_snapshot(
                run_dir / "asset_generation_request_snapshot.json",
                run_dir=run_dir,
                verify_references=False,
            )

        self.assertEqual(len(entries), 2)
        self.assertEqual(len({entry["selector"] for entry in entries}), 2)
        self.assertEqual(len({item.item_id for item in snapshot.items}), 2)

    def test_sync_refreshes_deterministic_review_for_the_repaired_revision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            _write_v2_revision_fixture(run_dir)
            (run_dir / "story.md").write_text("# story\n", encoding="utf-8")
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            with patch(
                "server.image_gen_app.subprocess.run",
                return_value=Mock(returncode=0, stdout="", stderr=""),
            ) as run:
                image_gen_app._synchronize_image_prompt_repair_outputs(run_dir)

        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands), 2)
        self.assertTrue(commands[0][1].endswith("generate-assets-from-manifest.py"))
        self.assertTrue(commands[1][1].endswith("review-image-prompt-story-consistency.py"))
        self.assertIn(str(run_dir / "video_manifest.md"), commands[1])
        self.assertIn(str(run_dir / "image_prompt_story_review.md"), commands[1])


if __name__ == "__main__":
    unittest.main()
