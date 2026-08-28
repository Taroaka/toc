# Design: Existing-story value amplification

## Decision

Markdown、YAML template、plain deterministic validator、semantic review を競合させず、次の4層に分ける。

1. `docs/adaptation-value-amplification.md`
   - なぜ必要か、authoring順、良い例・悪い例、provider boundaryを定義する人間向け正本。
2. `workflow/*template*`
   - 新しいAIがそのまま埋められる、コメント付きのartifact形。
3. `toc/adaptation_value_contract.py`
   - key名、型、enum、局所的cross-field条件を既存artifact方式に合わせて検証するplain validator。
   - required key / enum / markerを定数化し、schema driftをtestで検出する。
4. stage evaluator / semantic review
   - deterministic: marker、必須block、ID参照、空値、projection整合。
   - semantic: 原作価値への忠実さ、映画的増幅、generic illustrationへの縮退。

Pydantic / JSON Schema はcanonical artifactの主方式にしない。既存artifactはMarkdown内YAML、未知keyを許容するdict、legacy projection、custom cross-field validatorを前提としている。PydanticはFastAPI等の固定API入力境界、JSON Schemaは将来のIDE補助/exportに限定する。

## Canonical flow

```text
story.md.adaptation_source_contract.core_values[].value_id
  -> visual_value.md.adaptation_intent.source_value_ids[]
  -> visual_value.md.scene_visual_values[].scene_value_amplification.source_value_refs[]
  -> script.md.scenes[].scene_intent.scene_value_amplification.source_value_refs[]
  -> script/video_manifest cut_contract.expressive_contract.source_value_refs[]
```

## Contracts

### `adaptation_source_contract_v1`

原作の何を守るかを固定する。`source_story_promise`、`core_values[]`、`non_negotiable_events[]`、`non_negotiable_meanings[]`、`iconic_moments[]`、`forbidden_value_distortions[]` を持つ。

### `adaptation_intent_v1`

p300で、原作価値を映像・演技・空間・音・編集へ翻訳する全編方針を持つ。原作を変更する権限は持たない。

### `scene_value_amplification_v1`

各sceneの `why_this_scene_matters`、観客状態before/after、`emotional_contradiction`、映像/演技/空間/音/編集のopportunity、`iconic_moment_target`、`must_not_reduce_to[]` を持つ。

### `cut_expressive_contract_v1`

各cutが担当する原作価値、`audience_experience_delta`、`expressive_function`、performance / visual pressure / attention / edit / sound / afterimageを持つ。1 cut = 1 expressive intentを維持する。

## Compatibility

- 新規の既存物語 adaptation artifact はmetadata marker `adaptation_value_contract: required_v1` を持つ。
- 汎用templateではmarkerをコメント状態にし、既存物語の場合だけ有効化する。original storyはmarkerとadaptation blockを出力しない。
- markerがあるartifactは新契約をblocking検証する。
- markerがないlegacy artifactはwarning/未適用とし、新契約だけを理由にfailさせない。
- `expressive_contract` はprovider proseではなくreview/compilation source。下流compilerは描画可能・観察可能な断片だけを既存contractへ投影する。

## Verification

- plain contract validatorのvalid/invalid unit tests
- required-key / enum定数とtemplate keyの同期test
- story marker時のsource contract gate
- script scene/cutのID参照と必須block gate
- grounding readsetに新しい正本doc/schema/templateが含まれること
- pointer docs validator、slot validator、対象stage evaluator tests
