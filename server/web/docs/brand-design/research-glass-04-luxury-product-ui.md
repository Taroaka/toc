# Glass 04: Luxury Product UI Research

## Purpose

この調査は、自動車HMI、時計/宝飾、ハイエンドSaaS、金融端末、クリエイティブツールに見られる「過剰に派手ではない高級なガラス表現」を、ToC `/image_gen` の暗色制作UIへ翻訳するための設計メモである。

目的は、各ブランドの見た目を模倣することではない。金属、ガラス、反射、OLED 的な黒、精密な操作密度、短い microcopy、button hierarchy を、prompt / reference / candidate / repo insertion の実務 UI に使える判断基準へ落とす。

対象コンポーネント:

- `topbar`: run / folder / 現在地を示す精密なインストルメント
- `controls`: tab、filter、candidate count、generate 操作
- `grid`: request item 群を並べる高密度な制作面
- `candidate`: 画像候補の額装、比較、採用判断
- `footer`: download / repo insertion の採用 dock
- `chat pane`: 制作判断を支える静かな補助室

## Research Sources

長い引用は避け、公式ページ、公式ドキュメント、製品資料、信頼できる一次寄りの公開情報を中心に参照した。

### Automotive HMI / Luxury Cockpit

- Mercedes-Benz USA, MBUX Hyperscreen: https://www.mbusa.com/en/eq-electric-cars/technology/hyperscreen
- Mercedes-Benz Group, MBUX Hyperscreen: https://group.mercedes-benz.com/innovation/digitalisation/connectivity/mbux-hyperscreen.html
- BMW, Inside Neue Klasse - BMW Panoramic iDrive: https://www.bmw.com/en/digital-journey/inside-neue-klasse-bmw-panoramic-idrive.html
- BMW Group, The next stage in the evolution of BMW iDrive: https://www.bmwgroup.com/en/news/allgemein/2025/newidrive.html
- Porsche Newsroom, New Porsche Driver Experience: https://newsroom.porsche.com/en_US/2023/products/New-Cayenne-debuts-Porsche-Driver-Experience-.html
- Bentley Media, Bentley Rotating Display: https://www.bentleymedia.com/en/newsitem/1112-flying-spur-in-det%C3%A2%E2%82%AC%C2%A6

### Watches / Jewelry / Premium Product Surfaces

- TAG Heuer Official Magazine, Connected Calibre E4: https://magazine.tagheuer.com/en/2022/02/10/latest-tag-heuer-connected-watch-goes-the-distance-calibre-e4/
- TAG Heuer, Connected Calibre E4 product page: https://www.tagheuer.com/us/en/smartwatches/collections/tag-heuer-connected/45-mm/SBR8A11.BT6260.html
- Apple Support, Apple Watch Ultra technical specifications: https://support.apple.com/en-ie/111852
- Apple Newsroom, Introducing Apple Watch Ultra: https://images.apple.com/uk/newsroom/2022/09/introducing-apple-watch-ultra/
- Rolex, Watch configurator: https://www.rolex.com/watches/configure
- Cartier, High Jewelry creations: https://www.cartier.com/en-us/high-jewelry/all-creations/

### Financial Terminal / Dense Professional Workspaces

- Bloomberg Professional Services, Bloomberg Terminal: https://www.bloomberg.com/professional/products/bloomberg-terminal/
- Bloomberg Professional Services, Documentation: https://www.bloomberg.com/professional/support/documentation/
- Bloomberg LP, How Terminal UX designers conceal complexity: https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/
- Refinitiv UI, Halo theme documentation: https://cdn.ppe.refinitiv.com/public/apps/elf-docs/book/en/start/theming.html
- LSEG Workspace App Store description: https://apps.apple.com/id/app/refinitiv-workspace/id1481442629
- Purdue Libraries, LSEG Workspace overview: https://guides.lib.purdue.edu/refinitivworkspace

### High-End SaaS / Creative Tools

