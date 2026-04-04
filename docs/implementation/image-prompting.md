# Image Prompting（Gemini Image / cross-model）: 正本

このドキュメントは **画像生成プロンプト品質**をシステムの根幹として扱い、
`video_manifest.md` の `scenes[].image_generation.prompt` を「全体 → 個別」の順で安定して組み立てるための正本。
ただし、**全scene/cutに新規の生成静止画が必要とは限らない**。新規生成は、同じ場所/物体/人物状態の continuity anchor を初めて作るとき、または複数scene/cutで再利用する参照画像が必要なときに優先する。

画像生成の正解は、**「うまい一文を書く」ことではなく、構造化して anchor を決め、reference を固定し、manifest を直接レビューし、story/script と矛盾していないか確認してから回すこと**である。

画像生成の既定順は、**対象選定 → contract 設定 → subagent review → 修正反映 → 再 review → 人間レビュー → 画像生成** とする。review は `video_manifest.md` を直接対象にし、`image_generation.review` に結果を書き戻す。review は単なる missing character 検出ではなく、prompt が環境寄りに流れすぎていないか、story 上の関係性/行為が抜けていないかも確認し、足りない `character_ids` は先に補完する。各 cut の review 状態は `agent_review_ok` と `human_review_ok` を持ち、さらに **false 理由 key** を明示する。canonical field 名は `agent_review_reason_keys` とし、現行の `agent_review_reason_codes` は互換 alias として扱う。criterion score は `rubric_scores`、加重合計は `overall_score` に残す。**両方 false の cut が残っている限り画像生成には進まない**。また、**prompt 本文に人物が出ているのに `image_generation.character_ids` が空の entry は review fail** とする。人物参照は自然言語だけに頼らず、manifest の `character_ids` で明示する。

対象:
- `/toc-immersive-ride` の `video_manifest.md`（特に Gemini Image）
- scene-series / 通常 run の `video_manifest.md`（静止画生成）

除外:
- アニメ/イラスト調の最適化
- Midjourney 専用構文（`--ar` など）に依存したテンプレ

---

## 結論（最短の型）

**prompt は 1本の自由文にせず、毎回同じ見出し順で書く。**

さらに、正しい順番は「うまい一文を書く」ではなく、
**構造化する → anchor を決める → reference を固定する → manifest をレビューする → story/script 整合を確認する → 画像生成する** である。
camera は `30mm` のような数値単独で止めず、`広め / 中広角 / 寄り` と `前景 / 中景 / 背景`、そして「何を読ませるか」まで書く。

加えて運用順は次の通り。

1. `still_image_plan` で新規生成対象を確定する
2. `python scripts/review-image-prompt-story-consistency.py --manifest output/<run>/video_manifest.md --fix-character-ids` で story/script 整合を確認し、不足 `character_ids` を補完する
3. review 結果で問題がある cut は `image_generation.review.agent_review_ok: false` になり、理由は `agent_review_reason_keys`（または互換 alias の `agent_review_reason_codes`）に残る
4. rubric の各軸 `story_alignment` / `subject_specificity` / `prompt_craft` / `continuity_readiness` / `production_readiness` を見て、弱い軸から直す
5. false reason に対応する fix を manifest に反映する
6. fix 後に再 review して finding が消えた cut は、subagent が `agent_review_ok: true` に戻す
7. 人間が issue を理解したうえで例外許容して進める cut だけ `python scripts/review-image-prompt-story-consistency.py --manifest output/<run>/video_manifest.md --set-human-review scene02_cut01` のように `human_review_ok: true` を付け、判断理由も残す
8. manifest review を通してから、初めて画像生成を回す

## Review lifecycle（manifest 契約）

この契約は Urashima 専用ではなく repo 全体に適用する。各 `image_generation.review` は、少なくとも次の review field を明示する。

```yaml
contract:
  target_focus: "character|relationship|setpiece|blocking|environment"
  must_include: []
  must_avoid: []
  done_when: []
agent_review_ok: false
agent_review_reason_keys:
  - missing_story_action
  - camera_or_composition_under_specified
rubric_scores: {}
overall_score: 0.0
human_review_ok: false
human_review_reason: ""
```

