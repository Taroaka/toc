# Glass 03: Museum Architecture Research

## Purpose

この調査は、ガラス建築、美術館、ギャラリー、展示照明、没入型展示の原則を `/image_gen` UI に翻訳するための設計メモである。

対象コンポーネント:

- `topbar`: run / folder / 現在地を示す入口
- `controls`: tab、filter、candidate count、generate 操作
- `grid`: request item 群を並べる展示室
- `candidate`: 画像候補の額装と比較面
- `footer`: download / repo insertion の収蔵カウンター
- `chat pane`: 制作判断を相談するキュレーター室

## Research Sources

長い引用は避け、公式情報、博物館・財団・設計ガイド、専門機関の公開資料を中心に参照した。

### Glass Architecture / Daylight

- Toledo Museum of Art, Campus & Architecture: https://toledomuseum.org/about/campus-architecture
- Toledo Museum of Art, GAPP Residency: https://toledomuseum.org/learn/gapp-residency
- Toledo Museum of Art, In a New Light: https://toledomuseum.org/exhibitions/in-a-new-light-impressionism-and-post-impressionism
- Fondation Cartier and architecture: https://www.fondationcartier.com/en/building
- Fondation Cartier, Diller Scofidio + Renfro exhibition: https://www.fondationcartier.com/programme/exposition/diller-scofidio-renfro
- Louvre Abu Dhabi Architecture: https://www.louvreabudhabi.ae/en/about-us/architecture
- Menil Collection, Main Building: https://www.menil.org/campus/main-building
- Menil Collection, Cy Twombly Gallery: https://www.menil.org/campus/cy-twombly-gallery

### Exhibition Lighting / Accessibility / Labels

- Getty Conservation Institute, Museum Lighting Research: https://www.getty.edu/projects/museum-lighting-research/
- Getty Publications, Museum Lighting: https://www.getty.edu/conservation/publications_resources/books/museum_lighting.html
- Practical Guide for Sustainable Climate Control and Lighting in Museums and Galleries: https://www.nla.gov.au/sites/default/files/2022-02/Practical-guide-for-sustainable-climate-control-and%20lighting-in-museums-and-galleries.pdf
- Smithsonian Guidelines for Accessible Exhibition Design: https://affiliations.si.edu/wp-content/uploads/PDFs/Accessible-Exhibition-Design.pdf
- Western Australian Museum, Text and Labels in Museum Exhibitions: https://museum.wa.gov.au/research/development-service/text-and-labels-museum-exhibitions

### Interactive / Immersive Exhibition

- Cleveland Museum of Art, ArtLens Gallery: https://www.clevelandart.org/artlens-gallery
- Cleveland Museum of Art, ARTLENS Gallery press release: https://www.clevelandart.org/about/press/cleveland-museum-art-introduces-artlens-gallery-touchscreen-free-approach-integrating
- Cleveland Museum of Art, ArtLens App: https://www.clevelandart.org/digital-innovations/artlens-app
- Cooper Hewitt, What is the Pen?: https://support.cooperhewitt.org/hc/en-us/articles/203903068-What-is-the-Pen
- Cooper Hewitt, Using the Pen: https://www.cooperhewitt.org/exhibitions/using-the-pen/
- Cooper Hewitt Labs, The Pen: https://labs.cooperhewitt.org/tag/the-pen/
- Smithsonian, Immersion Room: https://www.si.edu/exhibitions/immersion-room-event-exhib-5434
- Mori Building / teamLab Borderless press release: https://www.mori.co.jp/en/company/press/release/2023/12/20231201140000004579.html

## Governing Thought

最高峰の展示空間は、透明性を「見せびらかす素材」ではなく、境界、採光、視線、回収行為、静けさを調停する仕組みとして使う。`/image_gen` でも glass / reflection / light は装飾ではなく、候補画像を比較し、採用し、会話で判断するための情報建築に限定する。

## Findings

### 1. Glass Is A Relationship System