- Stripe Docs, Dark mode appearance variables: https://docs.stripe.com/connect/embedded-appearance-support-dark-mode
- Figma Blog, UI3 redesign: https://www.figma.com/blog/behind-our-redesign-ui3/
- Adobe Design, Spectrum Design System: https://adobe.design/toolkit/spectrum
- Adobe Blog, Spectrum 2 design system: https://blog.adobe.com/en/publish/2023/12/12/adobe-unveils-spectrum-2-design-system-reimagining-user-experience-over-100-adobe-applications
- Adobe Spectrum Web Components, Theme: https://opensource.adobe.com/spectrum-web-components/what-is-a-theme/
- Adobe Spectrum Web Components, Button: https://opensource.adobe.com/spectrum-web-components/components/button/
- Vercel Geist examples: https://examples.vercel.com/design/pill

### Display Glass / Reflection Control

- Apple, Pro Display XDR: https://www.apple.com/md/pro-display-xdr/
- React Spectrum, Theming: https://react-spectrum.adobe.com/react-spectrum/theming.html

## Governing Thought

最高峰の高級プロダクトUIは、ガラスを「透明な飾り」ではなく、黒、金属、光、密度を制御するための精密な境界として使う。ToC `/image_gen` では、candidate image と prompt を主役に保ち、glass / reflection は、操作層、採用状態、危険な上書き操作、会話領域を区別するための静かな計器盤として使う。

## Cross-Domain Findings

### 1. Luxury Glass Is Usually Darker Than Expected

Mercedes-Benz MBUX Hyperscreen、Porsche Driver Experience、TAG Heuer Connected、Apple Watch Ultra、Bloomberg Terminal、Refinitiv Workspace に共通するのは、明るい透明感ではなく、深い黒の中に情報と反射を限定的に浮かせる構成である。高級感は「見える背景の多さ」ではなく、黒の締まり、表面の連続性、必要な部分だけ光る精度から出る。

ToC 適用:

- app background は黒寄りにし、control surface は黒の上に 1-2 段だけ持ち上げる。
- glass は透明度を上げるほど高級になるわけではない。重要操作はむしろ濃くする。
- `candidate image` と `prompt textarea` は glass 化しない。読む面と見る面は安定した near-solid surface に置く。
- topbar / footer / chat frame / selected candidate rim だけに glass の光を集中させる。

### 2. Reflections Are Edges, Not Decorations

自動車HMIの curved glass、時計の sapphire crystal、Apple の display glass、宝飾品の金属・石の見せ方は、面全体を白く光らせるより、端部、角度、接合部で質感を伝える。Porsche の black panel design や TAG Heuer の flush screen は、境界を消しつつ、縁の精度で面を読ませる。

ToC 適用:

- reflection は `1px border`、inner top highlight、corner rim、selected outer glow に限定する。
- 斜めの大きな shine、白い帯、画像上の反射 overlay は使わない。
- glass の説得力は `border + inset highlight + shadow + blur` の合成で作る。
- hover 時は面を光らせず、rim の明度と shadow の深さを少しだけ変える。

### 3. Premium Density Is Controlled, Not Sparse

金融端末とクリエイティブツールは、情報量が多くても、利用者の記憶と速度を壊さないように構造化する。Bloomberg の価値は、データ、ニュース、分析、コミュニティが統合された高密度環境にある。Figma UI3 は canvas を主役にするため interface を整理し、Adobe Spectrum は多くのアプリを一貫した部品体系で支える。

ToC 適用:

- `/image_gen` は luxury landing page ではなく制作端末。余白を広げすぎない。
- grid card 内は `metadata -> prompt -> references -> existing/candidate -> action` の順に固定する。
- card は高密度でよいが、各行の役割を揃える。装飾的な card nesting を避ける。
- toolbar は小さな chip の散乱ではなく、1本の instrument rail としてまとめる。

### 4. The Best Button Hierarchy Is Calm Until It Matters

Mercedes-Benz の zero layer、BMW の Panoramic iDrive、Porsche の driver-focused control、Adobe Spectrum の button system、Stripe の dark variables は、状態や操作階層を過剰な発光ではなく、配置、色、密度、短い文言で整理する。

ToC 適用:

- primary は `Generate` と `Adopt to repo` に限定する。
- destructive / overwrite risk は美しさより確認可能性を優先する。
- secondary は outline / subdued fill、tertiary は icon / quiet text に落とす。
- disabled は opacity だけでなく、理由を短い tooltip / caption で示す。
- active tab は glow ではなく、fill、rim、font weight、position の差で示す。

### 5. Luxury Microcopy Is Short, Specific, And Operational

高級プロダクトUIの文言は、長い説明よりも短い名詞・動詞で状態を切る。自動車HMIでは運転中の認知負荷、金融端末では速度、クリエイティブツールでは作業面の邪魔をしないことが重要になる。

ToC 適用:

- button label は 1-3 words 相当の短い動詞にする。
- error は「失敗しました」ではなく、原因分類と次アクションに寄せる。
- status は感情語ではなく作業語にする。
- repo insertion は `Save` では弱い。上書きの意味を含む `Adopt` / `Insert` / `Confirm insert` 系の文言にする。

### 6. Warm Metal Should Be Scarce

Cartier、Rolex、Bentley の高級感は金色の量ではなく、黒、白、金属、宝石色の対比と余白で成立する。UI に直接金を広く敷くと、すぐに装飾過多やカジノ風になる。高級UIでは、金属色は status や special surface の細部に留める方が強い。

ToC 適用:

- gold / champagne は brand accent ではなく `premium rim`、`chat pane warmth`、`confirmed adoption` の微細な補助色にする。
- primary action は金ではなく cool cyan / blue を維持する。制作UIとしての精度を保つ。
- warning と gold を混同しない。warning は amber / orange、premium rim は desaturated champagne に分ける。
- warm accent は画面面積の 3% 未満に抑える。

### 7. High-End SaaS Uses Restraint To Protect Work

Stripe の dark mode variables、Figma UI3、Adobe Spectrum、Vercel Geist に共通するのは、製品の表現より作業対象を優先する姿勢である。暗色UIは「高級っぽい背景」ではなく、foreground content、states、controls を一貫して読ませるための色体系で成立する。

ToC 適用:

- text colors は low contrast に逃げず、主要文は確実に読ませる。
- accent は少数にする。cyan、champagne、red、green を同時に強く使わない。
- button や badge はコンポーネント体系で統一し、画面ごとの特注装飾を増やさない。
- professional UI として、hover / focus / selected / failed / generating の見分けを最優先する。

## Component Translation Matrix

| Source pattern | Luxury role | `/image_gen` component | UI translation |
| --- | --- | --- | --- |
| MBUX Hyperscreen curved glass | 複数画面を1枚の面として統合 | `topbar` + `controls` | separate chips ではなく、連続した black glass rail にする。 |
| Mercedes zero layer | よく使う機能を前面化 | `controls` | generation count、tab、generate を最短導線に置き、深い menu に逃がさない。 |
| BMW Panoramic iDrive | 視線を前方に保つ横長情報帯 | `topbar` | run / folder / current mode を薄い横長帯で見せ、主作業面を邪魔しない。 |
| Porsche black panel glass | 物理面とデジタル面の連続 | `footer` | repo insertion dock を濃い black glass にし、重要操作を一段手前に置く。 |
| Bentley rotating display | digital / analog / material の切替 | view modes | asset / scene / chara / obj を単なるタブでなく「作業面の切替」として見せる。 |
| TAG Heuer sapphire flush screen | 端部が滑らかにつながる精密面 | `candidate` frame | 画像本体は触らず、frame の rim と corner highlight で質感を出す。 |
| Apple Watch Ultra raised titanium edge | ガラスを保護する金属縁 | selected / failed frame | selected / failed / generating を image 外側の rim で示し、画像を汚さない。 |
| Rolex configurator | 静かな選択体験 | selectors | option は大きく騒がせず、選択済みだけを明確にする。 |
| Cartier high jewelry contrast | 黒、白、宝石色、金属の対比 | accents | champagne / emerald / ruby 系は微細な semantic rim に限定する。 |
| Bloomberg Terminal | 高密度でも速度優先 | grid | metadata と操作を詰めつつ、行・桁・位置を固定する。 |
| Refinitiv Halo dark theme | light/dark を体系化 | theme tokens | dark surface、border、text、semantic color を token として固定する。 |
| Stripe dark variables | component-level dark consistency | buttons / badges | colorPrimary、danger、border、badge を role ごとに分ける。 |
| Figma UI3 | canvas を主役に戻す | workspace | image / prompt を主役にし、chrome は薄く整理する。 |
| Adobe Spectrum | 多アプリを支える部品体系 | all controls | button size、quiet / emphasized、pending state を統一する。 |
| Pro Display XDR nano-texture | glare を制御する高級表面 | all glass | 反射を増やすより、glare を減らす方向で glass を調整する。 |

