# ToC LP strategy

更新日: 2026-08-09

用途: ToC の LP 部門における、調査、情報設計、copy、proof、conversion、法務、accessibility、performance、検証の正本。

## 1. LP の仕事

LP は機能カタログではない。訪問者が次の順序で判断できる、一つの意思決定ページである。

```text
これは自分の問題だ
  -> 画像・動画を作る意味がある
  -> ToC なら制作の障壁を下げられる
  -> 提供形態と費用を理解できる
  -> proof と限界を確認できる
  -> 自分の用途で相談する
```

広告から来た場合は、広告で約束した persona、問題、価値、表現を Hero で一致させる。Google Ads の landing page guidance でも、広告との関連性、期待との一致、navigation の容易さ、mobile usability、上部の重要情報が重視されている。

## 2. Offer facts

- product: 企画、構成、画像、動画、音声、編集、品質確認を一つの流れにする ToC ビジュアル制作システム
- delivery: 顧客の利用環境へシステム一式を納品
- ToC monthly fee: 納品後 0 円
- external cost: AI model、image / video / voice generation、cloud 等の外部 API 料金は別途、使用量に応じて発生
- initial price: 未確定。公開までは `導入費用は個別見積り`
- support / updates: 必要な場合だけ範囲と料金を別途定義

表示単位:

```text
システム納品
導入費用：個別見積り

納品後の ToC 月額料金：0円
外部API料金：別途・使用量に応じて発生
```

`月額0円` を `無料` と言い換えない。外部 API 料金と初期導入費を同じ視界に置く。

## 3. 画像・動画が伝えられる情報的価値

画像・動画の価値は「目立つ」だけではない。言葉、図像、動き、音声、時間軸を目的に合わせ、情報を理解・判断・再利用できる形に変えることで生まれる。

| 情報価値 | 画像・動画でできること | 紹介ページで見せる根拠 |
|----------|------------------|------------------------|
| 抽象を可視化する | 概念、関係、世界観、見えない変化を図像と動きへ変える | 一行のテーマと完成 scene の対比 |
| 順序を理解させる | 手順、因果、before / after、時間変化を同じ時間軸で示す | production flow / tutorial example |
| 注意を案内する | narration、highlight、camera、字幕で「今どこを見るか」を揃える | 無音でも意味が取れる短い demo |
| 知識を記憶の手掛かりへ変える | 言葉と対応する visuals を組み合わせ、理解を支える | source -> script -> visual の対応 |
| 信頼の根拠を見せる | 操作、比較、制作過程、完成物を「実演」する | input、工程、output、費用、修正履歴 |
| 再利用できる資産にする | 長尺、Shorts、章、字幕、静止画へ再編集できる | 同じ brief から複数 format への展開 |
| 届く条件を広げる | caption、transcript により無音環境、聴覚差、検索・indexing に対応する | 字幕・transcript 付きの example |

Cambridge の multimedia learning research は、内容に対応する words と pictures の組合せが、words alone より深い理解を助け得ると説明する。一方で、無関係な装飾や情報過多は認知負荷を増やす。したがって `映像を増やす` ではなく、`伝えたい意味に必要な映像だけを設計する` を ToC の品質方針にする。

### Persona への翻訳

副業 persona:

```text
動画を作れる
  -> 商品、知識、企画を「反応を確かめられる形」で市場へ出せる
  -> 推測ではなく公開後の反応で次を判断できる
```

小規模ビジネス persona:

```text
画像・動画を作れる
  -> 商品、サービス、知識を見れば分かる形にできる
  -> 素材、表現基準、採用判断を事業へ蓄積できる
  -> 外注のたびに説明し直さず、改善・再利用できる
```

禁止する飛躍:

- 動画を作れば必ず売れる
- 視覚情報なら必ず記憶に残る
- AI が作れば人間の確認は不要
- 本数を増やせばブランドになる

## 4. ページ設計

共通 LP prototype の基本順序:

1. Hero: `あなたの想いを、映像に。` を入口に、visitor outcome と mechanism を順に見せる
2. Problem: 分断された tool と制作工程で、企画が完成しない
3. Informational value: 説明だけでは伝わりにくいものを、見れば分かる形へ
4. Mechanism: 一行の案から画像セットまたは完成動画までの制作の流れ
5. 顧客層の分岐: 副業 / 小規模ビジネス
6. Delivery and cost: システム納品、ToC 月額 0 円、外部 API 別途
7. Proof and boundary: 完成例、時間、human work、API cost、revision、human approval
8. 行動: 作りたい画像・動画を一行で入力して相談
9. Footer: 事業者情報、取引条件、privacy、外部 API 費用注記

mobile では各 section を `結論 -> 1 visual -> 根拠 -> 1 CTA` の順にし、横並びを前提にしない。primary CTA は一種類に揃え、ページ内の再掲は同じ action と label を使う。

## 5. Copy hierarchy

### Hero

```text
あなたの想いを、映像に。

一枚の画像から、一本の動画まで。

企画、構成、画像、動画、音声、編集を、ひとつの制作の流れへ。
ToC は、あなたが画像・動画を作り続けるためのシステム一式を納品します。

[作りたい画像・動画を一行で入力する]
```

最上部は `0秒: ブランドの言葉 -> 3秒: 制作範囲 -> 10秒: 実現方法` の順に見せる。`0秒` は内部設計用語であり、外向けの脳科学的主張には使わない。速度は信じる理由として下位へ置き、比較可能な実測が揃うまでは `画像も動画も、もっと速く、もっと簡単に。` を使う。

