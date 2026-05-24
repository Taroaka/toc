import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, parse_state_file
from toc import stage_evaluator as STAGE_EVALUATOR
from toc.review_loop import REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE, SCENE_REVIEW_CRITIC_FOCUS


def _good_research_yaml() -> str:
    sources = "\n".join(f"  - title: source{i}\n    url: https://example.com/{i}" for i in range(12))
    beat_sheet = "\n".join(f"        - beat: beat{i}\n          scene_ids: [{i}]" for i in range(1, 21))
    source_passages = "\n".join(
        f"  - passage_id: P{i}\n    source_id: S1\n    passage: passage {i}\n    evidence_note: evidence {i}\n    confidence: 0.9"
        for i in range(1, 3)
    )
    facts = "\n".join(
        f"    - fact_id: F{i}\n      claim: fact {i}\n      kind: plot\n      confidence: 0.9\n      verification: verified\n      sources: [S1]\n      notes: \"\""
        for i in range(1, 11)
    )
    return "\n".join(
        [
            "```yaml",
            "sources:",
            sources,
            "story_baseline:",
            "  canonical_synopsis:",
            "    short_summary: summary",
            "    beat_sheet:",
            beat_sheet,
            "conflicts:",
            "  - conflict_id: C1",
            "    topic: 採用する物語軸",
            "    accounts:",
            "      - account_id: A",
            "        claim: 英雄譚として扱う",
            "        sources: [S1]",
            "        confidence: 0.9",
            "      - account_id: B",
            "        claim: 教訓譚として扱う",
            "        sources: [S2]",
            "        confidence: 0.8",
            "    impact_on_story: p200 の候補比較に使う",
            "    selection_notes:",
            "      recommended_choice: both_separated",
            "      rationale: 候補比較で分けて扱える",
            "source_passages:",
            source_passages,
            "facts:",
            "  items:",
            facts,
            "handoff_to_story:",
            "  recommended_focus: [\"focus\"]",
            "  must_preserve: [\"preserve\"]",
            "  avoid_overstating: [\"avoid\"]",
            "  selection_questions_for_p200: [\"question\"]",
            "evaluation_contract:",
            "  target_questions: [\"summary\"]",
            "  must_cover: [\"summary\"]",
            "  must_resolve_conflicts: []",
            "  done_when: [\"story materials と根拠が埋まる\"]",
            "metadata:",
            "  confidence_score: 0.9",
            "```",
            "",
        ]
    )


def _good_story_yaml() -> str:
    scene_lines: list[str] = []
    for i in range(1, 21):
        scene_lines.extend(
            [
                f"    - scene_id: {i}",
                "      phase: \"development\"",
                f"      purpose: \"Scene {i} の役割\"",
                f"      conflict: \"Scene {i} の葛藤\"",
                f"      turn: \"Scene {i} の転換\"",
                "      affect:",
                "        label_hint: \"curiosity\"",
                "        audience_job: \"hook\"",
                f"      visualizable_action: \"Scene {i} の画面化可能な行動\"",
                f"      grounding_note: \"Scene {i} は research refs に基づき、心理描写は演出補完\"",
                f"      narration: \"Scene {i} の語り\"",
                f"      visual: \"Scene {i} の情景\"",
                f"      research_refs: [\"research.story_baseline.canonical_synopsis.beat_sheet[{i - 1}]\"]",
            ]
        )
    return "\n".join(
        [
            "```yaml",
            "selection:",
            "  candidates:",
            "    - candidate_id: \"A\"",
            "      logline: \"王道案\"",
            "      why_it_scores: [\"clear\"]",
            "      requires_hybridization_approval: false",
            "    - candidate_id: \"B\"",
            "      logline: \"別視点案\"",
            "      why_it_scores: [\"fresh\"]",
            "      requires_hybridization_approval: false",
            "  chosen_candidate_id: \"A\"",
            "  rationale: \"最も安定している\"",
            "hybridization:",
            "  approval_status: \"not_needed\"",
            "script:",
            "  scenes:",
            *scene_lines,
            "```",
            "",
        ]
    )


def _run_grounding(run_dir: Path, stage: str, *, flow: str = "toc-run") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "resolve-stage-grounding.py"),
            "--stage",
            stage,
            "--run-dir",
            str(run_dir),
            "--flow",
            flow,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _ensure_story_ready(run_dir: Path) -> None:
    story_path = run_dir / "story.md"
    if not story_path.exists():
        story_path.write_text(_good_story_yaml(), encoding="utf-8")
    append_state_snapshot(run_dir / "state.txt", {"review.story.status": "approved"})


def _ensure_script_ready(run_dir: Path) -> None:
    script_path = run_dir / "script.md"
    if not script_path.exists():
        script_path.write_text(
            "```yaml\nscript:\n  scenes:\n    - scene_id: 1\n      phase: opening\n      summary: \"十分な長さの台本本文です。十分な長さの台本本文です。\"\n      research_refs: [\"research.story_materials\"]\n```\n",
            encoding="utf-8",
        )


def _ensure_video_generation_ready(run_dir: Path) -> None:
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.image.status": "approved",
            "review.narration.status": "approved",
        },
    )


def _resolve_ready_grounding(run_dir: Path, *stages: str, flow: str = "toc-run") -> None:
    if any(stage in {"story", "script", "image_prompt", "scene_implementation", "video_generation"} for stage in stages):
        _ensure_story_ready(run_dir)
    if any(stage in {"image_prompt", "scene_implementation", "video_generation"} for stage in stages):
        _ensure_script_ready(run_dir)
    if any(stage in {"image_prompt", "scene_implementation", "video_generation"} for stage in stages):
        append_state_snapshot(run_dir / "state.txt", {"review.duration_fit.status": "passed"})
    if any(stage in {"image_prompt", "scene_implementation", "video_generation"} for stage in stages):
        append_state_snapshot(run_dir / "state.txt", {"eval.p400_readiness.status": "approved"})
    if "video_generation" in stages:
        _ensure_video_generation_ready(run_dir)
    expanded_stages = list(stages)
    if "image_prompt" in expanded_stages and "manifest" not in expanded_stages:
        expanded_stages.insert(expanded_stages.index("image_prompt"), "manifest")
    for stage in expanded_stages:
        result = _run_grounding(run_dir, stage, flow=flow)
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)


