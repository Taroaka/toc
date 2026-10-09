import hashlib
import json

import pytest

from toc.candidate_notes import CandidateNotesError, add_note, load_notes


def _add(tmp_path, *, revision=0, candidate="candidate.png", digest=None, **overrides):
    path = tmp_path / candidate
    digest = digest or (hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "0" * 64)
    args = {
        "root": tmp_path,
        "item_id": "scene_1",
        "kind": "image",
        "candidate_path": candidate,
        "candidate_sha256": digest,
        "expected_revision": revision,
        "disposition": "undecided",
        "problem": "face differs",
        "change": "preserve eyes",
        "result": "needs another pass",
        "request_revision": "req-1",
    }
    args.update(overrides)
    return add_note(**args)


def test_notes_append_with_global_revision_and_exact_byte_binding(tmp_path):
    candidate = tmp_path / "candidate.png"
    candidate.write_bytes(b"candidate bytes")
    result = _add(tmp_path)
    assert result["schema_version"] == "candidate_notes_v1"
    assert result["revision"] == 1
    entry = result["entries"][0]
    assert entry["candidate_sha256"] == hashlib.sha256(candidate.read_bytes()).hexdigest()
    assert entry["is_stale"] is False
    result = _add(tmp_path, revision=1, disposition="keep")
    assert result["revision"] == 2
    persisted = json.loads((tmp_path / "candidate_notes.json").read_text())
    assert len(persisted["entries"]) == 2
    assert "is_stale" not in persisted["entries"][0]


def test_load_reports_missing_or_replaced_candidate_as_stale_without_erasing_note(tmp_path):
    candidate = tmp_path / "candidate.png"
    candidate.write_bytes(b"before")
    _add(tmp_path)
    candidate.write_bytes(b"after")
    notes = load_notes(tmp_path, "scene_1")
    assert notes["revision"] == 1
    assert notes["entries"][0]["is_stale"] is True
    assert len(json.loads((tmp_path / "candidate_notes.json").read_text())["entries"]) == 1
    candidate.unlink()
    assert load_notes(tmp_path)["entries"][0]["is_stale"] is True


def test_revision_conflict_stale_hash_and_unsafe_path_are_rejected(tmp_path):
    (tmp_path / "candidate.png").write_bytes(b"candidate")
    _add(tmp_path)
    with pytest.raises(CandidateNotesError, match="revision conflict"):
        _add(tmp_path, revision=0)
    with pytest.raises(CandidateNotesError, match="does not match"):
        _add(tmp_path, revision=1, digest="0" * 64)
    with pytest.raises(CandidateNotesError, match="run-relative"):
        _add(tmp_path, revision=1, candidate="../outside.png")


def test_rejects_symlink_candidate_path(tmp_path):
    target = tmp_path / "actual.png"
    target.write_bytes(b"candidate")
    (tmp_path / "candidate.png").symlink_to(target)
    with pytest.raises(CandidateNotesError, match="symlinks"):
        _add(tmp_path)


def test_load_rejects_malformed_entry_shape_clearly(tmp_path):
    (tmp_path / "candidate.png").write_bytes(b"candidate")
    _add(tmp_path)
    document = json.loads((tmp_path / "candidate_notes.json").read_text())
    document["entries"] = ["not an observation"]
    (tmp_path / "candidate_notes.json").write_text(json.dumps(document))
    with pytest.raises(CandidateNotesError, match="must be an object"):
        load_notes(tmp_path)


def test_notes_document_symlink_is_rejected(tmp_path):
    target = tmp_path / "other.json"
    target.write_text('{"schema_version":"candidate_notes_v1","revision":0,"entries":[]}')
    (tmp_path / "candidate_notes.json").symlink_to(target)
    with pytest.raises(CandidateNotesError, match="symlinks|unsafe"):
        load_notes(tmp_path)