補足:

- 現行表記として `agent_review_reason_codes` を使っていてもよいが、意味は `agent_review_reason_keys` と同じに保つ
- `agent_review_reason_summary` は任意の補助説明であり、reason key の代替にはしない

意味:

- `agent_review_ok`
  - subagent が「この entry は story/script/reference 契約を満たしている」と判定したときだけ `true`
  - 不足がある間は `false`
- `agent_review_reason_keys`
  - `agent_review_ok: false` の根拠
  - false のときは 1 つ以上必須
  - fix 完了後は空配列に戻してよい
- `rubric_scores`
  - criterion score
  - `story_alignment` / `subject_specificity` / `prompt_craft` / `continuity_readiness` / `production_readiness`
- `overall_score`
  - rubric score の加重合計
- `human_review_ok`
  - 人間が finding を理解したうえで例外許容した記録
  - subagent finding を消した意味にはしない
- `human_review_reason`
  - 人間 override の理由
  - `human_review_ok: true` のときは必須

既定の reason key:

- `source_anchor_missing_from_prompt`
- `missing_character_id`
- `missing_object_id`
- `prompt_only_local_mismatch`
- `prompt_missing_expected_character_anchor`
- `prompt_missing_expected_object_anchor`
- `prompt_subject_drift`
- `blocking_drift`
- `missing_required_prompt_block`
- `prompt_not_self_contained`
- `non_japanese_prompt_term`
- `prompt_mentions_character_but_character_ids_empty`
- `image_contract_missing`
- `image_contract_must_include_unmet`
- `image_contract_must_avoid_violated`
- `image_contract_target_focus_unmet`
- `image_prompt_story_alignment_weak`
- `image_prompt_subject_specificity_weak`
- `image_prompt_continuity_weak`
- `image_prompt_production_readiness_weak`

運用ルール:

1. subagent は不足を見つけた entry を `agent_review_ok: false` にする
2. subagent は false 理由を `agent_review_reason_keys` に残す
3. fix 可能なものは manifest 側へ反映する
4. fix 後に subagent が再 review し、解消した entry は `agent_review_ok: true` に戻す
5. 未解消 finding を人間判断で許容する場合だけ、人間が `human_review_ok: true` と `human_review_reason` を記録する

subagent review の必須 criterion:

- `[全体 / 不変条件]`
- `[登場人物]`
- `[小道具 / 舞台装置]`
- `[シーン]`
- `[連続性]`
- `[禁止]`

上記 6 block のいずれかが欠けている prompt entry は、内容の良し悪し以前に設計違反として `agent_review_ok: false` にする。reason key は `missing_required_prompt_block` を使い、必要なら補助説明で欠けた block 名を列挙する。

独立性 criterion:

- 画像生成 AI は stateful ではない前提で扱う
- prompt 本文で `scene03_cut01` のような他 cut 参照をしない
- `前カット`, `次カット`, `前scene`, `次scene`, `前のprompt` のような参照依存表現を使わない
- `[連続性]` には「この cut 単体で何が読み取れるべきか」を書き、別 prompt の記憶を前提にしない
- 英語の混在語 `rideable` は使わず、日本語の `騎乗可能` などへ統一する
- prompt 本文に人物名があるのに `image_generation.character_ids` が空なら `prompt_mentions_character_but_character_ids_empty` として false にする

still 生成の既定実行対象:

- story cut は `still_image_plan.mode: generate_still` のものだけを既定で生成する
- `reuse_anchor` と `no_dedicated_still` は、明示的に `--image-plan-modes` を広げない限り生成しない
- `assets/characters/*` と `assets/objects/*` の reference 画像は `still_image_plan` に関係なく既定対象に含める

## 言語ポリシー（重要）

- `video_manifest.md` は **日本語で書く**（修正指示・レビューを日本語で完結させるため）。
- 見出しは **日本語**で書く。review gate は `[全体 / 不変条件]`, `[登場人物]`, `[小道具 / 舞台装置]`, `[シーン]`, `[連続性]`, `[禁止]` の 6 ブロックを必須として扱う。
  - 生成スクリプト側は英語見出しも互換で認識するが、運用は日本語に寄せる。
