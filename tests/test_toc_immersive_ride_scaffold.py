import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from toc.review_loop import review_input_snapshot_issues
from toc.review_projection import review_source_fingerprint

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "toc-immersive-ride.py"
SPEC = importlib.util.spec_from_file_location("toc_immersive_ride", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
TOC_IMMERSIVE_RIDE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOC_IMMERSIVE_RIDE)


def parse_state(state_path: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    for raw in state_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        state[key.strip()] = value.strip()
    return state


def markdown_section(text: str, heading: str) -> str:
    start = text.index(heading)
    next_heading = text.find("\n### ", start + len(heading))
    if next_heading == -1:
        return text[start:]
    return text[start:next_heading]


def markdown_subsection(text: str, heading: str) -> str:
    start = text.index(heading)
    next_heading = text.find("\n#### ", start + len(heading))
    next_stage = text.find("\n### ", start + len(heading))
    candidates = [index for index in (next_heading, next_stage) if index != -1]
    end = min(candidates) if candidates else len(text)
    return text[start:end]


class TestTocImmersiveRideScaffold(unittest.TestCase):
    P400_REVIEW_STAGES = (
        "scene_set",
        "scene_detail",
        "cut_blueprint",
        "script",
        "production_readiness",
    )

    def run_scaffold(
        self,
        base: Path,
        stage: str,
        *,
        experience: str = "cloud_island_walk",
        force: bool = True,
    ) -> Path:
        command = [
            sys.executable,
            "scripts/toc-immersive-ride.py",
            "--topic",
            "テスト トピック",
            "--timestamp",
            "20990101_0000",
            "--base",
            str(base),
            "--stage",
            stage,
            "--experience",
            experience,
            "--review-policy",
            "drafts",
        ]
        if force:
            command.append("--force")
        subprocess.run(command, check=True, capture_output=True, text=True)
        return base / "テスト_トピック_20990101_0000"

    def assert_review_snapshot_binds_skeleton_manifest(self, run_dir: Path, stage: str) -> None:
        manifest_path = run_dir / "video_manifest.md"
        self.assertTrue(manifest_path.exists())
        self.assertIn("manifest_phase: skeleton", manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            parse_state(run_dir / "state.txt")["artifact.video_manifest"],
            str(manifest_path.resolve()),
        )

        snapshot_path = run_dir / "logs" / "eval" / stage / "round_01" / "review_input_snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(
            review_input_snapshot_issues(
                run_dir=run_dir,
                stage=stage,
                round_number=1,
            ),
            [],
        )
        sources = {str(item["path"]): item for item in snapshot["source_artifacts"]}
        expected_manifest_fingerprint = review_source_fingerprint(
            manifest_path,
            artifact_relpath="video_manifest.md",
            review_kind="review_loop",
            stage=stage,
        )
        self.assertEqual(
            sources["video_manifest.md"]["sha256"],
            expected_manifest_fingerprint.sha256,
        )
        self.assertEqual(
            sources["video_manifest.md"]["fingerprint_policy"],
            expected_manifest_fingerprint.policy,
        )
        state = parse_state(run_dir / "state.txt")
        self.assertEqual(state[f"eval.{stage}.loop.current_round"], "1")
        self.assertEqual(
            state[f"eval.{stage}.loop.round_01.input_digest"],
            snapshot["input_digest"],
        )

    def approve_existing_p435_run(self, run_dir: Path) -> dict[Path, bytes]:
        manifest_path = run_dir / "video_manifest.md"
        TOC_IMMERSIVE_RIDE.ensure_production_manifest_file(manifest_path)
        approval_updates = {
            "eval.p400_readiness.status": "approved",
            "eval.p400_readiness.reason_keys": "",
            "review.script.scene_set.status": "approved",
            "review.script.scene_detail.status": "approved",
            "review.script.cut.status": "approved",
            "review.script.production_readiness.status": "approved",
            "slot.p410.status": "done",
            "slot.p420.status": "done",
            "slot.p430.status": "done",
            "slot.p435.status": "done",
            "slot.p450.status": "done",
        }
        evidence: dict[Path, bytes] = {}
        for stage in self.P400_REVIEW_STAGES:
            review_updates = TOC_IMMERSIVE_RIDE.materialize_review_loop_prompts(
                run_dir,
                stage=stage,
            )
            approval_updates.update(review_updates)
            approval_updates[f"eval.{stage}.loop.status"] = "passed"
            approval_updates[f"eval.{stage}.loop.current_round"] = "1"
            final_report = run_dir / TOC_IMMERSIVE_RIDE.final_review_relpath(stage)
            final_report.write_text(
                f"# {stage} approved evidence\n\nstatus: passed\n",
                encoding="utf-8",
            )
            snapshot_path = (
                run_dir
                / "logs"
                / "eval"
                / stage
                / "round_01"
                / "review_input_snapshot.json"
            )
            evidence[final_report] = final_report.read_bytes()
            evidence[snapshot_path] = snapshot_path.read_bytes()
        TOC_IMMERSIVE_RIDE.append_state_block(run_dir / "state.txt", approval_updates)
        return evidence

    def continue_approved_run(self, run_dir: Path, stage: str) -> None:
        argv = [
            "toc-immersive-ride.py",
            "--topic",
            "テスト トピック",
            "--timestamp",
            "20990101_0000",
            "--run-dir",
            str(run_dir),
            "--base",
            str(run_dir.parent),
            "--stage",
            stage,
            "--experience",
            "cloud_island_walk",
            "--review-policy",
            "drafts",
        ]

        def assert_current_production_p400(candidate: Path) -> None:
            manifest = (candidate / "video_manifest.md").read_text(encoding="utf-8")
            self.assertIn("manifest_phase: production", manifest)
            self.assertNotIn("manifest_phase: skeleton", manifest)
            for review_stage in self.P400_REVIEW_STAGES:
                self.assertEqual(
                    review_input_snapshot_issues(
                        run_dir=candidate,
                        stage=review_stage,
                        round_number=1,
                    ),
                    [],
                    review_stage,
                )

        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(TOC_IMMERSIVE_RIDE, "maybe_run_stage_grounding"),
            mock.patch.object(
                TOC_IMMERSIVE_RIDE,
                "require_fresh_p400_readiness",
                side_effect=assert_current_production_p400,
            ),
        ):
            TOC_IMMERSIVE_RIDE.main()

    def test_stage_target_contract_normalizes_big_stages_to_handoff_slots(self) -> None:
        cases = {
            "p100": "p130",
            "100": "p130",
            "p300": "p330",
            "300": "p330",
            "p400": "p450",
            "400": "p450",
            "p600": "p680",
            "600": "p680",
            "p700": "p750",
            "700": "p750",
            "p800": "p850",
            "800": "p850",
            "p900": "p930",
            "900": "p930",
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(TOC_IMMERSIVE_RIDE.normalize_stage_target(raw), expected)

    def test_stage_target_contract_keeps_fine_slots_exact(self) -> None:
        for slot in ("p110", "p130", "p310", "p320", "p330", "p450", "p570"):
            with self.subTest(slot=slot):
                self.assertEqual(TOC_IMMERSIVE_RIDE.normalize_stage_target(slot), slot)

    def test_scaffold_creates_expected_files(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "p400",
                    "--experience",
                    "cinematic_story",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "p000_index.md").exists())
            self.assertTrue((run_dir / "state.txt").exists())
            self.assertTrue((run_dir / "run_status.json").exists())
            self.assertTrue((run_dir / "research.md").exists())
            self.assertTrue((run_dir / "story.md").exists())
            self.assertTrue((run_dir / "visual_value.md").exists())
            self.assertTrue((run_dir / "script.md").exists())
            self.assertTrue((run_dir / "video_manifest.md").exists())
            self.assertTrue((run_dir / "assets" / "characters").is_dir())
            self.assertTrue((run_dir / "assets" / "objects").is_dir())
            self.assertTrue((run_dir / "assets" / "scenes").is_dir())
            self.assertTrue((run_dir / "assets" / "audio").is_dir())
            self.assertTrue((run_dir / "logs" / "grounding" / "research.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "story.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "script.json").exists())
            self.assertFalse((run_dir / "logs" / "grounding" / "asset.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "script.readset.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "script.audit.json").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("status=P400", state)
            self.assertIn("runtime.stage=immersive_ride_scaffolded_p450", state)
            parsed_state = parse_state(run_dir / "state.txt")
            self.assertEqual(parsed_state["stage.script.status"], "awaiting_approval")
            self.assertEqual(parsed_state["slot.p450.status"], "pending")
            index_text = (run_dir / "p000_index.md").read_text(encoding="utf-8")
            p400_section = markdown_section(index_text, "### p400 Script / Narration Text / Human Changes")
            p450_section = markdown_subsection(index_text, "#### p450 Skeleton Manifest Materialization")
            self.assertIn("- current_state: `awaiting_approval (script)`", p400_section)
            self.assertIn("- status: `pending`", p450_section)
            manifest = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            self.assertIn("manifest_phase: skeleton", manifest)
            self.assertIn('reference_id: "protagonist_front_ref"', manifest)
            self.assertIn("全身（頭からつま先まで）", manifest)
            self.assertIn("scene_id: 10", manifest)

    def test_scaffold_cloud_island_experience_uses_template(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "p400",
                    "--experience",
                    "cloud_island_walk",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            manifest_path = run_dir / "video_manifest.md"
            self.assertTrue(manifest_path.exists())
            manifest = manifest_path.read_text(encoding="utf-8")
            self.assertIn("manifest_phase: skeleton", manifest)
            self.assertIn('experience: "cloud_island_walk"', manifest)
            self.assertIn("一人称POVで前進しながら歩く", manifest)
            self.assertIn("画面内テキスト", manifest)

    def test_scaffold_world_walk_requires_source_run(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--experience",
                    "world_walk",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--source-run", result.stderr)

    def test_scaffold_world_walk_experience_uses_source_run_template(self) -> None:
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with (
            tempfile.TemporaryDirectory(prefix="toc_test_out_") as td,
            tempfile.TemporaryDirectory(prefix="world_walk_source_", dir=output_root) as source_td,
        ):
            base = Path(td) / "out"
            source_run = Path(source_td)
            (source_run / "assets" / "characters").mkdir(parents=True, exist_ok=True)
            (source_run / "story.md").write_text("# 物語\n\nTODO source\n", encoding="utf-8")
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "桃太郎の世界観を散歩してみた",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--source-run",
                    str(source_run),
                    "--experience",
                    "world_walk",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "桃太郎の世界観を散歩してみた_20990101_0000"
            manifest_path = run_dir / "video_manifest.md"
            self.assertTrue(manifest_path.exists())
            manifest = manifest_path.read_text(encoding="utf-8")
            self.assertIn("manifest_phase: skeleton", manifest)
            self.assertIn('experience: "world_walk"', manifest)
            source_run_relative = f"output/{source_run.name}"
            self.assertIn(f'source_run: "{source_run_relative}"', manifest)
            self.assertIn(f'source_assets: "{source_run_relative}/assets"', manifest)
            self.assertIn("観察者POV", manifest)
            self.assertIn("物語が進まない asset 内散歩", manifest)
            self.assertIn("参照キャラが遠景に現れる", manifest)
            parsed_state = parse_state(run_dir / "state.txt")
            self.assertEqual(parsed_state["immersive.experience"], "world_walk")
            self.assertEqual(parsed_state["immersive.source_run"], source_run_relative)

    def test_scaffold_rejects_timestamp_traversal_without_writing_outside_base(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_ride_timestamp_") as td:
            root = Path(td)
            base = root / "output"
            base.mkdir()
            escaped = root / "escaped"

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "test",
                    "--timestamp",
                    "../../../escaped",
                    "--base",
                    str(base),
                    "--stage",
                    "p100",
                    "--review-policy",
                    "drafts",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("timestamp", result.stderr.lower())
            self.assertFalse(escaped.exists())
            self.assertEqual(list(base.iterdir()), [])

    def test_scaffold_rejects_run_dir_outside_base(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_ride_run_dir_") as td:
            root = Path(td)
            base = root / "output"
            base.mkdir()
            escaped = root / "escaped"

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "test",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--run-dir",
                    str(escaped),
                    "--stage",
                    "p100",
                    "--review-policy",
                    "drafts",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--run-dir", result.stderr)
            self.assertFalse(escaped.exists())
            self.assertEqual(list(base.iterdir()), [])

    def test_scaffold_rejects_broken_and_live_artifact_symlinks_without_external_write(
        self,
    ) -> None:
        for label, target_exists, force in (
            ("broken", False, False),
            ("live", True, True),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix=f"toc_ride_{label}_symlink_"
            ) as td:
                root = Path(td)
                base = root / "output"
                run_dir = base / "test_20990101_0000"
                run_dir.mkdir(parents=True)
                outside = root / "outside-research.md"
                if target_exists:
                    outside.write_text("outside-original\n", encoding="utf-8")
                (run_dir / "research.md").symlink_to(outside)
                command = [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "test",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "p100",
                    "--review-policy",
                    "drafts",
                ]
                if force:
                    command.append("--force")

                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertTrue((run_dir / "research.md").is_symlink())
                if target_exists:
                    self.assertEqual(
                        outside.read_text(encoding="utf-8"),
                        "outside-original\n",
                    )
                else:
                    self.assertFalse(outside.exists())

    def test_rewind_cleanup_rejects_symlinked_ancestor_without_external_deletion(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_ride_cleanup_") as td:
            root = Path(td)
            run_dir = root / "run"
            outside = root / "outside"
            run_dir.mkdir()
            victim_dir = outside / "eval" / "scene_set"
            victim_dir.mkdir(parents=True)
            victim = victim_dir / "victim.txt"
            victim.write_text("preserve\n", encoding="utf-8")
            (run_dir / "logs").symlink_to(outside, target_is_directory=True)

            with self.assertRaises((OSError, ValueError)):
                TOC_IMMERSIVE_RIDE.reset_p400_review_handoff(
                    run_dir,
                    experience="cinematic_story",
                    source_run=None,
                )

            self.assertEqual(victim.read_text(encoding="utf-8"), "preserve\n")
            self.assertTrue((run_dir / "logs").is_symlink())

    def test_scaffold_rejects_run_root_replacement_before_later_writes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_ride_root_swap_") as td:
            root = Path(td)
            base = root / "output"
            base.mkdir()
            run_dir = base / "test_20990101_0000"
            original_run = base / "test_20990101_0000-original"
            outside = root / "outside"
            outside.mkdir()
            outside_state = outside / "state.txt"
            outside_state.write_text("outside-original\n", encoding="utf-8")
            swapped = False

            def replace_root(
                candidate: Path,
                _stage: str,
                *,
                flow: str,
                fatal: bool = True,
            ) -> None:
                nonlocal swapped
                self.assertEqual(flow, "immersive")
                self.assertTrue(fatal)
                if swapped:
                    return
                swapped = True
                candidate.rename(original_run)
                candidate.symlink_to(outside, target_is_directory=True)

            argv = [
                "toc-immersive-ride.py",
                "--topic",
                "test",
                "--timestamp",
                "20990101_0000",
                "--base",
                str(base),
                "--stage",
                "p100",
                "--review-policy",
                "drafts",
            ]
            try:
                with (
                    mock.patch.object(sys, "argv", argv),
                    mock.patch.object(
                        TOC_IMMERSIVE_RIDE,
                        "maybe_run_stage_grounding",
                        side_effect=replace_root,
                    ),
                    self.assertRaises((OSError, ValueError)),
                ):
                    TOC_IMMERSIVE_RIDE.main()
                self.assertTrue(swapped)
                self.assertEqual(
                    outside_state.read_text(encoding="utf-8"),
                    "outside-original\n",
                )
                self.assertEqual(
                    sorted(path.name for path in outside.iterdir()),
                    ["state.txt"],
                )
            finally:
                if run_dir.is_symlink():
                    run_dir.unlink()
                if original_run.exists():
                    original_run.rename(run_dir)

    def test_world_walk_same_path_source_replacement_invalidates_p400_approval(
        self,
    ) -> None:
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with (
            tempfile.TemporaryDirectory(prefix="toc_ride_target_") as td,
            tempfile.TemporaryDirectory(
                prefix="toc_ride_source_",
                dir=output_root,
            ) as source_td,
        ):
            base = Path(td) / "output"
            base.mkdir()
            source_run = Path(source_td)
            source_backup = source_run.with_name(source_run.name + "-original")
            source_asset = source_run / "assets" / "characters" / "hero.png"
            source_asset.parent.mkdir(parents=True)
            source_asset.write_bytes(b"source-v1")
            (source_run / "story.md").write_text(
                "# Source Story\n\nversion one\n",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                "scripts/toc-immersive-ride.py",
                "--topic",
                "world walk",
                "--timestamp",
                "20990101_0000",
                "--base",
                str(base),
                "--source-run",
                f"output/{source_run.name}",
                "--experience",
                "world_walk",
                "--stage",
                "p435",
                "--review-policy",
                "drafts",
                "--force",
            ]
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
            run_dir = base / "world_walk_20990101_0000"
            self.approve_existing_p435_run(run_dir)
            state_before = parse_state(run_dir / "state.txt")
            receipt_before = state_before[
                "immersive.source_receipt.bundle_sha256"
            ]
            root_identity_before = state_before[
                "immersive.source_receipt.root_identity"
            ]
            self.assertTrue((run_dir / "production_readiness_review.md").exists())

            source_run.rename(source_backup)
            source_run.mkdir()
            replacement_asset = (
                source_run / "assets" / "characters" / "hero.png"
            )
            replacement_asset.parent.mkdir(parents=True)
            replacement_asset.write_bytes(b"source-v2")
            (source_run / "story.md").write_text(
                "# Source Story\n\nversion two\n",
                encoding="utf-8",
            )
            try:
                subprocess.run(
                    [arg for arg in command if arg != "--force"],
                    check=True,
                    capture_output=True,
                    text=True,
                )

                state_after = parse_state(run_dir / "state.txt")
                receipt_after = state_after[
                    "immersive.source_receipt.bundle_sha256"
                ]
                self.assertNotEqual(receipt_after, receipt_before)
                self.assertNotEqual(
                    state_after["immersive.source_receipt.root_identity"],
                    root_identity_before,
                )
                self.assertEqual(
                    state_after["eval.p400_readiness.status"],
                    "changes_requested",
                )
                self.assertEqual(
                    state_after["eval.production_readiness.loop.status"],
                    "running",
                )
                self.assertFalse(
                    (run_dir / "production_readiness_review.md").exists()
                )
                manifest = (run_dir / "video_manifest.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn(receipt_after, manifest)
                self.assertEqual(
                    review_input_snapshot_issues(
                        run_dir=run_dir,
                        stage="production_readiness",
                        round_number=1,
                    ),
                    [],
                )
            finally:
                shutil.rmtree(source_run)
                source_backup.rename(source_run)

    def test_world_walk_wrapper_derives_topic_from_source_run(self) -> None:
        import tempfile

        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with (
            tempfile.TemporaryDirectory(prefix="toc_test_out_") as td,
            tempfile.TemporaryDirectory(prefix="浦島太郎_", dir=output_root) as source_td,
        ):
            base = Path(td) / "out"
            source_run = Path(source_td)
            (source_run / "assets").mkdir(parents=True, exist_ok=True)
            (source_run / "story.md").write_text("# 物語\n\nTODO source\n", encoding="utf-8")
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-world-walk.py",
                    "--source-run",
                    str(source_run),
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "script",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            derived_title = f"{source_run.name}の世界観を散歩してみた"
            run_dir = base / (
                f"{TOC_IMMERSIVE_RIDE.sanitize_topic(derived_title)}"
                "_20990101_0000"
            )
            manifest = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            self.assertIn(f'topic: "{derived_title}"', manifest)
            self.assertIn('experience: "world_walk"', manifest)

    def test_scaffold_accepts_numeric_p300_stage_target_as_visual_handoff(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "300",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "research.md").exists())
            self.assertTrue((run_dir / "story.md").exists())
            self.assertTrue((run_dir / "visual_value.md").exists())
            self.assertFalse((run_dir / "script.md").exists())
            self.assertFalse((run_dir / "video_manifest.md").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("runtime.stage_target=p300", state)
            self.assertIn("runtime.stop_slot=p330", state)
            parsed_state = parse_state(run_dir / "state.txt")
            self.assertEqual(parsed_state["runtime.scaffold.status"], "draft")
            self.assertEqual(parsed_state["runtime.scaffold.content_status"], "placeholder")
            self.assertEqual(parsed_state["stage.research.status"], "pending")
            self.assertEqual(parsed_state["stage.story.status"], "pending")
            self.assertEqual(parsed_state["stage.visual_value.status"], "awaiting_approval")
            self.assertEqual(parsed_state["review.visual_value.status"], "pending")
            self.assertEqual(parsed_state["slot.p120.status"], "pending")
            self.assertEqual(parsed_state["slot.p220.status"], "pending")
            self.assertEqual(parsed_state["slot.p310.status"], "pending")
            self.assertEqual(parsed_state["slot.p320.status"], "pending")
            self.assertEqual(parsed_state["slot.p330.status"], "pending")
            self.assertEqual(parsed_state["artifact.visual_value.status"], "scaffold")
            self.assertEqual(parsed_state["eval.visual_value.loop.status"], "running")
            self.assertEqual(parsed_state["eval.visual_value.loop.current_round"], "1")
            self.assertEqual(parsed_state["eval.visual_value.loop.max_rounds"], "5")
            self.assertTrue((run_dir / "logs" / "eval" / "visual_value" / "round_01" / "prompts" / "critic_1.prompt.md").exists())
            self.assertTrue((run_dir / "logs" / "eval" / "visual_value" / "round_01" / "prompts" / "aggregator.prompt.md").exists())
            index_text = (run_dir / "p000_index.md").read_text(encoding="utf-8")
            self.assertIn("next_required_human_review: `visual_value.md", index_text)
            self.assertIn("#### p310 Visual Value", index_text)
            self.assertIn("#### p320 Visual Planning Eval/Improve Loop", index_text)
            self.assertIn("#### p330 Visual Planning Appendix", index_text)

    def test_scaffold_accepts_prefixed_numeric_stage_target(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "p300",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "visual_value.md").exists())
            self.assertFalse((run_dir / "script.md").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("runtime.stage_target=p300", state)
            self.assertIn("runtime.stop_slot=p330", state)

    def test_scaffold_stage_targets_record_placeholder_authoring_status(self) -> None:
        import tempfile

        expectations = {
            "100": {
                "stage.research.status": "awaiting_approval",
                "review.research.status": "pending",
                "slot.p120.status": "pending",
                "slot.p130.status": "pending",
                "artifact.research.status": "scaffold",
            },
            "200": {
                "stage.research.status": "pending",
                "stage.story.status": "awaiting_approval",
                "review.story.status": "pending",
                "slot.p120.status": "pending",
                "slot.p220.status": "pending",
                "slot.p230.status": "pending",
                "artifact.story.status": "scaffold",
            },
        }
        for stage, expected in expectations.items():
            with self.subTest(stage=stage):
                with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
                    base = Path(td) / "out"
                    base.mkdir(parents=True, exist_ok=True)

                    subprocess.run(
                        [
                            sys.executable,
                            "scripts/toc-immersive-ride.py",
                            "--topic",
                            "テスト トピック",
                            "--timestamp",
                            "20990101_0000",
                            "--base",
                            str(base),
                            "--stage",
                            stage,
                            "--force",
                            "--review-policy",
                            "drafts",
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )

                    run_dir = base / "テスト_トピック_20990101_0000"
                    state = parse_state(run_dir / "state.txt")
                    self.assertEqual(state["runtime.scaffold.status"], "draft")
                    self.assertEqual(state["runtime.scaffold.content_status"], "placeholder")
                    for key, value in expected.items():
                        self.assertEqual(state[key], value)

    def test_scaffold_numeric_p400_stops_at_script_handoff_slot(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "400",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "script.md").exists())
            self.assertTrue((run_dir / "video_manifest.md").exists())
            self.assertFalse((run_dir / "logs" / "grounding" / "narration.json").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("runtime.stage_target=p400", state)
            self.assertIn("runtime.stop_slot=p450", state)
            self.assertIn("review.script.scene_set.status=pending", state)
            self.assertIn("review.script.scene_detail.status=pending", state)
            self.assertIn("review.script.cut.status=pending", state)
            self.assertIn("review.script.production_readiness.status=pending", state)
            parsed_state = parse_state(run_dir / "state.txt")
            for review_stage in (
                "scene_set",
                "scene_detail",
                "cut_blueprint",
                "script",
                "production_readiness",
            ):
                self.assertEqual(parsed_state[f"eval.{review_stage}.loop.status"], "running")
            self.assertEqual(parsed_state["slot.p410.status"], "pending")
            self.assertEqual(parsed_state["slot.p435.status"], "pending")
            self.assertEqual(parsed_state["slot.p450.status"], "pending")

    def test_scaffold_p410_materializes_only_scene_reviews(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "p410",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "logs" / "eval" / "scene_set" / "round_01" / "prompts" / "critic_1.prompt.md").exists())
            self.assertTrue((run_dir / "logs" / "eval" / "scene_detail" / "round_01" / "prompts" / "critic_1.prompt.md").exists())
            self.assertFalse((run_dir / "logs" / "eval" / "cut_blueprint").exists())
            self.assertFalse((run_dir / "logs" / "eval" / "script").exists())
            self.assert_review_snapshot_binds_skeleton_manifest(run_dir, "scene_set")
            self.assert_review_snapshot_binds_skeleton_manifest(run_dir, "scene_detail")
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["eval.scene_set.loop.status"], "running")
            self.assertEqual(state["eval.scene_detail.loop.status"], "running")
            self.assertEqual(state["slot.p410.status"], "pending")
            self.assertEqual(state["slot.p450.status"], "pending")

    def test_scaffold_p420_materializes_cut_review_but_not_script_review(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "p420",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "logs" / "eval" / "scene_set" / "round_01" / "prompts" / "critic_1.prompt.md").exists())
            self.assertTrue((run_dir / "logs" / "eval" / "scene_detail" / "round_01" / "prompts" / "critic_1.prompt.md").exists())
            self.assertTrue((run_dir / "logs" / "eval" / "cut_blueprint" / "round_01" / "prompts" / "critic_1.prompt.md").exists())
            self.assertFalse((run_dir / "logs" / "eval" / "script").exists())
            self.assertFalse((run_dir / "logs" / "eval" / "production_readiness").exists())
            self.assert_review_snapshot_binds_skeleton_manifest(run_dir, "cut_blueprint")
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["eval.cut_blueprint.loop.status"], "running")
            self.assertEqual(state["slot.p420.status"], "pending")
            self.assertEqual(state["slot.p450.status"], "pending")

    def test_scaffold_p435_materializes_production_readiness_after_script_review(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "p435",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "logs" / "eval" / "script" / "round_01" / "prompts" / "critic_1.prompt.md").exists())
            self.assertTrue((run_dir / "logs" / "eval" / "production_readiness" / "round_01" / "prompts" / "critic_1.prompt.md").exists())
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["runtime.stop_slot"], "p435")
            self.assertEqual(state["review.script.production_readiness.status"], "pending")
            self.assertEqual(state["eval.production_readiness.loop.status"], "running")
            self.assertEqual(state["slot.p435.status"], "pending")
            self.assertEqual(state["slot.p450.status"], "pending")
            self.assert_review_snapshot_binds_skeleton_manifest(run_dir, "script")
            self.assert_review_snapshot_binds_skeleton_manifest(run_dir, "production_readiness")

    def test_scaffold_p430_materializes_script_review_without_production_readiness(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            self.run_scaffold(base, "p435")
            run_dir = self.run_scaffold(base, "p430")

            for review_stage in ("scene_set", "scene_detail", "cut_blueprint", "script"):
                self.assert_review_snapshot_binds_skeleton_manifest(run_dir, review_stage)
            self.assertFalse((run_dir / "logs" / "eval" / "production_readiness").exists())
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["runtime.stop_slot"], "p430")
            self.assertEqual(state["eval.script.loop.status"], "running")
            self.assertEqual(state["eval.production_readiness.loop.status"], "pending")
            self.assertEqual(state["eval.production_readiness.loop.current_round"], "0")
            self.assertEqual(state["eval.production_readiness.loop.round_01.input_snapshot"], "")
            self.assertEqual(state["slot.p430.status"], "pending")
            self.assertEqual(state["slot.p435.status"], "pending")
            self.assertEqual(state["slot.p450.status"], "pending")

    def test_scaffold_p410_rewind_invalidates_later_p400_reviews_and_approval(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            run_dir = self.run_scaffold(base, "p435")
            for review_stage in ("cut_blueprint", "script", "production_readiness"):
                (run_dir / f"{review_stage}_review.md").write_text("status: passed\n", encoding="utf-8")
            TOC_IMMERSIVE_RIDE.append_state_block(
                run_dir / "state.txt",
                {
                    "eval.p400_readiness.status": "approved",
                    "eval.p400_readiness.reason_keys": "",
                    "review.script.scene_set.status": "approved",
                    "review.script.scene_detail.status": "approved",
                    "review.script.cut.status": "approved",
                    "review.script.production_readiness.status": "approved",
                    "slot.p410.status": "done",
                    "slot.p420.status": "done",
                    "slot.p430.status": "done",
                    "slot.p435.status": "done",
                    "slot.p450.status": "done",
                },
            )

            self.run_scaffold(base, "p410")

            self.assertTrue((run_dir / "logs" / "eval" / "scene_set").exists())
            self.assertTrue((run_dir / "logs" / "eval" / "scene_detail").exists())
            for review_stage in ("cut_blueprint", "script", "production_readiness"):
                self.assertFalse((run_dir / "logs" / "eval" / review_stage).exists())
                self.assertFalse((run_dir / f"{review_stage}_review.md").exists())

            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["eval.p400_readiness.status"], "changes_requested")
            self.assertEqual(state["eval.p400_readiness.reason_keys"], "p400.review_loop_integrity")
            self.assertEqual(state["eval.scene_set.loop.status"], "running")
            self.assertEqual(state["eval.scene_detail.loop.status"], "running")
            for review_stage in ("cut_blueprint", "script", "production_readiness"):
                self.assertEqual(state[f"eval.{review_stage}.loop.status"], "pending")
                self.assertEqual(state[f"eval.{review_stage}.loop.current_round"], "0")
                self.assertEqual(state[f"eval.{review_stage}.loop.round_01.input_snapshot"], "")
                self.assertEqual(state[f"eval.{review_stage}.loop.round_01.input_digest"], "")
            self.assertEqual(state["review.script.scene_set.status"], "pending")
            self.assertEqual(state["review.script.scene_detail.status"], "pending")
            self.assertEqual(state["review.script.cut.status"], "pending")
            self.assertEqual(state["review.script.production_readiness.status"], "pending")
            for slot in ("p410", "p420", "p430", "p435", "p450"):
                self.assertEqual(state[f"slot.{slot}.status"], "pending")

    def test_scaffold_non_force_rewind_demotes_existing_production_manifest(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            run_dir = self.run_scaffold(base, "p435")
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8").replace(
                    "manifest_phase: skeleton",
                    "manifest_phase: production",
                    1,
                ),
                encoding="utf-8",
            )

            self.run_scaffold(base, "p410", force=False)

            self.assert_review_snapshot_binds_skeleton_manifest(run_dir, "scene_set")
            self.assert_review_snapshot_binds_skeleton_manifest(run_dir, "scene_detail")
            manifest = manifest_path.read_text(encoding="utf-8")
            self.assertIn("manifest_phase: skeleton", manifest)
            self.assertNotIn("manifest_phase: production", manifest)
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(
                state["slot.p450.note"],
                "review-bound skeleton exists; p450 readiness handoff remains pending before p500",
            )
            self.assertEqual(state["slot.p450.status"], "pending")

    def test_scaffold_forced_early_rewind_refreshes_experience_state(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            run_dir = self.run_scaffold(base, "p435", experience="cloud_island_walk")
            self.assertEqual(parse_state(run_dir / "state.txt")["immersive.experience"], "cloud_island_walk")
            TOC_IMMERSIVE_RIDE.append_state_block(
                run_dir / "state.txt",
                {"immersive.source_run": "output/stale_source_run"},
            )

            self.run_scaffold(base, "p410", experience="cinematic_story")

            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["immersive.experience"], "cinematic_story")
            self.assertEqual(state["immersive.source_run"], "")
            manifest = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            self.assertIn('experience: "cinematic_story"', manifest)

    def test_approved_p435_continues_to_p500_without_rewriting_p400_evidence(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)
            run_dir = self.run_scaffold(base, "p435")
            evidence_before = self.approve_existing_p435_run(run_dir)
            state_before = parse_state(run_dir / "state.txt")
            manifest_before = (run_dir / "video_manifest.md").read_bytes()

            self.continue_approved_run(run_dir, "p500")

            self.assertTrue((run_dir / "asset_plan.md").exists())
            self.assertEqual((run_dir / "video_manifest.md").read_bytes(), manifest_before)
            for path, content in evidence_before.items():
                self.assertTrue(path.exists(), path)
                self.assertEqual(path.read_bytes(), content, path)
            state = parse_state(run_dir / "state.txt")
            for stage in self.P400_REVIEW_STAGES:
                self.assertEqual(state[f"eval.{stage}.loop.status"], "passed", stage)
                self.assertEqual(
                    state[f"eval.{stage}.loop.round_01.input_digest"],
                    state_before[f"eval.{stage}.loop.round_01.input_digest"],
                    stage,
                )
            self.assertEqual(state["slot.p435.status"], "done")
            self.assertEqual(state["eval.p400_readiness.status"], "approved")

    def test_approved_p435_continues_to_p610_with_production_bound_p400_evidence(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)
            run_dir = self.run_scaffold(base, "p435")
            evidence_before = self.approve_existing_p435_run(run_dir)
            manifest_before = (run_dir / "video_manifest.md").read_bytes()

            self.continue_approved_run(run_dir, "p610")

            self.assertTrue((run_dir / "image_generation_requests.md").exists())
            self.assertEqual((run_dir / "video_manifest.md").read_bytes(), manifest_before)
            for path, content in evidence_before.items():
                self.assertTrue(path.exists(), path)
                self.assertEqual(path.read_bytes(), content, path)
            state = parse_state(run_dir / "state.txt")
            for stage in self.P400_REVIEW_STAGES:
                self.assertEqual(state[f"eval.{stage}.loop.status"], "passed", stage)
            self.assertEqual(state["slot.p435.status"], "done")
            self.assertEqual(state["eval.p400_readiness.status"], "approved")

    def test_forward_continuation_reruns_authoring_grounding_after_script_mutation(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)
            run_dir = self.run_scaffold(base, "p435")
            self.approve_existing_p435_run(run_dir)
            script_readset_path = run_dir / "logs" / "grounding" / "script.readset.json"
            script_path = run_dir / "script.md"
            script_path.write_text(
                script_path.read_text(encoding="utf-8")
                + "\n外部 producer による review-bound script 更新\n",
                encoding="utf-8",
            )
            grounded_stages: list[str] = []
            original_grounding = TOC_IMMERSIVE_RIDE.maybe_run_stage_grounding

            def selective_grounding(
                candidate: Path,
                stage: str,
                *,
                flow: str,
                fatal: bool = True,
            ) -> None:
                grounded_stages.append(stage)
                if stage in {"research", "story", "visual_value", "script"}:
                    original_grounding(
                        candidate,
                        stage,
                        flow=flow,
                        fatal=fatal,
                    )

            def assert_current_p400(candidate: Path) -> None:
                for review_stage in self.P400_REVIEW_STAGES:
                    self.assertEqual(
                        review_input_snapshot_issues(
                            run_dir=candidate,
                            stage=review_stage,
                            round_number=1,
                        ),
                        [],
                        review_stage,
                    )

            argv = [
                "toc-immersive-ride.py",
                "--topic",
                "テスト トピック",
                "--timestamp",
                "20990101_0000",
                "--run-dir",
                str(run_dir),
                "--base",
                str(run_dir.parent),
                "--stage",
                "p500",
                "--experience",
                "cloud_island_walk",
                "--review-policy",
                "drafts",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    TOC_IMMERSIVE_RIDE,
                    "maybe_run_stage_grounding",
                    side_effect=selective_grounding,
                ),
                mock.patch.object(
                    TOC_IMMERSIVE_RIDE,
                    "require_fresh_p400_readiness",
                    side_effect=assert_current_p400,
                ),
            ):
                TOC_IMMERSIVE_RIDE.main()

            self.assertEqual(
                grounded_stages[:4],
                ["research", "story", "visual_value", "script"],
            )
            current_readset_sha = hashlib.sha256(script_readset_path.read_bytes()).hexdigest()
            for review_stage in self.P400_REVIEW_STAGES:
                self.assertEqual(
                    review_input_snapshot_issues(
                        run_dir=run_dir,
                        stage=review_stage,
                        round_number=1,
                    ),
                    [],
                    review_stage,
                )
                snapshot_path = (
                    run_dir
                    / "logs"
                    / "eval"
                    / review_stage
                    / "round_01"
                    / "review_input_snapshot.json"
                )
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    snapshot["readset"]["path"],
                    "logs/grounding/script.readset.json",
                    review_stage,
                )
                self.assertEqual(
                    snapshot["readset"]["sha256"],
                    current_readset_sha,
                    review_stage,
                )

    def test_scaffold_script_stage_stops_before_narration(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "script",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "video_manifest.md").exists())
            self.assertFalse((run_dir / "logs" / "grounding" / "narration.json").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("runtime.stage_target=p400", state)
            self.assertIn("runtime.stop_slot=p450", state)

    def test_scaffold_p500_requires_p400_readiness_gate(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "p500",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((run_dir / "logs" / "grounding" / "asset.json").exists())
            self.assertTrue((run_dir / "logs" / "eval" / "production_readiness" / "round_01" / "prompts" / "critic_1.prompt.md").exists())
            self.assertFalse((run_dir / "asset_plan.md").exists())
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["eval.p400_readiness.status"], "changes_requested")

    def test_later_coarse_targets_record_matching_handoff_state(self) -> None:
        import tempfile

        cases = {
            "p600": {
                "runtime.stage_target": "p600",
                "runtime.stop_slot": "p680",
                "stage.scene_implementation.status": "awaiting_approval",
                "review.image_prompt.status": "pending",
                "gate.image_prompt_review": "required",
                "slot.p680.status": "pending",
                "artifact": "image_generation_requests.md",
            },
            "p700": {
                "runtime.stage_target": "p700",
                "runtime.stop_slot": "p750",
                "stage.narration.status": "awaiting_approval",
                "review.narration.status": "pending",
                "gate.narration_review": "required",
                "slot.p750.status": "pending",
                "artifact": "video_manifest.md",
            },
            "p800": {
                "runtime.stage_target": "p800",
                "runtime.stop_slot": "p850",
                "stage.video_generation.status": "awaiting_approval",
                "review.video.status": "pending",
                "gate.video_review": "required",
                "slot.p850.status": "pending",
                "artifact": "video_generation_requests.md",
            },
            "p900": {
                "runtime.stage_target": "p900",
                "runtime.stop_slot": "p930",
                "stage.qa.status": "awaiting_approval",
                "review.video.status": "pending",
                "gate.video_review": "required",
                "slot.p930.status": "pending",
                "artifact": "run_report.md",
            },
        }

        for stage, expected in cases.items():
            with self.subTest(stage=stage), tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
                base = Path(td) / "out"
                base.mkdir(parents=True, exist_ok=True)

                subprocess.run(
                    [
                        sys.executable,
                        "scripts/toc-immersive-ride.py",
                        "--topic",
                        "テスト トピック",
                        "--timestamp",
                        "20990101_0000",
                        "--base",
                        str(base),
                        "--stage",
                        stage,
                        "--force",
                        "--review-policy",
                        "drafts",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )

                run_dir = base / "テスト_トピック_20990101_0000"
                if stage == "p700":
                    self.assertTrue((run_dir / "video_manifest.md").exists())
                else:
                    self.assertFalse((run_dir / expected["artifact"]).exists())
                self.assertFalse((run_dir / "asset_plan.md").exists())
                state = parse_state(run_dir / "state.txt")
                self.assertEqual(state["eval.p400_readiness.status"], "changes_requested")


if __name__ == "__main__":
    unittest.main()