Toledo Museum of Art の Glass Pavilion は、外壁と多くの内壁をガラスにし、ガラス作品、スタジオ、教育、展示を同じ建築言語でつなぐ。Fondation Cartier の Jean Nouvel 建築は、庭と都市への開き、反射、光の変化を展示条件そのものにした。Louvre Abu Dhabi は幾何学的な dome で光を濾過し、建築が展示体験の環境装置になる。

UI への示唆:

- glass は `topbar`、`footer`、`chat pane`、selected `candidate` frame のような「関係を示す境界」に使う。
- prompt textarea や candidate image 本体をガラス化しない。読む面、見る面、判断する面は安定した solid surface に置く。
- 透明感は、背後を見せることより「隣接レイヤーの存在が分かる」程度でよい。
- 反射は 1px rim、inner highlight、淡い edge sheen に留める。

### 2. Daylight Is Filtered, Not Dumped

Louvre Abu Dhabi の dome は強い日射を直接入れるのではなく、層状の構造で濾過する。Menil の Cy Twombly Gallery は、屋根、布、壁面で自然光をやわらげる。Getty や照明ガイドは、視認性と保存性、glare 回避、光源選定のバランスを重視する。

UI への示唆:

- `selected`、`loading`、`failed` は画面全体の発光ではなく、該当領域の照度変化として表す。
- reflection overlay を画像や長文テキストの上に置かない。
- `topbar` と `footer` は光の band を持ってよいが、candidate comparison より明るくしない。
- progress は pulse や shimmer を強くせず、candidate frame 内の控えめな light sweep にする。

### 3. Circulation Comes Before Spectacle

美術館の導線は、入口、分岐、展示室、出口、休憩・相談の関係で成立する。Menil は住宅地に馴染む外観と内側の広がりを両立し、Fondation Cartier は都市や庭との境界を柔らかくした。ArtLens App は館内位置と作品探索を結び、迷いを減らす。

UI への示唆:

- `/image_gen` の導線は `topbar -> controls -> grid -> candidate -> footer` の順序を崩さない。
- `chat pane` は別アプリのログ窓ではなく、main gallery に隣接する相談室として扱う。
- `footer` は展示後の収蔵・搬出カウンターなので、grid scroll に埋め込まない。
- `controls` は展示 wing の分岐であり、装飾的な小型 chip 群にしすぎない。

### 4. The Frame Is A Decision Device

展示の額装は、作品を飾るだけでなく、どれを見ているか、どれが採用候補かを明確にする。Cooper Hewitt の Pen は wall label を収集点にし、ArtLens は壁面、app、collection data を連動させる。展示体験では「見る」と「持ち帰る」が接続される。

UI への示唆:

- `candidate` frame は選択状態、失敗状態、生成中状態を担う主装置にする。
- selected border は primary accent を使うが、全候補に常時使わない。
- existing image は旧展示、generated candidate は新展示として、frame tone を分ける。
- `footer` の repo insertion は「保存」ではなく「採用・収蔵」なので、download より強い視覚的責任を持たせる。

### 5. Captions Should Attach Meaning Without Becoming The Exhibit

Smithsonian や Western Australian Museum の label guidance は、読みやすさ、対象との対応、短い見出し、glare 対策を重視する。展示キャプションは作品理解を助けるが、過剰なテキストは作品体験を奪う。

UI への示唆:

- path、lane、request id は展示キャプションとして扱い、画像比較より弱く置く。
- 長い prompt は編集面として十分な contrast と安定背景を持たせる。
- button label は短い動詞にする。説明文で操作を補わない。
- error caption は短く、原因分類と次アクションだけを出す。
- filename は reference thumbnail のそばに置き、視覚対象との関係を切らない。

### 6. Quiet Immersion Beats Full-Screen Spectacle

teamLab Borderless は、作品が部屋を越えて関係し、鑑賞者の動きに反応することで没入感を作る。Cleveland ArtLens や Cooper Hewitt Immersion Room は、インタラクションを作品理解や保存行為につなぐ。制作 UI では、この没入性を全画面演出ではなく、比較・選択・回収の流れに翻訳する必要がある。

