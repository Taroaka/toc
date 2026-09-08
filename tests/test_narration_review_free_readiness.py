from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toc.narration_revision import (
    apply_authoring_update,
    current_audio_is_ready,
    prepare_audio_candidate,
    record_audio_candidate_result,
)
from toc.script_narration import resolve_script_cut_tts_text


def _candidate_narration() -> dict:
    narration: dict = {}
    apply_authoring_update(
        narration,
        text="帰る決意をします。",
        tts_text="かえる けついを します。",
        tool="elevenlabs",
        authoring_status="human_locked",
        source="frontend",
        expected_revision=0,
        now="2026-09-08T10:00:00+09:00",
    )
    snapshot = prepare_audio_candidate(
        narration,
        candidate_id="candidate-current",
        output="assets/audio/candidates/candidate-current.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-09-08T10:00:01+09:00",
    )
    record_audio_candidate_result(
        narration,
        snapshot=snapshot,
        succeeded=True,
        duration_seconds=5.0,
        output_sha256="sha256:" + "a" * 64,
        now="2026-09-08T10:00:06+09:00",
    )
    return narration


def test_current_candidate_is_ready_without_audio_approval_certificate() -> None:
    narration = _candidate_narration()

    assert current_audio_is_ready(narration) is True


def test_script_tts_text_does_not_use_legacy_human_review_override() -> None:
    cut = {
        "narration": "canonical narration",
        "tts_text": "canonical tts",
        "human_review": {
            "approved_narration": "obsolete narration",
            "approved_tts_text": "obsolete tts",
        },
    }

    assert resolve_script_cut_tts_text(cut) == "canonical tts"
