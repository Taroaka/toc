# P600 Scene Image Batch Spec Template

p600 image generation で、何をどこへ生成するかを明示する run-local batch spec。p600 は
image request authoring、ordinary request/file/provenance checks、generation を担当する。

## 1. Batch metadata

```yaml
batch:
  topic: ""
  run_dir: ""
  mode: test|production
  source_of_truth:
    manifest: output/<topic>_<timestamp>/video_manifest.md
    requests: output/<topic>_<timestamp>/image_generation_requests.md
  output_root: assets/scenes
  parallel_generation_requested: true
  grouping_rule: one-image-per-worker
  source_digest: sha256:<hash>
  notes: ""
```

test output と production output の path を混在させない。各 item の destination は run-relative
path で一意にする。

## 2. Visual rules

```yaml
visual_rules:
  continuity_anchor: ""
  style_lock: ""
  forbidden_elements: []
  aspect_ratio: "16:9"
  background_policy: ""
  render_constraints: []
```

batch 全体に共通する visual constraints だけを置く。人物/物/場所の identity と scene-specific
event は item と cut contract に残す。

## 3. Image items

```yaml
items:
  - item_id: scene01_cut01
    scene_id: scene01
    cut_id: cut01
    source_event_beat_ids: [scene01_beat01]
    purpose: opening cut image
    status: ready|hold|stale|failed
    prompt: ""
    prompt_sha256: sha256:<hash>
    source_digest: sha256:<hash>
    reference_images: []
    reference_sha256s: {}
    output_path: assets/scenes/scene01-cut01.png
    size_or_aspect: "16:9"
    notes: ""
```

Only `status: ready` items are submitted. Validate source/event IDs, unique item/output paths,
reference existence/type/hash, prompt/source hashes, provider settings, and destination constraints
before submission. A `hold` item is an explicit workflow choice and has no automatic result.

## 4. Execution

```yaml
execution:
  provider: codex_builtin_image
  invoke_skill: $toc-p600-image-runner
  delegate_skill: $codex-parallel-image-batch
  summary_format: compact
  max_concurrency: 6
  retry_policy: retry-stale-item
  provenance_fields:
    - generation_job_id
    - item_id
    - turn_id
    - prompt_sha256
    - reference_sha256s
    - savedPath
    - destination
```

Store the request snapshot before provider execution. Copy output only when response item ID, turn/job
ID, prompt/reference hashes, saved path, destination, file type, decode, and content hash match. Retry
the smallest failed item and never use output from another item.

## 5. Thumbnail note

Use a thumbnail-specific spec for text readability, 16:9, high contrast, and mobile readability.
This batch template contributes only the item/output path and ordinary image binding shape.

