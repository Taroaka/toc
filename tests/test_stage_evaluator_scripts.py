import subprocess
import sys
import tempfile
import unittest
import json
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, parse_state_file
from toc import stage_evaluator as STAGE_EVALUATOR
from toc.review_loop import REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE


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
            if stage == "scene_set":
                scene_count_gate = [
                    "## Scene Count Gate",
                    "",
                    "- maximal_meaningful_stop_condition: no additional independent scene remains",
                    "- next_scene_candidate: no additional independent scene candidate remains",
                    "- cut_thickening_reason: additional material repeats the same scene turn",
                    "- critic_1_scene_count_coverage_resolution: scene_count_coverage passed",
                    "",
                    "## Scene Specificity Gate",
                    "",
                    "- non_compressible_beat_inventory: approved story beats are inventoried",
                    "- scene_promotion_rule: every promoted scene has its own question, value shift, and causal turn",
                    "- unique_scene_responsibility: each scene owns a distinct story obligation",
                    "- actor_force_coverage: protagonist, opposing/helper, and witness forces are covered where story-relevant",
                    "- object_meaning_ladder: story objects and setpieces have staged meaning",
                    "- concrete_handoff_chain: handoff is visible or audible, not narration-only",
                    "- anti_template_language: banned generic placeholders are absent",
                    "",
                    "## Reveal Order Gate",
                    "",
                    "- reveal_order_preserved: approved reveal order is preserved",
                    "- withheld_information_preserved: future-only information remains withheld",
                    "- early_reveal_risk_resolved: no payoff evidence leaks early",
                    "",
                    "## Handoff Chain Gate",
                    "",
                    "- handoff_chain_coverage: each scene ending causes the next scene",
                    "- incoming_outgoing_anchor_ids: concrete anchor ids are present",
                    "- terminal_resolution_checked: final scene uses terminal_resolution",
                    "",
                ]
            elif stage == "scene_detail":
                scene_count_gate = [
                    "## Scene Detail Gate",
                    "",
                    "- scene_necessity: each scene owns a non-compressible beat",
                    "- internal_pressure: pressure escalates before the turn",
                    "- value_shift_visibility: value shift is visible",
                    "- causal_turn_visibility: causal turn is visible",
                    "- scene_event_sequence: setup, pressure, turn, and payoff are present",
                    "- turning_event_alignment: turning_event matches scene_intent.causal_turn",
                    "- end_situation_alignment: end_situation matches scene_intent.value_shift.to",
                    "- neighbor_handoff: neighboring handoffs are checked",
                    "",
                ]
            else:
                scene_count_gate = [
                    "## Cut Blueprint Gate",
                    "",
                    "- cut_intent_isolation: passed",
                    "- scene_event_coverage: passed",
                    "- event_beat_reference_integrity: passed",
                    "- first_frame_motion_readiness: passed",
                    "- event_first_frame_alignment: passed",
                    "- multimodal_event_boundary_coverage: passed",
                    "- source_event_preservation: passed",
                    "- no_unapproved_event_invention: passed",
                    "- event_motion_boundary: passed",
                    "- event_narration_boundary: passed",
                    "- event_context_for_cut_ready: passed",
                    "- causal_proof_coverage: passed",
                    "- role_coverage: passed",
                    "- audience_knowledge_delta_coverage: passed",
                    "- anti_redundancy_gate: passed",
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


def _valid_scene_intent_lines(topic: str, scene_idx: int, *, terminal: bool, indent: str = "      ") -> list[str]:
    next_selector = f"scene{scene_idx + 1}" if not terminal else ""
    outgoing_anchor_type = "terminal" if terminal else "question"
    return [
        f"{indent}scene_intent:",
        f"{indent}  story_purpose: \"{topic}の不可逆な一歩を映画的に見せる\"",
        f"{indent}  dramatic_question: \"{topic}は目の前の圧力を受けて次の責務を選べるか\"",
        f"{indent}  scene_spine: \"村道の静けさから圧力が増し、{topic}が具体的な選択をして痕跡を残す\"",
        f"{indent}  value_shift:",
        f"{indent}    from: \"ためらいが残る状態\"",
        f"{indent}    to: \"次の責務へ踏み出した状態\"",
        f"{indent}    visible_evidence: [\"足跡\", \"握られたきびだんご袋\"]",
        f"{indent}  causal_turn: \"{topic}が村道で袋を握り直し、後戻りせず進む決断を見せる\"",
        f"{indent}  audience_information: [\"{topic}が旅の責務を受け入れる\"]",
        f"{indent}  withheld_information: [\"結末の勝敗\"]",
        f"{indent}  reveal_constraints: [\"鬼との決着はまだ見せない\"]",
        f"{indent}  affect_transition: \"静かな不安から決意へ移る\"",
        f"{indent}  character_state:",
        f"{indent}    start: \"村道で迷いが残る\"",
        f"{indent}    end: \"袋を握り、視線が前に固定される\"",
        f"{indent}    visible_behavior: [\"袋を握る\", \"足を前へ出す\"]",
        f"{indent}  visual_thesis: \"朝霧の村道で、{topic}の足跡ときびだんご袋が決意の証拠になる\"",
        f"{indent}  visual_value_source: \"none\"",
        f"{indent}  production_risks: []",
        f"{indent}  scene_conflict_engine:",
        f"{indent}    desire: \"責務を果たすため前へ進む\"",
        f"{indent}    obstacle: \"村を離れる不安と見えない敵の圧力\"",
        f"{indent}    stakes: \"踏み出せなければ村を守る約束が宙に浮く\"",
        f"{indent}    escalation: \"朝霧の奥から村人の視線と沈黙が重くなる\"",
        f"{indent}    no_return_point: \"{topic}が袋を握り直して村道を越える\"",
        f"{indent}    visible_pressure: [\"村人の視線\", \"霧の奥へ伸びる道\"]",
        f"{indent}  audience_knowledge_delta:",
        f"{indent}    before_scene: [\"{topic}が旅に出る物語である\"]",
        f"{indent}    learned_during_scene: [\"{topic}が自分の意思で責務を引き受ける\"]",
        f"{indent}    still_unknown_after_scene: [\"鬼との決着\"]",
        f"{indent}    forbidden_early_reveals: [\"勝利の証拠\"]",
        f"{indent}  handoff_chain:",
        f"{indent}    incoming:",
        f"{indent}      anchor_id: \"scene{scene_idx}_incoming_mist\"",
        f"{indent}      anchor_type: \"sound\"",
        f"{indent}      visible_or_audible_form: \"朝霧の中の村の沈黙\"",
        f"{indent}    outgoing:",
        f"{indent}      anchor_id: \"scene{scene_idx}_footprint\"",
        f"{indent}      anchor_type: \"{outgoing_anchor_type}\"",
        f"{indent}      next_scene_selector: \"{next_selector}\"",
        f"{indent}      required_next_scene_start_pressure: \"足跡と握られたきびだんご袋が、村人の視線を背に山道へ向かわせる\"",
        f"{indent}  object_arc:",
        f"{indent}    - object_id: \"kibidango_bag\"",
        f"{indent}      first_meaning: \"旅の支え\"",
        f"{indent}      current_scene_meaning: \"決意の物証\"",
        f"{indent}      later_meaning: \"仲間を得る契機\"",
        f"{indent}      visible_state_in_this_scene: \"腰で揺れる小袋\"",
        f"{indent}      must_not_show_yet: [\"勝利の証拠\"]",
        f"{indent}  story_specificity:",
        f"{indent}    non_compressible_beat: \"{topic}が責務を自分の行為として引き受ける\"",
        f"{indent}    scene_promotion_reason: \"独立した問い、決意への価値変化、村道を越える因果 turn を持つ\"",
        f"{indent}    unique_scene_responsibility: \"旅の責務が口約束から身体行為へ変わる瞬間を担う\"",
        f"{indent}    actor_forces:",
        f"{indent}      protagonist: \"{topic}\"",
        f"{indent}      opposing: [\"見えない鬼の脅威\"]",
        f"{indent}      helping: [\"村人の沈黙\"]",
        f"{indent}      observing: [\"道端の子ども\"]",
        f"{indent}      pressure_method: \"村人の視線と霧の道が後戻りできない圧力を作る\"",
        f"{indent}    meaning_ladder:",
        f"{indent}      protagonist_stage: \"受け身から能動へ\"",
        f"{indent}      relationship_stage: \"村との関係が保護から責務へ移る\"",
        f"{indent}      object_or_setpiece_stage: \"きびだんご袋が旅の証拠になる\"",
        f"{indent}    concrete_handoff:",
        f"{indent}      incoming_trigger: \"村の沈黙と朝霧\"",
        f"{indent}      outgoing_anchor: \"足跡と握られた袋\"",
        f"{indent}      outgoing_pressure: \"足跡が残るため次の移動が避けられない\"",
        f"{indent}    anti_template_language:",
        f"{indent}      banned_generic_phrases_absent: true",
        f"{indent}      story_specific_terms: [\"{topic}\", \"きびだんご袋\", \"村道\"]",
        f"{indent}      specificity_note: \"人物、道具、場所、行為を明示する\"",
        f"{indent}  handoff_notes: {{p500_asset: [\"momotaro\", \"kibidango_bag\"], p600_image: [\"足跡と袋を見せる\"], p700_narration: [\"決意を補う\"], p800_video: [\"袋を握る動き\"]}}",
    ]


def _valid_scene_event_lines(topic: str, scene_idx: int, *, indent: str = "      ") -> list[str]:
    return [
        f"{indent}scene_event:",
        f"{indent}  schema_version: \"scene_event_v1\"",
        f"{indent}  event_logline: \"{topic}が村道で迷いを越え、次へ進む証拠を残す\"",
        f"{indent}  start_situation: \"{topic}は村道で旅立ちをためらい、村人の視線を受けている\"",
        f"{indent}  source_story_beat_ids: [\"story_scene{scene_idx}_departure\"]",
        f"{indent}  event_sequence:",
        f"{indent}    - beat_id: \"scene{scene_idx}_event_setup\"",
        f"{indent}      beat_function: \"setup\"",
        f"{indent}      source_story_beat_ids: [\"story_scene{scene_idx}_departure\"]",
        f"{indent}      what_happens: \"{topic}が村道に立ち、腰の袋と伸びる道が見える\"",
        f"{indent}      visible_action: \"{topic}が村道の入口で足を止める\"",
        f"{indent}      visible_reaction: \"村人が黙って見守る\"",
        f"{indent}      immediate_consequence: \"旅立ちの圧力が画面に生まれる\"",
        f"{indent}      emotional_pressure: \"ためらいと責務が同時に見える\"",
        f"{indent}      required_visual_evidence: [\"村道\", \"旅袋\", \"村人の視線\"]",
        f"{indent}      story_information_revealed_ids: [\"departure_pressure\"]",
        f"{indent}    - beat_id: \"scene{scene_idx}_event_pressure\"",
        f"{indent}      beat_function: \"pressure\"",
        f"{indent}      source_story_beat_ids: [\"story_scene{scene_idx}_departure\"]",
        f"{indent}      what_happens: \"霧の道と沈黙が{topic}に後戻りできない圧力をかける\"",
        f"{indent}      visible_action: \"{topic}が袋を握る手に力を入れる\"",
        f"{indent}      visible_reaction: \"道端の子どもが息をのむ\"",
        f"{indent}      immediate_consequence: \"迷いが行為へ変わり始める\"",
        f"{indent}      emotional_pressure: \"見えない敵への不安が高まる\"",
        f"{indent}      required_visual_evidence: [\"握られた袋\", \"霧\", \"止まった足\"]",
        f"{indent}      story_information_revealed_ids: [\"choice_pressure\"]",
        f"{indent}    - beat_id: \"scene{scene_idx}_event_turn\"",
        f"{indent}      beat_function: \"turn\"",
        f"{indent}      source_story_beat_ids: [\"story_scene{scene_idx}_departure\"]",
        f"{indent}      what_happens: \"{topic}が袋を握り直し、村道を越える決断を行動にする\"",
        f"{indent}      visible_action: \"{topic}が最初の一歩を前へ出す\"",
        f"{indent}      visible_reaction: \"村人の視線が足跡へ集まる\"",
        f"{indent}      immediate_consequence: \"後戻りできない足跡が残る\"",
        f"{indent}      emotional_pressure: \"不安が決意へ変わる\"",
        f"{indent}      required_visual_evidence: [\"一歩\", \"足跡\", \"握られた袋\"]",
        f"{indent}      story_information_revealed_ids: [\"departure_decision\"]",
        f"{indent}    - beat_id: \"scene{scene_idx}_event_payoff\"",
        f"{indent}      beat_function: \"payoff\"",
        f"{indent}      source_story_beat_ids: [\"story_scene{scene_idx}_departure\"]",
        f"{indent}      what_happens: \"{topic}の足跡と前を向く姿が次の場面の理由になる\"",
        f"{indent}      visible_action: \"{topic}が霧の先へ進む\"",
        f"{indent}      visible_reaction: \"村道に残った足跡が見える\"",
        f"{indent}      immediate_consequence: \"次の移動が避けられなくなる\"",
        f"{indent}      emotional_pressure: \"責務が継続する\"",
        f"{indent}      required_visual_evidence: [\"足跡\", \"前を向く姿\", \"霧の先の道\"]",
        f"{indent}      story_information_revealed_ids: [\"departure_handoff\"]",
        f"{indent}  turning_event:",
        f"{indent}    source_event_beat_id: \"scene{scene_idx}_event_turn\"",
        f"{indent}    causal_turn_ref: \"scene_intent.causal_turn\"",
        f"{indent}    irreversible_change: \"{topic}が旅立ちを身体行為として確定する\"",
        f"{indent}  end_situation:",
        f"{indent}    value_shift_to_ref: \"scene_intent.value_shift.to\"",
        f"{indent}    outcome: \"{topic}は次の責務へ踏み出した状態になる\"",
        f"{indent}    character_position: \"村道の先へ進んでいる\"",
        f"{indent}    object_state: \"袋は握られ、旅の証拠になる\"",
        f"{indent}    relationship_state: \"村との関係が保護から責務へ変わる\"",
        f"{indent}    new_pressure: \"足跡が次の移動を要求する\"",
        f"{indent}    visible_evidence_refs: [\"scene{scene_idx}_event_payoff\"]",
        f"{indent}  offscreen_context: [\"鬼との決着はまだ起きていない\"]",
        f"{indent}  forbidden_event_changes: [\"鬼との決着をこのsceneで起こさない\", \"勝利の証拠を見せない\"]",
    ]


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

    def coverage_plan_lines(scene_idx: int) -> list[str]:
        return [
            "    scene_cut_coverage_plan:",
            "      coverage_strategy: \"reverse_from_scene_event\"",
            "      source_schema_version: \"scene_event_v1\"",
            "      min_cut_count: {by_importance: 3, by_duration: 4, by_event_beats: 4, selected: 4, exception_reason: \"\"}",
            "      event_beat_inventory:",
            f"        - {{beat_id: \"scene{scene_idx}_event_setup\", beat_function: \"setup\", must_be_seen: true, assigned_cut_ids: [\"scene{scene_idx}_cut1\"]}}",
            f"        - {{beat_id: \"scene{scene_idx}_event_pressure\", beat_function: \"pressure\", must_be_seen: true, assigned_cut_ids: [\"scene{scene_idx}_cut2\"]}}",
            f"        - {{beat_id: \"scene{scene_idx}_event_turn\", beat_function: \"turn\", must_be_seen: true, assigned_cut_ids: [\"scene{scene_idx}_cut3\"]}}",
            f"        - {{beat_id: \"scene{scene_idx}_event_payoff\", beat_function: \"payoff\", must_be_seen: true, assigned_cut_ids: [\"scene{scene_idx}_cut4\"]}}",
            "      scene_obligations:",
            "        - obligation_id: \"dramatic_question_01\"",
            "          source: \"dramatic_question\"",
            f"          evidence: \"scene {scene_idx} の問い\"",
            f"          assigned_cut_ids: [\"scene{scene_idx}_cut1\"]",
            "        - obligation_id: \"value_shift_01\"",
            "          source: \"value_shift.visible_evidence\"",
            "          evidence: [\"桃太郎\"]",
            f"          assigned_cut_ids: [\"scene{scene_idx}_cut2\"]",
            "        - obligation_id: \"causal_turn_01\"",
            "          source: \"causal_turn\"",
            f"          evidence: \"scene {scene_idx} の因果\"",
            f"          assigned_cut_ids: [\"scene{scene_idx}_cut3\"]",
            "        - obligation_id: \"handoff_01\"",
            "          source: \"handoff_to_next_scene\"",
            f"          evidence: \"scene {scene_idx} の受け渡し\"",
            f"          assigned_cut_ids: [\"scene{scene_idx}_cut4\"]",
            "      cut_assignments:",
            f"        - {{cut_index: 1, cut_selector: \"scene{scene_idx}_cut1\", obligation_ids: [\"dramatic_question_01\"], cut_function: \"setup\", event_assignment: {{source_event_contract: {{primary_event_beat_id: \"scene{scene_idx}_event_setup\", source_event_beat_ids: [\"scene{scene_idx}_event_setup\"]}}}}, target_beat: \"桃太郎\", visual_proof: \"桃太郎が見える\", audience_knowledge_delta: \"桃太郎を理解する\", causal_proof: \"桃太郎が画面にいる\", required_roles: [\"protagonist\"], anti_redundancy_key: \"scene{scene_idx}:setup\"}}",
            f"        - {{cut_index: 2, cut_selector: \"scene{scene_idx}_cut2\", obligation_ids: [\"value_shift_01\"], cut_function: \"pressure\", event_assignment: {{source_event_contract: {{primary_event_beat_id: \"scene{scene_idx}_event_pressure\", source_event_beat_ids: [\"scene{scene_idx}_event_pressure\"]}}}}, target_beat: \"桃太郎\", visual_proof: \"桃太郎が進む\", audience_knowledge_delta: \"桃太郎の変化を理解する\", causal_proof: \"桃太郎が前を向く\", required_roles: [\"protagonist\"], anti_redundancy_key: \"scene{scene_idx}:pressure\"}}",
            f"        - {{cut_index: 3, cut_selector: \"scene{scene_idx}_cut3\", obligation_ids: [\"causal_turn_01\"], cut_function: \"turn\", event_assignment: {{source_event_contract: {{primary_event_beat_id: \"scene{scene_idx}_event_turn\", source_event_beat_ids: [\"scene{scene_idx}_event_turn\"]}}}}, target_beat: \"桃太郎\", visual_proof: \"桃太郎が決める\", audience_knowledge_delta: \"因果を理解する\", causal_proof: \"決意が行動を生む\", required_roles: [\"protagonist\"], anti_redundancy_key: \"scene{scene_idx}:turn\"}}",
            f"        - {{cut_index: 4, cut_selector: \"scene{scene_idx}_cut4\", obligation_ids: [\"handoff_01\"], cut_function: \"handoff\", event_assignment: {{source_event_contract: {{primary_event_beat_id: \"scene{scene_idx}_event_payoff\", source_event_beat_ids: [\"scene{scene_idx}_event_payoff\"]}}}}, target_beat: \"桃太郎\", visual_proof: \"桃太郎が次へ向く\", audience_knowledge_delta: \"次への理由を理解する\", causal_proof: \"視線が次へ渡る\", required_roles: [\"protagonist\"], anti_redundancy_key: \"scene{scene_idx}:handoff\"}}",
            "      unassigned_obligations: []",
            "      overloaded_cuts: []",
            "      duplicate_meaning_risks: []",
        ]

    def cut_contract_lines(scene_idx: int, cut_idx: int, selector: str) -> list[str]:
        next_anchor = f"scene{scene_idx}_cut{cut_idx}_to_cut{cut_idx + 1}" if cut_idx < 4 else f"scene{scene_idx}_to_next"
        incoming_anchor = f"scene{scene_idx}_incoming" if cut_idx == 1 else f"scene{scene_idx}_cut{cut_idx - 1}_to_cut{cut_idx}"
        incoming_type = "none" if cut_idx == 1 else "gesture"
        outgoing_type = "gesture"
        beat_functions = ["setup", "pressure", "turn", "payoff"]
        beat_function = beat_functions[min(cut_idx - 1, len(beat_functions) - 1)]
        beat_id = f"scene{scene_idx}_event_{beat_function}"
        beat_data = {
            "setup": (
                f"桃太郎が村道に立ち、腰の袋と伸びる道が見える",
                f"桃太郎が村道の入口で足を止める",
                "村人が黙って見守る",
                ["村道", "旅袋", "村人の視線"],
            ),
            "pressure": (
                f"霧の道と沈黙が桃太郎に後戻りできない圧力をかける",
                f"桃太郎が袋を握る手に力を入れる",
                "道端の子どもが息をのむ",
                ["握られた袋", "霧", "止まった足"],
            ),
            "turn": (
                f"桃太郎が袋を握り直し、村道を越える決断を行動にする",
                f"桃太郎が最初の一歩を前へ出す",
                "村人の視線が足跡へ集まる",
                ["一歩", "足跡", "握られた袋"],
            ),
            "payoff": (
                f"桃太郎の足跡と前を向く姿が次の場面の理由になる",
                f"桃太郎が霧の先へ進む",
                "村道に残った足跡が見える",
                ["足跡", "前を向く姿", "霧の先の道"],
            ),
        }
        what_happens, visible_action, visible_reaction, visual_evidence = beat_data[beat_function]
        blocked_ids = [
            f"scene{scene_idx}_event_{function}"
            for function in ("turn", "payoff")
            if function != beat_function
        ]
        neighbor_functions = [
            beat_functions[index]
            for index in (cut_idx - 2, cut_idx)
            if 0 <= index < len(beat_functions)
        ]
        return [
            "        cut_contract:",
            "          schema_version: \"3.0\"",
            "          source_event_contract:",
            f"            primary_event_beat_id: \"{beat_id}\"",
            f"            source_event_beat_ids: [\"{beat_id}\"]",
            f"            event_beat_function: \"{beat_function}\"",
            "            event_time_position: \"before_trigger\"",
            f"            source_event_summary: \"{what_happens}\"",
            f"            source_visible_action: \"{visible_action}\"",
            f"            source_visible_reaction: \"{visible_reaction}\"",
            f"            source_required_visual_evidence: {json.dumps(visual_evidence, ensure_ascii=False)}",
            "            source_story_information_revealed_ids: []",
            "            source_story_information_hinted_ids: []",
            f"            event_facts_to_preserve: {json.dumps([what_happens], ensure_ascii=False)}",
            "            event_facts_not_to_invent: [\"鬼との決着をこのsceneで起こさない\", \"勝利の証拠を見せない\"]",
            "            allowed_reveal_info_ids: []",
            "            forbidden_reveal_info_ids: [\"勝利の証拠\"]",
            "            must_not_change: [\"scene_eventにない出来事を追加しない\"]",
            "          cut_function: \"setup\"",
            "          intent_budget:",
            f"            primary_intent: \"桃太郎 cut {cut_idx}\"",
            f"            assigned_obligation_ids: [\"obligation_{cut_idx}\"]",
            "            secondary_intents_allowed: []",
            "            forbidden_combined_intents: [\"new_location_establishing + major_reveal + next_scene_handoff\"]",
            "            overload_exception_reason: \"\"",
            "          viewer_contract:",
            "            target_beat: \"桃太郎\"",
            "            screen_question: \"桃太郎は何をするか\"",
            "            dramatic_job: \"sceneの意味を一つ進める\"",
            "            audience_knowledge_delta: \"桃太郎の状態を理解する\"",
            "            causal_proof: \"桃太郎が画面にいて前へ進む\"",
            "            visual_evidence: [\"桃太郎\"]",
            "            required_roles: [\"protagonist\"]",
            f"            anti_redundancy_key: \"scene{scene_idx}:cut{cut_idx}\"",
            "            visual_proof: \"桃太郎が見える\"",
            "            must_show: [\"桃太郎\"]",
            "            must_avoid: []",
            "            done_when: [\"桃太郎が見える\"]",
            "          cinematic_contract:",
            "            camera_intent: \"桃太郎へ視線を導く\"",
            "            subject_priority: {primary: \"桃太郎\", secondary: \"道\", background: \"村\"}",
            "            screen_geography: {foreground: \"土の道\", midground: \"桃太郎\", background: \"村\", screen_direction: \"left_to_right\"}",
            "          continuity_contract:",
            "            start_state: {character_state: \"歩く前\", prop_state: \"袋が見える\", spatial_state: \"村道\", time_state: \"朝\"}",
            "            end_state: {character_state: \"前へ向く\", prop_state: \"袋が残る\", spatial_state: \"村道\", time_state: \"朝\"}",
            "            carry_forward_to_next_cut: [\"桃太郎\", \"村道\"]",
            "          cut_handoff:",
            "            receives_from_previous:",
            f"              anchor_id: \"{incoming_anchor}\"",
            f"              anchor_type: \"{incoming_type}\"",
            "              visible_or_audible_form: \"前cutから残る視線\"",
            f"              expected_previous_cut_selector: \"{'scene' + str(scene_idx) + '_cut' + str(cut_idx - 1) if cut_idx > 1 else ''}\"",
            "            delivers_to_next:",
            f"              anchor_id: \"{next_anchor}\"",
            f"              anchor_type: \"{outgoing_type}\"",
            "              visible_or_audible_form: \"次へ残る視線\"",
            f"              expected_next_cut_selector: \"{'scene' + str(scene_idx) + '_cut' + str(cut_idx + 1) if cut_idx < 4 else ''}\"",
            "          first_frame_contract:",
            "            imageable: true",
            f"            source_event_beat_id: \"{beat_id}\"",
            "            event_time_position: \"before_trigger\"",
            f"            event_fact_visible_in_still: \"{visible_action}\"",
            "            not_yet_happened_in_still: [\"鬼との決着\"]",
            "            first_frame_brief: \"桃太郎が村道に立つ\"",
            "            visible_start_state: {character_state: \"歩く前\", prop_state: \"袋が見える\", spatial_state: \"村道\", emotional_state: \"決意\", gaze_or_attention: \"前方\"}",
            "            motion_start_affordance: {movable_subject: \"桃太郎\", movement_vector: \"left_to_right\", camera_start_reason: \"道が奥へ続く\"}",
            "            action_completion_state: \"pre_action\"",
            "            static_first_frame_rule: \"静止画として桃太郎の状態が読める\"",
            "            must_be_static_evidence_not_motion: true",
            "          motion_contract:",
            "            movable: true",
            f"            source_event_beat_id: \"{beat_id}\"",
            "            starts_from_first_frame: true",
            "            reaches_event_position: \"early_action\"",
            f"            must_not_advance_to_event_beat_ids: {json.dumps(blocked_ids, ensure_ascii=False)}",
            "            must_not_resolve_scene_turn_unless_primary_event_is_turn: true",
            "            motion_brief: \"桃太郎が前へ進む\"",
            "            start_from_visible_state: \"first_frame_contract.visible_start_state\"",
            "            end_state: \"桃太郎が次へ向く\"",
            "            end_frame_brief: \"桃太郎が次へ向く\"",
            "            must_not_add: [\"新しい人物\"]",
            "          narration_contract:",
            f"            source_event_beat_ids: [\"{beat_id}\"]",
            "            allowed_info_ids: []",
            "            forbidden_info_ids: [\"勝利の証拠\"]",
            f"            must_not_advance_to_event_beat_ids: {json.dumps(blocked_ids, ensure_ascii=False)}",
            "            must_not_explain_visible_action_as_caption: true",
            "            narration_event_boundary: \"same_event_only\"",
            "            role: \"emotion\"",
            "            target_function: \"絵を説明せず決意を補う\"",
            "            must_avoid: [\"映像のキャプション化\"]",
            "            silence_reason: \"\"",
            "          rhythm_contract:",
            "            expected_duration_seconds: 12",
            "            pacing: \"standard\"",
            "            comprehension_moment: \"桃太郎が見えた瞬間\"",
            "            cut_out_reason: \"次への視線が残る\"",
            "            audio_visual_sync_point: \"視線の後に声が入る\"",
            "            duration_exception: {allowed: false, reason: \"\"}",
            "          asset_dependency:",
            "            character_ids_required: [\"momotaro\"]",
            "            object_ids_required: []",
            "            location_ids_required: [\"village_road\"]",
            "            variant_ids_required: []",
            "            new_asset_requests: []",
            "            reusable_anchor_ids: [\"momotaro\", \"village_road\"]",
            "          downstream_handoff:",
            "            p500_asset: {required_asset_ids: [\"momotaro\", \"village_road\"], asset_candidates: [\"momotaro\", \"village_road\"], continuity_anchor_needed: true, new_asset_needed: false, reuse_allowed: true}",
            "            p600_image: {prompt_requirements: [\"桃太郎\"], reference_requirements: [], first_frame_must_include: [\"桃太郎\"], first_frame_must_avoid: []}",
            "            p700_narration: {narration_requirements: [\"決意を補う\"], role: \"emotion\", must_not_caption_visible_content: true}",
            "            p800_video: {motion_requirements: [\"桃太郎が前へ進む\"], start_state: \"歩く前\", last_frame_or_end_state: \"桃太郎が次へ向く\", must_not_add: [\"新しい人物\"]}",
            "            carries_to_next_cut: [\"桃太郎\"]",
            "            carries_to_next_scene: []",
            "          event_context_for_cut:",
            "            derived_from: [\"scene_event.event_sequence[]\", \"cut_contract.source_event_contract\"]",
            "            editable: false",
            "            primary_event_beat:",
            f"              beat_id: \"{beat_id}\"",
            f"              beat_function: \"{beat_function}\"",
            f"              what_happens: \"{what_happens}\"",
            f"              visible_action: \"{visible_action}\"",
            f"              visible_reaction: \"{visible_reaction}\"",
            f"              required_visual_evidence: {json.dumps(visual_evidence, ensure_ascii=False)}",
            "            source_event_beats:",
            f"              - {{beat_id: \"{beat_id}\"}}",
            "            neighboring_event_beats:",
            *[f"              - {{beat_id: \"scene{scene_idx}_event_{function}\"}}" for function in neighbor_functions],
            "            forbidden_event_changes: [\"鬼との決着をこのsceneで起こさない\", \"勝利の証拠を見せない\"]",
            "            reveal_constraints_for_this_cut: []",
        ]

    for scene_idx in range(1, scene_count + 1):
        terminal = scene_idx == scene_count
        phase = "opening" if scene_idx <= max(1, scene_count // 3) else "development" if scene_idx <= max(2, (scene_count * 2) // 3) else "climax"
        script_lines.extend(
            [
                f"    - scene_id: {scene_idx}",
                f"      phase: \"{phase}\"",
                "      importance: \"medium\"",
                "      summary: \"桃太郎が進む。十分な長さの本文です。十分な長さの本文です。\"",
                "      target_duration_seconds: 30",
                "      estimated_duration_seconds: 30",
                ("      terminal_resolution: \"物語が締まる\"" if terminal else "      handoff_to_next_scene: \"次の場面へつながる\""),
                "      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, value_shift_visible: true, causal_turn_visible: true, scene_specificity_gate_passed: true, next_scene_connection_checked: true}",
                "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                *_valid_scene_intent_lines("桃太郎", scene_idx, terminal=terminal),
                *_valid_scene_event_lines("桃太郎", scene_idx),
                *[line.replace("    ", "      ", 1) for line in coverage_plan_lines(scene_idx)],
                "      agent_review: {status: \"passed\"}",
                "      cuts:",
            ]
        )
        manifest_lines.extend(
            [
                f"  - scene_id: {scene_idx}",
                "    importance: \"medium\"",
                "    target_duration_seconds: 30",
                "    estimated_duration_seconds: 30",
                "    scene_composite_review: {status: \"passed\", scene_obligation_covered_by_cut_group: true, no_duplicate_story_fact_without_new_evidence: true, scene_meaning_visualized_across_cuts: true, blocking_reason_keys: []}",
                *_valid_scene_event_lines("桃太郎", scene_idx, indent="    "),
                *coverage_plan_lines(scene_idx),
                "    cuts:",
            ]
        )
        for cut_idx in range(1, 5):
            selector = f"scene{scene_idx}_cut{cut_idx}"
            script_lines.extend(
                [
                    f"        - cut_id: {cut_idx}",
                    f"          selector: \"{selector}\"",
                    *[line.replace("        ", "          ", 1) for line in cut_contract_lines(scene_idx, cut_idx, selector)],
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
                    *cut_contract_lines(scene_idx, cut_idx, selector),
                    "        scene_contract: {target_beat: \"桃太郎\", must_show: [\"桃太郎\"], must_avoid: [], done_when: [\"桃太郎が見える\"]}",
                    "        image_generation:",
                    "          prompt: \"画面内テキストなし。実写映画風の村道。前景に湿った土と小石、中央に桃太郎の顔と衣装、腰のきびだんご袋、背景に朝霧の村と山並み、横から柔らかな朝日、布の質感、足元の影、次へ進む緊張まで具体的に見える。\"",
                    "          character_ids: [\"momotaro\"]",
                    "          object_ids: []",
                    f"          output: \"assets/scenes/{selector}.png\"",
                    "          review:",
                    "            triangulation_review: {status: \"passed\", same_target_beat: true, image_supports_motion_start: true, motion_reaches_declared_end_state: true, narration_not_captioning_image: true, reveal_constraints_preserved: true, continuity_preserved: true, handoff_visible_or_audible: true}",
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


def _read_script_yaml(run_dir: Path) -> dict:
    _, data = STAGE_EVALUATOR.load_structured_document(run_dir / "script.md")
    return data if isinstance(data, dict) else {}


def _write_script_yaml(run_dir: Path, data: dict) -> None:
    (run_dir / "script.md").write_text("```yaml\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "```\n", encoding="utf-8")


def _read_manifest_yaml(run_dir: Path) -> dict:
    _, data = STAGE_EVALUATOR.load_structured_document(run_dir / "video_manifest.md")
    return data if isinstance(data, dict) else {}


def _write_manifest_yaml(run_dir: Path, data: dict) -> None:
    (run_dir / "video_manifest.md").write_text("```yaml\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "```\n", encoding="utf-8")


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
                        "  must_avoid: [\"drift\"]",
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
                    "      target_duration_seconds: 16",
                    "      estimated_duration_seconds: 16",
                        "      handoff_to_next_scene: \"旅支度へ進む\"",
                        "      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, value_shift_visible: true, causal_turn_visible: true, scene_specificity_gate_passed: true, next_scene_connection_checked: true}",
                        "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                        *_valid_scene_intent_lines("桃太郎", 1, terminal=False),
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
                    "      target_duration_seconds: 16",
                    "      estimated_duration_seconds: 16",
                        "      handoff_to_next_scene: \"決戦へ進む\"",
                        "      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, value_shift_visible: true, causal_turn_visible: true, scene_specificity_gate_passed: true, next_scene_connection_checked: true}",
                        "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                        *_valid_scene_intent_lines("桃太郎", 2, terminal=False),
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
                    "      target_duration_seconds: 16",
                    "      estimated_duration_seconds: 16",
                        "      terminal_resolution: \"決戦への余韻で終わる\"",
                        "      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, value_shift_visible: true, causal_turn_visible: true, scene_specificity_gate_passed: true, next_scene_connection_checked: true}",
                        "      research_refs: [\"research.story_baseline.canonical_synopsis\"]",
                        *_valid_scene_intent_lines("桃太郎", 3, terminal=True),
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
                        "          must_avoid: [\"drift\"]",
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
            original_manifest_text = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            _write_valid_immersive_p400_pair(run_dir)
            (run_dir / "video_manifest.md").write_text(original_manifest_text, encoding="utf-8")
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
            text = text.replace("      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, value_shift_visible: true, causal_turn_visible: true, scene_specificity_gate_passed: true, next_scene_connection_checked: true}\n", "", 1)
            (run_dir / "script.md").write_text(text, encoding="utf-8")
            _resolve_ready_grounding(run_dir, "script", flow="immersive")

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.scene_readiness_contract", stage["reason_keys"])

    def test_script_evaluator_rejects_generic_scene_template_phrase(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_template_phrase_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014b"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            text = (run_dir / "script.md").read_text(encoding="utf-8")
            text = text.replace("桃太郎が進む。", "主人公は前進できるか", 1)
            (run_dir / "script.md").write_text(text, encoding="utf-8")
            _resolve_ready_grounding(run_dir, "script", flow="immersive")

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.no_generic_scene_template_phrases", stage["reason_keys"])

    def test_scene_series_evaluator_requires_scene_event_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_series_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014bb"
            scene_dir = run_dir / "scenes" / "scene1"
            scene_dir.mkdir(parents=True, exist_ok=True)
            (scene_dir / "script.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "scene_id: 1",
                        "scene_intent:",
                        "  dramatic_question: \"問い\"",
                        "cuts:",
                        "  - cut_id: 1",
                        "    cut_blueprint:",
                        "      cut_role: main",
                        "      duration_intent: standard",
                        "      target_beat: \"beat\"",
                        "      must_show: [\"beat\"]",
                        "      must_avoid: []",
                        "      done_when: [\"done\"]",
                        "      visual_beat: \"visual\"",
                        "      narration_role: setup",
                        "      asset_dependency_hint: {character_ids: [], object_ids: [], location_ids: [], reusable_still_candidates: []}",
                        "```",
                    ]
                ),
                encoding="utf-8",
            )

            stage, _ = STAGE_EVALUATOR.check_script_scene_series(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.scene_series_scene_event_contract", stage["reason_keys"])

    def test_script_evaluator_requires_scene_event(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014c"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            data["script"]["scenes"][0].pop("scene_event", None)
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.scene_event_exists", stage["reason_keys"])

    def test_script_evaluator_requires_complete_scene_event_sequence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014d"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            sequence = data["script"]["scenes"][0]["scene_event"]["event_sequence"]
            data["script"]["scenes"][0]["scene_event"]["event_sequence"] = [
                beat for beat in sequence if beat.get("beat_function") != "payoff"
            ]
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.scene_event_sequence_complete", stage["reason_keys"])
            self.assertIn("script.cut_event_beat_refs_valid", stage["reason_keys"])

    def test_script_evaluator_rejects_duplicate_scene_event_beat_ids(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014e"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            sequence = data["script"]["scenes"][0]["scene_event"]["event_sequence"]
            sequence[1]["beat_id"] = sequence[0]["beat_id"]
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.scene_event_beat_ids_unique", stage["reason_keys"])

    def test_script_evaluator_rejects_forbidden_scene_event_directing_field(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014f"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            data["script"]["scenes"][0]["scene_event"]["event_sequence"][0]["camera"] = "wide shot"
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.scene_event_no_forbidden_directing_fields", stage["reason_keys"])

    def test_script_evaluator_rejects_forbidden_reveal_id_in_scene_event(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014fr"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            scene = data["script"]["scenes"][0]
            scene["scene_intent"]["reveal_constraints"] = [{"forbidden_info_ids": ["victory_proof"]}]
            scene["scene_event"]["event_sequence"][0]["story_information_revealed_ids"] = ["victory_proof"]
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.scene_event_reveal_constraints_respected", stage["reason_keys"])

    def test_script_evaluator_rejects_string_forbidden_reveal_id_in_scene_event(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014fs"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            scene = data["script"]["scenes"][0]
            scene["scene_intent"]["reveal_constraints"] = ["victory_proof"]
            scene["scene_event"]["event_sequence"][0]["story_information_revealed_ids"] = ["victory_proof"]
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.scene_event_reveal_constraints_respected", stage["reason_keys"])

    def test_script_evaluator_rejects_invalid_cut_event_refs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014g"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            data["script"]["scenes"][0]["cuts"][0]["cut_contract"]["source_event_contract"]["source_event_beat_ids"] = ["missing_event"]
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.cut_event_beat_refs_valid", stage["reason_keys"])

    def test_script_evaluator_requires_cut_event_fact_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014gf"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            contract = data["script"]["scenes"][0]["cuts"][0]["cut_contract"]
            contract["source_event_contract"].pop("event_facts_to_preserve", None)
            contract["source_event_contract"].pop("event_facts_not_to_invent", None)
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.cut_event_beat_refs_valid", stage["reason_keys"])

    def test_script_evaluator_allows_empty_scene_event_context_lists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014gl"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            scene_event = data["script"]["scenes"][0]["scene_event"]
            scene_event["offscreen_context"] = []
            scene_event["forbidden_event_changes"] = []
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertNotIn("script.scene_event_exists", stage["reason_keys"])

    def test_script_evaluator_requires_turn_and_payoff_cut_assignment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014h"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            for cut in data["script"]["scenes"][0]["cuts"]:
                source_contract = cut["cut_contract"]["source_event_contract"]
                source_contract["primary_event_beat_id"] = "scene1_event_setup"
                source_contract["source_event_beat_ids"] = ["scene1_event_setup"]
                source_contract["event_beat_function"] = "setup"
                cut["cut_contract"]["first_frame_contract"]["source_event_beat_id"] = "scene1_event_setup"
                cut["cut_contract"]["motion_contract"]["source_event_beat_id"] = "scene1_event_setup"
                cut["cut_contract"]["narration_contract"]["source_event_beat_ids"] = ["scene1_event_setup"]
                cut["cut_contract"]["event_context_for_cut"]["primary_event_beat"]["beat_id"] = "scene1_event_setup"
                cut["cut_contract"]["event_context_for_cut"]["primary_event_beat"]["beat_function"] = "setup"
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.cuts_cover_scene_event_sequence", stage["reason_keys"])
            self.assertIn("script.turn_and_payoff_event_beats_have_cuts", stage["reason_keys"])

    def test_script_evaluator_rejects_v2_top_level_cut_event_refs_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014i"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            contract = data["script"]["scenes"][0]["cuts"][0]["cut_contract"]
            source_contract = contract.pop("source_event_contract")
            contract["schema_version"] = "2.2"
            contract["primary_event_beat_id"] = source_contract["primary_event_beat_id"]
            contract["source_event_beat_ids"] = source_contract["source_event_beat_ids"]
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.cut_event_beat_refs_valid", stage["reason_keys"])

    def test_script_evaluator_rejects_mismatched_source_event_function_and_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014j"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            contract = data["script"]["scenes"][0]["cuts"][0]["cut_contract"]
            contract["source_event_contract"]["event_beat_function"] = "turn"
            contract["event_context_for_cut"]["primary_event_beat"]["beat_id"] = "wrong_event"
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.event_beat_reference_integrity", stage["reason_keys"])
            self.assertIn("script.event_context_for_cut_ready", stage["reason_keys"])

    def test_script_evaluator_rejects_invented_v3_event_projection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014jp"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            contract = data["script"]["scenes"][0]["cuts"][0]["cut_contract"]
            contract["source_event_contract"]["event_facts_to_preserve"] = ["別の出来事"]
            contract["source_event_contract"]["source_required_visual_evidence"] = ["別の証拠"]
            contract["event_context_for_cut"]["source_event_beats"] = [{"beat_id": "scene1_event_turn"}]
            contract["event_context_for_cut"]["neighboring_event_beats"] = []
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.source_event_preservation", stage["reason_keys"])
            self.assertIn("script.event_context_for_cut_ready", stage["reason_keys"])

    def test_script_evaluator_rejects_first_frame_and_motion_event_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_scene_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0014k"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_valid_immersive_p400_pair(run_dir)
            data = _read_script_yaml(run_dir)
            contract = data["script"]["scenes"][0]["cuts"][0]["cut_contract"]
            contract["first_frame_contract"]["source_event_beat_id"] = "scene1_event_turn"
            contract["motion_contract"]["source_event_beat_id"] = "scene1_event_turn"
            _write_script_yaml(run_dir, data)

            stage, _ = STAGE_EVALUATOR.check_script_single(run_dir, "fast")

            self.assertFalse(stage["passed"])
            self.assertIn("script.event_first_frame_alignment", stage["reason_keys"])
            self.assertIn("script.event_motion_boundary", stage["reason_keys"])

    def test_manifest_evaluator_gates_p400_duration_and_review_integrity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_p400_duration_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0015"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000015\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            _write_valid_immersive_p400_pair(run_dir, target_duration=300, cut_duration=6, scene_count=10)
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
            text = text.replace("      coverage_review: {audience_information_covered: true, visualizable_action_covered: true, value_shift_visible: true, causal_turn_visible: true, scene_specificity_gate_passed: true, next_scene_connection_checked: true}\n", "", 1)
            (run_dir / "script.md").write_text(text, encoding="utf-8")
            _resolve_ready_grounding(run_dir, "manifest", flow="immersive")

            stage, updates = STAGE_EVALUATOR.check_manifest_single(run_dir, "standard", "immersive")

            self.assertFalse(stage["passed"])
            self.assertEqual(updates["eval.p400_readiness.status"], "changes_requested")
            self.assertIn("p400.script_readiness_contract", stage["reason_keys"])

    def test_manifest_p400_readiness_includes_script_scene_event_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_p400_script_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0018e"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000018e\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            _write_valid_immersive_p400_pair(run_dir, target_duration=300, cut_duration=15, scene_count=10)
            data = _read_script_yaml(run_dir)
            data["script"]["scenes"][0].pop("scene_event", None)
            _write_script_yaml(run_dir, data)
            _resolve_ready_grounding(run_dir, "manifest", flow="immersive")

            stage, updates = STAGE_EVALUATOR.check_manifest_single(run_dir, "standard", "immersive")

            self.assertFalse(stage["passed"])
            self.assertEqual(updates["eval.p400_readiness.status"], "changes_requested")
            self.assertIn("p400.script_readiness_contract", stage["reason_keys"])

    def test_manifest_p400_readiness_includes_manifest_scene_event_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_p400_manifest_event_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0018f"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000018f\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            _write_valid_immersive_p400_pair(run_dir, target_duration=300, cut_duration=15, scene_count=10)
            data = _read_manifest_yaml(run_dir)
            data["scenes"][0].pop("scene_event", None)
            _write_manifest_yaml(run_dir, data)
            _resolve_ready_grounding(run_dir, "manifest", flow="immersive")

            stage, updates = STAGE_EVALUATOR.check_manifest_single(run_dir, "standard", "immersive")

            self.assertFalse(stage["passed"])
            self.assertEqual(updates["eval.p400_readiness.status"], "changes_requested")
            self.assertIn("p400.script_readiness_contract", stage["reason_keys"])

    def test_manifest_p400_readiness_requires_scene_specificity_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_p400_scene_specificity_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0018b"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-04-04T00:00:00+09:00\njob_id=JOB_2026-04-04_000018b\ntopic=桃太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            _write_valid_immersive_p400_pair(run_dir, target_duration=300, cut_duration=15, scene_count=10)
            aggregate = run_dir / "logs" / "eval" / "scene_set" / "round_01" / "aggregated_review.md"
            text = aggregate.read_text(encoding="utf-8")
            start = text.index("## Scene Specificity Gate")
            end = text.index("## Generator Patch Brief", start)
            aggregate.write_text(text[:start] + text[end:], encoding="utf-8")
            _resolve_ready_grounding(run_dir, "manifest", flow="immersive")

            stage, updates = STAGE_EVALUATOR.check_manifest_single(run_dir, "standard", "immersive")

            self.assertFalse(stage["passed"])
            self.assertEqual(updates["eval.p400_readiness.status"], "changes_requested")
            self.assertIn("p400.review_loop_integrity", stage["reason_keys"])

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
