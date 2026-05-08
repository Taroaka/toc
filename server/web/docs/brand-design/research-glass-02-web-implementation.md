# Web Glass Implementation Research for `/image_gen`

## Purpose

ToC `/image_gen` で使える Liquid Glass / glassmorphism / refraction の現実的な Web 実装パターンを整理する。

この調査の焦点は「最高峰の見た目」ではなく、生成候補画像、prompt、reference、repo insertion を高速に比較する制作 UI で、どの表現なら採用できるかを判断することに置く。

## Executive Decision

`/image_gen` の glass 表現は 3 層に分ける。

1. **Core UI: CSS backdrop glass**
   - 採用する。
   - `topbar`、control rail、bulk footer、chat pane header など固定 UI に限定する。
   - `backdrop-filter: blur() saturate()` と半透明 background、rim border、inner highlight、shadow で「層」を作る。

2. **Accent UI: SVG filter / displacement**
   - 標準 UI には入れない。
   - selected rim、短い hover shine、実験用 preview など、失敗しても業務に影響しない場所だけに限定する。
   - SVG `feDisplacementMap` は画像や prompt 本文の背面には使わない。

3. **Showcase / Lab: Canvas or WebGL refraction**
   - `/image_gen` の通常画面には入れない。
   - 将来、brand demo、loading vignette、背景の 1 箇所だけに使う候補として残す。
   - candidate grid、prompt editor、bulk footer のような頻繁に再描画される実務面へは持ち込まない。

結論として、ToC の「現実的な最高峰」は shader ではなく、**CSS glass を堅く実装し、アクセントだけを opt-in で拡張する material system** である。

## Source Map

一次/公式/信頼できるドキュメントを優先して参照した。

| Area | Sources | Relevance |
|---|---|---|
| Liquid Glass concept | Apple Developer: Liquid Glass, Adopting Liquid Glass, WWDC25 "Meet Liquid Glass", HIG Materials | material は blur だけでなく lensing、highlight、shadow、adaptive contrast、interaction feedback の統合だと確認 |
| CSS backdrop | MDN `backdrop-filter`, MDN `filter`, MDN `@media (prefers-reduced-transparency)` | 実装構文、半透明 background 必須、互換性、透明度低減対応 |
| Browser compatibility | MDN compatibility tables, web.dev Baseline, Can I Use `css-backdrop-filter` | `backdrop-filter` は 2024 Baseline だが古い環境向け fallback が必要 |
| SVG filters | MDN `feDisplacementMap`, MDN `filter`, W3C Filter Effects Module Level 1 | displacement の公式モデルと CSS/SVG filter の境界確認 |
| Canvas/WebGL | MDN WebGL API, three.js docs/examples, PixiJS DisplacementFilter docs | shader/refraction は可能だが UI コアには重い |
| Performance | web.dev rendering performance, Chrome DevTools performance docs, MDN CSS properties | blur/filter は paint/compositing cost が高く、固定面と小面積に制限すべき |
| Field examples | Frontend Masters "Liquid Glass on the Web", kube.io "Liquid Glass in the Browser", Shuding liquid-glass repo, Inspira UI Liquid Glass, Lucky Graphics tutorial | Web での実装実例。ただし production 採用判断では公式情報より下位に置く |

## What Liquid Glass Means on Web

Apple の Liquid Glass は単なる frosted panel ではない。Web に翻訳すると、最低限次の 5 要素へ分解できる。

- **Backdrop sampling**: 背後の pixel をぼかす、彩度を上げる、明度差を作る。
- **Refraction hint**: 縁や hover 時に少しだけ背景が曲がったように見える。
- **Specular highlight**: 光沢の線、内側の白い反射、状態 rim。
- **Depth separation**: shadow と z-index で「どの層を触っているか」を示す。
- **Adaptive contrast**: 背景が明るいときも文字や icon が読める fallback を持つ。

ToC では refraction の物理忠実度より、画像比較を邪魔しない contrast と layout stability を優先する。

## CSS Backdrop Filter

### Capability

`backdrop-filter` は要素の背後にある描画結果へ blur、brightness、contrast、saturate などの filter を適用する。効果を見せるには対象要素自体に半透明 background が必要になる。

現在の主要ブラウザでは実用可能だが、古いブラウザや一部の埋め込み WebView では fallback が必要。MDN と web.dev Baseline では、`backdrop-filter` は 2024 年時点で Baseline Newly available と扱われている。

### Adopted Pattern

`/image_gen` では CSS glass を標準表現にする。

