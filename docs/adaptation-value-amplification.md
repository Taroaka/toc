# 既存物語の価値増幅契約

## 目的

ToC が既存の評価された物語を映像化するとき、成功条件は筋を別物へ作り替えることではない。原作で観客に届いてきた価値を特定し、その価値を scene / cut の演技、空間、構図、編集、音へ翻訳して、もう一度強く体験させることである。

この文書は会話履歴を持たない新しい authoring agent のための正本である。key の機械的な形は `workflow/story-template.yaml`、`workflow/visual-value-template.yaml`、`workflow/script-template.yaml`、`workflow/video-manifest-template.md` を使い、局所的な必須 key・enum・参照整合は `toc/adaptation_value_contract.py` が検証する。各汎用 template の marker はコメント状態なので、既存物語を扱うときだけコメントを外し、adaptation block を出力する。original story では marker と adaptation block を出力しない。

## 基本原則

1. **物語事実の忠実さと、映画的な増幅を分離する。** `non_negotiable_*` は変えてはいけない内容、`cinematic_gain` は同じ内容をどう強く体験させるかである。
2. **形ではなく効果へ忠実である。** 原文の説明をそのまま絵にするのではなく、その場面が生む期待、恐怖、承認、喪失、解放を再現する。
3. **抽象語を観察可能な差へ変換する。** 「感動的」「映画的」ではなく、呼吸、視線、身体の距離、遮蔽物、音の密度、編集点を書く。
4. **scene は価値変化、cut は一つの表現機能を持つ。** 美しいが物語価値を進めない cut は合格にしない。
5. **原作価値を変える repair は自動化しない。** 原作の意味、主要イベント、人物関係、結末を変える場合は人間承認へ送る。

## 正本フロー

```text
story.md
  adaptation_source_contract.core_values[].value_id
    ↓
visual_value.md
  adaptation_intent.source_value_ids[]
  scene_visual_values[].scene_value_amplification.source_value_refs[]
    ↓
script.md / video_manifest.md
  scenes[].scene_intent.scene_value_amplification.source_value_refs[]
  scenes[].cuts[].cut_contract.expressive_contract.source_value_refs[]
```

下流は上流の `value_id` を同じ文字列で参照する。似た意味の別 ID を勝手に作らない。

## authoring 順序

### 1. story: 原作価値を固定する

`story_metadata.adaptation_value_contract: required_v1` を宣言し、`adaptation_source_contract` を書く。

- `source_story_promise`: この作品を知る観客が失ってはいけない中心的な約束。
- `core_values[]`: 追跡可能な価値。各項目に安定 ID、意味、期待する観客効果、根拠 event を持たせる。
- `non_negotiable_events[]`: 圧縮はできても消去・逆転できない出来事。
- `non_negotiable_meanings[]`: 出来事を残しても意味を歪めれば失敗となる解釈。
- `iconic_moments[]`: 観客が再体験を期待する象徴的瞬間。
- `forbidden_value_distortions[]`: 現代化・スペクタクル化で起こりやすい意味の改悪。

frontend の deterministic scaffold が初期候補を置く場合、その候補は原作価値の最終判断ではない。`authoring_provenance: deterministic_candidate_requires_story_semantic_review` を残し、story semantic review の `adaptation_value_fidelity` で research / 原作に照らして修正・承認する。scene の位置だけから価値を確定したり、別作品の汎用的な価値語で上書きしたりしない。review 済み `adaptation_source_contract` がある場合、下流は必ずそれを一方向 projection する。

### 2. p300 visual value: 映画言語への翻訳方針を決める

`visual_value_metadata.adaptation_value_contract: required_v1` を宣言する。`adaptation_intent` は全編方針、各 `scene_value_amplification` は scene 固有の観客体験変化を担当する。

`cinematic_gain` の5要素はすべて、同じ価値へ協調して働かせる。

- `performance`: 表情ラベルではなく、抑制、躊躇、呼吸、視線、身体反応。
- `blocking_and_space`: 距離、遮蔽、孤立、包囲、接近、退路。
- `camera_and_composition`: 誰の認識に寄り添い、何をいつ見せないか。
- `edit_and_rhythm`: hold、cut、反応、情報開示、余韻の時間関係。
- `sound`: 環境音、沈黙、音の先行・残響。台詞や音楽だけに限定しない。

### 3. p400 scene: 価値増幅を制作可能な scene 意図へ固定する

`scene_intent.scene_value_amplification` は p300 の同 scene 契約を継承し、script の具体的な scene event と整合させる。`must_preserve_story_facts[]` は event 契約と矛盾させず、`success_evidence[]` は「映像を見れば何が成立したと判断できるか」を書く。

### 4. cut: 一つの表現機能を割り当てる

各 `cut_contract.expressive_contract` は scene の増幅を分担する。`expressive_function` は次から一つを選ぶ。

`recognition | withhold | pressure | release | contrast | reaction | reframe | afterimage | spectacle | transition`

`audience_experience_delta` は cut 前後の観客体験差、`edit_trigger` は切る理由、`emotional_afterimage` は cut 後に残す感覚である。`spectacle` も原作価値を増幅する場合だけ使い、豪華さ自体を目的にしない。

## 良い記述と悪い記述

悪い例:

```yaml
camera_and_composition: "映画的で感動的にする"
performance_beat: "主人公が悲しそうにする"
audience_experience_delta: "感動が増す"
```

良い例:

```yaml
camera_and_composition: "戸口に遮られた主人公を奥へ置き、名前を呼ばれた瞬間だけ遮蔽物のない正面へ切る"
performance_beat: "返事を急がず、呼吸を一度止めてから相手を見返す"
audience_experience_delta: "誰にも見つけられない孤立から、存在そのものを認識された緊張と安堵へ"
```

## validator と semantic review の境界

deterministic validator が判定するもの:

- marker、schema version、必須 key、非空 list
- 必須文字列の型、scene / cut / `value_id` の重複
- scene / cut が未知の `value_id` を参照していないこと
- `expressive_function` の enum
- p300 visual value → p400 script → manifest の scene / cut が欠落・余剰なく exact projection されること

semantic reviewer が判定するもの:

- 抽出した価値が本当に原作の評価理由を表しているか
- scene の before/after が原作の感情曲線を増幅しているか
- 5つの映画言語が一つの価値へ収束しているか
- cut が説明絵、美麗な壁紙、抽象的な「映画感」へ縮退していないか
- 原作の iconic moment が既視感の再現だけでなく、再発見を生むか

型が正しいだけでは合格ではない。逆に、意味品質を Python の文字列規則だけで判定しない。

## provider boundary

`value_id`、schema 名、`scene_amplification_ref`、抽象的な review 文を image / video provider の prose へ直接送らない。compiler は既存の `viewer_contract`、`cinematic_contract`、first-frame、motion、sound/rhythm 等へ、描画・観察できる断片だけを投影する。内部 ID は trace と review に残す。

## compatibility

新規の既存物語 adaptation は metadata に `adaptation_value_contract: required_v1` を持たせる。marker がある artifact は不足を blocking とする。marker がない legacy artifact は、この契約がないことだけを理由に fail させない。

scene-series の既存テンプレートは、series 全体の `story.md` / `visual_value.md` lineage をまだ必須化していないため、marker を自動付与しない legacy scope とする。ただし個別 scene script / manifest が marker を宣言した場合は evaluator が同じ契約を blocking 検証し、迂回経路にはしない。series 用テンプレートへ marker を標準搭載するのは、series 全体の source-value root と p300 projection を定義する別 migration で行う。
