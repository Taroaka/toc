"""Bounded, deterministic JSON object decoding for author transports.

The author transport carries a JSON document inside a string.  A provider can
occasionally append one closing brace after an otherwise complete object.  The
repair in this module is deliberately smaller than a general JSON fixer: it
only removes one redundant final ``}`` when the prefix is already a complete
JSON object and the suffix contains no other content.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


_JSON_WHITESPACE = " \t\r\n"
_REPAIR_RULE = "one_redundant_closing_brace"


@dataclass(frozen=True)
class JsonSyntaxDiagnostic:
    """Parser details suitable for a structured runtime error or log."""

    offset: int | None
    line: int | None
    column: int | None
    parser_message: str
    code: str = "invalid_json"

    def as_dict(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "line": self.line,
            "column": self.column,
            "parser_message": self.parser_message,
            "code": self.code,
        }


@dataclass(frozen=True)
class JsonSyntaxRepairReceipt:
    """Evidence for a clean decode or the one bounded syntax normalization."""

    repaired: bool
    rule: str | None
    original_text: str
    normalized_text: str
    removed_suffix: str = ""

    @classmethod
    def clean(cls, text: str) -> "JsonSyntaxRepairReceipt":
        return cls(
            repaired=False,
            rule=None,
            original_text=text,
            normalized_text=text,
        )

    @classmethod
    def one_redundant_closing_brace(
        cls, text: str, normalized_text: str
    ) -> "JsonSyntaxRepairReceipt":
        return cls(
            repaired=True,
            rule=_REPAIR_RULE,
            original_text=text,
            normalized_text=normalized_text,
            removed_suffix=text[len(normalized_text) :],
        )

    @property
    def original_sha256(self) -> str:
        return hashlib.sha256(self.original_text.encode("utf-8")).hexdigest()

    @property
    def normalized_sha256(self) -> str:
        return hashlib.sha256(self.normalized_text.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "repaired": self.repaired,
            "rule": self.rule,
            "original_sha256": self.original_sha256,
            "normalized_sha256": self.normalized_sha256,
            "original_length": len(self.original_text),
            "normalized_length": len(self.normalized_text),
            "removed_suffix": self.removed_suffix,
        }


class JsonSyntaxRepairError(ValueError):
    """Raised when an object cannot be decoded under the bounded rule."""

    def __init__(self, message: str, *, diagnostic: JsonSyntaxDiagnostic) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic


class _DuplicateKeyError(ValueError):
    def __init__(self, key: str) -> None:
        super().__init__(f"duplicate object key: {key!r}")
        self.key = key


class _NonJSONConstantError(ValueError):
    def __init__(self, constant: str) -> None:
        super().__init__(f"non-standard JSON constant: {constant}")
        self.constant = constant


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_non_json_constant(constant: str) -> None:
    raise _NonJSONConstantError(constant)


def _diagnostic_from_decode_error(
    error: json.JSONDecodeError,
) -> JsonSyntaxDiagnostic:
    return JsonSyntaxDiagnostic(
        offset=error.pos,
        line=error.lineno,
        column=error.colno,
        parser_message=error.msg,
    )


def _duplicate_key_diagnostic(error: _DuplicateKeyError) -> JsonSyntaxDiagnostic:
    return JsonSyntaxDiagnostic(
        offset=None,
        line=None,
        column=None,
        parser_message=str(error),
        code="duplicate_key",
    )


def _skip_json_whitespace(text: str) -> int:
    index = 0
    while index < len(text) and text[index] in _JSON_WHITESPACE:
        index += 1
    return index


def _is_one_redundant_closing_brace(suffix: str) -> bool:
    """Return whether *suffix* is exactly whitespace, one ``}``, whitespace."""

    start = _skip_json_whitespace(suffix)
    if start >= len(suffix) or suffix[start] != "}":
        return False
    return _skip_json_whitespace(suffix[start + 1 :]) == len(suffix) - start - 1


def _decode_first_value(
    text: str, decoder: json.JSONDecoder
) -> tuple[Any, int]:
    start = _skip_json_whitespace(text)
    return decoder.raw_decode(text, start)


def decode_json_object_with_repair(
    text: str,
) -> tuple[dict[str, Any], JsonSyntaxRepairReceipt]:
    """Decode one JSON object, applying only the bounded suffix repair.

    A successful repair requires the prefix to parse completely as an object
    with duplicate keys rejected, and the remaining input to be exactly one
    redundant closing brace surrounded by JSON whitespace.  No truncation,
    quote repair, guessed delimiters, prose stripping, or concatenated JSON is
    attempted.
    """

    if not isinstance(text, str):
        diagnostic = JsonSyntaxDiagnostic(
            offset=None,
            line=None,
            column=None,
            parser_message="JSON input must be a string",
            code="invalid_input",
        )
        raise JsonSyntaxRepairError(
            "JSON object input must be a string", diagnostic=diagnostic
        )

    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_non_json_constant,
    )
    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_json_constant,
        )
    except _DuplicateKeyError as exc:
        raise JsonSyntaxRepairError(
            str(exc), diagnostic=_duplicate_key_diagnostic(exc)
        ) from exc
    except _NonJSONConstantError as exc:
        diagnostic = JsonSyntaxDiagnostic(
            offset=None,
            line=None,
            column=None,
            parser_message=str(exc),
            code="non_json_constant",
        )
        raise JsonSyntaxRepairError(str(exc), diagnostic=diagnostic) from exc
    except json.JSONDecodeError as exc:
        parse_error = exc
        try:
            candidate, end = _decode_first_value(text, decoder)
        except (_DuplicateKeyError, _NonJSONConstantError) as strict_error:
            if isinstance(strict_error, _DuplicateKeyError):
                diagnostic = _duplicate_key_diagnostic(strict_error)
            else:
                diagnostic = JsonSyntaxDiagnostic(
                    offset=None,
                    line=None,
                    column=None,
                    parser_message=str(strict_error),
                    code="non_json_constant",
                )
            raise JsonSyntaxRepairError(
                str(strict_error), diagnostic=diagnostic
            ) from strict_error
        except json.JSONDecodeError:
            candidate = None
            end = -1

        if (
            isinstance(candidate, dict)
            and end >= 0
            and _is_one_redundant_closing_brace(text[end:])
        ):
            normalized_text = text[:end]
            return candidate, JsonSyntaxRepairReceipt.one_redundant_closing_brace(
                text, normalized_text
            )

        raise JsonSyntaxRepairError(
            parse_error.msg,
            diagnostic=_diagnostic_from_decode_error(parse_error),
        ) from parse_error

    if not isinstance(decoded, dict):
        diagnostic = JsonSyntaxDiagnostic(
            offset=None,
            line=None,
            column=None,
            parser_message="top-level JSON value must be an object",
            code="top_level_type",
        )
        raise JsonSyntaxRepairError(
            "top-level JSON value must be an object", diagnostic=diagnostic
        )

    return decoded, JsonSyntaxRepairReceipt.clean(text)


__all__ = [
    "JsonSyntaxDiagnostic",
    "JsonSyntaxRepairError",
    "JsonSyntaxRepairReceipt",
    "decode_json_object_with_repair",
]