## Material System For `/image_gen`

### Color Tokens

高級感の主軸は「黒を何段持つか」で決まる。彩度の高い色を増やすより、黒、金属グレー、低彩度の青、微量の champagne を精密に分ける。

| Token | Value | Role |
| --- | --- | --- |
| `lux.black.0` | `#050608` | app 最奥。OLED black に近い背景。 |
| `lux.black.1` | `#090B0F` | workspace 背景。grid の奥行き。 |
| `lux.black.2` | `#10141A` | card / prompt readable surface。 |
| `lux.black.3` | `#171C23` | raised controls / input surface。 |
| `lux.steel.1` | `#252B33` | borders、disabled、subtle separators。 |
| `lux.steel.2` | `#3A424D` | hover rim、secondary icon。 |
| `lux.text.1` | `#EEF3F8` | primary text。 |
| `lux.text.2` | `#B7C0CA` | metadata、secondary labels。 |
| `lux.text.3` | `#74808D` | tertiary captions。 |
| `lux.cyan` | `#7CD7F6` | selected candidate、primary focus。 |
| `lux.blue` | `#3C8CFF` | primary action fill / progress。 |
| `lux.champagne` | `#D6BE8A` | premium rim、confirmed adoption の微細 highlight。 |
| `lux.amber` | `#F2A84B` | warning / overwrite caution。 |
| `lux.red` | `#FF5D72` | failed / destructive。 |
| `lux.green` | `#64D68A` | completed / inserted。 |

避ける色:

- 大面積の金、紫グラデーション、青紫だけの単調な暗色UI。
- cyan-on-black の長文。accent は枠と状態に使い、本文には使わない。
- pure white glow。高級というより安い発光に見えやすい。

### Surface And Glass Tokens

| Surface | CSS direction | Usage |
| --- | --- | --- |
| `surface.workspace` | `#090B0F` | page background。 |
| `surface.card` | `rgba(16, 20, 26, 0.94-0.98)` | prompt / request card。blur なし。 |
| `surface.input` | `rgba(10, 13, 17, 0.96-0.99)` | textarea / code-like text。 |
| `glass.rail` | `rgba(15, 19, 25, 0.72-0.82)` + blur | topbar / controls。 |
| `glass.dock` | `rgba(13, 17, 22, 0.82-0.90)` + blur | footer / modal action bar。 |
| `glass.chip` | `rgba(28, 34, 42, 0.52-0.68)` + blur | icon chips / short filters。 |
| `glass.chat` | `rgba(20, 18, 15, 0.78-0.88)` + blur | chat pane frame。 |
| `rim.selected` | cyan border + small outer glow | selected candidate only。 |
| `rim.premium` | champagne 1px top / corner highlight | confirmed / adopted nuance。 |
| `rim.error` | red border + red caption | failed candidate / destructive caution。 |

CSS direction:

```css
--lux-shadow-raised: 0 18px 48px rgba(0, 0, 0, 0.42);
--lux-shadow-dock: 0 -18px 48px rgba(0, 0, 0, 0.46);
--lux-shadow-selected: 0 0 0 1px rgba(124, 215, 246, 0.72), 0 0 22px rgba(124, 215, 246, 0.16);
--lux-rim-top: inset 0 1px 0 rgba(255, 255, 255, 0.10);
--lux-rim-bottom: inset 0 -1px 0 rgba(0, 0, 0, 0.42);
--lux-blur-rail: blur(18px) saturate(1.25);
--lux-blur-dock: blur(24px) saturate(1.18);
```

### Reflection Rules