- prompt 本文も日本語で完結させる。英語の production shorthand を混ぜない。
- 禁止語彙（`禁止` / `assets.style_guide.forbidden`）も日本語で書く方向で統一する（例: `画面内テキスト`, `字幕`, `ウォーターマーク`, `ロゴ`）。

必須ブロック（順序固定）:

1) `全体 / 不変条件`（全scene共通の不変条件）
2) `登場人物`（人物・参照一致）
3) `小道具 / 舞台装置`（重要アイテム/舞台装置の不変条件）
4) `シーン`（場面固有の描写）
5) `連続性`（前後接続）
6) `禁止`（禁止/地雷）

この 6 block は推奨ではなく required。subagent review は block の欠落を検出した時点で false にする。

この repo の生成は、最終的に `scenes[].image_generation.prompt` のテキストをそのまま API に渡すため、
**「どこに何を書くか」自体をテンプレ化**すると品質が安定する。新規の静止画は、anchor を作る scene/cut に集中させる。

---

## 1) 画像品質を上げる prompt の原則（portable / cross-model）

### 1.1 具体に落とす（曖昧語の連打を避ける）

悪い例:
- “beautiful, epic, amazing”

良い例:
- 被写体（誰/何） + 位置関係（前景/中景/背景） + 光（どこから/色） + カメラ（POV/画角/動き）

### 1.2 一貫性は「固定フレーズ + 参照画像」で作る

人物/小物/手元が重要なら:
- **参照画像**（character / hands / props）を用意し、必要なscene/cutで `references` に入れる
- さらに **同じ語で**特徴を繰り返す（言い換え禁止）
- 参照画像は、毎回新規に作るのではなく、同じ場所/物体/人物状態をまたぐ複数scene/cutの共通アンカーとして再利用する

### 1.3 “構図のアンカー”を明示する

画像生成は「何が重要か」の優先順位に迷うと破綻しやすい。
優先したい要素は **画面内の位置**まで書く:

- “a clear foreground anchor in the lower foreground (e.g., hands+bar for an immersive ride, or a prop like a compass)”
- “leading lines centered (path / track / rail)”
- “main subject in the mid-ground”

（日本語で書くなら例）
- 「画面下の前景に“アンカー”（手元/小道具など）」
- 「導線（道/軌道/レール）を中央構図」
- 「登場人物は中景」

### 1.4 ネガティブは「禁止カテゴリ + 事故りやすい欠陥」を短く

入れすぎると逆に不安定になるので、まずは以下を定番化:
- 文字系: `画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし`
- スタイル: `アニメ/漫画/イラスト調を避ける`
- 手/人体: `手の崩れを避ける、指の増殖を避ける`

### 1.5 “シネマ/写真”語彙は「必要なものだけ」使う（チートシート）

モデルやプロバイダに依存しにくい（＝cross-modelで通りやすい）語彙だけに絞る。

- Shot / framing:
  - `導入の広いショット`, `中距離`, `クローズアップ`, `一人称POV`, `中央構図`
  - `foreground / mid-ground / background` を必ず書く（位置指定が強い）
- Lens / DOF:
  - `35mm lens`, `50mm lens`, `shallow depth of field`, `soft bokeh`
  - ただし “レンズ指定は必須ではない”。崩れるなら外す
- Lighting:
  - `soft key light`, `gentle rim light`, `golden hour`, `practical lighting`, `volumetric light (subtle)`
- Color / grade:
  - `warm tones`, `muted palette`, `high contrast (controlled)`
- Texture:
  - `subtle film grain`, `realistic textures`, `natural imperfections`

ポイント:
- “盛る”ための羅列ではなく、**破綻しやすい要素（手/バー/視点/構図）を守る**ために使う。

### 1.6 技術パラメータは “prompt ではなくフィールド” に寄せる

aspect ratio / size は `image_generation.aspect_ratio` / `image_generation.image_size` を使う。
既定の画像サイズは `1K` とし、より高解像度が必要な scene だけ個別に上書きする。
（`--ar` のような Midjourney 専用構文で書かない）

---

## 2) 推奨テンプレ（そのまま貼れる）

`image_generation.prompt: |` の中身:

