# P600 Scene Image Batch Spec Template

目的: `p600` の image generation 実行時に、何をどこへ生成するかを明確にするための batch spec。

このテンプレは:

- story/cut 固有の要件を書く場所
- test / production の出力先を明示する場所
- 共通 skill ではなく run/document 側に残すべき具体性を書く場所

実行 skill:

- adapter: `$toc-p600-image-runner`
- executor: `$codex-parallel-image-batch`

---

## 1. Batch Metadata

```yaml
batch:
  topic: ""
  run_dir: ""
  mode: "test" # test | production
  source_of_truth:
    manifest: "output/<topic>_<timestamp>/video_manifest.md"
    requests: "output/<topic>_<timestamp>/image_generation_requests.md"
  output_root: "asset/scene" # test default
  parallel_generation_requested: true
  grouping_rule: "one-image-per-subagent"
  notes: ""
```

ルール:

- `mode=test` のとき `output_root` は原則 `asset/scene`
- `mode=production` のとき `output_root` は原則 `output/<topic>_<timestamp>/asset/scene`
- 実行前に path の混在がないことを確認する

## 2. Batch-Level Visual Rules

```yaml
visual_rules:
  continuity_anchor: ""
  style_lock: ""
  forbidden_elements: []
  aspect_ratio: ""
  background_policy: ""
  quality_bar: ""
```

ここには batch 全体に共通する制約だけを書く。

- 例: same costume continuity
- 例: painterly but grounded lighting
- 例: no modern props

## 3. Image Items

```yaml
items:
  - item_id: "scene01-cut01"
    scene_id: "scene01"
    cut_id: "cut01"
    purpose: "opening cut image"
    status: "ready" # draft | ready | hold
    prompt: ""
    reference_images: []
    output_path: "asset/scene/scene01-cut01.png"
    size_or_aspect: "3:2"
    notes: ""
  - item_id: "scene01-cut02"
    scene_id: "scene01"
    cut_id: "cut02"
    purpose: "reaction cut image"
    status: "ready"
    prompt: ""
    reference_images: []
    output_path: "asset/scene/scene01-cut02.png"
    size_or_aspect: "3:2"
    notes: ""
```

ルール:

- `status=ready` の item だけ生成対象
- `output_path` は item ごとに一意
- `reference_images` は continuity に必要なものだけに絞る

## 4. Review / Gate

```yaml
review_gate:
  prompt_review_passed: true
  continuity_review_passed: true
  human_review_required: false
  human_review_passed: false
  unresolved_findings: []
```

原則:

- unresolved finding があるまま生成しない
- gate 管理の正本が別 artifact にある場合は、その参照先を明記する

## 5. Execution Notes

```yaml
execution:
  invoke_skill: "$toc-p600-image-runner"
  delegate_skill: "$codex-parallel-image-batch"
  summary_format: "compact"
  retry_policy: "retry-once-if-obvious"
```

## 6. Thumbnail Reuse Note

thumbnail のような別用途では、このテンプレをそのまま使わず、下記だけ再利用する:

- batch metadata の考え方
- item ごとの `output_path`
- parallel generation の指定

thumbnail 固有要件:

- 文字可読性
- 16:9
- high contrast
- mobile readability

これらは thumbnail 専用 spec に分ける。
