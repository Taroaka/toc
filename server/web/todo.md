# Frontend Design TODO

## Purpose

この TODO は、`server/web/docs/brand-design/` の調査書と現在の `/image_gen` フロント実装を比較し、最先端の Web design と現行 appserver UI の乖離を修正候補として管理する。

## Review Inputs

- `server/web/docs/brand-design/README.md`
- `server/web/docs/brand-design/apple-design-research-2026.md`
- `server/web/docs/brand-design/frontend-design-quality-guidelines.md`
- `server/web/docs/brand-design/glass-design-summit.md`
- `server/web/docs/brand-design/glass-implementation-design.md`
- `server/web/src/main.tsx`
- `server/web/src/styles.css`
- `server/web/src/components/LiquidGlass.tsx`
- `server/web/src/components/liquidGlass.css`

## Pending Multi-Agent Review

- [x] Apple platform / Liquid Glass 観点
- [x] Advanced web composition / anti generic SaaS 観点
- [x] Museum spatial design / information architecture 観点
- [x] Motion / interaction / state expression 観点
- [x] Accessibility / performance / responsive 観点
- [x] Implementation consistency / component architecture 観点

## Accepted Fix TODO

サブエージェントの提案をメインエージェントが採否判断し、妥当なものだけここへ追加する。

### High

- [x] 作業面を generic SaaS card mosaic から制作展示壁へ再構成する。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`
  - 現状: `promptCard` が prompt / reference / generate / candidate を縦積みで反復し、候補画像よりフォーム構造が主役に見える。
  - 修正案: desktop では card 内を横長フレーム化し、左に prompt / reference、右または中央に existing + candidate comparison wall を置く。candidate area の面積と視線優先度を上げる。

- [x] controls を run / target / generation count の 3 ステーションに再設計する。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`
  - 現状: `Select`, `Tabs`, sub tabs, count panel が MUI フォーム列として並び、現在地と操作順序が弱い。
  - 修正案: `Run selector`, `Target selector`, `Generation count` を control rail 上の区画として分け、`assetSubTabs` は asset 配下の二段目操作として弱める。

- [x] topbar を汎用ツール名ではなく制作現在地の案内板へ寄せる。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`
  - 現状: `ToC Image Gen` と英語 subtitle が主で、run / asset / scene / chara / obj の現在地が分散している。
  - 修正案: selected run を主見出し、asset / scene と sub-filter を breadcrumb として出す。英語の内部説明 copy は削るか日本語の作業者語へ統一する。

- [x] bulk footer に一括生成と repo insertion の進捗・結果状態を追加する。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`
  - 現状: 一括生成は各 card に状態が分散し、repo insertion は成功 / 失敗 / 処理中 state が UI に残らない。
  - 修正案: `bulkGenerating`, `completedCount`, `failedCount`, `insertBusy`, `insertStatus`, `lastInsertedCount` を持ち、footer に `生成中 3/12`, `失敗 1`, `X inserted` などの静的 status と progress を出す。

- [x] candidate 生成中 placeholder と採用済み state を追加する。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`
  - 現状: 生成開始時に `candidates: []` へ消え、candidate area が空白に見える。repo 挿入後も selected candidate が同じ見た目のまま。
  - 修正案: `candidate_count` 分の固定 placeholder frame を出し、`waiting / generating / ready / failed / adopted` を label + rim で表示する。

- [x] narrow viewport で chat pane を消さず、drawer / bottom sheet / tab view として到達可能にする。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`
  - 現状: `max-width: 1100px` で `.chatPane { display: none; }` になり、chat / approval へ到達できない。
  - 修正案: `chatOpen` state と mobile chat trigger を追加し、approval がある場合もアクセス可能な入口を残す。

- [x] `prefers-reduced-transparency` と `forced-colors` fallback を app 固有 class まで拡張する。
  - 対象: `server/web/src/styles.css`, `server/web/src/components/liquidGlass.css`
  - 現状: `.lg` 系中心の fallback で、`.shell`, `.promptCard .MuiInputBase-root`, `.bubble`, `.composer`, `.candidate` など読解面に透明・gradient が残る。
  - 修正案: reduced transparency では読解面を opaque 化し、forced colors では `.topbar`, `.promptCard`, `.bubble`, `.composer`, `.candidate`, selected/error state を system colors へ明示的に落とす。