```css
.toc-glass {
  background:
    linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.10),
      rgba(255, 255, 255, 0.035)
    ),
    rgba(23, 27, 31, 0.68);
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    0 18px 42px rgba(0, 0, 0, 0.30);
  backdrop-filter: blur(16px) saturate(132%);
  -webkit-backdrop-filter: blur(16px) saturate(132%);
}

@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .toc-glass {
    background: rgba(23, 27, 31, 0.94);
  }
}

@media (prefers-reduced-transparency: reduce) {
  .toc-glass {
    background: rgba(16, 20, 23, 0.96);
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
}
```

### ToC Rules

- `topbar`: `blur(12px) saturate(125%)`
- control rail: `blur(14px) saturate(130%)`
- bulk footer: `blur(16px) saturate(132%)`
- chat pane shell/header: `blur(16px) saturate(130%)`
- small selected chip: `blur(8px) saturate(115%)`
- prompt textarea: `backdrop-filter: none`
- candidate image and image preview: `backdrop-filter: none`
- modal/dialog text body: opacity high enough to read, preferably no strong backdrop blur

### Avoid

- `blur(24px+)` on large scrolling panels.
- Applying `opacity` to a parent container that also contains glass children; use `rgba()` backgrounds instead.
- Glass on every card in a dense grid.
- Transparent textarea or long prompt blocks.
- Glass directly over candidate images where color judgment matters.

## SVG Filter and Displacement

### Capability

SVG filters can combine `feGaussianBlur`, `feColorMatrix`, `feSpecularLighting`, `feDisplacementMap`, `feTurbulence`, and CSS `filter: url(#id)` to produce refractive-looking edges.

`feDisplacementMap` displaces pixels by sampling channels from a second input image. This is the closest standardized Web primitive to a 2D "bent glass" effect without WebGL.

### Practical Constraint

SVG filters are reliable for filtering the element itself. They are less reliable as a production-grade way to displace the **backdrop behind HTML UI** across browsers.

Field examples use creative combinations such as hidden SVG maps, CSS filters, backdrop layers, and pointer-driven masks. They are valuable for demos, but ToC should not depend on them for core controls.

### Allowed Pattern: Rim-only Distortion

Use SVG filter only on a decorative overlay, not on content.

```html
<svg aria-hidden="true" class="glass-filter-defs">
  <filter id="toc-rim-displace" x="-20%" y="-20%" width="140%" height="140%">
    <feTurbulence
      type="fractalNoise"
      baseFrequency="0.018 0.045"
      numOctaves="1"
      seed="7"
      result="noise"
    />
    <feDisplacementMap
      in="SourceGraphic"
      in2="noise"
      scale="5"
      xChannelSelector="R"
      yChannelSelector="G"
    />
  </filter>
</svg>
```

```css
.candidate-frame.is-selected::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  border-radius: 8px;
  border: 1px solid rgba(142, 232, 255, 0.72);
  filter: url("#toc-rim-displace");
  opacity: 0.72;
}
```

### ToC Rules

- Use displacement only on pseudo-elements or isolated highlight layers.
- Keep `scale` low, generally `2` to `6`.
- Do not animate `baseFrequency` continuously in the main grid.
- Do not apply SVG filters to prompt text, candidate images, or large scroll containers.
- Always provide the same state through border/icon/text so the UI remains usable if the filter is unsupported or disabled.

## Canvas and WebGL Refraction

### Capability

Canvas/WebGL can render real-time displacement, normal maps, environment maps, post-processing blur, chromatic aberration, caustics, and high-quality refraction. Three.js, PixiJS, OGL, and custom shaders can all produce glass effects well beyond CSS/SVG.

Typical techniques:

- Render the background or scene into a texture, then sample it through a normal/displacement map.
- Use a shader to offset UV coordinates near edges.
- Use `MeshPhysicalMaterial` transmission/refraction in three.js for 3D glass objects.
- Use PixiJS `DisplacementFilter` for 2D sprite/canvas displacement.
- Use offscreen canvas or render targets to avoid reading DOM pixels repeatedly.

### Practical Constraint

For `/image_gen`, WebGL refraction has a poor cost/benefit ratio in the core UI:

- DOM capture or background texture sync is expensive and fragile.
- Multiple WebGL contexts can exhaust browser limits.
- Large canvas over a dense grid increases GPU memory and compositing work.
- Accessibility and reduced transparency handling become custom work.
- It complicates screenshot testing and deterministic visual regression.

### Allowed Pattern: Single Background Lab Layer

If used later, WebGL should be limited to a single non-interactive background or demo pane:

- one canvas for the whole app shell, not per card
- static or low-frequency animation
- disabled under `prefers-reduced-motion` or `prefers-reduced-transparency`
- no dependency on candidate image pixels
- no overlap with text-heavy regions
- fallback to CSS background/grid