```text
[全体 / 不変条件]
実写、シネマティック、実物セット感。自然な映画照明。
画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

[登場人物]
<character constraints that must stay consistent across scenes>

[小道具 / 舞台装置]
<object/setpiece constraints that must stay consistent across scenes>

[シーン]
舞台: <どこ/いつ/天候>。見せ場: <1文で>.
構図: <前景/中景/遠景 + 主役の配置>.
カメラ: <POV/画角/動き（必要ならレンズ感）>.

[連続性]
前と一致: <光/位置/進行方向>.
次への仕込み: <アンカー/色/方向>.

[禁止]
アニメ/漫画/イラスト調。
手の崩れ、指の増殖、読めない物体、パース破綻。
```

メモ:
- このテンプレは “文章の上手さ” ではなく **指示の網羅と優先順位**で勝つためのもの。
- sceneごとの創作要素（セット装飾など）は `SCENE` に入れ、根拠が必要な事実は story/research 側で担保する。

---

## 3) /toc-immersive-ride（cinematic_story）向け invariants（推奨セット）

注意: これは `/toc-immersive-ride --experience cinematic_story` 用の固定条件。通常の run / scene-series では前提にしない（必要なら個別に指定する）。

`全体 / 不変条件` に毎回入れる（または将来的に assets から自動注入する）:

- `実写、シネマティック、実物セット感`
- `視点（POV/三人称）を明示し、1カット内で視点ブレさせない`
- `前景/中景/遠景のアンカー（人物/アイテム/導線）を指定する`
- `画面内テキストなし、字幕なし、ウォーターマークなし`

さらに “事故りやすい” ので早めに禁止しておく:
- `アニメ/漫画/イラスト調`
- `人体の崩れ / 指の増殖 / パース破綻`

## 3.2 /toc-immersive-ride（cloud_island_walk）向け invariants（推奨セット）

`cloud_island_walk` は「雲上の島を歩いて理解を深める」体験テンプレ。
`全体 / 不変条件` の定番（scene間の一貫性のため）:

- `一人称POVで前進しながら歩く`
- `雲海の上に浮かぶ楽園の島`（概念を実写の比喩として表現）
- `水平線安定、カメラ高さ一定、道/導線を中央`（連続性アンカー）
- `実写、シネマティック、実物セット感`
- `画面内テキストなし、字幕なし、ウォーターマークなし`

特に地雷なので早めに禁止しておく:
- `アニメ/漫画/イラスト調`
- `手の崩れ / 指の増殖`
- `画面内テキスト / 字幕 / ウォーターマーク / ロゴ`
- `三人称 / 肩越し / 自撮り`

## 3.1 character_bible を scene で選ぶ（混ざり防止）

複数キャラがいる物語では「全キャラ参照を全sceneに入れる」と混ざって破綻しやすい。
この repo では `video_manifest.md` の `image_generation.character_ids` で、そのsceneに登場するキャラだけを選び、
`--apply-asset-guides --asset-guides-character-refs scene` で参照画像/固定フレーズを注入する運用を推奨する。
人物が出る still では、`assets/characters/<name>_refstrip.png` が存在する場合、それも reference に自動で含めて一貫性を強める。
さらに `assets.character_bible[].physical_scale` と `relative_scale_rules` があれば、still prompt の `[登場人物]` に自動注入し、絶対体格と相対サイズを固定する。
`assets.character_bible[].review_aliases` があれば、story/script review で「その cut に本来出るべき人物が prompt/character_ids から欠けていないか」を検査できる。

B-roll（キャラを映さない）sceneは `character_ids: []` を明示し、キャラ注入ゼロにする。

- `character_reference` scene は reference-only として扱い、**全身（頭からつま先まで）** だけを撮る
- 顔寄り、上半身のみ、途中クロップの基準画像は作らない
- 参照用の識別子は人間が読める安定名にする（例: `protagonist_front_ref`, `protagonist_side_ref`, `protagonist_back_ref`）

### Human character baseline（推奨）

人間キャラは、物語上の特段の理由がない限り「美男美女（映画俳優レベル）」を初期値にする。
`assets.character_bible[].fixed_prompts` に短文で入れて固定する（例）:

