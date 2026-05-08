# PhotoshopVIP Liquid Glass Design Thinking

## 目的

ユーザー指定記事「Appleの新UI『Liquid Glass』とは？Webで再現できる最新UI完全ガイド」
（PhotoshopVIP, 2025-08-04）を調査し、ToC の `/image_gen` Web App に反映する設計指針をまとめる。

対象は `server/web/` の視覚デザイン、情報設計、操作感であり、この記事を実装仕様そのものとして扱うのではなく、
ToC の「透明なグラスの中に、ユーザーの指示で何層にも広がる美術館」という方向性へ翻訳して使う。

参照元:

- https://photoshopvip.net/166930

## 記事から抽出するデザイン思考

### 1. 透明感は装飾ではなく情報階層を作るために使う

記事では Liquid Glass を、半透明レイヤー、背景ぼかし、光の反射、丸み、シャドウによって
情報が空間に浮かぶように見せる UI 表現として整理している。

ToC ではこの考え方を「きれいなガラス風 UI」ではなく、作業者が現在どの判断面にいるかを把握するための
奥行き表現として使う。

- 背景層: run / request / candidate の一覧を支える暗い作業面
- 操作層: run selector、asset / scene tabs、candidate count、bulk action
- 判断層: prompt card、reference、candidate comparison、selected candidate
- 会話層: Codex App Chat pane

半透明表現は、上位層ほど強く、下位層ほど控えめにする。
すべてをガラス化すると記事内の注意点どおり視認性が落ちるため、作業の焦点だけに使う。

### 2. ぼかし、反射、歪みは「触れる前から状態が分かる」ための手がかりにする

記事は Liquid Glass の再現方法として `backdrop-filter`、SVG filter、CSS blur、WebGL、Figma effect などを紹介している。
ToC では高コストなシェーダ表現を標準 UI に入れるより、CSS で軽量に制御できる質感を優先する。

採用する手がかり:

- 生成可能: 薄いガラス面、弱い外光、primary accent の縁取り
- 生成中: 背景ぼかしを少し強め、progress を光の帯として流す
- 選択済み: 明るい rim light と 1px outline を重ねる
- 挿入待ち: footer / card action にやや強い光彩を与える
- エラー: ガラス面を濁らせず、赤系 outline と明確な text message で示す

避ける表現:

- 常時動く液体歪み
- 文字背面の強い画像透過
- ぼかしだけに依存した状態差
- カード全体を過度に光らせる演出

### 3. 可読性と操作性を Liquid Glass より上位に置く

記事は Liquid Glass の注意点として、文字の読みにくさ、古いブラウザでの対応、使いすぎを挙げている。
ToC の `/image_gen` は prompt 編集、候補比較、repo insertion が主作業なので、可読性を最優先する。

設計ルール:

- 本文テキストの背面は `rgba(14, 17, 19, 0.72)` 以上の暗い面を確保する
- prompt textarea はガラス化しすぎず、紙面に近い安定した dark surface にする
- candidate image 上に長い文字を重ねない
- chip / tab / icon button は色だけでなく outline、weight、位置で状態差を出す
- 主要操作ボタンは背景ぼかしよりも contrast ratio を優先する

## `/image_gen` への具体反映

### 色

既存の暗色管制卓トーンを維持し、Liquid Glass は黒いガラス、冷たい glass cyan の反射、暖かい museum amber の相談室光として扱う。
アプリ全体を Apple 風の白い frosted UI に寄せない。

推奨 token:

| 用途 | 値 | 使い方 |
|---|---:|---|
| app background | `#0e1113` | 既存の作業面。最も奥の層 |
| deep surface | `rgba(16, 20, 23, 0.94)` | prompt card / stable editor |
| glass surface | `rgba(23, 27, 31, 0.62)` | topbar、control rail、chat head |
| elevated glass | `rgba(255, 255, 255, 0.075)` | selected candidate 周辺の薄い反射 |
| hairline | `rgba(255, 255, 255, 0.14)` | 1px border |
| active rim | `#8ee8ff` | 選択、生成実行、insert 対象 |
| chat rim | `#f6d365` | Codex Chat 側の固有 accent |
| error rim | `#ff6b6b` | failure / invalid state |
| warning rim | `#ffd166` | missing reference / no output |

背景 grid は維持してよいが、ガラス層の背後でだけ見える程度に抑える。
候補画像が主役なので、背景が画像の色評価を邪魔しないよう彩度は低くする。

### タイポグラフィ

Liquid Glass の柔らかさに合わせて丸いフォントへ全面変更するのではなく、制作ツールとしての密度を保つ。

- font stack は既存の `"IBM Plex Sans", "Noto Sans JP", "Helvetica Neue", sans-serif` を継続
- h6 / section label は `font-weight: 800` 前後で、UI の区切りとして強くする
- prompt 本文は `14px - 15px`、line-height `1.55 - 1.65`
- metadata / path / execution lane は `12px - 13px`、色は `rgba(255,255,255,0.62)`
- button text は短くし、icon + tooltip を基本にする
- letter-spacing は増やさず、密度と読みやすさを優先する

Liquid Glass らしさは文字の装飾ではなく、文字を置く面の奥行きで表現する。

### レイアウト