UI への示唆:

- background は静かな奥行きに留め、candidate grid を主役にする。
- hover は浮遊や拡大より、rim、shadow、luminance の微差で示す。
- animations は state transition の理解に限定する。
- chat pane は没入空間の音声ガイドではなく、判断の文脈を保持する低刺激な補助層にする。

## Component Translation Matrix

| Architecture / exhibition concept | Spatial role | `/image_gen` component | UI translation |
| --- | --- | --- | --- |
| glass facade | 内外の関係を見せる境界 | `topbar` | 背景が少し透ける navigation glass。現在の run を入口として明確化する。 |
| transparent interior walls | 隣室の気配を残す | `grid` | card 間 gap を通路として一定化し、隣の request item が視野に入る余白を保つ。 |
| filtered daylight | 作品を読むための光 | `candidate` | selected / loading / failed を frame 内の照度差で表す。画像本体には filter をかけない。 |
| atrium | 現在地と分岐 | `topbar` + `controls` | folder selector、tabs、candidate count を上部に集約し、探索の起点にする。 |
| gallery circulation | 入口から出口までの順路 | whole layout | `topbar -> controls -> grid -> footer` を固定し、chat pane は隣接室として置く。 |
| exhibition wall | 作品、説明、資料の関係 | grid card | item id、path、prompt、reference、existing image、candidate を 1 card 内に収める。 |
| picture frame | 見る対象と選択対象の分離 | `candidate` | 16:9 frame を固定し、selected border を採用意思の唯一強い signal にする。 |
| wall label | 作品理解の入口 | metadata / caption | path と lane は muted text、error は短文、reference name は thumbnail 近接。 |
| collect action | 観覧後に持ち帰る | `footer` | download は非破壊、repo insertion は採用・収蔵として視覚差を出す。 |
| interactive wall | 一覧、探索、比較 | `grid` | candidate を同寸法・同操作で並べ、比較のリズムを作る。 |
| immersive room | 体験が連続する | `grid` + `chat pane` | card 群と会話を同じ制作文脈に置き、派手な背景演出に逃がさない。 |
| conservation lighting | glare と疲労を抑える | all text / media | glass reflection は text/image 上に重ねず、contrast と focus state を優先する。 |

## Component Rules

### Topbar

`topbar` は美術館の入口、案内板、中央アトリウムを兼ねる。

- glass strength: medium。背景を少し通すが、selector の読みやすさを最優先する。
- hierarchy: current run を最も明確にし、secondary path は muted にする。
- reflection: top edge に細い highlight。大きな shine は置かない。
- motion: folder selection change は短い fade / border transition でよい。
- risk: 透明度を上げすぎると現在地が読めない。`topbar` は装飾より orientation を優先する。

### Controls

`controls` は展示 wing の分岐と、生成条件の調整卓である。

- tabs は `asset` / `scene` の大きな分岐として見せる。
- sub-filter は展示室内の棚割りとして `chara -> obj -> asset` の順序を保つ。
- candidate count は照明卓の dimmer に近く、数値変更の効果が隣接して読める配置にする。
- generate action は primary accent を使ってよいが、常時発光させない。
- risk: chip を増やしすぎると展示 label の群れになる。頻出操作だけを前面に出す。

### Grid

`grid` は展示室群であり、比較の体験そのもの。

- desktop 2 columns、mobile 1 column を維持する。
- card gap は通路。狭めて情報密度だけを上げない。
- card は nested card にせず、展示壁として 1 枚のまとまりにする。
- loading / failed / selected で card size を変えない。
- empty state は短く、入口に戻る導線を示す。

### Candidate

`candidate` は作品であり、額装であり、採用判断の場である。

