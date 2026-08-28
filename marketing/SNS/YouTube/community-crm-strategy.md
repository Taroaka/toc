# ToC YouTube Community and CRM Strategy

更新日: 2026-08-08

この文書は、YouTube のコメント、概要欄、About、問い合わせ返信を、視聴者の反応と creator intent の学習へつなぐ現行正本である。

## Purpose

```text
viewer response
  -> 何が理解・感情として残ったかを学ぶ

creator intent
  -> 自分なら何を映像にしたいかを学ぶ
  -> persona-specific route
  -> approved qualification
  -> consultation / proposal / won-lost learning
```

YouTube 内で売り切ろうとしない。相手が十分な情報を理解し、実際に自分で次の行動を選べる状態を作る。

## Identity and voice

- brand entrance: `あなたの想いを、映像に。`
- 主語は AI model / agent ではなく creator / visitor の未来
- tone は近く、率直で、具体的。失敗と human judgment を隠さない
- `完全自動`、`AIが全部作った`、収益保証、偽の希少性を使わない
- `AIを一緒に育てる初期メンバー` を現行 audience identity にしない
- feedback を求める場合も、売り手が欲しい行動を「相手が自分で選んだように見せる」操作をしない

## Two kinds of community signal

### Viewer response

Questions:

- `いちばん印象に残った場面はどこでしたか？`
- `この動画で残った感情を一つ挙げるなら何ですか？`
- `説明が分かりにくかった箇所はありましたか？`

Use for:

- creative / clarity improvement
- intended understanding / affect と actual response の差
- proof package の viewer-response evidence

Viewer response alone is not a qualified sales lead.

### Creator intent

Questions:

- `あなたなら、何を映像にしたいですか？`
- `最初の1本を作るなら、どんなテーマを試したいですか？`
- `商品、サービス、知識を動画にするなら、誰に何を伝えたいですか？`
- `必要なのは複数画像、動画、その両方のどれですか？`

Use for:

- side-business / small-business の self-selection。personal brand は owner-expertise use case として記録する
- concrete image / video idea and reuse intent
- repeated obstacle and objection learning

Public comments に private brief や連絡先を書かせない。個別相談へ進む場合は approved site-native form を案内する。

## Persona-specific routing

| Signal | Route | CTA |
|--------|-------|-----|
| 限られた時間で最初のコンテンツを作り、反応を試したい | side-business LP | `副業の最初のコンテンツを作る` |
| 商品、サービス、顧客教育、採用、owner expertise を画像・動画資産にしたい | approved small-business LP | `ビジネスの画像・動画制作を設計する` |
| 目的がまだ決まっていない | common site persona selection | `自分なら何を作れるか見る` |
| 作品への感想・改善提案 | YouTube comment thread | one concrete viewer-response question |

同じ投稿、概要欄、固定コメントから両 persona の CTA を同時に並べない。投稿で約束した persona と destination を一致させる。

## Surface roles

| Surface | Job |
|---------|-----|
| banner / About | common brand line と、想いから映像への変化を説明する |
| video opening | original idea と completed output を対応させる |
| description | content persona と一致する一つの CTA / LP を置く |
| pinned comment | viewer response または creator intent の一問だけを置く |
| replies | 相手の言葉を復唱し、必要な場合だけ次の一問を返す |
| site-native form | private idea、persona、minimum contact、consent を安全に受け取る |

## Pinned comment patterns

### Viewer-response pattern

```text
ここまで見てくれてありがとうございます。
この動画でいちばん印象に残った場面を、一つだけ挙げるならどこでしたか？
映像、語り、テンポで分かりにくかったところもあれば教えてください。
```

### Creator-intent pattern: side-business

```text
この一本は、一行のテーマから企画、映像、音声、編集までをつないで制作しました。
あなたが最初の一本で試してみたいテーマを、一言で表すなら何ですか？
個人的な内容や連絡先はコメントに書かず、相談する場合は概要欄の副業向けページを使ってください。
```

### Creator-intent pattern: small-business

```text
商品、サービス、知識は、伝わる形にならなければ顧客や採用候補者から見えません。
あなたのビジネスで、動画にすると伝わりやすくなるものを一言で表すなら何ですか？
個人的な内容や連絡先はコメントに書かず、相談する場合は概要欄の小規模ビジネス向けページを使ってください。
```

## Inquiry follow-up

1. 相手の画像・動画 idea / purpose を一文で復唱する
2. `反応を試す最初のコンテンツ` か `事業で改善・再利用する画像・動画資産` かを確認する
3. intended audience、desired change、current obstacle、timing を一つずつ確認する
4. Workstream 1 の approved qualification に従って route を決める
5. 適合する場合だけ consultation を案内し、適合しない場合も理由を誠実に伝える
6. audience_unit_id / persona_id / customer_attribute_id / message_version / source / campaign / content / persona / use_case / output_mode / outcome を CRM に記録する
7. repo には匿名集計と objection summary だけを返す

Do not:

- 収益、再生数、ブランド成長を保証する
- offer / price / support boundary を独自に変更する
- private brief を public comment で求める
- pressure、fake scarcity、fear を使う
- generic sales greeting だけを返す

## Reply standard

- first response は `ありがとうございます` だけで終わらず、相手の具体語を一つ拾う
- viewer response には作品の意図または改善判断を返す
- creator intent には private detail を深掘りせず、適切な route を示す
- criticism に反論せず、どこでそう感じたかを確認する
- spam / harassment / unrelated promotion は platform policy に従い整理する

## CRM stages and privacy

Use the states in `analytics-kpis.md`:

```text
new lead
  -> qualified / disqualified
  -> consultation booked / completed
  -> proposal sent
  -> closed won / lost
  -> delivery started / completed
  -> first / next accepted output
```

- raw PII、raw idea、CRM ID、hashed email、contract details を analytics platform または repo へ送らない
- source / campaign / content / UTM / landing path は form submit 時に CRM へ一方向で保存する
- repo へ戻すのは audience unit / use_case / output_mode / source / campaign / content 単位の集計と匿名 objection のみ

## Weekly learning

毎週 `marketing/SNS/gtm-learning-log.md` へ次を返す。

- viewer response の repeated pattern
- creator intent の target / use_case / output_mode / obstacle pattern
- qualified / disqualified の集計
- consultation / proposal / won-lost の集計
- top objections / lost reasons
- continue / revise / stop / blocked
- Workstream 1 / 2 への handoff
