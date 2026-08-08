"""Low-level manifest node and production-artifact inspection."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from toc.harness import load_structured_document
from toc.immersive_manifest import make_scene_cut_selector

from .common import as_dotted_str, as_list

def _production_manifest_issues(run_dir: Path) -> list[str]:
    manifest_path = run_dir / "video_manifest.md"
    if not manifest_path.exists():
        return []
    _, data = load_structured_document(manifest_path)
    issues: list[str] = []
    for selector, node in _iter_manifest_nodes_with_selectors(data):
        image_generation = node.get("image_generation") if isinstance(node.get("image_generation"), dict) else {}
        video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
        prompt = str(image_generation.get("prompt") or "").strip()
        motion_prompt = str(video_generation.get("motion_prompt") or "").strip()
        if prompt:
            issues.append(f"{selector}:image_generation.prompt")
        if motion_prompt:
            issues.append(f"{selector}:video_generation.motion_prompt")
    return issues


def _p300_production_artifact_issues(run_dir: Path) -> list[str]:
    issues: list[str] = []
    for filename in ("asset_generation_requests.md", "image_generation_requests.md", "video_generation_requests.md", "video.mp4"):
        if (run_dir / filename).exists():
            issues.append(filename)
    shorts_dir = run_dir / "shorts"
    if shorts_dir.exists() and any(shorts_dir.rglob("*")):
        issues.append("shorts")
    scene_video_paths = sorted((run_dir / "scenes").glob("scene*/video.mp4"))
    if scene_video_paths:
        issues.extend(str(path.relative_to(run_dir)) for path in scene_video_paths[:20])
    for rel in ("assets/scenes", "assets/videos", "assets/characters", "assets/objects", "assets/locations", "assets/test"):
        path = run_dir / rel
        if path.exists() and any(path.rglob("*")):
            issues.append(rel)
    issues.extend(_production_manifest_issues(run_dir))
    return sorted(set(issues))


def _iter_manifest_nodes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for scene in as_list(manifest.get("scenes")):
        if isinstance(scene, dict) and str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        cuts = as_list(scene.get("cuts")) if isinstance(scene, dict) else []
        if cuts:
            nodes.extend([cut for cut in cuts if isinstance(cut, dict) and str(cut.get("cut_status") or "").strip().lower() != "deleted"])
        elif isinstance(scene, dict):
            nodes.append(scene)
    return nodes


def _iter_manifest_nodes_with_selectors(manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for scene in as_list(manifest.get("scenes")):
        if not isinstance(scene, dict):
            continue
        if str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        scene_id = as_dotted_str(scene.get("scene_id"))
        if scene_id is None:
            continue
        cuts = as_list(scene.get("cuts"))
        if cuts:
            for cut in cuts:
                if not isinstance(cut, dict):
                    continue
                if str(cut.get("cut_status") or "").strip().lower() == "deleted":
                    continue
                cut_id = as_dotted_str(cut.get("cut_id"))
                if cut_id is None:
                    continue
                items.append((make_scene_cut_selector(scene_id, cut_id), cut))
        else:
            items.append((make_scene_cut_selector(scene_id), scene))
    return items


