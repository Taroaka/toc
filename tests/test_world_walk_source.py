from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.world_walk_source import (
    copy_regular_file_atomic_nofollow,
    directory_identity_nofollow,
    unlink_regular_file_verified_nofollow,
    write_regular_file_nofollow,
)


class WorldWalkSourceWriteTests(unittest.TestCase):
    def test_nonexclusive_write_replaces_hardlink_without_mutating_outside_inode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination_root = root / "run"
            destination_root.mkdir()
            outside = root / "outside.txt"
            outside.write_bytes(b"outside-original")
            destination = destination_root / "state.txt"
            os.link(outside, destination)
            outside_identity = (outside.stat().st_dev, outside.stat().st_ino)

            digest = write_regular_file_nofollow(
                destination_root=destination_root,
                destination_relative="state.txt",
                data=b"new-state",
            )

            self.assertEqual(
                digest,
                hashlib.sha256(b"new-state").hexdigest(),
            )
            self.assertEqual(outside.read_bytes(), b"outside-original")
            self.assertEqual(
                (outside.stat().st_dev, outside.stat().st_ino),
                outside_identity,
            )
            self.assertEqual(destination.read_bytes(), b"new-state")
            self.assertNotEqual(
                (destination.stat().st_dev, destination.stat().st_ino),
                outside_identity,
            )

    def test_nonexclusive_write_replaces_existing_inode_instead_of_truncating_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            destination_root = Path(td)
            destination = destination_root / "state.txt"
            destination.write_bytes(b"old-state")
            descriptor = os.open(destination, os.O_RDONLY)
            original_identity = (
                destination.stat().st_dev,
                destination.stat().st_ino,
            )
            try:
                write_regular_file_nofollow(
                    destination_root=destination_root,
                    destination_relative="state.txt",
                    data=b"new-state",
                )
                os.lseek(descriptor, 0, os.SEEK_SET)
                self.assertEqual(os.read(descriptor, 1024), b"old-state")
            finally:
                os.close(descriptor)

            self.assertEqual(destination.read_bytes(), b"new-state")
            self.assertNotEqual(
                (destination.stat().st_dev, destination.stat().st_ino),
                original_identity,
            )

    def test_nonexclusive_write_rejects_symlink_without_touching_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination_root = root / "run"
            destination_root.mkdir()
            outside = root / "outside.txt"
            outside.write_bytes(b"outside-original")
            destination = destination_root / "state.txt"
            destination.symlink_to(outside)

            with self.assertRaisesRegex(
                ValueError,
                "destination.*(regular file|symlink|unsafe)",
            ):
                write_regular_file_nofollow(
                    destination_root=destination_root,
                    destination_relative="state.txt",
                    data=b"new-state",
                )

            self.assertTrue(destination.is_symlink())
            self.assertEqual(outside.read_bytes(), b"outside-original")

    def test_nonexclusive_write_preserves_bytes_when_temp_name_is_substituted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            destination_root = Path(td)
            destination = destination_root / "state.txt"
            destination.write_bytes(b"old-state")
            attacker = destination_root / "attacker.tmp"
            attacker.write_bytes(b"attacker-state")
            sibling = destination_root / "sibling.txt"
            sibling.write_bytes(b"sibling-sentinel")
            original_replace = os.replace
            substituted = False

            def substitute_temp_before_publish(
                source: str,
                target: str,
                *,
                src_dir_fd: int,
                dst_dir_fd: int,
            ) -> None:
                nonlocal substituted
                if not substituted and target == destination.name:
                    substituted = True
                    original_replace(
                        attacker.name,
                        source,
                        src_dir_fd=src_dir_fd,
                        dst_dir_fd=src_dir_fd,
                    )
                original_replace(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            with (
                patch(
                    "scripts.world_walk_source.os.replace",
                    side_effect=substitute_temp_before_publish,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "destination.*(identity|changed|rollback)",
                ),
            ):
                write_regular_file_nofollow(
                    destination_root=destination_root,
                    destination_relative="state.txt",
                    data=b"new-state",
                )

            self.assertTrue(substituted)
            self.assertEqual(sibling.read_bytes(), b"sibling-sentinel")
            remaining_payloads = {
                path.read_bytes()
                for path in destination_root.iterdir()
                if path.is_file() and not path.is_symlink()
            }
            self.assertIn(b"old-state", remaining_payloads)
            self.assertIn(b"attacker-state", remaining_payloads)


class WorldWalkSourceCleanupTests(unittest.TestCase):
    def test_atomic_copy_does_not_unlink_substituted_temp_or_destination(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_root = root / "source"
            source = source_root / "assets/hero.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"trusted-source")
            destination_root = root / "target"
            destination_root.mkdir()
            destination_relative = Path("assets/source_references/hero.png")
            destination_parent = destination_root / destination_relative.parent
            sibling = destination_parent / "sibling-sentinel.png"
            sibling.parent.mkdir(parents=True)
            sibling.write_bytes(b"attacker-replacement")
            original_link = os.link
            substituted_temp: Path | None = None

            def substitute_temp_name(
                source_name: str,
                destination_name: str,
                *,
                src_dir_fd: int,
                dst_dir_fd: int,
                follow_symlinks: bool,
            ) -> None:
                nonlocal substituted_temp
                os.unlink(source_name, dir_fd=src_dir_fd)
                original_link(
                    sibling.name,
                    source_name,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=src_dir_fd,
                    follow_symlinks=False,
                )
                substituted_temp = destination_parent / source_name
                original_link(
                    source_name,
                    destination_name,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with (
                patch(
                    "scripts.world_walk_source.os.link",
                    side_effect=substitute_temp_name,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "published destination identity mismatch",
                ),
            ):
                copy_regular_file_atomic_nofollow(
                    source_root=source_root,
                    source_relative="assets/hero.png",
                    destination_root=destination_root,
                    destination_relative=destination_relative,
                )

            destination = destination_root / destination_relative
            self.assertIsNotNone(substituted_temp)
            self.assertTrue(substituted_temp.is_file())
            self.assertEqual(
                substituted_temp.read_bytes(),
                b"attacker-replacement",
            )
            self.assertEqual(destination.read_bytes(), b"attacker-replacement")
            self.assertEqual(sibling.read_bytes(), b"attacker-replacement")

    def test_verified_unlink_preserves_name_reused_after_identity_check(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "reference.png"
            target.write_bytes(b"owned-reference")
            sibling = root / "sibling-sentinel.png"
            sibling.write_bytes(b"racing-replacement")
            expected_root_identity = directory_identity_nofollow(root)
            expected_sha256 = hashlib.sha256(b"owned-reference").hexdigest()
            original_stat = os.stat
            original_unlink = os.unlink
            original_link = os.link
            target_stats = 0

            def substitute_after_identity_check(
                path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
                *args,
                **kwargs,
            ):
                nonlocal target_stats
                result = original_stat(path, *args, **kwargs)
                if (
                    path == target.name
                    and kwargs.get("dir_fd") is not None
                    and kwargs.get("follow_symlinks") is False
                ):
                    target_stats += 1
                    if target_stats == 2:
                        original_unlink(
                            target.name,
                            dir_fd=kwargs["dir_fd"],
                        )
                        original_link(
                            sibling.name,
                            target.name,
                            src_dir_fd=kwargs["dir_fd"],
                            dst_dir_fd=kwargs["dir_fd"],
                            follow_symlinks=False,
                        )
                return result

            with patch(
                "scripts.world_walk_source.os.stat",
                side_effect=substitute_after_identity_check,
            ):
                removed = unlink_regular_file_verified_nofollow(
                    root=root,
                    relative_path=target.name,
                    expected_root_identity=expected_root_identity,
                    expected_sha256=expected_sha256,
                )

            self.assertFalse(removed)
            self.assertEqual(target.read_bytes(), b"racing-replacement")
            self.assertEqual(sibling.read_bytes(), b"racing-replacement")
            self.assertEqual(
                (target.stat().st_dev, target.stat().st_ino),
                (sibling.stat().st_dev, sibling.stat().st_ino),
            )


if __name__ == "__main__":
    unittest.main()
