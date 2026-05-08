# Glass Design Summit

## Purpose

この文書は、6本の調査結果を統合し、ToC `/image_gen` における「ガラスデザインの最高峰」を定義する。

最高峰とは、派手な屈折や白い frosted UI ではない。候補画像、prompt、reference、repo insertion を高速に判断する制作 UI の中で、透明なグラスにユーザーの指示で何層にも広がる美術館を成立させる material system である。

参照調査:

- `research-glass-01-apple-platform.md`
- `research-glass-02-web-implementation.md`
- `research-glass-03-museum-architecture.md`
- `research-glass-04-luxury-product-ui.md`
- `research-glass-05-motion-interaction.md`
- `research-glass-06-accessibility-performance.md`

## Definition

ToC の最高峰 glass design は、次を同時に満たす。

1. glass は decoration ではなく、operation layer と content layer の境界を作る。
2. prompt と candidate image は主役なので、透明化・反射・屈折を直接かけない。
3. topbar、controls、bulk footer、chat pane、selected candidate frame は、それぞれ異なる光り方を持つ。
4. 黒の階調、細い rim、edge highlight、shadow で高級感を作り、大面積の発光に頼らない。
5. motion は状態説明だけに使い、画像比較や prompt 読解を妨げない。
6. reduced transparency / reduced motion / forced colors / contrast に耐える。
7. Web 実装では CSS glass を core とし、SVG/WebGL refraction は通常 UI へ入れない。

## Layer Model

| Layer | Role | Material |
| --- | --- | --- |
| Background | 美術館の暗い展示空間 | near-black + subtle grid / edge depth |
| Workspace | prompt と候補比較の作業面 | solid / near-solid dark surface |
| Prompt Card | 制作指示と展示キャプション | solid dark, focus/generating only rim |
| Candidate Frame | 画像候補の額装 | idle は弱い hairline、selected/error のみ強い rim |
| Controls | 展示 wing と生成条件の操作卓 | low-glow rail glass |
| Topbar | run の入口と現在地 | horizontal navigation glass |
| Bulk Footer | 採用・搬出・収蔵カウンター | dense bottom dock glass |
| Chat Pane | キュレーター相談室 | warm amber side-rim glass |

## Component Light Grammar

各 component の輝き方を同じにしない。

### Topbar

- 役割: 入口 / 案内板。
- 光: 下端の水平 hairline、薄い top highlight。
- 禁止: radial shine、強い glow、縦方向の濃い反射。
- 透明度: medium。selector の読みやすさを最優先。

### Controls

- 役割: 操作卓 / 展示 wing 切替。
- 光: 細かい rail、目盛り、低い shine。
- active tab: filled capsule + rim。
- 禁止: 全体を大きく発光させる。

### Prompt Card

- 役割: wall text / 制作仕様。
- 光: 通常はほぼなし。focus で amber ring、generating で短い cyan sweep。
- 禁止: textarea の blur、本文背面の透明化、行ごとの animation。

### Candidate

- 役割: 作品の額縁。
- 光: idle は弱い hairline。selected は cyan rim + small glow。error は red rim + fixed error slot。
- 禁止: 画像本体の opacity / blur / reflection / scale。

### Bulk Footer

- 役割: 収蔵カウンター。
- 光: 下側からの重い shadow、上端の接地 highlight。
- 必須: selected count を常時見せる。
- repo insertion: download より強い adoption action として扱う。

### Chat Pane

- 役割: キュレーター相談室。
- 光: 左端の warm amber rim、chat head の下端 rim。
- 禁止: 生成ログ化、message bubble の過透明化。

## Token Direction

推奨色:

- `glass cyan`: `#8ee8ff` for selected / generation / primary precision.
- `museum amber`: `#f6d365` for curator / focus warmth.
- `deep black`: `#050608` to `#171c23` for surface hierarchy.
- `white hairline`: alpha `0.10-0.24` for glass edge.

避ける:

- 大面積の gold。
- 白い Apple 風 frosted UI への全面寄せ。
- 紫グラデーション。
- pure white glow。
- glass on glass の多重化。

## Motion Rules

- idle animation は置かない。
- hover は 90-140ms、border / alpha / shadow の微差だけ。
- candidate image は動かさない。
- selected は残存状態なので pulse しない。
- generating は対象 card 内の progress / short sweep に閉じる。
- reduced motion では sweep / shimmer / morph / pulse を止める。

## Web Implementation Rules

採用:

- `backdrop-filter: blur() saturate()` for fixed / low-count glass layers.
- `@supports` fallback.
- `prefers-reduced-transparency` fallback.
- role-specific CSS variables such as `--lg-shine`, `--lg-inner-border`, `--lg-tone`.

限定採用:

- SVG displacement: selected rim や lab 表現だけ。
- WebGL refraction: 通常画面では不採用。将来の brand demo / empty state の 1 箇所まで。

不採用:

- scroll grid 全体への blur。
- prompt textarea への glass。
- candidate image への filter。
- 長時間の continuous shimmer。

## Acceptance Checklist

- topbar / controls / candidate / footer / chat pane の光り方がそれぞれ違うか。
- candidate image と prompt text の可読性・比較性を損なっていないか。
- selected candidate は idle と明確に違うか。
- footer で selected count と repo insertion の重みが分かるか。
- chat pane は warm rim で別室として読めるか。
- reduced transparency で solid UI として成立するか。
- reduced motion で状態理解が失われないか。
- mobile で blur layer が増えすぎていないか。
- color だけで状態を伝えていないか。
- design docs と実装 token が同じ言語を使っているか。
