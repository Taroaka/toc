 # Asset Bibles（object / setpiece）: 正本

このドキュメントは、キャラクター以外の「物語の主役級要素（アイテム / 舞台装置 / 現象）」を
**映画品質で設計し、生成に必ず参照させる**ための正本。

狙い:
- 書籍/絵本でディテールが浅いまま語られてきた舞台装置を、**予算無限の実写映画**として成立する密度に引き上げる
- 物語のメイン筋に直接関係しない“ショー/仕掛け/誘惑”も、映像の魅力として積極的に設計し、sceneごとの思いつきにしない
- 文字で説明せず、**映像だけで情報が伝わる**ようにする（看板/刻印/字幕に頼らない）

---

## 1) データ契約（manifest-first）

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
