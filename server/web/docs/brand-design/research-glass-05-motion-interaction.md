# Glass Motion and Interaction Research for `/image_gen`

## Purpose

この文書は、ToC `/image_gen` の glass UI に「静かで高級な動き」を導入するための調査メモである。

目的は派手な glassmorphism を増やすことではない。candidate image、reference image、prompt の比較と読解を主役に保ちながら、hover / focus / press / selection / generation feedback を、状態理解のための最小限の motion grammar に落とす。

## Sources

一次情報・準一次情報を優先した。

- Apple Human Interface Guidelines: Motion  
  https://developer.apple.com/design/human-interface-guidelines/motion
- Apple Human Interface Guidelines: Feedback  
  https://developer.apple.com/design/human-interface-guidelines/feedback
- Apple Human Interface Guidelines: Accessibility  
  https://developer.apple.com/design/human-interface-guidelines/accessibility
- Apple Human Interface Guidelines: Designing for visionOS  
  https://developer.apple.com/design/human-interface-guidelines/designing-for-visionos
- Apple Developer: Principles of spatial design  
  https://developer.apple.com/videos/play/wwdc2023/10072/
- Apple Developer: Design for spatial input  
  https://developer.apple.com/videos/play/wwdc2023/10073/
- Apple Developer: Design considerations for vision and motion  
  https://developer.apple.com/videos/play/wwdc2023/10078/
- Fluent 2 Design System: Motion  
  https://fluent2.microsoft.design/motion
- Material Design: Duration and easing  
  https://m1.material.io/motion/duration-easing.html
- Material Design: Progress and activity  
  https://m1.material.io/components/progress-activity.html
- W3C WCAG 2.2: Pause, Stop, Hide  
  https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide
- WAI-ARIA APG: Developing a Keyboard Interface  
  https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/
- WAI-ARIA APG: Button Pattern  
  https://www.w3.org/WAI/ARIA/apg/patterns/button/
- MDN: `prefers-reduced-motion`  
  https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion
- MDN: Using CSS transitions  
  https://developer.mozilla.org/docs/Web/CSS/CSS_Transitions/Using_CSS_transitions
- React Aria: Quality / Interactions  
  https://react-aria.adobe.com/quality
- Figma Help: Add interactions to an element  
  https://help.figma.com/hc/en-us/articles/31242843431575-Add-interactions-to-an-element
- Figma Help: Create interactive components with variants  
  https://help.figma.com/hc/en-us/articles/360061175334-Create-interactive-components-with-variants
- Adobe Spectrum 2 overview  
  https://s2.spectrum.adobe.com/
- Adobe Spectrum: Action button  
  https://spectrum.adobe.com/page/action-button/
- Adobe Spectrum: Progress bar  
  https://spectrum.adobe.com/page/progress-bar/

## Governing Thought

`/image_gen` の motion は「美しい動き」ではなく「制作判断の邪魔をしない状態説明」である。

高級感は、動きの量ではなく、反応の正確さ、短さ、静けさ、一貫した奥行き、止まるべき時に止まることから生まれる。画像比較 UI では、視線を奪う motion は品質判断を汚すため、candidate image 上の連続 shimmer、強い parallax、大きな morph、長い loading loop は原則使わない。

## Research Synthesis

### 1. Motion Has to Explain a State Change

Apple HIG は motion を status、feedback、instruction、direct manipulation の理解補助として扱う。Fluent 2 も motion に一貫性と物理的な予測可能性を求める。Material Design は、遅すぎる motion は待たされている感覚を生み、短すぎる motion は変化が読めなくなると整理している。

ToC 適用:

- hover は「ここを操作できる」を示すだけにする。
- focus は「キーボード操作の現在地」を hover より強く、静的に示す。
- press は「押下が受け取られた」を即時に返す。
- selection は「この candidate を採用候補として固定した」を残存状態として示す。
- generation は「処理中 / 完了 / 失敗」を該当 card 内だけで示す。
- decorative motion は、上記のどれにも該当しないなら入れない。

### 2. Creative Tool UX Needs Low Noise

