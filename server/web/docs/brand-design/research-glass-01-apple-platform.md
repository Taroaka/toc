# Apple Platform Glass Research for `/image_gen`

## Purpose

この文書は、Apple Liquid Glass / visionOS / Human Interface Guidelines の一次情報から、ToC `/image_gen` の「透明なグラスにユーザーの指示で何層にも広がる美術館」UIへ適用できる最上位設計原則を抽出する。

Apple の見た目をそのまま再現するためではなく、透明素材、奥行き、レイヤー、コントロール、ナビゲーション、可読性、状態表現を、ToC の制作 UI に使える判断基準へ翻訳する。

## Primary Sources

Apple 公式情報を中心に参照した。

- Apple Developer Documentation: Liquid Glass  
  https://developer.apple.com/documentation/TechnologyOverviews/liquid-glass
- Apple Developer Documentation: Adopting Liquid Glass  
  https://developer.apple.com/documentation/TechnologyOverviews/adopting-liquid-glass
- Apple Developer Documentation: Applying Liquid Glass to custom views  
  https://developer.apple.com/documentation/SwiftUI/Applying-Liquid-Glass-to-custom-views
- Apple Developer Documentation: SwiftUI `Glass`  
  https://developer.apple.com/documentation/swiftui/glass
- Apple Human Interface Guidelines: Materials  
  https://developer.apple.com/design/human-interface-guidelines/materials
- Apple Human Interface Guidelines: Layout  
  https://developer.apple.com/design/human-interface-guidelines/layout
- Apple Human Interface Guidelines: Color  
  https://developer.apple.com/design/human-interface-guidelines/color
- Apple Human Interface Guidelines: Typography  
  https://developer.apple.com/design/human-interface-guidelines/typography
- Apple Human Interface Guidelines: Accessibility  
  https://developer.apple.com/design/human-interface-guidelines/accessibility
- Apple Human Interface Guidelines: Designing for visionOS  
  https://developer.apple.com/design/human-interface-guidelines/designing-for-visionos
- Apple Human Interface Guidelines: Spatial layout  
  https://developer.apple.com/design/human-interface-guidelines/spatial-layout
- Apple Human Interface Guidelines: Ornaments  
  https://developer.apple.com/design/human-interface-guidelines/ornaments
- Apple Human Interface Guidelines: Windows  
  https://developer.apple.com/design/human-interface-guidelines/windows
- WWDC25: Meet Liquid Glass  
  https://developer.apple.com/videos/play/wwdc2025/219/
- WWDC25: Build a SwiftUI app with the new design  
  https://developer.apple.com/videos/play/wwdc2025/323/
- WWDC23: Principles of spatial design  
  https://developer.apple.com/videos/play/wwdc2023/10072/
- WWDC23: Design for spatial input  
  https://developer.apple.com/videos/play/wwdc2023/10073/
- WWDC23: Design considerations for vision and motion  
  https://developer.apple.com/videos/play/wwdc2023/10078/

## Governing Thought

Liquid Glass の本質は「半透明な装飾」ではなく、content layer の上に浮く controls / navigation layer を、光、屈折、奥行き、反応、可読性で統合する platform-native material system である。

ToC `/image_gen` では、candidate image と prompt を主役に保ち、glass は「どの層をいま操作しているか」を明確にするための z-axis grammar として使う。

## Apple-Level Principles

### 1. Glass Is Functional, Not Decorative

Apple HIG は Liquid Glass を controls / navigation のための独立した機能レイヤーとして扱い、content layer には標準素材を使う方針を示している。つまり glass は「背景をきれいにぼかす表現」ではなく、操作領域と作品領域を分離するための素材である。

ToC 適用:

- candidate image、reference image、prompt textarea は glass 化しない。
- topbar、tabs、bulk footer、floating action、chat pane header だけを主要 glass 対象にする。
- prompt card 本体は暗い solid / near-solid surface にし、hover、focus、generating、selected などの状態で rim と光だけを増やす。
- glass の使用量は画面上の「操作層」に限定し、展示物の評価を邪魔しない。

### 2. Transparent Material Must Preserve Content Focus

