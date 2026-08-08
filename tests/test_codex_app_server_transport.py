from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.codex_app_server import (
    CodexAppServerClient,
    CodexAppServerError,
    CodexAppServerTransportError,
)


def test_submission_guard_runs_before_thread_and_turn_requests() -> None:
    calls: list[str] = []

    def guard() -> None:
        calls.append("guard")
        raise RuntimeError("bound run changed")

    async def run_case() -> None:
        client = CodexAppServerClient(
            cwd=Path("/tmp"),
            submission_guard=guard,
        )

        async def request_must_not_run(*_args, **_kwargs):
            raise AssertionError("guard must run before app-server request")

        client.request = request_must_not_run  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="bound run changed"):
            await client.start_thread()
        with pytest.raises(RuntimeError, match="bound run changed"):
            await client.run_turn(thread_id="thread-1", text="hello")

    asyncio.run(run_case())
    assert calls == ["guard", "guard"]


def test_submission_guard_rechecks_under_wire_write_lock() -> None:
    calls: list[str] = []
    writes: list[bytes] = []

    def guard() -> None:
        calls.append("guard")
        if len(calls) == 2:
            raise RuntimeError("bound run changed at wire boundary")

    class FakeStdin:
        def write(self, payload: bytes) -> None:
            writes.append(payload)

        async def drain(self) -> None:
            return None

    async def run_case() -> None:
        client = CodexAppServerClient(
            cwd=Path("/tmp"),
            submission_guard=guard,
        )
        client.proc = SimpleNamespace(stdin=FakeStdin())  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="wire boundary"):
            await client.start_thread()
        assert not client._pending

    asyncio.run(run_case())
    assert calls == ["guard", "guard"]
    assert writes == []


def test_app_server_accepts_multi_megabyte_image_notification() -> None:
    async def run_case(root: Path) -> None:
        fake_codex = root / "fake-codex"
        fake_codex.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import sys

                for raw_line in sys.stdin:
                    message = json.loads(raw_line)
                    if "id" in message:
                        print(json.dumps({"id": message["id"], "result": {}}), flush=True)
                    elif message.get("method") == "initialized":
                        payload = {
                            "method": "item/completed",
                            "params": {
                                "turnId": "turn-1",
                                "item": {
                                    "id": "image-1",
                                    "type": "imageGeneration",
                                    "status": "completed",
                                    "result": "A" * (3 * 1024 * 1024),
                                    "savedPath": "/tmp/generated.png",
                                },
                            },
                        }
                        print(json.dumps(payload), flush=True)
                        break
                """
            ),
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        codex_home = root / "codex-home"
        codex_home.mkdir()
        client = CodexAppServerClient(cwd=root, codex_bin=str(fake_codex))
        client.preflight_runtime = lambda: {}  # type: ignore[method-assign]

        with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False):
            await client.start()
            notification = await asyncio.wait_for(client._notifications.get(), timeout=2)
            await client.stop()

        item = notification["params"]["item"]
        assert item["savedPath"] == "/tmp/generated.png"
        assert "result" not in item

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(run_case(Path(tmp)))


def test_app_server_reader_failure_interrupts_turn_waiter() -> None:
    class BrokenStdout:
        async def readline(self) -> bytes:
            raise ValueError("reader exploded")

    class FakeProcess:
        stdout = BrokenStdout()
        returncode = None

    async def run_case() -> None:
        client = CodexAppServerClient(cwd=Path("/tmp"))
        client.proc = FakeProcess()  # type: ignore[assignment]

        async def fake_request(_method: str, _params: dict | None = None) -> dict:
            return {"turn": {"id": "turn-1"}}

        client.request = fake_request  # type: ignore[method-assign]
        client._reader_task = asyncio.create_task(client._read_loop())

        with pytest.raises(CodexAppServerTransportError, match="reader exploded"):
            await asyncio.wait_for(
                client.run_turn(thread_id="thread-1", text="hello", timeout_seconds=30),
                timeout=1,
            )

    asyncio.run(run_case())


def test_app_server_invalid_json_interrupts_turn_waiter() -> None:
    class BrokenStdout:
        async def readline(self) -> bytes:
            return b"not-json\n"

    class FakeProcess:
        stdout = BrokenStdout()
        returncode = None

    async def run_case() -> None:
        client = CodexAppServerClient(cwd=Path("/tmp"))
        client.proc = FakeProcess()  # type: ignore[assignment]

        async def fake_request(_method: str, _params: dict | None = None) -> dict:
            return {"turn": {"id": "turn-1"}}

        client.request = fake_request  # type: ignore[method-assign]
        client._reader_task = asyncio.create_task(client._read_loop())

        with pytest.raises(CodexAppServerTransportError, match="invalid JSONL frame"):
            await asyncio.wait_for(
                client.run_turn(thread_id="thread-1", text="hello", timeout_seconds=30),
                timeout=1,
            )

    asyncio.run(run_case())


def test_scrubbed_app_server_env_removes_api_lane_overrides() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        codex_home = Path(tmp) / "codex-home"
        codex_home.mkdir()
        client = CodexAppServerClient(cwd=Path(tmp), scrub_sensitive_env=True)
        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(codex_home),
                "OPENAI_API_KEY": "api-secret",
                "OPENAI_BASE_URL": "https://api.example.invalid",
                "AZURE_OPENAI_ENDPOINT": "https://azure.example.invalid",
                "TOC_SAFE_TEST_VALUE": "kept",
            },
            clear=False,
        ):
            child_env = client._subprocess_env()

        assert "OPENAI_API_KEY" not in child_env
        assert "OPENAI_BASE_URL" not in child_env
        assert "AZURE_OPENAI_ENDPOINT" not in child_env
        assert child_env["TOC_SAFE_TEST_VALUE"] == "kept"


def test_app_server_rejects_non_chatgpt_account_for_subscription_lane() -> None:
    async def run_case(root: Path) -> None:
        fake_codex = root / "fake-codex"
        fake_codex.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import sys

                for raw_line in sys.stdin:
                    message = json.loads(raw_line)
                    if "id" not in message:
                        continue
                    result = {}
                    if message.get("method") == "account/read":
                        result = {"account": {"type": "apiKey", "planType": None}}
                    print(json.dumps({"id": message["id"], "result": result}), flush=True)
                """
            ),
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)
        codex_home = root / "codex-home"
        codex_home.mkdir()
        client = CodexAppServerClient(
            cwd=root,
            codex_bin=str(fake_codex),
            scrub_sensitive_env=True,
            require_chatgpt_account=True,
            require_chatgpt_pro=True,
        )
        client.preflight_runtime = lambda: {}  # type: ignore[method-assign]

        with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False):
            with pytest.raises(CodexAppServerError, match="ChatGPT account authentication"):
                await client.start()
            await client.stop()

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(run_case(Path(tmp)))


