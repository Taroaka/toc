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

### 0.1 p500 slot 運用詳細

`p500` の目的は、p600 の cut 画像生成に入る前に、この物語で繰り返し使う視覚要素を漏れなく固定すること。`p500|500|asset` を target にした場合は、`p570` の asset continuity check まで進める。

#### p510 asset grounding

- やること: asset stage で読むべき正本、run local input、stage docs、template を確定する。
- 主な input: `script.md`、`story.md`、`video_manifest.md`、`docs/implementation/asset-bibles.md`、`docs/data-contracts.md`、`workflow/asset-plan-template.yaml`。
- 主な output: `logs/grounding/asset.json`、`logs/grounding/asset.readset.json`、`logs/grounding/asset.audit.json`。
- ゴール: readset が verified、audit が passed で、以後の p520-p570 が親会話だけの暗黙知に依存しない状態にする。

#### p520 reusable asset inventory

- やること: この物語の登場人物、物語固有のアイテム、使われる場所、舞台装置、繰り返し参照される still を網羅する。
- 対象: 主人公の状態差分、相手役、敵役/権力者、案内役/助力者、物語固有の小道具、setpiece、繰り返し使う場所、reusable still。
- ゴール: 後続 cut で visual identity が揺れる主要 subject が `asset_plan.md` 候補に入っていること。
- 判断基準: `script.md` / `story.md` / `video_manifest.md` に出る固有名詞・固有の場所・物語上の証拠品・再利用される背景を拾う。単発 cut の一時的な構図や演技は p600 に残す。

#### p530 asset plan authoring

- やること: p520 の inventory を `asset_plan.md` に構造化し、生成前 review に出せる状態にする。
- ゴール: 各 asset について、何を固定するか、どこで使うか、参照画像が必要か、どの output に保存するかが明確であること。
- character asset: 原則として全身が見える参照を作り、front / side / back の 3 面図を required views に含める。派生 character variant は main の front / side / back を参照して同一人物性を保つ。
- object / location / setpiece / reusable still: 単体 still を基本にし、同じ場所や同じ物体の状態差分だけ `derived_from_asset_id` と `reference_inputs[]` を使う。

#### p540 asset review / fix loop

- やること: review agent が `asset_plan.md` を監査し、漏れや矛盾があれば main agent が修正し、再度 review agent が確認する cycle を回す。
- 標準 loop: 最大 5 round。各 round は複数 critic と aggregator を使い、aggregator が `passed|changes_requested` と unresolved findings を返す。
- review 観点:
  - この物語の登場人物・物語固有アイテム・使用場所が漏れていないか
  - 後続 cut で identity drift が起きやすい subject が asset 化されているか
  - character の full-body front / side / back 参照方針が入っているか
  - variant が main reference から派生しており、別人/別物として新規設計されていないか
  - `source_script_selectors[]` と `generation_plan.reference_inputs[]` を混同していないか
  - `reference_inputs[]` が空なら no-reference lane、参照あり/derived なら standard lane になっているか
  - `story.md` / `script.md` に無い新情報を足していないか
  - p550 request に変換できるだけの visual specificity があるか
- ゴール: 漏れ・矛盾・lane 誤り・参照関係の誤用が解消され、未解決 finding がある場合は human review / explicit override の理由が残っていること。

#### p550 asset requests

- やること: `asset_plan.md` から `asset_generation_requests.md` と `asset_generation_manifest.md` を materialize する。
- ゴール: 人間が request file だけを見て、何を、どの参照画像で、どの output に、どの status で生成するか判断できること。
- prompt 本文は image API に渡る凍結文なので、制作管理メタではなく具体的に見える対象を書く。
- NG:
  - `物語「シンデレラ」の scene10 のための背景画像。`
  - `scene30_cut01 で使う魔法の変身 scene。`
  - `この画像は物語「シンデレラ」の一場面を視覚化する。`
  - `後続 scene でも使いやすい王子。`
