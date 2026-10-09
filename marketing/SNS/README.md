# ToC SNS Marketing Guide

更新日: 2026-08-10

`marketing/SNS/` は、ToC の価値をチャネルごとに証明し、persona-specific LP と利用開始へ接続する配信正本を置く。

## Channel job

SNS は完成画像・動画を並べるだけの作品棚でも、投稿内で直接売り切る販売ページでもない。

```text
0秒の約束: あなたの想いを、映像に。
出力範囲: 一枚の画像から、一本の動画まで。
見せる証拠: 一行の想い -> accepted image set / completed video
信じる理由: 速く、簡単で、繰り返せる制作フロー
次の行動: persona-specific CTA
```

brand line は共通の入口であり、各投稿は persona 固有の obstacle、proof、CTA へ具体化する。同じ文言を全投稿へ機械的に付けず、入力した想いと完成映像の対比で意味を見せる。

- ToC なら画像・動画制作を速く、簡単に進められることを見せる
- visitor が自分にも作れそうだと感じる proof を渡す
- 副業または小規模ビジネスの専用 LP へ送る
- 完成物だけでなく、入力、output mode、制作過程、所要時間、人間の判断を見せる

## Primary personas

| Persona | 最初に動かす感情 | 見せる変化 | CTA |
|---------|------------------|------------|-----|
| 副業を始めたい個人 | 停滞から解放、自己効力感 | 限られた時間でも最初のコンテンツを完成できる | 副業の最初のコンテンツを作る |
| 小規模ビジネス運営者 | 伝達可能性、信頼、継続への確信 | 商品、サービス、知識を改善・再利用できる画像・動画資産へ変える | ビジネスの画像・動画制作を設計する |

同じ投稿で両方へ訴求しない。投稿、広告、プロフィールリンク、LP の persona を一致させる。

## Current acquisition priority

2026-08-09 の owner decision により、最初の販売・獲得対象は `side_business` とする。

顧客本人の言葉では、`自分の想いを動画にしたい人` と定義する。ここでいう想いには、自分の経験、知識、物語、企画、伝えたい価値観を含む。表向きは共通 brand line `あなたの想いを、映像に。` で入口を作る。

内部の適合条件は、`副業として発信や反応検証をしたい`、`具体的なテーマがある`、`制作負荷によって完成・公開できていない` の3点とする。感情に刺さる入口と、販売対象を見極める条件を混同しない。

`small_business_operator` は将来の primary target として保持するが、最初の獲得施策には含めない。現行 ToC の物語・コンテンツ制作能力は副業層の発信検証に近く、小規模ビジネスへ売るには Eコマース寄りの表現、商品・導線との接続、事業ごとのカスタマイズが追加で必要になる、という product-fit 仮説に基づく。

したがって、当面の投稿、面談、proof、CTA、LP 送客、直接商談は副業向けへ集中する。小規模ビジネス向けの資料と計測軸は削除せず、後続市場の検証を再開できる状態で保持する。

ペルソナと顧客属性の組は `marketing/SNS/audience-unit-registry.md` で管理する。現行は `AU-001` の一組だけを active とし、今後の対象は既存定義の置換ではなく、新しい ID の追記で増やす。

## Content pillars

### 1. Proof

- 入力した一行
- accepted image set / completed video
- elapsed time / human working time
- ToC が担当した工程
- 人間が判断した工程
- 修正前後

### 2. Speed and simplicity

- 従来の分断された制作と ToC の比較
- 企画、台本、scene、映像、音声、編集が一つにつながる様子
- ツール操作ではなく、画像セットまたは動画を完成させる流れ

### 3. Persona outcomes

- 本業後でも最初のコンテンツを試せる
- 一つの商品、サービス、専門知識から series を作れる
- 集客、説明、顧客教育、採用で再利用できる画像・動画資産を蓄積できる
- 作った動画から反応を得て次を改善できる

### 4. Build in public

- 失敗、改善、品質判断を具体的に見せる
- `完全自動で完璧` と言わない
- 人間の目的設定と承認を隠さない

民話・神話は proof の一カテゴリとして利用できるが、SNS 全体の positioning にはしない。

## Post design rules

- 冒頭1秒で visitor 自身の変化を見せる
- agent / model / provider 名を主語にしない
- 1投稿は1 target、1 use case、1 output mode、1 obstacle、1 proof、1 CTA
- `稼げる` を保証せず、低い制作負担で検証回数を増やせる価値を伝える
- small-business persona には速さだけでなく業務適合、再利用、一貫性、人間の判断を見せる
- CTA は dedicated LP と一致させる

## Funnel

```text
persona-specific post / ad
  -> dedicated LP
  -> one-line image / video idea
  -> native form
  -> qualified lead
  -> consultation
  -> proposal
  -> closed won / lost
  -> system delivery
  -> first accepted output
  -> next output
```

## Current channels

- YouTube: long-form proof, making-of, product education
- Shorts / Reels / TikTok: one-line-to-video transformation and before/after
- X: production logs, comparisons, lessons, idea testing
- Meta ads: persona-specific acquisition after LP and measurement are ready

## Current operating files

- SNSアカウントと使用スキル：[accounts.md](accounts.md)（Instagram・TikTok：`eiyu_no_tabi`）

- persona / customer-attribute registry: `marketing/SNS/audience-unit-registry.md`
- first five-customer interview sprint: `marketing/SNS/first-customer-interview-sprint.md`
- proof inventory / claim boundary: `marketing/SNS/proof-inventory.md`
- production / human-review proof requests: `marketing/SNS/proof-requests.md`
- behavior-based customer interview: `marketing/SNS/customer-interview-guide.md`
- six-week experiment calendar: `marketing/SNS/YouTube/content-calendar.md`
- weekly hypothesis / result / decision: `marketing/SNS/gtm-learning-log.md`
- YouTube community / CRM: `marketing/SNS/YouTube/community-crm-strategy.md`
- web / CRM / delivery measurement: `marketing/SNS/YouTube/analytics-kpis.md`

Channel-specific instructions must inherit `marketing/README.md`. Campaign artifacts such as Urashima upload copy do not replace the product positioning.