### Hero visual direction

最上部は、同じ事例の実在する依頼内容と採用済み完成物を一つの視界に置く。見出しや句点へ操作を加えず、依頼と完成物の対応自体を記憶点にする。最初の販売対象に合わせ、主実例は副業向け動画とし、画像一括生成の実例は制作範囲の証明として次に置く。

既存 draft `marketing/test/lp-proposal-01/drafts-before-section-design/01-hero.png` は、旧 functional headline、electric-blue の速度表現、floating process cards、actual proof に束縛されていない video mock を使っているため archive / comparison 用とする。新 Hero の実装正本にはしない。

変更後の原則:

- process diagram より actual input / output を先に見せる
- glow や粒子で AI 感を作らず、actual brief、contact sheet、video frame、proof metadata という制作物固有の語彙を使う
- copy、proof、action の3責務以外の装飾を first viewport から外す
- animation を待たなくても意味が成立する
- mobile では proof を H1 直後に置き、工程を横並びへ圧縮しない

Hero の offer note:

```text
納品後のToC月額 0円
※外部AI API料金は別途・使用量に応じて発生
```

### Informational value

```text
説明するだけでは伝わりにくいものを、
見ればわかる形へ。

知識の構造。商品の使い方。考え方の違い。変化の順序。
言葉・映像・音声を対応させ、相手が理解し、判断できる情報へ変えます。
```

### Delivery

```text
借り続ける制作サービスではなく、
作り続けるためのシステムを手元へ。
```

## 6. Proof contract

LP へ出す example は完成映像だけでなく、次を同じ card または detail page で示す。

- initial brief
- target audience / intended understanding
- output format / duration
- ToC が進めた工程
- 人間が決めた内容
- elapsed production time
- active human time
- external API cost
- revision count
- caption / transcript availability

実測が揃うまでは `圧倒的`、時間短縮率、費用削減率を公開しない。

### Claim-to-proof contract

| Claim | Required proof |
|-------|----------------|
| `あなたの想い` | actual initial brief / original text or theme |
| `映像に` | 同じ brief から作られた再生可能な accepted output |
| `人の心へ届く` | target audience / intended change。実際に届いたと断定する場合は audience response |
| `ひとつの制作フロー` | stage ownership、human decisions、revision history |
| `速く、簡単に` | elapsed time、active human time、comparison boundary |
| `続けられる` | second / third video で再利用した brief、asset、series rule |

Hero では少なくとも `actual brief -> accepted output -> creator acceptance` を満たす。actual output が mythology / folklore だけの場合は examples library へ置き、common Hero の primary proof にしない。

## 7. Conversion and measurement

主な問い合わせ行動:

`作りたい画像・動画を一行で入力する`

この共通ボタンの言葉はスレッド2の推奨案であり、最終承認は `workstream-handoffs.md` の引き継ぎ001でスレッド1へ依頼する。顧客層別の行動ボタンは上流の決定を使う。

フォームはサイト内に置き、最初に `作りたい画像・動画` を取り、顧客層と制作形式を別々に選ばせ、連絡先は後にする。Google Forms / Notion は正式な公開経路にしない。

minimum events:

- `view_lp`
- `view_information_value`
- `view_delivery_model`
- `select_customer_segment`
- `select_production_mode`
- `start_idea_input`
- `start_lead_form`
- `generate_lead`

検証順:

1. 1 秒テスト: `自分の想いを映像にするサービス` と理解できる
2. 3 秒テスト: 画像から動画までの制作範囲と、実在する依頼・完成物の対応を指差せる
3. 10 秒テスト: 統合制作システムの納品サービスであり、単純な月額 SaaS ではないと分かる
4. offer comprehension: 初期費用、月額 0 円、API 別途を正しく説明できる
5. persona message test
6. CTA click / form start
7. qualified lead / consultation quality
8. 実際の導入と継続制作

## 8. Accessibility / performance / legal

- video example は captions と transcript を用意する
- autoplay に音を付けない。pause control と reduced motion を用意する
- focus、contrast、heading structure、tap target を mobile 実機で確認する
- Core Web Vitals の LCP、INP、CLS を計測する
- Hero 動画は poster と軽量 fallback を持ち、最初の CTA を遅らせない
- 問い合わせフォームの個人情報利用目的を本人へ通知または公表する
- LP から有償契約を受け付ける場合は、特定商取引法上の表示、価格、追加費用、支払時期、提供時期、解約・返品条件、事業者情報を公開前に確認する

## 9. Research references

- [Google Ads: Optimize your ads and landing pages](https://support.google.com/google-ads/answer/6238826/optimize-your-ads-and-landing-pages?hl=en-GB)
- [Google Ads: Landing page experience](https://support.google.com/google-ads/answer/14086?hl=en)
- [Google Ads: Mobile landing pages](https://support.google.com/google-ads/answer/7543502?hl=en)
- [web.dev: Core Web Vitals](https://web.dev/articles/vitals?hl=en)
- [Cambridge: Multimedia learning excerpt](https://assets.cambridge.org/052183/8738/excerpt/0521838738_excerpt.htm)
- [W3C WAI: Video captions](https://www.w3.org/WAI/perspective-videos/captions/)
- [消費者庁: 通信販売](https://www.no-trouble.caa.go.jp/what/mailorder/)
- [個人情報保護委員会: 個人情報保護法ガイドライン](https://www.ppc.go.jp/personalinfo/legal/guidelines_tsusoku/)
