# Brand Design

このフォルダは ToC の Web UI における色、質感、ブランディング、画面設計の正本を置く。

対象は主に `server/` 配下の image generation app であり、LINE bot の会話設計や webhook 運用とは分けて扱う。

## Scope

- `/image_gen` の視覚デザイン、情報設計、操作感
- `server/web/` の MUI theme、CSS tokens、layout rules
- prompt editing / candidate comparison / repo insertion に必要な作業者向け UI
- Codex app 風の右側 chat pane の会話体験

## Files

- `visual-identity.md`: 色、質感、タイポグラフィ、ブランドトーン
- `image-gen-ui.md`: `/image_gen` 画面の構造と UI 責務
- `interaction-principles.md`: 操作、状態表示、bulk action、チャットの振る舞い
- `photoshopvip-design-thinking.md`: PhotoshopVIP 記事から反映する Liquid Glass 系デザイン思考
- `liquid-glass-patterns.md`: Web / React / MUI で使う Liquid Glass component pattern
- `advanced-museum-spatial-design.md`: 先進的な美術館空間から導く z 軸、導線、展示壁の設計
- `apple-design-research-2026.md`: Apple Liquid Glass / visionOS / HIG 追加調査を ToC 実装判断へ翻訳したメモ
- `frontend-design-quality-guidelines.md`: note 記事と OpenAI frontend guidance から抽出した UI 品質ルール
- `glass-design-summit.md`: 6本の専門調査を統合した最高峰 glass design 方針
- `glass-implementation-design.md`: glass design 調査を実装抽象度ごとの担当範囲に落とす設計書
- `research-glass-01-apple-platform.md` - `research-glass-06-accessibility-performance.md`: glass design 深掘り調査ログ

## Design Direction

ToC image generation app は「透明なグラスの中に、ユーザーの指示で何層にも広がる美術館」として設計する。見た目は装飾的なギャラリーではなく、prompt、reference、candidate、repo insertion を高速に比較・判断するための実務 UI を優先する。

ただし単なる管理画面にはしない。暗い制作環境に、生成候補の画像と明るいアクセントが浮く構成にして、制作中の集中感、Liquid Glass の階層感、Codex app 的な会話体験を両立する。
