# Frontend Design Quality Guidelines

## Purpose

この文書は、note 記事「GPT-5.4で美しいフロントエンドを作る！OpenAI公式テクニック全まとめ」と OpenAI の GPT-5.4 / frontend quality guidance を、ToC `/image_gen` の設計ルールへ反映するためのメモである。

ToC は landing page ではなく制作アプリなので、記事内の LP ルールはそのまま適用しない。代わりに、AI っぽい凡庸な UI を避けるための制約、検証、構図の考え方を取り込む。

## Sources

- note: 〖完全解説〗GPT-5.4で美しいフロントエンドを作る！OpenAI公式テクニック全まとめ  
  https://note.com/masa_wunder/n/ndd8a03d6d5f2
- OpenAI: Introducing GPT-5.4  
  https://openai.com/index/introducing-gpt-5-4/

## Key Findings

### 1. Start From Composition, Not Components

記事では「コンポーネントではなくコンポジションから始める」ことが美しい default として整理されている。ToC では、GlassCard や MUI Card を積み上げる前に、画面全体を制作導線として設計する必要がある。

ToC 適用:

- 最初に `workspace + right chat + fixed footer` の全体構図を決める。
- component は構図の役割に従う。component が主役にならない。
- `promptCard` は必要な interaction container なので使うが、画面全体を card mosaic にしない。

### 2. Avoid Generic SaaS Card Grids

記事は、汎用 SaaS 風のカードグリッドやピル群、統計ストリップ、装飾 icon の濫用を明確な失敗パターンとしている。ToC の grid は画像生成 request を編集する実務上必要な構造だが、見た目を「カードを並べた管理画面」に寄せすぎない。

ToC 適用:

- grid は展示壁として扱い、各 card は prompt と候補画像を載せる working frame とする。
- card 内の装飾 icon を増やさない。
- section ごとに one job を守る。controls は生成条件、grid は編集・比較、footer は bulk action、chat は相談。
- glass の見栄えで情報構造をごまかさない。

### 3. Brand Signal Must Be Visible Without Nav

記事の Brand Test は、navigation を外してもブランド / プロダクトが伝わるかを見る考え方である。ToC `/image_gen` はアプリ画面なので hero はないが、第一 viewport で「透明なグラスの中に広がる美術館」という世界観が伝わる必要がある。

ToC 適用:

- topbar の小さな app name だけに brand を閉じ込めない。
- background、control rail、candidate frame、chat pane の光り方で世界観を持たせる。
- empty state は説明文ではなく、展示室 / 制作室としての空間を示す。
- theme color は cyan / amber に絞り、紫や generic AI gradient へ逃げない。

### 4. Restraint Is A Quality Constraint

記事では、装飾の前に余白、alignment、scale、cropping、contrast を使うこと、accent color と typeface を絞ることが強調されている。ToC の glass design も、blur や shine を足すほど良くなるわけではない。

ToC 適用:

- accent は `glass cyan` と `museum amber` を中心にする。
- shadow を全部消しても layout hierarchy が読めるか確認する。
- prompt / candidate / footer の spacing は固定し、hover で layout shift させない。
- CSS variable は semantic name で持ち、色を ad hoc に増やさない。

### 5. Motion Must Explain State

記事では motion を 2-3 個の意図的なものに絞る方針が紹介されている。OpenAI の GPT-5.4 発表でも、Playwright などによる視覚検証と反復改善が frontend quality に重要だと説明されている。

ToC 適用:

- generating sweep
- selected candidate rim
- chat / approval の状態変化

上記以外の常時 shimmer、floating animation、decorative parallax は原則入れない。

### 6. Copy Should Be Short And Operational

記事は、コピーを削って意味が改善するなら削り続ける方針を示している。ToC は作業アプリなので、UI copy は美辞麗句ではなく、操作判断に直結する短い言葉にする。

ToC 適用:

- 内部 lane 名を出さず、`参照なし生成` / `参照あり生成` のように作業者語へ翻訳する。
- empty state は短く、次に何を選ぶかだけ示す。
- design commentary を UI 上に出さない。
- button label は「一括生成」「一括ダウンロード」「一括repo内挿入」のように action を明示する。

## Litmus Checks For `/image_gen`

- nav を隠しても、制作美術館の世界観が残るか。
- grid は必要な作業面であり、generic SaaS card mosaic に見えていないか。
- 各領域に one job があるか。
- prompt と candidate image が glass 装飾より強く見えているか。
- motion は状態理解を助けているか。
- shadow を弱めても premium に見えるか。
- UI copy は短く、内部実装語を露出していないか。
- Playwright / browser screenshot で PC と mobile の重なり、scroll、footer 固定を確認したか。

## Implementation Impact

- 新しい UI を作る前に `Visual Thesis`、`Content Plan`、`Interaction Thesis` を 3 行で書く。
- 既存 UI を改善する時は、まず構図、余白、contrast、情報の責務を見直す。
- component を追加する時は、既存の `LiquidGlass` token / class hook を使う。
- 実装後は build だけでなく、ブラウザで viewport と screenshot を確認する。
- デザインレビューでは「きれいか」より先に「目的ごとに分離され、読めて、迷わないか」を見る。