- use: top edge highlight、1px rim、inset shadow、corner glint、focus ring。
- avoid: diagonal shine、animated white sweep、glass overlay over images、reflection over textarea。
- selected: cyan rim only on selected candidate, not entire card.
- adopted: champagne hairline can appear after confirmation, but should not replace the primary selected cyan.
- failed: red rim must pair with short error text and stable frame size.

### Shadow Rules

- `topbar`: small vertical separation, not heavy drop shadow.
- `controls`: same plane as topbar or slightly lower; no competing glow.
- `candidate frame`: selected only gets visible outer glow.
- `footer`: strongest shadow because it is the closest operation layer.
- `chat pane`: warm shadow, lower contrast than footer.

目安:

| Component | Shadow | Reason |
| --- | --- | --- |
| topbar | `0 12px 32px rgba(0,0,0,.28)` | 現在地の浮上。 |
| controls rail | `0 10px 28px rgba(0,0,0,.24)` | 操作帯として分離。 |
| card | `0 1px 0 rgba(255,255,255,.03), 0 16px 42px rgba(0,0,0,.20)` | content は主張しすぎない。 |
| selected candidate | cyan rim + `0 16px 38px rgba(0,0,0,.32)` | 採用候補だけ強調。 |
| footer | `0 -20px 54px rgba(0,0,0,.50)` | 上書き操作の dock。 |

## Density Rules

高級UIは必ずしも余白が広いわけではない。金融端末、HMI、クリエイティブツールのように、専門作業では高密度が信頼感になる。ただし密度は、部品の意味、位置、リズムが揃っている場合にだけ成立する。

### Layout Density

- desktop grid は 2 columns を維持し、candidate 比較を優先する。
- card gap は `16-20px`。これ以上詰めるなら card 内余白を先に見直す。
- card padding は `14-18px`。landing page 的な `32px+` は避ける。
- metadata row は `12-13px`、prompt body は `13-14px`、primary button は `14px`。
- toolbar height は `44-52px`。自動車HMIのように横長で安定させる。
- footer height は `64-76px`。重要操作を入れるが、画像比較を圧迫しない。

### Information Rhythm

各 card の順序:

1. `id / lane / output path`
2. prompt text field
3. reference selector
4. existing image and generated candidates
5. per-item generate / adopt controls

禁止:

- card 内の nested decorative card。
- candidate ごとに異なる button 位置。
- metadata が image 上に重なる配置。
- hover で card size が変わる state。

## Microcopy Rules

### Voice

文体は「制作端末の計器表示」。感情語、説明過多、マーケティング語を避ける。

Good:

- `Generate`
- `Regenerate`
- `Select`
- `Adopt`
- `Insert to repo`
- `Confirm insert`
- `Download zip`
- `Missing reference`
- `Prompt required`
- `Generation failed`
- `Retry`

Avoid:

- `Make magic`
- `Create amazing visuals`
- `Oops, something went wrong`
- `Save` for repo overwrite
- `Are you sure you want to proceed with this irreversible action?` in cramped UI

### Status Copy

| State | Copy | Note |
| --- | --- | --- |
| idle | `Ready` | 必要な場所だけ。常時表示しすぎない。 |
| generating | `Generating` | progress と組み合わせる。 |
| selected | `Selected` | candidate frame 内の小さな label。 |
| inserted | `Inserted` | green + champagne hairline で完了感。 |
| failed | `Generation failed` | 詳細は tooltip / expandable details。 |
| missing ref | `Missing reference` | reference selector 近くに置く。 |
| overwrite risk | `Will overwrite output` | footer / confirm に置く。 |

## Button Hierarchy

### Roles

| Role | Use | Visual |
| --- | --- | --- |
| Primary | `Generate`, `Adopt to repo` | cool blue fill or strong cyan rim. One region one primary. |
| Secondary | `Download zip`, `Regenerate`, `Select` | dark steel fill + subtle border. |
| Tertiary | inspect, copy path, open folder | icon button / quiet text. |
| Destructive / risk | overwrite confirm, remove candidate | amber pre-confirm, red destructive only at final danger. |
| Pending | generation / insertion in progress | disabled cursor + progress + label change. |

### Specific Mapping

