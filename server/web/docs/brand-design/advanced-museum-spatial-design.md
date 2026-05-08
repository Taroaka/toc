# Advanced Museum Spatial Design

## Purpose

`/image_gen` Web App の世界観は、「透明なグラスの中に、ユーザーの指示で何層にも広がる美術館」として扱う。これは landing page 的な比喩ではなく、制作判断の UI を支える空間設計の原則である。

画面の主役は candidate image と prompt であり、空間表現は次を助ける範囲に限定する。

- どの run / asset / scene を見ているか分かる
- 複数候補を静かに比較できる
- prompt、reference、candidate、採用操作の関係が見失われない
- 生成中、失敗、選択、挿入の状態が視線移動で読める
- 暗色の制作管制卓に、透明感、奥行き、静けさを足す

## Research Sources

調査は公式情報と博物館設計ガイドを中心に参照した。長い引用は避け、UI 設計に使える示唆だけを抽出する。

- Mori Building / teamLab Borderless: https://www.mori.co.jp/en/press/release/_202422018620228_20242bubble_u/
- Louvre Abu Dhabi architecture: https://www.louvreabudhabi.ae/en/about-us/architecture
- 21st Century Museum of Contemporary Art, Kanazawa concept: https://www.kanazawa21.jp/data_list.php?d=2&g=11
- 21st Century Museum of Contemporary Art, Kanazawa architectural data: https://www.kanazawa21.jp/data_list.php?d=2&g=36
- 21st Century Museum of Contemporary Art, Kanazawa public zone: https://www.kanazawa21.jp/data_list.php?d=4&g=130
- Cleveland Museum of Art Gallery One: https://www.clevelandart.org/articles/gallery-one
- Cleveland Museum of Art ARTLENS Gallery: https://www.clevelandart.org/about/press/cleveland-museum-art-introduces-artlens-gallery-touchscreen-free-approach-integrating
- Cooper Hewitt Pen support: https://support.cooperhewitt.org/hc/en-us/articles/203903068-What-is-the-Pen
- Cooper Hewitt Interactive Digital Visitor Experience: https://www.cooperhewitt.org/new-experience/
- M+ building design: https://www.mplus.org.hk/en/the-building/design/
- Herzog & de Meuron M+ project text: https://www.herzogdemeuron.com/projects/415-m-plus/lightbox/15217/
- Guggenheim Museum Bilbao inside the museum: https://www.guggenheim-bilbao.eus/en/the-building/inside-the-museum
- ARTECHOUSE story: https://www.artechouse.com/about/
- Superblue immersive art experiences: https://www.superblue.com/
- Practical Guide for Sustainable Climate Control and Lighting in Museums and Galleries: https://www.nla.gov.au/sites/default/files/2022-02/Practical-guide-for-sustainable-climate-control-and%20lighting-in-museums-and-galleries.pdf
- Smithsonian Guidelines for Accessible Exhibition Design: https://affiliations.si.edu/wp-content/uploads/PDFs/Accessible-Exhibition-Design.pdf
- V&A / museum interactives research PDF: https://media.vam.ac.uk/media/documents/legacy_documents/file_upload/5763_file.pdf

## Governing Thought

先進的なミュージアム空間の強さは、派手な没入感ではなく、「複数の体験層を、迷わず、静かに、比較可能な状態で重ねる」ことにある。`/image_gen` では、グラス、光、反射、階層、展示壁を、候補画像の比較と採用判断を補助する情報建築として使う。

## Design Principles

### 1. Glass As Boundary, Not Decoration

金沢21世紀美術館は、円形とガラスによって内外の境界を曖昧にし、来館者同士の存在を感じさせる。Louvre Abu Dhabi は、光と影と反射を建築体験の中心に置く。これらから、透明素材は「きれいな blur」ではなく、関係性を見せる境界として扱うべきだと分かる。

UI への変換:

- glass layer は固定 topbar、chat pane、bulk footer、selected candidate frame など、状態の境界にだけ使う。
- prompt card 自体を過度な frosted glass にしない。画像比較と text reading を邪魔するため。
- 透明面は「背後が少し見える」程度に抑え、奥行きのヒントとして使う。
- 反射表現は細い highlight、1px border、淡い inner shadow に限定する。
- glass layer の役割は、階層、現在地、採用状態、非破壊/破壊操作の分離を示すこと。

