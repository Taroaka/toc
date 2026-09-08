# Scene-level Authoring Loop（正本）

scene を story meaning、event、visible evidence、handoff の単位として author し、
`script.md` と skeleton `video_manifest.md` を作る。処理は p400 の authoring と普通の
structural validation だけで完結する。

## p400 scope

`story.md` と `visual_value.md` を readset に従って読み、p500 asset、p600 image、p700
narration、p800 video が使える scene/cut design へ変換する。p400 では provider を呼ばない。

### p410 Scene Intent Card

各 scene は次を持つ。

- `scene_id`、`story_purpose`、`dramatic_question`
- `value_shift.from/to` と画面で読める `visible_evidence[]`
- `causal_turn`、`audience_information[]`、`withheld_information[]`、
  `reveal_constraints[]`
- character start/end state、visual thesis、spatial plan、production risks
- `scene_event.event_sequence[]` と ordered source beat IDs
- concrete incoming/outgoing handoff
- `story_specificity`（non-compressible beat、unique responsibility、actor forces、
  meaning ladder、concrete handoff、story-specific terms）
- `coverage_checks` と p500/p600/p700/p800 handoff notes

`target_duration_seconds`、`estimated_duration_seconds`、`importance` は計画注釈として
使えるが、値だけで scene/cut 数を決めない。

### Scene event contract

```yaml
scene_event:
  schema_version: scene_event_v1
  event_logline: ""
  start_situation: ""
  source_story_beat_ids: []
  event_sequence:
    - beat_id: scene_01_beat_01
      beat_function: custom
      source_story_beat_ids: []
      what_happens: ""
      visible_action: ""
      visible_reaction: ""
      immediate_consequence: ""
      required_visual_evidence: []
      story_information_revealed_ids: []
  turning_event:
    source_event_beat_id: scene_01_beat_01
    irreversible_change: ""
  end_situation: ""
  offscreen_context: []
  forbidden_event_changes: []
```

`beat_function` は authoring key として open。setup、pressure、turn、payoff、threshold、
custom は候補であり固定 ladder ではない。provider fields（prompt、camera、lens、motion）は
この object に入れない。

## p410 authoring procedure

1. story source IDs と visual-value handoff を読む。
2. scene ownership、canonical order、reveal ledger、start/end state を決める。
3. scene event beats と visible evidence を具体化する。
4. next-scene handoff と location/time transition を exact ID で書く。
5. scene set を `script.md` に L2 single writer が統合する。
6. ordinary validator で unique IDs、source refs、ordered event inventory、coverage、handoff、
   location、time-of-day を確認する。

主要 beat を一つの説明段落へ圧縮しない。独立した question/value shift/causal turn がある場合
は scene を分け、同一責務なら既存 scene/cut を厚くする。目標尺だけの filler は作らない。

## p420 Cut Blueprint

p420 は scene event を renderable cuts へ変換する。各 cut は一つの viewer-facing intent を
持ち、次を exact に束縛する。

- `cut_id`、`cut_function`、`target_beat`、`screen_question`、`dramatic_job`
- `audience_knowledge_delta`、`causal_proof`、`visual_evidence[]`
- `source_event_contract.primary_event_beat_id` と `source_event_beat_ids[]`
- `first_frame_contract`、`motion_contract`、`narration_contract`
- `must_show[]`、`must_avoid[]`、`asset_dependency_hint`、downstream handoff

cut count は must-see event beat と distinct visual obligation の coverage から導く。同じ
fact を証明する cut はまとめ、別の obligation があるときだけ分ける。first frame は current
visible state、motion はそこからの continuous change、narration は event boundary 内とする。

## Structural validation

p410/p420 完了時に次を確認する。

- scene/cut/beat/asset IDs が unique で、source refs、selectors、handoffs が解決する
- event inventory が authored beat の ordered list と一致し、must-see beat が cut に assigned される
- reveal constraints、location sequence、time-of-day、start/end state に drift がない
- first frame が静止画として imageable、motion が未許可の story event を追加しない
- narration role または explicit silence contract があり、visible action の caption にならない
- script と skeleton manifest の selector が一致する
- request を作る前に schema、type、duration、provider capability を確認する

不備があれば owner artifact と selector を修正し、validator を再実行する。別 agent の品質
判定や合格値を待たない。

## p450 Skeleton Manifest

p450 は `script.md` から `video_manifest.md` を `manifest_phase: skeleton` で materialize
する。scene/cut selector、`cut_contract`、optional legacy `scene_contract` read alias、
asset ID placeholder、image/audio/video execution shells を持つ。provider call は p500 以後で行う。

## Ownership and state

p400 L2 supervisor が `script.md`、skeleton manifest、state、navigation index の single
writer。scene author workers は scratch output だけを書き、source/readset path、selector、
output path を packet に含める。state は append-only delta event とし、scene/cut status、
artifact digest、ordinary validation result、request revision を記録する。

## References

- `docs/script-creation.md`
- `docs/data-contracts.md`
- `workflow/scene-outline-template.yaml`
- `workflow/cut-blueprint-template.yaml`
- `workflow/scene-conte-template.md`

