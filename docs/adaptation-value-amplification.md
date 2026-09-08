# 既存物語の価値増幅契約

既存物語を映像化するとき、原作の value、non-negotiable event、人物関係、結末を source IDs
で保ち、scene/cut の performance、space、composition、edit、sound へ一方向に投影する。
これは authoring と structural validation の契約であり、別の content judge は起動しない。

## 基本原則

1. 物語事実と cinematic gain を分離する。
2. 原文の説明の形ではなく、期待、恐怖、承認、喪失、解放など観客効果を映像へ翻訳する。
3. 抽象語を呼吸、視線、身体距離、遮蔽、音密度、編集点など観察可能な差へ変える。
4. scene は value shift、cut は一つの表現機能を持つ。
5. 原作の意味、主要イベント、人物関係、結末を変える hybridization は、確定前にユーザーへ
   明示許可を求める。

## 正本 lineage

```text
story.md
  adaptation_source_contract.core_values[].value_id
    ↓
visual_value.md
  adaptation_intent.source_value_ids[]
  scene_visual_values[].scene_value_amplification.source_value_refs[]
    ↓
script.md / video_manifest.md
  scene_intent.scene_value_amplification.source_value_refs[]
  cut_contract.expressive_contract.source_value_refs[]
```

下流は上流の value ID を exact string で参照する。似た意味の別 ID を作らない。

## 1. Story value contract

既存物語の run は `story_metadata.adaptation_value_contract: required_v1` と
`adaptation_source_contract` を宣言する。

```yaml
adaptation_source_contract:
  source_story_promise: "観客が失ってはいけない中心の約束"
  core_values:
    - value_id: value_01
      meaning: ""
      expected_audience_effect: ""
      source_event_refs: []
  non_negotiable_events: []
  non_negotiable_meanings: []
  iconic_moments: []
  forbidden_value_distortions: []
```

各 value/event/meaning は research/source passage の ID を持つ。新しい事実を足す場合は
追加調査または明示された creative hypothesis として隔離する。

## 2. Visual value authoring

p300 `visual_value.md` の `adaptation_intent` は全編方針、各
`scene_value_amplification` は scene 固有の観客体験変化を持つ。

[観客の理解と意味の設計](story-creation.md#観客の理解と意味の設計) を採用する場合、
`audience_state_before / audience_state_after` は理解の維持・深化・揺らぎも扱う。
反復要素の意味や世界観の見せ方は、既存の value ID と scene に接続し、原作の曖昧さ、
対立する立場、結末を保つ。理解を変えるためだけに原作にない教訓・救済・反転を加えない。
この汎用指針を original に使うために、adaptation の marker や専用 block を要求しない。

- performance: 抑制、躊躇、呼吸、視線、身体反応
- blocking_and_space: 距離、遮蔽、孤立、包囲、接近、退路
- camera_and_composition: 誰の認識に寄り添い、何を見せないか
- edit_and_rhythm: hold、cut、反応、情報開示、余韻の時間関係
- sound: 環境音、沈黙、先行音、残響

## 3. Scene and cut authoring

p400 scene intent は p300 の同 scene 契約を継承し、具体的な scene event と整合させる。
`must_preserve_story_facts[]` は event contract と一致させ、`success_evidence[]` は
映像を見れば成立したと分かる状態を書く。

各 `cut_contract.expressive_contract` は一つの function を担当する。

```yaml
expressive_contract:
  source_value_refs: [value_01]
  expressive_function: recognition|withhold|pressure|release|contrast|reaction|reframe|afterimage|spectacle|transition
  audience_experience_delta: ""
  edit_trigger: ""
  emotional_afterimage: ""
```

spectacle は原作 value を増幅する場合だけ使い、豪華さだけを目的にしない。

## 4. Structural checks

validator は次を確認する。

- marker、schema version、required fields、non-empty list、types
- scene/cut/value ID の uniqueness と source reference 解決
- expressive_function の enum
- p300 → p400 → manifest の value ID projection が欠落/余剰なく exact であること
- non-negotiable event の順序、reveal boundary、scene/cut handoff
- provider prompt に value ID、schema 名、abstract design text を直接出していないこと

意味を隠すために missing source ID や abstract placeholder を使わない。structural check が
失敗した場合は owning artifact を修正し、同じチェックを再実行する。

## 5. Provider boundary

`value_id`、schema 名、`scene_amplification_ref`、抽象的な設計文は image/video
provider prose に送らない。compiler は viewer、first-frame、motion、sound/rhythm から
描画・観察できる断片だけを投影する。内部 IDs は manifest metadata と source digest に残す。

## 6. Hybridization and compatibility

Contradictory source elementsを同じ scene/settings に混成する場合、ユーザーの explicit choice、
selected source IDs、actor、timestamp、理由を run artifact に保存する。自動 hybridization はしない。

marker がある artifact は contract version、source ID、projection、digest の欠落を普通の
structural error にする。marker がない legacy artifact は、契約欠落だけで読み込みを止めない。
scene-series が marker を宣言した場合も同じ projection/structural checks を使う。
