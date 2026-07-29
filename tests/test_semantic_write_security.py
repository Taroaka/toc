import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toc.partial_media import (
    PARTIAL_MEDIA_PROJECTION_RELPATH,
    PARTIAL_MEDIA_PROJECTION_SCHEMA,
    PARTIAL_MEDIA_RECEIPT_RELPATH,
    write_partial_media_generation_receipt,
    write_partial_media_projection,
)
from toc.semantic_review import safe_semantic_write_text


class SemanticWriteSecurityTests(unittest.TestCase):
    def test_safe_write_rejects_hardlinked_destination_without_replacing_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            root = Path(td)
            run_dir = root / "run"
            destination = run_dir / "logs" / "review.md"
            outside = root / "outside.md"
            destination.parent.mkdir(parents=True)
            outside.write_text("unrelated\n", encoding="utf-8")
            os.link(outside, destination)

            with self.assertRaisesRegex(ValueError, "multiple hard links"):
                safe_semantic_write_text(
                    run_dir,
                    destination,
                    "semantic artifact\n",
                )

            self.assertTrue(destination.samefile(outside))
            self.assertEqual(outside.read_text(encoding="utf-8"), "unrelated\n")

    def test_safe_write_does_not_clobber_destination_appearing_at_publish(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            root = Path(td)
            run_dir = root / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            original_link = os.link
            raced = False

            def create_destination_before_link(
                source,
                target,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
                follow_symlinks=True,
            ):
                nonlocal raced
                if not raced and target == destination.name:
                    raced = True
                    descriptor = os.open(
                        target,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=dst_dir_fd,
                    )
                    try:
                        os.write(descriptor, b"concurrent replacement\n")
                    finally:
                        os.close(descriptor)
                return original_link(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with patch(
                "toc.semantic_review.os.link",
                side_effect=create_destination_before_link,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "appeared|changed",
                ):
                    safe_semantic_write_text(
                        run_dir,
                        destination,
                        "semantic artifact\n",
                    )

            self.assertTrue(raced)
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "concurrent replacement\n",
            )

    def test_safe_write_preserves_hardlinked_leaf_reused_during_rename(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            root = Path(td)
            run_dir = root / "run"
            destination = run_dir / "logs" / "review.md"
            preserved_original = destination.with_name(
                ".review.original-preserved.md"
            )
            unrelated = root / "unrelated.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("canonical before write\n", encoding="utf-8")
            unrelated.write_text("unrelated replacement\n", encoding="utf-8")
            original_replace = os.replace
            original_link = os.link
            raced = False

            def reuse_destination_before_rename(
                source,
                target,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
            ):
                nonlocal raced
                if not raced:
                    raced = True
                    if src_dir_fd is None:
                        original_replace(destination, preserved_original)
                        original_link(unrelated, destination)
                    else:
                        original_replace(
                            source,
                            preserved_original.name,
                            src_dir_fd=src_dir_fd,
                            dst_dir_fd=src_dir_fd,
                        )
                        original_link(
                            unrelated,
                            source,
                            dst_dir_fd=src_dir_fd,
                            follow_symlinks=False,
                        )
                return original_replace(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            with patch(
                "toc.semantic_review.os.replace",
                side_effect=reuse_destination_before_rename,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "identity changed|multiple hard links",
                ):
                    safe_semantic_write_text(
                        run_dir,
                        destination,
                        "semantic artifact\n",
                    )

            self.assertTrue(raced)
            self.assertTrue(destination.samefile(unrelated))
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "unrelated replacement\n",
            )
            self.assertEqual(
                preserved_original.read_text(encoding="utf-8"),
                "canonical before write\n",
            )

    def test_partial_media_projection_parent_swap_never_publishes_outside(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            root = Path(td)
            run_dir = root / "run"
            semantic_dir = run_dir / "logs" / "review" / "semantic"
            detached_semantic_dir = root / "semantic-original"
            outside = root / "outside"
            semantic_dir.mkdir(parents=True)
            outside.mkdir()
            destination = run_dir / PARTIAL_MEDIA_PROJECTION_RELPATH
            outside_destination = outside / destination.name
            destination.write_text("canonical before write\n", encoding="utf-8")
            outside_destination.write_text(
                "outside must not change\n",
                encoding="utf-8",
            )
            original_replace = os.replace
            swapped = False

            def swap_parent_before_rename(
                source,
                target,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
            ):
                nonlocal swapped
                if not swapped:
                    semantic_dir.rename(detached_semantic_dir)
                    semantic_dir.symlink_to(
                        outside,
                        target_is_directory=True,
                    )
                    # The vulnerable pathname implementation resolves both
                    # names again after the swap. Mirror its temp entry outside
                    # so the unsafe rename deterministically reaches the
                    # attacker-controlled directory.
                    if src_dir_fd is None:
                        detached_temp = detached_semantic_dir / Path(source).name
                        (outside / Path(source).name).write_bytes(
                            detached_temp.read_bytes()
                        )
                    swapped = True
                return original_replace(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            projection = {
                "schema_version": PARTIAL_MEDIA_PROJECTION_SCHEMA,
                "projection_sha256": "sha256:test",
            }
            with patch(
                "toc.semantic_review.os.replace",
                side_effect=swap_parent_before_rename,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "identity changed|became unsafe",
                ):
                    write_partial_media_projection(run_dir, projection)

            self.assertTrue(swapped)
            self.assertEqual(
                outside_destination.read_text(encoding="utf-8"),
                "outside must not change\n",
            )
            self.assertEqual(
                (detached_semantic_dir / destination.name).read_text(
                    encoding="utf-8"
                ),
                "canonical before write\n",
            )

    def test_partial_media_receipt_rejects_hardlinked_destination(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            root = Path(td)
            run_dir = root / "run"
            destination = run_dir / PARTIAL_MEDIA_RECEIPT_RELPATH
            unrelated = root / "unrelated-receipt.json"
            destination.parent.mkdir(parents=True)
            unrelated.write_text(
                json.dumps({"owner": "unrelated"}) + "\n",
                encoding="utf-8",
            )
            os.link(unrelated, destination)

            with self.assertRaisesRegex(ValueError, "multiple hard links"):
                write_partial_media_generation_receipt(
                    run_dir,
                    projection={
                        "request_revision": "revision-1",
                        "projection_sha256": "sha256:projection",
                        "blocked_image_item_ids": [],
                        "synthetic_candidates": [],
                    },
                    provider_submitted_item_ids=[],
                    reused_item_ids=[],
                    generated_item_ids=[],
                    satisfied_item_ids=[],
                )

            self.assertTrue(destination.samefile(unrelated))
            self.assertEqual(
                json.loads(unrelated.read_text(encoding="utf-8")),
                {"owner": "unrelated"},
            )


if __name__ == "__main__":
    unittest.main()
