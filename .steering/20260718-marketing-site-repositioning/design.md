# ToC marketing site repositioning design

更新日: 2026-07-18

## Positioning

### Category

個人向け AI 動画制作システム。

### Functional promise

`動画制作を、圧倒的に速く、簡単に。`

`圧倒的` は公開時に実測で裏付ける。比較可能な所要時間、人間の実作業時間、担当工程、完成物が揃うまでは `動画制作を、もっと速く、もっと簡単に。` を使用する。

### Emotional promise

`作りたいと思った瞬間を、完成まで止めない。`

### Transformational promise

- 速いから試せる
- 簡単だから続けられる
- 続けられるから副業やブランドへ育てられる

### Mechanism

テーマを起点に、企画、調査、構成、台本、scene、画像、動画、ナレーション、編集、品質確認を一つの制作フローとして組み立てる。複数の生成サービスを人間が一つずつ操作する負担を減らし、人間は目的、品質、公開判断へ集中する。

## Audience architecture

### Persona A: 副業を始めたい個人

- job: 限られた時間と予算で最初の動画を完成させ、反応を検証し、継続可能な収益の種を作る
- barrier: 編集スキル不足、ツール過多、時間不足、外注費、失敗への不安
- desired emotion: `難しそう` から `自分にも作れそう`、`まず 1 本試したい` へ
- primary CTA: `副業の最初の1本を作る`
- destination: `/for-side-business`

### Persona B: 個人ブランドを構築したい個人

- job: 自分の知識、経験、思想、世界観を、一貫して継続できる動画発信へ変える
- barrier: 発信停止、制作時間、外注の不統一、没個性的な AI 表現、自分らしさの毀損
- desired emotion: `伝えたいのに形にできない` から `自分の価値を継続的に見せられる` へ
- primary CTA: `自分のブランド動画を設計する`
- destination: `/for-personal-brand`

2 ペルソナを一つの広告、Hero、LPへ混ぜない。共通トップだけ、動画を作った先の未来を尋ねて分岐させる。

## Message hierarchy

1. visitor outcome: 副業またはブランドを前へ進められる
2. product value: 動画を速く、簡単に、継続して作れる
3. mechanism: 分断された制作工程を ToC がつなぐ
4. proof: 完成動画、入力テーマ、担当工程、所要時間、人間の作業時間、修正回数
5. technical detail: agent、provider、pipeline は希望者向けの下層ページで説明する

民話・神話は proof library の一カテゴリであり、positioning、Hero、primary persona にしない。

## Affect and intuitive design

`右脳設計` は外部向けの科学的主張ではなく、内部の設計略語として扱う。

意味:

- 説明を読む前に変化が分かる
- visitor 自身の止まっていた企画が動く感覚を作る
- 機能一覧より、入力から完成への変化を先に見せる
- 偽の希少性、恐怖、過剰な収益保証は使わない

共通感情遷移:

```text
制作の重さ・停滞
  -> 一行から動き出す驚き
  -> 自分にもできるという解放
  -> 完成を想像する期待
  -> 最初の一歩を自分で選ぶ
```

## Public site information architecture

```text
/
├── /for-side-business
├── /for-personal-brand
├── /examples
├── /how-it-works
├── /contact
├── /privacy
└── /thanks
```

Meta / SNS campaigns send each persona directly to its dedicated LP. The common home page is for brand, organic, comparison, and returning visitors.

## Home page structure

1. Hero: common promise
2. `Idea-to-Video Line`: one-line theme becomes a finished timeline
3. persona split: side business / personal brand
4. three values: speed / simplicity / repeatability
5. proof library
6. workflow comparison
7. human judgment and quality
8. persona CTA

### Hero draft

```text
動画制作を、圧倒的に速く、簡単に。

テーマを伝えるだけで、企画、台本、映像、ナレーション、編集まで。
ToC は、複雑な動画制作を一つの流れに変えます。

[自分なら何を作れるか見る]
[制作事例を見る]
```

## Signature interaction

The single memorable visual is `Idea-to-Video Line`.

```text
一行のテーマ
  -> 構成
  -> 台本
  -> scene
  -> visual / voice
  -> completed timeline
```

Do not scatter decorative motion. Reduced-motion users receive the same transformation as a static sequence.

## Visual direction

Theme: `アイデアが、一気に動画へ走り出す制作レーン。`

- Base Ink: `#172033`
- Canvas: `#F5F6F2`
- Action Blue: `#315BE8`
- Momentum Orange: `#FF6A3D`
- Success Mint: `#72D6B2`
- Muted Steel: `#9AA5B5`

Typography:

- display: `Dela Gothic One`
- body: `Zen Kaku Gothic New`
- process/data: `IBM Plex Mono`

Avoid generic purple AI gradients, mythic ornaments, dashboard-first heroes, and ungrounded numerical claims.

## Conversion design

Common CTA flow:

```text
何を作りたいですか
  -> 副業 / ブランド構築
  -> テーマを一行で入力
  -> 利用方法または相談を案内
```

The input is carried into the site-native form. Do not send the visitor to Google Forms or Notion.

## Measurement

- `select_persona`
- `start_idea_input`
- `complete_idea_input`
- `view_example`
- `view_how_it_works`
- `start_lead_form`
- `generate_lead`
- `lead_persona`
- `lead_source`

Primary business metrics:

- persona LP -> idea input rate
- idea input -> lead completion rate
- qualified lead rate by persona
- first-video start rate
- first-video completion rate
- continuation / second-video intent