def test_generate_image_recovers_completed_item_from_transport_transcript() -> None:
    async def run_case(root: Path) -> None:
        saved = root / "generated.png"
        saved.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        client = CodexAppServerClient(cwd=root)
        client.generated_images_root = lambda: root / "generated_images"  # type: ignore[method-assign]

        async def fake_start_thread(**_kwargs) -> str:
            return "thread-1"

        async def fake_run_turn(**_kwargs) -> list[dict]:
            raise CodexAppServerTransportError(
                "turn transport closed",
                transcript=[
                    {"method": "turn/started", "params": {"turnId": "turn-1"}},
                    {
                        "method": "item/completed",
                        "params": {
                            "turnId": "turn-1",
                            "item": {
                                "id": "image-1",
                                "type": "imageGeneration",
                                "status": "completed",
                                "savedPath": str(saved),
                            },
                        },
                    },
                ],
            )

        client.start_thread = fake_start_thread  # type: ignore[method-assign]
        client.run_turn = fake_run_turn  # type: ignore[method-assign]
        result = await client.generate_image(
            prompt="prompt",
            output_path=root / "candidate.png",
            reference_images=[],
            item_id="scene1",
            run_dir=root,
            generation_job_id="job-1",
            allow_generated_images_fallback=False,
            provenance_policy="request_bound_v2",
            timeout_seconds=1,
        )

        assert result.saved_path == saved
        assert result.turn_id == "turn-1"
        assert result.image_generation_item_id == "image-1"
        assert result.provenance_authoritative

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(run_case(Path(tmp)))


