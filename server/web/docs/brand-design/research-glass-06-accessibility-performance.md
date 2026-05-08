# Glass UI Accessibility and Performance Research for `/image_gen`

## Purpose

ToC `/image_gen` で Liquid Glass を使いながら、prompt 編集、candidate 比較、右 chat pane の可読性と操作性能を落とさないための実装ルールをまとめる。

この文書の結論は、glass を「装飾」ではなく「操作層の境界」に限定すること。読む場所、見る場所、判断する場所は near-solid surface に置き、透明・屈折・反射は状態と階層を伝えるために最小限使う。

## Executive Decision

`/image_gen` の glass UI は、次の 4 条件を満たす場合だけ採用する。

1. **可読性が固定背景なしで成立する**
   - text は WCAG AA の通常テキスト 4.5:1、large text 3:1 を下回らない。
   - prompt textarea と chat message body は `rgba(16,20,23,.92)` 以上の solid 寄り surface にする。
   - dynamic image / grid / gradient の上で contrast が毎回変わる場所に長文を置かない。

2. **状態が色以外でも分かる**
   - selected / failed / disabled / focus は、色だけでなく border weight、outline、icon、label、位置で示す。
   - UI component の境界や状態 rim は 3:1 以上を目標にする。
   - focus ring は `:focus-visible` で必ず出し、sticky footer / chat pane に隠れない。

3. **user preference と forced colors を尊重する**
   - `prefers-reduced-transparency: reduce` では glass を opaque surface に切り替える。
   - `prefers-reduced-motion: reduce` では sweep、morph、shine、blur animation を止める。
   - `forced-colors: active` では gradients / box-shadow / backdrop blur を意味情報にしない。
   - `prefers-contrast: more` では border、outline、message surface を強める。

4. **rendering cost を限定する**
   - 常時 `backdrop-filter` は fixed / low-count layer だけに使う。
   - repeated prompt cards、candidate grid、scroll container、chat message bubble には常時 blur を入れない。
   - `will-change` は常用しない。測定で必要な短時間の hint に限定する。
   - glass を追加したら DevTools の Paint flashing、Layer borders、FPS、Performance trace で検証する。

## Source Map

| Area | Sources | ToC relevance |
|---|---|---|
| WCAG text contrast | W3C Understanding SC 1.4.3 Contrast Minimum: https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html | prompt / chat / button label の最低 contrast |
| WCAG non-text contrast | W3C Understanding UI Component Contrast / SC 1.4.11: https://w3c.github.io/wcag21/understanding/21/user-interface-component-contrast-minimum.html | selected rim、focus ring、icon、control outline |
| WCAG 2.2 changes | W3C What's New in WCAG 2.2: https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/ | focus not obscured、target size、new AA requirements |
| Focus appearance | W3C Understanding SC 2.4.13 Focus Appearance: https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html | two-color focus ring と dynamic backgrounds |
| Target size | W3C Understanding SC 2.5.8 Target Size Minimum: https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum | icon buttons、candidate selection、chat send |
| Backdrop filter | MDN `backdrop-filter`: https://developer.mozilla.org/en-US/docs/Web/CSS/backdrop-filter | backdrop root、filter list、parent opacity pitfalls |
| Backdrop performance | web.dev backdrop-filter: https://web.dev/articles/backdrop-filter | fallback、stacking context、performance warning |
| Rendering pipeline | web.dev Rendering performance: https://web.dev/articles/rendering-performance | layout / paint / composite の cost model |
| DevTools rendering | Chrome DevTools Rendering performance: https://developer.chrome.com/docs/devtools/rendering/performance | paint flashing、layer borders、FPS overlay |
| Reduced motion | MDN `prefers-reduced-motion`: https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion | animation opt-out |
| Reduced transparency | MDN `@media`: https://developer.mozilla.org/en-US/docs/Web/CSS/@media | Media Queries Level 5 の `prefers-reduced-transparency` |
| Forced colors | MDN `forced-colors`: https://developer.mozilla.org/en-US/docs/Web/CSS/@media/forced-colors | Windows High Contrast 等の system colors |
| Forced color adjust | MDN `forced-color-adjust`: https://developer.mozilla.org/docs/Web/CSS/forced-color-adjust | user choice を尊重する例外運用 |
| Contrast preference | MDN `prefers-contrast`: https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-contrast | stronger outlines / solid surfaces |
| Will-change | MDN `will-change`: https://developer.mozilla.org/en-US/docs/Web/CSS/will-change | premature optimization と stacking context risk |
| CSS performance | MDN CSS performance optimization: https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Performance/CSS | animation property selection、GPU/compositing |
| Animation performance | MDN CSS/JS animation performance: https://developer.mozilla.org/en-US/docs/Web/Performance/CSS_JavaScript_animation_performance | transform / layer promotion の条件 |

