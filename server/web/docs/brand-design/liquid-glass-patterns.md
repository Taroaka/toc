# Liquid Glass Patterns for `/image_gen`

## Purpose

`/image_gen` Web App の Liquid Glass は、Apple 風の見た目をそのまま模倣するためではなく、
「透明なグラスにユーザーの指示で何層にも広がる美術館」という世界観を、制作判断に使える UI 階層へ翻訳するために使う。

この画面の主役は candidate image、prompt、reference、採用操作である。
Liquid Glass は背景装飾ではなく、ユーザーが「いまどの層を触っているか」を理解するための material system として扱う。

## Research Summary

参照した一次/準一次情報と実装例:

- Apple Developer Documentation: Liquid Glass  
  https://developer.apple.com/documentation/TechnologyOverviews/liquid-glass
- Apple Human Interface Guidelines: Materials  
  https://developer.apple.com/design/human-interface-guidelines/materials
- Apple Developer: Meet Liquid Glass - WWDC25  
  https://developer.apple.com/videos/play/wwdc2025/219/
- Apple Developer Documentation: Adopting Liquid Glass  
  https://developer.apple.com/documentation/TechnologyOverviews/adopting-liquid-glass
- Apple Developer Documentation: Applying Liquid Glass to custom views  
  https://developer.apple.com/documentation/SwiftUI/Applying-Liquid-Glass-to-custom-views
- Apple Developer Documentation: SwiftUI `glassEffect(_:in:)`  
  https://developer.apple.com/documentation/swiftui/view/glasseffect%28_%3Ain%3A%29
- MDN: `backdrop-filter`  
  https://developer.mozilla.org/en-US/docs/Web/CSS/backdrop-filter
- MDN: `prefers-reduced-transparency`  
  https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-transparency
- MUI: CSS theme variables overview  
  https://mui.com/material-ui/customization/css-theme-variables/overview/
- MUI: CSS theme variables usage  
  https://mui.com/material-ui/customization/css-theme-variables/usage/
- PhotoshopVIP: Apple の新 UI「Liquid Glass」とは？Web で再現できる最新 UI 完全ガイド  
  https://photoshopvip.net/166930
- Frontend Masters Blog: Liquid Glass on the Web  
  https://frontendmasters.com/blog/liquid-glass-on-the-web/
- kube.io: Liquid Glass in the Browser: Refraction with CSS and SVG  
  https://kube.io/blog/liquid-glass-css-svg/
- Inspira UI: Liquid Glass Effect  
  https://v2.inspira-ui.com/docs/en/components/visualization/liquid-glass
- Lucky Graphics: Liquid Glass CSS glassmorphism tutorial  
  https://lucky.graphics/learn/liquid-glass-css-glassmorphism-tutorial/

主要な示唆:

- Apple HIG は Liquid Glass を content layer ではなく controls/navigation layer に限定する方針を示している。ToC でも prompt 本文や candidate 画像そのものをガラス化しない。
- Apple の説明では、Liquid Glass は lensing、highlight、shadow、interaction feedback、adaptive contrast が一体になった material である。CSS では完全再現よりも「層」「縁」「光」「状態」の再現を優先する。
- PhotoshopVIP 記事は、Web では `backdrop-filter`、半透明面、反射、丸み、シャドウ、SVG filter などで再現できる一方、可読性低下・古いブラウザ・使いすぎに注意が必要だと整理している。ToC ではこの注意点を実装ルールに昇格する。
- Web 実装例では SVG displacement / WebGL / shader で屈折を強められるが、互換性と負荷が高い。通常 UI は CSS glass、hero 的な一部だけ advanced effect の候補にする。
- MUI 7 は CSS theme variables と channel token を使えるため、透明色を `rgba(${theme.vars.palette.*Channel} / alpha)` で管理しやすい。

## Governing Pattern

Liquid Glass は `/image_gen` の z 軸を作る。