Figma や Adobe 系の creative tool は、多数の状態、選択、編集、プレビュー、非同期処理を同時に扱う。React Aria は hover / press / focus を input type ごとに正規化し、WAI-ARIA は focus と selection を混同しないことを重視する。

ToC 適用:

- hover と selection は別状態として扱う。hover で selected border を上書きしない。
- focus と selection も別状態として扱う。keyboard focus は外側 ring、selected は candidate frame の rim。
- generation feedback は right chat pane に流さず、該当 card と bulk footer に閉じる。
- prompt textarea では装飾 motion を使わない。caret、selection、focus ring の可読性を優先する。
- reference multi-select は、選択済み thumbnail を静的 check / rim で残す。hover motion は thumbnail の視認を妨げない。

### 3. Spatial Feedback Should Be Small and Consistent

visionOS の空間設計は、奥行き、焦点、入力、comfort を結びつける。大きな視差や急な移動は、空間 UI では疲労や違和感につながる。`/image_gen` は 3D UI ではないが、glass layer は z 軸の文法として使える。

ToC 適用:

- z 軸は `background -> workspace -> promptCard -> candidateFrame -> controls -> footer/chat` に固定する。
- hover でカード全体を浮かせない。candidate frame や button だけを `translateY(-1px)` 以内で反応させる。
- active control は shadow を増やすより、rim と fill alpha を少し増やす。
- modal / confirmation だけは背面 dim と foreground scale を使ってよい。
- pointer 追従の lens / reflection は、画像比較エリアでは禁止。control rail の短い highlight に限定する。

### 4. Reduced Motion Is a First-Class Mode

MDN の `prefers-reduced-motion` は、ユーザーが不要な motion の削減を求めていることを CSS へ伝える。WCAG 2.2 は、自動で動き続け、他コンテンツと並行して表示される motion には停止・非表示の仕組みを求める。Apple の accessibility guidance も Reduce Motion を前提にした確認を求める。

ToC 適用:

- `prefers-reduced-motion: reduce` では、morph、parallax、sweep、shimmer、pulse、spring を止める。
- 残すのは opacity、border-color、background alpha、static progress text、determinate bar。
- loading が 5 秒を超えうる場合、常時 looping shimmer ではなく、静的 label と progress / elapsed を併用する。
- motion を止めても、hover / focus / selected / generating / failed が区別できることを合格条件にする。

## Motion Principles for Glass UI

### Principle 1: Motion Is a State Label

motion は装飾ではなく、状態ラベルの補助である。

実装判断:

- 状態が text / icon / border だけで十分なら motion は足さない。
- motion を足す場合、どの状態を説明するかを token 名に含める。
- 例: `--motion-focus-rim`, `--motion-press-settle`, `--motion-generation-sweep`。

### Principle 2: The Image Never Moves

candidate image と reference image は、比較・採点・採用判断の対象である。

禁止:

- image の scale hover。
- image 上の shimmer / sweep / reflection loop。
- selected candidate の image opacity 変更。
- prompt 編集中にカード全体が揺れる hover。

許可:

- image の外側 frame rim。
- frame 外側の very soft shadow。
- selected check badge の短い fade。
- failed / missing image の static state panel。

### Principle 3: Prompt Readability Beats Delight

prompt は長文であり、ユーザーが編集する制作仕様である。

禁止:

- textarea 背景の blur animation。
- prompt text の fade-in per line。
- caret 周辺の glow pulse。
- placeholder の animated hint。

許可:

- focus ring の 120ms fade。
- dirty state の small static dot。
- save / generation use state の短い badge fade。

### Principle 4: Glass Moves Less Than Solid UI

glass は背景の pixel と一緒に見えるため、強く動くと視覚ノイズが増える。

実装判断:

- glass control は `transform` より `border-color`、`box-shadow`、`background alpha` を優先する。
- morph は segmented control の active pill など、位置関係を説明する時だけ使う。
- reflection は idle では固定し、hover / press の瞬間だけ動かす。

### Principle 5: Feedback Stays Where the Action Happened

生成や選択の結果は、ユーザーが操作した場所に返す。

実装判断:

- single generate: 対象 card の button と candidate area だけを変える。
- bulk generate: bulk footer に全体 progress、各 card に個別 status。
- repo insertion: bulk footer で confirmation、成功後に selected candidate frame に static adopted state。
- chat pane は production advice と approval conversation の部屋であり、job log animation を流さない。

## Motion Taxonomy

| Motion | Primary purpose | Use in `/image_gen` | Avoid |
|---|---|---|---|
| shimmer | 非同期処理中の「生きている」感 | candidate placeholder の初期 1-2 秒、または skeleton | 画像上、prompt 上、5秒超ループ |
| sweep | glass surface の反射、処理開始の合図 | generate button 押下直後、bulk footer の progress rail | 全カード同時、常時 idle |
| reflection | 高級感のある素材反応 | topbar / control rail の hover highlight | text 背面、candidate image 上 |
| morph | 同一 control 内の選択移動 | asset / scene tabs、sub-filter、candidate count segmented UI | card layout 変更、画像 frame 変形 |
| press | 入力受領 | button、icon button、thumbnail select | 長い squash、layout shift |
| focus | keyboard 現在地 | focus-visible ring、textarea border、candidate action | hover と同じ見た目にすること |
| loading | 処理継続と待機理由 | determinate / indeterminate progress、status label | spinner と shimmer の重複 |
| pulse | 注意喚起または進行中 | 例外的に generating rim を低頻度で | selected 状態の常時 pulse |
| fade | 状態切替 | badge、error、completion toast | 重要 feedback の fade-only |
| parallax | 空間感 | 原則使わない。背景のごく弱い depth only | pointer 追従、画像比較中 |

## State Patterns

### Idle

目的: 静かで、比較に集中できる。

- glass rail は固定 highlight。
- candidate frame は低コントラスト hairline。
- button は背景 alpha と label で階層化。
- idle animation は置かない。

### Hover

目的: 操作可能性の確認。

- duration: 90-140ms。
- easing: ease-out / standard deceleration。
- 変化: border alpha +8-12%、background alpha +4-6%、shadow +軽微。
- transform: button / chip だけ `translateY(-1px)` まで。
- candidate card 全体は動かさない。

### Press

目的: 入力が受け取られたことを即時返す。

- duration down: 60-90ms。
- duration up: 100-140ms。
- 変化: `translateY(0)` or `scale(0.985)`、inner highlight 減少。
- press 後に generation が始まる場合、press motion から loading state へ連続させる。
- disabled press feedback は出さない。tooltip / label で理由を返す。

### Focus

目的: keyboard / assistive tech ユーザーの現在地を明示する。

- focus-visible は hover より強く、静的に残す。
- duration: 100-140ms fade。
- ring は外側に出し、layout を変えない。
- candidate selection と focus ring は併存させる。
- reduced motion でも focus ring は必ず残す。

### Selection

目的: 採用候補を固定し、比較中に見失わない。

- selected candidate は persistent rim + small badge。
- selection 直後だけ 120-160ms の rim settle を許可。
- selected image 自体は動かさない。
- hover は selected rim を弱めない。
- multiple selected / adopted / failed は icon と label を併用する。

### Generation Start

目的: クリック後に処理が始まったことを即時に返す。

- generate button は press 直後に disabled + progress affordance へ切り替える。
- candidate area は skeleton / empty frame を保ち、layout shift を起こさない。
- sweep は button または frame edge に 1 回だけ。
- bulk generate は footer に全体 status、card に個別 status。

### Generation In Progress

目的: 待機理由と対象範囲を示す。

- 1 秒未満: button busy state だけでよい。
- 1-5 秒: card 内の compact progress + low-motion rim。
- 5 秒超: elapsed / queue / retryable など text feedback を足す。
- determinate が取れるなら linear bar。取れないなら indeterminate bar + status text。
- shimmer と spinner を同時に使わない。

### Completion

目的: 新しい candidate が比較対象に入ったことを示す。

- candidate image は fade-in 80-140ms まで。
- frame rim を 1 回だけ highlight し、すぐ selected ではない通常候補に戻す。
- auto-selection する場合は selected state を明確に残す。
- success toast は必要最小限。card 内 feedback を優先する。

### Failure

目的: 何が失敗し、次に何をすればよいかを示す。