### 2. Layered Museum In A Glass

Louvre Abu Dhabi の dome は、複数層の幾何学が光を濾過する。M+ は podium、tower、central light well、Found Space を重ね、上下の視線関係を作る。teamLab Borderless は作品同士が部屋を越えて移動し、ひとつの連続世界として変化する。

`/image_gen` の世界観では、透明なグラスを次の階層として捉える。

- Base floor: dark production desk。全体の作業面。
- Run layer: folder selector と asset / scene tabs。どの展示群に入るか。
- Gallery layer: grid。各 request item は小展示室。
- Wall layer: prompt、reference、existing image、candidate。展示壁と注釈。
- Light layer: generation progress、selected border、error state。作品を読むための照明。
- Archive layer: zip download、repo insertion、backup。展示後の収蔵操作。
- Conversation layer: right chat pane。キュレーターとの相談室。

重要なのは、すべてを同じ強度で見せないこと。階層は z-index の派手さではなく、明度、余白、border、固定位置、scroll の違いで読ませる。

### 3. Circulation Before Ornament

Guggenheim Bilbao は atrium を中心に複数階の gallery へ接続する。M+ は複数の入口と中央の lobby で内外の連続性を作る。金沢21世紀美術館は円形平面により複数方向から入れる。先進的な美術館でも、体験の基礎は「今どこにいて、次にどこへ行けるか」である。

UI への変換:

- workflow の順序は `run folder -> asset / scene -> candidate count -> grid -> bulk footer` から変えない。
- tab と folder selector は美術館の入口。小さくしすぎない。
- grid は展示室群。card 間の余白は「通路」として一定に保つ。
- bulk footer は出口の収蔵カウンター。scroll に巻き込まない。
- right chat pane は別棟ではなく隣接する相談室。作業進捗ログを流さず、制作判断の会話に限定する。

### 4. Exhibition Wall Grammar

美術館の展示壁は、作品、余白、キャプション、照明の関係で成立する。Cooper Hewitt の Pen は wall label を収集点にし、Cleveland Art Museum の Gallery One / ARTLENS は大きな interactive wall と app を連動させた。展示壁は情報を並べるだけでなく、あとで比較・回収できる接点になる。

`/image_gen` の card は展示壁として設計する。

- candidate image は中央展示。16:9 を固定し、比率を崩さない。
- prompt text field は wall text。長文でも編集しやすく、画像の上には被せない。
- reference selector は資料棚。thumbnail と filename で視覚照合できる。
- existing image は旧展示。candidate とは違う枠や label で区別する。
- selected candidate は採用候補の額装。primary accent border を使う。
- failed candidate は空の展示枠として残し、layout を崩さず短い error を出す。

### 5. Captions Should Reduce Cognitive Load

Smithsonian の accessible exhibition design は、導線、object、label の読みやすさ、glare 対策を重視する。展示キャプションは作品理解の入口だが、読ませすぎると作品体験を奪う。

UI への変換:

- label は短く、状態と操作対象を明確にする。
- technical path は必要箇所にだけ出し、主表示では truncate する。
- button label は動詞中心にする。例: `Generate`, `Insert`, `Download`。
- error は原因の分類と次行動だけを出す。
- tooltip は icon の意味補助に使い、常時説明文を置かない。

### 6. Quiet Immersion

ARTECHOUSE や Superblue は、映像、音、センサー、反応する空間によって作品の中に入る体験を作る。一方で制作 UI では、没入感が強すぎると比較判断を邪魔する。ここで必要なのは、全画面のショーではなく、静かな没入である。

UI への変換:

- 背景は低輝度のまま、細い grid と微細な light band で奥行きを出す。
- 大きな動画背景、派手な gradient、orb 装飾は使わない。
- generation progress は展示室内の照明変化として扱い、画面全体を点滅させない。
- hover は浮き上がるより、枠線と luminance の微差で示す。
- animation は短く、状態理解に寄与するものだけにする。

### 7. Comparison Is The Core Experience

