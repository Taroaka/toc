# Image Prompting（Gemini Image / cross-model）: 正本

このドキュメントは **画像生成プロンプト品質**をシステムの根幹として扱い、
`video_manifest.md` の `scenes[].image_generation.prompt` を「全体 → 個別」の順で安定して組み立てるための正本。

対象:
- `/toc-immersive-ride` の `video_manifest.md`（特に Gemini Image）
- scene-series / 通常 run の `video_manifest.md`（静止画生成）

除外:
- アニメ/イラスト調の最適化
- Midjourney 専用構文（`--ar` など）に依存したテンプレ

---

## 結論（最短の型）

**prompt は 1本の自由文にせず、毎回同じ見出し順で書く。**

## 言語ポリシー（重要）

- `video_manifest.md` は **日本語で書く**（修正指示・レビューを日本語で完結させるため）。
- 見出しは **日本語**を推奨（例: `[全体 / 不変条件]`, `[登場人物]`, `[小道具 / 舞台装置]`, `[シーン]`, `[連続性]`, `[禁止]`）。
  - 生成スクリプト側は英語見出しも互換で認識するが、運用は日本語に寄せる。
- 禁止語彙（`禁止` / `assets.style_guide.forbidden`）も日本語で書く方向で統一する（例: `画面内テキスト`, `字幕`, `ウォーターマーク`, `ロゴ`）。

推奨ブロック（順序固定）:

1) `全体 / 不変条件`（全scene共通の不変条件）
2) `登場人物`（人物・参照一致）
3) `小道具 / 舞台装置`（重要アイテム/舞台装置の不変条件）
4) `シーン`（場面固有の描写）
5) `連続性`（前後接続）
6) `禁止`（禁止/地雷）

この repo の生成は、最終的に `scenes[].image_generation.prompt` のテキストをそのまま API に渡すため、
**「どこに何を書くか」自体をテンプレ化**すると品質が安定する。

---

## 1) 画像品質を上げる prompt の原則（portable / cross-model）

### 1.1 具体に落とす（曖昧語の連打を避ける）

悪い例:
- “beautiful, epic, amazing”

良い例:
- 被写体（誰/何） + 位置関係（前景/中景/背景） + 光（どこから/色） + カメラ（POV/画角/動き）

### 1.2 一貫性は「固定フレーズ + 参照画像」で作る

人物/小物/手元が重要なら:
- **参照画像**（character / hands / props）を用意し、毎sceneで `references` に入れる
- さらに **同じ語で**特徴を繰り返す（言い換え禁止）

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

## 3) /toc-immersive-ride（ride_action_boat）向け invariants（推奨セット）

注意: これは `/toc-immersive-ride --experience ride_action_boat` 用の固定条件。通常の run / scene-series では前提にしない（必要なら個別に指定する）。

`全体 / 不変条件` に毎回入れる（または将来的に assets から自動注入する）:

- `一人称POVのライド（アクションボート）`
- `画面下の前景に手があり、安全バーを握っている`
- `中央にレールが見える軌道が中央構図`
- `実写、シネマティック、実物セット感`
- `画面内テキストなし、字幕なし、ウォーターマークなし`

さらに “事故りやすい” ので早めに禁止しておく:
- `アニメ/漫画/イラスト調`
- `手の崩れ / 指の増殖`

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

B-roll（キャラを映さない）sceneは `character_ids: []` を明示し、キャラ注入ゼロにする。

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

### 4.1 Character turnaround 基準画像（scene_id: 0）

この repo では、キャラクター参照画像を「前/横/後ろ」の3枚で作り、さらに3枚を横並び結合した1枚（動画生成側の参照）も作る運用を推奨する。
`scripts/generate-assets-from-manifest.py` の `--character-reference-views front,side,back --character-reference-strip` で自動生成できる。

また、後から中間sceneを差し込めるように `scene_id` は **10刻み**（例: 10,20,30...）で運用するのがおすすめ（後段は scene_id の連番を前提にしない）。

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
First-person POV from ride action boat. Realistic hands gripping ornate brass safety bar in the lower foreground.
Theme park ride track with central rail visible, centered. Photorealistic, cinematic, practical effects.
No text, no subtitles, no watermark.

[CHARACTERS]
The story character(s) MUST match the reference image exactly (same face, hair, outfit).

[SCENE]
Setting: dusk, misty entrance gate into the world of <topic>. Practical set pieces, real lighting.
Key moment: the gate opens and a story character draws you into the world.
Composition: hands+bar foreground; track centered; story character mid-ground; glowing gate far background center.

[CONTINUITY]
Set up next: track curves left beyond the gate; warm light spills from the left side.

[AVOID]
anime/cartoon/illustration, CGI look, distorted hands, extra fingers, text, logos.
```

### 4.3 Scene 2（最初の見せ場へ）

```text
[GLOBAL / INVARIANTS]
First-person POV from ride action boat. Realistic hands gripping ornate brass safety bar in the lower foreground.
Track centered with central rail visible. Photorealistic, cinematic, practical effects. No text.

[CHARACTERS]
The story character(s) match the reference image exactly.

[SCENE]
Setting: the ride enters a new area themed around <topic>; practical fog and water spray; wet reflections on metal.
Key moment: the first big reveal appears ahead.
Composition: story character mid-ground center (if present); reveal object far background; droplets on lens kept subtle.

[CONTINUITY]
Must match previous: warm light source from left, same brass bar details.
Set up next: reveal object becomes dominant in frame, centered.

[AVOID]
anime/cartoon/illustration, unreadable shapes, extreme motion blur, text, watermark.
```

---

## 5) チェックリスト（生成前レビュー）

- [ ] POV が明示されている（first-person / foreground hands 等）
- [ ] “画面内のアンカー”が書かれている（前景/中景/背景の配置）
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