1. `shell`: 美術館の暗い展示空間。最奥の非ガラス層。
2. `topbar`: run を選ぶ案内板。薄い navigation glass。
3. `controls`: asset / scene、candidate count、一括生成の操作卓。glass dock。
4. `promptCard`: 作品キャプションと制作指示。基本は安定した dark surface、状態時のみ rim glass。
5. `candidateFrame`: 展示額。画像自体は透明化せず、周囲の frame だけをガラス化。
6. `bulkFooter`: 採用・搬出の docking layer。最も明確な操作状態を持つ。
7. `chatPane`: curator / Codex との対話室。workspace と別色の glass layer。

## Design Tokens

### Color

既存の暗色管制卓トーンを維持し、Liquid Glass は黒いガラス、冷たい glass cyan の反射、暖かい museum amber の相談室光で作る。
全体を白い frosted UI に寄せない。

| Token | Value | Usage |
|---|---:|---|
| `--lg-bg` | `#0e1113` | 最奥の app background |
| `--lg-bg-grid-cyan` | `rgba(142, 232, 255, 0.035)` | 背景 grid の低彩度 accent |
| `--lg-bg-grid-white` | `rgba(255, 255, 255, 0.028)` | 背景 grid の補助線 |
| `--lg-surface-solid` | `rgba(16, 20, 23, 0.96)` | prompt textarea / stable editor |
| `--lg-surface-card` | `rgba(18, 22, 25, 0.90)` | prompt card 通常面 |
| `--lg-surface-glass` | `rgba(23, 27, 31, 0.64)` | topbar / controls / footer |
| `--lg-surface-glass-strong` | `rgba(23, 27, 31, 0.78)` | hover / focus-within |
| `--lg-surface-clear` | `rgba(255, 255, 255, 0.055)` | selected frame の反射 |
| `--lg-line` | `rgba(255, 255, 255, 0.14)` | 通常 hairline |
| `--lg-line-strong` | `rgba(255, 255, 255, 0.24)` | hover hairline |
| `--lg-rim-primary` | `#8ee8ff` | selected / generate / insert |
| `--lg-rim-chat` | `#f6d365` | chat pane / assistant |
| `--lg-rim-error` | `#ff6b6b` | failed / invalid |
| `--lg-rim-warning` | `#ffd166` | missing reference / no output |
| `--lg-text` | `rgba(255, 255, 255, 0.92)` | primary text |
| `--lg-text-muted` | `rgba(255, 255, 255, 0.64)` | metadata / path |
| `--lg-text-faint` | `rgba(255, 255, 255, 0.46)` | disabled / helper |

### Transparency

透明度はコンポーネントの役割で固定する。

| Layer | Background alpha | Rule |
|---|---:|---|
| navigation glass | `0.58 - 0.68` | `topbar`、小さい control group |
| dock glass | `0.72 - 0.86` | `bulkFooter`、重要操作 |
| content card | `0.88 - 0.96` | prompt card、textarea、message body |
| clear media overlay | `0.04 - 0.10` | 画像上の短い selected chip のみ |

長文テキストの背面は `rgba(16, 20, 23, 0.88)` より薄くしない。
candidate 画像の色評価を妨げるため、画像そのものに opacity をかけない。

### Backdrop Filter

基本値:

```css
.lg-glass {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.10), rgba(255, 255, 255, 0.035)),
    rgba(23, 27, 31, 0.64);
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    0 18px 42px rgba(0, 0, 0, 0.30);
  backdrop-filter: blur(18px) saturate(135%);
  -webkit-backdrop-filter: blur(18px) saturate(135%);
}
```

使い分け:

- `blur(10px) saturate(120%)`: chip、small button、candidate selected chip。
- `blur(14px) saturate(130%)`: `topbar`、`controls`。
- `blur(18px) saturate(135%)`: `bulkFooter`、right chat head。
- `blur(0)`: prompt textarea、candidate image、error message。

