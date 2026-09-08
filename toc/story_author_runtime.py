"""Small, dependency-injected runtime for structured story author turns.

The story author is intentionally kept behind a client factory.  This module
only knows the narrow async protocol required to run a turn; it does not know
how a Codex client is constructed.  Keeping construction outside this module
also makes the author easy to exercise with a deterministic fake in tests.

The returned value contains the exact identities of the prompt and decoded
payload.  Those identities are useful to callers which persist ``story.md``
and need to prove which author turn produced it.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence


DEFAULT_STORY_AUTHOR_MODEL = "gpt-6-astra"
DEFAULT_SCENE_AUTHOR_MODEL = "gpt-6-astra"
DEFAULT_STORY_AUTHOR_TIMEOUT_SECONDS = 1200
STORY_AUTHOR_PROVENANCE_SCHEMA = "story_author_runtime_provenance_v1"
STORY_AUTHOR_TRANSPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"result_json": {"type": "string"}},
    "required": ["result_json"],
    "additionalProperties": False,
}


class StoryAuthorRuntimeError(RuntimeError):
    """Raised when a structured story-author turn cannot be trusted."""


class StoryAuthorClient(Protocol):
    """The client surface needed by :func:`run_structured_story_turn`."""

    async def start(self) -> None: ...

    async def start_thread(self, **kwargs: Any) -> str: ...

    async def run_turn(self, **kwargs: Any) -> list[dict[str, Any]]: ...

    async def stop(self) -> None: ...


ClientFactory = Callable[..., StoryAuthorClient]


@dataclass(frozen=True)
class StoryAuthorProvenance:
    """Immutable identity and execution metadata for an author turn."""

    schema_version: str
    model: str
    thread_id: str
    cwd: str
    sandbox: str
    approval_policy: str
    prompt_sha256: str
    output_schema_sha256: str
    response_sha256: str
    payload_sha256: str
    transcript_sha256: str

    def as_dict(self) -> dict[str, str]:
        """Return a JSON-serializable mapping for artifact persistence."""

        return {
            "schema_version": self.schema_version,
            "model": self.model,
            "thread_id": self.thread_id,
            "cwd": self.cwd,
            "sandbox": self.sandbox,
            "approval_policy": self.approval_policy,
            "prompt_sha256": self.prompt_sha256,
            "output_schema_sha256": self.output_schema_sha256,
            "response_sha256": self.response_sha256,
            "payload_sha256": self.payload_sha256,
            "transcript_sha256": self.transcript_sha256,
        }


@dataclass(frozen=True)
class StoryAuthorResult:
    """The decoded story author payload and its request-bound provenance."""

    payload: dict[str, Any]
    model: str
    thread_id: str
    prompt_sha256: str
    payload_sha256: str
    response_sha256: str
    transcript_sha256: str
    provenance: StoryAuthorProvenance
    transcript: tuple[dict[str, Any], ...] = ()
    response_text: str = ""

    @property
    def output_sha256(self) -> str:
        """Compatibility alias for callers that call the payload output."""

        return self.payload_sha256

    @property
    def input_sha256(self) -> str:
        """Compatibility alias for the request prompt identity."""

        return self.prompt_sha256

    def as_dict(self) -> dict[str, Any]:
        """Return a persistence-friendly representation of this result."""

        return {
            "payload": self.payload,
            "model": self.model,
            "thread_id": self.thread_id,
            "prompt_sha256": self.prompt_sha256,
            "payload_sha256": self.payload_sha256,
            "response_sha256": self.response_sha256,
            "transcript_sha256": self.transcript_sha256,
            "provenance": self.provenance.as_dict(),
        }


def _canonical_json(value: Any) -> bytes:
    """Encode JSON values deterministically for request/output identities."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StoryAuthorRuntimeError(
            "story author provenance value is not JSON serializable"
        ) from exc


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value))


def build_story_transport_prompt(
    prompt: str, output_schema: Mapping[str, Any]
) -> str:
    """Wrap a flexible rich contract in a strict app-server envelope.

    OpenAI structured output requires every object schema to be closed. Story
    artifacts deliberately allow rich extension keys, so the transport uses
    one closed string field and validates the decoded document deterministically
    in the authoring pipeline.
    """

    return (
        prompt.rstrip()
        + "\n\nTRANSPORT CONTRACT:\n"
        + "Return exactly one JSON object with one key, result_json. "
        + "result_json must be a JSON-encoded string containing the complete "
        + "inner author result. The decoded inner object must satisfy this "
        + "authoring schema and all prompt invariants:\n"
        + json.dumps(output_schema, ensure_ascii=False, sort_keys=True)
    )