def test_generate_image_recovers_saved_path_with_thread_read() -> None:
    async def run_case(root: Path) -> None:
        saved = root / "generated.png"
        saved.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        client = CodexAppServerClient(cwd=root)
        client.generated_images_root = lambda: root / "generated_images"  # type: ignore[method-assign]

        async def fake_start_thread(**_kwargs) -> str:
            return "thread-1"

        async def fake_run_turn(**_kwargs) -> list[dict]:
            raise CodexAppServerTransportError(
                "turn timed out",
                transcript=[{"method": "turn/started", "params": {"turnId": "turn-1"}}],
            )

        async def fake_request(method: str, params: dict | None = None) -> dict:
            assert method == "thread/read"
            assert params == {"threadId": "thread-1", "includeTurns": True}
            return {
                "thread": {
                    "id": "thread-1",
                    "turns": [
                        {
                            "id": "turn-1",
                            "status": "completed",
                            "items": [
                                {
                                    "id": "image-1",
                                    "type": "imageGeneration",
                                    "status": "completed",
                                    "savedPath": str(saved),
                                }
                            ],
                        }
                    ],
                }
            }

        client.start_thread = fake_start_thread  # type: ignore[method-assign]
        client.run_turn = fake_run_turn  # type: ignore[method-assign]
        client.request = fake_request  # type: ignore[method-assign]
        result = await client.generate_image(
            prompt="prompt",
            output_path=root / "candidate.png",
            reference_images=[],
            item_id="scene1",
            run_dir=root,
            generation_job_id="job-1",
            allow_generated_images_fallback=False,
            provenance_policy="request_bound_v2",
            timeout_seconds=1,
        )

        assert result.saved_path == saved
        assert result.turn_id == "turn-1"
        assert result.image_generation_item_id == "image-1"

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(run_case(Path(tmp)))


def test_generate_image_restarts_broken_transport_before_thread_read() -> None:
    async def run_case(root: Path) -> None:
        saved = root / "generated.png"
        saved.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        client = CodexAppServerClient(cwd=root)
        client.generated_images_root = lambda: root / "generated_images"  # type: ignore[method-assign]
        lifecycle: list[str] = []

        async def fake_start_thread(**_kwargs) -> str:
            return "thread-1"

        async def fake_run_turn(**_kwargs) -> list[dict]:
            error = CodexAppServerTransportError(
                "stdout reader failed",
                transcript=[{"method": "turn/started", "params": {"turnId": "turn-1"}}],
            )
            client._transport_error = error
            raise error

        async def fake_stop() -> None:
            lifecycle.append("stop")

        async def fake_start() -> None:
            lifecycle.append("start")
            client._transport_error = None

        async def fake_request(method: str, params: dict | None = None) -> dict:
            assert lifecycle == ["stop", "start"]
            assert method == "thread/read"
            assert params == {"threadId": "thread-1", "includeTurns": True}
            return {
                "thread": {
                    "id": "thread-1",
                    "turns": [
                        {
                            "id": "turn-1",
                            "status": "completed",
                            "items": [
                                {
                                    "id": "image-1",
                                    "type": "imageGeneration",
                                    "status": "completed",
                                    "savedPath": str(saved),
                                }
                            ],
                        }
                    ],
                }
            }

        client.start_thread = fake_start_thread  # type: ignore[method-assign]
        client.run_turn = fake_run_turn  # type: ignore[method-assign]
        client.stop = fake_stop  # type: ignore[method-assign]
        client.start = fake_start  # type: ignore[method-assign]
        client.request = fake_request  # type: ignore[method-assign]
        result = await client.generate_image(
            prompt="prompt",
            output_path=root / "candidate.png",
            reference_images=[],
            item_id="scene1",
            run_dir=root,
            generation_job_id="job-1",
            allow_generated_images_fallback=False,
            provenance_policy="request_bound_v2",
            timeout_seconds=1,
        )

        assert lifecycle == ["stop", "start"]
        assert result.saved_path == saved
        assert result.image_generation_item_id == "image-1"

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(run_case(Path(tmp)))


def test_generate_image_preserves_original_transport_error_without_recovery() -> None:
    async def run_case(root: Path) -> None:
        client = CodexAppServerClient(cwd=root)
        client.generated_images_root = lambda: root / "generated_images"  # type: ignore[method-assign]

        async def fake_start_thread(**_kwargs) -> str:
            return "thread-1"

        async def fake_run_turn(**_kwargs) -> list[dict]:
            raise CodexAppServerTransportError(
                "original turn timeout",
                transcript=[{"method": "turn/started", "params": {"turnId": "turn-1"}}],
            )

        async def fake_request(_method: str, _params: dict | None = None) -> dict:
            return {"thread": {"id": "thread-1", "turns": []}}

        client.start_thread = fake_start_thread  # type: ignore[method-assign]
        client.run_turn = fake_run_turn  # type: ignore[method-assign]
        client.request = fake_request  # type: ignore[method-assign]
        with pytest.raises(CodexAppServerTransportError, match="original turn timeout"):
            await client.generate_image(
                prompt="prompt",
                output_path=root / "candidate.png",
                reference_images=[],
                item_id="scene1",
                run_dir=root,
                generation_job_id="job-1",
                allow_generated_images_fallback=False,
                provenance_policy="request_bound_v2",
                timeout_seconds=1,
            )

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(run_case(Path(tmp)))


