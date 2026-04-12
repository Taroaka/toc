"""Pure policy helpers for Kindle full-book runs.

The main runner can use these helpers to keep orchestration separate from
policy decisions:

- end-of-book detection inputs and scoring
- duplicate-page / page-skip detection across sequential page records
- retry decision scaffolding for transient failure classes

The helpers are intentionally free of I/O and runner side effects so they can be
used from the main runner, tests, or a future validation layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value).strip() or None


def _normalize_text(text: str | None) -> str | None:
    if text is None:
        return None
    compact = " ".join(text.split())
    return compact or None


@dataclass(frozen=True, slots=True)
class PageRecord:
    """Canonical page snapshot used by the policy helpers."""

    page_index: int
    kindle_page_number: int | None = None
    kindle_total_pages: int | None = None
    image_sha256: str | None = None
    vision_status: str | None = None
    vision_text: str | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PageRecord":
        return cls(
            page_index=int(raw["page_index"]),
            kindle_page_number=_as_int(raw.get("kindle_page_number")),
            kindle_total_pages=_as_int(raw.get("kindle_total_pages")),
            image_sha256=_as_str(raw.get("image_sha256")),
            vision_status=_as_str(raw.get("vision_status")),
            vision_text=_as_str(raw.get("vision_text")),
        )


@dataclass(frozen=True, slots=True)
class EndOfBookEvidence:
    """Inputs for the end-of-book policy check."""

    current_page: PageRecord
    previous_page: PageRecord | None = None
    next_button_enabled: bool | None = None
    reader_current_page: int | None = None
    reader_total_pages: int | None = None
    current_vision_text: str | None = None
    previous_vision_text: str | None = None

    @classmethod
    def from_page_records(
        cls,
        current_page: PageRecord | Mapping[str, Any],
        previous_page: PageRecord | Mapping[str, Any] | None = None,
        *,
        next_button_enabled: bool | None = None,
        reader_current_page: int | None = None,
        reader_total_pages: int | None = None,
        current_vision_text: str | None = None,
        previous_vision_text: str | None = None,
    ) -> "EndOfBookEvidence":
        current = current_page if isinstance(current_page, PageRecord) else PageRecord.from_mapping(current_page)
        previous = None
        if previous_page is not None:
            previous = previous_page if isinstance(previous_page, PageRecord) else PageRecord.from_mapping(previous_page)
        return cls(
            current_page=current,
            previous_page=previous,
            next_button_enabled=next_button_enabled,
            reader_current_page=reader_current_page,
            reader_total_pages=reader_total_pages,
            current_vision_text=current_vision_text,
            previous_vision_text=previous_vision_text,
        )


@dataclass(frozen=True, slots=True)
class EndOfBookPolicy:
    """Scoring policy for end-of-book detection."""

    min_signals_to_stop: int = 2
    allow_reader_total_pages_shortcut: bool = True


@dataclass(frozen=True, slots=True)
class EndOfBookDecision:
    """Decision result for end-of-book evaluation."""

    should_stop: bool
    triggered_signals: tuple[str, ...]
    score: int
    reason: str


def evaluate_end_of_book(
    evidence: EndOfBookEvidence | Mapping[str, Any],
    *,
    policy: EndOfBookPolicy | None = None,
) -> EndOfBookDecision:
    """Evaluate a page transition against the end-of-book policy.

    The default policy treats the following as independent signals:
    - the reader reports the current page as the final page
    - the next button is disabled
    - the Kindle page number is unchanged from the previous page
    - the page image hash is unchanged from the previous page
    - the transcription text is unchanged from the previous page
    """

    policy = policy or EndOfBookPolicy()
    if isinstance(evidence, Mapping):
        current = evidence.get("current_page")
        if not isinstance(current, PageRecord):
            current = PageRecord.from_mapping(current)
        previous = evidence.get("previous_page")
        if previous is not None and not isinstance(previous, PageRecord):
            previous = PageRecord.from_mapping(previous)
        evidence = EndOfBookEvidence(
            current_page=current,
            previous_page=previous,
            next_button_enabled=evidence.get("next_button_enabled"),
            reader_current_page=_as_int(evidence.get("reader_current_page")),
            reader_total_pages=_as_int(evidence.get("reader_total_pages")),
            current_vision_text=_as_str(evidence.get("current_vision_text")),
            previous_vision_text=_as_str(evidence.get("previous_vision_text")),
        )

    signals: list[str] = []

    if policy.allow_reader_total_pages_shortcut:
        if (
            evidence.reader_current_page is not None
            and evidence.reader_total_pages is not None
            and evidence.reader_current_page >= evidence.reader_total_pages
        ):
            signals.append("reader_reports_final_page")

    if evidence.next_button_enabled is False:
        signals.append("next_button_disabled")

    if evidence.previous_page is not None:
        if (
            evidence.current_page.kindle_page_number is not None
            and evidence.previous_page.kindle_page_number is not None
            and evidence.current_page.kindle_page_number == evidence.previous_page.kindle_page_number
        ):
            signals.append("kindle_page_unchanged")

        if (
            evidence.current_page.image_sha256 is not None
            and evidence.previous_page.image_sha256 is not None
            and evidence.current_page.image_sha256 == evidence.previous_page.image_sha256
        ):
            signals.append("image_hash_repeated")

        current_text = _normalize_text(evidence.current_vision_text or evidence.current_page.vision_text)
        previous_text = _normalize_text(evidence.previous_vision_text or evidence.previous_page.vision_text)
        if current_text and previous_text and current_text == previous_text:
            signals.append("vision_text_repeated")

    unique_signals = tuple(dict.fromkeys(signals))
    should_stop = len(unique_signals) >= max(1, policy.min_signals_to_stop)
    reason = (
        "end-of-book detected"
        if should_stop
        else "insufficient end-of-book signals"
    )
    return EndOfBookDecision(
        should_stop=should_stop,
        triggered_signals=unique_signals,
        score=len(unique_signals),
        reason=reason,
    )


@dataclass(frozen=True, slots=True)
class PageTransitionIssue:
    """A single issue detected while comparing sequential page records."""

    code: str
    message: str
    previous_page_index: int
    current_page_index: int
    previous_kindle_page_number: int | None = None
    current_kindle_page_number: int | None = None


@dataclass(frozen=True, slots=True)
class PageSequenceReport:
    """Summary of sequential page record validation."""

    issues: tuple[PageTransitionIssue, ...]

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    @property
    def has_duplicate_like_pages(self) -> bool:
        return any(
            issue.code.startswith("duplicate_") or issue.code == "repeated_image_sha256"
            for issue in self.issues
        )

    @property
    def has_page_skips(self) -> bool:
        return any(issue.code.endswith("_gap") or issue.code.endswith("_skip") for issue in self.issues)


def _ensure_page_record(record: PageRecord | Mapping[str, Any]) -> PageRecord:
    if isinstance(record, PageRecord):
        return record
    return PageRecord.from_mapping(record)


def compare_page_records(
    previous: PageRecord | Mapping[str, Any],
    current: PageRecord | Mapping[str, Any],
) -> tuple[PageTransitionIssue, ...]:
    """Compare two sequential page records and return any detected issues."""

    prev = _ensure_page_record(previous)
    curr = _ensure_page_record(current)
    issues: list[PageTransitionIssue] = []

    page_index_delta = curr.page_index - prev.page_index
    if page_index_delta != 1:
        code = "duplicate_page_index" if page_index_delta <= 0 else "page_index_gap"
        message = (
            f"expected page_index to advance by 1, got {prev.page_index} -> {curr.page_index}"
        )
        issues.append(
            PageTransitionIssue(
                code=code,
                message=message,
                previous_page_index=prev.page_index,
                current_page_index=curr.page_index,
                previous_kindle_page_number=prev.kindle_page_number,
                current_kindle_page_number=curr.kindle_page_number,
            )
        )

    if prev.kindle_page_number is not None and curr.kindle_page_number is not None:
        kindle_delta = curr.kindle_page_number - prev.kindle_page_number
        if kindle_delta != 1:
            code = "duplicate_kindle_page_number" if kindle_delta <= 0 else "kindle_page_gap"
            message = (
                "expected Kindle page number to advance by 1, "
                f"got {prev.kindle_page_number} -> {curr.kindle_page_number}"
            )
            issues.append(
                PageTransitionIssue(
                    code=code,
                    message=message,
                    previous_page_index=prev.page_index,
                    current_page_index=curr.page_index,
                    previous_kindle_page_number=prev.kindle_page_number,
                    current_kindle_page_number=curr.kindle_page_number,
                )
            )

    if prev.image_sha256 and curr.image_sha256 and prev.image_sha256 == curr.image_sha256:
        issues.append(
            PageTransitionIssue(
                code="repeated_image_sha256",
                message="page image hash repeated across sequential records",
                previous_page_index=prev.page_index,
                current_page_index=curr.page_index,
                previous_kindle_page_number=prev.kindle_page_number,
                current_kindle_page_number=curr.kindle_page_number,
            )
        )

    return tuple(issues)


def analyze_page_sequence(
    records: Sequence[PageRecord | Mapping[str, Any]],
) -> PageSequenceReport:
    """Validate a run's sequential page records."""

    page_records = [_ensure_page_record(record) for record in records]
    issues: list[PageTransitionIssue] = []
    for previous, current in zip(page_records, page_records[1:]):
        issues.extend(compare_page_records(previous, current))
    return PageSequenceReport(issues=tuple(issues))


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Policy inputs for retry scaffolding."""

    max_attempts: int = 3
    retryable_failure_kinds: tuple[str, ...] = (
        "image_export_failed",
        "vision_transcription_failed",
        "page_turn_failed",
    )
    base_delay_seconds: float = 1.5
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 15.0


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Scaffolded retry decision for a page-level failure."""

    should_retry: bool
    failure_kind: str
    attempt: int
    max_attempts: int
    delay_seconds: float
    reason: str