Cleveland の ARTLENS Wall は collection を大きく一覧し、app と組み合わせて探索と理解を支援する。Cooper Hewitt の table は複数人が collection object を選び、拡大し、関連を見られる。V&A の interactive research は、参加型展示が「対象物との接続」を失うと学習効果が落ちることを示している。

`/image_gen` では、比較のために次を守る。

- candidate は同一寸法、同一配置、同一操作で並べる。
- reference と candidate の距離を離しすぎない。
- prompt edit と generate button は同じ card 内に置き、原因と結果を接続する。
- selected state は候補単位で明確にし、bulk insertion 前に採用対象が一目で分かる。
- comparison area には marketing copy や装飾テキストを置かない。

### 8. Light, Reflection, And Accessibility

博物館照明ガイドは、光が作品の可視性だけでなく建築体験と導線にも関わること、ただし展示物より目立ってはいけないことを示す。透明ケースや glossy surface は glare を起こすため、観察位置を想定して照明を調整する必要がある。

UI への変換:

- text と image の上に強い reflection を重ねない。
- dark background でも caption、button、path は十分な contrast を保つ。
- selected border の primary accent は、常時多用せず意思決定箇所だけに使う。
- disabled / loading / failed は色だけに頼らず、形、opacity、text でも区別する。
- glass panel の backdrop blur は 8-16px 程度を上限にし、文字可読性を優先する。

## Spatial Components For `/image_gen`

### Glass Vessel

画面全体を包む透明な容器。実装上は body background と fixed surfaces の関係で表現する。

- dark base に、ごく薄い vertical depth gradient を重ねる。
- 背景 grid は制作座標であり、展示装飾ではない。
- viewport edge に淡い highlight を置き、グラスの縁を暗示する。
- container は 1 枚の大きな card にしない。ページ全体を vessel として扱う。

### Central Atrium

folder selector、tabs、candidate count がある上部領域。Guggenheim / M+ の atrium と同じく、現在地と分岐を示す。

- height は詰めすぎず、主要 selector の視認性を優先する。
- tabs は展示 wing の切り替えとして明確にする。
- 現在の run は小さな caption ではなく、選択状態として読める。
- chat pane の存在は secondary accent で示し、main workspace より強くしない。

### Gallery Grid

request item の集合。美術館の展示室群。

- desktop は 2 columns、mobile は 1 column を維持する。
- card 間の gap は通路。候補画像の見比べ時に視線が詰まらない幅を確保する。
- card height は content に応じて伸びてよいが、candidate area は安定した aspect-ratio を守る。
- hover / select / loading で grid reflow を起こさない。

### Exhibition Wall

各 card 内の構成。

- top: item id、output path、lane。展示室番号と収蔵先。
- middle: prompt、reference。壁テキストと資料。
- visual: existing image と candidate。作品比較。
- action: single generate。展示室内の局所操作。
- state: selected、failed、loading。額装、空枠、照明状態。

### Curator Pane

right chat pane は、キュレーターとの相談室。

- 生成ログではなく、prompt 設計、reference 見直し、md 編集依頼、承認 UI に限定する。
- secondary accent を使い、main decision area から一段控える。
- user / assistant message は読み物として扱い、candidate image の比較領域に侵入しない。
- chat pane が狭いときは隠し、main gallery の比較性を優先する。

### Archive Counter

bulk footer。展示の出口であり、zip download と repo insertion を扱う。

- fixed bottom とし、grid scroll から独立する。
- destructive / adoption action は primary accent または明確な confirmation state を使う。
- zip download は非破壊、repo insertion は採用操作として視覚差をつける。
- footer 内で長文説明をしない。必要なら confirmation UI へ逃がす。

## UI Translation Matrix

| Museum concept | Research cue | `/image_gen` translation |
| --- | --- | --- |
| 透明な境界 | 金沢21世紀美術館の glass circle | pane、footer、selected frame の境界表現 |
| 光の濾過 | Louvre Abu Dhabi の多層 dome | progress、focus、selected state の控えめな光 |
| 中央アトリウム | Guggenheim Bilbao / M+ | folder selector と tabs の orientation area |
| 連続する作品世界 | teamLab Borderless | generation grid を連続する展示室群として扱う |
| interactive wall | Cleveland Gallery One / ARTLENS | candidate comparison wall と collection-like grid |
| collect action | Cooper Hewitt Pen | selected candidate、zip、repo insertion |
| 多人数/比較体験 | Cooper Hewitt tables / V&A interactives | 同一寸法候補、reference proximity、明確な選択状態 |
| glare control | lighting/accessibility guides | glass と reflection は text/image 上に重ねない |
| public forum | M+ platform / Kanazawa public zone | right chat pane と workspace の隣接 |
| quiet immersion | ARTECHOUSE / Superblue | 背景演出は低強度、操作密度を保つ |