- OK:
  - `灰の台所。石床、大きな暖炉、薄い灰、朝の青灰色の光、奥へ続く暗い廊下が見える、人物なしの実写映画風 location anchor。`
  - `月光の庭に停まる、かぼちゃの丸みを残した実写の馬車。蔓の装飾、金属骨組み、重い車輪、扉の形が明確に見える。`
  - `若い王子の全身キャラクター参照。深紺と銀の宮廷衣装、落ち着いた目線、同じ人物として再利用できる顔・髪型・立ち姿。`

#### p560 asset generation

- やること: p550 request に従い、reusable asset image を output path に保存する。
- no-reference: `reference_count == 0` の request は、API provider 経由でも Codex GPT Image 1.5 経由でも、互換 lane 名 `execution_lane=bootstrap_builtin` の no-reference image lane に残す。
- reference-driven: `reference_count > 0`、`reference_inputs[]` あり、または `derived_from_asset_id` ありの request は `execution_lane=standard` に残す。
- ゴール: request と manifest の status、出力ファイル、失敗/skip/再生成対象が対応していること。

#### p570 asset continuity check

- やること: 生成済み asset が p600 の continuity anchor として使えるか確認する。
- review 観点: character の顔・髪・年齢感・衣装・3 面図、object の silhouette / material / scale、location の spatial identity / major structure / lighting、variant の同一性、`existing_outputs[]`、`review.status`、manifest status。
- ゴール: p600 の scene / cut prompt が参照できる approved asset path が揃い、未承認・不足・差し替え対象が明示されていること。

### 1.0 `asset_plan.md`

- asset 設計と review の正本
- `workflow/asset-plan-template.yaml` を基準にする
- approved 後に実 asset を作り、cut stage が参照する
- 各 asset entry は `creation_status: planned|created|stale|missing` を持ち、すでに作成済みの asset は `existing_outputs[]` に実ファイルを記録する
- asset を作る本筋目的は、複数 cut で同じ visual identity を再利用し、同一 cut 内でも関連 asset を派生させながら物語の視覚表現をブレさせないこと
- つまり asset は「先に作ると便利な画像」ではなく、「後続 cut の continuity anchor」として扱う
- character reference は全身が見える front / side / back の 3 面図を基本にする。顔だけ、上半身だけ、正面だけの参照は p600 の continuity anchor として不足しやすい
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

<!-- image-gen-setting:item:start -->
アイテムや舞台装置は `assets.object_bible` を正本にする。
silhouette、材質、装飾、縮尺感、工芸の痕跡、物語上の役割を映像だけで伝える。
看板、刻印、銘板、字幕、説明的 UI に頼らず、形、光、構造、ショー性で理解させる。
<!-- image-gen-setting:item:end -->

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
- ここでいう reference scene は、**毎scene/cutに作るものではない**。同一 run 内で同じ場所/物体/人物状態をまたぐ continuity anchor として、必要な回数だけ作る。
- アンカーがすでに存在する scene/cut は、同一 run 内の既存 reference image や直前の anchor frame を再利用してよい。

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

<!-- image-gen-setting:location:start -->
場所は `assets.location_bible` を正本にする。
spatial identity、主要構造、光環境、場所固有の空気を固定し、同じ場所の状態差分か、別エリアとして扱うべきかを明確にする。
別エリアから他エリアを見せる場合は、派生ではなく `reference_usage.mode=background_glimpse` などの見え関係として扱う。
<!-- image-gen-setting:location:end -->

場所そのものを再利用する修正要求は `object_bible` へ押し込まず、`assets.location_bible[]` を使う。

- `location_id`
- `reference_images`
- `reference_variants[]`
- `fixed_prompts`
- `review_aliases[]`
- `continuity_notes[]`
- `notes`

人レビューで「同じ神殿を別 cut でも参照する」「宴会エリアを奥に見せる」ような要求が来た場合は、まず `location_bible` に格上げしてから cut 側で `location_ids[]` / `reference_usage[]` へつなぐ。