DEFAULT_RETRY_POLICY = RetryPolicy()


def decide_retry(
    failure_kind: str,
    *,
    attempt: int,
    policy: RetryPolicy | None = None,
) -> RetryDecision:
    """Decide whether a failure should be retried.

    `attempt` is 1-based for the current failure occurrence. The returned delay
    is a simple exponential backoff scaffold the main runner can override.
    The default retryable kinds mirror the names currently emitted by the
    full-book runner's page-level retry wrappers.
    """

    policy = policy or DEFAULT_RETRY_POLICY
    normalized_kind = _as_str(failure_kind) or "unknown"
    effective_attempt = max(1, int(attempt))

    retryable = normalized_kind in policy.retryable_failure_kinds
    within_attempt_budget = effective_attempt < max(1, policy.max_attempts)
    should_retry = retryable and within_attempt_budget

    delay_seconds = 0.0
    if should_retry:
        delay_seconds = min(
            policy.base_delay_seconds * (policy.backoff_multiplier ** (effective_attempt - 1)),
            policy.max_delay_seconds,
        )

    if not retryable:
        reason = f"failure kind `{normalized_kind}` is not retryable"
    elif not within_attempt_budget:
        reason = f"attempt {effective_attempt} reached the retry cap of {policy.max_attempts}"
    else:
        reason = f"retryable failure kind `{normalized_kind}`"

    return RetryDecision(
        should_retry=should_retry,
        failure_kind=normalized_kind,
        attempt=effective_attempt,
        max_attempts=policy.max_attempts,
        delay_seconds=delay_seconds,
        reason=reason,
    )
