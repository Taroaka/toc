# Apple Design Research 2026

## Purpose

この文書は Apple の 2025-2026 年時点の Liquid Glass / visionOS / Human Interface Guidelines 系デザインを、ToC `/image_gen` の実務 UI へ反映するための追加調査メモである。

既存の `research-glass-01-apple-platform.md` を置き換えるものではなく、実装時にすぐ使える判断基準へ絞って再整理する。

## Sources

- Apple Developer: Meet Liquid Glass, WWDC25  
  https://developer.apple.com/videos/play/wwdc2025/219/
- Apple Developer Documentation: Liquid Glass  
  https://developer.apple.com/documentation/TechnologyOverviews/liquid-glass
- Apple Human Interface Guidelines  
  https://developer.apple.com/design/human-interface-guidelines
- Apple Human Interface Guidelines: Materials  
  https://developer.apple.com/design/human-interface-guidelines/materials
- Apple Human Interface Guidelines: Designing for visionOS  
  https://developer.apple.com/design/human-interface-guidelines/designing-for-visionos

## Key Findings

### 1. Liquid Glass Is A Functional Layer

Apple は Liquid Glass を、content そのものではなく controls / navigation が浮く機能レイヤーとして扱っている。WWDC25 では、Liquid Glass が Apple platform 全体を統合し、操作層を content の上に浮かせる design language として説明されている。

ToC 適用:

- prompt textarea、candidate image、reference thumbnail は content layer として solid に保つ。
- topbar、tabs、asset filter、count control、bulk footer、chat pane header を glass の主対象にする。
- glass は背景を見せるためではなく、どの操作面が content より手前にあるかを示すために使う。

### 2. Resting State Should Be Quiet

WWDC25 の Liquid Glass は、触れた時に光や柔軟性が増す一方、休止状態は content の邪魔をしない。これは制作 UI では特に重要で、常時光る component は candidate 比較の邪魔になる。

ToC 適用:

- idle の candidate rim は hairline に留める。
- selected、focus、generating、error のような状態だけ rim / glow / sweep を強める。
- hover は小さい border / alpha / shadow 変化に止め、candidate image を動かさない。

### 3. Glass Adapts To Size And Context

Apple は Liquid Glass を、背後の content、component size、platform context に応じて tint、shadow、lensing、dark/light を変える adaptive material として扱う。大きくなるほど厚みや影が増え、内部 content の可読性が優先される。

ToC 適用:

- chip / icon button は薄い clear glass を許容する。
- bulk footer、chat pane、controls など大きな surface は不透明寄りにする。
- prompt card は glass ではなく near-solid surface にし、focus ring だけ material grammar に参加させる。

### 4. Hierarchy Comes From Depth, Not Decoration

visionOS 系の設計では、奥行きは装飾ではなく hierarchy と focus の道具である。ToC でも「美術館の中に UI が浮く」表現は、単なる blur や glow ではなく、z-axis の一貫性として管理する。

ToC z-axis:

1. `museumBackground`: 暗い展示空間
2. `workspace`: prompt / candidate を置く作業面
3. `promptCard`: 制作仕様の wall text
4. `candidateFrame`: 画像の額装
5. `controlRail`: tabs / count / filter
6. `bulkFooter`: 採用 dock
7. `chatPane`: キュレーター相談室

### 5. Legibility Beats Transparency

Apple HIG の材料・色・アクセシビリティ方針は、透明感よりも contrast、可読性、motion / transparency 設定への適応を優先する。Liquid Glass を Web で模倣する場合も、Reduce Transparency / Reduce Motion / Forced Colors の fallback が必須になる。

ToC 適用:

- `prefers-reduced-transparency` では blur を切り、solid background に寄せる。
- `prefers-reduced-motion` では sweep / pulse / morph を止める。
- status は色だけでなく label、border、icon、progress を組み合わせる。
- path、error、button label は glass 上でも contrast を落としすぎない。

## Design Rules For `/image_gen`

1. Liquid Glass は control layer へ限定する。
2. content layer の prompt / image は安定した dark surface に置く。
3. glass の厚みは surface size と action importance に比例させる。
4. idle は静かに、状態変化だけが光る。
5. topbar、controls、candidate、footer、chat pane はそれぞれ別の light grammar を持つ。
6. accessibility fallback は glass token と同じ責務で管理する。
7. Apple 的な美しさを再現するのではなく、Apple 的な「役割分離」と「状態反応」を ToC の制作 UI に翻訳する。