- `Generate`: primary inside card, but less strong than footer adoption.
- `Bulk generate`: primary in footer only when no higher-risk operation is pending.
- `Download zip`: secondary; no glow.
- `Insert to repo`: highest responsibility. Use primary visual + confirmation state.
- `Confirm insert`: amber/cyan mixed hierarchy. The text must show the irreversible direction.
- `Select candidate`: secondary until selected; selected becomes cyan rim on frame, not a filled button.
- `Retry failed`: secondary with red rim only on failed frame.

### Interaction States

| State | Treatment |
| --- | --- |
| hover | border alpha +0.08, shadow +1 level, no size change. |
| focus | accessible ring outside rim, not just color. |
| active | inset shadow, slight luminance reduction. |
| disabled | lower contrast plus explicit reason if ambiguous. |
| pending | spinner/progress at icon slot, label remains stable width where possible. |

## Component Rules

### Topbar

Luxury role: panoramic instrument strip.

- Use dark glass rail with controlled blur.
- Keep run / folder selector readable; do not over-transparently reveal background texture.
- Current run should be clearer than secondary path.
- Use one thin top highlight and one bottom separator.
- Avoid gold in topbar except a tiny adopted-state indicator if needed.

Recommended:

- background: `rgba(12, 16, 21, 0.78)`
- border: `1px solid rgba(255,255,255,0.08)`
- top rim: `inset 0 1px 0 rgba(255,255,255,0.10)`
- text: `lux.text.1` for current, `lux.text.2` for secondary

### Controls

Luxury role: center console.

- Merge tabs, filters, candidate count, and generate controls into coherent rails.
- Active segment uses fill + rim, not large glow.
- Candidate count should feel like an instrument setting, with stable numeric width.
- Avoid many equal-weight chips. Only the active mode should come forward.

Recommended:

- rail background: `rgba(17, 22, 29, 0.76)`
- inactive chip: `rgba(255,255,255,0.035)`
- active chip: `rgba(124,215,246,0.10)` + cyan rim
- numeric control: monospaced tabular numbers

### Grid Card

Luxury role: dense professional work surface.

- Use near-solid dark surface; do not make full cards highly transparent.
- Metadata row should be quiet but legible.
- Prompt textarea must have no blur and strong text contrast.
- Reference thumbnails should look like inventory, not decorative stickers.
- Hover should clarify interactivity without making every card glow.

Recommended:

- card background: `rgba(15, 19, 25, 0.96)`
- card border: `rgba(255,255,255,0.07)`
- hover border: `rgba(124,215,246,0.18)`
- metadata text: `#9AA6B2`

### Candidate

Luxury role: sapphire display inside a protective metal frame.

- Keep image untouched: no blur, opacity reduction, or shine overlay.
- Show state on the frame outside image content.
- Selected candidate gets the strongest cyan rim in the card.
- Existing image uses archive tone: steel rim, no cyan.
- Failed candidate keeps the same 16:9 footprint.

Recommended:

- image frame background: `#050608`
- default rim: `rgba(255,255,255,0.08)`
- selected rim: `rgba(124,215,246,0.78)`
- selected glow: `0 0 24px rgba(124,215,246,0.16)`
- archive rim: `rgba(214,190,138,0.22)` only if needed

### Footer

Luxury role: adoption dock / black panel command surface.

- Footer is the closest and most responsible control plane.
- Stronger glass is acceptable because it handles irreversible or bulk actions.
- Repo insertion must visually outrank download.
- Confirmation state should replace or transform the button area, not open a noisy decorative modal unless necessary.

Recommended:

- background: `rgba(10, 13, 18, 0.88)`
- backdrop: `blur(24px) saturate(1.16)`
- shadow: `0 -20px 54px rgba(0,0,0,0.50)`
- primary adoption: blue fill + cyan rim, amber caption for overwrite risk

### Chat Pane

Luxury role: warm adjacent consultation room.

- Main UI remains cool black / steel; chat can use a slightly warmer black.
- Glass belongs to pane frame and header, not message bodies.
- Message body should be readable and stable.
- Chat should never look more important than candidate comparison.

Recommended:

