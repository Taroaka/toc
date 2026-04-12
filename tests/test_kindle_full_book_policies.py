import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kindle.kindle_full_book_policies import (  # noqa: E402
    DEFAULT_RETRY_POLICY,
    EndOfBookEvidence,
    EndOfBookPolicy,
    PageRecord,
    RetryPolicy,
    analyze_page_sequence,
    compare_page_records,
    decide_retry,
    evaluate_end_of_book,
)


class TestKindleFullBookPolicies(unittest.TestCase):
    def test_page_record_from_mapping_supports_run_state_shape(self) -> None:
        record = PageRecord.from_mapping(
            {
                "page_index": 7,
                "kindle_page_number": 42,
                "kindle_total_pages": 300,
                "image_sha256": "abc123",
                "vision_status": "completed",
                "vision_text": "mapped page text",
            }
        )

        self.assertEqual(record.page_index, 7)
        self.assertEqual(record.kindle_page_number, 42)
        self.assertEqual(record.kindle_total_pages, 300)
        self.assertEqual(record.image_sha256, "abc123")
        self.assertEqual(record.vision_status, "completed")
        self.assertEqual(record.vision_text, "mapped page text")

    def test_end_of_book_decision_uses_multiple_signals(self) -> None:
        previous = PageRecord(
            page_index=3,
            kindle_page_number=120,
            kindle_total_pages=120,
            image_sha256="abc123",
            vision_text="final page text",
        )
        current = PageRecord(
            page_index=4,
            kindle_page_number=120,
            kindle_total_pages=120,
            image_sha256="abc123",
            vision_text="final page text",
        )
        evidence = EndOfBookEvidence.from_page_records(
            current,
            previous,
            next_button_enabled=False,
            reader_current_page=120,
            reader_total_pages=120,
        )

        decision = evaluate_end_of_book(evidence, policy=EndOfBookPolicy(min_signals_to_stop=2))

        self.assertTrue(decision.should_stop)
        self.assertIn("reader_reports_final_page", decision.triggered_signals)
        self.assertIn("next_button_disabled", decision.triggered_signals)
        self.assertGreaterEqual(decision.score, 2)

    def test_evaluate_end_of_book_accepts_mapping_inputs(self) -> None:
        decision = evaluate_end_of_book(
            {
                "current_page": {
                    "page_index": 5,
                    "kindle_page_number": 99,
                    "kindle_total_pages": 99,
                    "image_sha256": "same-image",
                    "vision_status": "completed",
                },
                "previous_page": {
                    "page_index": 4,
                    "kindle_page_number": 99,
                    "kindle_total_pages": 99,
                    "image_sha256": "same-image",
                    "vision_status": "completed",
                },
                "next_button_enabled": False,
                "reader_current_page": 99,
                "reader_total_pages": 99,
                "current_vision_text": "final page text",
                "previous_vision_text": " final   page text ",
            },
            policy=EndOfBookPolicy(min_signals_to_stop=2),
        )

        self.assertTrue(decision.should_stop)
        self.assertIn("next_button_disabled", decision.triggered_signals)
        self.assertIn("kindle_page_unchanged", decision.triggered_signals)
        self.assertIn("image_hash_repeated", decision.triggered_signals)
        self.assertIn("vision_text_repeated", decision.triggered_signals)

    def test_page_sequence_analysis_detects_duplicate_and_skip_signals(self) -> None:
        records = [
            PageRecord(page_index=1, kindle_page_number=10, image_sha256="a", vision_status="completed"),
            PageRecord(page_index=2, kindle_page_number=11, image_sha256="b", vision_status="completed"),
            PageRecord(page_index=4, kindle_page_number=13, image_sha256="b", vision_status="completed"),
            PageRecord(page_index=4, kindle_page_number=13, image_sha256="c", vision_status="completed"),
        ]

        report = analyze_page_sequence(records)
        duplicate_like = [issue for issue in report.issues if issue.code in {"duplicate_page_index", "duplicate_kindle_page_number", "repeated_image_sha256"}]
        skip_like = [issue for issue in report.issues if issue.code in {"page_index_gap", "kindle_page_gap"}]

        self.assertTrue(report.has_issues)
        self.assertTrue(report.has_duplicate_like_pages)
        self.assertTrue(report.has_page_skips)
        self.assertGreaterEqual(len(duplicate_like), 1)
        self.assertGreaterEqual(len(skip_like), 1)

        pair_issues = compare_page_records(records[2], records[3])
        self.assertTrue(any(issue.code == "duplicate_page_index" for issue in pair_issues))
        self.assertTrue(any(issue.code == "duplicate_kindle_page_number" for issue in pair_issues))

    def test_page_sequence_analysis_accepts_mapping_inputs(self) -> None:
        records = [
            {
                "page_index": 1,
                "kindle_page_number": 10,
                "kindle_total_pages": 200,
                "image_sha256": "hash-a",
                "vision_status": "completed",
            },
            {
                "page_index": 3,
                "kindle_page_number": 12,
                "kindle_total_pages": 200,
                "image_sha256": "hash-b",
                "vision_status": "completed",
            },
            {
                "page_index": 3,
                "kindle_page_number": 12,
                "kindle_total_pages": 200,
                "image_sha256": "hash-b",
                "vision_status": "completed",
            },
        ]

        report = analyze_page_sequence(records)

        self.assertTrue(report.has_issues)
        self.assertTrue(report.has_duplicate_like_pages)
        self.assertTrue(report.has_page_skips)
        self.assertTrue(any(issue.code == "page_index_gap" for issue in report.issues))
        self.assertTrue(any(issue.code == "kindle_page_gap" for issue in report.issues))
        self.assertTrue(any(issue.code == "duplicate_page_index" for issue in report.issues))
        self.assertTrue(any(issue.code == "duplicate_kindle_page_number" for issue in report.issues))
        self.assertTrue(any(issue.code == "repeated_image_sha256" for issue in report.issues))

        pair_issues = compare_page_records(records[1], records[2])
        self.assertTrue(any(issue.code == "duplicate_page_index" for issue in pair_issues))
        self.assertTrue(any(issue.code == "duplicate_kindle_page_number" for issue in pair_issues))
        self.assertTrue(any(issue.code == "repeated_image_sha256" for issue in pair_issues))

    def test_retry_decision_scaffolding_respects_policy(self) -> None:
        retryable = decide_retry("vision_transcription_failed", attempt=1)
        capped = decide_retry("vision_transcription_failed", attempt=3, policy=RetryPolicy(max_attempts=3))
        no_longer_retryable = decide_retry("reader_lost", attempt=1, policy=DEFAULT_RETRY_POLICY)
        non_retryable = decide_retry("unexpected_parser_error", attempt=1, policy=DEFAULT_RETRY_POLICY)

        self.assertTrue(retryable.should_retry)
        self.assertGreater(retryable.delay_seconds, 0.0)
        self.assertFalse(capped.should_retry)
        self.assertIn("retry cap", capped.reason)
        self.assertFalse(no_longer_retryable.should_retry)
        self.assertIn("not retryable", no_longer_retryable.reason)
        self.assertFalse(non_retryable.should_retry)
        self.assertIn("not retryable", non_retryable.reason)


if __name__ == "__main__":
    unittest.main()
