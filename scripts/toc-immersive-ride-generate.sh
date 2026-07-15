#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Generate assets and render the final immersive (cinematic) video from an existing run dir.

Usage:
  scripts/toc-immersive-ride-generate.sh --run-dir output/<topic>_<timestamp>

What it does:
  1) Generate reusable assets and scene images from video_manifest.md
  2) Generate narration audio
  3) Generate video clips
  4) Build ffmpeg concat lists and render final video.mp4 (1280x720, 24fps)
USAGE
}

run_dir=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir)
      run_dir="$2"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage; exit 1 ;;
  esac
done

if [[ -z "$run_dir" ]]; then
  echo "--run-dir is required." >&2
  usage
  exit 1
fi

manifest="${run_dir%/}/video_manifest.md"
if [[ ! -f "$manifest" ]]; then
  echo "Manifest not found: $manifest" >&2
  exit 1
fi

python scripts/toc-state.py ensure --run-dir "$run_dir" --manifest "$manifest"

python - <<'PY'
from pathlib import Path
run_dir = Path(r"""'"$run_dir"'""")
state_path = run_dir / "state.txt"
if not state_path.exists():
    raise SystemExit(0)
state = {}
for raw in state_path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line == "---" or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    state[k.strip()] = v.strip()
gate = state.get("gate.hybridization_review", "").strip().lower()
status = state.get("review.hybridization.status", "").strip().lower()
if gate == "required" and status != "approved":
    raise SystemExit(
        "Hybridization approval is required before generating assets.\n"
        f"  python scripts/toc-state.py approve-hybridization --run-dir {run_dir} --note \"OK\""
    )
PY

stage="images"
on_err() {
  code=$?
  set +e
  python scripts/toc-state.py append --run-dir "$run_dir" \
    --set "runtime.stage=${stage}" \
    --set "runtime.render.status=failed" \
    --set "last_error=toc-immersive-ride-generate.sh failed (stage=${stage}, exit=${code})"
  exit "$code"
}
trap on_err ERR

python scripts/toc-state.py append --run-dir "$run_dir" \
  --set "runtime.stage=${stage}" \
  --set "runtime.render.status=started"

python scripts/generate-assets-from-manifest.py \
  --manifest "$manifest" \
  --skip-audio \
  --skip-videos \
  --apply-asset-guides \
  --asset-guides-character-refs scene \
  --require-character-ids \
  --require-object-ids \
  --require-object-reference-scenes \
  --character-reference-views front,side,back \
  --character-reference-strip

stage="narration"
python scripts/toc-state.py append --run-dir "$run_dir" --set "runtime.stage=${stage}"

revision_aware_narration=$(python - "$run_dir" <<'PY'
from pathlib import Path
import sys
from toc.harness import load_structured_document

run_dir = Path(sys.argv[1]).resolve()
_text, data = load_structured_document(run_dir / "video_manifest.md")
aware = False
for scene in data.get("scenes") or []:
    if not isinstance(scene, dict):
        continue
    nodes = scene.get("cuts") if isinstance(scene.get("cuts"), list) else [scene]
    for node in nodes:
        if not isinstance(node, dict):
            continue
        audio = node.get("audio") if isinstance(node.get("audio"), dict) else {}
        narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
        revision = narration.get("revision") if isinstance(narration.get("revision"), dict) else {}
        aware = aware or revision.get("schema_version") == "narration_revision_v1"
print("true" if aware else "false")
PY
)

verify_revision_aware_narration_gate() {
  local expected_audio_set_hash="${1:-}"
  local expected_timeline_hash="${2:-}"
  python - "$run_dir" "$expected_audio_set_hash" "$expected_timeline_hash" <<'PY'
from pathlib import Path
import sys
from server.image_gen_app import _read_manifest_data, _require_narration_ready_for_video

run_dir = Path(sys.argv[1]).resolve()
expected_audio_set_hash = sys.argv[2]
expected_timeline_hash = sys.argv[3]
_require_narration_ready_for_video(run_dir)
_path, _original, data = _read_manifest_data(run_dir)
workflow = data.get("narration_workflow") if isinstance(data.get("narration_workflow"), dict) else {}
review = workflow.get("final_audio_review") if isinstance(workflow.get("final_audio_review"), dict) else {}
audio_set_hash = str(review.get("approved_audio_set_hash") or "")
timeline_hash = str(review.get("approved_timeline_hash") or "")
if expected_audio_set_hash and audio_set_hash != expected_audio_set_hash:
    raise SystemExit("approved narration audio set changed during generation")
if expected_timeline_hash and timeline_hash != expected_timeline_hash:
    raise SystemExit("approved narration timeline changed during generation")
print(audio_set_hash, timeline_hash)
PY
}

