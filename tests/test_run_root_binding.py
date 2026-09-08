from __future__ import annotations

import asyncio
import contextvars
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from server import image_gen_app
from toc.harness import append_state_snapshot, parse_state_file, write_json
from toc.image_request_snapshot import (
    load_request_snapshot,
    materialize_request_snapshot,
)
from toc.run_root_binding import (
    RunRootBindingError,
    RunFilePostAppendError,
    append_run_file_text,
    append_run_file_bytes_inplace,
    bind_run_root,
    current_run_root_binding,
    list_run_directory_entry_names,
    read_run_file_bytes,
    run_file_entry_exists,
    run_file_append_transaction,
    require_bound_run_root,
    unlink_run_file,
    write_run_file_text,
)


class RunRootBindingTests(unittest.TestCase):
    def test_cleanup_root_failure_overrides_a_projection_primary_error(self) -> None:
        from toc import run_root_binding

        primary = RunFilePostAppendError("projection failed")

        with self.assertRaisesRegex(RunRootBindingError, "root changed"):
            run_root_binding._run_cleanup_actions(
                primary,
                [
                    (
                        "verifying run root",
                        lambda: (_ for _ in ()).throw(
                            RunRootBindingError("root changed")
                        ),
                    )
                ],
            )

    def test_relative_run_root_helpers_do_not_repeat_the_run_path(self) -> None:
        workspace = Path.cwd()
        with tempfile.TemporaryDirectory(
            prefix="relative_run_root_",
            dir=workspace,
        ) as tmp:
            run_dir = Path(tmp).relative_to(workspace)

            write_run_file_text(run_dir, "state.txt", "status=created\n")
            append_run_file_text(run_dir, "state.txt", "status=ready\n")
            write_run_file_text(
                run_dir,
                run_dir / "logs" / "grounding" / "research.json",
                '{"status":"grounded"}\n',
            )
            append_run_file_text(
                run_dir,
                run_dir / "state.txt",
                "status=grounded\n",
            )

            self.assertEqual(
                read_run_file_bytes(run_dir, "state.txt"),
                b"status=created\nstatus=ready\nstatus=grounded\n",
            )
            self.assertEqual(
                read_run_file_bytes(
                    run_dir,
                    run_dir / "logs" / "grounding" / "research.json",
                ),
                b'{"status":"grounded"}\n',
            )
            self.assertTrue((run_dir / "state.txt").is_file())
            self.assertFalse((run_dir / run_dir / "state.txt").exists())
            self.assertFalse((run_dir / run_dir / "logs").exists())

    def test_bound_file_helpers_use_pinned_root_during_swap_restore(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            original_slot = parent / "original"
            replacement_slot = parent / "replacement"
            run_dir.mkdir()
            (run_dir / "logs").mkdir()
            (run_dir / "logs" / "events.jsonl").write_text(
                "trusted\n",
                encoding="utf-8",
            )
            (run_dir / "logs" / "receipt.json").write_text(
                "trusted receipt\n",
                encoding="utf-8",
            )
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            real_write = os.write
            append_swapped = False

            def swap_for_append(fd: int, data: bytes) -> int:
                nonlocal append_swapped
                if not append_swapped:
                    append_swapped = True
                    run_dir.rename(original_slot)
                    run_dir.mkdir()
                    (run_dir / "logs").mkdir()
                    (run_dir / "logs" / "events.jsonl").write_text(
                        "replacement\n",
                        encoding="utf-8",
                    )
                    try:
                        return real_write(fd, data)
                    finally:
                        run_dir.rename(replacement_slot)
                        original_slot.rename(run_dir)
                return real_write(fd, data)

            with bind_run_root(run_dir, expected_identity=identity):
                with patch(
                    "toc.run_root_binding.os.write",
                    side_effect=swap_for_append,
                ):
                    append_run_file_text(
                        run_dir,
                        Path("logs/events.jsonl"),
                        "appended\n",
                    )

            self.assertTrue(append_swapped)
            self.assertEqual(
                (run_dir / "logs" / "events.jsonl").read_text(
                    encoding="utf-8"
                ),
                "trusted\nappended\n",
            )
            self.assertEqual(
                (
                    replacement_slot / "logs" / "events.jsonl"
                ).read_text(encoding="utf-8"),
                "replacement\n",
            )

            replacement_slot.rename(parent / "first_replacement")
            receipt = run_dir / "logs" / "receipt.json"
            from toc.atomic_exchange import atomic_exchange_names as real_exchange

            unlink_swapped = False

            def swap_for_unlink(
                source_fd: int,
                source_name: str,
                destination_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal unlink_swapped
                if (
                    not unlink_swapped
                    and source_name == "receipt.json"
                ):
                    unlink_swapped = True
                    run_dir.rename(original_slot)
                    run_dir.mkdir()
                    (run_dir / "logs").mkdir()
                    (run_dir / "logs" / "receipt.json").write_text(
                        "replacement receipt\n",
                        encoding="utf-8",
                    )
                    try:
                        real_exchange(
                            source_fd,
                            source_name,
                            destination_fd,
                            destination_name,
                        )
                    finally:
                        run_dir.rename(replacement_slot)
                        original_slot.rename(run_dir)
                    return
                real_exchange(
                    source_fd,
                    source_name,
                    destination_fd,
                    destination_name,
                )

            with bind_run_root(run_dir, expected_identity=identity):
                with patch(
                    "toc.run_root_binding.atomic_exchange_names",
                    side_effect=swap_for_unlink,
                ):
                    self.assertTrue(
                        unlink_run_file(
                            run_dir,
                            Path("logs/receipt.json"),
                        )
                    )

            self.assertTrue(unlink_swapped)
            self.assertFalse(receipt.exists())
            self.assertEqual(
                (
                    replacement_slot / "logs" / "receipt.json"
                ).read_text(encoding="utf-8"),
                "replacement receipt\n",
            )

    def test_bound_debug_writer_publishes_only_to_pinned_root_during_swap_restore(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            original_slot = parent / "original"
            replacement_slot = parent / "replacement"
            run_dir.mkdir()
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            real_path_write_text = Path.write_text
            real_link = os.link
            attacked = False

            def perform_swap(
                relative: Path,
                publish: object,
            ) -> object:
                nonlocal attacked
                attacked = True
                run_dir.rename(original_slot)
                run_dir.mkdir()
                replacement_target = run_dir / relative
                replacement_target.parent.mkdir(parents=True)
                real_path_write_text(
                    replacement_target,
                    "replacement\n",
                    encoding="utf-8",
                )
                try:
                    return publish()  # type: ignore[operator]
                finally:
                    run_dir.rename(replacement_slot)
                    original_slot.rename(run_dir)

            def swapping_path_write_text(
                path: Path,
                data: str,
                *args: object,
                **kwargs: object,
            ) -> int:
                if (
                    not attacked
                    and path.suffix == ".json"
                    and "app_server" in path.parts
                ):
                    relative = path.relative_to(run_dir)
                    return perform_swap(
                        relative,
                        lambda: real_path_write_text(
                            path,
                            data,
                            *args,
                            **kwargs,
                        ),
                    )  # type: ignore[return-value]
                return real_path_write_text(path, data, *args, **kwargs)

            def swapping_link(
                source: str | bytes,
                destination: str | bytes,
                *args: object,
                **kwargs: object,
            ) -> None:
                if not attacked and kwargs.get("dst_dir_fd") is not None:
                    relative = (
                        Path("logs/app_server/binding_test")
                        / os.fsdecode(destination)
                    )
                    perform_swap(
                        relative,
                        lambda: real_link(
                            source,
                            destination,
                            *args,
                            **kwargs,
                        ),
                    )
                    return
                real_link(source, destination, *args, **kwargs)

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch.object(
                        Path,
                        "write_text",
                        autospec=True,
                        side_effect=swapping_path_write_text,
                    ),
                    patch(
                        "toc.run_root_binding.os.link",
                        side_effect=swapping_link,
                    ),
                ):
                    result = image_gen_app.write_app_server_debug_log(
                        run_dir=run_dir,
                        operation="binding_test",
                        status="trusted",
                    )

            self.assertTrue(attacked)
            relative = result.relative_to(run_dir)
            self.assertEqual(
                json.loads(result.read_text(encoding="utf-8"))["status"],
                "trusted",
            )
            self.assertEqual(
                (replacement_slot / relative).read_text(encoding="utf-8"),
                "replacement\n",
            )

    def test_bound_media_read_uses_retained_descriptor_during_swap_restore(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            original_slot = parent / "original"
            replacement_slot = parent / "replacement"
            (run_dir / "logs").mkdir(parents=True)
            (run_dir / "logs" / "truth.json").write_text(
                "trusted",
                encoding="utf-8",
            )
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            real_require = require_bound_run_root
            real_open = os.open
            attacked = False
            inside_require = False
            restored = False

            def swapping_require(path: Path):
                nonlocal attacked, inside_require
                inside_require = True
                try:
                    binding = real_require(path)
                finally:
                    inside_require = False
                if binding is not None and not attacked:
                    attacked = True
                    run_dir.rename(original_slot)
                    (run_dir / "logs").mkdir(parents=True)
                    (run_dir / "logs" / "truth.json").write_text(
                        "replacement",
                        encoding="utf-8",
                    )
                return binding

            def swapping_open(
                path: str | bytes | os.PathLike[str],
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal attacked, restored
                path_value = os.fspath(path)
                if (
                    not inside_require
                    and not attacked
                    and os.path.abspath(os.fsdecode(path_value))
                    == os.path.abspath(os.fspath(run_dir))
                ):
                    attacked = True
                    run_dir.rename(original_slot)
                    (run_dir / "logs").mkdir(parents=True)
                    (run_dir / "logs" / "truth.json").write_text(
                        "replacement",
                        encoding="utf-8",
                    )
                    try:
                        return real_open(path, flags, *args, **kwargs)
                    finally:
                        run_dir.rename(replacement_slot)
                        original_slot.rename(run_dir)
                if (
                    attacked
                    and not restored
                    and os.fsdecode(path_value) == "logs"
                ):
                    descriptor = real_open(path, flags, *args, **kwargs)
                    run_dir.rename(replacement_slot)
                    original_slot.rename(run_dir)
                    restored = True
                    return descriptor
                return real_open(path, flags, *args, **kwargs)

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch(
                        "toc.run_root_binding.require_bound_run_root",
                        side_effect=swapping_require,
                    ),
                    patch(
                        "toc.run_root_binding.os.open",
                        side_effect=swapping_open,
                    ),
                ):
                    content = read_run_file_bytes(
                        run_dir,
                        "logs/truth.json",
                    )

            self.assertTrue(attacked)
            self.assertEqual(content, b"trusted")
            self.assertEqual(
                (
                    replacement_slot / "logs" / "truth.json"
                ).read_text(encoding="utf-8"),
                "replacement",
            )

    def test_bound_media_destination_presence_ignores_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            original_slot = parent / "original"
            replacement_slot = parent / "replacement"
            (run_dir / "images").mkdir(parents=True)
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            real_require = require_bound_run_root
            real_open = os.open
            attacked = False
            inside_require = False
            restored = False

            def install_replacement() -> None:
                run_dir.rename(original_slot)
                (run_dir / "images").mkdir(parents=True)
                (run_dir / "images" / "blocked.png").write_bytes(
                    b"replacement"
                )

            def restore_original() -> None:
                run_dir.rename(replacement_slot)
                original_slot.rename(run_dir)

            def swapping_require(path: Path):
                nonlocal attacked, inside_require
                inside_require = True
                try:
                    binding = real_require(path)
                finally:
                    inside_require = False
                if binding is not None and not attacked:
                    attacked = True
                    install_replacement()
                return binding

            def swapping_open(
                path: str | bytes | os.PathLike[str],
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal attacked, restored
                path_value = os.fsdecode(os.fspath(path))
                if (
                    not inside_require
                    and not attacked
                    and kwargs.get("dir_fd") is None
                    and Path(path_value).name == run_dir.name
                ):
                    attacked = True
                    install_replacement()
                    try:
                        return real_open(path, flags, *args, **kwargs)
                    finally:
                        restore_original()
                if attacked and not restored and path_value == "images":
                    descriptor = real_open(path, flags, *args, **kwargs)
                    restore_original()
                    restored = True
                    return descriptor
                return real_open(path, flags, *args, **kwargs)

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch(
                        "toc.run_root_binding.require_bound_run_root",
                        side_effect=swapping_require,
                    ),
                    patch(
                        "toc.run_root_binding.os.open",
                        side_effect=swapping_open,
                    ),
                ):
                    exists = run_file_entry_exists(
                        run_dir,
                        "images/blocked.png",
                    )

            self.assertTrue(attacked)
            self.assertFalse(exists)
            self.assertTrue(
                replacement_slot.joinpath(
                    "images/blocked.png"
                ).is_file()
            )

    def test_bound_directory_listing_uses_retained_nested_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            original_logs = parent / "original-logs"
            replacement_logs = parent / "replacement-logs"
            image_logs = run_dir / "logs" / "app_server" / "image_gen"
            image_logs.mkdir(parents=True)
            (image_logs / "trusted.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            real_listdir = os.listdir
            attacked = False

            def swap_during_listdir(path):
                nonlocal attacked
                entries = real_listdir(path)
                if not attacked:
                    attacked = True
                    (run_dir / "logs").rename(original_logs)
                    replacement = (
                        run_dir / "logs" / "app_server" / "image_gen"
                    )
                    replacement.mkdir(parents=True)
                    (replacement / "replacement.json").write_text(
                        "{}\n",
                        encoding="utf-8",
                    )
                return entries

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch(
                        "toc.run_root_binding.os.listdir",
                        side_effect=swap_during_listdir,
                    ),
                    self.assertRaises(RunRootBindingError),
                ):
                    list_run_directory_entry_names(
                        run_dir,
                        "logs/app_server/image_gen",
                    )

            self.assertTrue(attacked)
            (run_dir / "logs").rename(replacement_logs)
            original_logs.rename(run_dir / "logs")
            self.assertEqual(
                list_run_directory_entry_names(
                    run_dir,
                    "logs/app_server/image_gen",
                ),
                ("trusted.json",),
            )

    def test_bound_media_read_rejects_nested_directory_swap_restore(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            original_logs = parent / "original-logs"
            replacement_logs = parent / "replacement-logs"
            (run_dir / "logs").mkdir(parents=True)
            (run_dir / "logs" / "truth.json").write_text(
                "trusted",
                encoding="utf-8",
            )
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            real_open = os.open
            real_stat = os.stat
            replacement_installed = False
            restored = False

            def swapping_open(
                path: str | bytes | os.PathLike[str],
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal replacement_installed
                if (
                    not replacement_installed
                    and os.fsdecode(os.fspath(path)) == "logs"
                    and kwargs.get("dir_fd") is not None
                ):
                    replacement_installed = True
                    (run_dir / "logs").rename(original_logs)
                    (run_dir / "logs").mkdir()
                    (run_dir / "logs" / "truth.json").write_text(
                        "replacement",
                        encoding="utf-8",
                    )
                return real_open(path, flags, *args, **kwargs)

            def restoring_stat(
                path: str | bytes | os.PathLike[str],
                *args: object,
                **kwargs: object,
            ):
                nonlocal restored
                metadata = real_stat(path, *args, **kwargs)
                if (
                    replacement_installed
                    and not restored
                    and os.fsdecode(os.fspath(path)) == "logs"
                    and kwargs.get("dir_fd") is not None
                ):
                    restored = True
                    (run_dir / "logs").rename(replacement_logs)
                    original_logs.rename(run_dir / "logs")
                return metadata

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch(
                        "toc.run_root_binding.os.open",
                        side_effect=swapping_open,
                    ),
                    patch(
                        "toc.run_root_binding.os.stat",
                        side_effect=restoring_stat,
                    ),
                    self.assertRaises(
                        RunRootBindingError
                    ),
                ):
                    read_run_file_bytes(
                        run_dir,
                        "logs/truth.json",
                    )

            self.assertTrue(replacement_installed)
            self.assertTrue(restored)
            self.assertEqual(
                (run_dir / "logs" / "truth.json").read_text(
                    encoding="utf-8"
                ),
                "trusted",
            )
            self.assertEqual(
                (replacement_logs / "truth.json").read_text(
                    encoding="utf-8"
                ),
                "replacement",
            )

    def test_stable_scene_snapshot_does_not_select_swap_restore_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            original_slot = parent / "original"
            replacement_slot = parent / "replacement"
            run_dir.mkdir()
            replacement_slot.mkdir()

            def snapshot_for(base: Path, prompt: str):
                return materialize_request_snapshot(
                    base,
                    kind="scene",
                    items=[
                        {
                            "id": "scene1_cut01",
                            "output": "images/scene1_cut01.png",
                            "prompt": prompt,
                            "prompt_policy_version": "test-v1",
                            "compiler_version": "test-v1",
                            "source_digest": "a" * 64,
                            "references": [],
                        }
                    ],
                    created_at="2026-08-01T00:00:00+09:00",
                )

            trusted = snapshot_for(run_dir, "trusted prompt")
            replacement = snapshot_for(
                replacement_slot,
                "replacement prompt",
            )
            snapshot_path = (
                run_dir / "image_generation_request_snapshot.json"
            )
            snapshot_path.write_text(
                json.dumps(trusted.to_dict()),
                encoding="utf-8",
            )
            (
                replacement_slot
                / "image_generation_request_snapshot.json"
            ).write_text(
                json.dumps(replacement.to_dict()),
                encoding="utf-8",
            )
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            from toc import image_request_snapshot as snapshot_module

            real_reader = snapshot_module.read_regular_file_nofollow
            swapped = False

            def swapping_reader(root: Path, relative: str | Path, **kwargs: object) -> bytes:
                nonlocal swapped
                if Path(relative) == Path("image_generation_request_snapshot.json"):
                    trusted_bytes = real_reader(root, relative, **kwargs)
                    run_dir.rename(original_slot)
                    replacement_slot.rename(run_dir)
                    swapped = True
                    try:
                        return trusted_bytes
                    finally:
                        run_dir.rename(replacement_slot)
                        original_slot.rename(run_dir)
                return real_reader(root, relative, **kwargs)

            with bind_run_root(run_dir, expected_identity=identity):
                with patch.object(snapshot_module, "read_regular_file_nofollow", side_effect=swapping_reader):
                    loaded = load_request_snapshot(
                        snapshot_path,
                        run_dir=run_dir,
                        verify_references=False,
                    )

            self.assertTrue(swapped)
            self.assertEqual(loaded.request_revision, trusted.request_revision)
            self.assertNotEqual(
                loaded.request_revision,
                replacement.request_revision,
            )

    def test_bound_state_append_rejects_hardlinked_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            run_dir.mkdir()
            outside = parent / "outside.txt"
            outside.write_text(
                "runtime.stage=outside\n---\n",
                encoding="utf-8",
            )
            os.link(outside, run_dir / "state.txt")
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            with bind_run_root(run_dir, expected_identity=identity):
                with self.assertRaises(ValueError):
                    append_state_snapshot(
                        run_dir / "state.txt",
                        {"runtime.stage": "must_not_append"},
                    )

            self.assertEqual(
                outside.read_text(encoding="utf-8"),
                "runtime.stage=outside\n---\n",
            )

    def test_bound_state_parse_uses_serialized_run_file_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            (run_dir / "state.txt").write_text(
                "runtime.stage=reviewing\n---\n",
                encoding="utf-8",
            )
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            with bind_run_root(run_dir, expected_identity=identity):
                with patch(
                    "toc.harness.read_regular_file_nofollow",
                    side_effect=AssertionError(
                        "bound state reads must share append serialization"
                    ),
                ):
                    state = parse_state_file(run_dir / "state.txt")

            self.assertEqual(state["runtime.stage"], "reviewing")

    def test_state_parse_waits_for_cow_append_publication(self) -> None:
        from toc import run_root_binding

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            (run_dir / "state.txt").write_text(
                "runtime.stage=prepared\n---\n",
                encoding="utf-8",
            )

            exchange_ready = threading.Event()
            release_exchange = threading.Event()
            reader_waiting = threading.Event()
            writer_errors: list[BaseException] = []
            reader_errors: list[BaseException] = []
            reader_states: list[dict[str, str]] = []
            real_exchange = run_root_binding._exchange_names_reconciled
            real_flock = fcntl.flock

            def pause_before_publication(*args, **kwargs):
                exchange_ready.set()
                if not release_exchange.wait(timeout=5):
                    raise TimeoutError("test did not release COW publication")
                return real_exchange(*args, **kwargs)

            def observe_reader_lock(descriptor: int, operation: int):
                if (
                    threading.current_thread().name == "state-reader"
                    and operation in {fcntl.LOCK_SH, fcntl.LOCK_EX}
                ):
                    reader_waiting.set()
                return real_flock(descriptor, operation)

            def write_state() -> None:
                try:
                    append_run_file_text(
                        run_dir,
                        "state.txt",
                        "runtime.stage=reviewing\n---\n",
                    )
                except BaseException as exc:
                    writer_errors.append(exc)

            def read_state() -> None:
                try:
                    reader_states.append(parse_state_file(run_dir / "state.txt"))
                except BaseException as exc:
                    reader_errors.append(exc)

            with (
                patch.object(
                    run_root_binding,
                    "_exchange_names_reconciled",
                    side_effect=pause_before_publication,
                ),
                patch.object(
                    run_root_binding.fcntl,
                    "flock",
                    side_effect=observe_reader_lock,
                ),
            ):
                writer = threading.Thread(target=write_state, name="state-writer")
                writer.start()
                self.assertTrue(exchange_ready.wait(timeout=5))

                reader = threading.Thread(target=read_state, name="state-reader")
                reader.start()
                self.assertTrue(reader_waiting.wait(timeout=5))

                release_exchange.set()
                writer.join(timeout=5)
                reader.join(timeout=5)

            self.assertFalse(writer.is_alive())
            self.assertFalse(reader.is_alive())
            self.assertEqual(writer_errors, [])
            self.assertEqual(reader_errors, [])
            self.assertEqual(reader_states[0]["runtime.stage"], "reviewing")

    def test_inplace_append_preserves_inode_and_writes_only_new_record(self) -> None:
        from toc import run_root_binding

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"legacy=1\n---\n")
            before = state_path.stat()
            record = b"# toc.state.delta.v1 {}\nvalue=2\n---\n"
            writes: list[bytes] = []
            real_write_all = run_root_binding._write_all

            def observe_write(descriptor: int, data: bytes) -> None:
                writes.append(bytes(data))
                return real_write_all(descriptor, data)

            identity = run_dir.stat()
            with bind_run_root(
                run_dir,
                expected_identity=(identity.st_dev, identity.st_ino),
            ):
                with (
                    patch.object(
                        run_root_binding,
                        "_write_all",
                        side_effect=observe_write,
                    ),
                    patch.object(
                        run_root_binding,
                        "atomic_exchange_names",
                        side_effect=AssertionError(
                            "in-place append must not publish a COW replacement"
                        ),
                    ),
                ):
                    result = append_run_file_bytes_inplace(
                        run_dir,
                        "state.txt",
                        record,
                        expected_head_size=before.st_size,
                    )

            after = state_path.stat()
            self.assertEqual(result, state_path)
            self.assertEqual(
                (after.st_dev, after.st_ino),
                (before.st_dev, before.st_ino),
            )
            self.assertEqual(state_path.read_bytes(), b"legacy=1\n---\n" + record)
            self.assertEqual(writes, [record])

    def test_inplace_append_rejects_stale_expected_head_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"head\n---\n")
            before = state_path.read_bytes()

            with self.assertRaises(RunRootBindingError):
                append_run_file_bytes_inplace(
                    run_dir,
                    "state.txt",
                    b"must-not-append\n---\n",
                    expected_head_size=len(before) - 1,
                )

            self.assertEqual(state_path.read_bytes(), before)

    def test_inplace_append_full_write_loop_preserves_one_record(self) -> None:
        from toc import run_root_binding

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"head\n---\n")
            record = b"event=short-writes\n---\n"
            calls: list[bytes] = []
            real_write = os.write

            def short_write(descriptor: int, data: bytes | memoryview) -> int:
                remaining = bytes(data)
                calls.append(remaining)
                return real_write(descriptor, remaining[:1])

            with patch.object(
                run_root_binding.os,
                "write",
                side_effect=short_write,
            ):
                append_run_file_bytes_inplace(run_dir, "state.txt", record)

            self.assertGreater(len(calls), 1)
            self.assertEqual(
                state_path.read_bytes(),
                b"head\n---\n" + record,
            )
            self.assertEqual(state_path.read_bytes().count(record), 1)

    def test_inplace_append_serializes_concurrent_writers_without_lost_records(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"seed=1\n---\n")
            writer_count = 16
            barrier = threading.Barrier(writer_count)
            errors: list[BaseException] = []

            def write_record(index: int) -> None:
                try:
                    barrier.wait(timeout=5)
                    append_run_file_bytes_inplace(
                        run_dir,
                        "state.txt",
                        f"event-{index}=committed\n---\n".encode(),
                    )
                except BaseException as exc:
                    errors.append(exc)

            writers = [
                threading.Thread(
                    target=write_record,
                    args=(index,),
                    name=f"delta-writer-{index}",
                )
                for index in range(writer_count)
            ]
            for writer in writers:
                writer.start()
            for writer in writers:
                writer.join(timeout=10)

            self.assertTrue(all(not writer.is_alive() for writer in writers))
            self.assertEqual(errors, [])
            data = state_path.read_bytes()
            self.assertTrue(data.startswith(b"seed=1\n---\n"))
            for index in range(writer_count):
                record = f"event-{index}=committed\n---\n".encode()
                self.assertEqual(data.count(record), 1)

    def test_inplace_append_rejects_symlink_fifo_and_hardlink_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            outside = parent / "outside.txt"
            outside.write_bytes(b"outside\n")

            symlink_run = parent / "symlink-run"
            symlink_run.mkdir()
            (symlink_run / "state.txt").symlink_to(outside)
            with self.assertRaises(RunRootBindingError):
                append_run_file_bytes_inplace(
                    symlink_run,
                    "state.txt",
                    b"must-not-follow\n",
                )

            fifo_run = parent / "fifo-run"
            fifo_run.mkdir()
            os.mkfifo(fifo_run / "state.txt")
            with self.assertRaises(RunRootBindingError):
                append_run_file_bytes_inplace(
                    fifo_run,
                    "state.txt",
                    b"must-not-open\n",
                )

            hardlink_run = parent / "hardlink-run"
            hardlink_run.mkdir()
            os.link(outside, hardlink_run / "state.txt")
            with self.assertRaises(RunRootBindingError):
                append_run_file_bytes_inplace(
                    hardlink_run,
                    "state.txt",
                    b"must-not-touch\n",
                )

            self.assertEqual(outside.read_bytes(), b"outside\n")

    def test_inplace_append_rejects_symlink_fifo_and_hardlink_locks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            outside = parent / "outside-lock.txt"
            outside.write_bytes(b"lock\n")

            for label in ("symlink", "fifo", "hardlink"):
                run_dir = parent / f"{label}-run"
                run_dir.mkdir()
                state_path = run_dir / "state.txt"
                state_path.write_bytes(b"head\n---\n")
                lock_path = run_dir / ".state.txt.append.lock"
                if label == "symlink":
                    lock_path.symlink_to(outside)
                elif label == "fifo":
                    os.mkfifo(lock_path)
                else:
                    os.link(outside, lock_path)

                with self.subTest(lock_kind=label):
                    with self.assertRaises(RunRootBindingError):
                        append_run_file_bytes_inplace(
                            run_dir,
                            "state.txt",
                            b"must-not-append\n---\n",
                        )
                    self.assertEqual(state_path.read_bytes(), b"head\n---\n")

            self.assertEqual(outside.read_bytes(), b"lock\n")

    def test_append_transaction_reads_and_appends_under_one_exclusive_lock(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"head=1\n---\n")
            callback_entered = threading.Event()
            release_callback = threading.Event()
            competing_done = threading.Event()
            errors: list[BaseException] = []

            def merge(descriptor: int, current_size: int) -> bytes:
                current = os.pread(descriptor, current_size, 0)
                self.assertEqual(current, b"head=1\n---\n")
                self.assertEqual(current_size, len(current))
                callback_entered.set()
                if not release_callback.wait(timeout=5):
                    raise TimeoutError("test did not release append callback")
                return b"callback=2\n---\n"

            def competing_writer() -> None:
                try:
                    append_run_file_bytes_inplace(
                        run_dir,
                        "state.txt",
                        b"competing=3\n---\n",
                    )
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    competing_done.set()

            callback_thread = threading.Thread(
                target=lambda: run_file_append_transaction(
                    run_dir,
                    "state.txt",
                    merge,
                ),
                name="callback-writer",
            )
            callback_thread.start()
            self.assertTrue(callback_entered.wait(timeout=5))

            competing_thread = threading.Thread(
                target=competing_writer,
                name="competing-writer",
            )
            competing_thread.start()
            self.assertFalse(competing_done.wait(timeout=0.2))
            release_callback.set()

            callback_thread.join(timeout=10)
            competing_thread.join(timeout=10)
            self.assertFalse(callback_thread.is_alive())
            self.assertFalse(competing_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(
                state_path.read_bytes(),
                b"head=1\n---\ncallback=2\n---\ncompeting=3\n---\n",
            )

    def test_append_transaction_keeps_writer_locked_through_post_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"head=1\n---\n")
            post_entered = threading.Event()
            release_post = threading.Event()
            competing_done = threading.Event()
            errors: list[BaseException] = []

            def post_append(_descriptor: int, new_size: int) -> None:
                self.assertEqual(new_size, state_path.stat().st_size)
                post_entered.set()
                if not release_post.wait(timeout=5):
                    raise TimeoutError("test did not release post-append hook")

            def primary() -> None:
                try:
                    run_file_append_transaction(
                        run_dir,
                        "state.txt",
                        lambda _descriptor, _size: b"primary=2\n---\n",
                        post_append=post_append,
                    )
                except BaseException as exc:
                    errors.append(exc)

            def competing() -> None:
                try:
                    append_run_file_bytes_inplace(
                        run_dir,
                        "state.txt",
                        b"competing=3\n---\n",
                    )
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    competing_done.set()

            primary_thread = threading.Thread(target=primary)
            primary_thread.start()
            self.assertTrue(post_entered.wait(timeout=5))
            competing_thread = threading.Thread(target=competing)
            competing_thread.start()
            self.assertFalse(competing_done.wait(timeout=0.2))
            release_post.set()
            primary_thread.join(timeout=10)
            competing_thread.join(timeout=10)

            self.assertEqual(errors, [])
            self.assertEqual(
                state_path.read_bytes(),
                b"head=1\n---\nprimary=2\n---\ncompeting=3\n---\n",
            )

    def test_append_transaction_does_not_downgrade_root_binding_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"initial\n")

            def fail_root_binding(_descriptor: int, _size: int) -> None:
                raise RunRootBindingError("root changed")

            with self.assertRaisesRegex(RunRootBindingError, "root changed"):
                run_file_append_transaction(
                    run_dir,
                    "state.txt",
                    lambda _descriptor, _size: b"committed\n",
                    post_append=fail_root_binding,
                )

            self.assertEqual(state_path.read_bytes(), b"initial\ncommitted\n")

    def test_append_transaction_does_not_eagerly_read_history(self) -> None:
        from toc import run_root_binding

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            history = b"legacy=value\n---\n" * 128
            state_path.write_bytes(history)
            observed: list[tuple[int, int]] = []

            def append_without_read(descriptor: int, current_size: int) -> bytes:
                observed.append((descriptor, current_size))
                return b"delta=only\n---\n"

            with patch.object(
                run_root_binding.os,
                "pread",
                side_effect=AssertionError(
                    "append callback must choose its own read range"
                ),
            ):
                run_file_append_transaction(
                    run_dir,
                    "state.txt",
                    append_without_read,
                )

            self.assertEqual(observed[0][1], len(history))
            self.assertEqual(
                state_path.read_bytes(),
                history + b"delta=only\n---\n",
            )

    def test_bound_append_rolls_back_a_late_hardlink_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_text("trusted\n", encoding="utf-8")
            preserved = run_dir / "state.before-attack"
            outside = parent / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            from toc.atomic_exchange import (
                atomic_exchange_names as real_exchange,
            )

            attacked = False

            def substitute_then_exchange(
                source_fd: int,
                source_name: str,
                destination_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal attacked
                if not attacked and destination_name == "state.txt":
                    attacked = True
                    state_path.rename(preserved)
                    os.link(outside, state_path)
                real_exchange(
                    source_fd,
                    source_name,
                    destination_fd,
                    destination_name,
                )

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch(
                        "toc.run_root_binding.atomic_exchange_names",
                        side_effect=substitute_then_exchange,
                    ),
                    self.assertRaises(RunRootBindingError),
                ):
                    append_run_file_text(
                        run_dir,
                        "state.txt",
                        "must-not-reach-outside\n",
                    )

            self.assertTrue(attacked)
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")
            self.assertEqual(state_path.read_text(encoding="utf-8"), "outside\n")
            self.assertEqual(preserved.read_text(encoding="utf-8"), "trusted\n")

    def test_bound_append_opens_fifo_nonblocking_and_rejects_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            os.mkfifo(run_dir / "state.txt")
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            real_open = os.open
            saw_nonblocking_fifo_open = False

            def inspect_open(path, flags, *args, **kwargs):
                nonlocal saw_nonblocking_fifo_open
                if os.fsdecode(os.fspath(path)) == "state.txt":
                    saw_nonblocking_fifo_open = bool(
                        flags & getattr(os, "O_NONBLOCK", 0)
                    )
                return real_open(path, flags, *args, **kwargs)

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch(
                        "toc.run_root_binding.os.open",
                        side_effect=inspect_open,
                    ),
                    self.assertRaises(RunRootBindingError),
                ):
                    append_run_file_text(run_dir, "state.txt", "blocked\n")

            self.assertTrue(saw_nonblocking_fifo_open)

    def test_unbound_harness_rejects_hardlink_symlink_and_fifo_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            outside = parent / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")

            hardlink_run = parent / "hardlink-run"
            hardlink_run.mkdir()
            os.link(outside, hardlink_run / "state.txt")
            with self.assertRaises(RunRootBindingError):
                append_state_snapshot(
                    hardlink_run / "state.txt",
                    {"runtime.stage": "must-not-append"},
                )

            symlink_run = parent / "symlink-run"
            symlink_run.mkdir()
            (symlink_run / "state.txt").symlink_to(outside)
            with self.assertRaises((OSError, RunRootBindingError)):
                append_state_snapshot(
                    symlink_run / "state.txt",
                    {"runtime.stage": "must-not-append"},
                )

            fifo_run = parent / "fifo-run"
            fifo_run.mkdir()
            os.mkfifo(fifo_run / "state.txt")
            with self.assertRaises(RunRootBindingError):
                append_state_snapshot(
                    fifo_run / "state.txt",
                    {"runtime.stage": "must-not-append"},
                )

            self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")

    def test_bound_write_rolls_back_late_leaf_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            run_dir.mkdir()
            target = run_dir / "report.json"
            target.write_text("trusted\n", encoding="utf-8")
            preserved = run_dir / "report.before-attack"
            outside = parent / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            from toc.atomic_exchange import (
                atomic_exchange_names as real_exchange,
            )

            attacked = False

            def substitute_then_exchange(
                source_fd: int,
                source_name: str,
                destination_fd: int,
                destination_name: str,
            ) -> None:
                nonlocal attacked
                if not attacked and destination_name == "report.json":
                    attacked = True
                    target.rename(preserved)
                    os.link(outside, target)
                real_exchange(
                    source_fd,
                    source_name,
                    destination_fd,
                    destination_name,
                )

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch(
                        "toc.run_root_binding.atomic_exchange_names",
                        side_effect=substitute_then_exchange,
                    ),
                    self.assertRaises(RunRootBindingError),
                ):
                    write_run_file_text(run_dir, "report.json", "new\n")

            self.assertTrue(attacked)
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")
            self.assertEqual(target.read_text(encoding="utf-8"), "outside\n")
            self.assertEqual(preserved.read_text(encoding="utf-8"), "trusted\n")

    def test_bound_write_absent_publication_never_clobbers_racing_leaf(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            target = run_dir / "new.json"
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            real_link = os.link
            attacked = False

            def install_before_link(source, destination, *args, **kwargs):
                nonlocal attacked
                if not attacked and os.fsdecode(destination) == "new.json":
                    attacked = True
                    target.write_text("racing\n", encoding="utf-8")
                return real_link(source, destination, *args, **kwargs)

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch(
                        "toc.run_root_binding.os.link",
                        side_effect=install_before_link,
                    ),
                    self.assertRaises(RunRootBindingError),
                ):
                    write_run_file_text(run_dir, "new.json", "new\n")

            self.assertTrue(attacked)
            self.assertEqual(target.read_text(encoding="utf-8"), "racing\n")

    def test_primary_write_error_is_not_masked_by_integrity_cleanup(self) -> None:
        class PrimaryWriteError(OSError):
            pass

        class CleanupIntegrityError(RunRootBindingError):
            pass

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch(
                        "toc.run_root_binding._write_all",
                        side_effect=PrimaryWriteError("primary write failed"),
                    ),
                    patch(
                        "toc.run_root_binding._verify_bound_parent_ancestry",
                        side_effect=CleanupIntegrityError(
                            "cleanup verification failed"
                        ),
                    ),
                    self.assertRaises(PrimaryWriteError) as raised,
                ):
                    append_run_file_text(run_dir, "state.txt", "new\n")

            notes = getattr(raised.exception, "__notes__", [])
            self.assertTrue(
                any("cleanup verification failed" in note for note in notes),
                notes,
            )

    def test_bound_harness_write_rejects_path_outside_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            outside = parent / "outside.json"
            run_dir.mkdir()
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            with bind_run_root(run_dir, expected_identity=identity):
                with self.assertRaises(RunRootBindingError):
                    write_json(outside, {"must": "not publish"})

            self.assertFalse(outside.exists())

    def test_app_server_guard_keeps_captured_binding_without_ambient_context(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            captured: dict[str, object] = {}

            def fake_factory(**kwargs):
                captured.update(kwargs)
                return object()

            with bind_run_root(run_dir, expected_identity=identity):
                with patch.object(
                    image_gen_app,
                    "_create_codex_app_server_client_unbound",
                    side_effect=fake_factory,
                ):
                    image_gen_app.create_codex_app_server_client(cwd=run_dir)
                guard = captured["submission_guard"]
                self.assertTrue(callable(guard))
                contextvars.Context().run(guard)  # type: ignore[arg-type]

            with self.assertRaises(RunRootBindingError):
                contextvars.Context().run(guard)  # type: ignore[arg-type]

    def test_app_server_guard_cannot_revive_after_descriptor_number_reuse(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            captured: dict[str, object] = {}

            def fake_factory(**kwargs):
                captured.update(kwargs)
                return object()

            with bind_run_root(run_dir, expected_identity=identity) as binding:
                descriptor_number = binding.descriptor
                with patch.object(
                    image_gen_app,
                    "_create_codex_app_server_client_unbound",
                    side_effect=fake_factory,
                ):
                    image_gen_app.create_codex_app_server_client(cwd=run_dir)
                guard = captured["submission_guard"]
                self.assertTrue(callable(guard))

            reopened = os.open(
                run_dir,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            installed_reuse = reopened != descriptor_number
            try:
                if installed_reuse:
                    os.dup2(reopened, descriptor_number)
                with self.assertRaises(RunRootBindingError):
                    contextvars.Context().run(guard)  # type: ignore[arg-type]
            finally:
                os.close(reopened)
                if installed_reuse:
                    os.close(descriptor_number)

    def test_nested_same_root_binding_reuses_outer_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            second_descriptor = os.open(
                run_dir,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                with bind_run_root(
                    run_dir,
                    expected_identity=identity,
                ) as outer:
                    with bind_run_root(
                        run_dir,
                        expected_identity=identity,
                        descriptor=second_descriptor,
                    ) as inner:
                        self.assertIs(inner, outer)
                        self.assertNotEqual(inner.descriptor, second_descriptor)
                    self.assertIs(current_run_root_binding(), outer)
            finally:
                os.close(second_descriptor)

        self.assertIsNone(current_run_root_binding())

    def test_bound_state_io_never_reads_or_writes_replacement_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            original = parent / "original"
            replacement = parent / "replacement"
            run_dir.mkdir()
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            with bind_run_root(
                run_dir,
                expected_identity=identity,
            ):
                append_state_snapshot(
                    run_dir / "state.txt",
                    {"runtime.stage": "trusted"},
                )
                run_dir.rename(original)
                run_dir.mkdir()
                (run_dir / "state.txt").write_text(
                    "runtime.stage=replacement\n---\n",
                    encoding="utf-8",
                )
                try:
                    with self.assertRaises(RunRootBindingError):
                        append_state_snapshot(
                            run_dir / "state.txt",
                            {"runtime.stage": "must_not_write"},
                        )
                finally:
                    run_dir.rename(replacement)
                    original.rename(run_dir)

            self.assertEqual(
                parse_state_file(replacement / "state.txt")[
                    "runtime.stage"
                ],
                "replacement",
            )
            self.assertEqual(
                parse_state_file(run_dir / "state.txt")["runtime.stage"],
                "trusted",
            )

    def test_bound_subprocess_enters_inherited_root_without_preexec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            run_dir.mkdir()
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            with bind_run_root(
                run_dir,
                expected_identity=identity,
            ):
                completed = image_gen_app._run_bound_subprocess(
                    run_dir,
                    [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            "Path('child.txt').write_text('pinned', "
                            "encoding='utf-8')"
                        ),
                    ],
                    cwd=parent,
                    capture_output=True,
                    text=True,
                    check=False,
                )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                (run_dir / "child.txt").read_text(encoding="utf-8"),
                "pinned",
            )

    def test_binding_propagates_into_async_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            async def inspect() -> tuple[int, int]:
                await asyncio.sleep(0)
                binding = require_bound_run_root(run_dir)
                self.assertIsNotNone(binding)
                return binding.identity

            with bind_run_root(
                run_dir,
                expected_identity=identity,
            ):
                self.assertEqual(asyncio.run(inspect()), identity)

            self.assertIsNone(current_run_root_binding())

    def test_binding_rejects_replacement_and_final_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            original = parent / "original"
            replacement = parent / "replacement"
            outside = parent / "outside"
            run_dir.mkdir()
            outside.mkdir()
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino

            with bind_run_root(
                run_dir,
                expected_identity=identity,
            ):
                run_dir.rename(original)
                run_dir.mkdir()
                try:
                    with self.assertRaises(RunRootBindingError):
                        require_bound_run_root(run_dir)
                finally:
                    run_dir.rename(replacement)
                    original.rename(run_dir)

            run_dir.rename(original)
            run_dir.symlink_to(outside, target_is_directory=True)
            try:
                with self.assertRaises(RunRootBindingError):
                    with bind_run_root(
                        run_dir,
                        expected_identity=identity,
                    ):
                        self.fail("a final symlink must not bind")
            finally:
                run_dir.unlink()
                original.rename(run_dir)


if __name__ == "__main__":
    unittest.main()