Apple は Liquid Glass を、背後の content を隠さず、かつ controls の可読性を保つ素材として説明している。背後の色や光を拾うが、操作対象が読めなくなるほど透明にしない。大きな要素ほど不透明寄りに振るのが自然で、複雑な背景上では contrast と separation を優先する。

ToC 適用:

- small chip / icon button は clear glass を使えるが、長文や重要 action はより濃い glass にする。
- bulk footer は最重要操作層なので、topbar より不透明にする。
- selected candidate の画像上に強い透明 overlay を置かない。画像の色判断を守る。
- 背景 grid や museum texture は glass の背後でだけ感じる程度に抑える。

### 3. Depth Communicates Hierarchy

visionOS の空間設計では、奥行きは見た目の派手さではなく hierarchy と focus を伝える道具である。重要なものは field of view の中心に置き、奥行き差は light、shadow、occlusion、scale と整合させる。奥行きの乱用や矛盾した depth cue は疲労や違和感につながる。

ToC 適用:

- z 軸は `background -> workspace -> content card -> candidate frame -> controls -> footer/chat` の順に固定する。
- modal / confirmation は、背面を少し後退させるように dimming と shadow で表す。
- text は浮かせない。浮いてよいのは control container、image frame、active toolbar。
- shadow は「接地」と「層の違い」を示すために使い、全カードに同じ強さでかけない。

### 4. Glass Responds to Interaction

WWDC25 と SwiftUI の glass APIs は、Liquid Glass が touch / pointer / focus にリアルタイム反応し、複数の glass shape が container 内で結合・変形しうる素材であることを示している。標準コントロールでは slider knob、toggle、button、menu、popover が操作時に material と movement を変える。

ToC 適用:

- idle glass は控えめ、hover / focus / active で rim、highlight、shadow、background alpha を増やす。
- tabs や segmented controls は active indicator だけでなく、選択面そのものが少し前に出る。
- slider thumb、candidate count stepper、generate button は操作中だけ glass の反射を強める。
- 複数ボタンが近接する toolbar は、個別にバラバラな glass を置くより、ひとつの glass rail の中で状態差を作る。

### 5. Navigation Floats Above Content

visionOS の ornaments は、window の content を覆わず、window と一緒に動く付属 control plane として定義される。Apple の空間設計では、tab bar や toolbar を content の外側または少し手前に浮かせることで、主画面を狭めず操作を常時使える状態にする。

ToC 適用:

- topbar は run selection の案内板として、workspace の最上部に薄く浮かせる。
- asset / scene tabs と sub-filter は content grid とは別の control rail にする。
- bulk footer は scroll content に巻き込まず、採用・download・repo insertion の docking layer として固定する。
- chat pane は画像生成ログではなく、curator / Codex との別室として扱い、workspace glass と色温度を少し変える。

### 6. Legibility Beats Transparency

Apple HIG の material / color / typography / accessibility guidance は、透明感よりも可読性、contrast、Dynamic Type、accessibility settings への適応を優先する。Reduce Transparency や Reduce Motion が有効な環境では、標準 components は自動適応する。custom UI も同等の fallback を持つべきである。

ToC 適用:

- prompt textarea、error message、file path、button label は solid surface に近づける。
- text 背面の alpha は薄くしすぎない。長文領域は glass ではなく dark paper。
- color だけで状態を示さず、label、icon、border、progress、disabled affordance を併用する。
- `prefers-reduced-transparency` では blur を切り、背景 alpha を上げる。
- `prefers-reduced-motion` では morph / spring / parallax を短く、または opacity transition に置き換える。

### 7. Spatial Comfort Requires Restraint

visionOS の spatial guidance は、重要 content を field of view 中央へ置く、head-locked な大面積 UI を避ける、過剰な窓や奥行き差を避ける、直接操作を多用しすぎない、十分な interactive spacing を確保する、といった comfort 原則を示している。

ToC 適用:

- 2-column grid は視線移動が読みやすい幅に保ち、右 chat pane が圧迫する場合は workspace を優先する。
- candidate card 内の primary action は同じ場所に置き、ユーザーが毎回探さないようにする。
- hover glow や parallax は小さくし、画像比較時に視線が揺れないようにする。
- narrow viewport では chat pane を隠し、main workspace を単一 focus にする。
- interactive controls の間隔を詰めすぎず、誤クリックしやすい透明ボタン群を作らない。