## Visual Rules

### Color

既存の `visual-identity.md` を正とする。

- Base: `#0e1113`
- Surface: `#171b1f`
- Primary accent: `#8ee8ff`
- Secondary accent: `#f6d365`
- Divider: `rgba(255,255,255,0.12)`

追加ルール:

- glass highlight は white alpha 0.06-0.16 に抑える。
- reflection は diagonal shine ではなく、edge highlight と subtle surface gradient で表現する。
- selected candidate 以外で primary accent を面塗りしない。
- warning / failed は赤の面積を小さくし、candidate frame の安定性を優先する。

### Material

- `background: rgba(23, 27, 31, 0.72)` 程度の translucent surface を固定 UI に使う。
- `backdrop-filter` は使ってよいが、prompt text field と image preview の上では使わない。
- border は `1px solid rgba(255,255,255,0.10-0.16)` を基準にする。
- inner shadow は depth のために薄く使う。大きな glow は使わない。

### Lighting

- focus ring は sharp にし、glow で膨らませない。
- loading は skeleton shimmer より、progress line / dimmed frame / short status を優先する。
- selected state は primary accent border + small selected marker の二重表現にする。
- failed state は red text + preserved frame。画像枠を消さない。

### Typography

- museum caption 風にする場合も、本文は制作 UI の可読性を優先する。
- hero scale heading は使わない。
- path、item id、lane は metadata として小さく、ただし読める contrast を確保する。
- prompt editing area は monospaced に寄せすぎない。日本語 prompt の読みやすさを優先する。

### Motion

- museum-like transition は 120-180ms 程度に抑える。
- layout shift を起こす hover は禁止。
- candidate select は border / marker / subtle luminance change。
- generation completed は一瞬の highlight でよい。祝祭的な effect は不要。

## Interaction Density

先進的なミュージアムは、体験密度を高めても導線は単純に保つ。`/image_gen` は制作ツールなので、操作密度を下げすぎない。

- 常時見える操作: folder selector、asset / scene tabs、candidate count、single generate、bulk actions。
- card 内に閉じる操作: prompt edit、reference select、candidate select、single generate。
- footer に集約する操作: bulk generate、zip download、repo insertion。
- chat に逃がす操作: md 更新、prompt 設計相談、reference 方針の見直し。

避けること:

- candidate card 内に説明文を増やす。
- すべての metadata を常時大きく見せる。
- gallery grid の前に世界観説明 section を置く。
- right chat pane に generation job log を混ぜる。

## Design Checklist

- 透明感は、境界と階層を読むために使われているか。
- candidate image の 16:9 比較性は崩れていないか。
- prompt、reference、candidate、採用操作の因果関係が同じ card 内で読めるか。
- bulk footer は常に出口として機能しているか。
- selected / loading / failed が色だけに依存していないか。
- text と image の上に glare、blur、reflection が乗っていないか。
- right chat pane が作業ログ化していないか。
- mobile で chat pane を隠しても workflow が成立するか。
- primary accent が意思決定以外に漏れていないか。
- 背景演出が候補画像より目立っていないか。

## Summary For Implementation

`/image_gen` の美術館性は、装飾的な gallery theme ではなく、制作判断のための spatial system として実装する。透明なグラスは画面全体の容器、grid は展示室群、candidate area は展示壁、selected candidate は額装、bulk footer は収蔵カウンター、right chat pane はキュレーター相談室である。

実装では、暗色の制作管制卓を維持しながら、固定 UI にだけ glass material を使う。候補比較領域には透明効果を重ねず、光と反射は状態認識の補助にとどめる。これにより、「ユーザーの指示で何層にも広がる美術館」という世界観と、実務的な画像生成/比較/採用 workflow を両立できる。
