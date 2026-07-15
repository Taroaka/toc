from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch

import yaml

from toc.harness import load_structured_document, parse_state_file
from toc.narration_arc import narration_text_set_hash
from toc.narration_revision import apply_authoring_update, ensure_narration_revision
from toc.narration_semantic_review import (
    RESPONSE_SCHEMA_VERSION,
    SEMANTIC_CRITIC_PROFILES,
    aggregate_narration_critic_results,
    build_narration_semantic_review_pack,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts" / "run-p720-narration-semantic.py"


def _load_runner_module():
    module_name = "toc_test_run_p720_narration_semantic"
    spec = importlib.util.spec_from_file_location(module_name, RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner_module()


def _write_manifest(path: Path, data: dict[str, Any]) -> None:
    dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000)
    path.write_text(f"```yaml\n{dumped}```\n", encoding="utf-8")


def _write_revision_aware_run(run_dir: Path) -> tuple[Path, str, str]:
    run_dir.mkdir(parents=True)
    narration: dict[str, Any] = {
        "text": "主人公は迷いを抱えたまま、浜辺で足を止めます。",
        "tts_text": "主人公は迷いを抱えたまま、浜辺で足を止めます。",
        "tool": "elevenlabs",
        "authoring_status": "human_locked",
        "output": "",
        "review": {
            "agent_review_ok": True,
            "human_review_ok": False,
        },
    }
    ensure_narration_revision(narration)
    data: dict[str, Any] = {
        "scenes": [
            {
                "scene_id": 10,
                "cuts": [
                    {
                        "cut_id": 1,
                        "audio": {"narration": narration},
                    }
                ],
            }
        ]
    }
    text_set_hash = narration_text_set_hash(data)
    data["narration_workflow"] = {
        "schema_version": "narration_run_workflow_v1",
        "arc_review": {
            "status": "passed",
            "narration_text_set_hash": text_set_hash,
            "findings": [],
            "report": "narration_text_review.md",
        },
    }
    manifest_path = run_dir / "video_manifest.md"
    _write_manifest(manifest_path, data)
    (run_dir / "state.txt").write_text(
        "job_id=JOB_2026-07-11_000000\n"
        "status=NARRATION\n"
        "slot.p720.status=in_progress\n"
        "slot.p730.status=pending\n"
        "slot.p740.status=pending\n"
        "slot.p750.status=pending\n"
        "---\n",
        encoding="utf-8",
    )
    input_hash = str(build_narration_semantic_review_pack(data)["semantic_review_input_hash"])
    return manifest_path, text_set_hash, input_hash


def _aggregate(
    text_set_hash: str,
    input_hash: str,
    *,
    status: str,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw_findings = findings or []
    critic_finding = (
        {
            key: value
            for key, value in raw_findings[0].items()
            if key not in {"critic_id", "critic_label"}
        }
        if raw_findings
        else None
    )
    critics: list[dict[str, Any]] = []
    for profile in SEMANTIC_CRITIC_PROFILES:
        critic_status = status if profile.critic_id == "retention_hook" else "passed"
        critic_findings = [critic_finding] if critic_finding and profile.critic_id == "retention_hook" else []
        critics.append(
            {
                "schema_version": RESPONSE_SCHEMA_VERSION,
                "critic_id": profile.critic_id,
                "narration_text_set_hash": text_set_hash,
                "semantic_review_input_hash": input_hash,
                "status": critic_status,
                "summary": "物語全体を通した評価です。",
                "findings": critic_findings,
            }
        )
    return aggregate_narration_critic_results(
        critics,
        text_set_hash=text_set_hash,
        semantic_review_input_hash=input_hash,
        reviewed_at="2026-07-11T12:00:00+09:00",
    )


def test_runner_persists_hash_bound_pass_and_artifacts_after_current_arc_review(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    manifest_path, expected_hash, expected_input_hash = _write_revision_aware_run(run_dir)

    async def fake_critics(
        supplied_run_dir: Path,
        snapshot: dict[str, Any],
        *,
        expected_narration_text_set_hash: str,
        expected_semantic_review_input_hash: str,
        timeout_seconds: int,
        max_concurrency: int,
    ) -> dict[str, Any]:
        assert supplied_run_dir == run_dir
        assert narration_text_set_hash(snapshot) == expected_hash
        assert expected_narration_text_set_hash == expected_hash
        assert expected_semantic_review_input_hash == expected_input_hash
        assert timeout_seconds == 77
        assert max_concurrency == 2
        return _aggregate(expected_hash, expected_input_hash, status="passed")

    with patch.object(RUNNER, "run_narration_semantic_critics", side_effect=fake_critics):
        status = asyncio.run(
            RUNNER.run_semantic_review(
                run_dir=run_dir,
                manifest_path=manifest_path,
                timeout_seconds=77,
                max_concurrency=2,
            )
        )

    _, persisted = load_structured_document(manifest_path)
    record = persisted["narration_workflow"]["semantic_critic_review"]
    state = parse_state_file(run_dir / "state.txt")

    assert status == "passed"
    assert record["status"] == "passed"
    assert record["narration_text_set_hash"] == expected_hash
    assert record["semantic_review_input_hash"] == expected_input_hash
    assert record["schema_version"] == "narration_semantic_critic_aggregate_v1"
    assert record["report"].startswith("logs/eval/narration/semantic_critics/")
    assert record["json"].startswith("logs/eval/narration/semantic_critics/")
    assert "status: passed" in (run_dir / record["report"]).read_text(encoding="utf-8")
    assert json.loads((run_dir / record["json"]).read_text(encoding="utf-8"))["narration_text_set_hash"] == expected_hash
    assert (run_dir / "logs/eval/narration/semantic_critics/latest.md").is_file()
    assert (run_dir / "logs/eval/narration/semantic_critics/latest.json").is_file()
    assert state["slot.p720.status"] == "done"
    assert state["review.narration.status"] == "approved"
    assert state["review.narration.semantic_critics.status"] == "passed"
    assert state["review.narration.semantic_critics.text_set_hash"] == expected_hash
    assert state["review.narration.semantic_critics.input_hash"] == expected_input_hash


def test_runner_persists_changes_requested_and_blocks_downstream_stages(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    manifest_path, expected_hash, expected_input_hash = _write_revision_aware_run(run_dir)
    findings = [
        {
            "critic_id": "retention_hook",
            "code": "opening_promise_is_vague",
            "severity": "blocking",
            "message": "冒頭で続きを聞く理由が立ち上がっていません。",
            "evidence": ["scene10_cut1"],
            "suggestion": "具体的な未解決の問いを置いてください。",
        }
    ]

    async def fake_critics(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return _aggregate(
            expected_hash,
            expected_input_hash,
            status="changes_requested",
            findings=findings,
        )

    with patch.object(RUNNER, "run_narration_semantic_critics", side_effect=fake_critics):
        status = asyncio.run(
            RUNNER.run_semantic_review(
                run_dir=run_dir,
                manifest_path=manifest_path,
                timeout_seconds=60,
                max_concurrency=3,
            )
        )

    _, persisted = load_structured_document(manifest_path)
    record = persisted["narration_workflow"]["semantic_critic_review"]
    state = parse_state_file(run_dir / "state.txt")

    assert status == "changes_requested"
    assert record["status"] == "changes_requested"
    assert record["narration_text_set_hash"] == expected_hash
    assert record["semantic_review_input_hash"] == expected_input_hash
    assert record["findings"][0]["critic_id"] == "retention_hook"
    assert record["findings"][0]["code"] == findings[0]["code"]
    assert state["slot.p720.status"] == "blocked"
    assert state["slot.p730.status"] == "blocked"
    assert state["slot.p740.status"] == "blocked"
    assert state["slot.p750.status"] == "blocked"
    assert state["stage.narration.status"] == "in_progress"
    assert state["review.narration.status"] == "changes_requested"
    assert state["review.narration.semantic_critics.status"] == "changes_requested"


def test_runner_cannot_mark_p720_done_when_cut_local_deterministic_review_is_blocked(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    manifest_path, expected_hash, expected_input_hash = _write_revision_aware_run(run_dir)
    original, manifest = load_structured_document(manifest_path)
    manifest["scenes"][0]["cuts"][0]["audio"]["narration"]["review"] = {
        "agent_review_ok": False,
        "human_review_ok": True,
        "human_review_reason": "",
    }
    RUNNER._atomic_write(manifest_path, RUNNER._replace_yaml_block(original, manifest))

    async def fake_critics(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return _aggregate(expected_hash, expected_input_hash, status="passed")

    with patch.object(RUNNER, "run_narration_semantic_critics", side_effect=fake_critics):
        status = asyncio.run(
            RUNNER.run_semantic_review(
                run_dir=run_dir,
                manifest_path=manifest_path,
                timeout_seconds=60,
                max_concurrency=3,
            )
        )

    _, persisted = load_structured_document(manifest_path)
    state = parse_state_file(run_dir / "state.txt")
    assert status == "changes_requested"
    assert persisted["narration_workflow"]["semantic_critic_review"]["status"] == "passed"
    assert state["slot.p720.status"] == "blocked"
    assert state["review.narration.status"] == "changes_requested"


def test_runner_marks_result_stale_when_narration_changes_during_critic_execution(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    manifest_path, expected_hash, expected_input_hash = _write_revision_aware_run(run_dir)

    async def fake_critics(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        original, edited = load_structured_document(manifest_path)
        narration = edited["scenes"][0]["cuts"][0]["audio"]["narration"]
        apply_authoring_update(
            narration,
            text="主人公は波音を聞き、浜辺から歩き出します。",
            tts_text="主人公は波音を聞き、浜辺から歩き出します。",
            tool="elevenlabs",
            authoring_status="human_locked",
            source="frontend",
            expected_revision=int(narration["revision"]["number"]),
            now="2026-07-11T12:01:00+09:00",
        )
        RUNNER._atomic_write(manifest_path, RUNNER._replace_yaml_block(original, edited))
        return _aggregate(expected_hash, expected_input_hash, status="passed")

    with patch.object(RUNNER, "run_narration_semantic_critics", side_effect=fake_critics):
        status = asyncio.run(
            RUNNER.run_semantic_review(
                run_dir=run_dir,
                manifest_path=manifest_path,
                timeout_seconds=60,
                max_concurrency=3,
            )
        )

    _, persisted = load_structured_document(manifest_path)
    current_hash = narration_text_set_hash(persisted)
    state = parse_state_file(run_dir / "state.txt")
    review_dir = run_dir / "logs" / "eval" / "narration" / "semantic_critics"

    assert status == "stale"
    assert current_hash != expected_hash
    assert persisted["scenes"][0]["cuts"][0]["audio"]["narration"]["text"].endswith("歩き出します。")
    assert "semantic_critic_review" not in persisted["narration_workflow"]
    assert not review_dir.exists()
    assert state["runtime.stage"] == "narration_semantic_critics_stale"
    assert state["slot.p720.status"] == "in_progress"
    assert state["review.narration.semantic_critics.status"] == "stale"
    assert state["review.narration.semantic_critics.text_set_hash"] == expected_hash


def test_runner_marks_result_stale_when_visual_context_changes_but_text_does_not(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    manifest_path, expected_hash, expected_input_hash = _write_revision_aware_run(run_dir)

    async def fake_critics(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        original, edited = load_structured_document(manifest_path)
        edited["scenes"][0]["cuts"][0]["image_generation"] = {
            "prompt": "嵐の浜辺で足元に割れた羅針盤が光る"
        }
        assert narration_text_set_hash(edited) == expected_hash
        assert (
            build_narration_semantic_review_pack(edited)["semantic_review_input_hash"]
            != expected_input_hash
        )
        RUNNER._atomic_write(manifest_path, RUNNER._replace_yaml_block(original, edited))
        return _aggregate(expected_hash, expected_input_hash, status="passed")

    with patch.object(RUNNER, "run_narration_semantic_critics", side_effect=fake_critics):
        status = asyncio.run(
            RUNNER.run_semantic_review(
                run_dir=run_dir,
                manifest_path=manifest_path,
                timeout_seconds=60,
                max_concurrency=3,
            )
        )

    _, persisted = load_structured_document(manifest_path)
    state = parse_state_file(run_dir / "state.txt")
    assert status == "stale"
    assert narration_text_set_hash(persisted) == expected_hash
    assert "semantic_critic_review" not in persisted["narration_workflow"]
    assert state["review.narration.semantic_critics.status"] == "stale"
    assert state["review.narration.semantic_critics.input_hash"] == expected_input_hash


def test_runner_does_not_overwrite_a_newer_same_hash_review(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    manifest_path, expected_hash, expected_input_hash = _write_revision_aware_run(run_dir)

    async def fake_critics(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        RUNNER.append_state_snapshot(
            run_dir / "state.txt",
            {"review.narration.semantic_critics.review_run_id": "newer-review"},
        )
        return _aggregate(expected_hash, expected_input_hash, status="passed")

    with patch.object(RUNNER, "run_narration_semantic_critics", side_effect=fake_critics):
        status = asyncio.run(
            RUNNER.run_semantic_review(
                run_dir=run_dir,
                manifest_path=manifest_path,
                timeout_seconds=60,
                max_concurrency=3,
            )
        )

    _, persisted = load_structured_document(manifest_path)
    assert status == "stale"
    assert "semantic_critic_review" not in persisted["narration_workflow"]
    assert not (run_dir / "logs" / "eval" / "narration" / "semantic_critics").exists()
