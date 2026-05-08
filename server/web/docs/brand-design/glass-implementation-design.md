# Glass Implementation Design

## Purpose

この文書は `glass-design-summit.md` と 6 本の調査ログを、`/image_gen` の実装作業へ落とし込むための設計書である。

目標は「透明なグラスにユーザーの指示で何層にも広がる美術館」を、単なる装飾ではなく制作 UI の判断速度を上げる material system として実装することにある。

対象は `server/web/` の React + MUI UI であり、このスレッドでは LINE 側は扱わない。

## Source Documents

- `glass-design-summit.md`: glass design の統合方針
- `research-glass-01-apple-platform.md`: platform glass の扱い
- `research-glass-02-web-implementation.md`: Web 実装方式
- `research-glass-03-museum-architecture.md`: 美術館的な空間設計
- `research-glass-04-luxury-product-ui.md`: 高級 UI の光量制御
- `research-glass-05-motion-interaction.md`: motion と状態表現
- `research-glass-06-accessibility-performance.md`: accessibility / performance 制約
- `apple-design-research-2026.md`: Apple design 追加調査
- `frontend-design-quality-guidelines.md`: frontend quality / anti AI-slop ルール

## Abstraction Levels

### Level 1: Foundation Tokens

担当範囲:

- `server/web/src/components/liquidGlass.css`

責務:

- glass cyan、museum amber、deep black、white hairline を semantic token として扱う。
- `lg` component の初期状態は主張しすぎない hairline と影にする。
- status rim は idle では弱く、selected / active / error など状態がある時だけ強くする。
- reduced transparency / reduced motion / forced colors でも操作面が成立する fallback を持つ。

禁止:

- image candidate や prompt textarea 自体に blur / filter / reflection をかけない。
- 長時間の idle shimmer を入れない。
- 全 component が同じ radial shine になる token をデフォルト化しない。

### Level 2: Shared Liquid Glass Components

担当範囲:

- `server/web/src/components/LiquidGlass.tsx`

責務:

- `LiquidGlass` の `variant` / `tone` / `density` / `status` / `dockPosition` を、画面側が意味で指定できる API に保つ。
- 状態 class は material system の vocabulary と一致させる。
- React component は装飾 detail を持ちすぎず、CSS token へ責務を渡す。
- chat、footer、candidate などの個別表現に必要な class hook を安定して提供する。

禁止:

- component 内で inline style による光表現を増やす。
- image generation の業務ロジックを glass component に混ぜる。

### Level 3: Screen Composition

担当範囲:

- `server/web/src/styles.css`
- `server/web/src/main.tsx`

責務:

- topbar / controls / prompt card / candidate / bulk footer / chat pane の光り方をそれぞれ変える。
- prompt と candidate image は主役として読みやすく保つ。
- asset 側の表示順は `キャラ > obj > asset` を維持し、全表示も同じ順序にする。
- `bootstrap_builtin` など内部 lane 名を UI に露出させない。
- bottom footer は常時表示し、selected count と repo insertion の重みが分かる構成にする。
- 右 chat は画像生成ログではなく、ユーザーとの通常 chat と approval UI に限定する。

禁止:

- grid 全体に heavy blur をかけない。
- candidate image を hover / selected で scale しない。
- 右 chat に generation job log を混ぜない。

## Component Light Grammar

### Topbar

- 水平方向の案内板として読む。
- 下端 hairline と薄い top highlight を使う。
- radial glow は使わない。

### Controls

- 展示 wing / 生成条件の操作卓として読む。
- rail、目盛り、segment の active capsule を使う。
- active 以外の発光は抑える。

### Prompt Card

- 制作指示の wall text として読む。
- 通常は solid dark surface。
- focus は museum amber ring、generating は短い cyan sweep に限定する。

### Candidate

- 作品の額縁として読む。
- idle は hairline のみ。
- selected は cyan rim、error は red rim。
- 画像本体には opacity / blur / reflection をかけない。

### Bulk Footer

- 収蔵カウンターとして読む。
- bottom dock の接地 shadow と上端 highlight を使う。
- repo insertion は採用 action として download より強く見せる。

### Chat Pane

- キュレーター相談室として読む。
- warm amber side rim で main workspace と別室化する。
- message bubble は過透明にしない。

## Implementation Sequence

1. Foundation tokens を整え、共通 `lg` material が控えめな baseline を持つようにする。
2. Shared component API を確認し、画面側が意味 class を付けやすい状態にする。
3. Screen composition で各エリアの光り方を分離する。
4. Screen composition の前に `frontend-design-quality-guidelines.md` の litmus checks を確認する。
5. Build と pointer docs validation を通す。
6. UI レビューでは「単調な輝きになっていないか」「prompt / image の読みやすさを損なっていないか」「generic SaaS card mosaic に見えていないか」を優先して見る。

## Acceptance Checklist

- topbar、controls、candidate、footer、chat pane の光り方が別物として読める。
- candidate image と prompt textarea に glass effect が直接かかっていない。
- selected candidate と idle candidate が明確に違う。
- footer で selected count と repo insertion が常時分かる。
- chat pane は warm amber rim でユーザー chat 専用の別室として読める。
- reduced transparency で solid UI として成立する。
- reduced motion で状態理解が失われない。
- asset 全表示と選択肢は `キャラ > obj > asset` の順番を保つ。