- image area は 16:9 fixed。
- image の opacity、blur、glass overlay は避ける。
- selected frame は primary cyan rim と細い outer glow。
- failed frame は red rim + short caption。空枠を残して layout を守る。
- existing image は archive frame、new candidate は active frame として tone を分ける。
- multiple candidates は同じ寸法、同じ操作、同じ metadata rhythm で並べる。

### Footer

`footer` は展示出口の archive counter。

- fixed bottom とし、grid scroll から独立させる。
- download は neutral / secondary、repo insertion は adoption / primary。
- destructive risk がある action は confirmation state を持つ。
- glass strength は topbar より強くてよいが、candidate より目立たせない。
- footer text は短くし、説明が必要な場合は modal / confirm に逃がす。

### Chat Pane

`chat pane` は制作判断を相談するキュレーター室。

- main workspace より一段控えた warm accent を使う。
- generation logs は流さない。prompt 設計、reference 見直し、md 編集依頼、承認に限定する。
- message body は readable solid surface。glass は pane frame と header に限定する。
- narrow viewport では隠し、gallery comparison を優先する。
- risk: chat が強くなりすぎると制作 UI が会話アプリになる。主役は candidate と prompt。

## Material Guidance

### Transparency

- navigation glass: `rgba(23, 27, 31, 0.62-0.72)`
- dock glass: `rgba(23, 27, 31, 0.76-0.86)`
- content card: `rgba(18, 22, 25, 0.90-0.96)`
- prompt textarea: `rgba(16, 20, 23, 0.94-0.98)`
- media overlay: 原則なし。必要な selected chip のみ `rgba(0, 0, 0, 0.42-0.56)`

### Reflection

- use: rim light、inner top highlight、selected border、focus ring
- avoid: diagonal shine over image、large white gradient、text-backed glare、moving reflection loop
- selected: cyan rim は候補採用に限定
- chat: warm amber rim は会話領域に限定
- error: red rim と short text を併用し、色だけに依存しない

### Light

- ambient: dark base + subtle grid
- focus: border luminance, not full-card glow
- loading: localized soft sweep inside frame
- disabled: opacity + text + cursor/state
- success: selected frame and footer adoption state

### Quietness

- no oversized hero treatment inside app
- no decorative glass bubbles, orbs, bokeh, or gradient blobs
- no marketing copy in comparison area
- no animated background behind candidate images
- no heavy backdrop blur behind long prompt text

## Implementation Checklist

- `topbar` answers: which run am I in?
- `controls` answer: which request class and how many candidates?
- `grid` answers: which items need review?
- each card answers: what prompt, which references, what existing output, what new candidates?
- `candidate` answers: which image is selected?
- `footer` answers: what will be exported or inserted?
- `chat pane` answers: what decision or instruction is being discussed?
- glass is used only for boundaries, docks, and frames.
- text surfaces remain solid enough to read.
- image surfaces remain unfiltered for judgment.
- hover, focus, loading, failed, selected do not reflow layout.

## Design Risks

| Risk | Why it matters | Safe direction |
| --- | --- | --- |
| Too much glass | prompt と画像評価の可読性が落ちる | glass は navigation / dock / frame に限定 |
| Too much reflection | museum glare と同じ問題を UI 上で起こす | text/image 上に反射を重ねない |
| Immersion as spectacle | 比較判断より背景演出が勝つ | grid と candidate を主役にする |
| Weak orientation | run / tab / count が見失われる | topbar と controls を atrium として明確化 |
| Decorative captions | metadata が情報ノイズになる | caption は短く、対象に近接させる |
| Adoption ambiguity | download と repo insertion の重みが混ざる | footer 内で非破壊 / 採用操作を視覚分離 |

## Final Direction

`/image_gen` の museum-glass UI は、透明なガラスの中に展示室が広がる見た目ではなく、透明素材を使って「どこにいて、何を比較し、何を採用し、何を相談しているか」を静かに読ませる設計にする。ガラスは境界、光は状態、額装は選択、キャプションは認知負荷の削減、footer は収蔵、chat pane はキュレーター室として扱う。
