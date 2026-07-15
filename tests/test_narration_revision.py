from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toc.narration_revision import (
    NarrationRevisionConflict,
    apply_authoring_update,
    approve_audio_candidate,
    current_audio_is_human_approved,
    prepare_audio_candidate,
    record_audio_candidate_result,
)


def _authored_narration() -> dict:
    narration: dict = {}
    apply_authoring_update(
        narration,
        text="浦島太郎は、帰る決意をします。",
        tts_text="うらしまたろうは、かえる けついを します。",
        tool="elevenlabs",
        authoring_status="human_locked",
        source="frontend",
        expected_revision=0,
        now="2026-07-11T10:00:00+09:00",
    )
    return narration


def _approved_narration() -> dict:
    narration = _authored_narration()
    snapshot = prepare_audio_candidate(
        narration,
        candidate_id="candidate-approved",
        output="assets/audio/candidates/candidate-approved.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:00:10+09:00",
    )
    record_audio_candidate_result(
        narration,
        snapshot=snapshot,
        succeeded=True,
        duration_seconds=7.2,
        output_sha256="sha256:" + "a" * 64,
        now="2026-07-11T10:00:17+09:00",
    )
    approve_audio_candidate(
        narration,
        candidate_id="candidate-approved",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:00:20+09:00",
    )
    return narration


def test_authoring_update_creates_hash_bound_revision_without_collapsing_public_text() -> None:
    narration = _authored_narration()

    assert narration["text"] == "浦島太郎は、帰る決意をします。"
    assert narration["tts_text"] == "うらしまたろうは、かえる けついを します。"
    assert narration["authoring_status"] == "human_locked"
    assert narration["revision"]["number"] == 1
    assert narration["revision"]["text_revision"] == 1
    assert narration["revision"]["tts_revision"] == 1
    assert narration["revision"]["text_hash"].startswith("sha256:")
    assert len(narration["revision"]["text_hash"]) == 71
    assert narration["revision"]["tts_hash"].startswith("sha256:")
    assert narration["review"]["status"] == "pending"
    assert narration["review"]["human_review_ok"] is False


def test_idempotent_save_does_not_bump_revision() -> None:
    narration = _authored_narration()
    before = deepcopy(narration["revision"])

    changed = apply_authoring_update(
        narration,
        text=narration["text"],
        tts_text=narration["tts_text"],
        tool="elevenlabs",
        authoring_status="human_locked",
        source="frontend",
        expected_revision=1,
        now="2026-07-11T10:01:00+09:00",
    )

    assert changed is False
    assert narration["revision"] == before


def test_source_only_save_is_idempotent_and_does_not_bump_revision() -> None:
    narration = _authored_narration()
    before = deepcopy(narration)

    changed = apply_authoring_update(
        narration,
        text=narration["text"],
        tts_text=narration["tts_text"],
        tool=narration["tool"],
        authoring_status=narration["authoring_status"],
        source="script_sync",
        expected_revision=1,
        now="2026-07-11T10:01:30+09:00",
    )

    assert changed is False
    assert narration == before


def test_revision_conflict_rejects_stale_frontend_save() -> None:
    narration = _authored_narration()

    with pytest.raises(NarrationRevisionConflict):
        apply_authoring_update(
            narration,
            text="古いタブからの変更",
            tts_text="ふるい たぶからの へんこう",
            tool="elevenlabs",
            authoring_status="draft",
            source="frontend",
            expected_revision=0,
            now="2026-07-11T10:02:00+09:00",
        )


def test_matching_generation_result_is_candidate_and_never_human_review_override() -> None:
    narration = _authored_narration()
    snapshot = prepare_audio_candidate(
        narration,
        candidate_id="candidate-a",
        output="assets/audio/candidates/candidate-a.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:03:00+09:00",
    )

    status = record_audio_candidate_result(
        narration,
        snapshot=snapshot,
        succeeded=True,
        duration_seconds=8.4,
        output_sha256="sha256:" + "a" * 64,
        now="2026-07-11T10:03:08+09:00",
    )

    assert status == "candidate"
    assert narration["generation"]["status"] == "candidate"
    assert narration["status"] == "candidate"
    assert narration.get("output", "") == ""
    assert narration["review"]["human_review_ok"] is False
    assert current_audio_is_human_approved(narration) is False