- 赤い shake は使わない。
- failed frame は static error state。
- retry button は focusable にする。
- error label は短く、stack trace は出さない。
- failed candidate area の比率は崩さない。

## Timing Tokens

| Token | Duration | Use |
|---|---:|---|
| `--motion-instant` | 60ms | press down、tiny icon feedback |
| `--motion-fast` | 100ms | hover in、badge appear |
| `--motion-base` | 140ms | focus ring、hover out、small fade |
| `--motion-state` | 180ms | selection settle、tab pill morph |
| `--motion-slow` | 240ms | modal enter、bulk footer emphasis |
| `--motion-max` | 320ms | rare large state transition |

Material Design の desktop guidance は 150-200ms 程度の短い motion を推奨している。`/image_gen` は制作ツールなので、通常 interaction は 60-180ms に寄せ、240ms 以上は modal / destructive confirmation だけに限定する。

## Easing Tokens

| Token | Curve | Use |
|---|---|---|
| `--ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | hover / focus / fade |
| `--ease-enter` | `cubic-bezier(0, 0, 0.2, 1)` | badge / image appear |
| `--ease-exit` | `cubic-bezier(0.4, 0, 1, 1)` | temporary feedback dismiss |
| `--ease-press` | `cubic-bezier(0.3, 0, 0.2, 1)` | press settle |
| `--ease-morph` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | active pill movement |

spring は原則不要。使う場合も tabs / segmented controls の active indicator だけにし、candidate frame や prompt card には使わない。

## Component Guidance

### Topbar

- idle: static glass, no loop.
- hover on icon: rim alpha + highlight fade.
- run selector focus: clear focus ring, no dropdown bounce.
- loading run list: topbar bottom edgeに 2px indeterminate bar。
- reduced motion: bar は static stripe または opacity shift。

### Asset / Scene Tabs

- active indicator は morph を許可する代表箇所。
- duration: 160-200ms。
- tab content grid は crossfade ではなく即時差し替えでもよい。必要なら 80ms fade。
- active pill の移動で category change を説明する。
- hover は active state より弱くする。

### Sub-filter

- `chara -> obj -> asset` の棚移動を small pill morph で示す。
- selected filter は fill + rim + label weight。
- image grid 側は大きく動かさない。

### Candidate Count / Stepper

- press は immediate。
- value change は数字の vertical slide ではなく static replace または 80ms fade。
- validation error は field rim + helper text。

### Prompt Card

- card hover で浮かせない。
- focus-within で rim と header metadata の contrast を上げる。
- prompt textarea は `backdrop-filter: none`。
- dirty / edited state は static dot + label。
- generating 中でも prompt text を揺らさない。

### Reference Selector

- dropdown open: 120-160ms opacity + slight y offset。
- thumbnail hover: border / background only。
- selected thumbnail: check badge + rim。
- missing reference: warning rim + static label。
- image thumbnail は scale しない。

### Candidate Frame

- idle: stable 16:9 frame。
- hover: frame rim slightly brighter。
- selected: persistent cyan rim + badge。
- newly generated: one-time rim highlight。
- failed: static error panel。
- adopted: persistent adopted badge, not animated after first confirmation。

### Generate Button

- idle: primary command with calm glass.
- hover: single reflection highlight, no continuous sweep.
- press: 60-90ms compress.
- generating: disabled + progress label。
- complete: brief success icon fade, then ready state。
- failed: retry affordance with error state nearby。

### Bulk Footer

- footer is the strongest glass layer.
- bulk progress は footer 内 linear bar を第一候補にする。
- all-card shimmer は禁止。
- repo insertion は press feedback の後、confirmation state へ移す。
- destructive / overwrite action は motion より明示的 confirmation を優先する。

### Right Chat Pane

- chat pane の motion は workspace よりさらに少なくする。
- assistant response streaming は text readability を優先し、cursor pulse を弱くする。
- approval UI は focus / press / disabled を明確にする。
- image generation job log を流さない。

## Decision Matrix

動きを入れる前に、次の基準で判定する。

| Question | Pass | Fail |
|---|---|---|
| 状態変化を説明しているか | hover / focus / press / selected / generating / failed を明確化する | 単に高級に見せたい |
| 画像比較を邪魔しないか | image 外側だけが動く | image 自体、色、明暗、輪郭を動かす |
| prompt 可読性を保つか | text 背面は安定している | text 背面の blur / shimmer / reflection が動く |
| keyboard focus と selection を分けるか | focus ring と selected rim が併存 | hover / focus / selected が同じ |
| reduced motion で意味が残るか | border / icon / label で同じ状態を伝える | motion がないと状態不明 |
| layout shift がないか | frame / card dimensions が固定 | hover / loading で高さや位置が変わる |
| loop が必要か | 処理中で、停止・代替がある | idle 装飾として動き続ける |
| 範囲が局所的か | 操作した card / footer だけ反応 | 画面全体が同時に光る |

採用条件:

- 上の 8 項目中、最初の 6 項目は必須。
- loop motion は generation 中だけ許可。
- candidate image 上の motion は原則不採用。例外は、画像がまだ存在しない placeholder のみ。

## Reduced Motion Rules

```css
@media (prefers-reduced-motion: reduce) {
  .lg-motion,
  .lg-shimmer,
  .lg-sweep,
  .lg-pulse,
  .lg-morph {
    animation: none;
    transition-duration: 1ms;
  }

  .lg-glass-control,
  .lg-candidate-frame,
  .lg-focusable {
    transition-property: border-color, background-color, box-shadow, opacity;
  }
}
```

Reduced motion mode の設計ルール:

- `transform` を使う hover / press は止める。
- shimmer / sweep は static gradient または progress bar へ置換する。
- pulse は static rim へ置換する。
- morph は instant selected state へ置換する。
- focus-visible は消さない。
- loading は text と progress value で伝える。

## Implementation Tokens

```css
:root {
  --motion-instant: 60ms;
  --motion-fast: 100ms;
  --motion-base: 140ms;
  --motion-state: 180ms;
  --motion-slow: 240ms;
  --motion-max: 320ms;

  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --ease-enter: cubic-bezier(0, 0, 0.2, 1);
  --ease-exit: cubic-bezier(0.4, 0, 1, 1);
  --ease-press: cubic-bezier(0.3, 0, 0.2, 1);
  --ease-morph: cubic-bezier(0.2, 0.8, 0.2, 1);
}
```

```css
.lg-control {
  transition:
    border-color var(--motion-base) var(--ease-standard),
    background-color var(--motion-base) var(--ease-standard),
    box-shadow var(--motion-base) var(--ease-standard),
    transform var(--motion-fast) var(--ease-press);
}

