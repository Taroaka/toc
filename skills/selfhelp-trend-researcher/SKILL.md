---
name: selfhelp-trend-researcher
description: |
  Research notable self-help or business personalities, produce a candidate slate, and shape one person into a cautious, source-aware script outline.
  Use when: the user asks for trending self-help figures, business personalities, motivational influencers, or source-aware profile ideas with explicit verification TODOs and uncertainty handling.
---

# Self-help Trend Researcher（ネタ収集その2）

## Overview

「世界で話題の自己啓発系人物」を制作向けに整理する。
ここでの価値は “断定” ではなく、**候補リスト + 検証TODO + 60秒紹介に落とせる骨格**。

## When to Use

- 「最近話題の自己啓発系の人を紹介したい」
- 「億万長者になった/ビジネスで成功した人で、ポッドキャストで影響力がある人物を調べたい」

## Clarify（最初に確認）

未指定なら仮定して進める（仮定は明示）。

- 対象地域/言語: global / 英語圏 / 日本語圏 など
- 対象領域: 起業/投資/習慣/健康/メンタル/キャリア（複数可）
- トーン: 批判も扱う/ポジ寄り/中立
- “話題”の定義: 直近6〜24ヶ月 / SNS / podcastランキング / 書籍ベストセラー など
- NG: 露骨な煽り、誹謗中傷、医療/投資の断定助言

## Research policy（Hybrid）

### Webが使える場合

最低限これらを横断して “候補と出典候補” を集める:
- podcastディレクトリ（Apple Podcasts / Spotify / YouTube 等）
- 本人の公式サイト/プロフィール
- 信頼できる紹介記事（大手メディア/出版社/講演主催者）
- Wikipedia/Encyclopedia（あれば）

### Webが使えない場合

以下を “未検証” として出力し、ユーザーにリンク貼り付けを依頼して精査する:
- 話題の根拠（ランキング/記事/出演）
- 資産/収入/肩書の真偽
- 論争点（批判/炎上/詐欺疑義など）の一次情報

## Output（slate）

8〜12人の候補を、各1ブロックで出す。

- name（表記ゆれ/別名があれば併記）
- one_liner（何者か、何で話題か）
- where_to_find（podcast名/番組/主要プラットフォーム）
- core_claims（主張の柱 3つ）
- why_people_listen（人気理由/刺さる悩み）
- critiques（反証・批判の論点 2〜4）
- “billionaire” label: `Verified|Reported|Claimed|Unknown`
  - Verified: 公的/信頼できる根拠がある
  - Reported: 大手メディア等の報道だが一次は未確認
  - Claimed: 本人/周辺の主張のみ
  - Unknown: 不明（触れない方が良い）
- verification_todo（確認すべき点）
- sensitivity_notes（名誉毀損回避: 断定しない、ソースが揃うまで断言しない）

## Output（deep_dive: 1人）

### 1) 60秒紹介の構成（台本骨格）

- hook（最初の3秒）
- who（何者）
- claim（何を言う人か）
- proof/context（なぜ広まったかの根拠候補）
- critique（注意点/反証）
- takeaway（視聴者が持ち帰る指針）
- sources_to_check（URLが無ければ出典名）

### 2)（任意）ToC research YAML（互換）

`workflow/research-template.yaml` に沿って、人物紹介を “ストーリー化” して落とす。
不確かな点は `metadata.confidence_score` を下げ、TODOを残す。

## Guidelines（安全）

- 事実断定は避ける（資産、犯罪/詐欺疑義、医療・投資）
- 私的情報/ドクシングは扱わない
- 視聴者に不利益が出やすい領域は「一般論 + 注意喚起」に留める