def test_completion_from_old_hash_is_retained_as_stale_without_replacing_current_state() -> None:
    narration = _authored_narration()
    old_snapshot = prepare_audio_candidate(
        narration,
        candidate_id="candidate-old",
        output="assets/audio/candidates/candidate-old.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:04:00+09:00",
    )
    apply_authoring_update(
        narration,
        text="浦島太郎は、それでも帰る決意をします。",
        tts_text="うらしまたろうは、それでも かえる けついを します。",
        tool="elevenlabs",
        authoring_status="human_locked",
        source="frontend",
        expected_revision=1,
        now="2026-07-11T10:04:01+09:00",
    )

    status = record_audio_candidate_result(
        narration,
        snapshot=old_snapshot,
        succeeded=True,
        duration_seconds=8.8,
        output_sha256="sha256:" + "b" * 64,
        now="2026-07-11T10:04:09+09:00",
    )

    assert status == "stale"
    old = next(candidate for candidate in narration["candidates"] if candidate["candidate_id"] == "candidate-old")
    assert old["status"] == "stale"
    assert narration.get("output", "") == ""
    assert narration["revision"]["number"] == 2
    assert current_audio_is_human_approved(narration) is False


def test_only_current_locked_candidate_can_be_human_approved() -> None:
    narration = _authored_narration()
    snapshot = prepare_audio_candidate(
        narration,
        candidate_id="candidate-current",
        output="assets/audio/candidates/candidate-current.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:05:00+09:00",
    )
    record_audio_candidate_result(
        narration,
        snapshot=snapshot,
        succeeded=True,
        duration_seconds=7.2,
        output_sha256="sha256:" + "c" * 64,
        now="2026-07-11T10:05:07+09:00",
    )

    approved = approve_audio_candidate(
        narration,
        candidate_id="candidate-current",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:06:00+09:00",
    )

    assert approved["output"] == "assets/audio/candidates/candidate-current.mp3"
    assert narration["status"] == "audio_ready"
    assert narration["generation"]["status"] == "human_approved"
    assert narration["audio_review"]["status"] == "approved"
    assert narration["review"]["human_review_ok"] is False
    assert current_audio_is_human_approved(narration) is True


def test_preview_candidate_remains_approvable_when_same_text_is_later_locked() -> None:
    narration: dict = {}
    apply_authoring_update(
        narration,
        text="先に試聴する文面です。",
        tts_text="さきに しちょうする ぶんめんです。",
        tool="elevenlabs",
        authoring_status="draft",
        source="frontend",
        expected_revision=0,
        now="2026-07-11T10:06:10+09:00",
    )
    snapshot = prepare_audio_candidate(
        narration,
        candidate_id="candidate-preview",
        output="assets/audio/candidates/candidate-preview.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:06:20+09:00",
    )
    record_audio_candidate_result(
        narration,
        snapshot=snapshot,
        succeeded=True,
        duration_seconds=6.0,
        output_sha256="sha256:" + "f" * 64,
        now="2026-07-11T10:06:26+09:00",
    )

    apply_authoring_update(
        narration,
        text=narration["text"],
        tts_text=narration["tts_text"],
        tool="elevenlabs",
        authoring_status="human_locked",
        source="frontend",
        expected_revision=1,
        now="2026-07-11T10:06:30+09:00",
    )
    approved = approve_audio_candidate(
        narration,
        candidate_id="candidate-preview",
        expected_revision=2,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:06:40+09:00",
    )

    assert approved["status"] == "human_approved"
    assert current_audio_is_human_approved(narration) is True


def test_text_edit_after_audio_approval_reopens_workflow_and_keeps_old_file_as_stale_candidate() -> None:
    narration = _authored_narration()
    snapshot = prepare_audio_candidate(
        narration,
        candidate_id="candidate-approved",
        output="assets/audio/candidates/candidate-approved.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:07:00+09:00",
    )
    record_audio_candidate_result(
        narration,
        snapshot=snapshot,
        succeeded=True,
        duration_seconds=7.2,
        output_sha256="sha256:" + "d" * 64,
        now="2026-07-11T10:07:07+09:00",
    )
    approve_audio_candidate(
        narration,
        candidate_id="candidate-approved",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:08:00+09:00",
    )

    apply_authoring_update(
        narration,
        text="帰る決意は、もう揺らぎません。",
        tts_text="かえる けついは、もう ゆらぎません。",
        tool="elevenlabs",
        authoring_status="draft",
        source="frontend",
        expected_revision=1,
        now="2026-07-11T10:09:00+09:00",
    )

    candidate = narration["candidates"][0]
    assert candidate["status"] == "stale"
    assert narration["status"] == "stale"
    assert narration["generation"]["status"] == "stale"
    assert narration["audio_review"]["status"] == "pending"
    assert narration["output"] == ""
    assert current_audio_is_human_approved(narration) is False


