from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toc.atomic_exchange import (
    AtomicExchangeUnavailableError,
    atomic_exchange_names,
)
from toc.image_request_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    ImageRequestSnapshotError,
    bind_request_snapshot_references,
    current_reference_sha256s,
    load_request_snapshot,
    materialize_request_snapshot,
    match_output_provenance,
    sha256_file,
    sha256_text,
    write_request_snapshot_atomic,
)
from toc.run_root_binding import bind_run_root


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
    def test_materialize_hashes_existing_self_reference_instead_of_deferring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            destination = run_dir / "assets" / "scenes" / "scene1.png"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"existing-image")

            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    _item(
                        "scene1_cut1",
                        "assets/scenes/scene1.png",
                        references=["assets/scenes/scene1.png"],
                    )
                ],
            )

        reference = snapshot.items[0].references[0]
        self.assertFalse(reference.deferred)
        self.assertEqual(reference.sha256, sha256_text("existing-image"))
        self.assertIsNone(reference.producer_item_id)

    def test_materialize_rejects_missing_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            with self.assertRaisesRegex(ImageRequestSnapshotError, "self-reference does not exist"):
                materialize_request_snapshot(
                    run_dir,
                    kind="scene",
                    items=[
                        _item(
                            "scene1_cut1",
                            "assets/scenes/scene1.png",
                            references=["assets/scenes/scene1.png"],
                        )
                    ],
                    defer_missing_references=True,
                )

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

    def test_atomic_write_publishes_private_regular_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_request_snapshot.json"
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )

            write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            published = os.stat(path, follow_symlinks=False)
            self.assertTrue(stat.S_ISREG(published.st_mode))
            self.assertEqual(published.st_nlink, 1)

    def test_atomic_write_rejects_symlink_and_hardlinked_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            outside = root / "outside.json"
            outside.write_text("outside must remain unchanged\n", encoding="utf-8")
            path = run_dir / "image_generation_request_snapshot.json"

            path.symlink_to(outside)
            with self.assertRaisesRegex(ImageRequestSnapshotError, "regular file"):
                write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside must remain unchanged\n")

            path.unlink()
            os.link(outside, path)
            with self.assertRaisesRegex(ImageRequestSnapshotError, "multiple hard links"):
                write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)
            self.assertTrue(path.samefile(outside))
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside must remain unchanged\n")

    def test_atomic_write_root_swap_never_publishes_to_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            detached = root / "run-original"
            replacement = root / "run-replacement"
            run_dir.mkdir()
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            opened = os.stat(run_dir, follow_symlinks=False)
            identity = opened.st_dev, opened.st_ino
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
                expected_root_identity=identity,
            )
            original_exchange = atomic_exchange_names
            swapped = False

            def swap_root_during_publish(
                source_dir_fd,
                source,
                destination_dir_fd,
                destination,
            ):
                nonlocal swapped
                if not swapped and destination == path.name:
                    swapped = True
                    run_dir.rename(detached)
                    run_dir.mkdir()
                    (run_dir / path.name).write_text(
                        "replacement must remain unchanged\n",
                        encoding="utf-8",
                    )
                return original_exchange(
                    source_dir_fd,
                    source,
                    destination_dir_fd,
                    destination,
                )

            try:
                with patch(
                    "toc.image_request_snapshot.atomic_exchange_names",
                    side_effect=swap_root_during_publish,
                ):
                    with self.assertRaisesRegex(
                        ImageRequestSnapshotError,
                        "root|ancestor|unsafe",
                    ):
                        write_request_snapshot_atomic(
                            path,
                            snapshot,
                            run_dir=run_dir,
                            expected_root_identity=identity,
                        )
            finally:
                if detached.exists():
                    run_dir.rename(replacement)
                    detached.rename(run_dir)

            self.assertTrue(swapped)
            self.assertEqual(path.read_text(encoding="utf-8"), "previous snapshot\n")
            self.assertEqual(
                (replacement / path.name).read_text(encoding="utf-8"),
                "replacement must remain unchanged\n",
            )

    def test_atomic_write_parent_swap_never_publishes_through_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            parent = run_dir / "metadata"
            detached_parent = run_dir / "metadata-original"
            outside = root / "outside"
            parent.mkdir(parents=True)
            outside.mkdir()
            path = parent / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            outside_path = outside / path.name
            outside_path.write_text("outside must remain unchanged\n", encoding="utf-8")
            opened = os.stat(run_dir, follow_symlinks=False)
            identity = opened.st_dev, opened.st_ino
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
                expected_root_identity=identity,
            )
            original_exchange = atomic_exchange_names
            swapped = False

            def swap_parent_during_publish(
                source_dir_fd,
                source,
                destination_dir_fd,
                destination,
            ):
                nonlocal swapped
                if not swapped and destination == path.name:
                    swapped = True
                    parent.rename(detached_parent)
                    parent.symlink_to(outside, target_is_directory=True)
                return original_exchange(
                    source_dir_fd,
                    source,
                    destination_dir_fd,
                    destination,
                )

            try:
                with patch(
                    "toc.image_request_snapshot.atomic_exchange_names",
                    side_effect=swap_parent_during_publish,
                ):
                    with self.assertRaisesRegex(
                        ImageRequestSnapshotError,
                        "ancestor|unsafe",
                    ):
                        write_request_snapshot_atomic(
                            path,
                            snapshot,
                            run_dir=run_dir,
                            expected_root_identity=identity,
                        )
            finally:
                if parent.is_symlink():
                    parent.unlink()
                    detached_parent.rename(parent)

            self.assertTrue(swapped)
            self.assertEqual(path.read_text(encoding="utf-8"), "previous snapshot\n")
            self.assertEqual(outside_path.read_text(encoding="utf-8"), "outside must remain unchanged\n")

    def test_atomic_write_does_not_clobber_destination_that_races_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            outside = root / "outside.json"
            outside.write_text("racing destination\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            original_exchange = atomic_exchange_names
            raced = False

            def insert_destination_before_publish(
                source_dir_fd,
                source,
                destination_dir_fd,
                destination,
            ):
                nonlocal raced
                if not raced and destination == path.name:
                    raced = True
                    os.unlink(destination, dir_fd=destination_dir_fd)
                    os.link(
                        outside,
                        destination,
                        dst_dir_fd=destination_dir_fd,
                        follow_symlinks=False,
                    )
                return original_exchange(
                    source_dir_fd,
                    source,
                    destination_dir_fd,
                    destination,
                )

            with patch(
                "toc.image_request_snapshot.atomic_exchange_names",
                side_effect=insert_destination_before_publish,
            ):
                with self.assertRaisesRegex(
                    ImageRequestSnapshotError,
                    "identity changed during atomic exchange",
                ):
                    write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            self.assertTrue(raced)
            self.assertTrue(path.samefile(outside))
            self.assertEqual(outside.read_text(encoding="utf-8"), "racing destination\n")

    def test_atomic_new_file_post_link_racer_remains_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            path = run_dir / "image_generation_request_snapshot.json"
            outside = root / "outside.json"
            outside.write_text("racing destination\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            original_link = os.link
            raced = False

            def replace_destination_after_link(
                source,
                destination,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
                follow_symlinks=True,
            ):
                nonlocal raced
                result = original_link(
                    source,
                    destination,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )
                if (
                    not raced
                    and destination == path.name
                    and src_dir_fd == dst_dir_fd
                ):
                    raced = True
                    os.unlink(destination, dir_fd=dst_dir_fd)
                    original_link(
                        outside,
                        destination,
                        dst_dir_fd=dst_dir_fd,
                        follow_symlinks=False,
                    )
                return result

            with patch(
                "toc.image_request_snapshot.os.link",
                side_effect=replace_destination_after_link,
            ):
                with self.assertRaisesRegex(
                    ImageRequestSnapshotError,
                    "identity changed after publish",
                ):
                    write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            self.assertTrue(raced)
            self.assertTrue(path.samefile(outside))
            self.assertEqual(path.read_text(encoding="utf-8"), "racing destination\n")

    def test_atomic_write_parent_fsync_failure_restores_previous_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            original_fsync = os.fsync
            calls = 0

            def fail_first_parent_fsync(descriptor: int) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected parent fsync failure")
                original_fsync(descriptor)

            with patch(
                "toc.image_request_snapshot.os.fsync",
                side_effect=fail_first_parent_fsync,
            ):
                with self.assertRaisesRegex(
                    ImageRequestSnapshotError,
                    "injected parent fsync failure",
                ):
                    write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            self.assertGreaterEqual(calls, 3)
            self.assertEqual(path.read_text(encoding="utf-8"), "previous snapshot\n")
            self.assertEqual(
                [entry for entry in run_dir.iterdir() if entry.is_file() and entry.name.startswith(".")],
                [],
            )

    def test_materialize_and_bind_hashes_reject_transient_root_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            detached = root / "run-original"
            replacement = root / "run-replacement"
            reference = run_dir / "assets" / "characters" / "hero.png"
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"trusted reference")
            opened = os.stat(run_dir, follow_symlinks=False)
            identity = opened.st_dev, opened.st_ino
            from scripts.world_walk_source import sha256_regular_file_nofollow as real_hash

            def hash_after_transient_swap(root_path, relative_path, **kwargs):
                run_dir.rename(detached)
                malicious = run_dir / "assets" / "characters" / "hero.png"
                malicious.parent.mkdir(parents=True)
                malicious.write_bytes(b"attacker reference")
                try:
                    return real_hash(root_path, relative_path, **kwargs)
                finally:
                    run_dir.rename(replacement)
                    detached.rename(run_dir)

            with patch(
                "toc.image_request_snapshot.sha256_regular_file_nofollow",
                side_effect=hash_after_transient_swap,
            ):
                with self.assertRaises(ImageRequestSnapshotError):
                    materialize_request_snapshot(
                        run_dir,
                        kind="scene",
                        items=[
                            _item(
                                "scene1_cut1",
                                "assets/scenes/scene1_cut1.png",
                                references=["assets/characters/hero.png"],
                            )
                        ],
                        expected_root_identity=identity,
                    )

            deferred = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    _item(
                        "scene1_cut1",
                        "assets/scenes/scene1_cut1.png",
                        references=["assets/characters/future.png"],
                    )
                ],
                defer_missing_references=True,
                expected_root_identity=identity,
            )
            future = run_dir / "assets" / "characters" / "future.png"
            future.write_bytes(b"trusted future reference")

            with patch(
                "toc.image_request_snapshot.sha256_regular_file_nofollow",
                side_effect=hash_after_transient_swap,
            ):
                with self.assertRaises(ImageRequestSnapshotError):
                    bind_request_snapshot_references(
                        deferred,
                        run_dir=run_dir,
                        expected_root_identity=identity,
                    )

    def test_bound_load_rejects_replaced_run_root_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            original = parent / "original"
            replacement = parent / "replacement"
            run_dir.mkdir()
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    _item(
                        "scene1_cut1",
                        "assets/scenes/scene1_cut1.png",
                    )
                ],
            )
            snapshot_path = (
                run_dir / "image_generation_request_snapshot.json"
            )
            write_request_snapshot_atomic(
                snapshot_path,
                snapshot,
                run_dir=run_dir,
            )
            root_stat = run_dir.stat()
            expected_identity = root_stat.st_dev, root_stat.st_ino
            malicious = snapshot.to_dict()
            malicious["items"][0]["prompt"] = "attacker prompt"

            run_dir.rename(original)
            run_dir.mkdir()
            (run_dir / snapshot_path.name).write_text(
                json.dumps(malicious, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                with self.assertRaises(ImageRequestSnapshotError):
                    load_request_snapshot(
                        run_dir / snapshot_path.name,
                        run_dir=run_dir,
                        expected_root_identity=expected_identity,
                    )
            finally:
                run_dir.rename(replacement)
                original.rename(run_dir)

            self.assertEqual(
                load_request_snapshot(
                    run_dir / snapshot_path.name,
                    run_dir=run_dir,
                    expected_root_identity=expected_identity,
                ),
                snapshot,
            )

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

    def test_load_without_reference_verification_does_not_read_source_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "image_generation_requests.md"
            source.write_text("# frozen request\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
                source_artifact=source.name,
            )
            path = run_dir / "image_generation_request_snapshot.json"
            write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)
            source.unlink()

            with patch(
                "toc.image_request_snapshot._snapshot_file_sha256",
                side_effect=AssertionError(
                    "verify_references=False must not hash source_artifact"
                ),
            ) as source_hash:
                loaded = load_request_snapshot(
                    path,
                    run_dir=run_dir,
                    verify_references=False,
                )

        self.assertEqual(loaded, snapshot)
        source_hash.assert_not_called()

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

            with patch(
                "toc.image_request_snapshot.atomic_exchange_names",
                side_effect=OSError("exchange failed"),
            ):
                with self.assertRaisesRegex(
                    ImageRequestSnapshotError,
                    "exchange failed",
                ):
                    write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            remaining_temps = list(run_dir.glob(f".{path.name}.*.tmp"))
            previous = path.read_text(encoding="utf-8")

        self.assertEqual(previous, "previous snapshot\n")
        self.assertEqual(remaining_temps, [])

    def test_atomic_overwrite_never_exposes_missing_canonical_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            observed: list[str] = []
            real_rename = os.rename

            def observe_exchange(source_fd, source, destination_fd, destination):
                observed.append(path.read_text(encoding="utf-8"))
                atomic_exchange_names(
                    source_fd,
                    source,
                    destination_fd,
                    destination,
                )
                observed.append(path.read_text(encoding="utf-8"))

            def observe_rename(source, destination, **kwargs):
                result = real_rename(source, destination, **kwargs)
                self.assertTrue(path.is_file())
                return result

            with (
                patch(
                    "toc.image_request_snapshot.atomic_exchange_names",
                    side_effect=observe_exchange,
                ),
                patch(
                    "toc.image_request_snapshot.os.rename",
                    side_effect=observe_rename,
                ),
            ):
                write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            self.assertEqual(observed[0], "previous snapshot\n")
            self.assertNotEqual(observed[1], "previous snapshot\n")
            self.assertEqual(
                json.loads(observed[1])["request_revision"],
                snapshot.request_revision,
            )

    def test_atomic_overwrite_rollback_never_exposes_missing_canonical_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            observed: list[str] = []
            calls = 0

            def exchange_then_fail(source_fd, source, destination_fd, destination):
                nonlocal calls
                calls += 1
                observed.append(path.read_text(encoding="utf-8"))
                atomic_exchange_names(
                    source_fd,
                    source,
                    destination_fd,
                    destination,
                )
                observed.append(path.read_text(encoding="utf-8"))
                if calls == 1:
                    raise OSError("exchange completion was reported as failed")

            with patch(
                "toc.image_request_snapshot.atomic_exchange_names",
                side_effect=exchange_then_fail,
            ):
                with self.assertRaisesRegex(
                    ImageRequestSnapshotError,
                    "exchange completion was reported as failed",
                ):
                    write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            self.assertEqual(calls, 2)
            self.assertEqual(path.read_text(encoding="utf-8"), "previous snapshot\n")
            self.assertTrue(all(observation for observation in observed))

    def test_atomic_overwrite_rolls_back_after_base_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            calls = 0

            def exchange_then_interrupt(source_fd, source, destination_fd, destination):
                nonlocal calls
                calls += 1
                atomic_exchange_names(
                    source_fd,
                    source,
                    destination_fd,
                    destination,
                )
                if calls == 1:
                    raise KeyboardInterrupt("injected interrupt after exchange")

            with patch(
                "toc.image_request_snapshot.atomic_exchange_names",
                side_effect=exchange_then_interrupt,
            ):
                with self.assertRaisesRegex(
                    KeyboardInterrupt,
                    "injected interrupt after exchange",
                ):
                    write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            self.assertEqual(calls, 2)
            self.assertEqual(path.read_text(encoding="utf-8"), "previous snapshot\n")
            self.assertEqual(list(run_dir.glob(f".{path.name}.*.tmp")), [])

    def test_atomic_overwrite_failed_rollback_preserves_both_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            calls = 0
            observed: list[str] = []

            def publish_then_fail_rollback(
                source_fd,
                source,
                destination_fd,
                destination,
            ):
                nonlocal calls
                calls += 1
                observed.append(path.read_text(encoding="utf-8"))
                if calls == 1:
                    atomic_exchange_names(
                        source_fd,
                        source,
                        destination_fd,
                        destination,
                    )
                    observed.append(path.read_text(encoding="utf-8"))
                    raise OSError("injected post-exchange failure")
                raise OSError("injected rollback exchange failure")

            with patch(
                "toc.image_request_snapshot.atomic_exchange_names",
                side_effect=publish_then_fail_rollback,
            ):
                with self.assertRaisesRegex(
                    ImageRequestSnapshotError,
                    "previous snapshot could not be restored atomically",
                ):
                    write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            self.assertEqual(calls, 2)
            self.assertTrue(all(observation for observation in observed))
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["request_revision"],
                snapshot.request_revision,
            )
            retained = list(run_dir.glob(f".{path.name}.*.tmp"))
            self.assertEqual(len(retained), 1)
            self.assertEqual(
                retained[0].read_text(encoding="utf-8"),
                "previous snapshot\n",
            )

    def test_atomic_overwrite_reconciles_failed_post_exchange_inspection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            from toc.image_request_snapshot import _snapshot_named_stat

            exchange_completed = False
            inspection_failed = False

            def exchange_then_fail(source_fd, source, destination_fd, destination):
                nonlocal exchange_completed
                atomic_exchange_names(
                    source_fd,
                    source,
                    destination_fd,
                    destination,
                )
                exchange_completed = True
                raise OSError("injected post-exchange failure")

            def fail_first_reconciliation_inspection(parent_fd, name):
                nonlocal inspection_failed
                if (
                    exchange_completed
                    and not inspection_failed
                    and name == path.name
                ):
                    inspection_failed = True
                    raise OSError("injected reconciliation inspection failure")
                return _snapshot_named_stat(parent_fd, name)

            with (
                patch(
                    "toc.image_request_snapshot.atomic_exchange_names",
                    side_effect=exchange_then_fail,
                ),
                patch(
                    "toc.image_request_snapshot._snapshot_named_stat",
                    side_effect=fail_first_reconciliation_inspection,
                ),
            ):
                with self.assertRaisesRegex(
                    ImageRequestSnapshotError,
                    "reconciliation inspection failure",
                ):
                    write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            self.assertTrue(inspection_failed)
            self.assertEqual(path.read_text(encoding="utf-8"), "previous snapshot\n")
            self.assertEqual(list(run_dir.glob(f".{path.name}.*.tmp")), [])

    def test_atomic_overwrite_indeterminate_rollback_is_fsynced_and_wrapped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )
            from toc.image_request_snapshot import _snapshot_named_stat

            exchange_calls = 0
            inspection_failed = False
            fsync_calls = 0
            real_fsync = os.fsync

            def publish_then_fail_rollback(
                source_fd,
                source,
                destination_fd,
                destination,
            ):
                nonlocal exchange_calls
                exchange_calls += 1
                if exchange_calls == 1:
                    atomic_exchange_names(
                        source_fd,
                        source,
                        destination_fd,
                        destination,
                    )
                    raise OSError("injected initial post-exchange failure")
                raise OSError("injected rollback exchange failure")

            def fail_rollback_inspection(parent_fd, name):
                nonlocal inspection_failed
                if exchange_calls >= 2 and not inspection_failed:
                    inspection_failed = True
                    raise OSError("injected rollback inspection failure")
                return _snapshot_named_stat(parent_fd, name)

            def count_fsync(descriptor):
                nonlocal fsync_calls
                fsync_calls += 1
                return real_fsync(descriptor)

            with (
                patch(
                    "toc.image_request_snapshot.atomic_exchange_names",
                    side_effect=publish_then_fail_rollback,
                ),
                patch(
                    "toc.image_request_snapshot._snapshot_named_stat",
                    side_effect=fail_rollback_inspection,
                ),
                patch(
                    "toc.image_request_snapshot.os.fsync",
                    side_effect=count_fsync,
                ),
            ):
                with self.assertRaisesRegex(
                    ImageRequestSnapshotError,
                    "rollback.*inspection|restored atomically",
                ):
                    write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            self.assertEqual(exchange_calls, 2)
            self.assertTrue(inspection_failed)
            self.assertGreaterEqual(fsync_calls, 3)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["request_revision"],
                snapshot.request_revision,
            )
            retained = list(run_dir.glob(f".{path.name}.*.tmp"))
            self.assertEqual(len(retained), 1)
            self.assertEqual(retained[0].read_text(encoding="utf-8"), "previous snapshot\n")

    def test_atomic_overwrite_fails_closed_when_exchange_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )

            with patch(
                "toc.image_request_snapshot.atomic_exchange_names",
                side_effect=AtomicExchangeUnavailableError(
                    errno.ENOTSUP,
                    "native atomic name exchange is unavailable",
                ),
            ):
                with self.assertRaisesRegex(
                    ImageRequestSnapshotError,
                    "native atomic name exchange is unavailable",
                ):
                    write_request_snapshot_atomic(path, snapshot, run_dir=run_dir)

            self.assertEqual(path.read_text(encoding="utf-8"), "previous snapshot\n")
            self.assertEqual(list(run_dir.glob(f".{path.name}.*.tmp")), [])

    def test_atomic_overwrite_postcommit_cleanup_failure_returns_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = run_dir / "image_generation_request_snapshot.json"
            path.write_text("previous snapshot\n", encoding="utf-8")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[_item("scene1_cut1", "assets/scenes/scene1_cut1.png")],
            )

            with patch(
                "toc.image_request_snapshot._snapshot_cleanup_public_name",
                side_effect=OSError("injected postcommit cleanup failure"),
            ):
                result = write_request_snapshot_atomic(
                    path,
                    snapshot,
                    run_dir=run_dir,
                )

            self.assertEqual(result, path)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["request_revision"],
                snapshot.request_revision,
            )

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
