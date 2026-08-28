# ToC proof, acquisition, and sales learning requirements

更新日: 2026-08-09

## Goal

Workstream 3 として、実在する ToC の証拠を公開可能性ごとに棚卸しし、persona-specific proof、organic acquisition、直接商談、提案、受注・失注、継続制作までを一つの学習ループにする。legacy の神話中心運用を現行 product acquisition から分離し、根拠のない claim や raw views 最適化へ戻らない運用正本を作る。

## Success criteria

1. `marketing/SNS/proof-inventory.md` が実在 artifact、証明できること、証明できないこと、公開 gate を記録する
2. `marketing/SNS/proof-requests.md` が production / human review へ必要な evidence package を渡せる
3. `marketing/SNS/YouTube/content-calendar.md` が 6 週間の仮説検証カレンダーになり、旧神話カレンダーが legacy artifact として分離される
4. `marketing/SNS/gtm-learning-log.md` が persona、obstacle、proof、CTA、商談、proposal、won-lost、判断を記録できる
5. `community-crm-strategy.md` が現行 primary personas、誠実な自己決定、persona-specific route、privacy-safe CRM に従う
6. 浦島太郎を product category や persona proof として過大評価しない
7. publish-ready proof がない状態で paid acquisition を開始しない
8. Workstream 1 の offer / qualification と Workstream 2 の LP copy を独自に変更しない
9. target と `image_batch|video` を別軸で記録し、image proof の requested / generated / accepted / rejected / variant を分離する。再利用は第三の production mode にしない
10. `1 persona x 1 customer attribute = 1 audience unit` とし、将来の対象は既存定義の置換ではなく registry への追記で増やす

## Confirmed evidence

- `output/浦島太郎_20260208_1515_immersive/render/final/urashima_taro_full_compiled.mp4` は実在する
- media metadata は 342.148 秒、1280x720、24 fps、H.264 / AAC stereo
- 同 run には MP4 109 files、image 261 files、audio 291 files が存在する
- image 261 files は raw filesystem count であり、accepted unique image 数や公開可能な volume claim ではない
- existing `run_report.md` は 2026-05-02 生成、final render は 2026-05-03 更新で、run report は final render QA の fresh evidence ではない
- human public approval、creator acceptance、rights check、elapsed / active human time、API cost、comparison baseline は未確認
- 浦島太郎は system capability の候補 proof だが、side-business / small-business customer outcome の proof ではない
- `output/シンデレラ_20260808_1934` は research review failure で downstream generation が blocked され、proof として利用できない
- 2026-08-09 owner decision: 最初の販売・獲得対象は `side_business`
- customer-language decision: `自分の想いを動画にしたい人`。内部では副業目的、具体的テーマ、制作停止の行動条件で適合を判定する
- active audience unit: `AU-001` = `P-001 自分の想いを動画にしたい人` x `CA-001 副業として発信・反応検証に取り組む個人`
- `small_business_operator` は、Eコマース寄りの表現、商品導線、事業別カスタマイズの要件整理まで獲得実験を延期する

## In scope

- `marketing/SNS/README.md`
- `marketing/SNS/proof-inventory.md`
- `marketing/SNS/proof-requests.md`
- `marketing/SNS/gtm-learning-log.md`
- `marketing/SNS/customer-interview-guide.md`
- `marketing/SNS/YouTube/content-calendar.md`
- `marketing/SNS/YouTube/content-calendar-legacy-mythology.md`
- `marketing/SNS/YouTube/community-crm-strategy.md`
- `marketing/SNS/YouTube/community-crm-strategy-legacy-test-channel.md`
- `marketing/SNS/YouTube/engagement-strategy-single-upload.md`
- `marketing/SNS/YouTube/strategy.md`
- `marketing/SNS/YouTube/analytics-kpis.md`
- 本 steering directory

## Out of scope

- `marketing/README.md` と `marketing/go-to-market.md` の変更
- `marketing/LP/` の変更
- production pipeline、output artifact、動画の再生成・修正
- 公開、広告出稿、外部連絡、CRM への実データ入力
- price / offer / qualification の独自決定
- public brand / channel name の決定

## Decision rule

- artifact が実在しても、fresh QA、human approval、rights、claim metrics が揃わなければ `publish_ready` にしない
- raw image file count を `大量生成` や採用画像点数へ読み替えない
- persona-specific proof が揃うまでは、mythology proof を acquisition の主軸にしない
- 最初の6週間は `side_business` に集中し、`small_business_operator` を同一施策へ混ぜない。`personal_brand` は small-business use case として後続検証へ保持する
- public CTA destination が未完成なら paid acquisition を開始せず、behavior interview と直接商談 learning を優先する
