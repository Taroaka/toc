 # Asset Bibles（object / setpiece）: 正本

このドキュメントは、キャラクター以外の「物語の主役級要素（アイテム / 舞台装置 / 現象）」を
**映画品質で設計し、生成に必ず参照させる**ための正本。

狙い:
- 書籍/絵本でディテールが浅いまま語られてきた舞台装置を、**予算無限の実写映画**として成立する密度に引き上げる
- 物語のメイン筋に直接関係しない“ショー/仕掛け/誘惑”も、映像の魅力として積極的に設計し、sceneごとの思いつきにしない
- 文字で説明せず、**映像だけで情報が伝わる**ようにする（看板/刻印/字幕に頼らない）

---

## 1) データ契約（asset stage → manifest）

画像生成は 2 段で扱う。

1. asset stage
   - `asset_plan.md` を作り、人が review してから reusable asset を生成する
2. cut stage
   - 既存どおり `video_manifest.md` に materialize された bible / reference を使って各 cut を生成する

asset stage では、`script.md` の該当 scene/cut を必ず見る。とくに human review で

- どの画像を参照するか
- 背景としてだけ使うか
- 先に別 asset を作ってから派生を作るか

のような指示が入った場合は、まず `asset_plan.md` で受ける。

### 1.0 `asset_plan.md`

- asset 設計と review の正本
- `workflow/asset-plan-template.yaml` を基準にする
- approved 後に実 asset を作り、cut stage が参照する
- 各 asset entry は `creation_status: planned|created|stale|missing` を持ち、すでに作成済みの asset は `existing_outputs[]` に実ファイルを記録する
- asset を作る本筋目的は、複数 cut で同じ visual identity を再利用し、同一 cut 内でも関連 asset を派生させながら物語の視覚表現をブレさせないこと
- つまり asset は「先に作ると便利な画像」ではなく、「後続 cut の continuity anchor」として扱う
- 同一人物の state/time variant は、main の `character_reference` を基準に派生させる
- variant entry では `generation_plan.reference_inputs[]` に main reference を入れ、`generation_plan.derived_from_asset_id` で元 asset を明示する
- 例: `urashima_old` は `urashima` の front / side / back を参照して作り、別人としてゼロから起こさない
- 同じ場所の昼夜差分、現在/未来差分、状態違いも同じで、main の `location_anchor` または `reusable_still` から派生させる
- 例: 昼の浜辺 anchor を先に作り、夜の浜辺 anchor は `derived_from_asset_id` で昼 anchor を参照して作る
- 例: 浜辺の現在と未来も、同じ場所として continuity を保ちたいなら main beach anchor を基準に派生させる
- `source_script_selectors[]` は使用箇所の記録であり、`reference_inputs[]` とは別物
- `reference_inputs[]` は同一人物 variant / 同一場所 variant / same-camera 派生のときだけ使う
- `reference_inputs[]` が空の asset では、bootstrap 用に `execution_lane=bootstrap_builtin` を選んでよい
- 既存 reference を持つ派生 asset では使わない
- `bootstrap_builtin` という lane 名は asset 専用語ではなく、repo 全体では no-reference built-in image lane の互換名として扱う
- asset 段階で参照を持つのは、複数 cut で再利用される同一 entity の identity / state / structure / relation continuity を固定したい場合に限る
- shot 内の移動、演技、立ち位置、カメラ差分のような表現差分は cut stage で扱い、asset 段階の参照理由にしない
- 独立した location anchor は原則 `reference_inputs: []`
- ただし、同じ建物の中でも物語上は別エリアなら、無理に派生させない
- 例: 竜宮城の宴会エリアと foyer は別 `location_anchor` にしてよい
- このとき「奥に宴会エリアが見える」のような関係は、派生ではなく `reference_usage.mode=background_glimpse` などで表す

移行中 run の扱い:

- 浦島 run のように設計試行錯誤の途中で、先に scene still ができてから asset に昇格される例外はありうる
- これは移行中の互換運用であり、本来フローでは asset stage が先、cut stage が後
- 将来の run では、scene still がそのまま asset 正本になる前提では進めない
- 例外として、`reference_inputs[]` が無い初期 asset seed は Codex built-in image generation を bootstrap lane として使ってよい
- その場合も human review で `review.status=approved` になるまでは canonical asset にしない
- approved 後は bootstrap 生成物をそのまま canonical reference として後続 stage で使ってよい

正本は `/toc-immersive-ride` の `video_manifest.md`（`assets` 内）:

### 1.1 `assets.object_bible[]`

- `object_id: string`（例: `ryugu_palace`, `tamatebako`）
- `kind: "setpiece"|"artifact"|"phenomenon"`（最小3種）
- `reference_images: [string, ...]`（必須・非空）
- `fixed_prompts: [string, ...]`（必須・非空）
- `cinematic:`（任意だが強く推奨）
  - `role: string`（映画での役割。例: 境界/誘惑/贈与/代償/啓示 など）
  - `visual_takeaways: [string, ...]`（映像から観客に与える情報）
  - `spectacle_details: [string, ...]`（非メイン筋でも“ワクワク”を作る見せ場/仕掛け）
- `notes: string|null`（根拠、創作ラベル、注意点など）

### 1.2 `scenes[].image_generation.object_ids`

sceneに映す object/setpiece を **IDで宣言**する。

- 例: `object_ids: ["ryugu_palace", "tamatebako"]`
- B-roll でも必ず `object_ids: []` を明示（検証を通すため）

---

## 2) 参照画像運用（reference scene）

`reference_images` に入れたパスは、どこかの scene が必ず生成する:

- `assets/objects/...png` を `scenes[].image_generation.output` にする
- 参照画像は「無人の setpiece」「クローズアップの artifact」中心（混ざり防止）
- ここでいう reference scene は、**毎scene/cutに作るものではない**。同じ場所/物体/人物状態をまたぐ continuity anchor として、必要な回数だけ作る。
- アンカーがすでに存在する scene/cut は、既存の reference image や直前の anchor frame を再利用してよい。

生成側は `--apply-asset-guides` で、該当 object の `fixed_prompts` と cinematic 情報を
sceneの `[PROPS / SETPIECES]` に自動注入できる。

review で最低限確認する項目:

- `character_reference`: 顔、髪型、衣装、年齢感
- `object_reference`: silhouette、材質、装飾、縮尺感
- `location_anchor`: spatial identity、主要構造、光環境
- `reusable_still`: 後続 cut の continuity anchor として十分か

---

## 3) 書くべきディテール（設計観点）

各 object について、少なくとも以下を一度設計して固定する:

- **映画での役割**: 物語/感情/テーマに対して何を担うか（扉・誘惑・贈与・代償・帰還の証など）
- **映像から与える情報**: 観客は“何を理解する”べきか（言葉ではなく形/光/動きで）
- **材質/構造**: 実写で成立する素材感、重量感、経年、工芸の痕跡
- **機構/ルール**: “開けたくなる”“近づきたくなる”を生む仕掛け（ただ豪華、で終わらせない）
- **ショー/見せ場**: メイン筋と無関係でも映像として魅力的な現象（音/光/流体/群体/変形）
- **禁止**: 文字、看板、銘板、説明的UI、露骨なメタ表現（字幕で語らない）

---

## 4) 具体例（浦島太郎）

### 4.1 竜宮城（`ryugu_palace` / setpiece）

設計の要点:
- 役割: “境界の越境”と“饗宴の誘惑”。現実とは別の時間/倫理が働く場所
- 映像情報: この城は生きている／海そのものが建築になっている／招かれた者だけが気づく仕掛け
- ショー性: 水族館以上の“見せ物”が常にどこかで起きている（発光、泡、群泳、潮流で舞う光）

例（manifest断片）:

```yaml
assets:
  object_bible:
    - object_id: "ryugu_palace"
      kind: "setpiece"
      reference_images: ["assets/objects/ryugu_palace_exterior.png", "assets/objects/ryugu_palace_hall.png"]
      fixed_prompts:
        - "Ryugu Palace is built from living coral, mother-of-pearl, and lacquered bronze ribs; wet sheen; realistic scale"
        - "Interior features suspended bubble-lanterns and bioluminescent coral chandeliers; no text signage"
        - "Showmanship: distant aquarium-like grand atrium with swirling fish schools and controlled currents"
      cinematic:
        role: "Threshold + temptation; a paradise that feels too perfect to leave"
        visual_takeaways:
          - "This place is alive; architecture and ocean are one organism"
          - "Time feels different here (slow drift, impossible calm)"
        spectacle_details:
          - "Hidden coral doors open with water pressure; reveal a moving underwater light show"
          - "Ceiling ripples like a calm sea surface, casting animated caustics"
```

### 4.2 玉手箱（`tamatebako` / artifact）

設計の要点:
- 役割: “贈与”であり“代償”。禁忌の魅力（開けたくなる設計）が必要
- 映像情報: 箱そのものがルールを持つ／触れると反応する／開封が不可逆であると直感できる
- ショー性: 開封前から誘惑演出（微細な振動、呼吸する光、封印の結晶が脈動）

例（manifest断片）:

```yaml
assets:
  object_bible:
    - object_id: "tamatebako"
      kind: "artifact"
      reference_images: ["assets/objects/tamatebako_closeup.png"]
      fixed_prompts:
        - "Tamatebako is an ornate lacquered box with gold inlay and shell mosaics; hyper-detailed craftsmanship"
        - "Temptation mechanism: seals shimmer and subtly respond to proximity; no engraved letters"
        - "Opening consequence is hinted visually (hairline cracks of light, drifting ash motes trapped under the lid)"
      cinematic:
        role: "Gift + taboo; the irresistible wrong choice"
        visual_takeaways:
          - "You can feel the rule: do not open, yet it begs to be opened"
        spectacle_details:
          - "The lid boundary emits slow, breathing light like a living seal"
```

---

## 5) 実装との接続

- 自動注入: `scripts/generate-assets-from-manifest.py --apply-asset-guides`
- 検証ゲート:
  - `--require-object-ids`（object_bibleがある場合、各sceneで `object_ids: []` を必須）
  - `--require-object-reference-scenes`（reference_images が必ずどこかの scene output として生成されること）
- 人間レビュー:
  - setpiece / artifact に対する修正要求は、口頭メモで流さず `human_review.change_requests[]` に残す
  - reveal 順序、spectacle 不足、continuity drift のように論点が複数ある場合は request を分ける
  - `human_review_ok` は evaluator finding の例外許容であり、asset bible 改稿要求の正本には使わない

### 5.1 location_bible

場所そのものを再利用する修正要求は `object_bible` へ押し込まず、`assets.location_bible[]` を使う。

- `location_id`
- `reference_images`
- `reference_variants[]`
- `fixed_prompts`
- `review_aliases[]`
- `continuity_notes[]`
- `notes`

人レビューで「同じ神殿を別 cut でも参照する」「宴会エリアを奥に見せる」ような要求が来た場合は、まず `location_bible` に格上げしてから cut 側で `location_ids[]` / `reference_usage[]` へつなぐ。