## Browser Compatibility

| Feature | Current practical status | ToC decision |
|---|---|---|
| `backdrop-filter` | Broad modern support; Baseline Newly available in 2024; old browsers/WebViews still need fallback | Use for fixed UI with `@supports` fallback |
| `-webkit-backdrop-filter` | Still useful for Safari compatibility habits and older code paths | Include alongside unprefixed property |
| CSS `filter` | Mature for filtering element content; not a replacement for backdrop blur | Use for icons/highlight layers only |
| SVG `feDisplacementMap` | Standard SVG filter primitive; element filtering is broadly usable | Use only on decorative overlays |
| CSS `filter: url(#svg-filter)` | Works for element filtering; cross-browser details and coordinate systems can be tricky | Avoid for essential state |
| Backdrop displacement via SVG/CSS hacks | Demo-quality, browser-sensitive | Do not adopt in production UI |
| Canvas 2D displacement | Possible but custom and CPU/GPU dependent | Avoid except generated static assets |
| WebGL refraction | Powerful and widely available on capable devices; context/device limits remain | Lab/showcase only, not default UI |
| `prefers-reduced-transparency` | Supported as an accessibility media feature in modern engines | Use as a hard fallback trigger |

## Performance Model

Glass is expensive because the browser must sample and process pixels behind the element. The cost grows with area, blur radius, animation, overlap, and scroll invalidation.

### Budget

| UI area | Max effect | Reason |
|---|---|---|
| topbar | static `blur(12px)` | small fixed area |
| controls | static `blur(14px)` | small to medium area |
| bulk footer | static `blur(16px)` | fixed, high-value operation layer |
| chat pane | static shell blur; message bodies mostly solid | readable text and continuous scroll |
| grid cards | no backdrop blur by default | many repeated items |
| candidate images | no filter/opacity | visual evaluation integrity |
| hover/selected overlays | short transition, border/box-shadow first | state feedback without repaint-heavy distortion |

### Implementation Guardrails

- Keep glass surfaces fixed or low count.
- Avoid animating `backdrop-filter`, `filter`, and large `box-shadow`.
- Animate `opacity` and `transform` on small highlight layers instead.
- Use `contain: paint` only after verifying it does not break the desired backdrop sampling.
- Avoid nested glass surfaces; prefer solid content panels inside a glass shell.
- Test slow machines with Chrome DevTools Performance and Safari Web Inspector, not only a high-end desktop.
- Measure scroll jank in the prompt grid before adding any filter to repeated cards.

## Recommended Component Pattern

### Material Tokens

```css
:root {
  --glass-bg: rgba(23, 27, 31, 0.68);
  --glass-bg-strong: rgba(23, 27, 31, 0.82);
  --glass-solid: rgba(16, 20, 23, 0.96);
  --glass-line: rgba(255, 255, 255, 0.14);
  --glass-line-strong: rgba(255, 255, 255, 0.24);
  --glass-rim-primary: #8ee8ff;
  --glass-rim-chat: #f6d365;
  --glass-shadow: 0 18px 42px rgba(0, 0, 0, 0.30);
}
```

### Layer Classes

```css
.glass-nav {
  background: var(--glass-bg);
  border: 1px solid var(--glass-line);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.22);
  backdrop-filter: blur(12px) saturate(125%);
  -webkit-backdrop-filter: blur(12px) saturate(125%);
}

.glass-dock {
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-line);
  box-shadow: 0 -18px 40px rgba(0, 0, 0, 0.34);
  backdrop-filter: blur(16px) saturate(132%);
  -webkit-backdrop-filter: blur(16px) saturate(132%);
}

.content-paper {
  background: var(--glass-solid);
  border: 1px solid rgba(255, 255, 255, 0.10);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.24);
}

.state-rim-selected {
  border-color: var(--glass-rim-primary);
  box-shadow:
    0 0 0 1px rgba(142, 232, 255, 0.48),
    0 0 24px rgba(142, 232, 255, 0.16);
}
```

### Accessibility Fallback

```css
@media (prefers-reduced-transparency: reduce) {
  .glass-nav,
  .glass-dock {
    background: var(--glass-solid);
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .glass-shine,
  .glass-rim-animated {
    animation: none;
    transition-duration: 0.01ms;
  }
}
```

## Libraries and Examples