## Design Translation for ToC

### Layer Model

| Layer | Role | Material | Rule |
|---|---|---|---|
| `museumBackground` | 最奥の展示空間 | dark solid + subtle grid | 透明 UI のための環境光。主張しない |
| `workspace` | prompt / candidate の作業面 | solid / standard material | content layer。Liquid Glass を使わない |
| `promptCard` | 制作指示のキャプション | near-solid dark surface | 長文可読性を最優先 |
| `candidateFrame` | 画像の展示額 | rim glass only | 画像本体は透明化しない |
| `controlRail` | tabs / filters / counts | Liquid Glass | content の上に浮く操作層 |
| `topbar` | run navigation | light Liquid Glass | 案内板。薄く、読みやすく |
| `bulkFooter` | 採用・挿入 dock | dense Liquid Glass | 最重要 action。最も明確な状態を持つ |
| `chatPane` | 会話・承認 room | warm-tinted glass + solid messages | workspace と役割を分離 |

### Transparent Material

Apple 的な glass は、blur 単体ではなく、backdrop color pickup、edge highlight、shadow、lensing-like distortion、interaction response の組み合わせで成立する。Web / MUI では完全再現より、以下を揃える。

- `background`: 半透明 base + 上辺の弱い highlight gradient。
- `backdrop-filter`: blur と saturation。長文面には使わない。
- `border`: hairline と inner highlight で輪郭を出す。
- `shadow`: 背景からの分離と接地を担当。
- `state rim`: selected / focus / error / warning を material の上に重ねる。
- `fallback`: reduced transparency で blur なし、solid alpha 高めにする。

推奨の役割別透明度:

| Role | Background alpha | Notes |
|---|---:|---|
| icon chip | 0.46-0.60 | 短い label / icon のみ |
| topbar / small rail | 0.58-0.72 | 背後が単純な場合のみ薄くできる |
| tabs / segmented control | 0.68-0.82 | active segment は rim と fill を増やす |
| bulk footer / modal controls | 0.78-0.90 | 重要操作なので濃くする |
| prompt body / message body | 0.88-0.98 | glass ではなく readable surface |

### Depth and Motion

ToC の depth は、実際の 3D ではなく 2.5D の視覚文法で十分である。

- 手前にあるものほど shadow は広く、background alpha はやや高く、rim は明確にする。
- hover で `translateY(-1px)` 以上の大きな移動を多用しない。画像比較 UI では layout stability を優先する。
- modal は背面 dimming + slight scale / blur で focus を作る。
- generating 状態は大きな揺れではなく、progress、rim pulse、button state で示す。
- motion は「状態が変わった理由」を伝える時だけ使う。

### Controls

Apple の新しい controls は、標準 components が platform context に合わせて形状、サイズ、focus、material を調整する。ToC では MUI の標準挙動を壊さず、見た目だけを glass token で統一する。

- button は primary / secondary / destructive を明確に分ける。
- destructive や repo insertion は透明な美しさより、確認可能性を優先する。
- menu item は icon + label で scan しやすくする。
- slider / stepper は操作中の thumb や handle にだけ clear glass を使う。
- disabled は opacity だけでなく、cursor、label、tooltip、action availability で伝える。

### Navigation

Navigation は content を覆う装飾ではなく、ユーザーが今どの展示室にいるかを理解するための位置情報である。

- run selector は最上位の現在地。
- asset / scene tabs は展示カテゴリ。
- chara / obj / asset sub-filter は asset 内の棚。
- candidate count は生成条件の control。
- bulk footer は搬出・採用 dock。
- chat pane は curator room。

この対応を崩すと、glass がきれいでも「どこを触っているのか」が曖昧になる。

### Readability

Apple の material guidance は、material の見え方が環境・背景・accessibility settings によって変わることを前提にしている。ToC も、特定の美しい screenshot ではなく、候補画像が明るい、暗い、彩度が高い、細かい、のすべてで読める必要がある。

必須ルール:

- text over image は最小限。必要なら dark scrim を使う。
- file path や metadata は muted でも contrast を落としすぎない。
- prompt textarea は `backdrop-filter: none`。
- selected / failed / missing reference は、色、icon、label、border を併用する。
- low contrast な cyan-on-glass を長文に使わない。

### State Expression

| State | Apple-derived principle | ToC expression |
|---|---|---|
| idle | material は控えめに content を支える | low alpha glass + weak border |
| hover | pointer / gaze に反応する | rim と highlight を少し増やす |
| focus | 入力対象を明確化する | solid focus ring + label / caret visibility |
| active | control が手前に出る | dense fill + pressed shadow |
| generating | system activity を邪魔しない | progress + subtle rim pulse |
| selected | hierarchy を強く示す | cyan rim + stable selected label |
| inserted | action result を明確にする | success label + path confirmation |
| warning | 色だけに頼らない | amber rim + icon + short copy |
| error | 背景を赤く染めすぎない | red rim + message + retry action |
| disabled | 操作不能を予測可能にする | reduced contrast + reason / tooltip |

## Concrete Rules for `/image_gen`

1. Liquid Glass は navigation / controls / docks に限定する。
2. prompt と candidate image は content layer として安定させる。
3. glass は blur、fill、border、inner highlight、shadow、state rim の 5 点セットで設計する。
4. 大きい glass surface ほど不透明寄りにする。
5. scroll content の上に浮く bar は、scroll edge 相当の contrast treatment を持つ。
6. selected state は glow だけにしない。border と label を必ず持つ。
7. error state は赤い透明面だけにしない。短い文と retry action を持つ。
8. reduced transparency / reduced motion の fallback を必ず用意する。
9. text を奥行き方向に浮かせない。立体化するのは container まで。
10. visual novelty は topbar / footer / selected frame に集中し、全カードを派手にしない。
11. chat pane は workspace と同じ glass を流用せず、会話 room として別の色温度を持つ。
12. repo insertion は保存ではなく採用操作なので、bulk footer で最も重い affordance にする。

## Anti-Patterns

- candidate image 自体に opacity、blur、glass overlay をかける。
- prompt textarea を透明にして背後の grid を見せる。
- すべてのカードを glass 化し、content layer と control layer の差を消す。
- hover のたびに大きく浮く、揺れる、屈折する。
- cyan glow だけで selected / focus / success / generating を兼用する。
- disabled button を薄くするだけで理由を示さない。
- image grid の上に透明 footer を置き、下の画像と action label が干渉する。
- modal 背面を十分に整理せず、透明同士を重ねて読めなくする。
- 小さい icon button を密集させ、どれに pointer / focus が当たっているか曖昧にする。

## Implementation Notes

CSS / MUI では、Apple system APIs の自動適応を直接使えない。そのため、platform-native の考え方を token と component rule に落とす。

```css
@media (prefers-reduced-transparency: reduce) {
  .toc-glass {
    background: rgba(18, 22, 25, 0.94);
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .toc-glass,
  .toc-glass * {
    transition-duration: 0.01ms;
    animation-duration: 0.01ms;
  }
}
```

Glass token の最小構成:

```css
.toc-glass {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.10), rgba(255, 255, 255, 0.035)),
    rgba(23, 27, 31, 0.68);
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    0 18px 42px rgba(0, 0, 0, 0.30);
  backdrop-filter: blur(18px) saturate(135%);
  -webkit-backdrop-filter: blur(18px) saturate(135%);
}
```

ただし、この class を content card に一括適用しない。component の role に応じて alpha、blur、shadow、state rim を変える。

## Product Interpretation

ToC `/image_gen` の glass museum は、Apple 的には「透明な壁に覆われたギャラリー」ではない。

正しい解釈は、暗い制作空間の中で、作品と指示は読みやすい展示面に固定し、その前面に run selector、tabs、filters、candidate operations、chat approval が glass の操作層として浮かぶ構造である。

ユーザーは画像を鑑賞しているのではなく、生成候補を比較し、採用し、repo に挿入する。Liquid Glass はその判断の速度を上げるために、奥行きと状態を静かに可視化する。
