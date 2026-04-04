# Design

## Script Contract

各 `scenes[].cuts[]` に次を追加する。

```yaml
tts_text: "string"
human_review:
  status: "pending|approved|changes_requested"
  notes: ""
  approved_narration: ""
  approved_tts_text: ""
```

- `narration` は物語文面の正本
- `tts_text` は読み上げ用 spoken form
- `approved_*` は human review 後の確定値

## Sync Direction

- source: `script.md`
- sink: `video_manifest.md`
- target:
  - `audio.narration.text`
  - `audio.narration.tts_text`

優先順位:

1. `human_review.approved_narration`
2. `narration`

1. `human_review.approved_tts_text`
2. `tts_text`
3. `human_review.approved_narration`
4. `narration`

## Scope

- docs: `docs/script-creation.md`, `docs/data-contracts.md`, `docs/how-to-run.md`
- template: `workflow/script-template.yaml`
- new CLI: `scripts/sync-narration-from-script.py`
- tests: dedicated sync test
- current run: `output/浦島太郎_20260208_1515_immersive/script.md`