## Governing Thought

`/image_gen` の最高峰 glass UI は、透明度を増やす UI ではなく、透明度を **読める範囲、動く範囲、測れる範囲** に閉じ込める material system である。

Liquid Glass の美しさは topbar、controls、bulk footer、chat shell、selected candidate rim で担い、prompt 本文、candidate image、chat message は solid readable surface に戻す。これにより、候補画像の色判断、長い prompt 編集、右チャットの読解、bulk 操作の反応速度を守れる。

## Accessibility Baseline

### Contrast

WCAG 1.4.3 は text contrast の基準を定める。ToC では次を下限にする。

| Target | Minimum | ToC rule |
|---|---:|---|
| prompt textarea text | 4.5:1 | 背面は `rgba(16,20,23,.96)`、文字は `rgba(255,255,255,.92)` 以上 |
| chat message text | 4.5:1 | message bubble は glass ではなく solid surface |
| metadata / path / caption | 4.5:1 preferred | 小さい文字なので muted を薄くしすぎない。`rgba(255,255,255,.64)` を下限目安 |
| large heading / title | 3:1 | topbar title は背景変化に負けない |
| disabled text | WCAG 対象外になり得るが実用上読めること | opacity だけで無効を表さない。helper text を併用 |

WCAG 1.4.11 は UI component や graphic の重要な視覚情報にも contrast を求める。ToC では selected rim、focus indicator、error rim、warning rim、icon-only button の shape を 3:1 以上で設計する。

### Dynamic Background Rule

Glass の背後は常に変わるため、静的な color pair だけで合格判定しない。

- 背景が candidate image、thumbnail、grid texture、scrolling content の場合、text を直接置かない。
- どうしても画像上に label を置く場合は 1 行 chip までにし、chip 自体を `rgba(16,20,23,.88)` 以上にする。
- focus ring は dynamic background に強い two-color ring を使う。例: outer `CanvasText` / inner brand rim、または dark outer + amber inner。
- text shadow は contrast の主手段にしない。blurred shadow は低視力ユーザーににじみとして見える。

### Color Is Never the Only Signal

| State | Required non-color signal |
|---|---|
| selected candidate | 2px rim、check icon または `Selected` label、bulk footer count との連動 |
| failed candidate | error icon、`Failed` label、固定 16:9 error slot |
| missing reference | warning icon、filename row の message、border weight |
| disabled action | disabled attribute、helper text、icon tone、cursor / interaction removal |
| focus-visible | outline / box-shadow ring。hover と別形状 |
| generating | progress bar または static status label。motion だけにしない |

## User Preference Modes

### Reduced Transparency

`prefers-reduced-transparency` は、透明・半透明 layer を減らしたいユーザーの preference を表す。対応ブラウザ差があるため、通常 mode でも最低 contrast を満たしつつ、対応環境では glass を切る。

```css
@media (prefers-reduced-transparency: reduce) {
  .glassTopbar,
  .glassControls,
  .bulkFooter,
  .chatPane,
  .chatHead {
    background: #171b1f !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    box-shadow: none;
  }

  .promptCard,
  .chatMessage,
  .candidate {
    background: #101417;
  }
}
```

ToC rule:

- reduced transparency では layer hierarchy を border と spacing で維持する。
- frosted / translucent / glass / lensing / refraction はすべて decorative とみなし、意味情報を載せない。
- chat pane は残してよいが、pane shell と message bubble を opaque にする。

### Reduced Motion

`prefers-reduced-motion: reduce` では、非必須の motion を削除または静的表示へ置き換える。