def _write_p400_review_artifacts(run_dir: Path) -> None:
    reports = {
        "scene_set_review.md": "status: passed\n\n全 scene set は承認済み。\n",
        "scene_detail_review.md": "status: passed\n\n全 scene detail は承認済み。\n",
        "cut_blueprint_review.md": "status: passed\n\n全 cut blueprint は承認済み。\n",
        "script_review.md": "status: passed\n\nscript review は承認済み。\n",
        "production_readiness_review.md": "\n".join(
            [
                "status: passed",
                "",
                "Structure: scene/cut 構造は連続している。",
                "Duration: target duration を cut duration 合計で満たしている。",
                "Quality: 追加 cut は不要。",
                "## Design Owner Patch Brief",
                "",
                "No blocking changes.",
            ]
        )
        + "\n",
    }
    for filename, text in reports.items():
        (run_dir / filename).write_text(text, encoding="utf-8")
    for stage in ("scene_set", "scene_detail", "cut_blueprint", "script", "production_readiness"):
        round_dir = run_dir / "logs" / "eval" / stage / "round_01"
        round_dir.mkdir(parents=True, exist_ok=True)
        prompt_dir = round_dir / "prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        stage_focus = REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE.get(stage, {})
        for idx in range(1, 6):
            focus_name = stage_focus.get(idx, ("", ""))[0]
            focus_line = f"- critic_focus: {focus_name}\n" if focus_name else ""
            (round_dir / f"critic_{idx}.md").write_text(f"{focus_line}- status: passed\n", encoding="utf-8")
            (prompt_dir / f"critic_{idx}.prompt.md").write_text(
                f"Critic focus for this prompt:\n- role: {focus_name}\n" if focus_name else "generic critic\n",
                encoding="utf-8",
            )
        patch_heading = "Design Owner Patch Brief" if stage == "production_readiness" else "Generator Patch Brief"
        scene_count_gate = []
        if stage_focus:
            if stage in SCENE_REVIEW_CRITIC_FOCUS:
                scene_count_gate = [
                    "## Scene Count Gate",
                    "",
                    "- maximal_meaningful_stop_condition: no additional independent scene remains",
                    "- next_scene_candidate: none",
                    "- cut_thickening_reason: additional material repeats the same scene turn",
                    "- critic_1_scene_count_coverage_resolution: scene_count_coverage passed",
                    "",
                ]
            else:
                scene_count_gate = [
                    "## Cut Blueprint Gate",
                    "",
                    "- cut_intent_isolation: passed",
                    "- beat_ladder_coverage: passed",
                    "- first_frame_motion_readiness: passed",
                    "- multimodal_contract_coverage: passed",
                    "- duration_density_and_handoff: passed",
                    "- coverage_plan_complete: passed",
                    "- continuity_contract_complete: passed",
                    "- narration_contract_complete: passed",
                    "- downstream_handoff_complete: passed",
                    "- triangulation_review_ready: passed",
                    "",
                ]
        (round_dir / "aggregated_review.md").write_text(
            "\n".join(
                [
                    "- status: passed",
                    "",
                    "## Blocking Findings",
                    "",
                    "[]",
                    "",
                    "## Recommended Changes",
                    "",
                    "[]",
                    "",
                    "## Rejected Suggestions",
                    "",
                    "[]",
                    "",
                    *scene_count_gate,
                    f"## {patch_heading}",
                    "",
                    "No changes.",
                    "",
                    "## Round Summary",
                    "",
                    "passed",
                ]
            )
            + "\n",
            encoding="utf-8",
        )


