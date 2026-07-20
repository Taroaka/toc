# ToC Marketing Guide

更新日: 2026-07-19

`marketing/` は、ToC を必要な個人へ届け、利用開始、継続、収益化またはブランド構築へ接続するための正本を置く。

## Marketing North Star

ToC は、個人の動画制作を圧倒的に速く、簡単にする AI 動画制作システムである。

```text
速いから試せる。
簡単だから続けられる。
続けられるから、副業やブランドへ育てられる。
```

### Functional promise

`動画制作を、圧倒的に速く、簡単に。`

`圧倒的` は、従来制作と ToC の所要時間、人間の実作業時間、担当工程、完成物を比較できる場合だけ公開コピーに使う。実測前は `動画制作を、もっと速く、もっと簡単に。` とする。

### Emotional promise

`作りたいと思った瞬間を、完成まで止めない。`

### Why ToC

一般的な AI 動画制作では、人間が企画、台本、scene、画像、動画、音声、編集のサービスを行き来する。ToC はこれらを一つの制作フローとして組み立て、人間が目的、品質、公開判断へ集中できるようにする。

神話、民話、物語は ToC の商品テーマではない。制作能力を検証し、長尺ストーリーも作れることを示す proof / example の一カテゴリとして扱う。

## Primary personas

### A. 副業を始めたい個人

- 限られた時間と予算で最初の動画を完成させたい
- 編集スキル、ツール過多、外注費、継続できない不安が障壁
- 欲しい結果は、反応を検証できる動画と継続可能な収益の種
- 感情遷移は `難しそう -> 自分にも作れそう -> まず1本試したい`
- primary CTA は `副業の最初の1本を作る`

### B. 個人ブランドを構築したい個人

- 知識、経験、思想、世界観を動画として継続発信したい
- 制作時間、外注の不統一、没個性的な AI 表現、発信停止が障壁
- 欲しい結果は、一貫した動画資産と `この分野ならこの人` という認知
- 感情遷移は `形にできない -> 自分らしく作れそう -> 続けられる -> ブランドになる`
- primary CTA は `自分のブランド動画を設計する`

2 ペルソナを同一の広告や LP へ丸めない。共通サイトでは動画を作った先の目的で分岐させ、広告は専用 LP へ直接送る。

## Affect / intuitive design rule

内部で使う `右脳設計` は、外部向けの脳科学的主張ではない。説明を読む前に visitor が変化を理解し、自分の企画が動き出す可能性を感じるための設計略語である。

| 原則 | 実務ルール |
|------|------------|
| 主語は visitor の未来 | agent や provider より、作れる・続けられる・育てられるを先に置く |
| 説明より変化 | 機能一覧より、一行のテーマが完成動画へ進む様子を見せる |
| 速さより解放 | 秒数だけでなく、制作の重さから解放される感覚を作る |
| 簡単さより自己効力感 | `初心者向け` ではなく `自分にも完成させられる` を渡す |
| CTA は自己決定 | 副業かブランドか、何を作りたいかを visitor が選ぶ |
| 感情と操作を分ける | 偽の希少性、収益保証、恐怖、誇大な実績を使わない |

## Funnel

```text
Meta / YouTube / SNS / search
  -> persona-specific LP or common site
  -> one-line video idea
  -> native form / consultation / onboarding
  -> first video
  -> continued creation
  -> side-income validation or brand growth
```

- Meta 広告は副業向けとブランド構築向けを分ける
- YouTube は ToC の完成物、制作過程、速さ、簡単さを証明する
- public site は positioning、比較、proof、conversion の正本
- フォームはサイト内に実装し、入力した動画テーマを引き継ぐ
- Notion / Google Forms は canonical route にしない

## Source of truth

- Marketing North Star: this file
- Public site / LP: `marketing/LP/`
- Persona / message contract: `marketing/LP/personas.md`
- SNS distribution: `marketing/SNS/`
- YouTube channel strategy: `marketing/SNS/YouTube/strategy.md`
- Repositioning decisions: `.steering/20260718-marketing-site-repositioning/`

Campaign 固有の浦島太郎、民話、神話の upload copy / publish kit は個別 artifact であり、この North Star を上書きしない。

## Scope boundary

marketing guidance は public site、LP、広告導線、SNS配信、リード獲得、反応分析、改善に適用する。通常の ToC research、story、script、image、narration、video generation の制作仕様へ流用しない。

## Directory structure

```text
marketing/
├── README.md
├── browser-use.md
├── LP/
└── SNS/
```

- `LP/`: 独立した公開サイト、共通LP、ペルソナ別LP、native form の正本
- `SNS/`: public site へ送客し、ToC の価値を proof する各チャネルの正本
- `browser-use.md`: 管理画面操作が必要な marketing task の共通ガイド
