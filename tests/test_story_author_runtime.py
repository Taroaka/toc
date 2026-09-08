from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from toc.story_author_runtime import (
    STORY_AUTHOR_TRANSPORT_SCHEMA,
    StoryAuthorRuntimeError,
    build_story_transport_prompt,
    decode_story_transport_payload,
    run_structured_story_turn,
)


def test_flexible_story_schema_uses_closed_transport_envelope() -> None:
    inner_schema = {
        "type": "object",
        "properties": {"scene_plan": {"type": "array"}},
        "required": ["scene_plan"],
        "additionalProperties": True,
    }

    prompt = build_story_transport_prompt("author", inner_schema)
    decoded = decode_story_transport_payload(
        {"result_json": '{"scene_plan": [], "rich_extension": {"x": 1}}'}
    )

    assert STORY_AUTHOR_TRANSPORT_SCHEMA["additionalProperties"] is False
    assert "result_json" in prompt
    assert '"scene_plan"' in prompt
    assert decoded["rich_extension"] == {"x": 1}


class FakeClient:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        self.started = False
        self.stopped = False
        self.thread_kwargs: dict = {}
        self.turn_kwargs: dict = {}

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def start_thread(self, **kwargs) -> str:
        self.thread_kwargs = kwargs
        return "thread-story-author"

    async def run_turn(self, **kwargs) -> list[dict]:
        self.turn_kwargs = kwargs
        return [
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "agentMessage",
                        "text": message,
                    }
                },
            }
            for message in self.messages
        ]


def test_structured_story_turn_uses_astra_default_read_only_and_output_schema() -> None:
    client = FakeClient(['{"scene_plan": []}'])
    schema = {
        "type": "object",
        "properties": {"scene_plan": {"type": "array"}},
        "required": ["scene_plan"],
        "additionalProperties": False,
    }

    result = asyncio.run(
        run_structured_story_turn(
            client_factory=lambda: client,
            cwd=Path("/tmp/story-author"),
            prompt="author a research-grounded story",
            output_schema=schema,
            timeout_seconds=1200,
        )
    )

    assert result.payload == {"scene_plan": []}
    assert result.model == "gpt-6-astra"
    assert client.thread_kwargs["model"] == "gpt-6-astra"
    assert client.thread_kwargs["sandbox"] == "read-only"
    assert client.thread_kwargs["approval_policy"] == "never"
    assert client.turn_kwargs["output_schema"] == schema
    assert client.turn_kwargs["reset_timeout_on_notification"] is False
    assert client.stopped is True


def test_structured_story_turn_ignores_noncompleted_agent_message_repeats() -> None:
    class RepeatingClient(FakeClient):
        async def run_turn(self, **kwargs) -> list[dict]:
            self.turn_kwargs = kwargs
            item = {"type": "agentMessage", "text": '{"scene_plan": []}'}
            return [
                {"method": "item/started", "params": {"item": item}},
                {"method": "item/delta", "params": {"item": item}},
                {"method": "item/completed", "params": {"item": item}},
            ]

    result = asyncio.run(
        run_structured_story_turn(
            client_factory=lambda: RepeatingClient([]),
            cwd=Path("/tmp/story-author"),
            prompt="author",
            output_schema={"type": "object"},
        )
    )

    assert result.payload == {"scene_plan": []}


def test_structured_story_turn_rejects_multiple_agent_payloads() -> None:
    client = FakeClient(['{"scene_plan": []}', '{"scene_plan": [1]}'])

    with pytest.raises(StoryAuthorRuntimeError, match="exactly one"):
        asyncio.run(
            run_structured_story_turn(
                client_factory=lambda: client,
                cwd=Path("/tmp/story-author"),
                prompt="author",
                output_schema={"type": "object"},
            )
        )

    assert client.stopped is True


def test_structured_story_turn_can_use_last_completed_transport_revision() -> None:
    client = FakeClient(
        [
            '{"result_json":"{\\"scene_plan\\": [1]}"}',
            '{"result_json":"{\\"scene_plan\\": [1, 2]}"}',
        ]
    )

    result = asyncio.run(
        run_structured_story_turn(
            client_factory=lambda: client,
            cwd=Path("/tmp/story-author"),
            prompt="author",
            output_schema=STORY_AUTHOR_TRANSPORT_SCHEMA,
            allow_multiple_completed_messages=True,
        )
    )

    assert decode_story_transport_payload(result.payload) == {
        "scene_plan": [1, 2]
    }


def test_structured_story_turn_rejects_non_json_output() -> None:
    client = FakeClient(["not json"])

    with pytest.raises(StoryAuthorRuntimeError, match="valid JSON"):
        asyncio.run(
            run_structured_story_turn(
                client_factory=lambda: client,
                cwd=Path("/tmp/story-author"),
                prompt="author",
                output_schema={"type": "object"},
            )
        )