.lg-control:hover {
  transform: translateY(-1px);
}

.lg-control:active {
  transform: translateY(0);
}

.lg-control:focus-visible {
  outline: 0;
  box-shadow:
    0 0 0 2px rgba(246, 211, 101, 0.72),
    0 0 0 5px rgba(246, 211, 101, 0.18);
}

.lg-candidate-frame {
  transition:
    border-color var(--motion-base) var(--ease-standard),
    box-shadow var(--motion-state) var(--ease-standard),
    background-color var(--motion-base) var(--ease-standard);
}
```

## Anti-patterns

- idle glass が常に shimmer する。
- candidate image が hover で zoom する。
- selected candidate が pulse し続ける。
- prompt textarea 背面で reflection が走る。
- loading spinner、shimmer、progress bar を同時に出す。
- focus ring を hover と同じ見た目にする。
- keyboard focus を selection と同義にする。
- reduced motion で focus / loading / selected の意味まで消える。
- bulk generation で全カードが同時に光る。
- failure に shake animation を使う。

## Final Recommendation

`/image_gen` の glass motion は、次の 5 つに限定する。

1. control hover の微細な rim / alpha transition。
2. button press の短い compress / settle。
3. tabs / sub-filter の active pill morph。
4. candidate selection / generation completion の one-time rim highlight。
5. generation progress の局所的な bar / restrained sweep。

それ以外は原則、静的な icon、label、border、background alpha、progress text で表現する。高級な制作ツールらしさは、動き続ける装飾ではなく、ユーザーの意図にだけ反応し、画像と prompt を汚さず、必要な状態だけが正確に残ることから作る。