def test_stale_candidate_cannot_be_approved() -> None:
    narration = _authored_narration()
    snapshot = prepare_audio_candidate(
        narration,
        candidate_id="candidate-old",
        output="assets/audio/candidates/candidate-old.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:10:00+09:00",
    )
    apply_authoring_update(
        narration,
        text="新しい意味原稿です。",
        tts_text="あたらしい いみげんこうです。",
        tool="elevenlabs",
        authoring_status="human_locked",
        source="frontend",
        expected_revision=1,
        now="2026-07-11T10:10:01+09:00",
    )
    record_audio_candidate_result(
        narration,
        snapshot=snapshot,
        succeeded=True,
        duration_seconds=5.0,
        output_sha256="sha256:" + "e" * 64,
        now="2026-07-11T10:10:05+09:00",
    )

    with pytest.raises(NarrationRevisionConflict):
        approve_audio_candidate(
            narration,
            candidate_id="candidate-old",
            expected_revision=2,
            expected_tts_hash=narration["revision"]["tts_hash"],
            now="2026-07-11T10:11:00+09:00",
        )


@pytest.mark.parametrize(
    "mutate_flat_field",
    [
        lambda narration: narration.__setitem__("text", "revision を通さない改変"),
        lambda narration: narration.__setitem__("tts_text", "りびじょんを とおさない かいへん"),
        lambda narration: narration.__setitem__("tool", "silent"),
        lambda narration: narration.__setitem__("voice_id", "different-voice"),
    ],
    ids=["text", "tts_text", "tool", "delivery"],
)
def test_flat_field_hash_drift_invalidates_human_approved_audio(mutate_flat_field) -> None:
    narration = _approved_narration()
    mutate_flat_field(narration)

    assert current_audio_is_human_approved(narration) is False


def test_prepare_candidate_rejects_flat_field_hash_drift() -> None:
    narration = _authored_narration()
    narration["voice_settings"] = {"stability": 0.1}

    with pytest.raises(NarrationRevisionConflict, match="hash drift"):
        prepare_audio_candidate(
            narration,
            candidate_id="candidate-drifted",
            output="assets/audio/candidates/candidate-drifted.mp3",
            expected_revision=1,
            expected_tts_hash=narration["revision"]["tts_hash"],
            now="2026-07-11T10:12:00+09:00",
        )

    assert narration["candidates"] == []


def test_record_candidate_marks_result_stale_after_flat_field_hash_drift() -> None:
    narration = _authored_narration()
    snapshot = prepare_audio_candidate(
        narration,
        candidate_id="candidate-drifted",
        output="assets/audio/candidates/candidate-drifted.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:13:00+09:00",
    )
    narration["tts_text"] = "生成中に直接改変された読み"

    status = record_audio_candidate_result(
        narration,
        snapshot=snapshot,
        succeeded=True,
        duration_seconds=4.2,
        output_sha256="sha256:" + "b" * 64,
        now="2026-07-11T10:13:05+09:00",
    )

    assert status == "stale"
    assert narration["candidates"][0]["status"] == "stale"
    assert narration["generation"]["status"] == "stale"


def test_approve_candidate_rejects_flat_field_hash_drift() -> None:
    narration = _authored_narration()
    snapshot = prepare_audio_candidate(
        narration,
        candidate_id="candidate-drifted",
        output="assets/audio/candidates/candidate-drifted.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:14:00+09:00",
    )
    record_audio_candidate_result(
        narration,
        snapshot=snapshot,
        succeeded=True,
        duration_seconds=4.2,
        output_sha256="sha256:" + "c" * 64,
        now="2026-07-11T10:14:05+09:00",
    )
    narration["elevenlabs_prompt"] = {"style": "whispered"}

    with pytest.raises(NarrationRevisionConflict, match="hash drift"):
        approve_audio_candidate(
            narration,
            candidate_id="candidate-drifted",
            expected_revision=1,
            expected_tts_hash=narration["revision"]["tts_hash"],
            now="2026-07-11T10:14:10+09:00",
        )


