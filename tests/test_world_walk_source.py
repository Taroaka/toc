from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toc.atomic_exchange import AtomicExchangeUnavailableError

from scripts.world_walk_source import (
    _entry_identity,
    _remove_owned_name_nofollow,
    _restore_quarantined_entry_nofollow,
    copy_regular_file_atomic_nofollow,
    directory_identity_nofollow,
    unlink_regular_file_verified_nofollow,
    write_regular_file_nofollow,
)


class WorldWalkSourceWriteTests(unittest.TestCase):
    def test_existing_overwrite_keeps_canonical_name_visible_at_exchange(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination = root / "state.txt"
            destination.write_bytes(b"old-state")
            from toc.atomic_exchange import atomic_exchange_names

            observed: list[bytes] = []

            def observe_exchange(
                source_dir_fd: int,
                source_name: str,
                destination_dir_fd: int,
                destination_name: str,
            ) -> None:
                observed.append(destination.read_bytes())
                atomic_exchange_names(
                    source_dir_fd,
                    source_name,
                    destination_dir_fd,
                    destination_name,
                )
                observed.append(destination.read_bytes())

            with patch(
                "scripts.world_walk_source.atomic_exchange_names",
                side_effect=observe_exchange,
            ):
                write_regular_file_nofollow(
                    destination_root=root,
                    destination_relative=destination.name,
                    data=b"new-state",
                )

            self.assertEqual(observed, [b"old-state", b"new-state"])
            self.assertEqual(destination.read_bytes(), b"new-state")

    def test_post_exchange_failure_rolls_back_without_missing_canonical_name(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination = root / "state.txt"
            destination.write_bytes(b"old-state")
            from toc.atomic_exchange import atomic_exchange_names

            original_fsync = os.fsync
            root_identity = (root.stat().st_dev, root.stat().st_ino)
            observed: list[tuple[bytes, bytes]] = []
            exchange_calls = 0
            failed = False

            def observe_exchange(
                source_dir_fd: int,
                source_name: str,
                destination_dir_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal exchange_calls
                exchange_calls += 1
                before = destination.read_bytes()
                atomic_exchange_names(
                    source_dir_fd,
                    source_name,
                    destination_dir_fd,
                    destination_name,
                )
                observed.append((before, destination.read_bytes()))

            def fail_publication_parent_fsync(descriptor: int) -> None:
                nonlocal failed
                opened = os.fstat(descriptor)
                if (
                    not failed
                    and stat.S_ISDIR(opened.st_mode)
                    and (opened.st_dev, opened.st_ino) == root_identity
                ):
                    failed = True
                    raise OSError("injected post-exchange failure")
                original_fsync(descriptor)

            with (
                patch(
                    "scripts.world_walk_source.atomic_exchange_names",
                    side_effect=observe_exchange,
                ),
                patch(
                    "scripts.world_walk_source.os.fsync",
                    side_effect=fail_publication_parent_fsync,
                ),
                self.assertRaisesRegex(
                    OSError,
                    "injected post-exchange failure",
                ),
            ):
                write_regular_file_nofollow(
                    destination_root=root,
                    destination_relative=destination.name,
                    data=b"new-state",
                )

            self.assertTrue(failed)
            self.assertEqual(exchange_calls, 2)
            self.assertEqual(
                observed,
                [
                    (b"old-state", b"new-state"),
                    (b"new-state", b"old-state"),
                ],
            )
            self.assertEqual(destination.read_bytes(), b"old-state")

    def test_existing_overwrite_fails_closed_without_atomic_exchange(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination = root / "state.txt"
            destination.write_bytes(b"old-state")

            with (
                patch(
                    "scripts.world_walk_source.atomic_exchange_names",
                    side_effect=AtomicExchangeUnavailableError(
                        "atomic exchange unavailable"
                    ),
                ),
                self.assertRaisesRegex(
                    AtomicExchangeUnavailableError,
                    "atomic exchange unavailable",
                ),
            ):
                write_regular_file_nofollow(
                    destination_root=root,
                    destination_relative=destination.name,
                    data=b"new-state",
                )

            self.assertEqual(destination.read_bytes(), b"old-state")

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

    def test_nonexclusive_write_does_not_clobber_destination_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination = root / "state.txt"
            victim = root / "victim.txt"
            destination.write_bytes(b"old-state")
            victim.write_bytes(b"must-survive")
            victim_identity = _entry_identity(victim.stat())
            original_rename = os.rename
            from toc.atomic_exchange import atomic_exchange_names

            raced = False

            def race_destination_before_exchange(
                source_dir_fd: int,
                source_name: str,
                destination_dir_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal raced
                if not raced and destination_name == destination.name:
                    raced = True
                    original_rename(
                        victim.name,
                        destination.name,
                        src_dir_fd=destination_dir_fd,
                        dst_dir_fd=destination_dir_fd,
                    )
                atomic_exchange_names(
                    source_dir_fd,
                    source_name,
                    destination_dir_fd,
                    destination_name,
                )

            with (
                patch(
                    "scripts.world_walk_source.atomic_exchange_names",
                    side_effect=race_destination_before_exchange,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "destination.*(changed|rollback|publishing)",
                ),
            ):
                write_regular_file_nofollow(
                    destination_root=root,
                    destination_relative=destination.name,
                    data=b"new-state",
                )

            self.assertTrue(raced)
            self.assertEqual(destination.read_bytes(), b"must-survive")
            self.assertEqual(_entry_identity(destination.stat()), victim_identity)
            self.assertFalse(victim.exists())

    def test_nonexclusive_write_fails_closed_when_publication_disappears(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination = root / "state.txt"
            destination.write_bytes(b"old-state")
            original_fsync = os.fsync
            original_unlink = os.unlink
            fsync_calls = 0

            def remove_publication_before_parent_fsync(
                descriptor: int,
            ) -> None:
                nonlocal fsync_calls
                fsync_calls += 1
                if fsync_calls == 2:
                    original_unlink(destination.name, dir_fd=descriptor)
                    raise OSError("injected parent fsync failure")
                original_fsync(descriptor)

            with (
                patch(
                    "scripts.world_walk_source.os.fsync",
                    side_effect=remove_publication_before_parent_fsync,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "destination changed before safe rollback",
                ),
            ):
                write_regular_file_nofollow(
                    destination_root=root,
                    destination_relative=destination.name,
                    data=b"new-state",
                )

            self.assertEqual(fsync_calls, 4)
            self.assertFalse(destination.exists())
            self.assertIn(
                b"old-state",
                {
                    path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                },
            )

    def test_rollback_unlink_failure_keeps_canonical_destination_attached(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination = root / "state.txt"
            original_fsync = os.fsync
            original_unlink = os.unlink
            root_identity = (root.stat().st_dev, root.stat().st_ino)
            parent_fsync_failed = False
            protected_unlinks = 0

            def fail_publication_parent_fsync(descriptor: int) -> None:
                nonlocal parent_fsync_failed
                opened = os.fstat(descriptor)
                if (
                    not parent_fsync_failed
                    and stat.S_ISDIR(opened.st_mode)
                    and (opened.st_dev, opened.st_ino) == root_identity
                ):
                    parent_fsync_failed = True
                    raise OSError("injected publication fsync failure")
                original_fsync(descriptor)

            def fail_rollback_protected_unlink(
                name: str,
                *,
                dir_fd: int | None = None,
            ) -> None:
                nonlocal protected_unlinks
                if dir_fd is not None:
                    opened = os.fstat(dir_fd)
                    opened_identity = (opened.st_dev, opened.st_ino)
                    if (
                        stat.S_ISDIR(opened.st_mode)
                        and opened_identity != root_identity
                    ):
                        protected_unlinks += 1
                        if protected_unlinks == 2:
                            raise OSError(
                                "injected rollback cleanup failure"
                            )
                original_unlink(name, dir_fd=dir_fd)

            with (
                patch(
                    "scripts.world_walk_source.os.fsync",
                    side_effect=fail_publication_parent_fsync,
                ),
                patch(
                    "scripts.world_walk_source.os.unlink",
                    side_effect=fail_rollback_protected_unlink,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "destination changed before safe rollback",
                ),
            ):
                write_regular_file_nofollow(
                    destination_root=root,
                    destination_relative=destination.name,
                    data=b"new-state",
                )

            self.assertTrue(parent_fsync_failed)
            self.assertEqual(protected_unlinks, 3)
            self.assertEqual(destination.read_bytes(), b"new-state")

    def test_postcommit_backup_cleanup_failure_returns_committed_success(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination = root / "state.txt"
            destination.write_bytes(b"old-state")
            original_unlink = os.unlink
            root_identity = (root.stat().st_dev, root.stat().st_ino)
            protected_unlinks = 0

            def fail_postcommit_protected_unlink(
                name: str,
                *,
                dir_fd: int | None = None,
            ) -> None:
                nonlocal protected_unlinks
                if dir_fd is not None:
                    opened = os.fstat(dir_fd)
                    opened_identity = (opened.st_dev, opened.st_ino)
                    if (
                        stat.S_ISDIR(opened.st_mode)
                        and opened_identity != root_identity
                    ):
                        protected_unlinks += 1
                        if protected_unlinks == 1:
                            raise OSError(
                                "injected postcommit cleanup failure"
                            )
                original_unlink(name, dir_fd=dir_fd)

            with patch(
                "scripts.world_walk_source.os.unlink",
                side_effect=fail_postcommit_protected_unlink,
            ):
                digest = write_regular_file_nofollow(
                    destination_root=root,
                    destination_relative=destination.name,
                    data=b"new-state",
                )

            self.assertGreaterEqual(protected_unlinks, 2)
            self.assertEqual(
                digest,
                hashlib.sha256(b"new-state").hexdigest(),
            )
            self.assertEqual(destination.read_bytes(), b"new-state")

    def test_rollback_fsyncs_parent_and_cleanup_namespaces(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination = root / "state.txt"
            destination.write_bytes(b"old-state")
            original_fsync = os.fsync
            root_identity = (root.stat().st_dev, root.stat().st_ino)
            parent_fsyncs = 0
            cleanup_fsyncs = 0
            directory_fsync_order: list[str] = []

            def fail_publication_fsync_once(descriptor: int) -> None:
                nonlocal parent_fsyncs, cleanup_fsyncs
                opened = os.fstat(descriptor)
                if stat.S_ISDIR(opened.st_mode):
                    opened_identity = (opened.st_dev, opened.st_ino)
                    if opened_identity == root_identity:
                        parent_fsyncs += 1
                        directory_fsync_order.append("parent")
                        if parent_fsyncs == 1:
                            raise OSError(
                                "injected publication fsync failure"
                            )
                    else:
                        cleanup_fsyncs += 1
                        directory_fsync_order.append("cleanup")
                original_fsync(descriptor)

            with (
                patch(
                    "scripts.world_walk_source.os.fsync",
                    side_effect=fail_publication_fsync_once,
                ),
                self.assertRaisesRegex(
                    OSError,
                    "injected publication fsync failure",
                ),
            ):
                write_regular_file_nofollow(
                    destination_root=root,
                    destination_relative=destination.name,
                    data=b"new-state",
                )

            self.assertGreaterEqual(cleanup_fsyncs, 1)
            self.assertEqual(parent_fsyncs, 2)
            self.assertEqual(
                directory_fsync_order,
                ["parent", "parent", "cleanup"],
            )
            self.assertEqual(destination.read_bytes(), b"old-state")

    def test_rollback_cleanup_fsync_failure_is_distinct_fail_closed_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination = root / "state.txt"
            destination.write_bytes(b"old-state")
            original_fsync = os.fsync
            root_identity = (root.stat().st_dev, root.stat().st_ino)
            parent_fsyncs = 0
            cleanup_fsyncs = 0

            def fail_rollback_cleanup_fsync(descriptor: int) -> None:
                nonlocal parent_fsyncs, cleanup_fsyncs
                opened = os.fstat(descriptor)
                if stat.S_ISDIR(opened.st_mode):
                    opened_identity = (opened.st_dev, opened.st_ino)
                    if opened_identity == root_identity:
                        parent_fsyncs += 1
                        if parent_fsyncs == 1:
                            raise OSError(
                                "injected publication fsync failure"
                            )
                    else:
                        cleanup_fsyncs += 1
                        raise OSError(
                            "injected rollback cleanup fsync failure"
                        )
                original_fsync(descriptor)

            with (
                patch(
                    "scripts.world_walk_source.os.fsync",
                    side_effect=fail_rollback_cleanup_fsync,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "rollback durability could not be proved",
                ),
            ):
                write_regular_file_nofollow(
                    destination_root=root,
                    destination_relative=destination.name,
                    data=b"new-state",
                )

            self.assertEqual(cleanup_fsyncs, 1)
            self.assertEqual(parent_fsyncs, 2)
            self.assertEqual(destination.read_bytes(), b"old-state")

    def test_rollback_exchange_failure_still_fsyncs_both_namespaces(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            destination = root / "state.txt"
            destination.write_bytes(b"old-state")
            original_fsync = os.fsync
            from toc.atomic_exchange import atomic_exchange_names

            root_identity = (root.stat().st_dev, root.stat().st_ino)
            parent_fsyncs = 0
            cleanup_fsyncs = 0
            exchange_calls = 0
            rollback_visible_bytes: bytes | None = None

            def fail_publication_fsync_once(descriptor: int) -> None:
                nonlocal parent_fsyncs, cleanup_fsyncs
                opened = os.fstat(descriptor)
                if stat.S_ISDIR(opened.st_mode):
                    opened_identity = (opened.st_dev, opened.st_ino)
                    if opened_identity == root_identity:
                        parent_fsyncs += 1
                        if parent_fsyncs == 1:
                            raise OSError(
                                "injected publication fsync failure"
                            )
                    else:
                        cleanup_fsyncs += 1
                original_fsync(descriptor)

            def fail_rollback_exchange(
                source_dir_fd: int,
                source_name: str,
                destination_dir_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal exchange_calls, rollback_visible_bytes
                exchange_calls += 1
                if exchange_calls == 2:
                    rollback_visible_bytes = destination.read_bytes()
                    raise OSError("injected rollback exchange failure")
                atomic_exchange_names(
                    source_dir_fd,
                    source_name,
                    destination_dir_fd,
                    destination_name,
                )

            with (
                patch(
                    "scripts.world_walk_source.os.fsync",
                    side_effect=fail_publication_fsync_once,
                ),
                patch(
                    "scripts.world_walk_source.atomic_exchange_names",
                    side_effect=fail_rollback_exchange,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "atomic rollback exchange failed",
                ),
            ):
                write_regular_file_nofollow(
                    destination_root=root,
                    destination_relative=destination.name,
                    data=b"new-state",
                )

            self.assertEqual(exchange_calls, 2)
            self.assertEqual(rollback_visible_bytes, b"new-state")
            self.assertGreaterEqual(cleanup_fsyncs, 1)
            self.assertEqual(parent_fsyncs, 2)
            self.assertEqual(destination.read_bytes(), b"new-state")
            self.assertIn(
                b"old-state",
                {
                    path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file() and path != destination
                },
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
            original_rename = os.rename
            from toc.atomic_exchange import atomic_exchange_names

            substituted = False

            def substitute_temp_before_publish(
                source_dir_fd: int,
                source_name: str,
                destination_dir_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal substituted
                if not substituted:
                    substituted = True
                    original_rename(
                        attacker.name,
                        source_name,
                        src_dir_fd=source_dir_fd,
                        dst_dir_fd=source_dir_fd,
                    )
                atomic_exchange_names(
                    source_dir_fd,
                    source_name,
                    destination_dir_fd,
                    destination_name,
                )

            with (
                patch(
                    "scripts.world_walk_source.atomic_exchange_names",
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
            self.assertEqual(destination.read_bytes(), b"old-state")
            self.assertFalse(attacker.exists())
            quarantined_payloads = {
                path.read_bytes()
                for path in destination_root.rglob("*")
                if path.is_file()
                and path not in {destination, sibling}
            }
            self.assertIn(b"attacker-state", quarantined_payloads)
            self.assertEqual(
                sorted(
                    path.name
                    for path in destination_root.iterdir()
                    if not path.is_dir()
                ),
                ["sibling.txt", "state.txt"],
            )

    def test_nonexclusive_write_removes_substituted_absent_publication(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            destination_root = Path(td)
            destination = destination_root / "state.txt"
            sibling = destination_root / "sibling.txt"
            sibling.write_bytes(b"attacker-state")
            original_link = os.link
            substituted = False

            def substitute_temp_before_link(
                source: str,
                target: str,
                *,
                src_dir_fd: int,
                dst_dir_fd: int,
                follow_symlinks: bool,
            ) -> None:
                nonlocal substituted
                if not substituted and target == destination.name:
                    substituted = True
                    os.unlink(source, dir_fd=src_dir_fd)
                    original_link(
                        sibling.name,
                        source,
                        src_dir_fd=src_dir_fd,
                        dst_dir_fd=src_dir_fd,
                        follow_symlinks=False,
                    )
                original_link(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with (
                patch(
                    "scripts.world_walk_source.os.link",
                    side_effect=substitute_temp_before_link,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "destination.*identity changed",
                ),
            ):
                write_regular_file_nofollow(
                    destination_root=destination_root,
                    destination_relative=destination.name,
                    data=b"new-state",
                )

            self.assertTrue(substituted)
            self.assertFalse(destination.exists())
            self.assertEqual(sibling.read_bytes(), b"attacker-state")
            self.assertEqual(
                sorted(
                    path.name
                    for path in destination_root.iterdir()
                    if not path.is_dir()
                ),
                ["sibling.txt"],
            )


class WorldWalkSourceCleanupTests(unittest.TestCase):
    def test_restore_cleanup_failure_keeps_only_protected_alias(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            backup = root / "backup.bin"
            original = root / "original.bin"
            backup.write_bytes(b"rollback-state")
            backup_identity = _entry_identity(backup.stat())
            parent_descriptor = os.open(
                root,
                os.O_RDONLY | os.O_DIRECTORY,
            )
            original_unlink = os.unlink
            failed_once = False

            def fail_first_protected_unlink(
                name: str,
                *,
                dir_fd: int | None = None,
            ) -> None:
                nonlocal failed_once
                if not failed_once and dir_fd != parent_descriptor:
                    failed_once = True
                    raise OSError("injected protected cleanup failure")
                original_unlink(name, dir_fd=dir_fd)

            try:
                with patch(
                    "scripts.world_walk_source.os.unlink",
                    side_effect=fail_first_protected_unlink,
                ):
                    restored = _restore_quarantined_entry_nofollow(
                        parent_descriptor=parent_descriptor,
                        quarantine_name=backup.name,
                        original_name=original.name,
                        quarantined_identity=backup_identity,
                    )
            finally:
                os.close(parent_descriptor)

            self.assertTrue(failed_once)
            self.assertFalse(restored)
            self.assertEqual(original.read_bytes(), b"rollback-state")
            self.assertFalse(backup.exists())
            protected_files = [
                path for path in root.rglob("*") if path.is_file()
            ]
            self.assertEqual(len(protected_files), 2)
            self.assertIn(original, protected_files)

    def test_owned_cleanup_unlinks_only_in_protected_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "temporary.bin"
            target.write_bytes(b"owned")
            expected_identity = _entry_identity(target.stat())
            parent_descriptor = os.open(
                root,
                os.O_RDONLY | os.O_DIRECTORY,
            )
            original_unlink = os.unlink
            unlink_calls: list[tuple[str, int | None]] = []

            def record_unlink(
                name: str,
                *,
                dir_fd: int | None = None,
            ) -> None:
                unlink_calls.append((name, dir_fd))
                original_unlink(name, dir_fd=dir_fd)

            try:
                with patch(
                    "scripts.world_walk_source.os.unlink",
                    side_effect=record_unlink,
                ):
                    removed = _remove_owned_name_nofollow(
                        parent_descriptor=parent_descriptor,
                        name=target.name,
                        expected_identity=expected_identity,
                    )
            finally:
                os.close(parent_descriptor)

            self.assertTrue(removed)
            self.assertFalse(target.exists())
            self.assertTrue(unlink_calls)
            self.assertTrue(
                all(
                    dir_fd != parent_descriptor
                    for _name, dir_fd in unlink_calls
                )
            )
            cleanup_directories = [
                path
                for path in root.iterdir()
                if path.name.startswith(".toc-cleanup-")
            ]
            self.assertEqual(len(cleanup_directories), 1)
            self.assertEqual(
                stat.S_IMODE(cleanup_directories[0].stat().st_mode),
                0o700,
            )

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
            self.assertFalse(substituted_temp.exists())
            self.assertFalse(destination.exists())
            self.assertEqual(sibling.read_bytes(), b"attacker-replacement")
            quarantined_payloads = {
                path.read_bytes()
                for path in destination_parent.rglob("*")
                if path.is_file() and path != sibling
            }
            self.assertIn(b"attacker-replacement", quarantined_payloads)

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
