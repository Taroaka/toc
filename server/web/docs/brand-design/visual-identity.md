# Visual Identity

## Positioning

`/image_gen` は ToC 制作フローの中で、asset / scene 画像の生成候補を比較し、採用画像を repo に挿入するための作業画面である。

ブランドの中心は「AI 画像生成の派手さ」ではなく、「映像制作判断の精度」に置く。UI は制作管制卓として、暗色、密度、可読性、画像の見比べやすさを優先する。

## Color System

現在の基本色:

- Base: `#0e1113`
- Surface: `#171b1f`
- Primary accent: `#8ee8ff`
- Secondary accent: `#f6d365`
- Divider: `rgba(255,255,255,0.12)`

運用ルール:

- Base / Surface は作業集中のための低輝度背景として使う。
- Primary accent は生成、選択、採用、現在地など「意思決定」にだけ使う。
- Secondary accent は chat pane、補助情報、非破壊の補助操作に使う。
- 画像候補そのものが主役なので、背景やカードは彩度を抑える。
- 紫のグラデーション、過剰な単色テーマ、装飾だけの光彩は使わない。

## Texture

背景の細い grid は、制作ツールとしての座標感を出すために使う。強い模様や大きい装飾は避け、画像候補と prompt text の読み取りを邪魔しない。

Glass / blur 表現を入れる場合は、topbar、footer、chat pane など固定 UI に限定する。prompt card や candidate image の上に強い blur をかけない。

## Typography

基本 font stack:

```css
"IBM Plex Sans", "Noto Sans JP", "Helvetica Neue", sans-serif
```

ルール:

- UI は日本語 prompt と英語パラメータが混在するため、本文は可読性を優先する。
- 見出しは太く短くし、hero 的な大見出しは使わない。
- button label は操作名を短くし、icon と組み合わせる。
- letter spacing は原則 `0`。

## Shape

- 基本 radius は `8px`。
- card は repeated item と modal に限定する。
- page section を card 化しない。
- candidate image は 16:9 を安定維持し、hover / select でレイアウトが動かないようにする。

## Brand Voice

UI 文言は説明的にしすぎない。利用者は ToC の制作作業者であり、画面は学習用 landing page ではない。

望ましいトーン:

- 短い
- 実務的
- 状態が分かる
- 生成/挿入など破壊的またはコストを伴う操作は明確

避けるトーン:

- マーケティング風コピー
- 機能説明の長文
- 装飾的な比喩
- 画像生成ログを chat と混ぜる表現