```css
@media (prefers-reduced-motion: reduce) {
  .promptCard.is-generating::after,
  .glass-shine,
  .glass-rim-animated {
    animation: none !important;
  }

  .candidate,
  .promptCard,
  .bulkFooter,
  .chatPane {
    transition: none !important;
  }
}
```

ToC rule:

- loading は shimmer / sweep ではなく `LinearProgress` または text status にする。
- hover は scale ではなく border / background delta にする。
- candidate image、prompt card、chat pane は panning / parallax / morph しない。
- animation を完全に消しても state が分かるかを keyboard だけで確認する。

### Forced Colors

`forced-colors: active` では user agent が user-chosen palette を適用する。Glass の gradient、shadow、半透明背景は信頼できない。

```css
@media (forced-colors: active) {
  .glassTopbar,
  .glassControls,
  .bulkFooter,
  .chatPane,
  .promptCard,
  .candidate {
    background: Canvas;
    color: CanvasText;
    border: 1px solid CanvasText;
    box-shadow: none;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }

  .candidate.is-selected,
  .Mui-focusVisible,
  .candidate[role="button"]:focus-visible {
    outline: 2px solid Highlight;
    outline-offset: 2px;
  }

  .candidate.lg-status-rim--error {
    outline: 2px solid Mark;
  }
}
```

ToC rule:

- `forced-color-adjust: none` は原則使わない。user choice を壊すため、画像やブランドロゴなど本当に必要な局所だけ検討する。
- selected / error / focus は system color keyword で表す。
- icon-only buttons は `aria-label` と visible focus を必須にする。

### Prefers Contrast

`prefers-contrast: more` では、glass の繊細な境界を強める。

```css
@media (prefers-contrast: more) {
  .promptCard,
  .candidate,
  .chatMessage {
    background: #0c0f11;
    border-color: rgba(255, 255, 255, .42);
  }

  .candidate.is-selected {
    border-width: 2px;
  }

  .Mui-focusVisible,
  .candidate[role="button"]:focus-visible {
    outline: 3px solid #f6d365;
    outline-offset: 2px;
  }
}
```

## Rendering and GPU Rules

### Browser Pipeline Implications

Browser rendering は大きく style、layout、paint、composite に分かれる。Glass UI で問題になるのは、`backdrop-filter`、large blur、box-shadow、gradient、scrolling content が paint / rasterization / compositing の仕事を増やす点である。

ToC rule:

- animated property は原則 `transform` / `opacity` に限定する。ただし opacity は parent に使うと backdrop root を変えるため、glass parent には使わない。
- `box-shadow`、`filter`、`backdrop-filter`、large gradient を連続 animation しない。
- candidate grid の scroll 中に paint flashing が広範囲で出る glass は不採用。
- blur radius は desktop 18px 以下、mobile 12px 以下を上限にする。
- visible glass blur layer は desktop 4 以下、mobile 3 以下に抑える。

### Backdrop Root Pitfalls

MDN は、`filter`、`opacity < 1`、`mask`、`clip-path`、`backdrop-filter`、`mix-blend-mode`、関連する `will-change` が backdrop root になると説明している。親が backdrop root になると、子の blur は期待したページ背景ではなく親内だけに効く。

ToC avoid:

- `.workspace { opacity: .98 }` のような親 opacity。
- glass shell の親に `filter` / `mix-blend-mode` / `clip-path` を付ける。
- all cards に `will-change: transform` を常時付ける。
- nested glass inside glass。必要なら outer shell は glass、inner text body は solid に分離する。

### Will-change Policy

`will-change` は「最後の手段」として扱う。

- 常時付与しない。
- hover 直前や drag / open transition の短時間だけ JS で付け、終了後に外す。
- `will-change: opacity` は stacking context と backdrop root の副作用を確認してから使う。
- prompt grid 全体、candidate list 全体、chat scroll 全体には付けない。

### GPU and Compositing Policy

GPU compositing は万能ではない。layer を増やすと memory と texture upload が増え、mobile で逆効果になる。

Adopt:

- fixed topbar / footer / chat shell は単独 layer になってもよい。
- candidate hover は `transform: translateY(0)` のような実質不要な promotion をしない。
- panel open / close が必要な場合だけ `transform` animation にする。

Avoid:

- candidate card ごとの `translateZ(0)`。
- scroll container 内の大量 glass layer。
- blur / shadow / backdrop の continuous animation。
- WebGL / SVG displacement を core UI の state 表現に使う。

## Glass Anti-patterns

`/image_gen` でやってはいけないこと。

| Anti-pattern | Why it fails | Required alternative |
|---|---|---|
| prompt textarea を透明 glass にする | 長文編集の contrast が背景で変わる | solid dark paper |
| chat message bubble を frosted にする | 右 chat の連続読解が疲れる | bubble は `rgba(18,22,25,.92+)` |
| candidate image に opacity / blur / filter をかける | 画像比較と色判断が壊れる | frame と label chip だけ glass |
| grid card 全体を常時 backdrop blur | scroll jank と layer 過多 | card は near-solid、固定 UI だけ blur |
| selected を cyan glow だけで示す | 色覚差、forced colors で消える | rim + check + label + aria state |
| focus outline を消して custom hover と兼用 | keyboard 操作が追えない | `:focus-visible` 専用 ring |
| sticky bulk footer が focused target を隠す | WCAG 2.4.11 risk | scroll padding / focus scroll margin |
| large animated shine / shimmer | reduced motion と GPU cost に弱い | static progress / short local indicator |
| parent opacity で glass の濃さを調整 | backdrop root と text opacity の副作用 | background alpha token |
| forced colors で brand color を固定 | user palette を壊す | system colors を使う |
| fallback なしの `backdrop-filter` | unsupported / low power 環境で読めない | `@supports not` solid background |
| SVG/WebGL refraction を button state に使う | accessibility / test / perf が複雑化 | decorative rim-only、状態は DOM/CSS |

## Fallback Strategy

### Support Fallback

```css
.toc-glass {
  background:
    linear-gradient(180deg, rgba(255,255,255,.10), rgba(255,255,255,.035)),
    rgba(23,27,31,.72);
  border: 1px solid rgba(255,255,255,.16);
  backdrop-filter: blur(16px) saturate(130%);
  -webkit-backdrop-filter: blur(16px) saturate(130%);
}

@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .toc-glass {
    background: rgba(23,27,31,.96);
  }
}
```

Fallback rule:

- unsupported browser では「glass が消える」のではなく「opaque UI として成立する」こと。
- fallback で layout size を変えない。
- fallback でも selected / focus / error の visual language を維持する。

### Degradation Levels

| Level | Trigger | Behavior |
|---|---|---|
| Full glass | default modern desktop | topbar / controls / bulk footer / chat shell に static backdrop blur |
| Reduced glass | mobile or low power profile | blur radius 30% down、animated shine none |
| Opaque accessible | reduced transparency / forced colors / unsupported | no backdrop filter、solid surface、system colors |
| Diagnostic off | performance regression | CSS class or feature flagで all glass disabled |

## Component Checklist

### App Shell

- [ ] background は静的で、animated gradient / orb / bokeh を置かない。
- [ ] glass layer の背後に高彩度・高周波 pattern を置かない。
- [ ] shell に `opacity`、`filter`、`mix-blend-mode` を付けない。
- [ ] reduced transparency / forced colors で shell と panel の境界が残る。

### Topbar / Folder Selector

- [ ] `backdrop-filter` は許可。ただし `blur(12px-16px)` 程度。
- [ ] folder selector の text contrast は背景変化に関係なく 4.5:1。
- [ ] reload / icon buttons は 24x24 CSS px 以上、できれば 32-40px target。
- [ ] focus ring は topbar glass 上で 3:1 以上。
- [ ] loading indicator は topbar height を変えない。

### Controls / Tabs / Candidate Count

- [ ] active tab は色だけでなく filled background / border / selected state を持つ。
- [ ] slider thumb、stepper、select は 24x24 CSS px 以上の target。
- [ ] controls rail は glass 可、menu / dropdown list は opaque 寄り。
- [ ] hover と focus-visible を別表現にする。
- [ ] `prefers-contrast: more` で border を強める。

### Prompt Card

