from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from toc.review_loop import (
    REVIEW_LOOP_CRITIC_COUNT,
    REVIEW_LOOP_SPECS,
    aggregator_prompt_relpath,
    build_review_input_snapshot,
    critic_prompt_relpath,
    review_input_snapshot_issues,
    write_review_input_snapshot,
)
from toc.review_projection import (
    RAW_REVIEW_SOURCE_FINGERPRINT_POLICY,
    REVIEW_LOOP_MANIFEST_PROJECTION_STAGES,
    REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD,
    SEMANTIC_MANIFEST_PROJECTION_STAGES,
    VIDEO_MANIFEST_REVIEW_PROJECTION_SCHEMA,
    ReviewProjectionError,
    review_source_fingerprint,
    video_manifest_review_projection_sha256,
)
from toc.semantic_review import (
    SEMANTIC_REVIEW_INPUT_SCHEMA,
    semantic_review_currentness_issues,
    semantic_review_input_digest,
    semantic_review_relpaths,
    semantic_review_scope_binding_sha256,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_PACK_PATH = REPO_ROOT / "scripts" / "build-semantic-review-pack.py"


def _load_pack_builder():
    spec = importlib.util.spec_from_file_location(
        "build_semantic_review_pack_projection_test",
        BUILD_PACK_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BUILD_PACK_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest_data() -> dict[str, object]:
    return {
        "schema_version": "scene_event_v1",
        "manifest_phase": "production",
        "video_metadata": {
            "topic": "projection test",
            "target_duration_seconds": 300,
        },
        "assets": {
            "style_guide": {
                "visual_style": "cinematic",
            }
        },
        "scenes": [
            {
                "scene_id": "01",
                "time_of_day": "朝",
                "cuts": [
                    {
                        "cut_id": "01",
                        "duration_seconds": 8,
                        "image_generation": {
                            "prompt": "hero at dawn",
                            "output": "assets/scenes/scene1_cut1.png",
                        },
                        "video_generation": {
                            "duration_seconds": 8,
                        },
                    }
                ],
            }
        ],
    }


def _write_manifest(path: Path, data: dict[str, object]) -> None:
    path.write_text(
        "# Video Manifest\n\n```yaml\n"
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        + "```\n",
        encoding="utf-8",
    )


def _render_units() -> list[dict[str, object]]:
    return [
        {
            "unit_id": "1",
            "source_cut_ids": ["1"],
            "storyboard_image": "assets/storyboards/scene1_storyboard.png",
            "video_generation": {
                "tool": "seedance",
                "duration_seconds": 8,
                "prompt": "move",
            },
        }
    ]


class ReviewProjectionUnitTests(unittest.TestCase):
    def test_only_direct_scene_render_units_are_removed_from_projected_fingerprint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_projection_") as td:
            manifest_path = Path(td) / "video_manifest.md"
            base = _manifest_data()
            _write_manifest(manifest_path, base)
            before = review_source_fingerprint(
                manifest_path,
                artifact_relpath="video_manifest.md",
                review_kind="review_loop",
                stage="script",
            )

            with_overlay = copy.deepcopy(base)
            with_overlay["scenes"][0]["render_units"] = _render_units()  # type: ignore[index]
            _write_manifest(manifest_path, with_overlay)
            after = review_source_fingerprint(
                manifest_path,
                artifact_relpath="video_manifest.md",
                review_kind="review_loop",
                stage="script",
            )

            self.assertEqual(after.sha256, before.sha256)
            self.assertEqual(after.size_bytes, before.size_bytes)
            self.assertTrue(after.projected)
            self.assertEqual(
                after.policy,
                VIDEO_MANIFEST_REVIEW_PROJECTION_SCHEMA,
            )

            nested_overlay = copy.deepcopy(with_overlay)
            nested_overlay["scenes"][0]["cuts"][0]["render_units"] = [  # type: ignore[index]
                {"must_remain_reviewed": True}
            ]
            _write_manifest(manifest_path, nested_overlay)
            nested = review_source_fingerprint(
                manifest_path,
                artifact_relpath="video_manifest.md",
                review_kind="review_loop",
                stage="script",
            )
            self.assertNotEqual(nested.sha256, before.sha256)

    def test_every_non_overlay_manifest_mutation_changes_projection(self) -> None:
        mutations = {
            "cut_id": lambda data: data["scenes"][0]["cuts"][0].__setitem__("cut_id", "02"),  # type: ignore[index]
            "duration": lambda data: data["scenes"][0]["cuts"][0].__setitem__("duration_seconds", 9),  # type: ignore[index]
            "prompt": lambda data: data["scenes"][0]["cuts"][0]["image_generation"].__setitem__("prompt", "changed"),  # type: ignore[index]
            "asset": lambda data: data["assets"]["style_guide"].__setitem__("visual_style", "changed"),  # type: ignore[index]
        }
        with tempfile.TemporaryDirectory(prefix="toc_review_projection_mutation_") as td:
            manifest_path = Path(td) / "video_manifest.md"
            base = _manifest_data()
            _write_manifest(manifest_path, base)
            expected = video_manifest_review_projection_sha256(manifest_path)
            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    changed = copy.deepcopy(base)
                    mutate(changed)
                    _write_manifest(manifest_path, changed)
                    self.assertNotEqual(
                        video_manifest_review_projection_sha256(manifest_path),
                        expected,
                    )

    def test_stage_allowlists_keep_p800_and_unknown_stages_raw(self) -> None:
        self.assertEqual(
            REVIEW_LOOP_MANIFEST_PROJECTION_STAGES,
            frozenset(
                {
                    "script",
                    "production_readiness",
                    "scene_set",
                    "scene_detail",
                    "cut_blueprint",
                    "asset",
                    "scene_implementation_hard",
                    "scene_implementation_judgment",
                }
            ),
        )
        self.assertEqual(
            SEMANTIC_MANIFEST_PROJECTION_STAGES,
            frozenset(
                {
                    "scene_set",
                    "scene_detail",
                    "cut_blueprint",
                    "asset_plan",
                    "image_prompt",
                }
            ),
        )
        with tempfile.TemporaryDirectory(prefix="toc_review_projection_stage_") as td:
            manifest_path = Path(td) / "video_manifest.md"
            base = _manifest_data()
            _write_manifest(manifest_path, base)
            raw_before = {
                (kind, stage): review_source_fingerprint(
                    manifest_path,
                    artifact_relpath="video_manifest.md",
                    review_kind=kind,
                    stage=stage,
                )
                for kind, stage in (
                    ("review_loop", "narration"),
                    ("review_loop", "video_generation_motion"),
                    ("review_loop", "video_generation_review"),
                    ("review_loop", "unknown_future_stage"),
                    ("semantic", "video_motion"),
                    ("semantic", "narration"),
                )
            }
            with_overlay = copy.deepcopy(base)
            with_overlay["scenes"][0]["render_units"] = _render_units()  # type: ignore[index]
            _write_manifest(manifest_path, with_overlay)

            for key, before in raw_before.items():
                with self.subTest(kind=key[0], stage=key[1]):
                    after = review_source_fingerprint(
                        manifest_path,
                        artifact_relpath="video_manifest.md",
                        review_kind=key[0],
                        stage=key[1],
                    )
                    self.assertFalse(after.projected)
                    self.assertEqual(
                        after.policy,
                        RAW_REVIEW_SOURCE_FINGERPRINT_POLICY,
                    )
                    self.assertNotEqual(after.sha256, before.sha256)

    def test_malformed_manifest_projection_fails_closed(self) -> None:
        malformed_documents = (
            "```yaml\nscenes: [\n```\n",
            "```yaml\n- not\n- a\n- mapping\n```\n",
            "```yaml\nscenes: wrong\n```\n",
            "```yaml\nscenes:\n  - not-a-mapping\n```\n",
            "```yaml\nscenes:\n  - scene_id: 1\n    render_units: wrong\n```\n",
            "```yaml\nscenes: []\nscenes: []\n```\n",
            (
                "```yaml\nscenes: []\n```\n"
                "```yaml\nscenes:\n"
            ),
        )
        with tempfile.TemporaryDirectory(prefix="toc_review_projection_bad_") as td:
            manifest_path = Path(td) / "video_manifest.md"
            for index, text in enumerate(malformed_documents):
                with self.subTest(index=index):
                    manifest_path.write_text(text, encoding="utf-8")
                    with self.assertRaises(ReviewProjectionError):
                        video_manifest_review_projection_sha256(manifest_path)

    def test_scene_alias_does_not_hide_non_direct_render_units(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_projection_alias_") as td:
            manifest_path = Path(td) / "video_manifest.md"
            manifest_path.write_text(
                "```yaml\n"
                "shared: &scene\n"
                "  scene_id: 1\n"
                "  cuts: []\n"
                "scenes:\n"
                "  - *scene\n"
                "```\n",
                encoding="utf-8",
            )
            before = video_manifest_review_projection_sha256(
                manifest_path
            )
            manifest_path.write_text(
                "```yaml\n"
                "shared: &scene\n"
                "  scene_id: 1\n"
                "  cuts: []\n"
                "  render_units:\n"
                "    - unit_id: 1\n"
                "scenes:\n"
                "  - *scene\n"
                "```\n",
                encoding="utf-8",
            )

            self.assertNotEqual(
                video_manifest_review_projection_sha256(manifest_path),
                before,
            )


class ReviewProjectionIntegrationTests(unittest.TestCase):
    def _write_review_sources(self, run_dir: Path, stage: str) -> None:
        for relpath in REVIEW_LOOP_SPECS[stage].source_artifacts:
            path = run_dir / relpath
            path.parent.mkdir(parents=True, exist_ok=True)
            if relpath == "video_manifest.md":
                _write_manifest(path, _manifest_data())
            else:
                path.write_text(f"# {relpath}\n", encoding="utf-8")

    def test_review_loop_projection_keeps_input_digest_current_and_stable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_loop_projection_") as td:
            run_dir = Path(td)
            self._write_review_sources(run_dir, "script")
            snapshot = build_review_input_snapshot(
                run_dir=run_dir,
                stage="script",
                round_number=1,
            )
            manifest_source = next(
                source
                for source in snapshot["source_artifacts"]
                if source["path"] == "video_manifest.md"
            )
            self.assertEqual(
                manifest_source[
                    REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD
                ],
                VIDEO_MANIFEST_REVIEW_PROJECTION_SCHEMA,
            )
            prompt_relpaths = tuple(
                critic_prompt_relpath("script", 1, index)
                for index in range(1, REVIEW_LOOP_CRITIC_COUNT + 1)
            ) + (aggregator_prompt_relpath("script", 1),)
            for relpath in prompt_relpaths:
                path = run_dir / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# {relpath.name}\n", encoding="utf-8")
            write_review_input_snapshot(
                run_dir=run_dir,
                stage="script",
                round_number=1,
                snapshot=snapshot,
                prompt_relpaths=prompt_relpaths,
            )

            manifest_path = run_dir / "video_manifest.md"
            with_overlay = _manifest_data()
            with_overlay["scenes"][0]["render_units"] = _render_units()  # type: ignore[index]
            _write_manifest(manifest_path, with_overlay)

            self.assertEqual(
                review_input_snapshot_issues(
                    run_dir=run_dir,
                    stage="script",
                    round_number=1,
                ),
                [],
            )
            rebuilt = build_review_input_snapshot(
                run_dir=run_dir,
                stage="script",
                round_number=1,
            )
            self.assertEqual(rebuilt["input_digest"], snapshot["input_digest"])
            self.assertEqual(
                rebuilt["source_artifacts"],
                snapshot["source_artifacts"],
            )

            changed = copy.deepcopy(with_overlay)
            changed["scenes"][0]["cuts"][0]["duration_seconds"] = 9  # type: ignore[index]
            _write_manifest(manifest_path, changed)
            self.assertIn(
                "stale review source sha256: video_manifest.md",
                review_input_snapshot_issues(
                    run_dir=run_dir,
                    stage="script",
                    round_number=1,
                ),
            )

    def test_review_loop_narration_stage_keeps_raw_manifest_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_loop_raw_") as td:
            run_dir = Path(td)
            self._write_review_sources(run_dir, "narration")
            snapshot = build_review_input_snapshot(
                run_dir=run_dir,
                stage="narration",
                round_number=1,
            )
            prompt_relpaths = tuple(
                critic_prompt_relpath("narration", 1, index)
                for index in range(1, REVIEW_LOOP_CRITIC_COUNT + 1)
            ) + (aggregator_prompt_relpath("narration", 1),)
            for relpath in prompt_relpaths:
                path = run_dir / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# {relpath.name}\n", encoding="utf-8")
            write_review_input_snapshot(
                run_dir=run_dir,
                stage="narration",
                round_number=1,
                snapshot=snapshot,
                prompt_relpaths=prompt_relpaths,
            )
            changed = _manifest_data()
            changed["scenes"][0]["render_units"] = _render_units()  # type: ignore[index]
            _write_manifest(run_dir / "video_manifest.md", changed)
            self.assertIn(
                "stale review source sha256: video_manifest.md",
                review_input_snapshot_issues(
                    run_dir=run_dir,
                    stage="narration",
                    round_number=1,
                ),
            )

    def test_review_loop_legacy_raw_policy_is_safe_until_exact_bytes_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_loop_legacy_") as td:
            run_dir = Path(td)
            self._write_review_sources(run_dir, "script")
            snapshot = build_review_input_snapshot(
                run_dir=run_dir,
                stage="script",
                round_number=1,
            )
            for source in snapshot["source_artifacts"]:
                source.pop(REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD)
                source_path = run_dir / source["path"]
                source["sha256"] = hashlib.sha256(
                    source_path.read_bytes()
                ).hexdigest()
                source["size_bytes"] = source_path.stat().st_size
            digest_payload = {
                "schema_version": snapshot["schema_version"],
                "stage": snapshot["stage"],
                "round": snapshot["round"],
                "source_artifacts": snapshot["source_artifacts"],
                "readset": snapshot["readset"],
            }
            snapshot["input_digest"] = hashlib.sha256(
                json.dumps(
                    digest_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            prompt_relpaths = tuple(
                critic_prompt_relpath("script", 1, index)
                for index in range(1, REVIEW_LOOP_CRITIC_COUNT + 1)
            ) + (aggregator_prompt_relpath("script", 1),)
            for relpath in prompt_relpaths:
                path = run_dir / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# {relpath.name}\n", encoding="utf-8")
            write_review_input_snapshot(
                run_dir=run_dir,
                stage="script",
                round_number=1,
                snapshot=snapshot,
                prompt_relpaths=prompt_relpaths,
            )

            self.assertEqual(
                review_input_snapshot_issues(
                    run_dir=run_dir,
                    stage="script",
                    round_number=1,
                ),
                [],
            )

            changed = _manifest_data()
            changed["scenes"][0]["render_units"] = _render_units()  # type: ignore[index]
            _write_manifest(run_dir / "video_manifest.md", changed)
            self.assertIn(
                "stale review source sha256: video_manifest.md",
                review_input_snapshot_issues(
                    run_dir=run_dir,
                    stage="script",
                    round_number=1,
                ),
            )

    def _write_semantic_scope(
        self,
        *,
        run_dir: Path,
        stage: str,
    ) -> Path:
        builder = _load_pack_builder()
        paths = semantic_review_relpaths(stage)
        collection_path = run_dir / paths["collection"]
        prompt_path = run_dir / paths["prompt"]
        scope_path = run_dir / paths["scope"]
        report_path = run_dir / paths["report"]
        collection_path.parent.mkdir(parents=True, exist_ok=True)
        collection_path.write_text("collection\n", encoding="utf-8")
        prompt_path.write_text("prompt\n", encoding="utf-8")
        records = builder._source_artifact_digest_records(
            run_dir,
            ["video_manifest.md"],
            stage=stage,
        )
        entry_ids = [f"{stage}:entry:1"]
        scope = {
            "stage": stage,
            "entry_count": 1,
            "entry_ids": entry_ids,
            "review_scope": "all_entries",
            "source_artifacts": ["video_manifest.md"],
            "semantic_review_input_schema": SEMANTIC_REVIEW_INPUT_SCHEMA,
            "source_artifact_digests": records,
            "collection_sha256": builder.semantic_review_file_sha256(
                collection_path
            ),
            "prompt_sha256": builder.semantic_review_file_sha256(prompt_path),
            "artifacts": {
                "collection": paths["collection"].as_posix(),
                "scope": paths["scope"].as_posix(),
                "prompt": paths["prompt"].as_posix(),
                "report": paths["report"].as_posix(),
            },
        }
        scope_binding = semantic_review_scope_binding_sha256(scope)
        digest = semantic_review_input_digest(
            stage=stage,
            entry_ids=entry_ids,
            collection_sha256=scope["collection_sha256"],
            prompt_sha256=scope["prompt_sha256"],
            source_artifact_digests=records,
            scope_binding_sha256=scope_binding,
        )
        scope["scope_binding_sha256"] = scope_binding
        scope["semantic_review_input_digest"] = digest
        scope_path.write_text(
            json.dumps(scope, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report_path.write_text(
            "status: passed\n"
            f"semantic_review_input_digest: {digest}\n",
            encoding="utf-8",
        )
        return scope_path

    def test_semantic_pack_and_currentness_share_stage_scoped_projection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_semantic_projection_") as td:
            run_dir = Path(td)
            manifest_path = run_dir / "video_manifest.md"
            _write_manifest(manifest_path, _manifest_data())
            scope_path = self._write_semantic_scope(
                run_dir=run_dir,
                stage="scene_set",
            )
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            self.assertEqual(
                scope["source_artifact_digests"][0][
                    REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD
                ],
                VIDEO_MANIFEST_REVIEW_PROJECTION_SCHEMA,
            )
            self.assertEqual(
                semantic_review_currentness_issues(run_dir, "scene_set"),
                (),
            )

            with_overlay = _manifest_data()
            with_overlay["scenes"][0]["render_units"] = _render_units()  # type: ignore[index]
            _write_manifest(manifest_path, with_overlay)
            self.assertEqual(
                semantic_review_currentness_issues(run_dir, "scene_set"),
                (),
            )

            changed = copy.deepcopy(with_overlay)
            changed["scenes"][0]["cuts"][0]["cut_id"] = "02"  # type: ignore[index]
            _write_manifest(manifest_path, changed)
            self.assertTrue(
                any(
                    "source SHA-256 mismatch" in issue
                    for issue in semantic_review_currentness_issues(
                        run_dir,
                        "scene_set",
                    )
                )
            )

    def test_semantic_legacy_raw_policy_is_safe_until_exact_bytes_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_semantic_legacy_") as td:
            run_dir = Path(td)
            manifest_path = run_dir / "video_manifest.md"
            _write_manifest(manifest_path, _manifest_data())
            scope_path = self._write_semantic_scope(
                run_dir=run_dir,
                stage="scene_set",
            )
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            records = scope["source_artifact_digests"]
            records[0].pop(REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD)
            records[0]["sha256"] = hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest()
            digest = semantic_review_input_digest(
                stage="scene_set",
                entry_ids=scope["entry_ids"],
                collection_sha256=scope["collection_sha256"],
                prompt_sha256=scope["prompt_sha256"],
                source_artifact_digests=records,
                scope_binding_sha256=scope[
                    "scope_binding_sha256"
                ],
            )
            scope["semantic_review_input_digest"] = digest
            scope_path.write_text(
                json.dumps(scope, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            report_path = (
                run_dir / semantic_review_relpaths("scene_set")["report"]
            )
            report_path.write_text(
                "status: passed\n"
                f"semantic_review_input_digest: {digest}\n",
                encoding="utf-8",
            )

            self.assertEqual(
                semantic_review_currentness_issues(
                    run_dir,
                    "scene_set",
                ),
                (),
            )

            with_overlay = _manifest_data()
            with_overlay["scenes"][0]["render_units"] = _render_units()  # type: ignore[index]
            _write_manifest(manifest_path, with_overlay)
            self.assertTrue(
                any(
                    "source SHA-256 mismatch" in issue
                    for issue in semantic_review_currentness_issues(
                        run_dir,
                        "scene_set",
                    )
                )
            )

    def test_semantic_video_motion_remains_raw_and_malformed_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_semantic_raw_") as td:
            run_dir = Path(td)
            manifest_path = run_dir / "video_manifest.md"
            _write_manifest(manifest_path, _manifest_data())
            self._write_semantic_scope(run_dir=run_dir, stage="video_motion")
            with_overlay = _manifest_data()
            with_overlay["scenes"][0]["render_units"] = _render_units()  # type: ignore[index]
            _write_manifest(manifest_path, with_overlay)
            self.assertTrue(
                semantic_review_currentness_issues(run_dir, "video_motion")
            )

            _write_manifest(manifest_path, _manifest_data())
            self._write_semantic_scope(run_dir=run_dir, stage="scene_set")
            manifest_path.write_text(
                "```yaml\nscenes: [\n```\n",
                encoding="utf-8",
            )
            issues = semantic_review_currentness_issues(run_dir, "scene_set")
            self.assertTrue(issues)
            self.assertTrue(
                any("projection" in issue.lower() for issue in issues),
                issues,
            )


if __name__ == "__main__":
    unittest.main()
