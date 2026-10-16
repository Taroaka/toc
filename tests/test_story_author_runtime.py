from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest

from toc.story_author_runtime import (
    DEFAULT_REPAIR_AUTHOR_MODEL,
    DEFAULT_SCENE_AUTHOR_MODEL,
    DEFAULT_STORY_AUTHOR_MODEL,
    JsonSyntaxRepairReceipt,
    STORY_AUTHOR_TRANSPORT_SCHEMA,
    StoryAuthorRuntimeError,
    build_story_transport_prompt,
    decode_json_object_with_repair,
    decode_story_transport_payload,
    decode_story_transport_payload_with_receipt,
    run_structured_story_turn,
)


def test_story_author_roles_default_to_gpt6_model_family() -> None:
    assert DEFAULT_STORY_AUTHOR_MODEL == "gpt-6-astra"
    assert DEFAULT_SCENE_AUTHOR_MODEL == "gpt-6-astra"
    assert DEFAULT_REPAIR_AUTHOR_MODEL == "gpt-6-luna"


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


def test_transport_decoder_repairs_one_redundant_final_object_delimiter() -> None:
    receipts: list[JsonSyntaxRepairReceipt] = []

    decoded = decode_story_transport_payload(
        {"result_json": '{"scene_plan": [], "title": "kept"} }'},
        on_syntax_repair=receipts.append,
    )

    assert decoded == {"scene_plan": [], "title": "kept"}
    assert len(receipts) == 1
    assert receipts[0].repaired is True
    assert receipts[0].rule == "one_redundant_closing_brace"
    assert receipts[0].removed_suffix == " }"


def test_transport_decoder_keeps_clean_decode_receipt_available() -> None:
    decoded, receipt = decode_story_transport_payload_with_receipt(
        {"result_json": '{"scene_plan": []}'}
    )

    assert decoded == {"scene_plan": []}
    assert receipt == JsonSyntaxRepairReceipt.clean('{"scene_plan": []}')


def test_json_object_helper_returns_a_clean_receipt_without_changing_text() -> None:
    decoded, receipt = decode_json_object_with_repair('{"nested": {"x": 1}}')

    assert decoded == {"nested": {"x": 1}}
    assert receipt.repaired is False
    assert receipt.original_text == receipt.normalized_text == '{"nested": {"x": 1}}'


@pytest.mark.parametrize('raw, expected', [
    ('{"items":[{"name":"本文"],"kept":true}}', None),
    ('{"items":[{"name":"本文"]},"kept":true}', {'items': [{'name': '本文'}], 'kept': True}),
    ('{"data":{"values":[1,2}]}}', None),
    ('{"data":{"values":[1,2}]}', {'data': {'values': [1, 2]}}),
])
def test_single_reversed_closing_pair_is_bounded_and_preserves_all_tokens(raw, expected):
    from toc.story_syntax_patch import _tokens
    if expected is None:
        with pytest.raises(StoryAuthorRuntimeError):
            decode_story_transport_payload({'result_json': raw})
        return
    decoded, receipt = decode_story_transport_payload_with_receipt({'result_json': raw})
    assert decoded == expected
    assert receipt.rule == 'one_transposed_closing_pair'
    assert len(receipt.original_text) == len(receipt.normalized_text)
    assert _tokens(receipt.original_text)[0] == _tokens(receipt.normalized_text)[0]
    assert receipt.as_dict()['edit_offset'] >= 0


@pytest.mark.parametrize(
    "result_json",
    [
        '{"a": 1}{"b": 2}',
        '{"a": 1} prose',
        '{"a": 1}}}',
        '{"a": 1]}',
        '{"a":',
        '{"a": "unterminated}',
        '{"a": 1, "a": 2}',
        '{"nested": {"a": 1, "a": 2}}',
        '{"value": NaN}',
    ],
)
def test_transport_decoder_rejects_unbounded_or_ambiguous_json_repairs(
    result_json: str,
) -> None:
    with pytest.raises(StoryAuthorRuntimeError):
        decode_story_transport_payload({"result_json": result_json})


def test_transport_decoder_preserves_non_object_error_boundary() -> None:
    with pytest.raises(
        StoryAuthorRuntimeError,
        match="must decode to a JSON object",
    ) as raised:
        decode_story_transport_payload({"result_json": '[1, 2]'})

    assert raised.value.diagnostic is not None
    assert raised.value.diagnostic.code == "top_level_type"


def test_invalid_json_error_exposes_structured_parser_diagnostic() -> None:
    with pytest.raises(StoryAuthorRuntimeError) as raised:
        decode_story_transport_payload({"result_json": '{"a": }'})

    diagnostic = raised.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.offset == 6
    assert diagnostic.line == 1
    assert diagnostic.column == 7
    assert diagnostic.parser_message == "Expecting value"
    assert raised.value.diagnostics == diagnostic.as_dict()


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


def _write_valid_png(path: Path) -> Path:
    """Write a small valid PNG without requiring Pillow in the test setup."""

    path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
        )
    )
    return path


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


def test_structured_story_turn_forwards_valid_local_images(tmp_path: Path) -> None:
    client = FakeClient(['{"scene_plan": []}'])
    image = _write_valid_png(tmp_path / "reference.png")

    asyncio.run(
        run_structured_story_turn(
            client_factory=lambda: client,
            cwd=Path("/tmp/story-author"),
            prompt="author",
            output_schema={"type": "object"},
            local_images=[image],
        )
    )

    assert client.turn_kwargs["local_images"] == [image]
    assert client.stopped is True


def test_structured_story_turn_omits_local_images_when_unspecified() -> None:
    client = FakeClient(['{"scene_plan": []}'])

    asyncio.run(
        run_structured_story_turn(
            client_factory=lambda: client,
            cwd=Path("/tmp/story-author"),
            prompt="author",
            output_schema={"type": "object"},
        )
    )

    assert "local_images" not in client.turn_kwargs


@pytest.mark.parametrize("image_kind", ["missing", "directory", "undecodable"])
def test_structured_story_turn_rejects_invalid_local_images_before_starting_client(
    tmp_path: Path, image_kind: str
) -> None:
    image = tmp_path / "reference.png"
    if image_kind == "directory":
        image.mkdir()
    elif image_kind == "undecodable":
        image.write_bytes(b"not an image")

    def unexpected_client_factory() -> FakeClient:
        pytest.fail("invalid local images must be rejected before creating a client")

    with pytest.raises(StoryAuthorRuntimeError, match="local image"):
        asyncio.run(
            run_structured_story_turn(
                client_factory=unexpected_client_factory,
                cwd=tmp_path,
                prompt="author",
                output_schema={"type": "object"},
                local_images=[image],
            )
        )


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