MDN の説明どおり、`backdrop-filter` は背後の pixel に効くため、対象要素は半透明背景を持つ必要がある。
親要素に `opacity < 1`、`filter`、`mask`、`will-change` などがあると backdrop root が変わり、期待した背景がぼけないことがある。
ToC では glass layer 自体に `opacity` を使わず、`background: rgba()` で透明度を管理する。

### Border

Liquid Glass の輪郭は「枠線 + 内側 highlight + 状態 rim」の 3 層で作る。

- 通常: `1px solid rgba(255,255,255,0.14)`
- hover: `1px solid rgba(255,255,255,0.24)`
- focus: `1px solid #f6d365` + `box-shadow: 0 0 0 3px rgba(246,211,101,0.20)`
- selected: `1px solid #8ee8ff` + `box-shadow: 0 0 0 1px rgba(142,232,255,0.48), 0 0 24px rgba(142,232,255,0.16)`
- error: `1px solid #ff6b6b` + text message。赤い半透明面だけにしない。

### Shadow

Apple の説明では shadow は背後の内容からの分離と接地感を担う。
ToC では影を強くしすぎると展示画像の評価を邪魔するため、層ごとに抑制する。

| Component | Shadow |
|---|---|
| `topbar` | `0 10px 30px rgba(0,0,0,0.22)` |
| `controls` | `0 12px 30px rgba(0,0,0,0.20)` |
| `promptCard` | `0 16px 36px rgba(0,0,0,0.24)` |
| `candidate.selected` | `0 0 0 1px rgba(142,232,255,0.48), 0 18px 34px rgba(0,0,0,0.34)` |
| `bulkFooter` | `0 -18px 40px rgba(0,0,0,0.34)` |
| `chatPane` | `-16px 0 40px rgba(0,0,0,0.26)` |

## Component Patterns

### Shell

役割: 透明な美術館の最奥。

- 背景は暗色のままにする。
- grid texture は現在より少し弱め、glass layer の背後でだけ見える程度にする。
- 背景に大きな gradient orb や装飾 blob は置かない。

CSS:

```css
.shell {
  background:
    linear-gradient(90deg, rgba(142, 232, 255, 0.035) 1px, transparent 1px),
    linear-gradient(0deg, rgba(255, 255, 255, 0.028) 1px, transparent 1px),
    #0e1113;
  background-size: 28px 28px;
}
```

### Topbar

役割: run selection と reload の navigation glass。

- `AppBar` を使う場合も elevation は 0 にし、CSS の glass shadow で層を作る。
- run selector は可読性優先で `rgba(16,20,23,0.82)` を保つ。
- reload icon button は hover 時だけ rim を出す。

状態:

- idle: 薄い glass。
- loading: topbar 下端に `LinearProgress` を 2px で固定。
- error: topbar 全体を赤くせず、selector 下に短い error text を出す。

### Controls

役割: asset / scene、candidate count、bulk generation count の control rail。

- `Tabs` は capsule に寄せるが、巨大な丸みにはしない。既存の 8px radius を維持する。
- active tab は `#8ee8ff` の text + bottom indicator ではなく、薄い filled capsule + rim にする。
- `Slider` は track を glass の下に沈めず、つまみだけを clear glass として扱う。

MUI 対応:

- `MuiTabs` / `MuiTab` の `styleOverrides` で `minHeight: 40`、`borderRadius: 8`。
- `MuiSlider.thumb` に `boxShadow: inset 0 1px 0 rgba(255,255,255,.28), 0 0 0 6px rgba(142,232,255,.10)`。
- `FormControl` / `Select` は menu surface を不透明寄りにし、menu item 背面を透明にしすぎない。

### Prompt Card

役割: 作品の制作指示と metadata をまとめる展示キャプション。

