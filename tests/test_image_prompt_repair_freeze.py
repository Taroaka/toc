from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from server import image_gen_app
from toc.harness import load_structured_document
from toc.image_prompt_compiler import compile_image_api_prompt_v2
from toc.image_request_snapshot import (
    load_request_snapshot,
    materialize_request_snapshot,
    write_request_snapshot_atomic,
)
from toc.run_root_binding import RunRootBindingError, bind_run_root


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
    return manifest


def _current_request_revision(run_dir: Path) -> str:
    return load_request_snapshot(
        run_dir / "image_generation_request_snapshot.json",
        run_dir=run_dir,
        verify_references=False,
    ).request_revision


def _write_p600_supervisor_result_fixture(run_dir: Path) -> None:
    result_path = run_dir / "logs/orchestration/p600.supervisor_result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(
            {
                "bucket": "p600",
                "status": "pending",
                "completed_slots": ["p610", "p620"],
                "required_artifacts": [],
                "state_keys": {"slot.p650.status": "pending"},
                "next_bucket": None,
            }
        )
        + "\n",
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

    def test_recompile_rejects_replaced_bound_run_root_without_touching_replacement(
        self,
    ) -> None:
        """A recompile must remain pinned to its original run inode throughout.

        This swaps the named run root after the compiler has received the visual
        plan but before the recompiled manifest can be published.  The decoy
        replacement is intentionally complete enough to look like a real run;
        it must remain byte-for-byte untouched.
        """

        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            _write_v2_revision_fixture(run_dir)
            original_manifest = (run_dir / "video_manifest.md").read_bytes()
            original_identity = os.stat(run_dir, follow_symlinks=False)

            parked_run = Path(td) / "parked-run"
            replacement = Path(td) / "replacement-run"
            replacement.mkdir()
            replacement_manifest = replacement / "video_manifest.md"
            replacement_manifest.write_text(
                "replacement manifest must not change\n",
                encoding="utf-8",
            )
            replacement_sentinel = replacement / "sentinel.txt"
            replacement_sentinel.write_text(
                "replacement sentinel must not change\n",
                encoding="utf-8",
            )
            expected_replacement_manifest = replacement_manifest.read_bytes()
            expected_replacement_sentinel = replacement_sentinel.read_bytes()

            original_compile = image_gen_app.compile_image_api_prompt_v2
            swapped = False

            def compile_then_replace_root(*args: object, **kwargs: object) -> dict[str, object]:
                nonlocal swapped
                payload = original_compile(*args, **kwargs)
                os.rename(run_dir, parked_run)
                os.rename(replacement, run_dir)
                swapped = True
                return payload

            try:
                with self.assertRaisesRegex(
                    RunRootBindingError,
                    "bound run (directory )?identity changed",
                ):
                    with bind_run_root(
                        run_dir,
                        expected_identity=(
                            original_identity.st_dev,
                            original_identity.st_ino,
                        ),
                    ):
                        with patch(
                            "server.image_gen_app.compile_image_api_prompt_v2",
                            side_effect=compile_then_replace_root,
                        ):
                            image_gen_app._recompile_image_prompt_payloads_from_plans(
                                run_dir
                            )
            finally:
                if swapped:
                    os.rename(run_dir, replacement)
                    os.rename(parked_run, run_dir)

            self.assertEqual(
                (replacement / "video_manifest.md").read_bytes(),
                expected_replacement_manifest,
            )
            self.assertEqual(
                (replacement / "sentinel.txt").read_bytes(),
                expected_replacement_sentinel,
            )
            self.assertEqual(
                (run_dir / "video_manifest.md").read_bytes(),
                original_manifest,
            )

    def test_freeze_binds_exact_manifest_markdown_and_snapshot_revision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            manifest = _write_v2_revision_fixture(run_dir)

            request_revision = _current_request_revision(run_dir)
            _write_p600_supervisor_result_fixture(run_dir)
            image_gen_app._mark_image_prompt_request_freeze_done(
                run_dir,
                expected_request_revision=request_revision,
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
                    expected_request_revision=request_revision,
                )

        self.assertEqual(state["generation.image_prompt.request_freeze.status"], "frozen")
        self.assertTrue(state["generation.image_prompt.request_freeze.request_revision"])

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

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["completed_slots"], ["p610", "p620", "p650"])
        self.assertEqual(result["state_keys"]["slot.p650.status"], "done")
        self.assertEqual(state["orchestration.p600.supervisor.status"], "done")

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

    def test_request_preparation_promotes_deferred_reference_and_freeze_is_read_only(self) -> None:
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

            image_gen_app._prepare_image_prompt_request_revision(run_dir)
            frozen = load_request_snapshot(
                run_dir / "image_generation_request_snapshot.json",
                run_dir=run_dir,
                verify_references=True,
            )
            bound_reference = frozen.items[0].references[0]
            self.assertFalse(bound_reference.deferred)
            self.assertIsNotNone(bound_reference.sha256)

            snapshot_path = run_dir / "image_generation_request_snapshot.json"
            snapshot_mtime_ns = snapshot_path.stat().st_mtime_ns
            _write_p600_supervisor_result_fixture(run_dir)
            image_gen_app._mark_image_prompt_request_freeze_done(
                run_dir,
                expected_request_revision=_current_request_revision(run_dir),
            )
            self.assertEqual(snapshot_path.stat().st_mtime_ns, snapshot_mtime_ns)

            reference_path.write_bytes(b"reference-v2")
            with self.assertRaisesRegex(RuntimeError, "reference sha256 mismatch"):
                image_gen_app._validate_image_prompt_request_revision(
                    run_dir,
                    manifest,
                    require_resolved_references=True,
                    require_compiled_v2=True,
                )

    def test_recompile_from_visual_plan_refreshes_prompt_debug_plan_and_story_time(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            old_plan = _plan("旅人が閉じた城門を見る")
            old_payload = compile_image_api_prompt_v2(
                first_frame_visual_plan=old_plan,
                character_ids=["traveler"],
                location_ids=["castle_gate"],
                reference_images=["assets/characters/traveler.png"],
                story_time="",
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
        self.assertEqual(image_generation["debug_prompt_source"]["first_frame_visual_plan"], repaired_plan)
        self.assertNotEqual(payload["sha256"], old_payload["sha256"])

    def test_sync_materializes_manifest_asset_addition_and_marks_refresh(self) -> None:
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
                image_gen_app._synchronize_image_prompt_requests(run_dir)
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
                image_gen_app._synchronize_image_prompt_requests(run_dir)

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
            unchanged_state["generation.image_prompt.asset_refresh_required"],
            "false",
        )
        self.assertEqual(
            state["generation.image_prompt.asset_refresh_required"],
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
                image_gen_app._synchronize_image_prompt_requests(run_dir)

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
            state["generation.image_prompt.asset_refresh_required"],
            "true",
        )
        self.assertEqual(
            asset_plan["assets"][0]["fixed_prompts"],
            ["深紅の絹の旅装、金糸の縁取り"],
        )

    def test_asset_plan_drops_stale_explicit_prompt(self) -> None:
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
            with (
                patch(
                    "server.image_gen_app._recompile_image_prompt_payloads_from_plans",
                ) as recompile,
                patch(
                    "server.image_gen_app.subprocess.run",
                    return_value=Mock(returncode=0, stdout="", stderr=""),
                ),
            ):
                image_gen_app._synchronize_image_prompt_requests(
                    run_dir,
                    precompiled_selectors=["scene1_cut1"],
                )
            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        recompile.assert_not_called()
        self.assertEqual(
            state["generation.image_prompt.request_sync.compiled_count"],
            "1",
        )
        self.assertEqual(
            state["generation.image_prompt.request_sync.compiled_selectors"],
            "scene1_cut1",
        )

    def test_failed_request_sync_restores_precompiled_manifest_revision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="image_prompt_repair_") as td:
            run_dir = Path(td)
            _write_v2_revision_fixture(run_dir)
            manifest_path = run_dir / "video_manifest.md"
            approved_manifest = manifest_path.read_bytes()

            def fail_after_manifest_write(*_args: object, **_kwargs: object) -> Mock:
                manifest_path.write_text("stale request revision\n", encoding="utf-8")
                return Mock(returncode=1, stdout="", stderr="request failed")

            with (
                patch(
                    "server.image_gen_app._recompile_image_prompt_payloads_from_plans",
                ) as recompile,
                patch(
                    "server.image_gen_app._run_bound_subprocess",
                    side_effect=fail_after_manifest_write,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "request failed"):
                    image_gen_app._synchronize_image_prompt_requests(
                        run_dir,
                        precompiled_selectors=["scene1_cut1"],
                    )

            recompile.assert_not_called()
            self.assertEqual(manifest_path.read_bytes(), approved_manifest)


if __name__ == "__main__":
    unittest.main()
