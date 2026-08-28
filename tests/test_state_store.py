from __future__ import annotations

import unittest
import tempfile
import threading
import json
import hashlib
from pathlib import Path
from unittest.mock import patch

from toc.run_root_binding import RunRootBindingError
from toc.state_store import (
    NoStateChange,
    StateLogIntegrityError,
    StateViewError,
    append_state_delta,
    read_current_state,
    resolve_idempotent_event,
    parse_current_view,
    replay_state_bytes,
    serialize_current_view,
    serialize_delta_event,
)


class StateStoreContractTests(unittest.TestCase):
    def test_legacy_replay_checks_aggregate_json_size_once_not_per_assignment(self) -> None:
        from toc import state_store

        data = b"".join(
            f"status=P{index}\nshared=value-{index}\n---\n".encode("utf-8")
            for index in range(200)
        )
        with patch(
            "toc.state_store._canonical_json",
            wraps=state_store._canonical_json,
        ) as canonical_json:
            replay = replay_state_bytes(data)

        self.assertEqual(replay.state["status"], "P199")
        self.assertLessEqual(canonical_json.call_count, 2)

    def test_harness_rejects_a_broken_state_symlink(self) -> None:
        from toc.harness import parse_state_file

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.symlink_to(run_dir / "missing-state.txt")

            with self.assertRaises(RunRootBindingError):
                parse_state_file(state_path)

    def test_replays_legacy_partial_blocks_with_global_last_write_wins(self) -> None:
        replay = replay_state_bytes(
            b"job_id=JOB_1\nstatus=INIT\nshared=old\n---\n"
            b"status=P410\nscene.status=reviewing\n---\n"
            b"shared=new\n---\n"
        )

        self.assertEqual(
            replay.state,
            {
                "job_id": "JOB_1",
                "status": "P410",
                "shared": "new",
                "scene.status": "reviewing",
            },
        )
        self.assertEqual(replay.head.sequence, 0)
        self.assertFalse(replay.incomplete_tail)

    def test_accepts_one_delimiterless_legacy_mapping_for_compatibility(self) -> None:
        replay = replay_state_bytes(b"topic=legacy\nstatus=SCRIPT\n")

        self.assertEqual(replay.state["topic"], "legacy")
        self.assertEqual(replay.state["status"], "SCRIPT")
        self.assertFalse(replay.incomplete_tail)
        self.assertEqual(replay.head.committed_bytes, len(b"topic=legacy\nstatus=SCRIPT\n"))

    def test_first_delta_normalizes_a_delimiterless_legacy_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            legacy = b"topic=legacy\nstatus=SCRIPT\n"
            state_path.write_bytes(legacy)

            committed = append_state_delta(
                state_path,
                {"status": "P500"},
                event_id="event-normalize",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )

            self.assertTrue(state_path.read_bytes().startswith(legacy + b"---\n"))
            replayed = replay_state_bytes(state_path.read_bytes())
            self.assertEqual(replayed.state["topic"], "legacy")
            self.assertEqual(replayed.state["status"], "P500")
            self.assertEqual(replayed.head, committed.head)

    def test_first_delta_accepts_a_crlf_legacy_delimiter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            legacy = b"topic=legacy\r\nstatus=SCRIPT\r\n---\r\n"
            state_path.write_bytes(legacy)

            committed = append_state_delta(
                state_path,
                {"status": "P500"},
                event_id="event-crlf",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )

            replayed = replay_state_bytes(state_path.read_bytes())
            self.assertEqual(replayed.state["topic"], "legacy")
            self.assertEqual(replayed.state["status"], "P500")
            self.assertEqual(replayed.head, committed.head)

    def test_first_delta_normalizes_legacy_file_without_final_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"status=P410")

            append_state_delta(
                state_path,
                {"status": "P500"},
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )

            replayed = replay_state_bytes(state_path.read_bytes())
            self.assertEqual(replayed.state["status"], "P500")
            self.assertEqual(replayed.head.sequence, 1)

    def test_delta_serialization_contains_only_changed_keys(self) -> None:
        legacy = replay_state_bytes(
            b"job_id=JOB_1\nstatus=P410\nunchanged=value\n---\n"
        )

        encoded, commit = serialize_delta_event(
            current_state=legacy.state,
            head=legacy.head,
            updates={
                "status": "P500",
                "unchanged": "value",
                "slot.p510.status": "done",
            },
            event_id="event-1",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )

        text = encoded.decode("utf-8")
        self.assertIn("status=P500\n", text)
        self.assertIn("slot.p510.status=done\n", text)
        self.assertNotIn("job_id=JOB_1\n", text)
        self.assertNotIn("unchanged=value\n", text)
        self.assertEqual(commit.changed_keys, ("slot.p510.status", "status"))

        replay = replay_state_bytes(
            b"job_id=JOB_1\nstatus=P410\nunchanged=value\n---\n" + encoded
        )
        self.assertEqual(replay.state["job_id"], "JOB_1")
        self.assertEqual(replay.state["status"], "P500")
        self.assertEqual(replay.state["unchanged"], "value")
        self.assertEqual(replay.state["slot.p510.status"], "done")
        self.assertEqual(replay.head.sequence, 1)

    def test_delta_only_replay_is_global_last_write_wins(self) -> None:
        empty = replay_state_bytes(b"")
        first, _ = serialize_delta_event(
            current_state=empty.state,
            head=empty.head,
            updates={"status": "P410", "shared": "first"},
            event_id="event-1",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )
        current = replay_state_bytes(first)
        second, _ = serialize_delta_event(
            current_state=current.state,
            head=current.head,
            updates={"status": "P500", "shared": "second"},
            event_id="event-2",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:02+09:00",
            committed_at="2026-08-21T00:00:03+09:00",
        )

        replay = replay_state_bytes(first + second)
        self.assertEqual(replay.state["status"], "P500")
        self.assertEqual(replay.state["shared"], "second")
        self.assertEqual(replay.head.sequence, 2)

    def test_empty_string_is_an_explicit_assignment(self) -> None:
        legacy = replay_state_bytes(b"last_error=old\n---\n")
        encoded, _ = serialize_delta_event(
            current_state=legacy.state,
            head=legacy.head,
            updates={"last_error": ""},
            event_id="event-clear",
            event_type="state.invalidated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )

        replay = replay_state_bytes(b"last_error=old\n---\n" + encoded)
        self.assertIn("last_error=\n", encoded.decode("utf-8"))
        self.assertEqual(replay.state["last_error"], "")

    def test_incomplete_tail_is_not_applied(self) -> None:
        replay = replay_state_bytes(
            b"status=P410\n---\nstatus=P500\nslot.p510.status=done\n"
        )

        self.assertEqual(replay.state["status"], "P410")
        self.assertNotIn("slot.p510.status", replay.state)
        self.assertTrue(replay.incomplete_tail)

    def test_detects_tampered_delta_payload(self) -> None:
        legacy_bytes = b"status=P410\n---\n"
        legacy = replay_state_bytes(legacy_bytes)
        encoded, _ = serialize_delta_event(
            current_state=legacy.state,
            head=legacy.head,
            updates={"status": "P500"},
            event_id="event-tamper",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )

        with self.assertRaisesRegex(StateLogIntegrityError, "event hash"):
            replay_state_bytes(legacy_bytes + encoded.replace(b"status=P500", b"status=P600"))

    def test_rejects_sequence_or_previous_head_mismatch(self) -> None:
        legacy_bytes = b"status=P410\n---\n"
        legacy = replay_state_bytes(legacy_bytes)
        encoded, _ = serialize_delta_event(
            current_state=legacy.state,
            head=legacy.head,
            updates={"status": "P500"},
            event_id="event-head",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )

        with self.assertRaisesRegex(StateLogIntegrityError, "sequence"):
            replay_state_bytes(legacy_bytes + encoded.replace(b'"seq":1', b'"seq":2'))
        with self.assertRaisesRegex(StateLogIntegrityError, "previous hash"):
            replay_state_bytes(
                legacy_bytes
                + encoded.replace(
                    legacy.head.event_hash.encode("ascii"),
                    ("sha256:" + "0" * 64).encode("ascii"),
                )
            )

    def test_rejects_legacy_block_after_delta_mode_begins(self) -> None:
        legacy_bytes = b"status=P410\n---\n"
        legacy = replay_state_bytes(legacy_bytes)
        encoded, _ = serialize_delta_event(
            current_state=legacy.state,
            head=legacy.head,
            updates={"status": "P500"},
            event_id="event-1",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )

        with self.assertRaisesRegex(StateLogIntegrityError, "legacy block"):
            replay_state_bytes(legacy_bytes + encoded + b"status=P600\n---\n")

    def test_current_view_round_trips_only_as_a_head_bound_cache(self) -> None:
        replay = replay_state_bytes(b"job_id=JOB_1\nstatus=P410\n---\n")
        encoded = serialize_current_view(
            replay=replay,
            run_root_identity=(123, 456),
            log_identity=(123, 789, replay.head.committed_bytes, 1, 1),
            generated_at="2026-08-21T00:00:00+09:00",
        )

        state = parse_current_view(
            encoded,
            expected_run_root_identity=(123, 456),
            expected_head=replay.head,
        )
        self.assertEqual(state, replay.state)

    def test_current_view_rejects_a_stale_log_cursor(self) -> None:
        first = replay_state_bytes(b"status=P410\n---\n")
        encoded = serialize_current_view(
            replay=first,
            run_root_identity=(123, 456),
            log_identity=(123, 789, first.head.committed_bytes, 1, 1),
            generated_at="2026-08-21T00:00:00+09:00",
        )
        delta, _ = serialize_delta_event(
            current_state=first.state,
            head=first.head,
            updates={"status": "P500"},
            event_id="event-next",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:01+09:00",
            committed_at="2026-08-21T00:00:02+09:00",
        )
        current = replay_state_bytes(b"status=P410\n---\n" + delta)

        with self.assertRaisesRegex(StateViewError, "cursor"):
            parse_current_view(
                encoded,
                expected_run_root_identity=(123, 456),
                expected_head=current.head,
            )

    def test_current_view_rejects_a_different_run_root(self) -> None:
        replay = replay_state_bytes(b"status=P410\n---\n")
        encoded = serialize_current_view(
            replay=replay,
            run_root_identity=(123, 456),
            log_identity=(123, 789, replay.head.committed_bytes, 1, 1),
            generated_at="2026-08-21T00:00:00+09:00",
        )

        with self.assertRaisesRegex(StateViewError, "run root"):
            parse_current_view(
                encoded,
                expected_run_root_identity=(999, 456),
                expected_head=replay.head,
            )

    def test_unicode_line_separator_cannot_inject_a_second_key(self) -> None:
        legacy = replay_state_bytes(b"status=P410\n---\n")
        encoded, _ = serialize_delta_event(
            current_state=legacy.state,
            head=legacy.head,
            updates={"note": "safe\u2028slot.p900.status=done"},
            event_id="event-safe-note",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )

        replay = replay_state_bytes(b"status=P410\n---\n" + encoded)
        self.assertEqual(replay.state["note"], "safe slot.p900.status=done")
        self.assertNotIn("slot.p900.status", replay.state)

    def test_rejects_comment_or_control_character_state_keys(self) -> None:
        legacy = replay_state_bytes(b"status=P410\n---\n")
        for bad_key in ("#hidden", "a\vb", "a=b", ""):
            with self.subTest(bad_key=bad_key):
                with self.assertRaisesRegex(ValueError, "invalid state key"):
                    serialize_delta_event(
                        current_state=legacy.state,
                        head=legacy.head,
                        updates={bad_key: "value"},
                        event_id="event-invalid-key",
                        event_type="state.updated",
                        occurred_at="2026-08-21T00:00:00+09:00",
                        committed_at="2026-08-21T00:00:01+09:00",
                    )

    def test_rejects_metadata_line_separators_before_serialization(self) -> None:
        legacy = replay_state_bytes(b"status=P410\n---\n")
        with self.assertRaisesRegex(ValueError, "event_id is invalid"):
            serialize_delta_event(
                current_state=legacy.state,
                head=legacy.head,
                updates={"status": "P500"},
                event_id="event-safe\u2028injected",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )

    def test_no_effective_update_does_not_emit_a_timestamp_only_event(self) -> None:
        legacy = replay_state_bytes(b"status=P410\n---\n")
        for updates in ({}, {"status": "P410"}):
            with self.subTest(updates=updates):
                with self.assertRaises(NoStateChange):
                    serialize_delta_event(
                        current_state=legacy.state,
                        head=legacy.head,
                        updates=updates,
                        event_id="event-noop",
                        event_type="state.updated",
                        occurred_at="2026-08-21T00:00:00+09:00",
                        committed_at="2026-08-21T00:00:01+09:00",
                    )

    def test_serializer_rejects_a_frame_larger_than_replay_accepts(self) -> None:
        legacy = replay_state_bytes(b"status=P410\n---\n")
        with (
            patch("toc.state_store.MAX_BLOCK_BYTES", 128),
            self.assertRaisesRegex(ValueError, "size limit"),
        ):
            serialize_delta_event(
                current_state=legacy.state,
                head=legacy.head,
                updates={"status": "P500"},
                event_id="event-oversized-frame",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )

    def test_rejects_empty_block_after_delta_mode_begins(self) -> None:
        legacy_bytes = b"status=P410\n---\n"
        legacy = replay_state_bytes(legacy_bytes)
        encoded, _ = serialize_delta_event(
            current_state=legacy.state,
            head=legacy.head,
            updates={"status": "P500"},
            event_id="event-1",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )

        with self.assertRaisesRegex(StateLogIntegrityError, "empty block"):
            replay_state_bytes(legacy_bytes + encoded + b"---\n")

    def test_rejects_noncanonical_or_malformed_delta_payload(self) -> None:
        legacy_bytes = b"status=P410\n---\n"
        legacy = replay_state_bytes(legacy_bytes)
        encoded, _ = serialize_delta_event(
            current_state=legacy.state,
            head=legacy.head,
            updates={"status": "P500"},
            event_id="event-1",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )
        malformed = encoded.replace(b"status=P500\n", b"not-an-assignment\n")

        with self.assertRaises(StateLogIntegrityError):
            replay_state_bytes(legacy_bytes + malformed)

    def test_rejects_boolean_sequence_even_with_recomputed_hash(self) -> None:
        legacy_bytes = b"status=P410\n---\n"
        legacy = replay_state_bytes(legacy_bytes)
        encoded, _ = serialize_delta_event(
            current_state=legacy.state,
            head=legacy.head,
            updates={"status": "P500"},
            event_id="event-1",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )
        malformed = encoded.replace(b'"seq":1', b'"seq":true')

        with self.assertRaises(StateLogIntegrityError):
            replay_state_bytes(legacy_bytes + malformed)

    def test_current_view_rejects_invalid_state_keys_and_generated_at(self) -> None:
        replay = replay_state_bytes(b"status=P410\n---\n")
        encoded = serialize_current_view(
            replay=replay,
            run_root_identity=(123, 456),
            log_identity=(123, 789, replay.head.committed_bytes, 1, 1),
            generated_at="2026-08-21T00:00:00+09:00",
        )
        bad_generated_at = encoded.replace(
            b'"generated_at": "2026-08-21T00:00:00+09:00"',
            b'"generated_at": 1',
        )
        with self.assertRaises(StateViewError):
            parse_current_view(
                bad_generated_at,
                expected_run_root_identity=(123, 456),
                expected_head=replay.head,
            )

    def test_same_event_id_and_request_resolves_to_existing_commit(self) -> None:
        legacy_bytes = b"status=P410\n---\n"
        legacy = replay_state_bytes(legacy_bytes)
        encoded, commit = serialize_delta_event(
            current_state=legacy.state,
            head=legacy.head,
            updates={"status": "P500"},
            event_id="event-retry",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )
        replay = replay_state_bytes(legacy_bytes + encoded)

        existing = resolve_idempotent_event(
            replay,
            event_id="event-retry",
            event_type="state.updated",
            updates={"status": "P500"},
        )
        self.assertEqual(existing.event_hash, commit.event_hash)

    def test_same_event_id_with_different_request_is_rejected(self) -> None:
        legacy_bytes = b"status=P410\n---\n"
        legacy = replay_state_bytes(legacy_bytes)
        encoded, _ = serialize_delta_event(
            current_state=legacy.state,
            head=legacy.head,
            updates={"status": "P500"},
            event_id="event-retry",
            event_type="state.updated",
            occurred_at="2026-08-21T00:00:00+09:00",
            committed_at="2026-08-21T00:00:01+09:00",
        )
        replay = replay_state_bytes(legacy_bytes + encoded)

        with self.assertRaisesRegex(StateLogIntegrityError, "conflicting retry"):
            resolve_idempotent_event(
                replay,
                event_id="event-retry",
                event_type="state.updated",
                updates={"status": "P600"},
            )

    def test_first_delta_materializes_a_current_view_without_rewriting_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            legacy = b"job_id=JOB_1\nstatus=P410\nunchanged=value\n---\n"
            state_path.write_bytes(legacy)

            replay = append_state_delta(
                state_path,
                {"status": "P500", "unchanged": "value"},
                event_id="event-first-delta",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )

            committed = state_path.read_bytes()
            self.assertTrue(committed.startswith(legacy))
            self.assertEqual(committed.count(b"unchanged=value\n"), 1)
            self.assertEqual(replay.state["status"], "P500")
            self.assertTrue((run_dir / "state.current.json").is_file())
            self.assertEqual(read_current_state(state_path).state, replay.state)

    def test_warm_append_uses_current_view_instead_of_full_log_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"status=P410\n---\n")
            append_state_delta(
                state_path,
                {"status": "P500"},
                event_id="event-1",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )
            append_state_delta(
                state_path,
                {"slot.p510.status": "done"},
                event_id="event-2",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:02+09:00",
                committed_at="2026-08-21T00:00:03+09:00",
            )

            with patch(
                "toc.state_store._replay_state_descriptor",
                side_effect=AssertionError("warm append replayed full history"),
            ):
                replay = append_state_delta(
                    state_path,
                    {"slot.p520.status": "done"},
                    event_type="state.updated",
                    occurred_at="2026-08-21T00:00:04+09:00",
                    committed_at="2026-08-21T00:00:05+09:00",
                )

            self.assertEqual(replay.state["status"], "P500")
            self.assertEqual(replay.state["slot.p510.status"], "done")
            self.assertEqual(replay.state["slot.p520.status"], "done")

    def test_legacy_only_view_is_warm_after_one_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"status=P410\n---\n")
            self.assertEqual(read_current_state(state_path).state["status"], "P410")

            with patch(
                "toc.state_store._replay_state_descriptor",
                side_effect=AssertionError("legacy current view replayed full history"),
            ):
                replay = read_current_state(state_path)

            self.assertEqual(replay.state["status"], "P410")

    def test_concurrent_deltas_preserve_both_updates_and_latest_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"status=P410\n---\n")
            barrier = threading.Barrier(2)
            errors: list[BaseException] = []

            def update(name: str) -> None:
                try:
                    barrier.wait(timeout=5)
                    append_state_delta(
                        state_path,
                        {f"concurrent.{name}": "done"},
                        event_id=f"event-{name}",
                        event_type="state.updated",
                        occurred_at="2026-08-21T00:00:00+09:00",
                        committed_at="2026-08-21T00:00:01+09:00",
                    )
                except BaseException as exc:
                    errors.append(exc)

            workers = [
                threading.Thread(target=update, args=(name,))
                for name in ("a", "b")
            ]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=10)

            self.assertEqual(errors, [])
            replay = read_current_state(state_path)
            self.assertEqual(replay.state["concurrent.a"], "done")
            self.assertEqual(replay.state["concurrent.b"], "done")
            self.assertEqual(replay.head.sequence, 2)

    def test_committed_event_retry_is_idempotent_across_view_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"status=P410\n---\n")
            first = append_state_delta(
                state_path,
                {"status": "P500"},
                event_id="event-retry",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )
            before = state_path.stat().st_size

            retried = append_state_delta(
                state_path,
                {"status": "P500"},
                event_id="event-retry",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )

            self.assertEqual(state_path.stat().st_size, before)
            self.assertEqual(retried.head, first.head)

    def test_retry_older_than_recent_view_index_scans_canonical_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"status=P410\n---\n")
            first: object | None = None
            for index in range(130):
                replay = append_state_delta(
                    state_path,
                    {f"event.value.{index}": str(index)},
                    event_id=f"event-{index}",
                    event_type="state.updated",
                    occurred_at="2026-08-21T00:00:00+09:00",
                    committed_at="2026-08-21T00:00:01+09:00",
                )
                if index == 0:
                    first = replay
            before = state_path.stat().st_size

            retried = append_state_delta(
                state_path,
                {"event.value.0": "0"},
                event_id="event-0",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )

            self.assertIsNotNone(first)
            self.assertEqual(state_path.stat().st_size, before)
            self.assertEqual(retried.head.sequence, 130)

    def test_view_publication_failure_never_rolls_back_committed_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            legacy = b"status=P410\n---\n"
            state_path.write_bytes(legacy)

            with (
                patch(
                    "toc.state_store.write_run_file_text",
                    side_effect=OSError("projection disk failure"),
                ),
                self.assertWarnsRegex(RuntimeWarning, "delta committed"),
            ):
                committed = append_state_delta(
                    state_path,
                    {"status": "P500"},
                    event_id="event-projection-failure",
                    event_type="state.updated",
                    occurred_at="2026-08-21T00:00:00+09:00",
                    committed_at="2026-08-21T00:00:01+09:00",
                )

            self.assertGreater(state_path.stat().st_size, len(legacy))
            self.assertEqual(committed.state["status"], "P500")
            repaired = read_current_state(state_path)
            self.assertEqual(repaired.state["status"], "P500")

    def test_corrupt_current_view_is_rebuilt_from_canonical_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"status=P410\n---\n")
            expected = append_state_delta(
                state_path,
                {"status": "P500"},
                event_id="event-current",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )
            view_path = run_dir / "state.current.json"
            view_path.write_text('{"corrupt": true}\n', encoding="utf-8")

            rebuilt = read_current_state(state_path)

            self.assertEqual(rebuilt.state, expected.state)
            self.assertEqual(rebuilt.head, expected.head)
            self.assertIn(
                '"schema_version": "toc.state.current.v1"',
                view_path.read_text(encoding="utf-8"),
            )

    def test_self_consistent_forged_view_state_is_rebuilt_from_delta_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"status=P410\n---\n")
            expected = append_state_delta(
                state_path,
                {"review.scene.status": "approved"},
                event_id="event-approved",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )
            view_path = run_dir / "state.current.json"
            payload = json.loads(view_path.read_text(encoding="utf-8"))
            payload["state"]["review.scene.status"] = "rejected"
            canonical = json.dumps(
                payload["state"],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            payload["state_sha256"] = "sha256:" + hashlib.sha256(
                b"toc.state.current.v1.state\0" + canonical
            ).hexdigest()
            view_path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            rebuilt = read_current_state(state_path)

            self.assertEqual(rebuilt.state, expected.state)
            self.assertEqual(rebuilt.state["review.scene.status"], "approved")

    def test_ahead_current_view_is_rebuilt_from_canonical_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            state_path = run_dir / "state.txt"
            state_path.write_bytes(b"status=P410\n---\n")
            expected = append_state_delta(
                state_path,
                {"status": "P500"},
                event_id="event-current",
                event_type="state.updated",
                occurred_at="2026-08-21T00:00:00+09:00",
                committed_at="2026-08-21T00:00:01+09:00",
            )
            view_path = run_dir / "state.current.json"
            payload = json.loads(view_path.read_text(encoding="utf-8"))
            payload["log_cursor"]["committed_bytes"] += 1
            view_path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            rebuilt = read_current_state(state_path)

            self.assertEqual(rebuilt.state, expected.state)
            self.assertEqual(rebuilt.head, expected.head)

    def test_concurrent_compat_writers_cannot_publish_a_stale_run_status(self) -> None:
        from toc.harness import append_state_snapshot

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            (run_dir / "state.txt").write_bytes(b"status=P410\n---\n")
            barrier = threading.Barrier(2)
            errors: list[BaseException] = []

            def update(name: str) -> None:
                try:
                    barrier.wait(timeout=5)
                    append_state_snapshot(
                        run_dir / "state.txt",
                        {f"projection.{name}": "done"},
                    )
                except BaseException as exc:
                    errors.append(exc)

            threads = [
                threading.Thread(target=update, args=(name,))
                for name in ("a", "b")
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertEqual(errors, [])
            payload = json.loads(
                (run_dir / "run_status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["state_flat"]["projection.a"], "done")
            self.assertEqual(payload["state_flat"]["projection.b"], "done")


if __name__ == "__main__":
    unittest.main()
