"""Run navigation index generation for output/<topic>_<timestamp>/."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterable


DEFAULT_SLOT_MEANINGS: dict[str, str] = {
    "00": "source-of-truth",
    "10": "evaluator / subagent review",
    "20": "human review",
    "30": "request freeze / execution manifest",
    "40": "generated outputs",
    "50": "appendix / transitional / exclusions / backups / migration / runtime notes",
}

ROLE_ORDER = {
    "canonical": 0,
    "review": 1,
    "request": 2,
    "output": 3,
    "log": 4,
    "scratch": 5,
    "transitional": 6,
    "legacy": 7,
    "compat": 8,
    "designed_absent": 9,
}


@dataclass(frozen=True)
class StageSpec:
    bucket: str
    title: str
    slots: dict[str, str]
    state_keys: tuple[str, ...]
    source_of_truth: str
    evaluator: str
    human_review: str
    request_target: str
    outputs: str
    default_owner: str
    planned_artifacts: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class SlotSpec:
    code: str
    title: str
    purpose: str
    default_requirement: str = "required"
    planned_artifacts: tuple[str, ...] = ()
    state_keys: tuple[str, ...] = ()

    @property
    def bucket(self) -> str:
        return f"p{self.code[1]}00"


@dataclass(frozen=True)
class InventoryEntry:
    rel_path: str
    slot: str
    role: str
    note: str = ""

    @property
    def bucket(self) -> str:
        return f"p{self.slot[1]}00"


def _stage_slots(overrides: dict[str, str]) -> dict[str, str]:
    merged = dict(DEFAULT_SLOT_MEANINGS)
    merged.update(overrides)
    return merged


STAGES: tuple[StageSpec, ...] = (
    StageSpec(
        bucket="p000",
        title="Run Entrance",
        slots=_stage_slots(
            {
                "00": "run navigation source-of-truth",
                "10": "current stage / gate summary",
                "20": "next human review pointer",
                "30": "stage table / navigation handoff",
                "40": "current run inventory",
                "50": "run appendix / classification notes",
            }
        ),
        state_keys=(),
        source_of_truth="p000_index.md",
        evaluator="-",
        human_review="p000_index.md から次の review target へ進む",
        request_target="stage table / inventory",
        outputs="p000_index.md",
        default_owner="human",
        planned_artifacts=(("p000", "p000_index.md"),),
    ),
    StageSpec(
        bucket="p100",
        title="Research",
        slots=_stage_slots(
            {
                "00": "research source-of-truth",
                "10": "research evaluator / subagent review",
                "20": "research human review",
            }
        ),
        state_keys=("stage.research.status",),
        source_of_truth="research.md",
        evaluator="research_review.md",
        human_review="research.md / research_review.md",
        request_target="-",
        outputs="research.md",
        default_owner="subagent",
        planned_artifacts=(
            ("p100", "research.md"),
            ("p110", "research_review.md"),
        ),
    ),
    StageSpec(
        bucket="p200",
        title="Story",
        slots=_stage_slots(
            {
                "00": "story source-of-truth",
                "10": "story evaluator / subagent review",
                "20": "story human review",
            }
        ),
        state_keys=("stage.story.status",),
        source_of_truth="story.md",
        evaluator="story review artifact",
        human_review="story.md",
        request_target="-",
        outputs="story.md",
        default_owner="subagent",
        planned_artifacts=(("p200", "story.md"),),
    ),
    StageSpec(
        bucket="p300",
        title="Visual Planning",
        slots=_stage_slots(
            {
                "00": "visual planning source-of-truth: visual identity, scene visual value, anchors, references, risks, handoff",
                "10": "visual planning evaluator / subagent review",
                "20": "visual planning human review",
                "50": "p400/p600/p700 handoff appendix / transitional notes",
            }
        ),
        state_keys=("stage.visual_value.status",),
        source_of_truth="visual_value.md",
        evaluator="visual planning evaluator",
        human_review="visual planning source doc",
        request_target="p400/p600/p700 visual planning handoff",
        outputs="visual_value.md",
        default_owner="subagent",
        planned_artifacts=(("p300", "visual_value.md"),),
    ),
    StageSpec(
        bucket="p400",
        title="Script / Narration Text / Human Changes",
        slots=_stage_slots(
            {
                "00": "script source-of-truth",
                "10": "script evaluator / subagent review",
                "20": "script human review",
                "30": "human change log / structured review edits",
            }
        ),
        state_keys=("stage.script.status",),
        source_of_truth="script.md",
        evaluator="script evaluator artifact",
        human_review="script.md",
        request_target="human change log",
        outputs="script.md",
        default_owner="subagent",
        planned_artifacts=(
            ("p400", "script.md"),
            ("p410", "script_review.md"),
        ),
    ),
    StageSpec(
        bucket="p500",
        title="Narration / Audio Runtime Stage",
        slots=_stage_slots(
            {
                "00": "narration runtime source-of-truth",
                "10": "narration-ready manifest sync / review",
                "20": "tts request / generation",
                "30": "duration fit gate",
                "40": "scene stretch review",
                "50": "narration stretch review",
                "60": "audio qa / human review handoff",
            }
        ),
        state_keys=("stage.narration.status",),
        source_of_truth="script.md narration / skeleton video_manifest.md runtime handoff",
        evaluator="narration_text_review.md / duration fit gate",
        human_review="script.md / duration stretch prompts",
        request_target="manifest audio node / TTS runtime request",
        outputs="assets/audio/**",
        default_owner="generator",
        planned_artifacts=(("p520", "narration_text_review.md"),),
    ),
    StageSpec(
        bucket="p600",
        title="Asset Stage",
        slots=_stage_slots(
            {
                "00": "asset plan source-of-truth",
                "10": "asset evaluator / subagent review",
                "20": "asset human review",
                "30": "asset generation manifests / request freeze",
                "40": "asset outputs",
                "50": "asset appendix / test variants / transitional notes",
            }
        ),
        state_keys=("stage.asset.status", "stage.asset_plan_review.status", "stage.asset_generation.status"),
        source_of_truth="asset_plan.md",
        evaluator="asset review state / asset evaluator",
        human_review="asset_plan.md",
        request_target="asset_generation_requests.md / asset generation manifests",
        outputs="assets/characters/**, assets/objects/**, assets/locations/**, assets/test/**",
        default_owner="generator",
        planned_artifacts=(
            ("p600", "asset_plan.md"),
            ("p660", "asset_generation_requests.md"),
        ),
    ),
    StageSpec(
        bucket="p700",
        title="Scene Implementation Stage",
        slots=_stage_slots(
            {
                "00": "production manifest source-of-truth",
                "10": "hard scene evaluator / semantic review",
                "20": "scene human review",
                "30": "generation ready / request freeze",
                "40": "scene image outputs",
                "50": "scene appendix / transitional prompt artifacts",
            }
        ),
        state_keys=("stage.scene_implementation.status", "stage.image_prompt_review.status", "stage.image_generation.status"),
        source_of_truth="video_manifest.md",
        evaluator="manifest_review.md / image_prompt_story_review.md",
        human_review="image_generation_requests.md",
        request_target="image_generation_requests.md",
        outputs="assets/scenes/**",
        default_owner="generator",
        planned_artifacts=(
            ("p700", "video_manifest.md"),
            ("p730", "manifest_review.md"),
            ("p750", "image_generation_requests.md"),
        ),
    ),
    StageSpec(
        bucket="p800",
        title="Video Stage",
        slots=_stage_slots(
            {
                "00": "video generation plan / handoff",
                "10": "motion / video review",
                "20": "video human review",
                "30": "video generation requests / clip plan",
                "40": "video clip outputs",
                "50": "video appendix / exclusions / transitional notes",
            }
        ),
        state_keys=("stage.video.status", "stage.video_generation.status"),
        source_of_truth="video_generation plan / manifest handoff",
        evaluator="video request review / final video review",
        human_review="video_generation_requests.md",
        request_target="video_generation_requests.md",
        outputs="assets/videos/**",
        default_owner="generator",
        planned_artifacts=(("p830", "video_generation_requests.md"),),
    ),
    StageSpec(
        bucket="p900",
        title="Render / QA / Runtime",
        slots=_stage_slots(
            {
                "00": "render inputs / concat lists",
                "10": "eval report",
                "20": "human-facing run report",
                "30": "runtime state / machine-facing status",
                "40": "final render outputs",
                "50": "runtime appendix / logs / backups / scratch",
            }
        ),
        state_keys=("stage.render.status", "stage.qa.status"),
        source_of_truth="video_clips.txt / video_narration_list.txt",
        evaluator="eval_report.json",
        human_review="run_report.md / final video review target",
        request_target="render inputs / clip list",
        outputs="video.mp4 / shorts/**",
        default_owner="render pipeline",
        planned_artifacts=(
            ("p900", "video_clips.txt"),
            ("p900", "video_narration_list.txt"),
            ("p910", "eval_report.json"),
            ("p920", "run_report.md"),
            ("p930", "state.txt"),
            ("p930", "run_status.json"),
        ),
    ),
)

STAGE_BY_BUCKET = {stage.bucket: stage for stage in STAGES}
STAGE_ORDER = [stage.bucket for stage in STAGES]

SLOT_CONTRACTS: dict[str, tuple[SlotSpec, ...]] = {
    "p000": (
        SlotSpec("p000", "Run Entrance", "run navigation source-of-truth", planned_artifacts=("p000_index.md",)),
        SlotSpec("p010", "Current Position", "current stage and gate summary"),
        SlotSpec("p020", "Next Human Review", "next required human review target"),
        SlotSpec("p030", "Stage Table", "fixed slot workflow table and handoff summary"),
        SlotSpec("p040", "Run Inventory", "artifact inventory and file-to-slot mapping"),
        SlotSpec("p050", "Run Appendix", "classification notes and transitional appendix", default_requirement="optional"),
    ),
    "p100": (
        SlotSpec(
            "p110",
            "Research Grounding",
            "resolve, audit, readset, and preflight artifacts for research",
            planned_artifacts=(
                "logs/grounding/research.json",
                "logs/grounding/research.readset.json",
                "logs/grounding/research.audit.json",
            ),
            state_keys=("stage.research.grounding.status", "stage.research.audit.status"),
        ),
        SlotSpec("p120", "Research Authoring", "author research.md", planned_artifacts=("research.md",), state_keys=("stage.research.status",)),
        SlotSpec("p130", "Research Review", "research evaluator and review pass", planned_artifacts=("research_review.md",), default_requirement="optional"),
    ),
    "p200": (
        SlotSpec(
            "p210",
            "Story Grounding",
            "resolve, audit, readset, and preflight artifacts for story",
            planned_artifacts=(
                "logs/grounding/story.json",
                "logs/grounding/story.readset.json",
                "logs/grounding/story.audit.json",
            ),
            state_keys=("stage.story.grounding.status", "stage.story.audit.status"),
        ),
        SlotSpec("p220", "Story Authoring", "author story.md", planned_artifacts=("story.md",), state_keys=("stage.story.status",)),
        SlotSpec(
            "p230",
            "Story Review",
            "story review and approval handoff",
            planned_artifacts=("story_review.md",),
            state_keys=("review.story.status",),
            default_requirement="optional",
        ),
    ),
    "p300": (
        SlotSpec("p310", "Visual Value", "author visual_value.md as p300 visual planning source-of-truth", planned_artifacts=("visual_value.md",), default_requirement="optional"),
        SlotSpec("p320", "Visual Planning Review", "review visual identity, scene visual value, anchor/reference strategy, and regeneration risks", default_requirement="optional"),
        SlotSpec("p330", "Visual Planning Appendix", "p400/p600/p700 handoff and transitional notes", default_requirement="optional"),
    ),
    "p400": (
        SlotSpec(
            "p410",
            "Script Grounding",
            "resolve, audit, readset, and preflight artifacts for script",
            planned_artifacts=(
                "logs/grounding/script.json",
                "logs/grounding/script.readset.json",
                "logs/grounding/script.audit.json",
            ),
            state_keys=("stage.script.grounding.status", "stage.script.audit.status"),
        ),
        SlotSpec("p420", "Script Authoring", "author script.md and narration text source", planned_artifacts=("script.md",), state_keys=("stage.script.status",)),
        SlotSpec("p430", "Script Review", "script evaluator and review pass", planned_artifacts=("script_review.md",), default_requirement="optional"),
        SlotSpec("p440", "Human Changes / Narration Sync", "human change log and narration synchronization", default_requirement="optional"),
        SlotSpec("p450", "Skeleton Manifest Materialization", "materialize or update narration-ready skeleton video_manifest.md", planned_artifacts=("video_manifest.md",), default_requirement="required"),
    ),
    "p500": (
        SlotSpec(
            "p510",
            "Narration Grounding",
            "resolve, audit, readset, and confirm skeleton manifest for narration/audio runtime",
            planned_artifacts=(
                "logs/grounding/narration.json",
                "logs/grounding/narration.readset.json",
                "logs/grounding/narration.audit.json",
            ),
            state_keys=("stage.narration.grounding.status", "stage.narration.audit.status"),
        ),
        SlotSpec("p520", "Narration Text Review", "review narration text before TTS", planned_artifacts=("narration_text_review.md", "narration_review.md"), default_requirement="optional"),
        SlotSpec("p530", "TTS Request / Generation", "prepare and run TTS generation", default_requirement="optional"),
        SlotSpec("p540", "Duration Fit Gate", "check actual audio-driven runtime against the target minimum duration", default_requirement="optional"),
        SlotSpec("p550", "Scene Stretch Review", "scene-level duration expansion review prompt and report", default_requirement="optional"),
        SlotSpec("p560", "Narration Stretch Review", "narration-level duration expansion review prompt and report", default_requirement="optional"),
        SlotSpec("p570", "Audio QA / Human Review Handoff", "audio runtime QA and human review handoff after duration gate", default_requirement="optional"),
    ),
    "p600": (
        SlotSpec(
            "p610",
            "Asset Grounding",
            "resolve, audit, readset, and preflight artifacts for asset stage",
            planned_artifacts=(
                "logs/grounding/asset.json",
                "logs/grounding/asset.readset.json",
                "logs/grounding/asset.audit.json",
            ),
            state_keys=("stage.asset.grounding.status", "stage.asset.audit.status"),
        ),
        SlotSpec("p620", "Reusable Asset Inventory", "inventory recurring characters, objects, and locations", default_requirement="optional"),
        SlotSpec("p630", "Asset Plan Authoring", "author asset_plan.md", planned_artifacts=("asset_plan.md",), default_requirement="optional"),
        SlotSpec("p640", "Asset Review", "review and approve reusable asset plan", default_requirement="optional"),
        SlotSpec("p650", "Asset Plan Fixes", "apply asset review fixes and approval notes", default_requirement="optional"),
        SlotSpec(
            "p660",
            "Asset Requests",
            "materialize asset generation requests and manifests",
            planned_artifacts=("asset_generation_requests.md", "asset_generation_manifest.md", "location_asset_generation_manifest.md"),
            default_requirement="optional",
        ),
        SlotSpec("p670", "Asset Generation", "generate reusable character/object/location assets", default_requirement="optional"),
        SlotSpec("p680", "Asset Continuity Check", "verify reusable assets before p700", default_requirement="optional"),
    ),
    "p700": (
        SlotSpec(
            "p710",
            "Scene Implementation Grounding",
            "resolve, audit, readset, and preflight artifacts for scene implementation",
            planned_artifacts=(
                "logs/grounding/scene_implementation.json",
                "logs/grounding/scene_implementation.readset.json",
                "logs/grounding/scene_implementation.audit.json",
            ),
            state_keys=("stage.scene_implementation.grounding.status", "stage.scene_implementation.audit.status"),
        ),
        SlotSpec("p720", "Production Manifest / Prompt Authoring", "author and revise production video_manifest.md for cut-level prompts", planned_artifacts=("video_manifest.md",)),
        SlotSpec(
            "p730",
            "Hard Scene Review",
            "run deterministic function review for production manifest and prompts",
            planned_artifacts=("manifest_review.md", "image_prompt_story_review.md"),
            default_requirement="optional",
        ),
        SlotSpec(
            "p740",
            "Judgment Review",
            "contextless subagent or judgment artifacts for semantic image review",
            default_requirement="optional",
            state_keys=("review.image_prompt.judgment.status",),
        ),
        SlotSpec(
            "p750",
            "Generation Ready",
            "request freeze, judgment prompt artifacts, and generation-ready handoff",
            planned_artifacts=("image_generation_requests.md",),
            default_requirement="optional",
        ),
        SlotSpec("p760", "Image Generation", "generate scene stills and cut images", default_requirement="optional"),
        SlotSpec("p770", "Image QA / Fix Loop", "evaluate generated images and loop fixes", default_requirement="optional"),
    ),
    "p800": (
        SlotSpec(
            "p810",
            "Video Grounding",
            "resolve, audit, readset, and preflight artifacts for video generation",
            planned_artifacts=(
                "logs/grounding/video_generation.json",
                "logs/grounding/video_generation.readset.json",
                "logs/grounding/video_generation.audit.json",
            ),
            state_keys=("stage.video_generation.grounding.status", "stage.video_generation.audit.status"),
        ),
        SlotSpec("p820", "Motion / Video Review", "motion prompt review and video request review", default_requirement="optional"),
        SlotSpec("p830", "Video Requests", "freeze video generation requests", planned_artifacts=("video_generation_requests.md",), default_requirement="optional"),
        SlotSpec("p840", "Video Generation", "generate video clips", default_requirement="optional"),
        SlotSpec("p850", "Video Review / Exclusions", "video review and exclusion appendix", default_requirement="optional"),
    ),
    "p900": (
        SlotSpec("p910", "Render Inputs", "freeze concat lists and render inputs", planned_artifacts=("video_clips.txt", "video_narration_list.txt"), default_requirement="optional"),
        SlotSpec("p920", "Final Render", "render final deliverables", default_requirement="optional"),
        SlotSpec("p930", "QA / Runtime Summary", "run report, eval report, and state sync", planned_artifacts=("state.txt", "run_status.json", "run_report.md", "eval_report.json"), default_requirement="optional"),
    ),
}

SLOT_BY_CODE = {slot.code: slot for slots in SLOT_CONTRACTS.values() for slot in slots}

PENDING_GATE_TARGETS: dict[str, tuple[str, str, str]] = {
    "research_review": ("p100", "research review", "research.md / research_review.md"),
    "story_review": ("p200", "story review", "story.md"),
    "script_review": ("p400", "script human review", "script.md"),
    "asset_review": ("p600", "asset human review", "asset_plan.md / asset_generation_requests.md"),
    "image_prompt_review": ("p700", "scene implementation review", "video_manifest.md / image_generation_requests.md"),
    "image_review": ("p700", "image review", "image_generation_requests.md"),
    "narration_review": ("p500", "narration runtime gate", "script.md (text source) / narration_text_review.md"),
    "hybridization_review": ("p400", "hybridization review", "script.md"),
    "video_review": ("p900", "final video review", "run_report.md / final video output"),
}

PENDING_GATE_REVIEW_KEYS: tuple[tuple[str, str], ...] = (
    ("research_review", "review.research.status"),
    ("story_review", "review.story.status"),
    ("script_review", "review.script.status"),
    ("asset_review", "review.asset.status"),
    ("image_prompt_review", "review.image_prompt.status"),
    ("image_review", "review.image.status"),
    ("narration_review", "review.narration.status"),
    ("hybridization_review", "review.hybridization.status"),
    ("video_review", "review.video.status"),
)


def _parse_state_file(state_path: Path) -> dict[str, str]:
    if not state_path.exists():
        return {}
    merged: dict[str, str] = {}
    for raw in state_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().replace("\n", " ")
        if key:
            merged[key] = value
    return merged


def _pending_gates(state: dict[str, str]) -> list[str]:
    pending: list[str] = []
    for gate_name, review_key in PENDING_GATE_REVIEW_KEYS:
        gate_value = state.get(f"gate.{gate_name}", "").strip().lower()
        review_value = state.get(review_key, "").strip().lower()
        if gate_value != "required":
            continue
        if review_value in {"approved", "rejected", "changes_requested"}:
            continue
        pending.append(gate_name)
    return pending


def _normalize_review_status(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"approved", "passed", "done", "ready"}:
        return "done"
    if lowered in {"changes_requested", "rejected", "failed"}:
        return lowered
    if lowered in {"pending", "in_progress", "awaiting_approval", "blocked", "skipped"}:
        return lowered
    return lowered


def _summarize_stage_status(stage: StageSpec, state: dict[str, str]) -> str:
    if not stage.state_keys:
        return "always_available"
    statuses: list[tuple[str, str]] = []
    for key in stage.state_keys:
        value = state.get(key, "").strip()
        if value:
            statuses.append((key, value))
    if not statuses:
        return "not_started"
    for wanted in ("failed", "awaiting_approval", "in_progress"):
        for key, value in statuses:
            if value == wanted:
                substage = key.removeprefix("stage.").removesuffix(".status")
                return f"{wanted} ({substage})"
    values = {value for _, value in statuses}
    if values <= {"done", "skipped"}:
        return "done"
    return statuses[-1][1]


def _effective_stage_status(stage: StageSpec, state: dict[str, str], stage_entries: dict[str, list[InventoryEntry]]) -> str:
    summary = _summarize_stage_status(stage, state)
    if summary != "not_started":
        return summary
    slot_specs = SLOT_CONTRACTS.get(stage.bucket, ())
    if any(_summarize_slot_status(slot, state, stage_entries.get(slot.code, [])) == "done" for slot in slot_specs):
        return "done"
    return summary


def _summarize_slot_status(slot: SlotSpec, state: dict[str, str], entries: list[InventoryEntry]) -> str:
    explicit = state.get(f"slot.{slot.code}.status", "").strip().lower()
    if explicit:
        return explicit

    values = [_normalize_review_status(state.get(key, "")) for key in slot.state_keys if state.get(key, "").strip()]
    values = [value for value in values if value]
    if values:
        if any(value in {"failed", "rejected", "changes_requested", "blocked"} for value in values):
            return next(value for value in values if value in {"failed", "rejected", "changes_requested", "blocked"})
        if any(value == "awaiting_approval" for value in values):
            return "awaiting_approval"
        if any(value == "in_progress" for value in values):
            return "in_progress"
        if all(value in {"done", "passed", "ready"} for value in values):
            return "done"
        if any(value == "skipped" for value in values):
            return "skipped"
        if any(value == "pending" for value in values):
            return "pending"

    if entries:
        return "done"
    return "pending"


def _slot_requirement(slot: SlotSpec, state: dict[str, str]) -> str:
    return state.get(f"slot.{slot.code}.requirement", "").strip().lower() or slot.default_requirement


def _current_position(state: dict[str, str]) -> tuple[str, str]:
    pending = _pending_gates(state)
    if pending:
        bucket, label, target = PENDING_GATE_TARGETS[pending[0]]
        return f"{bucket} {STAGE_BY_BUCKET[bucket].title} / awaiting {label}", target

    for bucket in reversed(STAGE_ORDER):
        summary = _summarize_stage_status(STAGE_BY_BUCKET[bucket], state)
        if summary.startswith(("failed", "awaiting_approval", "in_progress")):
            return f"{bucket} {STAGE_BY_BUCKET[bucket].title} / {summary}", "-"

    runtime_stage = state.get("runtime.stage", "").strip()
    if runtime_stage:
        return f"runtime.stage={runtime_stage}", "-"
    status = state.get("status", "").strip()
    if status:
        return f"status={status}", "-"
    return "unknown", "-"


def _normalize_rel_path(rel_path: str) -> str:
    return rel_path.replace("\\", "/")


def _manifest_phase_for_file(path: Path) -> str:
    if not path.exists():
        return "production"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "production"
    match = re.search(r'(?m)^\s*manifest_phase:\s*"?([A-Za-z_]+)"?\s*$', text)
    if not match:
        return "production"
    return str(match.group(1) or "production").strip().lower() or "production"


def classify_run_file(rel_path: str, *, run_dir: Path | None = None) -> InventoryEntry:
    rel = _normalize_rel_path(rel_path)
    scene_match = re.match(r"^(scenes/[^/]+)/(.*)$", rel)
    if scene_match:
        scene_prefix = scene_match.group(1)
        nested_rel = scene_match.group(2)
        if nested_rel:
            nested_run_dir = (run_dir / scene_prefix).resolve() if run_dir is not None else None
            nested_entry = classify_run_file(nested_rel, run_dir=nested_run_dir)
            return InventoryEntry(
                rel_path=rel,
                slot=nested_entry.slot,
                role=nested_entry.role,
                note=f"scene subrun: {nested_entry.note}",
            )

    grounding_slots = {
        "research": "p110",
        "story": "p210",
        "script": "p410",
        "narration": "p510",
        "asset": "p610",
        "scene_implementation": "p710",
        "image_prompt": "p710",
        "video_generation": "p810",
    }
    for stage_name, slot in grounding_slots.items():
        prefix = f"logs/grounding/{stage_name}"
        if rel.startswith(prefix):
            return InventoryEntry(rel, slot, "log", f"{stage_name} grounding artifact")

    if rel.startswith("logs/review/image_prompt"):
        return InventoryEntry(rel, "p740", "log", "scene implementation judgment review artifact")
    if rel.startswith("logs/review/duration_scene"):
        return InventoryEntry(rel, "p550", "log", "scene stretch review artifact")
    if rel.startswith("logs/review/duration_narration"):
        return InventoryEntry(rel, "p560", "log", "narration stretch review artifact")

    if Path(rel).name == "video_manifest.md":
        manifest_path = (run_dir / rel).resolve() if run_dir is not None else None
        manifest_phase = _manifest_phase_for_file(manifest_path) if manifest_path is not None else "production"
        if manifest_phase == "skeleton":
            return InventoryEntry(rel, "p450", "canonical", "narration-ready skeleton manifest")
        return InventoryEntry(rel, "p720", "canonical", "production scene implementation manifest")

    exact: dict[str, tuple[str, str, str]] = {
        "p000_index.md": ("p000", "canonical", "human-facing run navigation entry"),
        "research.md": ("p120", "canonical", "research source-of-truth"),
        "research_review.md": ("p130", "review", "research evaluator report"),
        "story.md": ("p220", "canonical", "story source-of-truth"),
        "visual_value.md": ("p310", "canonical", "visual planning source-of-truth"),
        "scene_outline_v3.md": ("p320", "transitional", "visual planning transitional doc"),
        "scene_conte.md": ("p320", "transitional", "visual planning transitional doc"),
        "script.md": ("p420", "canonical", "script / narration text source-of-truth"),
        "script_review.md": ("p430", "review", "script evaluator report"),
        "human_change_requests.md": ("p440", "request", "structured human change log"),
        "asset_plan.md": ("p630", "canonical", "asset plan source-of-truth"),
        "asset_generation_manifest.md": ("p660", "request", "asset generation manifest"),
        "location_asset_generation_manifest.md": ("p660", "request", "location asset generation manifest"),
        "location_asset_generation_manifest_patch_105_106.md": ("p660", "request", "asset generation patch manifest"),
        "asset_generation_requests.md": ("p660", "request", "asset generation request freeze"),
        "manifest_review.md": ("p730", "review", "manifest evaluator report"),
        "image_prompt_story_review.md": ("p730", "review", "image prompt evaluator report"),
        "image_generation_requests.md": ("p750", "request", "image generation request freeze"),
        "image_generation_plan.md": ("p770", "transitional", "legacy image planning helper"),
        "image_prompt_collection.md": ("p740", "transitional", "image prompt review collection"),
        "image_prompt_review.md": ("p740", "transitional", "legacy image prompt review"),
        "video_generation_plan.md": ("p820", "transitional", "legacy video planning helper"),
        "video_generation_requests.md": ("p830", "request", "video generation request freeze"),
        "video_generation_exclusions.md": ("p850", "transitional", "video-stage exclusion appendix"),
        "narration_text_review.md": ("p520", "review", "narration runtime review"),
        "narration_review.md": ("p520", "review", "legacy narration review"),
        "logs/review/duration_scene.subagent_prompt.md": ("p550", "log", "scene stretch review prompt artifact"),
        "logs/review/duration_narration.subagent_prompt.md": ("p560", "log", "narration stretch review prompt artifact"),
        "video_clips.txt": ("p910", "request", "render concat list"),
        "video_narration_list.txt": ("p910", "request", "render narration concat list"),
        "eval_report.json": ("p930", "output", "eval harness json output"),
        "run_report.md": ("p930", "output", "human-facing run report"),
        "state.txt": ("p930", "canonical", "canonical append-only state"),
        "run_status.json": ("p930", "output", "derived machine-facing state"),
        "generation_exclusion_report.md": ("p850", "transitional", "legacy exclusion appendix"),
        ".DS_Store": ("p950", "legacy", "macOS metadata"),
    }
    if rel in exact:
        slot, role, note = exact[rel]
        return InventoryEntry(rel_path=rel, slot=slot, role=role, note=note)

    if rel.startswith("assets/characters/"):
        return InventoryEntry(rel, "p670", "output", "character asset output")
    if rel.startswith("assets/objects/"):
        return InventoryEntry(rel, "p670", "output", "object asset output")
    if rel.startswith("assets/locations/"):
        return InventoryEntry(rel, "p670", "output", "location asset output")
    if rel.startswith("assets/test/"):
        return InventoryEntry(rel, "p680", "output", "asset test variant")
    if rel.startswith("assets/scenes/"):
        return InventoryEntry(rel, "p760", "output", "scene still output")
    if rel.startswith("assets/videos/"):
        return InventoryEntry(rel, "p840", "output", "video clip output")
    if rel.startswith("assets/audio/"):
        return InventoryEntry(rel, "p530", "output", "audio output")
    if rel.startswith("logs/providers/"):
        return InventoryEntry(rel, "p930", "log", "provider execution log")
    if rel.startswith("scratch/"):
        return InventoryEntry(rel, "p950", "scratch", "scratch workspace artifact")
    if rel.endswith(".bak") or rel.endswith(".pre_ja.bak"):
        return InventoryEntry(rel, "p950", "compat", "backup / compatibility copy")
    if rel == "video.mp4" or rel.startswith("shorts/"):
        return InventoryEntry(rel, "p920", "output", "final render output")

    return InventoryEntry(rel, "p950", "legacy", "unclassified run artifact")


def _slot_sort_key(slot: str) -> tuple[int, int]:
    return int(slot[1]), int(slot[2:])


def _inventory(run_dir: Path) -> list[InventoryEntry]:
    rel_paths = {
        _normalize_rel_path(path.relative_to(run_dir).as_posix())
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    rel_paths.add("p000_index.md")
    entries = [classify_run_file(rel, run_dir=run_dir) for rel in rel_paths]
    entries.sort(key=lambda item: (_slot_sort_key(item.slot), ROLE_ORDER.get(item.role, 99), item.rel_path))
    return entries


def _counts(entries: Iterable[InventoryEntry]) -> dict[str, int]:
    counts = {"root": 0, "assets": 0, "logs": 0, "scratch": 0, "other": 0}
    for entry in entries:
        if "/" not in entry.rel_path:
            counts["root"] += 1
        elif entry.rel_path.startswith("assets/"):
            counts["assets"] += 1
        elif entry.rel_path.startswith("logs/"):
            counts["logs"] += 1
        elif entry.rel_path.startswith("scratch/"):
            counts["scratch"] += 1
        else:
            counts["other"] += 1
    return counts


def _group_entries(entries: list[InventoryEntry]) -> dict[str, dict[str, list[InventoryEntry]]]:
    grouped: dict[str, dict[str, list[InventoryEntry]]] = {}
    for entry in entries:
        grouped.setdefault(entry.bucket, {}).setdefault(entry.slot, []).append(entry)
    return grouped


def _designed_absent(stage: StageSpec, existing_paths: set[str]) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for slot, rel_path in stage.planned_artifacts:
        if rel_path not in existing_paths:
            missing.setdefault(slot, []).append(rel_path)
    return missing


def _slot_designed_absent(slot: SlotSpec, existing_paths: set[str]) -> list[str]:
    return [rel_path for rel_path in slot.planned_artifacts if rel_path not in existing_paths]


def build_run_index_markdown(run_dir: Path, *, state: dict[str, str] | None = None) -> str:
    flat_state = dict(state or _parse_state_file(run_dir / "state.txt"))
    entries = _inventory(run_dir)
    existing_paths = {entry.rel_path for entry in entries}
    grouped = _group_entries(entries)
    counts = _counts(entries)
    current_position, next_review_target = _current_position(flat_state)
    pending = _pending_gates(flat_state)

    lines: list[str] = [
        "# Run Index",
        "",
        f"- run_dir: `{run_dir.resolve()}`",
        f"- topic: `{flat_state.get('topic', '') or '(unset)'}`",
        f"- job_id: `{flat_state.get('job_id', '') or '(unset)'}`",
        f"- status: `{flat_state.get('status', '') or '(unset)'}`",
        f"- runtime.stage: `{flat_state.get('runtime.stage', '') or '(unset)'}`",
        f"- current_position: `{current_position}`",
        f"- next_required_human_review: `{next_review_target if next_review_target != '-' else 'none'}`",
        f"- pending_gates: `{', '.join(pending) if pending else 'none'}`",
        "",
        "## Numbering Rules",
        "",
        "- `p000` は run 入口。",
        "- `p100` ごとに大工程を割り当てる。",
        "- `p110` 以降の細番号も全作品で固定契約として扱う。",
        "- 作品差分は slot meaning を変えるのではなく、`slot.<code>.status` / `slot.<code>.requirement` / `slot.<code>.skip_reason` で表す。",
        "- `p000_index.md` の slot table が、その run の進捗と skip の正本になる。",
        "",
        "### Generic Slot State Keys",
        "",
    ]
    lines.extend(
        [
            "- `slot.pXXX.status=pending|in_progress|done|skipped|blocked|awaiting_approval|failed`",
            "- `slot.pXXX.requirement=required|optional`",
            "- `slot.pXXX.skip_reason=string`",
            "- `slot.pXXX.note=string`",
        ]
    )
    lines += [
        "",
        "## Inventory Summary",
        "",
        f"- total_files: `{len(entries)}`",
        f"- root_files: `{counts['root']}`",
        f"- assets_files: `{counts['assets']}`",
        f"- logs_files: `{counts['logs']}`",
        f"- scratch_files: `{counts['scratch']}`",
        f"- other_files: `{counts['other']}`",
        "",
        "## Stage Table",
        "",
        "| P# | Stage | Current State | Source-of-Truth | Human Review Target | Request Target | Outputs | Next Owner |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for stage in STAGES:
        effective_stage_status = _effective_stage_status(stage, flat_state, grouped.get(stage.bucket, {}))
        lines.append(
            f"| `{stage.bucket}` | {stage.title} | `{effective_stage_status}` | "
            f"`{stage.source_of_truth}` | `{stage.human_review}` | `{stage.request_target}` | `{stage.outputs}` | `{stage.default_owner}` |"
        )

    lines += [
        "",
        "## Fixed Slot Contract",
        "",
        "| Slot | Stage | Default Requirement | Purpose | Planned Artifacts |",
        "| --- | --- | --- | --- | --- |",
    ]
    for stage in STAGES:
        for slot in SLOT_CONTRACTS.get(stage.bucket, ()):
            planned = ", ".join(f"`{path}`" for path in slot.planned_artifacts) if slot.planned_artifacts else "-"
            lines.append(
                f"| `{slot.code}` | {stage.title} | `{slot.default_requirement}` | {slot.title}: {slot.purpose} | {planned} |"
            )

    lines += [
        "",
        "## File-to-Stage Mapping",
        "",
    ]

    for stage in STAGES:
        stage_entries = grouped.get(stage.bucket, {})
        stage_missing = _designed_absent(stage, existing_paths)
        stage_slots = {slot.code: slot for slot in SLOT_CONTRACTS.get(stage.bucket, ())}
        effective_stage_status = _effective_stage_status(stage, flat_state, stage_entries)
        lines += [
            f"### {stage.bucket} {stage.title}",
            "",
            f"- current_state: `{effective_stage_status}`",
            f"- source_of_truth: `{stage.source_of_truth}`",
            f"- evaluator_artifact: `{stage.evaluator}`",
            f"- human_review_target: `{stage.human_review}`",
            f"- request_target: `{stage.request_target}`",
            f"- outputs: `{stage.outputs}`",
            f"- next_action_owner: `{stage.default_owner}`",
        ]
        lines.append("")
        slot_codes = sorted(set(stage_entries) | set(stage_missing) | set(stage_slots), key=_slot_sort_key)
        if not slot_codes:
            lines.extend(["この stage に対応する成果物はまだありません。", ""])
            continue
        for slot in slot_codes:
            slot_spec = stage_slots.get(slot)
            slot_entries = stage_entries.get(slot, [])
            slot_missing = list(stage_missing.get(slot, []))
            if slot_spec:
                slot_missing = sorted(set(slot_missing) | set(_slot_designed_absent(slot_spec, existing_paths)))
            slot_label = slot_spec.title if slot_spec else "Stage Appendix"
            slot_status = _summarize_slot_status(slot_spec, flat_state, slot_entries) if slot_spec else ("done" if slot_entries else "pending")
            slot_requirement = _slot_requirement(slot_spec, flat_state) if slot_spec else "optional"
            lines.append(f"#### {slot} {slot_label}")
            lines.append("")
            lines.append(f"- status: `{slot_status}`")
            lines.append(f"- requirement: `{slot_requirement}`")
            if slot_spec:
                lines.append(f"- purpose: {slot_spec.purpose}")
            skip_reason = flat_state.get(f"slot.{slot}.skip_reason", "").strip()
            note = flat_state.get(f"slot.{slot}.note", "").strip()
            if skip_reason:
                lines.append(f"- skip_reason: `{skip_reason}`")
            if note:
                lines.append(f"- note: `{note}`")
            if slot_missing:
                lines.append("- planned_artifacts:")
                for rel_path in slot_missing:
                    lines.append(f"  - `{rel_path}`")
            if slot_entries:
                lines.append("- current_artifacts:")
            if slot_entries:
                for entry in slot_entries:
                    note = f" ({entry.note})" if entry.note else ""
                    lines.append(f"  - [{entry.role}] `{entry.rel_path}`{note}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_run_index(run_dir: Path, *, state: dict[str, str] | None = None) -> Path:
    out_path = run_dir / "p000_index.md"
    out_path.write_text(build_run_index_markdown(run_dir, state=state), encoding="utf-8")
    return out_path