記事の「情報が浮かぶ」感覚を、画面全体の z 軸設計として取り込む。

1. `shell`
   - 最奥の暗い制作面
   - grid texture は弱め
   - viewport 全体に固定

2. `topbar`
   - glass surface
   - `backdrop-filter: blur(18px) saturate(135%)`
   - run selector、reload、現在 run の context を置く

3. `controls`
   - topbar より少し低い glass surface
   - tabs、candidate count、bulk generation の設定をまとめる
   - compact で、画像比較領域を圧迫しない

4. `promptCard`
   - 通常時は deep surface
   - hover / focus-within で glass rim を出す
   - 生成結果がある card だけ elevated glass を足す

5. `candidate`
   - 画像面はガラス化しない
   - 周囲の frame だけ Liquid Glass 化する
   - selected state は `box-shadow` と `border-color` で即時に分かるようにする

6. `bulkFooter`
   - bottom glass dock として固定
   - 選択数、insert、download を集約
   - 操作前後の状態変化が最も明確に見える場所にする

7. `chatPane`
   - 右側の会話層
   - workspace とは別の青系 rim を持たせる
   - bubble は透明にしすぎず、会話ログの可読性を優先する

### 操作感

Liquid Glass の「触れたくなる UI」は、単なる hover animation ではなく、作業者の判断を速くする feedback として使う。

- hover
  - card の border を少し明るくし、内部画像は動かさない
  - clickable candidate だけ cursor と rim で反応する

- focus
  - prompt textarea、reference selector、chat input は明確な focus ring を出す
  - focus ring は `#f6d365` または `#8ee8ff`、影だけにしない

- press
  - primary action は 1px 下がる程度の小さな押下感
  - blur や scale の大きな変化は避ける

- generating
  - candidate slot を glass placeholder にし、progress を薄い光の sweep として表示する
  - skeleton は画像サイズを固定し、layout shift を起こさない

- selected
  - candidate frame を明るくし、bulk footer に選択数を即時反映する
  - card 内にも小さな selected chip を出し、スクロール中に状態を見失わないようにする

- inserted
  - repo insertion 後は成功色で短く反応し、candidate の visual state を残す
  - 成功後に候補比較の文脈を消さない

## CSS 実装ガイド

基本の glass class は小さく保ち、全コンポーネントへ無差別に付けない。

```css
.glassSurface {
  background: linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.095),
      rgba(255, 255, 255, 0.035)
    ),
    rgba(23, 27, 31, 0.62);
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    0 16px 42px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(18px) saturate(135%);
}

@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .glassSurface {
    background: rgba(23, 27, 31, 0.94);
  }
}
```

候補画像の frame は、画像自体に filter をかけず、外側だけを制御する。

```css
.candidateFrame {
  background: rgba(16, 20, 23, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.13);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.candidateFrame:hover {
  border-color: rgba(142, 232, 255, 0.42);
}

.candidateFrame.isSelected {
  border-color: #8ee8ff;
  box-shadow:
    0 0 0 1px rgba(142, 232, 255, 0.5),
    0 0 24px rgba(142, 232, 255, 0.14);
}
```

## アクセシビリティとパフォーマンス

Liquid Glass は見た目の効果が強い一方で、環境によって可読性や描画負荷がぶれやすい。
ToC では次を必須条件にする。

- `prefers-reduced-motion` では sweep / shimmer / blur transition を止める
- `backdrop-filter` 非対応環境では不透明 dark surface にフォールバックする
- blur は topbar、controls、footer、chat head など固定領域中心に限定する
- scroll container 内の大量 card には強い backdrop blur を使わない
- text contrast は glass 表現より優先する
- mobile では chat pane を隠す既存方針を維持し、glass 表現も軽くする

## 実装優先度

### Phase 1: 安定した Liquid Glass 骨格

- topbar、controls、bulkFooter、chatHead を glass surface 化
- promptCard は deep surface のまま、hover / selected だけ rim を追加
- candidate selected state を active rim + shadow で強化
- fallback CSS と reduced motion を同時に入れる

### Phase 2: 状態 feedback の洗練

- generating placeholder に軽い光の sweep
- inserted / failed / missing reference の状態別 rim
- bulk footer を bottom glass dock として情報密度を上げる

### Phase 3: 必要な場所だけ高度化

- reference preview の小さな frosted frame
- selected candidate の比較モード
- 高負荷にならない範囲で subtle distortion を検証

WebGL や SVG distortion は Phase 3 以降の検証対象に留める。
標準 UI の成功条件は、画像比較と prompt 編集が速く、暗い制作面の中で現在の判断対象が自然に浮いて見えること。

## 採用しないこと

- アプリ全体を白い Apple 風 UI にする
- 全カードを半透明にして背景を透かす
- prompt editor 背景に強い blur を入れる
- 候補画像そのものへガラス filter をかける
- 見た目のために情報密度を落とす
- 色だけで状態を伝える

## 成功条件

- 作業者が `run -> request -> prompt -> candidate -> insert` の流れを迷わず追える
- 選択中 candidate と未選択 candidate の差が一目で分かる
- prompt の長文編集が疲れにくい
- 右側 chat pane が workspace と混ざらず、会話層として独立して見える
- Liquid Glass は「高級感」ではなく「奥行きと状態の理解」に効いている