- [x] prompt textarea を solid editor として扱う。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`
  - 現状: `.promptCard .MuiInputBase-root` が `rgba(8, 10, 12, 0.32)` で、設計書の solid / near-solid 方針より薄い。
  - 修正案: prompt 専用 class hook を付け、opaque surface token を適用する。長文入力面は glass 感より可読性を優先する。

- [x] CSS token の二重化を整理する。
  - 対象: `server/web/src/components/liquidGlass.css`, `server/web/src/styles.css`
  - 現状: `--lg-*` と `--museum-*` が併存し、直書き色も多い。
  - 修正案: `--museum-*` を `--lg-*` の alias に寄せ、代表的な surface / rim / text / line 色を semantic token 化する。

### Medium

- [x] candidate frame の通常状態を plain solid frame へ寄せる。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`, `server/web/src/components/liquidGlass.css`
  - 現状: candidate container が glass material として目立ち、作品より額装が勝ちやすい。
  - 修正案: idle candidate では shine を抑え、selected / error / adopted のみ rim と label を強める。

- [x] reference selection を persistent thumbnail rail として表示する。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`
  - 現状: reference は Autocomplete chips と option thumbnail に留まり、candidate との視覚照合が弱い。
  - 修正案: 選択済み reference を card 内に thumbnail rail として常設し、filename、check/rim、remove action を持たせる。

- [x] chat pane に現在の run / selected item context と承認状態を出す。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`
  - 現状: chat は別室感があるが、どの展示室 / candidate について相談しているかが弱い。承認待ちも通常応答待ちと同じ progress 表現。
  - 修正案: chat head に selected run / item context を短く表示し、`応答待ち`, `承認待ち N 件`, `送信失敗` の status row と approval block を分離する。

- [x] LiquidGlass の default hover / shine を弱め、lift は opt-in にする。
  - 対象: `server/web/src/components/liquidGlass.css`, `server/web/src/components/LiquidGlass.tsx`
  - 現状: `.lg.is-interactive:hover` が default で `translateY(-1px)` と raised shadow を持ち、今後の制作 UI で視線が揺れやすい。
  - 修正案: default hover は border / alpha / shadow 微差に限定し、lift は `data-lift` や slot class で opt-in にする。

- [x] LiquidGlass component に semantic slot / thin wrapper を追加する。
  - 対象: `server/web/src/components/LiquidGlass.tsx`, `server/web/src/components/liquidGlass.css`
  - 現状: `topbar glassTopbar`, `promptCard`, `bulkFooter`, `chatPane` など画面固有 class が material vocabulary になっている。
  - 修正案: `slot?: 'topbar' | 'controls' | 'prompt' | 'candidate' | 'footer' | 'chat'` か `GlassTopbar` / `GlassPromptCard` など薄い wrapper を段階導入する。

- [x] candidate media slot を 16:9 固定にする。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`
  - 現状: `aspect-ratio` は画像だけにあり、loading / error / empty で frame の見え方が揺れる。
  - 修正案: `.candidateMedia` を作り、画像・error text・loading placeholder を同じ 16:9 slot に入れる。

- [x] icon-only button と interactive glass のアクセシビリティを補強する。
  - 対象: `server/web/src/main.tsx`, `server/web/src/components/LiquidGlass.tsx`
  - 現状: reload / send icon button に明示 `aria-label` がない。`GlassSurface` の keyboard activation は利用側任せ。
  - 修正案: icon-only button に `aria-label` を追加し、将来的に `GlassButton` / `GlassSelectable` を `ButtonBase` ベースで用意する。

- [x] image rendering cost を抑える。
  - 対象: `server/web/src/main.tsx`, `server/web/src/styles.css`
  - 現状: reference / candidate images が通常 `<img>` で同時描画される。
  - 修正案: `loading="lazy"` と `decoding="async"` を付ける。件数増加時は `content-visibility: auto` や virtualization を検討する。

### Low

- [x] UI copy を日本語の作業者語へ揃える。
  - 対象: `server/web/src/main.tsx`
  - 現状: `ToC Image Gen`, `Codex App Chat`, `candidate`, `current`, `selected`, `output folder` など英語の内部説明語が残る。
  - 修正案: `画像候補の比較と採用`, `制作相談`, `候補`, `現在`, `採用`, `出力先` などへ寄せる。