- `人間キャラは美男美女（映画俳優レベル）。顔立ちのバランス、肌の質感、表情、目の印象が自然で実写的`

注意:
- “魅力”は過度な誇張より、実写で成立する自然さ（骨格/肌/表情/所作）を優先する

## 3.3 object_bible を scene で参照する（舞台装置の映画品質）

この repo では、竜宮城/玉手箱のような「背景ではなく物語の主役級 setpiece / artifact」を
`assets.object_bible` として設計し、scene 側は `image_generation.object_ids` で参照する運用を推奨する。

- 目的: “本や絵本では語られなかったディテール”を、**映像だけで伝わる情報**として固定し、sceneの思いつきにしない
- 運用:
  - `assets.object_bible[].reference_images` を先に生成（`assets/objects/...png` を `image_generation.output` にする reference scene）
  - story scene は `object_ids: ["..."]` を宣言
- 生成は `--apply-asset-guides` で、object の固定フレーズを `小道具 / 舞台装置` に自動注入する
  - 見出しは日本語推奨（`[小道具 / 舞台装置]`）。スクリプト側は英語見出しも互換で認識する。

ポイント:
- 画面内の文字で説明しない（看板/刻印/銘板などは禁止）。**形/光/動き/ショー性**で理解させる。
- “物語に直接関係しない”ショー/仕掛けでも、映像の魅力と世界の深みを作る（spectacle）。

### 3.4 Ryugu exploratory block（Otohime 登場前の視覚報酬）

`Ryugu Palace` の内部を見せる場面では、乙姫をすぐに登場させず、まず **4-6 cuts / 1 cut = 約4秒** の探索ブロックとして設計してよい。

このブロックの目的は次の通り。

- 竜宮城を「説明」ではなく「発見」で見せる
- 実写の見せ物として、建築・機構・光・群泳を先に印象づける
- 乙姫の登場を遅らせ、次のドラマの入口を強くする

推奨ルール:

- `character_ids: []` を基本にし、乙姫は出さない
- `object_ids: ["ryugu_palace"]` を使い、舞台装置を固定する
- 各 cut は `4` 秒前後、ナレーションなし
- 最後の cut は「乙姫が現れる直前の門/回廊/玉座の間の入口」で止める

Ryugu 探索ブロックの prompt には、以下の順で書くと安定しやすい。

1. `[全体 / 不変条件]` に実写・シネマ・プラクティカルを明記する
2. `[小道具 / 舞台装置]` に `ryugu_palace` の固定フレーズを入れる
3. `[シーン]` で gate / corridor / atrium / spectacle / threshold を cut ごとに変える
4. `[連続性]` で「前の cut の導線」と「次の cut の発見」を接続する
5. `[禁止]` に文字要素とアニメ調を再掲する

例:

```text
[全体 / 不変条件]
実写、シネマティック、プラクティカルエフェクト。自然な映画照明。
画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

[小道具 / 舞台装置]
Ryugu Palace is built from living coral, mother-of-pearl, and lacquered bronze ribs; wet sheen; realistic scale.
Interior features suspended bubble-lanterns and bioluminescent coral chandeliers; no text signage.
Showmanship: distant atrium, swirling fish schools, controlled currents.

[シーン]
珊瑚門が開く。回廊が深く伸びる。建築そのものが生き物のように呼吸する。
最後の cut は、乙姫が現れる直前の入口で止める。
```

例:

```yaml
assets:
  character_bible:
    - character_id: "momotaro"
      reference_images: ["assets/characters/momotaro.png"]
      fixed_prompts: ["momotaro matches reference exactly"]
    - character_id: "oni_leader"
      reference_images: ["assets/characters/oni_leader.png"]
      fixed_prompts: ["oni leader matches reference exactly"]

scenes:
  - scene_id: 5
    image_generation:
      character_ids: ["momotaro", "oni_leader"]
      references: []
      prompt: |
        [GLOBAL / INVARIANTS]
        ...
```

---

## 4) 具体例（immersive ride）

### 4.1 Character turnaround 基準画像（scene_id: 0, full-body only）

