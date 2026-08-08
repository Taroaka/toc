import json
import os
import stat
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
from toc.semantic_review import (
    SemanticWriteIndeterminateError,
    _semantic_entry_identity,
    _semantic_unlink_if_identity,
    safe_semantic_write_text,
)
from toc.run_root_binding import RunRootBindingError, bind_run_root


class SemanticWriteSecurityTests(unittest.TestCase):
    def test_bound_safe_write_rejects_replaced_run_root(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            root = Path(td)
            run_dir = root / "run"
            original = root / "original"
            replacement = root / "replacement"
            run_dir.mkdir()
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            with bind_run_root(run_dir, expected_identity=identity):
                run_dir.rename(original)
                run_dir.mkdir()
                try:
                    with self.assertRaises(RunRootBindingError):
                        safe_semantic_write_text(
                            run_dir,
                            run_dir / "logs" / "review.md",
                            "must not publish\n",
                        )
                finally:
                    run_dir.rename(replacement)
                    original.rename(run_dir)

            self.assertFalse((replacement / "logs" / "review.md").exists())
            self.assertFalse((run_dir / "logs" / "review.md").exists())

    def test_identity_cleanup_restores_raced_entry_without_hardlink_residue(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            root = Path(td)
            target = root / "temporary.md"
            replacement = root / "replacement.md"
            owned_survivor = root / "owned-survivor.md"
            target.write_text("owned\n", encoding="utf-8")
            replacement.write_text("raced replacement\n", encoding="utf-8")
            expected_identity = _semantic_entry_identity(target.stat())
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            original_rename = os.rename
            substituted = False

            def substitute_source_during_quarantine(
                source,
                destination,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
            ):
                nonlocal substituted
                if not substituted and source == target.name:
                    substituted = True
                    original_rename(
                        target.name,
                        owned_survivor.name,
                        src_dir_fd=src_dir_fd,
                        dst_dir_fd=src_dir_fd,
                    )
                    original_rename(
                        replacement.name,
                        target.name,
                        src_dir_fd=src_dir_fd,
                        dst_dir_fd=src_dir_fd,
                    )
                return original_rename(
                    source,
                    destination,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            try:
                with patch(
                    "toc.semantic_review.os.rename",
                    side_effect=substitute_source_during_quarantine,
                ):
                    removed = _semantic_unlink_if_identity(
                        parent_fd,
                        target.name,
                        expected_identity,
                    )
            finally:
                os.close(parent_fd)

            self.assertTrue(substituted)
            self.assertFalse(removed)
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "raced replacement\n",
            )
            self.assertEqual(target.stat().st_nlink, 1)
            self.assertFalse(replacement.exists())
            self.assertEqual(
                owned_survivor.read_text(encoding="utf-8"),
                "owned\n",
            )
            self.assertEqual(
                sorted(
                    path.name for path in root.rglob("*") if path.is_file()
                ),
                ["owned-survivor.md", "temporary.md"],
            )

    def test_identity_cleanup_unlinks_only_in_protected_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            root = Path(td)
            target = root / "temporary.md"
            target.write_text("owned\n", encoding="utf-8")
            expected_identity = _semantic_entry_identity(target.stat())
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            original_unlink = os.unlink
            unlink_calls: list[tuple[str, int | None]] = []

            def record_unlink(
                name,
                *,
                dir_fd=None,
            ):
                unlink_calls.append((str(name), dir_fd))
                return original_unlink(name, dir_fd=dir_fd)

            try:
                with patch(
                    "toc.semantic_review.os.unlink",
                    side_effect=record_unlink,
                ):
                    removed = _semantic_unlink_if_identity(
                        parent_fd,
                        target.name,
                        expected_identity,
                    )
            finally:
                os.close(parent_fd)

            self.assertTrue(removed)
            self.assertFalse(target.exists())
            self.assertTrue(unlink_calls)
            self.assertTrue(
                all(dir_fd != parent_fd for _name, dir_fd in unlink_calls)
            )
            cleanup_directories = [
                path
                for path in root.iterdir()
                if path.name.startswith(".semantic-cleanup-")
            ]
            self.assertEqual(len(cleanup_directories), 1)
            self.assertEqual(
                stat.S_IMODE(cleanup_directories[0].stat().st_mode),
                0o700,
            )

    def test_safe_write_never_clobbers_backup_reserve_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            root = Path(td)
            run_dir = root / "run"
            destination = run_dir / "logs" / "review.md"
            victim = destination.parent / "victim.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("previous\n", encoding="utf-8")
            victim.write_text("must survive\n", encoding="utf-8")
            original_link = os.link
            original_rename = os.rename
            raced_backup: Path | None = None
            race_injected = False

            def reserve_shared_backup_name_before_rename(
                source,
                target,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
            ):
                nonlocal raced_backup, race_injected
                if (
                    not race_injected
                    and str(source).startswith(".semantic-write-")
                    and str(target).startswith("backup-")
                ):
                    race_injected = True
                    raced_backup = destination.parent / str(target)
                    original_link(
                        victim.name,
                        target,
                        src_dir_fd=src_dir_fd,
                        dst_dir_fd=src_dir_fd,
                        follow_symlinks=False,
                    )
                return original_rename(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            with patch(
                "toc.semantic_review.os.rename",
                side_effect=reserve_shared_backup_name_before_rename,
            ):
                safe_semantic_write_text(
                    run_dir,
                    destination,
                    "new\n",
                )

            self.assertTrue(race_injected)
            self.assertIsNotNone(raced_backup)
            self.assertEqual(destination.read_text(encoding="utf-8"), "new\n")
            self.assertEqual(victim.read_text(encoding="utf-8"), "must survive\n")
            self.assertTrue(raced_backup.samefile(victim))

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

    def test_safe_write_quarantines_substituted_temporary_publication(
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
            substituted = False

            def substitute_temporary_during_publish(
                source,
                target,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
                follow_symlinks=True,
            ):
                nonlocal substituted
                if not substituted and target == destination.name:
                    substituted = True
                    os.unlink(source, dir_fd=src_dir_fd)
                    descriptor = os.open(
                        source,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=src_dir_fd,
                    )
                    try:
                        os.write(descriptor, b"attacker bytes\n")
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
                side_effect=substitute_temporary_during_publish,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "identity changed after publish",
                ):
                    safe_semantic_write_text(
                        run_dir,
                        destination,
                        "semantic artifact\n",
                    )

            self.assertTrue(substituted)
            self.assertFalse(destination.exists())
            quarantined_files = [
                path
                for path in destination.parent.rglob("*")
                if path.is_file()
            ]
            self.assertTrue(quarantined_files)
            self.assertEqual(
                {path.read_text(encoding="utf-8") for path in quarantined_files},
                {"attacker bytes\n"},
            )

    def test_safe_write_parent_fsync_failure_restores_previous_artifact(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            root = Path(td)
            run_dir = root / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("previous artifact\n", encoding="utf-8")
            original_fsync = os.fsync
            original_rename = os.rename
            parent_identity: tuple[int, int] | None = None
            cleanup_identity: tuple[int, int] | None = None
            cleanup_fd: int | None = None
            backup_name: str | None = None
            publication_fsync_failed = False
            rollback_sync_identities: list[tuple[int, int]] = []
            backup_retained_at_parent_sync = False

            def capture_backup_namespaces(
                source,
                target,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
            ):
                nonlocal parent_identity, cleanup_identity
                nonlocal cleanup_fd, backup_name
                if (
                    str(source).startswith(".semantic-write-")
                    and str(target).startswith("backup-")
                ):
                    parent_stat = os.fstat(src_dir_fd)
                    cleanup_stat = os.fstat(dst_dir_fd)
                    parent_identity = parent_stat.st_dev, parent_stat.st_ino
                    cleanup_identity = cleanup_stat.st_dev, cleanup_stat.st_ino
                    cleanup_fd = dst_dir_fd
                    backup_name = str(target)
                return original_rename(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            def fail_publication_fsync(descriptor: int) -> None:
                nonlocal publication_fsync_failed
                nonlocal backup_retained_at_parent_sync
                descriptor_stat = os.fstat(descriptor)
                descriptor_identity = (
                    descriptor_stat.st_dev,
                    descriptor_stat.st_ino,
                )
                if (
                    not publication_fsync_failed
                    and parent_identity is not None
                    and descriptor_identity == parent_identity
                ):
                    publication_fsync_failed = True
                    raise OSError("injected parent fsync failure")
                if publication_fsync_failed:
                    rollback_sync_identities.append(descriptor_identity)
                    if descriptor_identity == parent_identity:
                        try:
                            os.stat(
                                backup_name,
                                dir_fd=cleanup_fd,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError:
                            backup_retained_at_parent_sync = False
                        else:
                            backup_retained_at_parent_sync = True
                original_fsync(descriptor)

            with (
                patch(
                    "toc.semantic_review.os.rename",
                    side_effect=capture_backup_namespaces,
                ),
                patch(
                    "toc.semantic_review.os.fsync",
                    side_effect=fail_publication_fsync,
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "write became unsafe",
                ):
                    safe_semantic_write_text(
                        run_dir,
                        destination,
                        "new artifact\n",
                    )

            self.assertTrue(publication_fsync_failed)
            self.assertIsNotNone(parent_identity)
            self.assertIsNotNone(cleanup_identity)
            self.assertIn(parent_identity, rollback_sync_identities)
            self.assertIn(cleanup_identity, rollback_sync_identities)
            self.assertLess(
                rollback_sync_identities.index(parent_identity),
                rollback_sync_identities.index(cleanup_identity),
            )
            self.assertTrue(backup_retained_at_parent_sync)
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "previous artifact\n",
            )
            self.assertEqual(
                [
                    path.name
                    for path in destination.parent.iterdir()
                    if path.name.startswith(".semantic-")
                    and not path.is_dir()
                ],
                [],
            )

    def test_safe_write_cleanup_failure_after_commit_returns_success(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            run_dir = Path(td) / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("previous artifact\n", encoding="utf-8")
            original_fsync = os.fsync
            original_rename = os.rename
            parent_identity: tuple[int, int] | None = None
            publication_synced = False
            cleanup_failure_injected = False
            injected_after_publication = False

            def capture_parent(
                source,
                target,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
            ):
                nonlocal parent_identity, cleanup_failure_injected
                nonlocal injected_after_publication
                if (
                    str(source).startswith(".semantic-write-")
                    and str(target).startswith("backup-")
                ):
                    opened = os.fstat(src_dir_fd)
                    parent_identity = opened.st_dev, opened.st_ino
                if (
                    not cleanup_failure_injected
                    and publication_synced
                    and str(source).startswith(".semantic-write-")
                    and str(target).startswith("entry-")
                ):
                    cleanup_failure_injected = True
                    injected_after_publication = publication_synced
                    raise OSError("injected committed cleanup failure")
                return original_rename(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            def record_publication_fsync(descriptor: int) -> None:
                nonlocal publication_synced
                original_fsync(descriptor)
                opened = os.fstat(descriptor)
                if parent_identity == (opened.st_dev, opened.st_ino):
                    publication_synced = True

            with (
                patch(
                    "toc.semantic_review.os.rename",
                    side_effect=capture_parent,
                ),
                patch(
                    "toc.semantic_review.os.fsync",
                    side_effect=record_publication_fsync,
                ),
            ):
                result = safe_semantic_write_text(
                    run_dir,
                    destination,
                    "new artifact\n",
                )

            self.assertTrue(result.samefile(destination))
            self.assertTrue(cleanup_failure_injected)
            self.assertTrue(injected_after_publication)
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "new artifact\n",
            )

    def test_safe_write_cleanup_fsync_failure_after_commit_returns_success(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            run_dir = Path(td) / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("previous artifact\n", encoding="utf-8")
            original_fsync = os.fsync
            original_rename = os.rename
            parent_identity: tuple[int, int] | None = None
            parent_fsyncs = 0
            cleanup_fsync_failure_injected = False

            def capture_parent(
                source,
                target,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
            ):
                nonlocal parent_identity
                if (
                    str(source).startswith(".semantic-write-")
                    and str(target).startswith("backup-")
                ):
                    opened = os.fstat(src_dir_fd)
                    parent_identity = opened.st_dev, opened.st_ino
                return original_rename(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            def fail_cleanup_fsync(descriptor: int) -> None:
                nonlocal parent_fsyncs, cleanup_fsync_failure_injected
                opened = os.fstat(descriptor)
                identity = opened.st_dev, opened.st_ino
                if identity == parent_identity:
                    parent_fsyncs += 1
                    if parent_fsyncs == 2:
                        cleanup_fsync_failure_injected = True
                        raise OSError("injected committed namespace cleanup failure")
                original_fsync(descriptor)

            with (
                patch(
                    "toc.semantic_review.os.rename",
                    side_effect=capture_parent,
                ),
                patch(
                    "toc.semantic_review.os.fsync",
                    side_effect=fail_cleanup_fsync,
                ),
            ):
                result = safe_semantic_write_text(
                    run_dir,
                    destination,
                    "new artifact\n",
                )

            self.assertTrue(result.samefile(destination))
            self.assertTrue(cleanup_fsync_failure_injected)
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "new artifact\n",
            )

    def test_safe_write_reports_indeterminate_rollback_durability(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            run_dir = Path(td) / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("previous artifact\n", encoding="utf-8")
            original_fsync = os.fsync
            original_rename = os.rename
            parent_identity: tuple[int, int] | None = None
            cleanup_identity: tuple[int, int] | None = None
            publication_fsync_failed = False
            rollback_cleanup_fsync_failed = False
            rollback_parent_fsync_attempted = False
            rollback_sync_events: list[str] = []

            def capture_backup_namespaces(
                source,
                target,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
            ):
                nonlocal parent_identity, cleanup_identity
                if (
                    str(source).startswith(".semantic-write-")
                    and str(target).startswith("backup-")
                ):
                    parent_stat = os.fstat(src_dir_fd)
                    cleanup_stat = os.fstat(dst_dir_fd)
                    parent_identity = parent_stat.st_dev, parent_stat.st_ino
                    cleanup_identity = cleanup_stat.st_dev, cleanup_stat.st_ino
                return original_rename(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            def fail_publication_and_cleanup_fsync(descriptor: int) -> None:
                nonlocal publication_fsync_failed
                nonlocal rollback_cleanup_fsync_failed
                nonlocal rollback_parent_fsync_attempted
                opened = os.fstat(descriptor)
                identity = opened.st_dev, opened.st_ino
                if identity == parent_identity:
                    if not publication_fsync_failed:
                        publication_fsync_failed = True
                        raise OSError("injected publication fsync failure")
                    rollback_parent_fsync_attempted = True
                    rollback_sync_events.append("parent")
                if (
                    publication_fsync_failed
                    and not rollback_cleanup_fsync_failed
                    and identity == cleanup_identity
                ):
                    rollback_cleanup_fsync_failed = True
                    rollback_sync_events.append("cleanup")
                    raise OSError("injected rollback cleanup fsync failure")
                original_fsync(descriptor)

            with (
                patch(
                    "toc.semantic_review.os.rename",
                    side_effect=capture_backup_namespaces,
                ),
                patch(
                    "toc.semantic_review.os.fsync",
                    side_effect=fail_publication_and_cleanup_fsync,
                ),
            ):
                with self.assertRaisesRegex(
                    SemanticWriteIndeterminateError,
                    "rollback durability is indeterminate",
                ):
                    safe_semantic_write_text(
                        run_dir,
                        destination,
                        "new artifact\n",
                    )

            self.assertTrue(publication_fsync_failed)
            self.assertTrue(rollback_cleanup_fsync_failed)
            self.assertTrue(rollback_parent_fsync_attempted)
            self.assertEqual(rollback_sync_events, ["parent", "cleanup"])
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "previous artifact\n",
            )

    def test_safe_write_restores_backup_when_post_rename_inspection_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            run_dir = Path(td) / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("previous artifact\n", encoding="utf-8")
            from toc import semantic_review

            original_named_stat = semantic_review._semantic_named_stat
            failure_injected = False

            def fail_first_backup_inspection(parent_fd: int, name: str):
                nonlocal failure_injected
                if not failure_injected and name.startswith("backup-"):
                    failure_injected = True
                    raise OSError("injected post-rename inspection failure")
                return original_named_stat(parent_fd, name)

            with patch(
                "toc.semantic_review._semantic_named_stat",
                side_effect=fail_first_backup_inspection,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "write became unsafe",
                ):
                    safe_semantic_write_text(
                        run_dir,
                        destination,
                        "new artifact\n",
                    )

            self.assertTrue(failure_injected)
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "previous artifact\n",
            )

    def test_safe_write_reconciles_publication_link_that_raises_after_linking(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            run_dir = Path(td) / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            from toc import semantic_review

            original_link_without_clobber = (
                semantic_review._semantic_link_without_clobber
            )
            failure_injected = False

            def link_then_fail(
                parent_fd: int,
                source_name: str,
                destination_name: str,
            ) -> None:
                nonlocal failure_injected
                original_link_without_clobber(
                    parent_fd,
                    source_name,
                    destination_name,
                )
                failure_injected = True
                raise OSError("injected post-link failure")

            with patch(
                "toc.semantic_review._semantic_link_without_clobber",
                side_effect=link_then_fail,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "write became unsafe",
                ):
                    safe_semantic_write_text(
                        run_dir,
                        destination,
                        "new artifact\n",
                    )

            self.assertTrue(failure_injected)
            self.assertFalse(destination.exists())

    def test_safe_write_close_failure_after_commit_does_not_report_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            run_dir = Path(td) / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("previous artifact\n", encoding="utf-8")
            original_close = os.close
            original_fsync = os.fsync
            original_rename = os.rename
            parent_identity: tuple[int, int] | None = None
            publication_synced = False
            close_failure_injected = False
            close_attempts = 0
            failed_descriptor: int | None = None

            def capture_parent(
                source,
                target,
                *,
                src_dir_fd=None,
                dst_dir_fd=None,
            ):
                nonlocal parent_identity
                if (
                    str(source).startswith(".semantic-write-")
                    and str(target).startswith("backup-")
                ):
                    opened = os.fstat(src_dir_fd)
                    parent_identity = opened.st_dev, opened.st_ino
                return original_rename(
                    source,
                    target,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                )

            def record_publication_fsync(descriptor: int) -> None:
                nonlocal publication_synced
                original_fsync(descriptor)
                opened = os.fstat(descriptor)
                if parent_identity == (opened.st_dev, opened.st_ino):
                    publication_synced = True

            def fail_first_committed_close(descriptor: int) -> None:
                nonlocal close_attempts, close_failure_injected
                nonlocal failed_descriptor
                close_attempts += 1
                if publication_synced and not close_failure_injected:
                    close_failure_injected = True
                    failed_descriptor = descriptor
                    raise OSError("injected committed close failure")
                original_close(descriptor)

            try:
                with (
                    patch(
                        "toc.semantic_review.os.rename",
                        side_effect=capture_parent,
                    ),
                    patch(
                        "toc.semantic_review.os.fsync",
                        side_effect=record_publication_fsync,
                    ),
                    patch(
                        "toc.semantic_review.os.close",
                        side_effect=fail_first_committed_close,
                    ),
                ):
                    result = safe_semantic_write_text(
                        run_dir,
                        destination,
                        "new artifact\n",
                    )
            finally:
                if failed_descriptor is not None:
                    try:
                        original_close(failed_descriptor)
                    except OSError:
                        pass

            self.assertTrue(result.samefile(destination))
            self.assertTrue(close_failure_injected)
            self.assertGreater(close_attempts, 1)
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "new artifact\n",
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
            original_rename = os.rename
            original_link = os.link
            from toc import semantic_review

            original_exchange = semantic_review.atomic_exchange_names
            raced = False

            def reuse_destination_before_exchange(
                source_dir_fd: int,
                source_name: str,
                destination_dir_fd: int,
                destination_name: str,
            ):
                nonlocal raced
                if not raced and destination_name == destination.name:
                    raced = True
                    original_rename(
                        destination_name,
                        preserved_original.name,
                        src_dir_fd=destination_dir_fd,
                        dst_dir_fd=destination_dir_fd,
                    )
                    original_link(
                        unrelated,
                        destination_name,
                        dst_dir_fd=destination_dir_fd,
                        follow_symlinks=False,
                    )
                return original_exchange(
                    source_dir_fd,
                    source_name,
                    destination_dir_fd,
                    destination_name,
                )

            with patch(
                "toc.semantic_review.atomic_exchange_names",
                side_effect=reuse_destination_before_exchange,
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

    def test_safe_overwrite_never_exposes_missing_canonical_name(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            run_dir = Path(td) / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("old artifact\n", encoding="utf-8")
            from toc import semantic_review

            original_exchange = semantic_review.atomic_exchange_names
            observed: list[bytes] = []

            def observe_before_exchange(
                source_dir_fd: int,
                source_name: str,
                destination_dir_fd: int,
                destination_name: str,
            ) -> None:
                descriptor = os.open(
                    destination_name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=destination_dir_fd,
                )
                try:
                    observed.append(os.read(descriptor, 1024))
                finally:
                    os.close(descriptor)
                original_exchange(
                    source_dir_fd,
                    source_name,
                    destination_dir_fd,
                    destination_name,
                )

            with patch(
                "toc.semantic_review.atomic_exchange_names",
                side_effect=observe_before_exchange,
            ):
                safe_semantic_write_text(
                    run_dir,
                    destination,
                    "new artifact\n",
                )

            self.assertEqual(observed, [b"old artifact\n"])
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "new artifact\n",
            )

    def test_failed_overwrite_rollback_never_exposes_missing_canonical_name(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            run_dir = Path(td) / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("old artifact\n", encoding="utf-8")
            from toc import semantic_review

            original_exchange = semantic_review.atomic_exchange_names
            exchange_count = 0
            observed: list[bytes] = []

            def read_canonical(parent_fd: int) -> bytes:
                descriptor = os.open(
                    destination.name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=parent_fd,
                )
                try:
                    return os.read(descriptor, 1024)
                finally:
                    os.close(descriptor)

            def observe_each_exchange(
                source_dir_fd: int,
                source_name: str,
                destination_dir_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal exchange_count
                exchange_count += 1
                canonical_parent_fd = (
                    destination_dir_fd if exchange_count == 1 else source_dir_fd
                )
                observed.append(read_canonical(canonical_parent_fd))
                original_exchange(
                    source_dir_fd,
                    source_name,
                    destination_dir_fd,
                    destination_name,
                )
                observed.append(read_canonical(canonical_parent_fd))

            with (
                patch(
                    "toc.semantic_review.atomic_exchange_names",
                    side_effect=observe_each_exchange,
                ),
                patch(
                    "toc.semantic_review._semantic_link_without_clobber",
                    side_effect=OSError("injected post-exchange failure"),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "write became unsafe"):
                    safe_semantic_write_text(
                        run_dir,
                        destination,
                        "new artifact\n",
                    )

            self.assertEqual(exchange_count, 2)
            self.assertEqual(
                observed,
                [
                    b"old artifact\n",
                    b"new artifact\n",
                    b"new artifact\n",
                    b"old artifact\n",
                ],
            )
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "old artifact\n",
            )

    def test_failed_atomic_rollback_leaves_a_canonical_version_visible(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            run_dir = Path(td) / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("old artifact\n", encoding="utf-8")
            from toc import semantic_review

            original_exchange = semantic_review.atomic_exchange_names
            exchange_count = 0
            observed: list[bytes] = []

            def exchange_then_refuse_rollback(
                source_dir_fd: int,
                source_name: str,
                destination_dir_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal exchange_count
                exchange_count += 1
                if exchange_count == 1:
                    original_exchange(
                        source_dir_fd,
                        source_name,
                        destination_dir_fd,
                        destination_name,
                    )
                    return
                descriptor = os.open(
                    destination.name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=source_dir_fd,
                )
                try:
                    observed.append(os.read(descriptor, 1024))
                finally:
                    os.close(descriptor)
                raise OSError("injected atomic rollback failure")

            with (
                patch(
                    "toc.semantic_review.atomic_exchange_names",
                    side_effect=exchange_then_refuse_rollback,
                ),
                patch(
                    "toc.semantic_review._semantic_link_without_clobber",
                    side_effect=OSError("injected post-exchange failure"),
                ),
            ):
                with self.assertRaisesRegex(
                    SemanticWriteIndeterminateError,
                    "rollback durability is indeterminate",
                ):
                    safe_semantic_write_text(
                        run_dir,
                        destination,
                        "new artifact\n",
                    )

            self.assertEqual(exchange_count, 2)
            self.assertEqual(observed, [b"new artifact\n"])
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "new artifact\n",
            )

    def test_safe_overwrite_fails_closed_without_atomic_exchange(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="semantic_write_security_"
        ) as td:
            run_dir = Path(td) / "run"
            destination = run_dir / "logs" / "review.md"
            destination.parent.mkdir(parents=True)
            destination.write_text("old artifact\n", encoding="utf-8")

            with patch(
                "toc.semantic_review.atomic_exchange_names",
                side_effect=OSError("atomic exchange unavailable"),
            ):
                with self.assertRaisesRegex(ValueError, "write became unsafe"):
                    safe_semantic_write_text(
                        run_dir,
                        destination,
                        "new artifact\n",
                    )

            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                "old artifact\n",
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
            original_rename = os.rename
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
                    swapped = True
                    original_rename(
                        os.fspath(semantic_dir),
                        os.fspath(detached_semantic_dir),
                    )
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
                return original_rename(
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
                "toc.semantic_review.os.rename",
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