def test_generate_image_returns_on_current_turn_saved_item_before_turn_completed() -> None:
    async def run_case(root: Path) -> None:
        foreign_saved = root / "foreign.png"
        foreign_saved.write_bytes(b"\x89PNG\r\n\x1a\n" + b"foreign")
        current_saved = root / "current.png"
        current_saved.write_bytes(b"\x89PNG\r\n\x1a\n" + b"current")
        client = CodexAppServerClient(cwd=root)
        client.generated_images_root = lambda: root / "generated_images"  # type: ignore[method-assign]

        async def fake_start_thread(**_kwargs) -> str:
            return "thread-1"

        async def fake_request(method: str, _params: dict | None = None) -> dict:
            assert method == "turn/start"
            await client._notifications.put(
                {
                    "method": "item/completed",
                    "params": {
                        "turnId": "turn-foreign",
                        "item": {
                            "id": "image-foreign",
                            "type": "imageGeneration",
                            "status": "completed",
                            "savedPath": str(foreign_saved),
                        },
                    },
                }
            )
            await client._notifications.put(
                {
                    "method": "item/completed",
                    "params": {
                        "turnId": "turn-current",
                        "item": {
                            "id": "image-current",
                            "type": "imageGeneration",
                            "status": "completed",
                            "savedPath": str(current_saved),
                        },
                    },
                }
            )
            # Intentionally do not emit turn/completed. The completed, saved
            # image item is sufficient for the image-import caller to proceed.
            return {"turn": {"id": "turn-current"}}

        client.start_thread = fake_start_thread  # type: ignore[method-assign]
        client.request = fake_request  # type: ignore[method-assign]
        result = await asyncio.wait_for(
            client.generate_image(
                prompt="prompt",
                output_path=root / "candidate.png",
                reference_images=[],
                item_id="scene1",
                run_dir=root,
                generation_job_id="job-1",
                allow_generated_images_fallback=False,
                provenance_policy="request_bound_v2",
                timeout_seconds=30,
            ),
            timeout=0.5,
        )

        assert result.saved_path == current_saved
        assert result.turn_id == "turn-current"
        assert result.image_generation_item_id == "image-current"
        assert result.image_generation_item_count == 1
        assert result.provenance_authoritative

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(run_case(Path(tmp)))


def test_request_bound_v2_never_scans_shared_generated_images() -> None:
    async def run_case(root: Path) -> None:
        saved = root / "generated.png"
        saved.write_bytes(b"\x89PNG\r\n\x1a\n" + b"current")
        client = CodexAppServerClient(cwd=root)

        async def fake_start_thread(**_kwargs) -> str:
            return "thread-1"

        async def fake_run_turn(**_kwargs) -> list[dict]:
            return [
                {"method": "turn/started", "params": {"turnId": "turn-1"}},
                {
                    "method": "item/completed",
                    "params": {
                        "turnId": "turn-1",
                        "item": {
                            "id": "image-1",
                            "type": "imageGeneration",
                            "status": "completed",
                            "savedPath": str(saved),
                        },
                    },
                },
            ]

        client.start_thread = fake_start_thread  # type: ignore[method-assign]
        client.run_turn = fake_run_turn  # type: ignore[method-assign]
        with (
            patch(
                "server.codex_app_server.latest_generated_image_mtime_ns",
                side_effect=AssertionError("request_bound_v2 scanned generated_images"),
            ),
            patch(
                "server.codex_app_server.wait_for_unclaimed_generated_image_after",
                side_effect=AssertionError("request_bound_v2 watched generated_images"),
            ),
            patch(
                "server.codex_app_server.claim_latest_generated_image_after",
                side_effect=AssertionError("request_bound_v2 claimed from generated_images"),
            ),
        ):
            result = await client.generate_image(
                prompt="prompt",
                output_path=root / "candidate.png",
                reference_images=[],
                item_id="scene1",
                run_dir=root,
                generation_job_id="job-1",
                # A request-bound policy must remain strict even if a legacy
                # caller accidentally leaves this compatibility flag enabled.
                allow_generated_images_fallback=True,
                provenance_policy="request_bound_v2",
                timeout_seconds=1,
            )

        assert result.saved_path == saved
        assert result.source == "app_server"
        assert result.provenance_authoritative

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(run_case(Path(tmp)))
