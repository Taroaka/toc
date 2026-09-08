# Structural Validation Criteria

ToC の各 stage は、必要な入力、構造、参照、生成結果が揃っているかを普通の validator で
確認する。production の品質 score、rubric、critic、aggregate、合格証明は生成しない。

## 目的

- `research → story → script → manifest → asset/image → narration → video → render` の
  artifact contract を揃える
- source、ID、型、順序、request/provider binding、file/decode/provenance を検出する
- fast/standard の差で production authoring の必須構造を変えない

## Stage checks

### Research

- required source paths と exact source bytes/hash
- source passages、facts、events、conflicts、uncertainty、provenance
- unique IDs と source-to-story handoff
- YAML/Markdown shape と required fields

Confidence、curiosity、completeness などの research metadata は source context であり、production
quality score や pass gate ではない。

### Story

- protagonist、world、conflict、transformation、theme
- scene IDs、event order、source refs、creative boundary
- time-of-day/location contracts と scene handoff
- optional candidate selection と explicit hybridization choice

### Script

- scene intent、scene event sequence、cut blueprint
- unique scene/cut/beat IDs、event coverage、reveal boundaries
- first-frame/motion/narration contracts、asset dependencies、handoff selectors
- `script.md` と skeleton `video_manifest.md` の selector equality
- duration fields と provider capability

### Manifest and asset/image

- `manifest_phase`、renderable scenes/cuts、required image/audio/video fields
- character/object/location IDs と asset plan references
- compiled prompt payload、request snapshot、source/prompt/provider hashes
- first/last frame、ordered references、settings、destination
- generated files の existence、file type、decode、content hash、request-bound provenance

### Narration/audio

- `script.md` と `tts_text` の one-way projection
- narration spans、canonical cut order、silence contract
- pronunciation aliases、TTS settings、candidate revision
- audio decode と measured duration/timeline

### Video/render

- compiled motion payload、frame/reference bindings、provider capability
- clip response identity、file/decode、duration、stream compatibility
- concat order、stream normalization、ffprobe、aspect ratio、subtitle、audio sync
- final output path、content hash、publication target when supplied

## Validation result

Validator output records each concrete check:

```json
{
  "stage": "scene_implementation",
  "status": "passed|failed|skipped",
  "checks": [
    {"id": "scene_ids_unique", "status": "passed", "selectors": []},
    {"id": "request_provenance", "status": "passed", "selectors": []}
  ],
  "errors": [],
  "warnings": []
}
```

`passed` means the named structural check completed. It is not a subjective score and does not
stand in for user choice. If a check fails, the owner repairs the named artifact/selector and reruns
the relevant validator.

## Profiles

- `fast`: pointer, schema, path, ID, request, and file checks needed during local iteration
- `standard`: the same checks over the complete run, including media decode, duration, stream, and
  provenance checks

Profiles can change depth and provider calls; they do not introduce a quality rubric or a mandatory
human handoff.

## Outputs

`run_status.json`, `p000_index.md`, and optional `run_report.md` are derived execution summaries.
`eval_report.json` is a legacy filename accepted for reading old runs; new validation reports use
the concrete check shape above.

## Regression set

- `workflow/evals/golden-topics.yaml`