- 通常時は glass ではなく `surface-card`。
- hover / focus-within / generating / selected candidate あり、のときだけ rim と内側 highlight を増やす。
- prompt textarea は `backdrop-filter` を使わない。長文編集は安定した dark paper がよい。
- path、lane、id は `text-muted`。色だけで状態を表現しない。

状態:

| State | Visual |
|---|---|
| idle | `background: rgba(18,22,25,0.90)`、弱い border |
| hover | border を少し明るくする。card は浮かせすぎない |
| focus-within | chat 以外は primary rim ではなく `#f6d365` focus ring |
| generating | card 上端に細い light sweep。layout size は固定 |
| failed | card は通常面を維持し、candidate slot に error rim と text |

### Reference Selector

役割: 参照画像を棚から選ぶ drawer。

- dropdown option は thumbnail + filename。既存仕様を維持。
- selected chip は glass にしすぎず、`rgba(142,232,255,0.12)` + primary border。
- thumbnail は透明化しない。画像内容を正確に見ることを優先する。
- missing reference は warning rim と短い message。

アクセシビリティ:

- chip は色だけでなく check icon または border weight で selected を示す。
- option row の hover/focus は `rgba(255,255,255,0.08)` 以上。

### Candidate Frame

役割: 美術館の額縁。Liquid Glass の主戦場。

- 画像自体はガラス化しない。
- frame、selected rim、label chip、loading placeholder にだけ glass を使う。
- 16:9 aspect ratio は固定し、loading/error/empty でも崩さない。
- selected candidate は一目で分かる強い rim を許可する。

CSS:

```css
.candidate {
  background:
    linear-gradient(180deg, rgba(255,255,255,0.055), rgba(255,255,255,0.018)),
    rgba(16, 20, 23, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 8px;
}

.candidate.selected {
  border-color: #8ee8ff;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.18),
    0 0 0 1px rgba(142, 232, 255, 0.48),
    0 0 24px rgba(142, 232, 255, 0.16);
}
```

candidate 内の状態:

- empty: 暗い固定枠 + faint icon。
- generating: `LinearProgress` か sweep。画像枠の height は変えない。
- failed: error rim + 1 行 message。stack trace は出さない。
- existing: opacity ではなく `Existing` chip と subdued border で区別する。画像の opacity を下げると比較精度が落ちる。

### Bulk Footer

役割: 生成物を外へ出す bottom glass dock。

- 画面内で最も glass らしくしてよいが、操作の contrast を最優先する。
- selected count、download、repo insertion の関係を横並びで固定。
- insert は destructive に近い採用操作なので、primary rim + explicit label。
- disabled は opacity だけでなく、button variant と helper text で分かるようにする。

状態:

- no selection: `Download` / `Insert` は disabled。footer glass は静か。
- selection exists: selected count chip に primary rim。
- inserting: footer 上端に progress、button text は短く `Inserting`。
- inserted: 1.2s 程度の success flash。candidate selected state は消さない。

### Chat Pane

役割: Codex curator との対話層。

- workspace と混ざらないよう、chat rim は `#f6d365`。
- message bubble は透明にしすぎない。文章を読む場所なので `rgba(18,22,25,0.92)` 以上。
- user bubble は primary tint、assistant bubble は chat tint。
- composer は `bulkFooter` より控えめな glass。

## State Expression

状態表現は「色 + 輪郭 + 位置 + motion」の複合にする。

| State | Color | Border | Motion | Notes |
|---|---|---|---|---|
| hover | white alpha +0.08 | line strong | none or 80ms | 画像は動かさない |
| focus-visible | chat blue | 3px outer ring | none | keyboard 操作を最優先 |
| pressed | same | same | `translateY(1px)` | scale は最大 `0.99` |
| generating | primary tint | stable | sweep 1.4s | `prefers-reduced-motion` では static progress |
| selected | primary | primary rim | none | bulk footer と連動 |
| warning | yellow | warning rim | none | missing reference 等 |
| error | red | error rim | none | 背景を赤く塗りすぎない |
| disabled | muted | no glow | none | opacity だけに依存しない |

