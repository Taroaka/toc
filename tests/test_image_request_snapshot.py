from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toc.image_request_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    ImageRequestSnapshotError,
    current_reference_sha256s,
    load_request_snapshot,
    materialize_request_snapshot,
    match_output_provenance,
    sha256_file,
    sha256_text,
    write_request_snapshot_atomic,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _item(
    item_id: str,
    output: str,
    *,
    prompt: str | None = None,
    references: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": item_id,
        "kind": "scene",
        "output": output,
        "prompt": prompt or f"{item_id} の描画プロンプト",
        "prompt_policy_version": "image_api_prompt_v2",
        "compiler_version": "drawable_prompt_compiler_v2",
        "source_digest": _digest(f"source:{item_id}"),
        "references": references or [],
    }


class ImageRequestSnapshotTests(unittest.TestCase):
    def test_materialize_can_defer_cross_stage_reference_until_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    _item(
                        "scene1_cut1",
                        "assets/scenes/scene1.png",
                        references=["assets/characters/hero.png"],
                    )
                ],
                defer_missing_references=True,
            )

            reference = snapshot.items[0].references[0]

        self.assertTrue(reference.deferred)
        self.assertIsNone(reference.sha256)
        self.assertEqual(reference.producer_item_id, "external:assets/characters/hero.png")

    def test_materialize_hashes_current_references_and_defers_producer_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            fixed_ref = run_dir / "assets" / "characters" / "hero.png"
            fixed_ref.parent.mkdir(parents=True)
            fixed_ref.write_bytes(b"hero-reference")
            items = [
                _item("producer", "assets/scenes/producer.png"),
                _item(
                    "consumer",
                    "assets/scenes/consumer.png",
                    references=[
                        "assets/characters/hero.png",
                        "assets/scenes/producer.png",
                    ],
                ),
            ]

            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=items,
                created_at="2026-07-10T12:00:00+09:00",
            )

        self.assertEqual(snapshot.schema_version, SNAPSHOT_SCHEMA_VERSION)
        self.assertEqual([item.item_id for item in snapshot.items], ["consumer", "producer"])
        consumer = snapshot.item("consumer")
        self.assertEqual(consumer.prompt_sha256, sha256_text("consumer の描画プロンプト"))
        self.assertEqual(consumer.references[0].sha256, sha256_text("hero-reference"))
        self.assertFalse(consumer.references[0].deferred)
        self.assertIsNone(consumer.references[1].sha256)
        self.assertTrue(consumer.references[1].deferred)
        self.assertEqual(consumer.references[1].producer_item_id, "producer")
        self.assertEqual(len(snapshot.request_revision), 64)
        self.assertEqual(len(consumer.request_digest), 64)

    def test_materialize_rejects_missing_reference_without_snapshot_producer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            with self.assertRaisesRegex(ImageRequestSnapshotError, "reference does not exist"):
                materialize_request_snapshot(
                    run_dir,
                    kind="scene",
                    items=[
                        _item(
                            "consumer",
                            "assets/scenes/consumer.png",
                            references=["assets/characters/missing.png"],
                        )
                    ],
                )

    def test_atomic_write_round_trips_and_load_validates_current_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            reference = run_dir / "assets" / "characters" / "hero.png"
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"hero-reference")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    _item(
                        "scene1_cut1",
                        "assets/scenes/scene1_cut1.png",
                        references=["assets/characters/hero.png"],
                    )
                ],
            )
            path = run_dir / "image_generation_request_snapshot.json"

            written = write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)
            loaded = load_request_snapshot(path, run_dir=run_dir)
            serialized = path.read_text(encoding="utf-8")

        self.assertEqual(written, path)
        self.assertEqual(loaded, snapshot)
        self.assertTrue(serialized.endswith("\n"))

    def test_load_rejects_duplicate_item_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            payload = snapshot.to_dict()
            payload["items"].append(dict(payload["items"][0]))
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ImageRequestSnapshotError, "duplicate item id"):
                load_request_snapshot(path, run_dir=run_dir)

    def test_load_rejects_prompt_hash_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            payload = snapshot.to_dict()
            payload["items"][0]["prompt_sha256"] = "0" * 64
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ImageRequestSnapshotError, "prompt_sha256 mismatch"):
                load_request_snapshot(path, run_dir=run_dir)

    def test_load_rejects_request_revision_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            payload = snapshot.to_dict()
            payload["request_revision"] = "f" * 64
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ImageRequestSnapshotError, "request_revision mismatch"):
                load_request_snapshot(path, run_dir=run_dir)

    def test_load_rejects_destination_outside_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            payload = snapshot.to_dict()
            payload["items"][0]["destination"] = "../escaped.png"
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ImageRequestSnapshotError, "destination escapes run directory"):
                load_request_snapshot(path, run_dir=run_dir)

    def test_load_rejects_changed_fixed_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            reference = run_dir / "assets" / "characters" / "hero.png"
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"original")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    _item(
                        "scene1_cut1",
                        "assets/scenes/scene1_cut1.png",
                        references=["assets/characters/hero.png"],
                    )
                ],
            )
            path = run_dir / "image_generation_request_snapshot.json"
            write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)
            reference.write_bytes(b"changed")

            with self.assertRaisesRegex(ImageRequestSnapshotError, "reference sha256 mismatch"):
                load_request_snapshot(path, run_dir=run_dir)

    def test_deferred_reference_can_be_resolved_after_snapshot_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    _item("producer", "assets/scenes/producer.png"),
                    _item(
                        "consumer",
                        "assets/scenes/consumer.png",
                        references=["assets/scenes/producer.png"],
                    ),
                ],
            )
            path = run_dir / "image_generation_request_snapshot.json"
            write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)
            produced = run_dir / "assets" / "scenes" / "producer.png"
            produced.parent.mkdir(parents=True)
            produced.write_bytes(b"produced-reference")

            loaded = load_request_snapshot(path, run_dir=run_dir)
            hashes = current_reference_sha256s(run_dir, loaded.item("consumer"))

        self.assertEqual(hashes, (sha256_text("produced-reference"),))

    def test_reference_to_snapshot_producer_stays_deferred_when_old_output_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            old_producer_output = run_dir / "assets" / "scenes" / "producer.png"
            old_producer_output.parent.mkdir(parents=True)
            old_producer_output.write_bytes(b"old-producer-output")

            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    _item("producer", "assets/scenes/producer.png"),
                    _item(
                        "consumer",
                        "assets/scenes/consumer.png",
                        references=["assets/scenes/producer.png"],
                    ),
                ],
            )

        reference = snapshot.item("consumer").references[0]
        self.assertTrue(reference.deferred)
        self.assertIsNone(reference.sha256)
        self.assertEqual(reference.producer_item_id, "producer")

    def test_atomic_write_failure_preserves_previous_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )

            with patch("toc.image_request_snapshot.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            remaining_temps = list(run_dir.glob(f".{path.name}.*.tmp"))
            previous = path.read_text(encoding="utf-8")

        self.assertEqual(previous, "previous snapshot\n")
        self.assertEqual(remaining_temps, [])

    def test_strict_output_provenance_matches_exact_snapshot_and_current_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            reference = run_dir / "assets" / "characters" / "hero.png"
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"hero-reference")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    _item(
                        "scene1_cut1",
                        "assets/scenes/scene1_cut1.png",
                        references=["assets/characters/hero.png"],
                    )
                ],
            )
            item = snapshot.item("scene1_cut1")
            output = run_dir / item.destination
            output.parent.mkdir(parents=True)
            output.write_bytes(b"generated-output")
            provenance = {
                "status": "completed",
                "source": "app_server",
                "provenance_policy": "request_bound_v2",
                "authoritative": True,
                "generation_job_id": "job-1",
                "request_revision": snapshot.request_revision,
                "request_digest": item.request_digest,
                "item_id": item.item_id,
                "kind": item.kind,
                "turn_id": "turn-1",
                "image_generation_item_id": "image-item-1",
                "image_generation_item_count": 1,
                "prompt_sha256": item.prompt_sha256,
                "reference_sha256s": [sha256_file(reference)],
                "saved_path": "/tmp/generated.png",
                "destination": str(output),
                "output_sha256": sha256_file(output),
                "compiler_version": item.compiler_version,
                "source_digest": item.source_digest,
            }

            match = match_output_provenance(run_dir, snapshot, item, provenance)

        self.assertTrue(match.matches)
        self.assertEqual(match.reasons, ())
        self.assertTrue(match)

    def test_strict_output_provenance_reports_hash_and_request_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            reference = run_dir / "assets" / "characters" / "hero.png"
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"hero-reference")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    _item(
                        "scene1_cut1",
                        "assets/scenes/scene1_cut1.png",
                        references=["assets/characters/hero.png"],
                    )
                ],
            )
            item = snapshot.item("scene1_cut1")
            output = run_dir / item.destination
            output.parent.mkdir(parents=True)
            output.write_bytes(b"generated-output")
            provenance = {
                "status": "completed",
                "source": "app_server",
                "provenance_policy": "request_bound_v2",
                "authoritative": True,
                "generation_job_id": "job-1",
                "request_revision": "0" * 64,
                "request_digest": item.request_digest,
                "item_id": item.item_id,
                "kind": item.kind,
                "turn_id": "turn-1",
                "image_generation_item_id": "image-item-1",
                "image_generation_item_count": 2,
                "prompt_sha256": "1" * 64,
                "reference_sha256s": ["2" * 64],
                "saved_path": "/tmp/generated.png",
                "destination": item.destination,
                "output_sha256": "3" * 64,
                "compiler_version": "old-compiler",
                "source_digest": "4" * 64,
            }

            match = match_output_provenance(run_dir, snapshot, item, provenance)

        self.assertFalse(match.matches)
        self.assertIn("request_revision_mismatch", match.reasons)
        self.assertIn("image_generation_item_count_mismatch", match.reasons)
        self.assertIn("prompt_sha256_mismatch", match.reasons)
        self.assertIn("reference_sha256s_mismatch", match.reasons)
        self.assertIn("output_sha256_mismatch", match.reasons)
        self.assertIn("compiler_version_mismatch", match.reasons)
        self.assertIn("source_digest_mismatch", match.reasons)

    def test_strict_output_provenance_rejects_changed_output_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            item = snapshot.item("scene1_cut1")
            output = run_dir / item.destination
            output.parent.mkdir(parents=True)
            output.write_bytes(b"changed-output")
            provenance = {
                "status": "completed",
                "source": "app_server",
                "provenance_policy": "request_bound_v2",
                "authoritative": True,
                "generation_job_id": "job-1",
                "request_revision": snapshot.request_revision,
                "request_digest": item.request_digest,
                "item_id": item.item_id,
                "kind": item.kind,
                "turn_id": "turn-1",
                "image_generation_item_id": "image-item-1",
                "image_generation_item_count": 1,
                "prompt_sha256": item.prompt_sha256,
                "reference_sha256s": [],
                "saved_path": "/tmp/generated.png",
                "destination": item.destination,
                "output_sha256": sha256_text("original-output"),
                "compiler_version": item.compiler_version,
                "source_digest": item.source_digest,
            }

            match = match_output_provenance(run_dir, snapshot, item, provenance)

        self.assertFalse(match.matches)
        self.assertIn("output_sha256_mismatch", match.reasons)


if __name__ == "__main__":
    unittest.main()