- [ ] card body は near-solid。常時 `backdrop-filter` を使わない。
- [ ] prompt textarea は `backdrop-filter: none`。
- [ ] textarea は 4.5:1 contrast、selection color、caret visibility を確認する。
- [ ] item id / path / lane は小さいため薄くしすぎない。
- [ ] generating sweep は reduced motion で停止し、static progress に置換する。
- [ ] focus-within ring は card outline と textarea outline の両方で迷子にならない。

### Reference Selector

- [ ] thumbnail に opacity / blur / color filter をかけない。
- [ ] selected reference chip は check icon または label を持つ。
- [ ] missing reference は warning icon + message + rim。
- [ ] dropdown option hover / focus は background delta と outline で分かる。
- [ ] forced colors でも selected / focused option が system colors で読める。

### Candidate Frame

- [ ] 画像本体は `opacity: 1`、`filter: none`、`backdrop-filter: none`。
- [ ] frame は 16:9 fixed aspect ratio。empty / loading / failed でも高さを変えない。
- [ ] selected は 2px rim + label/icon + aria state。
- [ ] candidate selectable area は keyboard 操作可能で、Enter / Space に反応する。
- [ ] focus-visible は selected と区別できる。selected + focus の二重状態も確認する。
- [ ] failed candidate は 1 行 message と error rim。長い stack trace を出さない。
- [ ] image label chip は 1 行まで。画像の重要領域を覆わない。

### Candidate Grid / Scrolling

- [ ] repeated card / candidate に常時 blur を使わない。
- [ ] scroll 中に Paint flashing が grid 全体へ広がらない。
- [ ] layout shift が出ないよう image/candidate slot は固定寸法。
- [ ] mobile では 1 column、chat pane hidden、blur radius down。
- [ ] grid container に `will-change` を常時付けない。

### Bulk Footer

- [ ] fixed footer が keyboard focus target を隠さない。workspace に `scroll-padding-bottom` を設ける。
- [ ] selected count、download、insert の target size は 24x24 以上。
- [ ] insert は採用操作として label を明確にする。色だけで primary にしない。
- [ ] disabled は opacity だけでなく disabled attribute / helper text / icon state を併用。
- [ ] progress は footer height を変えず、reduced motion でも意味が残る。
- [ ] footer glass は許可。ただし background alpha は高めにして操作 label を守る。

### Right Chat Pane

- [ ] pane shell / header / composer は glass 可。message body は solid。
- [ ] assistant / user bubble の差は色だけにしない。alignment、avatar/label、border tone を併用。
- [ ] chat text contrast は 4.5:1。小さい metadata は薄くしすぎない。
- [ ] composer textarea/input は prompt editor と同じ readable surface。
- [ ] send button は icon-only なら `aria-label` 必須、focus-visible 必須。
- [ ] chat scroll 中に message bubble blur が repaint を増やさない。
- [ ] generation logs を chat に流さない。状態は left card に置く。

### Modal / Approval UI

- [ ] modal body は opaque。backdrop は暗くしてよいが本文背面を透明にしない。
- [ ] focus trap、initial focus、Escape、return focus を確認する。
- [ ] focus not obscured。modal footer や sticky action が focused control を隠さない。
- [ ] destructive / overwrite は icon + label + confirmation copy。
- [ ] forced colors で border、button、selected row が system colors になる。

## Test Plan

### Manual Accessibility

- [ ] Keyboard only: topbar -> controls -> grid card -> candidate -> bulk footer -> chat composer の順序が自然。
- [ ] `:focus-visible`: すべての interactive element に visible ring。
- [ ] Focus not obscured: sticky bulk footer / chat pane / modal が focused target を隠さない。
- [ ] Target size: icon buttons、candidate selectable frame、send button、tabs が 24x24 CSS px 以上。
- [ ] Text contrast: prompt textarea、chat message、button label、metadata を通常背景と busy state で確認。
- [ ] Non-text contrast: selected rim、focus ring、error/warning rim、icons を 3:1 目標で確認。
- [ ] Color independence: grayscale view または color-blindness simulator で selected / failed / disabled が分かる。
- [ ] 200% zoom: text が重ならず、chat pane が workspace を潰さない。

### Preference / System Mode

