"""Run navigation index generation for output/<topic>_<timestamp>/."""

from __future__ import annotations

from dataclasses import dataclass
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
                "00": "visual planning source-of-truth",
                "10": "visual planning evaluator / subagent review",
                "20": "visual planning human review",
                "50": "visual planning appendix / transitional notes",
            }
        ),
        state_keys=("stage.visual_value.status",),
        source_of_truth="visual_value.md",
        evaluator="visual planning evaluator",
        human_review="visual planning source doc",
        request_target="scene planning handoff",
        outputs="visual planning docs",
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
        state_keys=("stage.asset_plan_review.status", "stage.asset_generation.status"),
        source_of_truth="asset_plan.md",
        evaluator="asset review state / asset evaluator",
        human_review="asset_plan.md",
        request_target="asset_generation_requests.md / asset generation manifests",
        outputs="assets/characters/**, assets/objects/**, assets/locations/**, assets/test/**",
        default_owner="generator",
        planned_artifacts=(
            ("p500", "asset_plan.md"),
            ("p530", "asset_generation_requests.md"),
        ),
    ),
    StageSpec(
        bucket="p600",
        title="Image Stage",
        slots=_stage_slots(
            {
                "00": "image generation source-of-truth",
                "10": "manifest / image evaluator",
                "20": "image human review",
                "30": "image generation request freeze",
                "40": "scene image outputs",
                "50": "image appendix / transitional prompt artifacts",
            }
        ),
        state_keys=("stage.image_prompt_review.status", "stage.image_generation.status"),
        source_of_truth="video_manifest.md",
        evaluator="manifest_review.md / image_prompt_story_review.md",
        human_review="image_generation_requests.md",
        request_target="image_generation_requests.md",
        outputs="assets/scenes/**",
        default_owner="generator",
        planned_artifacts=(
            ("p600", "video_manifest.md"),
            ("p610", "manifest_review.md"),
            ("p620", "image_generation_requests.md"),
        ),
    ),
    StageSpec(
        bucket="p700",
        title="Video Stage",
        slots=_stage_slots(
            {
                "00": "video generation plan / handoff",
                "10": "video request review",
                "20": "video human review",
                "30": "video generation requests / clip plan",
                "40": "video clip outputs",
                "50": "video appendix / exclusions / transitional notes",
            }
        ),
        state_keys=("stage.video_generation.status",),
        source_of_truth="video_generation plan / manifest handoff",
        evaluator="video request review / final video review",
        human_review="video_generation_requests.md",
        request_target="video_generation_requests.md",
        outputs="assets/videos/**",
        default_owner="generator",
        planned_artifacts=(("p710", "video_generation_requests.md"),),
    ),
    StageSpec(
        bucket="p800",
        title="Audio Generation Stage",
        slots=_stage_slots(
            {
                "00": "audio generation entry",
                "10": "narration runtime evaluator",
                "20": "narration human review note (text source lives in script)",
                "30": "audio generation request / gate",
                "40": "audio outputs",
                "50": "audio appendix / silent-cut notes",
            }
        ),
        state_keys=("stage.narration.status",),
        source_of_truth="script.md narration / tts_text (text source), manifest audio node (runtime source)",
        evaluator="narration_text_review.md / narration_review.md",
        human_review="script.md (text source of truth)",
        request_target="manifest audio node / TTS runtime request",
        outputs="assets/audio/**",
        default_owner="generator",
        planned_artifacts=(("p810", "narration_text_review.md"),),
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

PENDING_GATE_TARGETS: dict[str, tuple[str, str, str]] = {
    "research_review": ("p100", "research review", "research.md / research_review.md"),
    "story_review": ("p200", "story review", "story.md"),
    "script_review": ("p400", "script human review", "script.md"),
    "asset_review": ("p500", "asset human review", "asset_plan.md / asset_generation_requests.md"),
    "image_prompt_review": ("p600", "image prompt review", "video_manifest.md / image_generation_requests.md"),
    "image_review": ("p600", "image review", "image_generation_requests.md"),
    "narration_review": ("p800", "narration runtime gate", "script.md (text source) / narration_text_review.md"),
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


def classify_run_file(rel_path: str) -> InventoryEntry:
    rel = _normalize_rel_path(rel_path)

    exact: dict[str, tuple[str, str, str]] = {
        "p000_index.md": ("p000", "canonical", "human-facing run navigation entry"),
        "research.md": ("p100", "canonical", "research source-of-truth"),
        "research_review.md": ("p110", "review", "research evaluator report"),
        "story.md": ("p200", "canonical", "story source-of-truth"),
        "visual_value.md": ("p300", "canonical", "visual planning source-of-truth"),
        "scene_outline_v3.md": ("p350", "transitional", "visual planning transitional doc"),
        "scene_conte.md": ("p350", "transitional", "visual planning transitional doc"),
        "script.md": ("p400", "canonical", "script / narration text source-of-truth"),
        "script_review.md": ("p410", "review", "script evaluator report"),
        "human_change_requests.md": ("p430", "request", "structured human change log"),
        "asset_plan.md": ("p500", "canonical", "asset plan source-of-truth"),
        "asset_generation_manifest.md": ("p530", "request", "asset generation manifest"),
        "location_asset_generation_manifest.md": ("p530", "request", "location asset generation manifest"),
        "location_asset_generation_manifest_patch_105_106.md": ("p530", "request", "asset generation patch manifest"),
        "asset_generation_requests.md": ("p530", "request", "asset generation request freeze"),
        "video_manifest.md": ("p600", "canonical", "image/video generation source-of-truth"),
        "manifest_review.md": ("p610", "review", "manifest evaluator report"),
        "image_prompt_story_review.md": ("p610", "review", "image prompt evaluator report"),
        "image_generation_requests.md": ("p620", "request", "image generation request freeze"),
        "image_generation_plan.md": ("p650", "transitional", "legacy image planning helper"),
        "image_prompt_collection.md": ("p650", "transitional", "legacy image prompt collection"),
        "image_prompt_review.md": ("p650", "transitional", "legacy image prompt review"),
        "video_generation_plan.md": ("p700", "transitional", "legacy video planning helper"),
        "video_generation_requests.md": ("p710", "request", "video generation request freeze"),
        "video_generation_exclusions.md": ("p750", "transitional", "video-stage exclusion appendix"),
        "narration_text_review.md": ("p810", "review", "narration runtime review"),
        "narration_review.md": ("p810", "review", "legacy narration review"),
        "video_clips.txt": ("p900", "request", "render concat list"),
        "video_narration_list.txt": ("p900", "request", "render narration concat list"),
        "eval_report.json": ("p910", "output", "eval harness json output"),
        "run_report.md": ("p920", "output", "human-facing run report"),
        "state.txt": ("p930", "canonical", "canonical append-only state"),
        "run_status.json": ("p930", "output", "derived machine-facing state"),
        "generation_exclusion_report.md": ("p950", "transitional", "legacy exclusion appendix"),
        ".DS_Store": ("p950", "legacy", "macOS metadata"),
    }
    if rel in exact:
        slot, role, note = exact[rel]
        return InventoryEntry(rel_path=rel, slot=slot, role=role, note=note)

    if rel.startswith("assets/characters/"):
        return InventoryEntry(rel, "p540", "output", "character asset output")
    if rel.startswith("assets/objects/"):
        return InventoryEntry(rel, "p540", "output", "object asset output")
    if rel.startswith("assets/locations/"):
        return InventoryEntry(rel, "p540", "output", "location asset output")
    if rel.startswith("assets/test/"):
        return InventoryEntry(rel, "p550", "output", "asset test variant")
    if rel.startswith("assets/scenes/"):
        return InventoryEntry(rel, "p640", "output", "scene still output")
    if rel.startswith("assets/videos/"):
        return InventoryEntry(rel, "p740", "output", "video clip output")
    if rel.startswith("assets/audio/"):
        return InventoryEntry(rel, "p840", "output", "audio output")
    if rel.startswith("logs/providers/"):
        return InventoryEntry(rel, "p930", "log", "provider execution log")
    if rel.startswith("scratch/"):
        return InventoryEntry(rel, "p950", "scratch", "scratch workspace artifact")
    if rel.endswith(".bak") or rel.endswith(".pre_ja.bak"):
        return InventoryEntry(rel, "p950", "compat", "backup / compatibility copy")
    if rel == "video.mp4" or rel.startswith("shorts/"):
        return InventoryEntry(rel, "p940", "output", "final render output")

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
    entries = [classify_run_file(rel) for rel in rel_paths]
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
        "- `x10~x50` は既定値を持つが固定契約ではない。stage ごとの actual slot meaning は下の stage table を正とする。",
        "",
        "### Default Slot Meanings",
        "",
    ]
    for suffix in ("00", "10", "20", "30", "40", "50"):
        lines.append(f"- `x{suffix}`: {DEFAULT_SLOT_MEANINGS[suffix]}")
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
        lines.append(
            f"| `{stage.bucket}` | {stage.title} | `{_summarize_stage_status(stage, flat_state)}` | "
            f"`{stage.source_of_truth}` | `{stage.human_review}` | `{stage.request_target}` | `{stage.outputs}` | `{stage.default_owner}` |"
        )

    lines += [
        "",
        "## File-to-Stage Mapping",
        "",
    ]

    for stage in STAGES:
        stage_entries = grouped.get(stage.bucket, {})
        stage_missing = _designed_absent(stage, existing_paths)
        lines += [
            f"### {stage.bucket} {stage.title}",
            "",
            f"- current_state: `{_summarize_stage_status(stage, flat_state)}`",
            f"- source_of_truth: `{stage.source_of_truth}`",
            f"- evaluator_artifact: `{stage.evaluator}`",
            f"- human_review_target: `{stage.human_review}`",
            f"- request_target: `{stage.request_target}`",
            f"- outputs: `{stage.outputs}`",
            f"- next_action_owner: `{stage.default_owner}`",
            "- slot_meanings:",
        ]
        for suffix in ("00", "10", "20", "30", "40", "50"):
            slot = f"{stage.bucket[:2]}{suffix}"
            lines.append(f"  - `{slot}`: {stage.slots[suffix]}")
        lines.append("")
        slot_codes = sorted(set(stage_entries) | set(stage_missing), key=_slot_sort_key)
        if not slot_codes:
            lines.extend(["この stage に対応する成果物はまだありません。", ""])
            continue
        for slot in slot_codes:
            slot_entries = stage_entries.get(slot, [])
            slot_missing = stage_missing.get(slot, [])
            suffix = slot[2:]
            slot_label = stage.slots.get(suffix, DEFAULT_SLOT_MEANINGS.get(suffix, "stage appendix"))
            lines.append(f"#### {slot} {slot_label}")
            lines.append("")
            if slot_entries:
                for entry in slot_entries:
                    note = f" ({entry.note})" if entry.note else ""
                    lines.append(f"- [{entry.role}] `{entry.rel_path}`{note}")
            if slot_missing:
                for rel_path in slot_missing:
                    lines.append(f"- [designed_absent] `{rel_path}`")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_run_index(run_dir: Path, *, state: dict[str, str] | None = None) -> Path:
    out_path = run_dir / "p000_index.md"
    out_path.write_text(build_run_index_markdown(run_dir, state=state), encoding="utf-8")
    return out_path