## Accessibility

必須ルール:

- 本文、prompt、chat message の背面は不透明寄りにする。
- candidate 画像上に長文を重ねない。
- focus ring は `:focus-visible` で必ず出す。
- selected / failed / disabled は色だけでなく border、icon、label でも示す。
- `prefers-reduced-motion: reduce` では sweep、morph、blur animation を止める。
- `prefers-reduced-transparency: reduce` では glass surface を opaque surface へ切り替える。MDN ではこの media feature は限定的サポートなので、未対応ブラウザ向けに通常 contrast も十分確保する。
- `forced-colors: active` では glass background、box-shadow、gradient に依存しない。

CSS:

```css
@media (prefers-reduced-transparency: reduce) {
  .lg-glass,
  .topbar,
  .controls,
  .bulkFooter,
  .chatPane {
    background: #171b1f !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}

@media (forced-colors: active) {
  .candidate.selected,
  .Mui-focusVisible {
    outline: 2px solid CanvasText;
    outline-offset: 2px;
  }
}
```

## Performance

`backdrop-filter` は高コストになりやすい。特に scroll area の大量 card に常時 blur を置くと、candidate grid の操作感が落ちる。

採用ルール:

- 常時 `backdrop-filter` を使うのは `topbar`、`controls`、`bulkFooter`、`chatPane` header/composer まで。
- `promptCard` 全体には通常 `backdrop-filter` を使わない。hover/focus でも border と shadow を増やすだけにする。
- candidate frame は selected / generating の局所だけにする。grid 内の全 candidate に blur を付けない。
- SVG displacement や WebGL refraction は標準 UI に入れない。使うなら first viewport のブランド表現や空 state の 1 箇所に限定し、fallback を必須にする。
- `will-change` は常時付けない。MDN の backdrop root の注意点どおり、意図せず blur 範囲が変わる場合がある。
- scroll container 内の blur は避け、`contain: paint` や固定 size で layout shift を抑える。
- mobile では blur radius を 30% 下げる。例: `18px -> 12px`。

推奨 upper bound:

- 同時に見える glass blur layer: desktop 4 以下、mobile 3 以下。
- blur radius: desktop 18px 以下、mobile 12px 以下。
- animated glass surface: 1 画面 1 箇所まで。

## React + MUI Implementation

### Theme Tokens

MUI 7 の CSS variables を有効にし、Liquid Glass 専用 token を theme に追加する。
透明色は MUI の channel token 形式に合わせ、`rgba(channel / alpha)` を使う。

```ts
import type {} from '@mui/material/themeCssVarsAugmentation';
import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  cssVariables: true,
  palette: {
    mode: 'dark',
    background: {
      default: '#0e1113',
      paper: '#171b1f',
    },
    primary: { main: '#8ee8ff' },
    secondary: { main: '#f6d365' },
    divider: 'rgba(255,255,255,0.12)',
  },
  shape: { borderRadius: 8 },
});
```

TypeScript で独自 token を theme に入れる場合:

```ts
declare module '@mui/material/styles' {
  interface Theme {
    liquidGlass: {
      surface: string;
      surfaceStrong: string;
      line: string;
      primaryRim: string;
      chatRim: string;
    };
  }
  interface ThemeOptions {
    liquidGlass?: Partial<Theme['liquidGlass']>;
  }
}
```

### Reusable `glassSx`

無差別に class を足すのではなく、navigation/control/dock 用に限定する。

```ts
const glassSx = {
  background:
    'linear-gradient(180deg, rgba(255,255,255,.10), rgba(255,255,255,.035)), rgba(23,27,31,.64)',
  border: '1px solid rgba(255,255,255,.14)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,.16), 0 18px 42px rgba(0,0,0,.30)',
  backdropFilter: 'blur(18px) saturate(135%)',
  WebkitBackdropFilter: 'blur(18px) saturate(135%)',
};
```