- pane background: `rgba(18, 16, 14, 0.84)`
- warm rim: `rgba(214,190,138,0.14)`
- assistant message: `rgba(20, 24, 29, 0.96)`
- user message: `rgba(27, 33, 40, 0.96)`

## Practical CSS Patterns

### Luxury Rail

```css
.luxury-rail {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.055), rgba(255, 255, 255, 0) 42%),
    rgba(12, 16, 21, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.10),
    inset 0 -1px 0 rgba(0, 0, 0, 0.42),
    0 12px 32px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(18px) saturate(1.22);
}
```

### Precision Candidate Frame

```css
.candidate-frame {
  background: #050608;
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 14px 34px rgba(0, 0, 0, 0.28);
}

.candidate-frame[data-selected="true"] {
  border-color: rgba(124, 215, 246, 0.78);
  box-shadow:
    0 0 0 1px rgba(124, 215, 246, 0.22),
    0 0 24px rgba(124, 215, 246, 0.16),
    0 16px 38px rgba(0, 0, 0, 0.32);
}
```

### Adoption Dock Button

```css
.adopt-button {
  background:
    linear-gradient(180deg, rgba(255,255,255,0.11), rgba(255,255,255,0) 48%),
    #1E6B9E;
  border: 1px solid rgba(124, 215, 246, 0.42);
  color: #F3FAFF;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    0 10px 28px rgba(30, 107, 158, 0.24);
}

.adopt-button[data-risk="overwrite"] {
  border-color: rgba(242, 168, 75, 0.56);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.14),
    0 0 0 1px rgba(242, 168, 75, 0.10),
    0 10px 28px rgba(0, 0, 0, 0.32);
}
```

## Engagement / Product Quality Hooks

| Hook | Applied scene in `/image_gen` | Design cue |
| --- | --- | --- |
| One sheet of black glass | topbar / controls | HMI-like continuous rail instead of scattered chips. |
| Sapphire frame | candidate area | image untouched, state lives on rim. |
| Black panel command dock | footer | repo insertion gets calm authority. |
| Watch-like precision | buttons / numeric controls | tabular numbers, fixed dimensions, no layout shift. |
| Jewelry restraint | accents | champagne only as tiny rim, not broad fill. |
| Terminal density | grid | compact rows with stable rhythm. |
| Creative canvas first | workspace | prompt and candidate remain dominant. |
| Zero-layer action | controls | frequent generation actions stay visible. |
| Anti-glare luxury | all glass | reduce glare before adding shine. |
| Quiet confirmation | repo insertion | confirm state is explicit but not theatrical. |

## Do / Don't

### Do

- Use near-black surfaces with 1px precision rims.
- Keep glass to operation layers, not content layers.
- Make selected candidate obvious through frame treatment.
- Make overwrite risk explicit in footer microcopy.
- Use cool cyan / blue for active production states.
- Use champagne only as scarce premium detail.
- Preserve high information density with stable positions.
- Ensure all text remains readable over dark surfaces.

### Don't

- Put diagonal reflection across images or prompt text.
- Turn every card into transparent glass.
- Use gold as the primary action color.
- Add large glow to all controls.
- Make luxury mean low-density landing-page spacing.
- Hide destructive meaning behind generic `Save`.
- Let chat pane visually overpower the candidate grid.
- Rely on color alone for failed / selected / pending states.

## Implementation Priorities

1. Define dark luxury tokens before component tweaks.
2. Convert topbar / controls / footer into coherent glass rails.
3. Keep prompt and candidate content near-solid and glare-free.
4. Move selection, failure, and adoption states onto rims and concise labels.
5. Tighten button hierarchy so repo insertion outranks download.
6. Audit microcopy and replace generic save/error text with operational labels.
7. Check density at desktop and mobile widths so controls do not wrap awkwardly.

## Residual Risks

- Too much gold will make the UI feel decorative rather than precise.
- Too much transparency will reduce trust because prompts, paths, and candidate states become harder to read.
- Too much empty space will make `/image_gen` feel like a marketing surface instead of a professional production terminal.
- Too many glows will flatten hierarchy because every control appears important.
- If button copy stays generic, visual luxury will not fix ambiguity around repo overwrite actions.
