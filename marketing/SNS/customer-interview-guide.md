# ToC Customer Interview Guide

更新日: 2026-08-10

この文書は、`side_business` / `small_business_operator` の actual behavior、current alternative、obstacle、paid intent を理解するための Workstream 3 interview guide である。personal brand は small-business の owner-expertise use case として分類する。売り込み、offer 確定、qualification 変更を目的にしない。

最初の5人の募集、日程、匿名進行、判断は `marketing/SNS/first-customer-interview-sprint.md` を使う。

## Initial sample

- side-business: matching people 5 interviews in the first cycle
- small-business operator: first-cycle recruitment is deferred。後続検証用の質問は保持する
- first-cycle inclusion: 自分の経験、知識、物語、企画、価値観のいずれかを動画にしたい
- first-cycle qualification context: 副業として発信・反応検証をしたく、具体的なテーマがあり、制作負荷で完成または公開が止まっている
- `想いがありますか` だけで選ばず、直近の制作行動と停止点を確認する
- sample が少ない間は percentage を一般化せず、repeated pattern と具体的な反証を残す

## Opening

```text
今日は商品を売るためではなく、自分の想いを動画にしようとしたときに実際に何が起きたかを知るためにお話を聞かせてください。
正解はありません。答えたくない質問は飛ばせます。
個人が特定されない形で、共通する課題だけを集計してもよいですか？
```

Consent が得られなければ記録しない。録音する場合は別に明示許可を取る。

## Core behavior questions

未来の理想より、直近の具体的行動から聞く。

1. `最後に自分の想いを動画にしたいと思ったのは、いつ、何を伝えたいときでしたか？`
2. `そのとき、実際に最初に何をしましたか？`
3. `完成または中断まで、どんな tool、人、外注を使いましたか？`
4. `いちばん時間や気力を使った工程はどこでしたか？`
5. `途中で止まった場合、どの瞬間に何が障壁になりましたか？`
6. `これまで画像・動画制作へ支払った費用や、支払おうと検討した選択肢はありますか？`
7. `完成した画像や動画を何に使う予定でしたか？実際にはどう使いましたか？`
8. `次の制作をしなかった / できなかった理由は何ですか？`
9. `その問題を解決する優先度が上がるのは、どんな出来事が起きたときですか？`
10. `必要だったのは複数画像、動画、その両方のどれでしたか？なぜその形式でしたか？`

Avoid:

- `AIで全部作れたら欲しいですか？`
- `速く簡単なら買いますか？`
- `月額0円なら魅力的ですか？`
- `いくらなら買いますか？` だけで終わる hypothetical pricing question

## Side-business follow-up

1. `試したかった niche / channel / format は何でしたか？`
2. `続けるか止めるかを、どんな反応で判断する予定でしたか？`
3. `最初の検証へ使える時間と費用を、実際にはどの程度確保しましたか？`
4. `編集を学ぶ、toolを組み合わせる、外注する、何もしない、の中で何を選びましたか？なぜですか？`
5. `収益が出る前でも、最初の一本と反応検証に有償で投資した経験はありますか？`

Do not ask or imply guaranteed income.

## Small-business follow-up

1. `画像や動画にしたかった商品、サービス、顧客教育、採用、専門知識のどれに近いですか？`
2. `今は営業、文章、SNS、資料、講座、外注など、どの形で伝えていますか？`
3. `伝わらない / 品質が信用に足りない / 外注のたびに説明が戻ると感じた具体例はありますか？`
4. `複数本で再利用したい business knowledge、tone、visual identity、approval rule はありますか？`
5. `画像・動画制作が止まると、顧客理解、問い合わせ前説明、採用、信頼形成にどんな影響がありますか？`
6. `外注または制作 tool に継続して支払った経験はありますか？何が継続・解約の理由でしたか？`
7. `運営者本人の知識や信用を前面に出す personal-brand use case ですか、それとも商品・サービス・組織を主語にしますか？`

## Proof reaction

Unprompted behavior questions の後だけ proof を見せる。`PRF-001` は publish-ready になるまで外部 interview で使用しない。

Ask:

1. `この入力と完成物の間で、信じにくい部分はどこですか？`
2. `自分のテーマで試す前に、何を確認したいですか？`
3. `品質、手間、自分らしさ、費用、所有、運用の中で最大の不安はどれですか？`
4. `この proof はあなたの目的に近いですか？近くないなら何が違いますか？`
5. `次の行動を取らない理由があるとすれば何ですか？`

## Price and paid-intent learning

Workstream 3 does not set price. Ask about observed tradeoffs:

- current tool / outsourcing / active-time cost
- last amount actually paid or approved for a similar outcome
- whether the problem has a budget owner
- expected timing for a paid decision
- what evidence or condition is required before paying

Record price reaction as evidence for Workstream 1. Do not promise a price, discount, or package not approved by Workstream 1.

## Objection codes

| Code | Meaning |
|------|---------|
| `quality` | 公開できる品質か |
| `identity` | 自分らしさ / brand consistency が失われないか |
| `effort` | 自分の作業や学習がどれだけ必要か |
| `reliability` | 毎回完成するか、修正できるか |
| `ownership` | system、source、asset、account、data の所有 |
| `setup` | 導入や環境構築が難しくないか |
| `cost` | 導入費、API費、保守費が見合うか |
| `timing` | 今取り組む優先度がない |
| `proof_fit` | 事例が自分の用途に近くない |
| `other` | 上記以外。具体的に匿名要約する |

## Anonymized interview record

```yaml
interview_id: INT-YYYYMMDD-001
audience_unit_id: AU-001
persona_id: P-001
customer_attribute_id: CA-001
message_version: MV-001
persona: side_business|small_business_operator
use_case: "e.g. personal_story|knowledge_explainer|original_story|idea_commentary|other"
output_mode_needed: image_batch|video|unclear
current_behavior:
  last_video_attempt: "anonymous summary"
  current_alternative: ""
  completion_status: completed|stopped|not_started
  largest_obstacle: ""
  active_time_or_cost: "only if voluntarily shared"
desired_progress: ""
paid_intent:
  actual_previous_spend: "bucket or not_shared"
  decision_timing: ""
  evidence_required: ""
objections: []
proof_reaction: "not_shown|anonymous summary"
qualification_revision_suggestion: ""
workstream_1_handoff: ""
workstream_2_handoff: ""
```

Raw interview notes and PII do not belong in this repository. `gtm-learning-log.md` receives only aggregated patterns.

## After five interviews for one audience unit

For each target, report:

- repeated obstacle count
- strongest current alternative
- actual paid behavior
- proof required before consultation
- top three objections
- disconfirming evidence
- recommended continue / revise / stop
- proposed handoff to Workstream 1 / 2