この repo では、キャラクター参照画像を「前/横/後ろ」の3枚で作り、さらに3枚を横並び結合した1枚（動画生成側の参照）も作る運用を推奨する。
`scripts/generate-assets-from-manifest.py` の `--character-reference-views front,side,back --character-reference-strip` で自動生成できる。

また、後から中間sceneを差し込めるように `scene_id` は **10刻み**（例: 10,20,30...）で運用するのがおすすめ（後段は scene_id の連番を前提にしない）。
`scene_id: 0` は character_reference 専用に分け、story scene の spacing と混ぜない。

```text
[GLOBAL / INVARIANTS]
Photorealistic, cinematic, practical effects. Natural film lighting. No text.

[SCENE]
Character reference. Full-body head-to-toe, feet fully visible (no cropping).
Neutral studio-like background, soft key light + gentle rim light, sharp focus.

[AVOID]
anime/cartoon/illustration, exaggerated makeup, text, watermark.
```

### 4.2 Scene 1（世界への入口）

```text
[GLOBAL / INVARIANTS]
実写、シネマティック、プラクティカルエフェクト（実物セット感）。アニメ調なし。
視点: 客観（三人称）。1カット内で視点ブレさせない。
画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

[CHARACTERS]
The story character(s) MUST match the reference image exactly (same face, hair, outfit).

[SCENE]
Setting: dusk, misty entrance gate into the world of <topic>. Practical set pieces, real lighting.
Key moment: the gate opens and a story character draws you into the world.
Composition: 前景=導線（道/門柱/光の筋）; 中景=物語キャラ; 遠景=発光するゲート（中央）。

[CONTINUITY]
Set up next: 導線が左へカーブし、左側から暖かい光が漏れる。

[AVOID]
anime/cartoon/illustration, CGI look, distorted hands, extra fingers, text, logos.
```

### 4.3 Scene 2（最初の見せ場へ）

```text
[GLOBAL / INVARIANTS]
実写、シネマティック、プラクティカルエフェクト（実物セット感）。アニメ調なし。
視点: 客観（三人称）。カメラ高さは安定。画面内テキストなし。

[CHARACTERS]
The story character(s) match the reference image exactly.

[SCENE]
Setting: <topic> の世界の新エリアへカメラが入る。実物の霧と水しぶき。金属の濡れ反射。
Key moment: the first big reveal appears ahead.
Composition: 中景=物語キャラ（必要なら）; 遠景=見せ場の対象（中央）; 前景=霧/水しぶきは控えめ。

[CONTINUITY]
Must match previous: 光源方向/色温度/空気感。
Set up next: 見せ場の対象がフレームを支配し、次カットで寄れる状態にする。

[AVOID]
anime/cartoon/illustration, unreadable shapes, extreme motion blur, text, watermark.
```

---

## 5) チェックリスト（生成前レビュー）

- [ ] 視点（POV/三人称）とカメラ意図が明示されている（1カット内でブレない）
- [ ] “画面内のアンカー”が書かれている（前景/中景/背景の配置。手元固定に限らない）
- [ ] 参照画像を使う前提の文がある（“must match reference” 等）
- [ ] 禁止事項（文字/アニメ調/崩れ手）が短く入っている
- [ ] scene固有の差分（場所/時間/出来事）が 1〜3文で具体
- [ ] continuity が1行でも入っている（次sceneへの仕込み）

---

## 6) Sources（調査メモ）

※ 本ドキュメントは以下の prompt guide / 公式ドキュメントの考え方をベースに、repoの manifest 契約に合わせて整理した。

- Google Cloud Vertex AI: Prompt and image attribute guide（Imagen / 画像生成の prompt の書き方）
  - https://cloud.google.com/vertex-ai/generative-ai/docs/image/img-gen-prompt-guide
- Google Cloud Vertex AI: Generate and edit images with Gemini（Gemini 画像生成の利用方法/制約）
  - https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images
- Google Cloud Vertex AI: Subject reference / customization（参照画像を使った一貫性の考え方）
  - https://cloud.google.com/vertex-ai/generative-ai/docs/image/subject-customization
- Gemini API reference（ImageConfig: aspectRatio / imageSize など）
  - https://ai.google.dev/api/caching#imageconfig