approved_narration_audio_set_hash=""
approved_narration_timeline_hash=""
if [[ "$revision_aware_narration" == "true" ]]; then
  if ! narration_binding="$(verify_revision_aware_narration_gate)"; then
    trap - ERR
    python scripts/toc-state.py append --run-dir "$run_dir" \
      --set "runtime.stage=narration_frontend_handoff" \
      --set "runtime.render.status=blocked" \
      --set "last_error=revision-aware narration requires current frontend candidate approvals and explicit p750 approval"
    echo "Revision-aware narration is not p750-approved. Finish text/audio review in the frontend before this CLI continues." >&2
    exit 1
  fi
  read -r approved_narration_audio_set_hash approved_narration_timeline_hash <<<"$narration_binding"
  if [[ -z "$approved_narration_audio_set_hash" || -z "$approved_narration_timeline_hash" ]]; then
    echo "Revision-aware narration approval hashes are missing." >&2
    exit 1
  fi
fi

require_frozen_narration_binding() {
  if [[ "$revision_aware_narration" == "true" ]]; then
    verify_revision_aware_narration_gate \
      "$approved_narration_audio_set_hash" \
      "$approved_narration_timeline_hash" >/dev/null
  fi
}

override_tool="${TOC_OVERRIDE_NARRATION_TOOL:-}"
override_args=()
if [[ -n "$override_tool" ]]; then
  override_args=(--override-narration-tool "$override_tool")
fi

if [[ "$revision_aware_narration" != "true" ]]; then
  python scripts/generate-assets-from-manifest.py \
    --manifest "$manifest" \
    --skip-images --skip-videos \
    "${override_args[@]}"

  python scripts/sync-manifest-durations-from-audio.py \
    --manifest "$manifest"

  if ! python scripts/check-audio-duration-gate.py \
    --manifest "$manifest" \
    --run-dir "$run_dir"; then
    trap - ERR
    python scripts/toc-state.py append --run-dir "$run_dir" \
      --set "runtime.stage=audio_duration_gate" \
      --set "runtime.render.status=blocked" \
      --set "last_error=audio duration gate requested scene/narration expansion before human review"
    echo "Audio duration gate blocked downstream generation." >&2
    echo "Review prompts:" >&2
    echo "  - ${run_dir%/}/logs/review/duration_scene.subagent_prompt.md" >&2
    echo "  - ${run_dir%/}/logs/review/duration_narration.subagent_prompt.md" >&2
    exit 1
  fi
fi

stage="videos"
python scripts/toc-state.py append --run-dir "$run_dir" --set "runtime.stage=${stage}"

python scripts/generate-assets-from-manifest.py \
  --manifest "$manifest" \
  --skip-images \
  --skip-audio \
  --apply-asset-guides \
  --asset-guides-character-refs scene \
  --require-character-ids \
  --require-object-ids \
  --require-object-reference-scenes \
  --character-reference-views front,side,back \
  --character-reference-strip \
  --enable-last-frame \
  --chain-first-frame-from-prev-video \
  --chain-first-frame-seconds-from-end 0.042 \
  --video-negative-prompt "fade out, fade to black, crossfade, dissolve, cut, hard cut, montage, timelapse, jump cut, title card, subtitle text, on-screen text, watermark"

require_frozen_narration_binding
if [[ "$revision_aware_narration" == "true" ]]; then
  python scripts/freeze-approved-render-inputs.py \
    --run-dir "$run_dir" \
    --output "video.mp4"
else
  python scripts/build-clip-lists.py --manifest "$manifest" --out-dir "$run_dir"
fi

narration_list="${run_dir%/}/video_narration_list.txt"
audio="${run_dir%/}/assets/audio/narration.mp3"
stage="render"
python scripts/toc-state.py append --run-dir "$run_dir" --set "runtime.stage=${stage}"
require_frozen_narration_binding
if [[ -s "$narration_list" ]]; then
  scripts/render-video.sh \
    --clip-list "${run_dir%/}/video_clips.txt" \
    --narration-list "$narration_list" \
    --fps 24 --size 1280x720 \
    --out "${run_dir%/}/video.mp4"
elif [[ -f "$audio" ]]; then
  scripts/render-video.sh \
    --clip-list "${run_dir%/}/video_clips.txt" \
    --audio "$audio" \
    --fps 24 --size 1280x720 \
    --out "${run_dir%/}/video.mp4"
else
  echo "Narration audio not found (rendering silent video): $audio" >&2
  scripts/render-video.sh \
    --clip-list "${run_dir%/}/video_clips.txt" \
    --fps 24 --size 1280x720 \
    --out "${run_dir%/}/video.mp4"
fi

require_frozen_narration_binding
python scripts/check-final-video-duration-gate.py \
  --run-dir "$run_dir" \
  --video "${run_dir%/}/video.mp4"

stage="done"
python scripts/toc-state.py append --run-dir "$run_dir" \
  --set "runtime.stage=${stage}" \
  --set "runtime.render.status=success" \
  --set "artifact.video=${run_dir%/}/video.mp4" \
  --set "review.video.status=pending"

python scripts/verify-pipeline.py \
  --run-dir "$run_dir" \
  --flow immersive \
  --profile standard

echo "Done:"
echo "  - ${run_dir%/}/video.mp4"
