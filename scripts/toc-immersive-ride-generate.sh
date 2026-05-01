#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Generate assets and render the final immersive (cinematic) video from an existing run dir.

Usage:
  scripts/toc-immersive-ride-generate.sh --run-dir output/<topic>_<timestamp>

What it does:
  1) Generate assets via APIs from video_manifest.md
  2) Build ffmpeg concat lists
  3) Render final video.mp4 (1280x720, 24fps)
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

stage="assets"
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

override_tool="${TOC_OVERRIDE_NARRATION_TOOL:-}"
override_args=()
if [[ -n "$override_tool" ]]; then
  override_args=(--override-narration-tool "$override_tool")
fi

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

python scripts/generate-assets-from-manifest.py \
  --manifest "$manifest" \
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

python scripts/build-clip-lists.py --manifest "$manifest" --out-dir "$run_dir"

narration_list="${run_dir%/}/video_narration_list.txt"
audio="${run_dir%/}/assets/audio/narration.mp3"
stage="render"
python scripts/toc-state.py append --run-dir "$run_dir" --set "runtime.stage=${stage}"
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
