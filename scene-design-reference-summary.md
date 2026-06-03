# Scene Design Reference Summary

作成日: 2026-06-02

このまとめは、ToC の scene 設計を他エージェントへ渡すための参照パックである。
対象は「story を production scene / cut / prompt へ落とす設計」と、その review gate。

## 結論

現在の scene 設計で最も重要なのは、story の段落や場所を scene にすることではなく、物語の不可逆 beat を production scene に昇格させること。

p410 では scene を画像生成 prompt にしない。
`story.md` / `visual_value.md` を読み、p500 asset、p600 still、p700 narration、p800 motion が迷わない `scene_intent` と `story_specificity` を固定する。

## Scene の役割

scene は、物語全体の中で観客の情報、感情、期待、因果を変化させる劇的単位である。
scene が弱いと、後段の cut、image prompt、narration、motion は、どれだけ丁寧に書いても「きれいな場所の列」になりやすい。

scene は次を担う。

- 物語上の不可逆 beat を観客に体験させる
- 観客が追う問いを発生させ、scene 内で進める
- 価値変化を画面で読める状態にする
- 次 scene を発生させる具体的な因果を渡す
- p500/p600/p700/p800 が使える visual evidence と production handoff を作る

## Scene Count 方針

scene 数は固定数で決めない。
どの物語でも、意味のある production scene として成立する範囲で最大化する。

上限は、次に追加する scene が既存 scene と同じ `dramatic_question` / `value_shift` / `causal_turn` しか持てず、scene を増やすより各 scene 内の cut 設計を厚くした方が品質が上がる地点。

このため、scene-set review では必ず次を説明する。

- 次に追加できる scene 候補は何か
- その候補を scene 追加ではなく cut 増厚へ回す理由は何か
- 承認済み story の主要 beat が既存 scene に埋もれていないか

## Scene Specificity Gate

p410 scene review では、次の 7 項目をお願いではなく gate として扱う。
aggregate review に欠ける、または `TODO` / `pending` のままなら p400 readiness は落ちる。

1. `non_compressible_beat_inventory`
   - cut に圧縮してはいけない不可逆 beat が抽出されているか。
2. `scene_promotion_rule`
   - その beat を scene に昇格させる理由があるか。
3. `unique_scene_responsibility`
   - 各 scene が物語全体で固有の責務を持つか。
4. `actor_force_coverage`
   - 主人公、対立者、助力者、観測者など scene に圧力を与える力が設計されているか。
5. `object_meaning_ladder`
   - 道具や舞台装置の意味が scene ごとに段階変化しているか。
6. `concrete_handoff_chain`
   - 次 scene を発生させる物、音、視線、行為、圧力が具体的か。
7. `anti_template_language`
   - 抽象テンプレ文で埋めていないか。

禁止する代表的なテンプレ文:

- `主人公は前進できるか`
- `次へ進む理由が生まれる`
- `光が次の場面へ運ぶ`
- `価値変化の兆し`
- `場所の圧力`
- `主人公の姿勢と視線`

## Review Process

p410 は二段階。

1. `scene_set_review`
   - 全 scene の追加、削除、統合、分割、順序、因果接続、最大 meaningful scene count を見る。
   - 標準 critic:
     - critic_1: `scene_count_coverage`
     - critic_2: `dramatic_structure + reveal_order`
     - critic_3: `duration_density`
     - critic_4: `visual_production`
     - critic_5: `handoff_integrity`
2. `scene_detail_review`
   - 各 scene の必要性、内部密度、cut 化前の情報量、前後 handoff を見る。

p420 は cut blueprint。
全 scene が p410 gate を通った後にだけ、scene を cut 列へ分解する。

## Included Files

### Core Design Docs

- `docs/script-creation.md`
  - p400 / p410 / p420 の正本。scene 数最大化、story_specificity、review order を定義。
- `docs/implementation/scene-loop.md`
  - scene loop の恒久仕様。p410 completion gate、multi-agent roles、blocking findings を定義。
- `docs/implementation/agent-roles-and-prompts.md`
  - p410 reviewer / aggregator の役割定義。
- `docs/data-contracts.md`
  - state、review loop、p400 readiness のデータ契約。
- `docs/how-to-run.md`
  - 実行手順と p410/p420 review loop の運用メモ。

### Templates

- `workflow/script-template.yaml`
  - `script.md` の scene/cut/review 構造テンプレート。
- `workflow/scene-outline-template.yaml`
  - scene contract と `story_specificity` の詳細テンプレート。
- `workflow/scene-conte-template.md`
  - scene/cut のコンテ設計テンプレート。
- `workflow/scene-video-manifest-template.md`
  - scene 単体の video manifest テンプレート。
- `workflow/cut-blueprint-template.yaml`
  - p420 cut blueprint の詳細テンプレート。

### Gate Implementation References

- `toc/review_loop.py`
  - p410 critic/aggregator prompt と `Scene Specificity Gate` marker 定義。
- `toc/stage_evaluator.py`
  - p400 readiness gate。p410 aggregate review の必須 marker と unresolved 値を検出。

### Test References

- `tests/test_review_loop.py`
  - p410 prompt / aggregate review materialization の検証。
- `tests/test_stage_evaluator_scripts.py`
  - p400 readiness が Scene Specificity Gate 欠落やテンプレ文を落とすことの検証。
- `tests/test_verify_pipeline.py`
  - pipeline fixture 側の p410 aggregate review 構造。

## Reading Order

1. `scene-design-reference-summary.md`
2. `docs/script-creation.md`
3. `docs/implementation/scene-loop.md`
4. `workflow/scene-outline-template.yaml`
5. `workflow/script-template.yaml`
6. `toc/review_loop.py`
7. `toc/stage_evaluator.py`

## Current Caveat

このパックは設計とgateの参照であり、個別物語の生成結果は含まない。
個別runの品質確認には、対象runの `script.md`、`scene_set_review.md`、`scene_detail_review.md`、`logs/eval/*/aggregated_review.md` を別途見る。