def decode_story_transport_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if set(payload) != {"result_json"} or not isinstance(
        payload.get("result_json"), str
    ):
        raise StoryAuthorRuntimeError(
            "story author transport must contain only result_json string"
        )
    try:
        decoded = json.loads(str(payload["result_json"]))
    except json.JSONDecodeError as exc:
        raise StoryAuthorRuntimeError(
            "story author result_json must contain valid JSON"
        ) from exc
    if not isinstance(decoded, dict):
        raise StoryAuthorRuntimeError(
            "story author result_json must decode to a JSON object"
        )
    return decoded


_JSON_FENCE_RE = re.compile(
    r"\A```(?:json)?[ \t]*\r?\n(?P<body>.*?)\r?\n```\Z",
    flags=re.IGNORECASE | re.DOTALL,
)


def _json_text_from_agent_message(text: Any) -> str:
    """Normalize one agent message while preserving a strict JSON boundary.

    Structured output should be JSON rather than prose.  A single conventional
    Markdown JSON fence is accepted because some clients still wrap structured
    output despite receiving an output schema; prose before or after the JSON
    remains invalid and is not silently stripped.
    """

    if not isinstance(text, str):
        raise StoryAuthorRuntimeError(
            "story author agentMessage must contain valid JSON text"
        )
    candidate = text.strip()
    match = _JSON_FENCE_RE.fullmatch(candidate)
    if match is not None:
        candidate = match.group("body").strip()
    if not candidate:
        raise StoryAuthorRuntimeError(
            "story author agentMessage must contain valid JSON text"
        )
    return candidate


def _agent_message_texts(transcript: Sequence[Mapping[str, Any]]) -> list[str]:
    """Collect completed agent messages exactly once.

    App-server transcripts can repeat the same item in started, delta, and
    completed notifications. Only ``item/completed`` owns a final payload;
    recursively walking every envelope incorrectly counts one response many
    times.
    """

    messages: list[str] = []
    for index, event in enumerate(transcript):
        if not isinstance(event, Mapping):
            raise StoryAuthorRuntimeError(
                f"story author transcript event {index} must be an object"
            )
        if event.get("method") != "item/completed":
            continue
        params = event.get("params")
        item = params.get("item") if isinstance(params, Mapping) else None
        if isinstance(item, Mapping) and item.get("type") == "agentMessage":
            messages.append(item.get("text"))  # type: ignore[arg-type]
    return messages


def _decode_agent_payload(
    transcript: Sequence[Mapping[str, Any]],
    *,
    allow_multiple_completed_messages: bool = False,
) -> tuple[dict[str, Any], str]:
    messages = _agent_message_texts(transcript)
    if len(messages) != 1 and not (
        allow_multiple_completed_messages and messages
    ):
        raise StoryAuthorRuntimeError(
            "story author turn must contain exactly one agentMessage JSON payload; "
            f"got {len(messages)}"
        )

    # Long structured Codex turns may complete several assistant items as the
    # model revises its draft. The last completed item is the canonical final
    # response; callers must opt into this transport behavior explicitly.
    response_text = _json_text_from_agent_message(messages[-1])
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise StoryAuthorRuntimeError(
            "story author agentMessage must contain valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise StoryAuthorRuntimeError(
            "story author agentMessage must contain a valid JSON object"
        )
    return payload, response_text


def _factory_accepts_cwd(factory: ClientFactory) -> bool:
    """Determine whether an injected factory asks for ``cwd``.

    The public test and the simplest callers use a zero-argument lambda.  A
    production integration often supplies ``cwd`` to a factory.  Supporting
    both forms keeps construction injected without relying on a concrete
    client import.
    """

    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        return False
    try:
        signature.bind()
    except TypeError:
        try:
            signature.bind(cwd=Path("."))
        except TypeError:
            return False
        return True
    return False


def _build_client(factory: ClientFactory, cwd: Path) -> StoryAuthorClient:
    client = factory(cwd=cwd) if _factory_accepts_cwd(factory) else factory()
    if client is None:
        raise StoryAuthorRuntimeError("story author client factory returned no client")
    return client