| Library / Example | Trust level | Useful for | ToC decision |
|---|---:|---|---|
| MDN CSS/SVG/WebGL docs | High | syntax, compatibility, standards-aligned behavior | Primary reference |
| Apple Liquid Glass docs/videos | High | material intent and interaction hierarchy | Design reference, not Web implementation contract |
| three.js | High | 3D glass, transmission/refraction demos | Only future brand demo or isolated canvas |
| PixiJS DisplacementFilter | High | 2D displacement in canvas/WebGL | Reference only; not core UI |
| Frontend Masters Liquid Glass article | Medium | practical Web tradeoffs and browser caveats | Use as implementation inspiration |
| kube.io CSS/SVG refraction article | Medium | SVG/CSS displacement technique | Experimental only |
| Shuding liquid-glass repo | Medium | modern React/WebGL-style Liquid Glass experiments | Do not vendor into core UI without audit |
| Inspira UI Liquid Glass | Medium | component API and visual recipes | Visual reference only |
| Lucky Graphics tutorial | Low/Medium | glassmorphism recipe | Pattern inspiration, not authority |

## Adopt for ToC

- CSS `backdrop-filter` on fixed, low-count UI layers.
- Strong fallback backgrounds through `@supports` and `prefers-reduced-transparency`.
- Solid prompt editor surfaces.
- Candidate image integrity: no opacity, no blur, no displacement on images.
- State expressed by border, icon, text, and layout-stable rim.
- Small specular highlights using pseudo-elements.
- SVG displacement only for non-essential rim accents.
- Performance testing before increasing blur radius or area.

## Avoid for ToC

- WebGL per card.
- DOM-to-canvas capture for live UI refraction.
- Full-screen animated distortion behind working text.
- Applying glass to prompt textareas.
- Heavy SVG filters on scroll containers.
- Continuous animated turbulence in the main grid.
- Reliance on color/shine alone for selected, failed, or destructive states.
- White frosted UI that reduces contrast against image candidates.
- Apple UI mimicry that ignores ToC's production workflow.

## Validation Checklist

Before shipping a glass change in `/image_gen`, verify:

- `backdrop-filter` unsupported fallback still reads correctly.
- `prefers-reduced-transparency: reduce` disables glass.
- `prefers-reduced-motion: reduce` disables shimmer/distortion animation.
- Prompt textarea contrast remains stable.
- Candidate image colors are not altered.
- Grid scroll remains smooth with a realistic number of request cards.
- Safari, Chrome, and Firefox render the same hierarchy even if the effect strength differs.
- Screenshot tests do not become noisy because of animated filter effects.

## References

- Apple Developer Documentation: Liquid Glass  
  https://developer.apple.com/documentation/TechnologyOverviews/liquid-glass
- Apple Developer Documentation: Adopting Liquid Glass  
  https://developer.apple.com/documentation/TechnologyOverviews/adopting-liquid-glass
- Apple Developer: Meet Liquid Glass - WWDC25  
  https://developer.apple.com/videos/play/wwdc2025/219/
- Apple Human Interface Guidelines: Materials  
  https://developer.apple.com/design/human-interface-guidelines/materials
- MDN: `backdrop-filter`  
  https://developer.mozilla.org/en-US/docs/Web/CSS/backdrop-filter
- MDN: CSS `filter`  
  https://developer.mozilla.org/en-US/docs/Web/CSS/filter
- MDN: `prefers-reduced-transparency`  
  https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-transparency
- MDN: SVG `feDisplacementMap`  
  https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/feDisplacementMap
- MDN: WebGL API  
  https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API
- W3C: Filter Effects Module Level 1  
  https://www.w3.org/TR/filter-effects-1/
- web.dev: Baseline  
  https://web.dev/baseline
- web.dev: Rendering performance  
  https://web.dev/articles/rendering-performance
- Chrome Developers: Analyze runtime performance  
  https://developer.chrome.com/docs/devtools/performance
- Can I Use: CSS backdrop-filter  
  https://caniuse.com/css-backdrop-filter
- three.js documentation  
  https://threejs.org/docs/
- three.js examples: WebGL materials physical transmission  
  https://threejs.org/examples/#webgl_materials_physical_transmission
- PixiJS: DisplacementFilter  
  https://pixijs.download/release/docs/filters.DisplacementFilter.html
- Frontend Masters Blog: Liquid Glass on the Web  
  https://frontendmasters.com/blog/liquid-glass-on-the-web/
- kube.io: Liquid Glass in the Browser: Refraction with CSS and SVG  
  https://kube.io/blog/liquid-glass-css-svg/
- Shuding: liquid-glass  
  https://github.com/shuding/liquid-glass
- Inspira UI: Liquid Glass Effect  
  https://v2.inspira-ui.com/docs/en/components/visualization/liquid-glass
- Lucky Graphics: Liquid Glass CSS glassmorphism tutorial  
  https://lucky.graphics/learn/liquid-glass-css-glassmorphism-tutorial/