- [ ] `prefers-reduced-motion: reduce`: sweep / shine / morph が止まる。
- [ ] `prefers-reduced-transparency: reduce`: backdrop blur が消え、opaque surface になる。
- [ ] `prefers-contrast: more`: border / outline / message surface が強くなる。
- [ ] `forced-colors: active`: system colors で focus、selected、error が見える。
- [ ] `@supports not backdrop-filter`: solid fallback で layout と readability が維持される。
- [ ] mobile viewport: chat pane hidden、grid 1 column、blur count / radius reduced。

### Performance

- [ ] Chrome DevTools Rendering > Paint flashing: scroll で grid 全体が常時 repaint しない。
- [ ] Chrome DevTools Rendering > Layer borders: candidate ごとに過剰 layer が増えていない。
- [ ] FPS overlay: grid scroll、candidate hover、bulk footer operation で visible jank がない。
- [ ] Performance trace: long task、recalculate style、paint、rasterize の増加を glass 変更前後で比較。
- [ ] Memory: candidate 多数表示時に GPU memory / layer count が増えすぎない。
- [ ] CPU throttling / mobile emulation: blur radius down でも操作可能。
- [ ] Reduced glass feature flag: all glass off で機能が同じ。

### Visual Regression

- [ ] default dark mode screenshot。
- [ ] reduced transparency screenshot。
- [ ] forced colors screenshot。
- [ ] selected + focus candidate screenshot。
- [ ] failed candidate screenshot。
- [ ] long prompt editing screenshot。
- [ ] long chat conversation screenshot。
- [ ] mobile 375px screenshot。

## Practical CSS Contract

```css
:root {
  --toc-surface-solid: rgba(16, 20, 23, .96);
  --toc-surface-message: rgba(18, 22, 25, .94);
  --toc-surface-glass: rgba(23, 27, 31, .72);
  --toc-surface-glass-strong: rgba(23, 27, 31, .84);
  --toc-line: rgba(255, 255, 255, .18);
  --toc-line-strong: rgba(255, 255, 255, .32);
  --toc-text: rgba(255, 255, 255, .92);
  --toc-text-muted: rgba(255, 255, 255, .66);
  --toc-rim-primary: #8ee8ff;
  --toc-rim-chat: #f6d365;
  --toc-rim-error: #ff6b6b;
}

.toc-glass-fixed {
  background:
    linear-gradient(180deg, rgba(255,255,255,.10), rgba(255,255,255,.035)),
    var(--toc-surface-glass);
  border: 1px solid var(--toc-line);
  backdrop-filter: blur(16px) saturate(130%);
  -webkit-backdrop-filter: blur(16px) saturate(130%);
}

.toc-readable {
  background: var(--toc-surface-solid);
  color: var(--toc-text);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

.toc-focusable:focus-visible {
  outline: 2px solid var(--toc-rim-chat);
  outline-offset: 2px;
  box-shadow: 0 0 0 4px rgba(246, 211, 101, .20);
}

.candidate.is-selected {
  border: 2px solid var(--toc-rim-primary);
}

@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .toc-glass-fixed {
    background: var(--toc-surface-glass-strong);
  }
}
```

## Acceptance Gate

Glass 変更は、次を満たさない限り merge しない。

1. prompt textarea、chat message、button label が WCAG AA contrast を満たす。
2. selected / failed / disabled / focus が色なしでも区別できる。
3. reduced motion、reduced transparency、forced colors の fallback がある。
4. candidate image そのものに opacity / blur / filter をかけていない。
5. repeated grid card に常時 `backdrop-filter` を入れていない。
6. Chrome DevTools で scroll 中の広範囲 repaint と過剰 layer を確認している。
7. sticky bulk footer が keyboard focus を隠していない。
8. mobile で chat pane を隠しても workspace の操作順序が保たれる。

## Final Rule Set

- Glass は `topbar`、`controls`、`bulkFooter`、`chatPane` shell/header/composer、selected candidate rim に限定する。
- Prompt と chat message は readable surface。長文領域に glass を使わない。
- Candidate image は絶対に加工しない。額縁と状態 label だけを加工する。
- State は color + shape + label + keyboard semantics で表す。
- User preference mode では glass を諦め、情報構造を残す。
- Performance は見た目の主観ではなく、Paint flashing、Layer borders、FPS、trace で測る。
- 最高峰の Liquid Glass は「透明にする量」ではなく、「透明にしない判断」の精度で決まる。