async def run_structured_story_turn(
    *,
    client_factory: ClientFactory,
    cwd: Path,
    prompt: str,
    output_schema: dict[str, Any],
    model: str = DEFAULT_STORY_AUTHOR_MODEL,
    timeout_seconds: int = DEFAULT_STORY_AUTHOR_TIMEOUT_SECONDS,
    allow_multiple_completed_messages: bool = False,
    reset_timeout_on_notification: bool = False,
) -> StoryAuthorResult:
    """Run one read-only, structured story-author turn.

    Client construction is deliberately injected.  The client is started,
    configured with the story-author safety contract, and always stopped in a
    ``finally`` block.  Only one completed ``agentMessage`` is accepted, and
    that message must decode to a JSON object.
    """

    if not isinstance(prompt, str) or not prompt.strip():
        raise StoryAuthorRuntimeError("story author prompt must not be empty")
    if not isinstance(output_schema, dict):
        raise StoryAuthorRuntimeError("story author output_schema must be an object")
    if not isinstance(model, str) or not model.strip():
        raise StoryAuthorRuntimeError("story author model must not be empty")
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or timeout_seconds < 1:
        raise StoryAuthorRuntimeError("story author timeout_seconds must be positive")

    resolved_cwd = Path(cwd)
    client: StoryAuthorClient | None = None
    try:
        client = _build_client(client_factory, resolved_cwd)
        await client.start()
        thread_id = await client.start_thread(
            cwd=resolved_cwd,
            model=model,
            sandbox="read-only",
            approval_policy="never",
        )
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise StoryAuthorRuntimeError(
                "story author thread start did not return a thread id"
            )
        transcript = await client.run_turn(
            thread_id=thread_id,
            text=prompt,
            cwd=resolved_cwd,
            timeout_seconds=timeout_seconds,
            reset_timeout_on_notification=reset_timeout_on_notification,
            output_schema=output_schema,
        )
        if not isinstance(transcript, (list, tuple)):
            raise StoryAuthorRuntimeError("story author turn transcript must be a list")

        payload, response_text = _decode_agent_payload(
            transcript,
            allow_multiple_completed_messages=allow_multiple_completed_messages,
        )
        prompt_sha256 = _sha256_text(prompt)
        output_schema_sha256 = _sha256_json(output_schema)
        response_sha256 = _sha256_text(response_text)
        payload_sha256 = _sha256_json(payload)
        transcript_sha256 = _sha256_json(transcript)
        provenance = StoryAuthorProvenance(
            schema_version=STORY_AUTHOR_PROVENANCE_SCHEMA,
            model=model,
            thread_id=thread_id,
            cwd=str(resolved_cwd),
            sandbox="read-only",
            approval_policy="never",
            prompt_sha256=prompt_sha256,
            output_schema_sha256=output_schema_sha256,
            response_sha256=response_sha256,
            payload_sha256=payload_sha256,
            transcript_sha256=transcript_sha256,
        )
        return StoryAuthorResult(
            payload=payload,
            model=model,
            thread_id=thread_id,
            prompt_sha256=prompt_sha256,
            payload_sha256=payload_sha256,
            response_sha256=response_sha256,
            transcript_sha256=transcript_sha256,
            provenance=provenance,
            transcript=tuple(dict(event) for event in transcript),
            response_text=response_text,
        )
    except StoryAuthorRuntimeError:
        raise
    except Exception as exc:
        raise StoryAuthorRuntimeError(
            f"story author turn failed: {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        if client is not None:
            await client.stop()


__all__ = [
    "ClientFactory",
    "DEFAULT_SCENE_AUTHOR_MODEL",
    "DEFAULT_STORY_AUTHOR_MODEL",
    "DEFAULT_STORY_AUTHOR_TIMEOUT_SECONDS",
    "STORY_AUTHOR_PROVENANCE_SCHEMA",
    "STORY_AUTHOR_TRANSPORT_SCHEMA",
    "StoryAuthorClient",
    "StoryAuthorProvenance",
    "StoryAuthorResult",
    "StoryAuthorRuntimeError",
    "build_story_transport_prompt",
    "decode_story_transport_payload",
    "run_structured_story_turn",
]