def _write_valid_immersive_p400_pair(
    run_dir: Path,
    *,
    target_duration: int = 300,
    cut_duration: int = 15,
    scene_count: int = 10,
    manifest_phase: str = "production",
) -> None:
    script_lines = [
        "```yaml",
        "evaluation_contract:",
        "  target_arc: \"opening\"",
        "  must_cover: [\"桃太郎\"]",
        "  must_avoid: []",
        "scene_set_review: {status: \"approved\"}",
        "scene_detail_review: {status: \"approved\"}",
        "cut_blueprint_review: {status: \"approved\"}",
        "script:",
        "  scenes:",
    ]
    manifest_lines = [
        "```yaml",
        f"manifest_phase: {manifest_phase}",
        "video_metadata:",
        "  topic: \"桃太郎\"",
        "  experience: \"cinematic_story\"",
        f"  target_duration_seconds: {target_duration}",
        "scenes:",
    ]
    for scene_idx in range(1, scene_count + 1):
        terminal = scene_idx == scene_count
        script_lines.extend(
            [
                f"    - scene_id: {scene_idx}",
                "      phase: \"opening\"",
                "      importance: \"medium\"",
                "      summary: \"桃太郎が進む。十分な長さの本文です。十分な長さの本文です。\"",
                "      target_duration_seconds: 30",
                "      estimated_duration_seconds: 30",
                ("      terminal_resolution: \"物語が締まる\"" if terminal else "      handoff_to_next_scene: \"次の場面へつながる\""),
                "      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, next_scene_connection_checked: true}",
                "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                "      scene_intent:",
                "        story_purpose: \"進行\"",
                "        audience_information: [\"桃太郎\"]",
                "        withheld_information: []",
                "        reveal_constraints: []",
                "        affect_transition: \"前進\"",
                "        visual_value_source: \"none\"",
                "        production_risks: []",
                "        handoff_notes: {p500_asset: [], p600_image: [], p700_narration: [], p800_video: []}",
                "      agent_review: {status: \"passed\"}",
                "      cuts:",
            ]
        )
        manifest_lines.extend([f"  - scene_id: {scene_idx}", "    cuts:"])
        for cut_idx in range(1, 4):
            selector = f"scene{scene_idx}_cut{cut_idx}"
            script_lines.extend(
                [
                    f"        - cut_id: {cut_idx}",
                    f"          selector: \"{selector}\"",
                    "          cut_blueprint:",
                    "            cut_role: \"main\"",
                    "            duration_intent: \"standard\"",
                    "            target_beat: \"桃太郎\"",
                    "            must_show: [\"桃太郎\"]",
                    "            must_avoid: []",
                    "            done_when: [\"桃太郎が見える\"]",
                    "            visual_beat: \"桃太郎が進む\"",
                    "            narration_role: \"setup\"",
                    "            asset_dependency_hint: {character_ids: [\"momotaro\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                ]
            )
            manifest_lines.extend(
                [
                    f"      - cut_id: {cut_idx}",
                    f"        selector: \"{selector}\"",
                    "        scene_contract: {target_beat: \"桃太郎\", must_show: [\"桃太郎\"], must_avoid: [], done_when: [\"桃太郎が見える\"]}",
                    "        image_generation:",
                    "          prompt: \"画面内テキストなし。実写映画風の村道。前景に湿った土と小石、中央に桃太郎の顔と衣装、腰のきびだんご袋、背景に朝霧の村と山並み、横から柔らかな朝日、布の質感、足元の影、次へ進む緊張まで具体的に見える。\"",
                    "          character_ids: [\"momotaro\"]",
                    "          object_ids: []",
                    f"          output: \"assets/scenes/{selector}.png\"",
                    "        video_generation:",
                    f"          duration_seconds: {cut_duration}",
                    "          motion_prompt: \"桃太郎が前へ進む。\"",
                    "        audio:",
                    "          narration:",
                    "            text: \"桃太郎が進む。\"",
                    "            tool: \"elevenlabs\"",
                ]
            )
    script_lines.extend(["```", ""])
    manifest_lines.extend(["```", ""])
    (run_dir / "script.md").write_text("\n".join(script_lines), encoding="utf-8")
    (run_dir / "video_manifest.md").write_text("\n".join(manifest_lines), encoding="utf-8")
    _write_p400_review_artifacts(run_dir)


class TestStageEvaluatorScripts(unittest.TestCase):
    def test_stage_evaluator_accepts_compact_grounded_research_pack(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0010"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "research.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "story_baseline:",
                        "  canonical_synopsis:",
                        "    short_summary: compact but grounded canonical story",
                        "sources:",
                        "  - source_id: S1",
                        "    title: Primary",
                        "    url: https://example.com/primary",
                        "source_passages:",
                    ]
                    + [
                        f"  - passage_id: P{i}\n    source_id: S1\n    passage: passage {i}\n    evidence_note: evidence {i}\n    confidence: 0.9"
                        for i in range(1, 6)
                    ]
                    + [
                        "conflicts:",
                        "  - conflict_id: C1",
                        "    topic: variant choice",
                        "    accounts: []",
                        "handoff_to_story:",
                        "  recommended_focus: [focus]",
                        "metadata:",
                        "  confidence_score: 0.9",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            stage, _ = STAGE_EVALUATOR.check_research(run_dir, "fast")
            checks = {check["id"]: check["passed"] for check in stage["checks"]}

            self.assertTrue(checks["research.sources"])
            self.assertTrue(checks["research.chronological_events"])
            self.assertTrue(checks["research.facts"])
            self.assertGreaterEqual(stage["rubric_scores"]["source_grounding"], 0.6)

    def test_stage_evaluator_scripts_update_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "timestamp=2026-03-29T00:00:00+09:00",
                        "job_id=JOB_2026-03-29_000001",
                        "topic=桃太郎",
                        "status=VIDEO",
                        "review.video.status=pending",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "research.md").write_text(_good_research_yaml(), encoding="utf-8")
            (run_dir / "script.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "evaluation_contract:",
                        "  target_arc: \"opening,development,climax\"",
                        "  must_cover: [\"桃太郎\"]",
                        "  must_avoid: [\"TODO\"]",
                        "  done_when: [\"主要 phase を含む\"]",
                        "scene_set_review:",
                        "  status: \"approved\"",
                        "  agent_review:",
                        "    status: \"passed\"",
                        "scene_detail_review:",
                        "  status: \"approved\"",
                        "cut_blueprint_review:",
                        "  status: \"approved\"",
                        "production_readiness_review:",
                        "  status: \"approved\"",
                        "  council:",
                        "    design_owner: {only_editor: true}",
                        "    advisory_agents: [\"structure_auditor\", \"duration_auditor\", \"quality_auditor\", \"orchestrator\"]",
                        "script:",
                        "  scenes:",
                        "    - scene_id: 1",
                        "      phase: \"opening\"",
                        "      summary: \"桃太郎が村で育つ。十分な長さの台本本文です。十分な長さの台本本文です。\"",
                    "      importance: \"low\"",
                    "      target_duration_seconds: 24",
                    "      estimated_duration_seconds: 24",
                        "      handoff_to_next_scene: \"旅支度へ進む\"",
                        "      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, next_scene_connection_checked: true}",
                        "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                        "      scene_intent:",
                        "        story_purpose: \"導入\"",
                        "        audience_information: [\"桃太郎が村にいる\"]",
                        "        withheld_information: []",
                        "        reveal_constraints: []",
                        "        affect_transition: \"hook\"",
                        "        visual_value_source: \"none\"",
                        "        production_risks: []",
                        "        handoff_notes: {p500_asset: [], p600_image: [], p700_narration: [], p800_video: []}",
                        "      agent_review:",
                        "        status: \"passed\"",
                        "      cuts:",
                        "        - cut_id: 1",
                        "          cut_blueprint:",
                        "            cut_role: \"main\"",
                        "            duration_intent: \"standard\"",
                        "            target_beat: \"桃太郎の導入\"",
                        "            must_show: [\"桃太郎\"]",
                        "            must_avoid: []",
                        "            done_when: [\"桃太郎の導入として読める\"]",
                        "            visual_beat: \"村にいる桃太郎\"",
                        "            narration_role: \"setup\"",
                        "            asset_dependency_hint: {character_ids: [\"momotaro\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                    "          narration: \"桃太郎は村で育ちました。\"",
                    "          tts_text: \"桃太郎は村で育ちました。\"",
                    "        - cut_id: 2",
                    "          cut_blueprint:",
                    "            cut_role: \"reaction\"",
                    "            duration_intent: \"standard\"",
                    "            target_beat: \"村での桃太郎の余韻\"",
                    "            must_show: [\"桃太郎\"]",
                    "            must_avoid: []",
                    "            done_when: [\"次の旅支度へつながる\"]",
                    "            visual_beat: \"村を見渡す桃太郎\"",
                    "            narration_role: \"aftertaste\"",
                    "            asset_dependency_hint: {character_ids: [\"momotaro\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                    "          narration: \"桃太郎は外の世界へ目を向けました。\"",
                    "          tts_text: \"桃太郎は外の世界へ目を向けました。\"",
                        "    - scene_id: 2",
                        "      phase: \"development\"",
                        "      summary: \"桃太郎が旅支度を整える。十分な長さの台本本文です。十分な長さの台本本文です。\"",
                    "      importance: \"low\"",
                    "      target_duration_seconds: 24",
                    "      estimated_duration_seconds: 24",
                        "      handoff_to_next_scene: \"決戦へ進む\"",
                        "      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, next_scene_connection_checked: true}",
                        "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                        "      scene_intent:",
                        "        story_purpose: \"旅立ち\"",
                        "        audience_information: [\"桃太郎が旅支度をする\"]",
                        "        withheld_information: []",
                        "        reveal_constraints: []",
                        "        affect_transition: \"lift\"",
                        "        visual_value_source: \"none\"",
                        "        production_risks: []",
                        "        handoff_notes: {p500_asset: [], p600_image: [], p700_narration: [], p800_video: []}",
                        "      agent_review:",
                        "        status: \"passed\"",
                        "      cuts:",
                        "        - cut_id: 1",
                        "          cut_blueprint:",
                        "            cut_role: \"main\"",
                        "            duration_intent: \"standard\"",
                        "            target_beat: \"旅支度\"",
                        "            must_show: [\"旅支度\"]",
                        "            must_avoid: []",
                        "            done_when: [\"旅立ち前の変化が読める\"]",
                        "            visual_beat: \"旅支度を整える桃太郎\"",
                        "            narration_role: \"fact\"",
                        "            asset_dependency_hint: {character_ids: [\"momotaro\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                    "          narration: \"桃太郎は旅支度を整えました。\"",
                    "          tts_text: \"桃太郎は旅支度を整えました。\"",
                    "        - cut_id: 2",
                    "          cut_blueprint:",
                    "            cut_role: \"reaction\"",
                    "            duration_intent: \"standard\"",
                    "            target_beat: \"旅立ち前の決意\"",
                    "            must_show: [\"旅支度\"]",
                    "            must_avoid: []",
                    "            done_when: [\"決戦へ向かう準備が読める\"]",
                    "            visual_beat: \"荷物を背負う桃太郎\"",
                    "            narration_role: \"aftertaste\"",
                    "            asset_dependency_hint: {character_ids: [\"momotaro\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                    "          narration: \"桃太郎は迷わず歩き出しました。\"",
                    "          tts_text: \"桃太郎は迷わず歩き出しました。\"",
                        "    - scene_id: 3",
                        "      phase: \"climax\"",
                        "      summary: \"桃太郎が決戦へ向かう。十分な長さの台本本文です。十分な長さの台本本文です。\"",
                    "      importance: \"low\"",
                    "      target_duration_seconds: 24",
                    "      estimated_duration_seconds: 24",
                        "      terminal_resolution: \"決戦への余韻で終わる\"",
                        "      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, next_scene_connection_checked: true}",
                        "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                        "      scene_intent:",
                        "        story_purpose: \"決戦\"",
                        "        audience_information: [\"桃太郎が決戦へ向かう\"]",
                        "        withheld_information: []",
                        "        reveal_constraints: []",
                        "        affect_transition: \"spike\"",
                        "        visual_value_source: \"none\"",
                        "        production_risks: []",
                        "        handoff_notes: {p500_asset: [], p600_image: [], p700_narration: [], p800_video: []}",
                        "      agent_review:",
                        "        status: \"passed\"",
                        "      cuts:",
                        "        - cut_id: 1",
                        "          cut_blueprint:",
                        "            cut_role: \"main\"",
                        "            duration_intent: \"standard\"",
                        "            target_beat: \"決戦へ向かう\"",
                        "            must_show: [\"桃太郎\"]",
                        "            must_avoid: []",
                        "            done_when: [\"climax として読める\"]",
                        "            visual_beat: \"決戦へ向かう桃太郎\"",
                        "            narration_role: \"emotion\"",
                        "            asset_dependency_hint: {character_ids: [\"momotaro\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                    "          narration: \"桃太郎は決戦へ向かいました。\"",
                    "          tts_text: \"桃太郎は決戦へ向かいました。\"",
                    "        - cut_id: 2",
                    "          cut_blueprint:",
                    "            cut_role: \"reaction\"",
                    "            duration_intent: \"standard\"",
                    "            target_beat: \"決戦前の緊張\"",
                    "            must_show: [\"桃太郎\"]",
                    "            must_avoid: []",
                    "            done_when: [\"climax の緊張が読める\"]",
                    "            visual_beat: \"遠くを見つめる桃太郎\"",
                    "            narration_role: \"aftertaste\"",
                    "            asset_dependency_hint: {character_ids: [\"momotaro\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                    "          narration: \"その先に決戦が待っていました。\"",
                    "          tts_text: \"その先に決戦が待っていました。\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "scenes:",
                        "  - scene_id: 1",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        scene_contract:",
                        "          target_beat: \"桃太郎\"",
                        "          must_show: [\"桃太郎\"]",
                        "          must_avoid: [\"TODO\"]",
                        "          done_when: [\"narration と prompt に桃太郎が出る\"]",
                        "        image_generation:",
                        "          prompt: \"桃太郎が朝の村をゆっくり歩く。藁屋根の家並み、土の道、やわらかな朝日、前景には風に揺れるのぼり、中央には桃太郎、背景には山並み。実写的で自然な衣装と光。\"",
                        "          character_ids: [\"momotaro\"]",
                        "          object_ids: [\"peach\"]",
                        "        video_generation:",
                        "          duration_seconds: 5",
                        "          motion_prompt: \"桃太郎が前へ進む。\"",
                        "        audio:",
                        "          narration:",
                        "            text: \"むかし、桃から生まれた子がいました。\"",
                        "            tool: \"elevenlabs\"",
                        "quality_check:",
                        "  review_contract:",
                        "    target_outcome: \"publishable_short\"",
                        "    must_have_artifacts: [\"video.mp4\"]",
                        "    must_avoid: []",
                        "    done_when: [\"video.mp4 が生成済み\"]",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "video.mp4").write_bytes(b"fake")
            _resolve_ready_grounding(run_dir, "research", "story", "script", "image_prompt", "video_generation")

            commands = [
                "scripts/review-research-stage.py",
                "scripts/review-story-stage.py",
                "scripts/review-script-stage.py",
                "scripts/review-manifest-stage.py",
                "scripts/review-video-stage.py",
            ]
            for command in commands:
                result = subprocess.run(
                    [sys.executable, str(REPO_ROOT / command), "--run-dir", str(run_dir), "--profile", "standard"],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, msg=result.stderr)

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.research.status"], "approved")
            self.assertEqual(state["eval.story.status"], "approved")
            self.assertEqual(state["review.story.status"], "approved")
            self.assertEqual(state["eval.script.status"], "approved")
            self.assertEqual(state["eval.manifest.status"], "approved")
            self.assertEqual(state["eval.video.status"], "approved")
            self.assertEqual(state["artifact.story_review"], str((run_dir / "story_review.md").resolve()))
            self.assertIn("eval.manifest.rubric.beat_clarity", state)
            self.assertIn("eval.video.overall_rubric", state)
            self.assertTrue((run_dir / "research_review.md").exists())
            self.assertTrue((run_dir / "story_review.md").exists())
            self.assertTrue((run_dir / "script_review.md").exists())
            self.assertTrue((run_dir / "manifest_review.md").exists())
            self.assertTrue((run_dir / "video_review.md").exists())

    def test_script_evaluator_fails_without_scene_set_approval(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_set_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0010"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "script.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "evaluation_contract:",
                        "  target_arc: \"opening\"",
                        "  must_cover: [\"桃太郎\"]",
                        "  must_avoid: []",
                        "scene_set_review:",
                        "  status: \"pending\"",
                        "scene_detail_review:",
                        "  status: \"approved\"",
                        "cut_blueprint_review:",
                        "  status: \"approved\"",
                        "production_readiness_review:",
                        "  status: \"approved\"",
                        "script:",
                        "  scenes:",
                        "    - scene_id: 1",
                        "      phase: \"opening\"",
                        "      summary: \"桃太郎の導入です。十分な長さの本文です。十分な長さの本文です。\"",
                        "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                        "      scene_intent:",
                        "        story_purpose: \"導入\"",
                        "        audience_information: [\"桃太郎\"]",
                        "        withheld_information: []",
                        "        reveal_constraints: []",
                        "        affect_transition: \"hook\"",
                        "        visual_value_source: \"none\"",
                        "        production_risks: []",
                        "        handoff_notes: {p500_asset: [], p600_image: [], p700_narration: [], p800_video: []}",
                        "      agent_review: {status: \"passed\"}",
                        "      cuts:",
                        "        - cut_id: 1",
                        "          cut_blueprint:",
                        "            cut_role: \"main\"",
                        "            duration_intent: \"standard\"",
                        "            target_beat: \"桃太郎\"",
                        "            must_show: [\"桃太郎\"]",
                        "            must_avoid: []",
                        "            done_when: [\"導入として読める\"]",
                        "            visual_beat: \"桃太郎の導入\"",
                        "            narration_role: \"setup\"",
                        "            asset_dependency_hint: {character_ids: [\"momotaro\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")
            self.assertFalse(stage["passed"])
            self.assertIn("script.scene_set_review_approved", stage["reason_keys"])

    def test_script_evaluator_fails_without_scene_detail_approval(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_detail_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0011"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "script.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "evaluation_contract:",
                        "  target_arc: \"opening\"",
                        "  must_cover: [\"桃太郎\"]",
                        "  must_avoid: []",
                        "scene_set_review:",
                        "  status: \"approved\"",
                        "scene_detail_review:",
                        "  status: \"pending\"",
                        "cut_blueprint_review:",
                        "  status: \"approved\"",
                        "production_readiness_review:",
                        "  status: \"approved\"",
                        "script:",
                        "  scenes:",
                        "    - scene_id: 1",
                        "      phase: \"opening\"",
                        "      summary: \"桃太郎の導入です。十分な長さの本文です。十分な長さの本文です。\"",
                        "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                        "      scene_intent:",
                        "        story_purpose: \"導入\"",
                        "        audience_information: [\"桃太郎\"]",
                        "        withheld_information: []",
                        "        reveal_constraints: []",
                        "        affect_transition: \"hook\"",
                        "        visual_value_source: \"none\"",
                        "        production_risks: []",
                        "        handoff_notes: {p500_asset: [], p600_image: [], p700_narration: [], p800_video: []}",
                        "      agent_review: {status: \"passed\"}",
                        "      cuts:",
                        "        - cut_id: 1",
                        "          cut_blueprint:",
                        "            cut_role: \"main\"",
                        "            duration_intent: \"standard\"",
                        "            target_beat: \"桃太郎\"",
                        "            must_show: [\"桃太郎\"]",
                        "            must_avoid: []",
                        "            done_when: [\"導入として読める\"]",
                        "            visual_beat: \"桃太郎の導入\"",
                        "            narration_role: \"setup\"",
                        "            asset_dependency_hint: {character_ids: [\"momotaro\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")
            self.assertFalse(stage["passed"])
            self.assertIn("script.scene_detail_review_approved", stage["reason_keys"])

    def test_script_evaluator_fails_without_cut_blueprint_approval(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_cut_blueprint_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0012"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "script.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "evaluation_contract:",
                        "  target_arc: \"opening\"",
                        "  must_cover: [\"桃太郎\"]",
                        "  must_avoid: []",
                        "scene_set_review:",
                        "  status: \"approved\"",
                        "scene_detail_review:",
                        "  status: \"approved\"",
                        "cut_blueprint_review:",
                        "  status: \"pending\"",
                        "production_readiness_review:",
                        "  status: \"approved\"",
                        "script:",
                        "  scenes:",
                        "    - scene_id: 1",
                        "      phase: \"opening\"",
                        "      summary: \"桃太郎の導入です。十分な長さの本文です。十分な長さの本文です。\"",
                        "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                        "      scene_intent:",
                        "        story_purpose: \"導入\"",
                        "        audience_information: [\"桃太郎\"]",
                        "        withheld_information: []",
                        "        reveal_constraints: []",
                        "        affect_transition: \"hook\"",
                        "        visual_value_source: \"none\"",
                        "        production_risks: []",
                        "        handoff_notes: {p500_asset: [], p600_image: [], p700_narration: [], p800_video: []}",
                        "      agent_review: {status: \"passed\"}",
                        "      cuts:",
                        "        - cut_id: 1",
                        "          cut_blueprint:",
                        "            cut_role: \"main\"",
                        "            duration_intent: \"standard\"",
                        "            target_beat: \"桃太郎\"",
                        "            must_show: [\"桃太郎\"]",
                        "            must_avoid: []",
                        "            done_when: [\"導入として読める\"]",
                        "            visual_beat: \"桃太郎の導入\"",
                        "            narration_role: \"setup\"",
                        "            asset_dependency_hint: {character_ids: [\"momotaro\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")
            self.assertFalse(stage["passed"])
            self.assertIn("script.cut_blueprint_review_approved", stage["reason_keys"])

    def test_script_evaluator_does_not_require_future_production_readiness_approval(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_production_readiness_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0013"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "script.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "evaluation_contract:",
                        "  target_arc: \"opening\"",
                        "  must_cover: [\"桃太郎\"]",
                        "  must_avoid: []",
                        "scene_set_review:",
                        "  status: \"approved\"",
                        "scene_detail_review:",
                        "  status: \"approved\"",
                        "cut_blueprint_review:",
                        "  status: \"approved\"",
                        "production_readiness_review:",
                        "  status: \"pending\"",
                        "script:",
                        "  scenes:",
                        "    - scene_id: 1",
                        "      phase: \"opening\"",
                        "      summary: \"桃太郎の導入です。十分な長さの本文です。十分な長さの本文です。\"",
                        "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                        "      scene_intent:",
                        "        story_purpose: \"導入\"",
                        "        audience_information: [\"桃太郎\"]",
                        "        withheld_information: []",
                        "        reveal_constraints: []",
                        "        affect_transition: \"hook\"",
                        "        visual_value_source: \"none\"",
                        "        production_risks: []",
                        "        handoff_notes: {p500_asset: [], p600_image: [], p700_narration: [], p800_video: []}",
                        "      agent_review: {status: \"passed\"}",
                        "      cuts:",
                        "        - cut_id: 1",
                        "          cut_blueprint:",
                        "            cut_role: \"main\"",
                        "            duration_intent: \"standard\"",
                        "            target_beat: \"桃太郎\"",
                        "            must_show: [\"桃太郎\"]",
                        "            must_avoid: []",
                        "            done_when: [\"導入として読める\"]",
                        "            visual_beat: \"桃太郎の導入\"",
                        "            narration_role: \"setup\"",
                        "            asset_dependency_hint: {character_ids: [\"momotaro\"], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")
            self.assertNotIn("script.production_readiness_review_approved", stage["reason_keys"])

    def test_script_evaluator_fails_without_scene_readiness_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_readiness_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            text = (run_dir / "script.md").read_text(encoding="utf-8")
            text = text.replace("      handoff_to_next_scene: \"次の場面へつながる\"\n", "", 1)
            text = text.replace("      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, next_scene_connection_checked: true}\n", "", 1)
            (run_dir / "script.md").write_text(text, encoding="utf-8")
            _resolve_ready_grounding(run_dir, "script", flow="immersive")

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.scene_readiness_contract", stage["reason_keys"])

    def test_manifest_evaluator_gates_p400_duration_and_review_integrity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_p400_duration_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0015"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000015\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            _write_valid_immersive_p400_pair(run_dir, target_duration=300, cut_duration=7, scene_count=10)
            (run_dir / "production_readiness_review.md").write_text(
                "status: passed\n\nStructure: ok\nDuration: p700 で後続確認する。\nQuality: ok\n",
                encoding="utf-8",
            )
            _resolve_ready_grounding(run_dir, "manifest", flow="immersive")

            stage, updates = STAGE_EVALUATOR.check_manifest_single(run_dir, "standard", "immersive")

            self.assertFalse(stage["passed"])
            self.assertEqual(updates["eval.p400_readiness.status"], "changes_requested")
            self.assertIn("p400.duration_coverage", stage["reason_keys"])
            self.assertIn("p400.review_report_integrity", stage["reason_keys"])

    def test_manifest_p400_readiness_includes_script_scene_readiness(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_p400_script_ready_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0018"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000018\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            _write_valid_immersive_p400_pair(run_dir, target_duration=300, cut_duration=15, scene_count=10)
            text = (run_dir / "script.md").read_text(encoding="utf-8")
            text = text.replace("      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, next_scene_connection_checked: true}\n", "", 1)
            (run_dir / "script.md").write_text(text, encoding="utf-8")
            _resolve_ready_grounding(run_dir, "manifest", flow="immersive")

            stage, updates = STAGE_EVALUATOR.check_manifest_single(run_dir, "standard", "immersive")

            self.assertFalse(stage["passed"])
            self.assertEqual(updates["eval.p400_readiness.status"], "changes_requested")
            self.assertIn("p400.script_readiness_contract", stage["reason_keys"])

    def test_manifest_evaluator_approves_complete_p400_readiness(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_p400_ready_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0016"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000016\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            _write_valid_immersive_p400_pair(run_dir, target_duration=300, cut_duration=15, scene_count=10)
            _resolve_ready_grounding(run_dir, "manifest", flow="immersive")

            stage, updates = STAGE_EVALUATOR.check_manifest_single(run_dir, "standard", "immersive")

            self.assertTrue(stage["passed"], stage["reason_keys"])
            self.assertEqual(updates["eval.p400_readiness.status"], "approved")

    def test_manifest_evaluator_approves_p400_readiness_for_skeleton_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_p400_skeleton_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0016b"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000016b\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            _write_valid_immersive_p400_pair(run_dir, target_duration=300, cut_duration=15, scene_count=10, manifest_phase="skeleton")
            _resolve_ready_grounding(run_dir, "manifest", flow="immersive")

            stage, updates = STAGE_EVALUATOR.check_manifest_single(run_dir, "standard", "immersive")

            self.assertFalse(stage["passed"])
            self.assertIn("manifest.phase", stage["reason_keys"])
            self.assertEqual(updates["eval.p400_readiness.status"], "approved")
            self.assertEqual(updates["eval.p400_readiness.reason_keys"], "")

    def test_manifest_p400_readiness_requires_explicit_manifest_phase(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_p400_phase_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0016c"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000016c\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            _write_valid_immersive_p400_pair(run_dir, target_duration=300, cut_duration=15, scene_count=10, manifest_phase="skeleton")
            manifest = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            (run_dir / "video_manifest.md").write_text(manifest.replace("manifest_phase: skeleton\n", "", 1), encoding="utf-8")
            _resolve_ready_grounding(run_dir, "manifest", flow="immersive")

            _stage, updates = STAGE_EVALUATOR.check_manifest_single(run_dir, "standard", "immersive")

            self.assertEqual(updates["eval.p400_readiness.status"], "changes_requested")
            self.assertIn("p400.skeleton_manifest_phase", updates["eval.p400_readiness.reason_keys"])

    def test_downstream_grounding_requires_p400_readiness_approval(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_p500_gate_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0017"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000017\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            _write_valid_immersive_p400_pair(run_dir, target_duration=300, cut_duration=15, scene_count=10)
            _ensure_story_ready(run_dir)

            for stage_name in ("asset", "scene_implementation", "narration", "video_generation"):
                result = _run_grounding(run_dir, stage_name, flow="immersive")
                self.assertNotEqual(result.returncode, 0, stage_name)

            append_state_snapshot(run_dir / "state.txt", {"eval.p400_readiness.status": "approved"})
            append_state_snapshot(run_dir / "state.txt", {"review.duration_fit.status": "passed", "review.image.status": "approved", "review.narration.status": "approved"})
            for stage_name in ("asset", "scene_implementation", "narration", "video_generation"):
                result = _run_grounding(run_dir, stage_name, flow="immersive")
                self.assertEqual(result.returncode, 0, msg=stage_name + (result.stderr or result.stdout))

    def test_manifest_evaluator_rejects_immersive_scene_with_single_cut(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_cuts_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0009"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000009\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text(
                "```yaml\nscript:\n  scenes:\n    - scene_id: 1\n      phase: opening\n      summary: \"桃太郎が出発する。\"\n```\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "video_metadata:",
                        "  topic: \"桃太郎\"",
                        "  experience: \"cinematic_story\"",
                        "manifest_phase: production",
                        "scenes:",
                        "  - scene_id: 1",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        scene_contract:",
                        "          target_beat: \"桃太郎\"",
                        "          must_show: [\"桃太郎\"]",
                        "          must_avoid: []",
                        "          done_when: [\"桃太郎が見える\"]",
                        "        image_generation:",
                        "          prompt: \"画面内テキストなし。桃太郎が朝の道を進む。桃太郎の姿、村の道、柔らかな朝日、出発の空気が具体的に見える。\"",
                        "          character_ids: [\"momotaro\"]",
                        "          object_ids: []",
                        "          output: \"assets/scenes/scene1_cut1.png\"",
                        "        video_generation:",
                        "          duration_seconds: 5",
                        "          motion_prompt: \"桃太郎が前へ進む。\"",
                        "        audio:",
                        "          narration:",
                        "            text: \"桃太郎が出発する。\"",
                        "            tool: \"elevenlabs\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            _resolve_ready_grounding(run_dir, "manifest", flow="immersive")

            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/review-manifest-stage.py"), "--run-dir", str(run_dir), "--profile", "standard", "--flow", "immersive", "--fail-on-findings"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1, msg=result.stderr)
            report = (run_dir / "manifest_review.md").read_text(encoding="utf-8")
            self.assertIn("manifest.minimum_scene_cuts", report)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.p400_readiness.status"], "changes_requested")
            self.assertIn("manifest.minimum_scene_cuts", state["eval.p400_readiness.reason_keys"])

    def test_manifest_evaluator_ignores_deleted_cuts_for_minimum_cut_count(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_deleted_cuts_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0013"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000013\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text(
                "```yaml\nscript:\n  scenes:\n    - scene_id: 1\n      phase: opening\n      summary: \"桃太郎が出発する。\"\n```\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "video_metadata:",
                        "  topic: \"桃太郎\"",
                        "  experience: \"cinematic_story\"",
                        "manifest_phase: production",
                        "scenes:",
                        "  - scene_id: 1",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        cut_status: \"active\"",
                        "        scene_contract: {target_beat: \"桃太郎\", must_show: [\"桃太郎\"], must_avoid: [], done_when: [\"桃太郎が見える\"]}",
                        "        image_generation: {prompt: \"画面内テキストなし。桃太郎が朝の道を進む。桃太郎の姿、村の道、柔らかな朝日、出発の空気が具体的に見える。\", character_ids: [\"momotaro\"], object_ids: []}",
                        "        video_generation: {duration_seconds: 5, motion_prompt: \"桃太郎が前へ進む。\"}",
                        "        audio: {narration: {text: \"桃太郎が出発する。\", tool: \"elevenlabs\"}}",
                        "      - cut_id: 2",
                        "        cut_status: \"deleted\"",
                        "        deletion_reason: \"audit trace only\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            _resolve_ready_grounding(run_dir, "manifest", flow="immersive")

            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/review-manifest-stage.py"), "--run-dir", str(run_dir), "--profile", "standard", "--flow", "immersive", "--fail-on-findings"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1, msg=result.stderr)
            report = (run_dir / "manifest_review.md").read_text(encoding="utf-8")
            self.assertIn("manifest.minimum_scene_cuts", report)

    def test_research_evaluator_fails_without_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_fail_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0001"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-03-29T00:00:00+09:00\njob_id=JOB_2026-03-29_000001\ntopic=桃太郎\nstatus=RESEARCH\n---\n",
                encoding="utf-8",
            )
            (run_dir / "research.md").write_text("```yaml\nsources: []\nscene_plan:\n  scenes: []\nstory_baseline:\n  canonical_synopsis:\n    short_summary: \"\"\n    beat_sheet: []\nconflicts: []\nmetadata:\n  confidence_score: 0.1\n```\n", encoding="utf-8")
            _resolve_ready_grounding(run_dir, "research")

            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/review-research-stage.py"), "--run-dir", str(run_dir), "--profile", "standard", "--fail-on-findings"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.research.status"], "changes_requested")

    def test_manifest_evaluator_fails_reveal_constraint_violation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_reveal_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0002"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-03-29T00:00:00+09:00\njob_id=JOB_2026-03-29_000001\ntopic=浦島太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text(
                "```yaml\n"
                "evaluation_contract:\n"
                "  target_arc: \"opening,development\"\n"
                "  must_cover: [\"竜宮城\"]\n"
                "  must_avoid: []\n"
                "  done_when: [\"reveal 順が守られる\"]\n"
                "  reveal_constraints:\n"
                "    - subject_type: \"character\"\n"
                "      subject_id: \"otohime\"\n"
                "      rule: \"must_not_appear_before\"\n"
                "      selector: \"scene05_cut01\"\n"
                "      rationale: \"宴まで乙姫を出さない\"\n"
                "scenes:\n"
                "  - scene_id: 4\n"
                "    phase: \"development\"\n"
                "    scene_summary: \"門が開く。\"\n"
                "    cuts: []\n"
                "```\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "scenes:",
                        "  - scene_id: 4",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        scene_contract:",
                        "          target_beat: \"門が開く\"",
                        "          must_show: [\"門\"]",
                        "          must_avoid: []",
                        "          done_when: [\"到着が読める\"]",
                        "        image_generation:",
                        "          prompt: \"乙姫が門の奥で浦島太郎を迎える。\"",
                        "          character_ids: [\"urashima\", \"otohime\"]",
                        "          object_ids: []",
                        "        video_generation:",
                        "          duration_seconds: 5",
                        "          motion_prompt: \"門へ進む。\"",
                        "        audio:",
                        "          narration:",
                        "            text: \"もんが ひらきます。\"",
                        "            tool: \"elevenlabs\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            _resolve_ready_grounding(run_dir, "image_prompt")

            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/review-manifest-stage.py"), "--run-dir", str(run_dir), "--profile", "standard", "--fail-on-findings"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.manifest.status"], "changes_requested")

    def test_manifest_evaluator_ignores_reference_scenes_for_narration_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_reference_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0005"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000003\ntopic=浦島太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text(
                "```yaml\n"
                "evaluation_contract:\n"
                "  target_arc: \"opening,development\"\n"
                "  must_cover: [\"竜宮城\"]\n"
                "  must_avoid: []\n"
                "  done_when: [\"manifest が scene/cut の契約を満たす\"]\n"
                "scenes:\n"
                "  - scene_id: 4\n"
                "    phase: \"development\"\n"
                "    scene_summary: \"門が開く。\"\n"
                "    cuts:\n"
                "      - cut_id: 1\n"
                "        narration: \"もんが ひらきます。\"\n"
                "        tts_text: \"もんが ひらきます。\"\n"
                "        visual_beat: \"門が開く\"\n"
                "```\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "scenes:",
                        "  - scene_id: 4",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        scene_contract:",
                        "          target_beat: \"門が開く\"",
                        "          must_show: [\"門\"]",
                        "          must_avoid: []",
                        "          done_when: [\"到着が読める\"]",
                        "        image_generation:",
                        "          prompt: \"門が開く瞬間。竜宮城の巨大な門がゆっくり開き、金の扉、珊瑚の柱、海底の青い反射光、石畳の前景まで明確に見える。門の前で浦島太郎が立ち止まり、これから内部へ入ることが一目で分かる。\"",
                        "          character_ids: [\"urashima\"]",
                        "          object_ids: []",
                        "        video_generation:",
                        "          duration_seconds: 5",
                        "          motion_prompt: \"門へ進む。\"",
                        "        audio:",
                        "          narration:",
                        "            text: \"もんが ひらきます。\"",
                        "            tool: \"elevenlabs\"",
                        "  - scene_id: \"otohime_reference\"",
                        "    kind: \"character_reference\"",
                        "    image_generation:",
                        "      prompt: \"乙姫のキャラクター参照。\"",
                        "      character_ids: [\"otohime\"]",
                        "      object_ids: []",
                        "      output: \"assets/characters/otohime/reference.png\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            _resolve_ready_grounding(run_dir, "image_prompt")

            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/review-manifest-stage.py"), "--run-dir", str(run_dir), "--profile", "standard"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.manifest.status"], "approved")
            self.assertEqual(state["eval.manifest.reason_keys"], "")

    def test_manifest_evaluator_fails_unexpanded_human_change_request_with_dotted_ids(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_hcr_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0003"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000001\ntopic=浦島太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text(
                "```yaml\n"
                "human_change_requests:\n"
                "  - request_id: \"REQ-1\"\n"
                "    status: \"pending\"\n"
                "    normalized_actions:\n"
                "      - action: \"update_narration\"\n"
                "        target:\n"
                "          scene_id: \"10.1\"\n"
                "          cut_id: \"2.3\"\n"
                "        payload:\n"
                "          text: \"あたらしい ないようです。\"\n"
                "evaluation_contract:\n"
                "  target_arc: \"opening,development\"\n"
                "  must_cover: [\"竜宮城\"]\n"
                "  must_avoid: []\n"
                "  done_when: [\"human review request が manifest へ反映される\"]\n"
                "scenes:\n"
                "  - scene_id: \"10.1\"\n"
                "    phase: \"development\"\n"
                "    scene_summary: \"竜宮城へ足を踏み入れる。\"\n"
                "    cuts:\n"
                "      - cut_id: \"2.3\"\n"
                "        narration: \"げんこうの ないようです。\"\n"
                "        tts_text: \"げんこうの ないようです。\"\n"
                "        human_review:\n"
                "          status: \"changes_requested\"\n"
                "          notes: \"言い回しを変える\"\n"
                "          approved_narration: \"\"\n"
                "          approved_tts_text: \"\"\n"
                "          change_request_ids: [\"REQ-1\"]\n"
                "```\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "scenes:",
                        "  - scene_id: \"10.1\"",
                        "    cuts:",
                        "      - cut_id: \"2.3\"",
                        "        scene_contract:",
                        "          target_beat: \"竜宮城\"",
                        "          must_show: [\"竜宮城\"]",
                        "          must_avoid: []",
                        "          done_when: [\"到着が読める\"]",
                        "        image_generation:",
                        "          prompt: \"竜宮城の回廊へ浦島太郎が足を踏み入れる。珊瑚の柱、青い水光、金の欄干、奥へ続く広い通路、床へ反射する波紋、静かな歓迎の空気まで具体的に見える。\"",
                        "          character_ids: [\"urashima\"]",
                        "          object_ids: []",
                        "        video_generation:",
                        "          duration_seconds: 5",
                        "          motion_prompt: \"回廊を進む。\"",
                        "        audio:",
                        "          narration:",
                        "            text: \"げんこうの ないようです。\"",
                        "            tool: \"elevenlabs\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            _resolve_ready_grounding(run_dir, "image_prompt")

            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/review-manifest-stage.py"), "--run-dir", str(run_dir), "--profile", "standard", "--fail-on-findings"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.manifest.status"], "changes_requested")
            self.assertIn("manifest.human_change_request_missing_from_manifest", state["eval.manifest.reason_keys"])
            self.assertIn("manifest.human_change_request_trace_missing", state["eval.manifest.reason_keys"])
            review = (run_dir / "manifest_review.md").read_text(encoding="utf-8")
            self.assertIn("scene10.1_cut2.3", review)
            self.assertIn("manifest.human_change_request_missing_from_manifest", review)

    def test_manifest_evaluator_accepts_verified_human_change_request_with_dotted_ids(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_hcr_ok_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0004"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000002\ntopic=浦島太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text(
                "```yaml\n"
                "human_change_requests:\n"
                "  - request_id: \"REQ-1\"\n"
                "    status: \"verified\"\n"
                "    normalized_actions:\n"
                "      - action: \"update_narration\"\n"
                "        target:\n"
                "          scene_id: \"10.1\"\n"
                "          cut_id: \"2.3\"\n"
                "        payload:\n"
                "          text: \"あたらしい ないようです。\"\n"
                "evaluation_contract:\n"
                "  target_arc: \"opening,development\"\n"
                "  must_cover: [\"竜宮城\"]\n"
                "  must_avoid: []\n"
                "  done_when: [\"human review request が manifest へ反映される\"]\n"
                "scenes:\n"
                "  - scene_id: \"10.1\"\n"
                "    phase: \"development\"\n"
                "    scene_summary: \"竜宮城へ足を踏み入れる。\"\n"
                "    cuts:\n"
                "      - cut_id: \"2.3\"\n"
                "        narration: \"あたらしい ないようです。\"\n"
                "        tts_text: \"あたらしい ないようです。\"\n"
                "        human_review:\n"
                "          status: \"changes_requested\"\n"
                "          notes: \"言い回しを変える\"\n"
                "          approved_narration: \"\"\n"
                "          approved_tts_text: \"\"\n"
                "          change_request_ids: [\"REQ-1\"]\n"
                "```\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "human_change_requests:",
                        "  - request_id: \"REQ-1\"",
                        "    status: \"verified\"",
                        "scenes:",
                        "  - scene_id: \"10.1\"",
                        "    cuts:",
                        "      - cut_id: \"2.3\"",
                        "        implementation_trace:",
                        "          source_request_ids: [\"REQ-1\"]",
                        "          status: \"implemented\"",
                        "        scene_contract:",
                        "          target_beat: \"竜宮城\"",
                        "          must_show: [\"竜宮城\"]",
                        "          must_avoid: []",
                        "          done_when: [\"到着が読める\"]",
                        "        image_generation:",
                        "          prompt: \"竜宮城の回廊へ浦島太郎が足を踏み入れる。珊瑚の柱、青い水光、金の欄干、奥へ続く広い通路、床へ反射する波紋、静かな歓迎の空気まで具体的に見える。\"",
                        "          character_ids: [\"urashima\"]",
                        "          object_ids: []",
                        "          applied_request_ids: [\"REQ-1\"]",
                        "        video_generation:",
                        "          duration_seconds: 5",
                        "          motion_prompt: \"回廊を進む。\"",
                        "          applied_request_ids: [\"REQ-1\"]",
                        "        audio:",
                        "          narration:",
                        "            text: \"あたらしい ないようです。\"",
                        "            tool: \"elevenlabs\"",
                        "            applied_request_ids: [\"REQ-1\"]",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            _resolve_ready_grounding(run_dir, "image_prompt")

            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/review-manifest-stage.py"), "--run-dir", str(run_dir), "--profile", "standard"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.manifest.status"], "approved")
            self.assertEqual(state["eval.manifest.reason_keys"], "")

    def test_manifest_evaluator_fails_unresolved_human_change_request(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_human_change_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0003"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-03-29T00:00:00+09:00\njob_id=JOB_2026-03-29_000001\ntopic=浦島太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "human_change_requests:",
                        "  - request_id: \"req-7\"",
                        "    status: \"pending\"",
                        "scenes:",
                        "  - scene_id: 3.1",
                        "    cuts:",
                        "      - cut_id: 2.1",
                        "        implementation_trace:",
                        "          source_request_ids: [\"req-7\"]",
                        "          status: \"pending\"",
                        "        scene_contract:",
                        "          target_beat: \"神殿へ向かう\"",
                        "          must_show: [\"神殿\"]",
                        "          must_avoid: []",
                        "          done_when: [\"神殿が映る\"]",
                        "        image_generation:",
                        "          prompt: \"神殿の入口。\"",
                        "          character_ids: []",
                        "          object_ids: []",
                        "          applied_request_ids: []",
                        "        video_generation:",
                        "          duration_seconds: 5",
                        "          motion_prompt: \"前進する。\"",
                        "          applied_request_ids: []",
                        "        audio:",
                        "          narration:",
                        "            text: \"しんでんへ むかいます。\"",
                        "            tool: \"elevenlabs\"",
                        "            applied_request_ids: []",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            _resolve_ready_grounding(run_dir, "image_prompt")

            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/review-manifest-stage.py"), "--run-dir", str(run_dir), "--profile", "standard", "--fail-on-findings"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.manifest.status"], "changes_requested")
