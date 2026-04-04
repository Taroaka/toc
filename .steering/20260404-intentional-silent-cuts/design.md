# Design

## Manifest contract
`audio.narration` に以下を追加する。

```yaml
audio:
  narration:
    tool: "silent"
    text: ""
    tts_text: ""
    silence_contract:
      intentional: true
      kind: "visual_value_hold"
      confirmed_by_human: true
      reason: "映像価値を優先する追加カット"
```

- `tool: silent` は従来どおり無音 mp3 を生成する。
- `silence_contract.intentional` が true のときだけ、空 narration を正当な設計として扱う。
- `kind` は `visual_value_hold|transition_hold|reaction_hold|breathing_room|other` を想定。
- `confirmed_by_human` は人レビュー済みを示す。

## Preflight
`scripts/generate-assets-from-manifest.py` の narration preflight で以下を追加する。
- renderable node で `tool == silent` または narration text が空のとき、`silence_contract.intentional=true` と `confirmed_by_human=true` を要求する。
- 満たさない場合は生成前に停止する。

## Evaluators
- `toc/stage_evaluator.py` の manifest check で、silent cut には `silence_contract` を要求する。
- `scripts/review-narration-text-quality.py` は `tool: silent` を従来どおりスキップ対象とするが、契約不足は別の preflight / manifest evaluator で止める。

## Final audio assembly
- 既存どおり `tool: silent` cut では cut duration 長の無音 mp3 を生成し、`video_narration_list.txt` に含める。
- `render-video.sh` で concat した narration は、その cut の秒数ぶんの無音を保持する。

## Docs
- `docs/implementation/video-integration.md`
- `docs/data-contracts.md`
- `docs/how-to-run.md`
- `workflow/video-manifest-template.md`
- `workflow/state-schema.txt`
に新しい silent cut 契約と運用を書く。