def test_status_only_revision_change_keeps_matching_approved_audio_current() -> None:
    narration = _approved_narration()

    changed = apply_authoring_update(
        narration,
        text=narration["text"],
        tts_text=narration["tts_text"],
        tool=narration["tool"],
        authoring_status="reviewed",
        source="review_ui",
        expected_revision=1,
        now="2026-07-11T10:15:00+09:00",
    )

    assert changed is True
    assert narration["revision"]["number"] == 2
    assert narration["audio_review"]["approved_revision"] == 1
    assert current_audio_is_human_approved(narration) is True


def test_provenance_only_revision_number_change_keeps_matching_approved_audio_current() -> None:
    narration = _approved_narration()
    narration["revision"]["number"] += 1
    narration["revision"]["source"] = "migration"
    narration["revision"]["updated_at"] = "2026-07-11T10:16:00+09:00"

    assert current_audio_is_human_approved(narration) is True


def test_approved_audio_is_bound_to_candidate_hashes_and_output() -> None:
    narration = _approved_narration()
    candidate = narration["candidates"][0]
    candidate["generated_from_tts_hash"] = "sha256:" + "0" * 64

    assert current_audio_is_human_approved(narration) is False

    candidate["generated_from_tts_hash"] = narration["revision"]["tts_hash"]
    narration["output"] = "assets/audio/candidates/a-different-file.mp3"

    assert current_audio_is_human_approved(narration) is False


def test_regeneration_keeps_current_approval_until_new_candidate_is_explicitly_approved() -> None:
    narration = _approved_narration()
    approved_output = narration["output"]
    approved_id = narration["audio_review"]["approved_candidate_id"]
    failed_snapshot = prepare_audio_candidate(
        narration,
        candidate_id="retry-failed",
        output="assets/audio/candidates/retry-failed.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:16:00+09:00",
    )

    assert current_audio_is_human_approved(narration) is True
    assert narration["output"] == approved_output
    assert narration["candidates"][0]["status"] == "human_approved"

    record_audio_candidate_result(
        narration,
        snapshot=failed_snapshot,
        succeeded=False,
        duration_seconds=None,
        output_sha256="",
        now="2026-07-11T10:16:05+09:00",
    )
    assert current_audio_is_human_approved(narration) is True
    assert narration["status"] == "audio_ready"

    replacement_snapshot = prepare_audio_candidate(
        narration,
        candidate_id="retry-current",
        output="assets/audio/candidates/retry-current.mp3",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:16:10+09:00",
    )
    record_audio_candidate_result(
        narration,
        snapshot=replacement_snapshot,
        succeeded=True,
        duration_seconds=4.3,
        output_sha256="sha256:" + "d" * 64,
        now="2026-07-11T10:16:15+09:00",
    )

    assert current_audio_is_human_approved(narration) is True
    assert narration["audio_review"]["approved_candidate_id"] == approved_id

    approve_audio_candidate(
        narration,
        candidate_id="retry-current",
        expected_revision=1,
        expected_tts_hash=narration["revision"]["tts_hash"],
        now="2026-07-11T10:16:20+09:00",
    )
    assert narration["candidates"][0]["status"] == "superseded"
    assert narration["audio_review"]["approved_candidate_id"] == "retry-current"
    assert narration["output"] == "assets/audio/candidates/retry-current.mp3"

def test_downgrade_to_draft_explicitly_unlocks_approved_audio() -> None:
    narration = _approved_narration()

    apply_authoring_update(
        narration,
        text=narration["text"],
        tts_text=narration["tts_text"],
        tool=narration["tool"],
        authoring_status="draft",
        source="frontend",
        expected_revision=1,
        now="2026-07-11T10:17:00+09:00",
    )

    assert narration["output"] == ""
    assert narration["audio_review"]["status"] == "pending"
    assert narration["candidates"][0]["status"] == "candidate"
    assert current_audio_is_human_approved(narration) is False
