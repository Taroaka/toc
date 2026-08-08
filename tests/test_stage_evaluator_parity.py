from __future__ import annotations

import ast
import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_PIPELINE_PATH = REPO_ROOT / "scripts" / "verify-pipeline.py"
STAGE_EVALUATOR_PATH = REPO_ROOT / "toc" / "stage_evaluator.py"
TARGET_PACKAGE = REPO_ROOT / "toc" / "stage_evaluation"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc import stage_evaluator as CANONICAL  # noqa: E402
from toc.harness import parse_state_file  # noqa: E402
from toc import stage_review_cli  # noqa: E402


def _load_verify_pipeline():
    spec = importlib.util.spec_from_file_location("verify_pipeline_parity", VERIFY_PIPELINE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PIPELINE = _load_verify_pipeline()


CANONICAL_SIGNATURES = {
    "check_research": "(run_dir: 'Path', profile: 'str') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_story": "(run_dir: 'Path', profile: 'str') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_script_single": "(run_dir: 'Path', profile: 'str') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_script_scene_series": "(run_dir: 'Path', profile: 'str') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_manifest_single": "(run_dir: 'Path', profile: 'str', flow: 'str', *, require_review_artifacts: 'bool' = True) -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_manifest_scene_series": "(run_dir: 'Path', profile: 'str') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_video_single": "(run_dir: 'Path') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_video_scene_series": "(run_dir: 'Path') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "evaluate_stage": "(run_dir: 'Path', *, stage: 'str', profile: 'str', flow: 'str | None' = None) -> 'tuple[dict[str, Any], dict[str, str], str]'",
    "render_stage_review": "(*, run_dir: 'Path', stage_result: 'dict[str, Any]', stage: 'str', flow: 'str', profile: 'str') -> 'str'",
    "append_stage_review_state": "(*, run_dir: 'Path', stage: 'str', stage_result: 'dict[str, Any]', updates: 'dict[str, str]', report_path: 'Path') -> 'None'",
}

PIPELINE_SIGNATURES = {
    "check_research": "(run_dir: 'Path', profile: 'str') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_story": "(run_dir: 'Path', profile: 'str') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_script_single": "(run_dir: 'Path', profile: 'str', *, target_slot: 'str' = 'p450') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_script_scene_series": "(run_dir: 'Path', profile: 'str', *, target_slot: 'str' = 'p450') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_manifest_single": "(run_dir: 'Path', profile: 'str', flow: 'str') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_manifest_scene_series": "(run_dir: 'Path', profile: 'str') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_video_single": "(run_dir: 'Path', *, target_slot: 'str' = 'p930') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "check_video_scene_series": "(run_dir: 'Path', *, target_slot: 'str' = 'p930') -> 'tuple[dict[str, Any], dict[str, str]]'",
    "shared_check_manifest_single": "(run_dir: 'Path', profile: 'str', flow: 'str', *, require_review_artifacts: 'bool' = True) -> 'tuple[dict[str, Any], dict[str, str]]'",
    "_probe_duration": "(path: 'Path') -> 'float | None'",
}

CANONICAL_STAGE_KEYS = {
    "stage",
    "artifact",
    "passed",
    "score",
    "overall_rubric",
    "rubric_scores",
    "reason_keys",
    "warning_keys",
    "checks",
    "details",
}
PIPELINE_STAGE_KEYS = {"stage", "artifact", "passed", "score", "checks", "details"}
CHECK_KEYS = {"id", "passed", "kind", "message"}
PIPELINE_MINIMAL_RESEARCH_CHECKS = [
    ("research.file_exists", True, "deterministic", "research.md exists"),
    ("research.grounding_report", False, "rubric", "grounding report exists for research (got (missing))"),
    ("research.grounding_state", False, "rubric", "state records stage grounding as ready (got (unset))"),
    ("research.readset_report", False, "rubric", "readset report exists for research (got (missing))"),
    ("research.audit_report", False, "rubric", "audit report exists for research (got (missing))"),
    ("research.readset_state", False, "rubric", "state records readset report for research (got (unset))"),
    ("research.audit_state", False, "rubric", "state records stage audit as passed (got (unset))"),
    ("research.structured", True, "deterministic", "research.md contains structured YAML output"),
    (
        "research.sources",
        False,
        "rubric",
        "sources meet broad target >= 12 or compact grounded pack is present (got sources=0, passages=0)",
    ),
    ("research.story_materials", False, "rubric", "story_materials or legacy story baseline is present"),
    ("research.canonical_story", False, "rubric", "canonical story dump or legacy synopsis is present"),
    (
        "research.chronological_events",
        False,
        "rubric",
        "chronological coverage meets broad target >= 20 or compact grounded pack is present (got events=0, passages=0)",
    ),
    ("research.source_passages", False, "rubric", "source passages are present (got 0)"),
    (
        "research.facts",
        False,
        "rubric",
        "facts meet broad target >= 10 or compact grounded pack is present (got facts=0, passages=0)",
    ),
    ("research.conflicts_field", False, "rubric", "conflicts field is present"),
    ("research.handoff_to_story", False, "rubric", "handoff_to_story is present"),
    ("research.confidence", True, "rubric", "metadata.confidence_score is between 0.0 and 1.0"),
]
CANONICAL_MINIMAL_RESEARCH_CHECKS = [
    *PIPELINE_MINIMAL_RESEARCH_CHECKS[:8],
    ("research.contract_missing", False, "rubric", "evaluation_contract is missing for research stage."),
    *PIPELINE_MINIMAL_RESEARCH_CHECKS[8:],
    ("research.rubric.source_grounding", False, "rubric", "source_grounding rubric is >= 0.60 (got 0.00)"),
    ("research.rubric.coverage", False, "rubric", "coverage rubric is >= 0.60 (got 0.00)"),
    ("research.rubric.conflict_readiness", True, "rubric", "conflict_readiness rubric is >= 0.55 (got 0.90)"),
    ("research.rubric.structure_readiness", False, "rubric", "structure_readiness rubric is >= 0.60 (got 0.25)"),
    ("research.rubric.story_material_readiness", False, "rubric", "story_material_readiness rubric is >= 0.60 (got 0.00)"),
]

CLI_CASES = {
    "research": ("Review research stage outputs.", "artifact.research_review"),
    "story": ("Review story stage outputs.", "artifact.story_review"),
    "script": ("Review script stage outputs.", "artifact.script_review"),
    "manifest": ("Review manifest(scene/cut) stage outputs.", "artifact.manifest_review"),
    "video": ("Review video stage outputs.", "artifact.video_review_report"),
}


def _review_script(stage: str) -> Path:
    return REPO_ROOT / "scripts" / f"review-{stage}-stage.py"


def _assert_stage_schema(stage_result: dict, expected_keys: set[str]) -> None:
    assert set(stage_result) == expected_keys
    assert isinstance(stage_result["stage"], str)
    assert isinstance(stage_result["artifact"], str)
    assert isinstance(stage_result["passed"], bool)
    assert isinstance(stage_result["score"], float)
    assert isinstance(stage_result["checks"], list)
    assert isinstance(stage_result["details"], dict)
    assert stage_result["checks"], "characterization fixture must exercise at least one check"
    assert all(set(check) == CHECK_KEYS for check in stage_result["checks"])


def _ordered_check_snapshot(stage_result: dict) -> list[tuple[str, bool, str, str]]:
    return [
        (check["id"], check["passed"], check["kind"], check["message"])
        for check in stage_result["checks"]
    ]


def test_behavior_public_evaluator_signatures_are_stable() -> None:
    for name, expected in CANONICAL_SIGNATURES.items():
        assert str(inspect.signature(getattr(CANONICAL, name))) == expected
    for name, expected in PIPELINE_SIGNATURES.items():
        assert str(inspect.signature(getattr(PIPELINE, name))) == expected


def test_behavior_stage_evaluator_compatibility_imports_remain_available() -> None:
    expected_names = {
        "_cut_event_ref_issue_map",
        "as_dict",
        "as_dotted_str",
        "as_int",
        "append_stage_review_state",
        "check_manifest_scene_series",
        "check_manifest_single",
        "check_research",
        "check_script_scene_series",
        "check_script_single",
        "check_story",
        "check_video_scene_series",
        "check_video_single",
        "check_visual_value",
        "compact_research_pack_ok",
        "contract_list",
        "dense_story_scene_count",
        "evaluate_stage",
        "flatten_text",
        "flatten_without_keys",
        "has_todo",
        "render_stage_review",
        "scene_time_of_day_contract_missing",
        "story_scene_coverage_ok",
    }
    missing = sorted(name for name in expected_names if not callable(getattr(CANONICAL, name, None)))
    assert not missing, f"toc.stage_evaluator lost compatibility callables: {missing}"


@pytest.mark.parametrize("stage", ["research", "story", "script", "manifest", "video"])
def test_behavior_canonical_return_schema_on_missing_artifact(tmp_path: Path, stage: str) -> None:
    result, updates, flow = CANONICAL.evaluate_stage(tmp_path, stage=stage, profile="fast")

    _assert_stage_schema(result, CANONICAL_STAGE_KEYS)
    assert result["stage"] == stage
    assert isinstance(result["reason_keys"], list)
    assert isinstance(result["warning_keys"], list)
    assert isinstance(result["rubric_scores"], dict)
    assert isinstance(result["overall_rubric"], float)
    assert isinstance(updates, dict)
    assert flow == "toc-run"


@pytest.mark.parametrize(
    ("stage", "call"),
    [
        ("research", lambda run_dir: PIPELINE.check_research(run_dir, "fast")),
        ("story", lambda run_dir: PIPELINE.check_story(run_dir, "fast")),
        ("script", lambda run_dir: PIPELINE.check_script_single(run_dir, "fast")),
        ("manifest", lambda run_dir: PIPELINE.check_manifest_single(run_dir, "fast", "toc-run")),
        ("video", lambda run_dir: PIPELINE.check_video_single(run_dir, target_slot="p700")),
    ],
)
def test_behavior_pipeline_return_schema_on_missing_artifact(tmp_path: Path, stage: str, call) -> None:
    result, updates = call(tmp_path)

    _assert_stage_schema(result, PIPELINE_STAGE_KEYS)
    assert result["stage"] == stage
    assert isinstance(updates, dict)


def test_behavior_canonical_warning_policy_stays_distinct_from_pipeline_policy() -> None:
    checks = [
        {"id": "base", "passed": True, "kind": "deterministic", "message": "base passes"},
        {"id": "advisory", "passed": False, "kind": "warning", "message": "warning only"},
    ]

    canonical = CANONICAL.make_stage("script", "script.md", [dict(check) for check in checks])
    pipeline = PIPELINE.make_stage("script", "script.md", [dict(check) for check in checks])

    assert canonical["passed"] is True
    assert canonical["score"] == 1.0
    assert canonical["warning_keys"] == ["advisory"]
    assert canonical["reason_keys"] == ["advisory"]
    assert pipeline["passed"] is False
    assert pipeline["score"] == 0.5
    assert "warning_keys" not in pipeline


def test_behavior_representative_research_outputs_keep_order_and_values(tmp_path: Path) -> None:
    (tmp_path / "research.md").write_text(
        "```yaml\nmetadata:\n  confidence_score: 0.5\n```\n",
        encoding="utf-8",
    )

    canonical, canonical_updates = CANONICAL.check_research(tmp_path, "fast")
    pipeline, pipeline_updates = PIPELINE.check_research(tmp_path, "fast")

    assert _ordered_check_snapshot(canonical) == CANONICAL_MINIMAL_RESEARCH_CHECKS
    assert {key: value for key, value in canonical.items() if key != "checks"} == {
        "stage": "research",
        "artifact": "research.md",
        "passed": False,
        "score": 0.1739,
        "overall_rubric": 0.2175,
        "rubric_scores": {
            "source_grounding": 0.0,
            "coverage": 0.0,
            "conflict_readiness": 0.9,
            "structure_readiness": 0.25,
            "story_material_readiness": 0.0,
        },
        "reason_keys": [
            check_id
            for check_id, passed, _kind, _message in CANONICAL_MINIMAL_RESEARCH_CHECKS
            if not passed
        ],
        "warning_keys": [],
        "details": {
            "sources": 0,
            "event_count": 0,
            "source_passage_count": 0,
            "fact_count": 0,
        },
    }
    assert canonical_updates == {"eval.research.score": "0.1739"}

    assert _ordered_check_snapshot(pipeline) == PIPELINE_MINIMAL_RESEARCH_CHECKS
    assert {key: value for key, value in pipeline.items() if key != "checks"} == {
        "stage": "research",
        "artifact": "research.md",
        "passed": False,
        "score": 0.1765,
        "details": {
            "sources": 0,
            "event_count": 0,
            "source_passage_count": 0,
            "fact_count": 0,
        },
    }
    assert pipeline_updates == {"eval.research.score": "0.1765"}


def test_behavior_pipeline_invalid_script_slot_uses_p450_fallback(tmp_path: Path) -> None:
    (tmp_path / "script.md").write_text("A concrete script body. " * 8, encoding="utf-8")

    default_result = PIPELINE.check_script_single(tmp_path, "fast")
    invalid_result = PIPELINE.check_script_single(tmp_path, "fast", target_slot="not-a-slot")
    p500_result = PIPELINE.check_script_single(tmp_path, "fast", target_slot="p500")

    assert invalid_result == default_result
    default_checks = {check["id"]: check["passed"] for check in default_result[0]["checks"]}
    p500_checks = {check["id"]: check["passed"] for check in p500_result[0]["checks"]}
    assert default_checks["scene_set.semantic_review_subagent_passed"] is True
    assert p500_checks["scene_set.semantic_review_subagent_passed"] is False


def test_behavior_shared_manifest_alias_keeps_optional_review_argument(tmp_path: Path) -> None:
    actual = PIPELINE.shared_check_manifest_single(
        tmp_path,
        "fast",
        "toc-run",
        require_review_artifacts=False,
    )
    expected = CANONICAL.check_manifest_single(
        tmp_path,
        "fast",
        "toc-run",
        require_review_artifacts=False,
    )

    assert actual == expected


def test_behavior_pipeline_duration_probe_remains_a_module_monkeypatch_seam(tmp_path: Path) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"not-a-real-video")
    (tmp_path / "video_manifest.md").write_text(
        "```yaml\nvideo_metadata:\n  target_duration_seconds: 300\n```\n",
        encoding="utf-8",
    )

    with patch.object(PIPELINE, "_probe_duration", return_value=300.0) as probe:
        result, updates = PIPELINE.check_video_single(tmp_path, target_slot="p700")

    probe.assert_called_once_with(video_path)
    checks = {check["id"]: check for check in result["checks"]}
    assert checks["video.duration"]["passed"] is True
    assert checks["video.duration"]["message"] == "video duration is positive (300.00s)"
    assert checks["video.duration_fit"]["passed"] is True
    assert updates == {}


