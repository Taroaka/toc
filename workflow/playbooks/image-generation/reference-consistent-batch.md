# Image Method: Reference Consistent Batch

## Use when

sceneごとの静止画を一括生成し、被写体、視点、構図の一貫性を維持したいとき。

## Scope

この方式は image request authoring、batch generation、file/decode/provenance checks を担当する。
scene design と video motion は別 stage の contract で扱う。

## Steps

1. character/object/location の共通 reference と役割を固定する。
2. `video_manifest.md` から item collection を作り、source IDs、anchor、reference paths、destination を束縛する。
3. `script.md` の story intent と `cut_contract` の first-frame state を各 item へ投影する。
4. prompt を `image_api_prompt_v2` payload と immutable request snapshot に materialize する。
5. schema、IDs、references、prompt hash、source digest、destination を確認する。
6. item ごとに Codex built-in image generation を実行する。
7. response item、savedPath、bytes、file type、decode、destination、provenance を照合する。
8. mismatch は該当 item の request/asset source を修正し、再 materialize/retry する。

推奨 command:

```bash
python scripts/export-image-prompt-collection.py \
  --manifest output/<topic>_<timestamp>/video_manifest.md
```

## Batch contract

```yaml
batch:
  source_manifest: output/<topic>_<timestamp>/video_manifest.md
  source_digest: sha256:<hash>
  items:
    - item_id: scene01_cut01
      scene_id: scene01
      cut_id: cut01
      source_event_beat_ids: [scene01_beat01]
      status: ready|hold|stale|failed
      prompt: ""
      prompt_sha256: sha256:<hash>
      references: []
      reference_sha256s: {}
      destination: assets/scenes/scene01_cut01.png
  execution:
    provider: codex_builtin_image
    max_concurrency: 6
```

Only `ready` items are submitted. Each item path is unique and run-relative. A `hold` item is an
explicit user/workflow choice and is not a production quality result.

## Prompt shape

```text
global style/forbidden elements
→ story time and scene time-of-day when present
→ reference identity and location
→ current visible moment and subject
→ composition, light, material
→ constraints and not-yet state
```

The prompt describes one drawable current moment. It must not contain scene/request metadata, IDs,
paths, hashes, first-frame labels, motion instructions, future action, or text overlay instructions.
Use concrete visible people, objects, location, action, material, light, and composition. No-reference
requests use the built-in no-reference lane; reference-driven requests bind actual bytes and their role.

## Structural checks

- required prompt groups and empty-group omission
- unique item/scene/cut IDs and valid source references
- character/object/location IDs and reference paths
- first-frame imageability and no future event reveal
- prompt/source/request hashes and destination
- output existence, type, decode, content hash, and provider response identity

## Output

- `assets/scenes/<item>.png`
- immutable request snapshot and provider provenance
- ordinary validation diagnostics under the run's validation log
- optional exploratory variants under `assets/test/`, never silently promoted

If scene information is missing, return an input error and fill the source scene contract first. Use
`workflow/scene-evidence-template.md` for evidence authoring and
`.claude/agents/scene-evidence-researcher.md` when a source worker is explicitly chosen.

