# ToC brand site conversion design

更新日: 2026-08-09

## Subject / audience / page job

- subject: 一行の想いを、必要な画像または完成動画へ変えるビジュアル制作システム
- audience: 共通サイトは副業に取り組む個人と小規模ビジネス運営者。主導線は、具体的なテーマがあるが制作負担で止まっている副業向け動画制作
- single page job: 訪問者が `一枚の画像から一本の動画まで作れる` と理解し、自分の案を一行入力する

## Hero thesis

```text
Headline
  あなたの想いを、映像に。

Visible proof
  副業向けの actual initial brief -> accepted completed video

Next action
  visitor 自身の一行を入力する
```

工程数や AI provider は thesis にしない。速さと簡単さは visible transformation を信じる reason-to-believe として下位へ置く。

## Direct Proof Pair

H1 は静かに読ませ、同じ事例の actual brief と accepted output を同時に見せる。input-output relation 自体を page の記憶点とする。

- actual brief を UI placeholder にせず、公開可能な原文として見せる
- output は同じ brief から生まれた accepted artifact に限定する
- input と output の間は simple arrow / transition で補助できるが、animation を理解の前提にしない
- glow、粒子、句点 interaction、floating cards、複数の scroll animation は使わない

## Visual system

| Role | Token | Use |
|------|-------|-----|
| Canvas | `#F5F6F2` | 静かな背景 |
| Ink | `#172033` | copy / frame / controls |
| Signal Blue | `#315BE8` | active line / link / primary control |
| Proof Mint | `#72D6B2` | accepted / verified proof state のみ |
| Muted Steel | `#9AA5B5` | metadata / inactive timeline |

- display: `Dela Gothic One` を `映像に。` へ限定
- headline / body: `Zen Kaku Gothic New`
- timecode / proof metadata: `IBM Plex Mono`

font の差は `想い -> 映像` の変換を符号化する。display face を長文や button へ広げない。

## Layout

Desktop:

```text
┌─────────────────────────────────────────────────────────┐
│ ToC                                      nav             │
├─────────────────────────┬───────────────────────────────┤
│ あなたの想いを、        │ INPUT / actual brief          │
│ 映像に。                │          ↓                    │
│ 一枚の画像から、        │ OUTPUT / [actual artifact]     │
│ 一本の動画まで。        │                               │
│ 実現方法                │                               │
│ [current approved CTA]  │                               │
│ offer facts             │                               │
└─────────────────────────┴───────────────────────────────┘
```

Mobile:

```text
ToC
あなたの想いを、
映像に。
[actual video poster / short muted preview]
INPUT: actual brief
一枚の画像から、一本の動画まで。
実現方法
[current approved CTA]
offer facts
```

Mobile で工程を横並びに縮小しない。proof video と source brief を H1 の直後に置き、visitor outcome / mechanism / action の順に一列で続ける。

## Motion

- initial content は animation 完了を待たず読める
- video preview は muted / inline / user-paused controls を持つ
- transition を使う場合も一度だけ短く行い、actual input / output は常時見える
- `prefers-reduced-motion` では transition を省き、同じ input-output relation を保つ
- scroll / hover へ意味を依存させない

## Proof gate

Hero proof の required fields:

- original brief bytes / approved public excerpt
- target audience / intended change
- completed video file and poster
- creator acceptance
- human-owned decisions
- ToC-owned stages
- elapsed time / active human time / API cost は計測できた項目だけ
- public use rights

神話・民話は実例集で使えるが、共通サイトの主実例にはしない。副業向けの採用済み動画が無い間は状態を `blocked_missing_side_business_video_proof` とする。

## Conversion continuity

- 共通サイト: 実例 -> 一行入力 -> 顧客層 -> 制作形式 -> 最小確認 -> 連絡先 -> 同意
- 顧客層別ページ: 顧客層を保持 -> 一行入力 -> 制作形式 -> 最小確認 -> 連絡先 -> 同意
- visitor の input を消さず、form / thanks / follow-up へ引き継ぐ
- instant video generation のように見せない。入力後の action は相談 / 導入案内であると明示する

## Acceptance

- 1 秒: `自分の想いを映像にするサービス` と理解できる
- 3 秒: 画像から動画まで作れる範囲と、actual input / output の対応を指差せる
- 10 秒: 統合制作システムの納品サービスで、月額 SaaS ではないと説明できる
- proof が架空 UI / stock video ではない
- primary CTA と offer note が最初の viewport または直後にある
- keyboard / reduced motion / caption / poster fallback が成立する