@pytest.mark.parametrize("stage", CLI_CASES)
def test_behavior_review_cli_help_contract(stage: str) -> None:
    description, _artifact_key = CLI_CASES[stage]
    completed = subprocess.run(
        [sys.executable, str(_review_script(stage)), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert description in completed.stdout
    for option in ("--run-dir", "--profile", "--flow", "--out", "--fail-on-findings"):
        assert option in completed.stdout
    assert "{fast,standard}" in completed.stdout
    assert "{toc-run,scene-series,immersive}" in completed.stdout


@pytest.mark.parametrize("stage", CLI_CASES)
def test_behavior_review_cli_default_output_stdout_and_state_contract(
    tmp_path: Path,
    stage: str,
) -> None:
    _description, artifact_key = CLI_CASES[stage]
    run_dir = tmp_path / stage
    run_dir.mkdir()
    (run_dir / "state.txt").write_text("topic=parity\n---\n", encoding="utf-8")
    report_path = run_dir / f"{stage}_review.md"

    completed = subprocess.run(
        [sys.executable, str(_review_script(stage)), "--run-dir", str(run_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == f"{report_path}\n"
    assert completed.stderr == ""
    report = report_path.read_text(encoding="utf-8")
    assert report.startswith(f"# {stage.title()} Evaluator Review\n")
    assert "- flow: `toc-run`" in report
    assert "- profile: `standard`" in report
    assert "- status: `changes_requested`" in report
    state = parse_state_file(run_dir / "state.txt")
    assert state[f"eval.{stage}.status"] == "changes_requested"
    assert int(state[f"eval.{stage}.findings"]) >= 1
    assert state[artifact_key] == str(report_path.resolve())


@pytest.mark.parametrize("stage", CLI_CASES)
def test_behavior_review_cli_relative_out_and_fail_on_findings_contract(
    tmp_path: Path,
    stage: str,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    relative_out = Path(f"reports/{stage}.md")
    (tmp_path / "reports").mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            str(_review_script(stage)),
            "--run-dir",
            str(run_dir),
            "--out",
            str(relative_out),
            "--fail-on-findings",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stdout == f"{relative_out}\n"
    assert completed.stderr == ""
    assert (tmp_path / relative_out).is_file()
    assert not (run_dir / relative_out).exists()
    assert not (run_dir / "state.txt").exists()


def test_behavior_review_cli_writes_report_before_appending_state(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state_path = run_dir / "state.txt"
    state_path.write_text("topic=parity\n---\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(_review_script("research")),
            "--run-dir",
            str(run_dir),
            "--out",
            str(state_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    final_text = state_path.read_text(encoding="utf-8")
    assert final_text.startswith("# Research Evaluator Review\n")
    assert "eval.research.status=changes_requested" in final_text
    assert final_text.index("# Research Evaluator Review") < final_text.index(
        "eval.research.status=changes_requested"
    )


def test_behavior_review_cli_leaves_write_exceptions_uncaught(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    missing_parent_out = tmp_path / "missing" / "research.md"

    completed = subprocess.run(
        [
            sys.executable,
            str(_review_script("research")),
            "--run-dir",
            str(run_dir),
            "--out",
            str(missing_parent_out),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "FileNotFoundError" in completed.stderr


@pytest.mark.parametrize(
    ("passed", "fail_on_findings", "expected_exit"),
    [(True, True, 0), (False, False, 0), (False, True, 1)],
)
def test_behavior_shared_review_cli_runner_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    passed: bool,
    fail_on_findings: bool,
    expected_exit: int,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    report_path = run_dir / "research_review.md"
    result = {"passed": passed}
    events: list[str] = []

    monkeypatch.setattr(
        stage_review_cli,
        "evaluate_stage",
        lambda *args, **kwargs: (result, {"eval.research.score": "1.0000"}, "toc-run"),
    )
    monkeypatch.setattr(
        stage_review_cli,
        "render_stage_review",
        lambda **kwargs: events.append("render") or "review body\n",
    )

    def append_state(**kwargs) -> None:
        assert report_path.read_text(encoding="utf-8") == "review body\n"
        events.append("append")

    monkeypatch.setattr(stage_review_cli, "append_stage_review_state", append_state)
    argv = ["review-research-stage.py", "--run-dir", str(run_dir)]
    if fail_on_findings:
        argv.append("--fail-on-findings")
    monkeypatch.setattr(sys, "argv", argv)

    exit_code = stage_review_cli.run_stage_review_cli(
        stage="research",
        description="Review research stage outputs.",
    )

    assert exit_code == expected_exit
    assert events == ["render", "append"]
    assert capsys.readouterr().out == f"{report_path}\n"


def _require_target_package() -> list[Path]:
    assert TARGET_PACKAGE.is_dir(), (
        "toc/stage_evaluation/ does not exist yet; create the extracted evaluator package "
        "before satisfying the structural refactor tests"
    )
    paths = sorted(TARGET_PACKAGE.glob("*.py"))
    assert paths, "toc/stage_evaluation/ exists but contains no Python modules"
    return paths


def _top_level_function_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def test_structure_stage_evaluator_is_a_facade_of_at_most_300_lines() -> None:
    physical_lines = len(STAGE_EVALUATOR_PATH.read_text(encoding="utf-8").splitlines())
    assert physical_lines <= 300, (
        f"toc/stage_evaluator.py is {physical_lines} lines; the compatibility facade limit is 300"
    )


def test_structure_shared_primitives_have_one_owner_under_target_package() -> None:
    package_paths = _require_target_package()
    paths = [STAGE_EVALUATOR_PATH, VERIFY_PIPELINE_PATH, *package_paths]
    definitions = {path: _top_level_function_names(path) for path in paths}
    primitive_groups = {
        "non_empty": {"non_empty"},
        "as_list": {"as_list"},
        "nested_get": {"nested_get"},
        "add_check": {"add_check"},
        "grounding-check append": {"append_grounding_checks", "_append_grounding_checks"},
        "duration probing": {"probe_duration", "_probe_duration"},
    }

    for label, accepted_names in primitive_groups.items():
        implementations = [
            (path, name)
            for path, names in definitions.items()
            for name in names
            if name in accepted_names
        ]
        rendered = [
            f"{path.relative_to(REPO_ROOT)}:{name}" for path, name in implementations
        ]
        assert len(implementations) == 1, (
            f"{label} must have exactly one function implementation; found "
            f"{rendered}"
        )
        owner, _name = implementations[0]
        assert owner.is_relative_to(TARGET_PACKAGE), (
            f"{label} must be implemented under toc/stage_evaluation/, got "
            f"{owner.relative_to(REPO_ROOT)}"
        )


def test_structure_target_package_functions_are_at_most_200_lines() -> None:
    oversized: list[str] = []
    for path in _require_target_package():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            assert node.end_lineno is not None
            physical_lines = node.end_lineno - node.lineno + 1
            if physical_lines > 200:
                oversized.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno} {node.name} ({physical_lines} lines)"
                )
    assert not oversized, "functions over the 200-line limit:\n" + "\n".join(oversized)


def _package_import_graph(paths: list[Path]) -> dict[str, set[str]]:
    module_by_path = {
        path: (
            "toc.stage_evaluation"
            if path.name == "__init__.py"
            else f"toc.stage_evaluation.{path.stem}"
        )
        for path in paths
    }
    known_modules = set(module_by_path.values())
    graph = {module: set() for module in known_modules}

    for path, current_module in module_by_path.items():
        current_package = (
            current_module if path.name == "__init__.py" else current_module.rpartition(".")[0]
        )
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in known_modules:
                        graph[current_module].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    relative_name = "." * node.level + (node.module or "")
                    imported_base = importlib.util.resolve_name(relative_name, current_package)
                else:
                    imported_base = node.module or ""
                if imported_base in known_modules:
                    graph[current_module].add(imported_base)
                for alias in node.names:
                    candidate = f"{imported_base}.{alias.name}" if imported_base else alias.name
                    if candidate in known_modules:
                        graph[current_module].add(candidate)
    return graph


def test_structure_target_package_has_no_internal_import_cycles() -> None:
    graph = _package_import_graph(_require_target_package())
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            cycle = visiting[visiting.index(module) :] + [module]
            pytest.fail("internal import cycle: " + " -> ".join(cycle))
        if module in visited:
            return
        visiting.append(module)
        for dependency in sorted(graph[module]):
            visit(dependency)
        visiting.pop()
        visited.add(module)

    for module in sorted(graph):
        visit(module)