`Card` には通常 `glassSx` を使わない。

```tsx
<Card
  className="promptCard"
  variant="outlined"
  sx={{
    bgcolor: 'rgba(18,22,25,.90)',
    borderColor: 'rgba(255,255,255,.13)',
    boxShadow: '0 16px 36px rgba(0,0,0,.24)',
    '&:hover': {
      borderColor: 'rgba(255,255,255,.24)',
    },
    '&:focus-within': {
      borderColor: 'secondary.main',
      boxShadow: '0 0 0 3px rgba(246,211,101,.20), 0 16px 36px rgba(0,0,0,.24)',
    },
  }}
>
  ...
</Card>
```

### MUI Component Overrides

対象:

- `MuiButton`: primary contained は solid 寄り、outlined は glass rim。
- `MuiIconButton`: square 8px radius、hover で rim。
- `MuiTextField`: textarea は solid surface、focus ring 明確。
- `MuiAutocomplete`: popup は opaque 寄り。option hover/focus を明確に。
- `MuiTabs`: active tab は filled capsule。
- `MuiLinearProgress`: generating sweep として細く使う。

例:

```ts
components: {
  MuiButton: {
    styleOverrides: {
      root: {
        borderRadius: 8,
        textTransform: 'none',
        fontWeight: 800,
      },
      outlined: {
        borderColor: 'rgba(255,255,255,.18)',
        backgroundColor: 'rgba(255,255,255,.045)',
        backdropFilter: 'blur(10px) saturate(120%)',
      },
      containedPrimary: {
        color: '#0e1113',
        boxShadow: '0 0 0 1px rgba(142,232,255,.32), 0 10px 24px rgba(142,232,255,.16)',
      },
    },
  },
  MuiTextField: {
    styleOverrides: {
      root: {
        '& .MuiOutlinedInput-root': {
          backgroundColor: 'rgba(16,20,23,.96)',
          '&.Mui-focused fieldset': {
            borderColor: '#f6d365',
            boxShadow: '0 0 0 3px rgba(246,211,101,.18)',
          },
        },
      },
    },
  },
}
```

### Advanced Refraction

SVG displacement / WebGL refraction は実装例としては有効だが、ToC の標準操作面には採用しない。

採用してよい場所:

- run 未選択 empty state の背景に 1 箇所。
- app title mark の hover easter interaction。
- `/image_gen` の将来の brand splash。

条件:

- Chromium 以外では frosted fallback。
- text を重ねない。
- `prefers-reduced-motion` と `prefers-reduced-transparency` で停止。
- 1 画面 1 インスタンス。

## Do / Do Not

Do:

- glass は navigation/control/dock の functional layer に使う。
- prompt と chat の可読性を最優先する。
- candidate 画像の frame にだけ glass を使う。
- selected / generating / error は border と label で明確化する。
- MUI theme token と CSS variables で透明色を管理する。

Do not:

- 全 card に `backdrop-filter` を付ける。
- candidate image 自体を opacity や blur で加工する。
- glass on glass を重ねる。
- text の背面を clear glass にする。
- SVG displacement を通常 button や大量 list item に使う。
- 色だけで状態を伝える。

## Component Checklist

- `shell`: dark museum background。grid は控えめ。
- `topbar`: glass navigation。run selector は readable。
- `controls`: compact glass rail。tabs と slider の状態を明確に。
- `promptCard`: solid card + state rim。textarea は no blur。
- `referenceSelector`: thumbnail は無加工。selected chip は border + icon。
- `candidateFrame`: 画像は無加工。frame / selected rim / loading slot に glass。
- `bulkFooter`: bottom glass dock。採用操作を最も明確に。
- `chatPane`: blue-rim glass。bubble は opaque 寄り。
- `accessibility`: reduced transparency / reduced motion / forced colors に対応。
- `performance`: active blur layer を制限し、mobile blur を弱める。
