# ToC Six-Week GTM Experiment Calendar

更新日: 2026-08-10

この文書は YouTube を中心とした Workstream 3 の 6 週間 GTM 実験正本である。投稿量ではなく、`target / use case / output mode / obstacle / proof / CTA` の仮説を一つずつ判定する。

現行の全獲得実験は `marketing/SNS/audience-unit-registry.md` の `AU-001` を参照する。一つの行に別の persona や customer attribute を追加しない。

旧神話カレンダーは `content-calendar-legacy-mythology.md` に保存する。民話・神話は shared capability proof の一カテゴリであり、現行 content mix や channel identity を決めない。

## Readiness gate

Public acquisition experiment は、対象行について次がすべて `ready` の場合だけ開始する。

- `proof`: `marketing/SNS/proof-inventory.md` で `publish_ready`
- `offer`: Workstream 1 が claim / CTA / offer boundary を承認
- `destination`: Workstream 2 が persona-specific LP / form を承認
- `attribution`: source / campaign / content / UTM を CRM へ一方向で保存できる
- `follow_up`: 問い合わせへの owner、返信期限、consultation route が決まっている

一つでも欠ければ、公開・広告出稿へ進まず `blocked` として learning log に残す。behavior interview と直接商談 learning は、approved question / privacy boundary の範囲で先に開始できる。

## Scheduling rule

- 期間: 2026-08-10 から 2026-09-20
- 投稿日時は固定の成功法則として扱わず、YouTube Studio の実データが得られるまで hypothesis とする
- 同じ投稿・広告で `side_business` と `small_business_operator` を混ぜない。personal brand は small-business use case として分類する
- target と `image_batch|video` を別軸で記録し、画像を第三 persona にしない。再利用は両方に共通する強みとして記録する
- 2026-08-09 の owner decision により、Week 2-6 は `side_business` に集中する
- `small_business_operator` は Eコマース対応と事業別カスタマイズの要件整理が終わるまで獲得実験を延期する
- paid acquisition は Week 1-6 の既定施策に含めない
- 各週末に `marketing/SNS/gtm-learning-log.md` へ continue / revise / stop / blocked を記録する

## Six-week plan

| Week | Dates | Persona | Obstacle / question | Hypothesis | Proof / asset | Channel | CTA | Primary decision evidence | Current status |
|------|-------|---------|---------------------|------------|---------------|---------|-----|---------------------------|----------------|
| 1 | 2026-08-10 / 08-16 | shared readiness | 何を本当に証明できるか | claim を絞れば PRF-001 を capability proof にできる | `PRF-001` full render + process artifacts + `REQ-004` image classification | internal review | none | human approval、fresh QA、rights、time / cost metadata、image classification | `blocked_by_review` |
| 1B | 2026-08-10 / 08-16 | `AU-001` / side_business | 自分の想いを動画にしようとして、どこで止まるか | 5人の最近の行動を聞けば、共通する停止点と有償検討条件が分かる | `marketing/SNS/first-customer-interview-sprint.md` | direct interview | no sales pressure | recent attempt、common stopping point、actual alternative / burden、required proof | `ready_to_recruit` |
| 2 | 2026-08-17 / 08-23 | `AU-001` / side_business | 最初に売る動画用途と障壁を何に絞るか | 5人の匿名集計から、共通する停止点、実負担、必要な証拠を一つの提供仮説へ絞れる | Week 1B interview summaries | internal synthesis / allowed follow-up | none | repeated obstacle、actual alternative / burden、required proof、continue / revise / stop | `blocked_by_week_1b_evidence` |
| 3 | 2026-08-24 / 08-30 | `AU-001` / side_business | 自分の想いを最初の動画にできず検証できない | 想いと accepted first-video の対比は tutorial / tool explanation より具体的な相談を生む | side-business first-video case (`video`) | YouTube / Short / X, separate packages | `副業の最初のコンテンツを作る` | qualified video idea / consultation, not raw views | `blocked_by_proof_and_destination` |
| 4 | 2026-08-31 / 09-06 | `AU-001` / side_business | 完成物ではなく制作システムへ支払う理由はあるか | 納品範囲と人間の担当を具体化すれば、有償相談の障壁を特定できる | approved side-business proof + provisional delivery boundary | direct conversation / organic follow-up | `副業の最初のコンテンツを作る` | paid intent、required proof、price reaction、top objection | `blocked_by_offer_and_proof` |
| 5 | 2026-09-07 / 09-13 | `AU-001` / side_business | Week 2-4 の最大 objection | objection-specific proof は generic making-of より proposal intent を高める | side-business proof + objection response | winning organic channel + direct follow-up | approved side-business CTA | consultation completion、proposal intent、objection change | `blocked_by_week_4_evidence` |
| 6 | 2026-09-14 / 09-20 | `AU-001` / side_business | 再現可能な需要か | hook を変えず別 proof / audience sample でも有償需要が再現する | second approved side-business proof package | repeat winning channel | same approved CTA | qualified consultation、proposal、won-lost reason | `blocked_by_week_5_evidence` |

## Experiment package contract

Every public row materializes:

```text
audience_unit_id:
persona_id:
customer_attribute_id:
message_version:
persona:
output_mode:
use_case:
obstacle:
hypothesis:
proof_id:
claim_boundary:
hook:
content_format:
cta:
destination:
source / campaign / content / UTM:
primary_metric:
decision_rule:
result:
next_action:
```

## Packaging hypotheses

These are testable starting points, not approved public copy.

### Side-business

- transformation: 自分の想い -> accepted first video -> test begins
- proof first: 本人の言葉と完成動画を最初の5秒で対比する
- obstacle first: tool learning and fragmented operations prevent the first publish
- success signal: concrete idea and qualified consultation
- prohibited conclusion: income or view guarantee

### Small business operator

Status: deferred from the first six-week acquisition cycle.

- transformation: product / service / expertise -> accepted reusable image / video assets
- proof first: one concrete business use case plus accepted items and reuse evidence
- obstacle first: no dedicated production function、outsourcing resets context、production stops
- success signal: concrete business use case and qualified consultation
- prohibited conclusion: automatic lead growth、sales、trust、or brand growth
- personal brand remains one owner-expertise use case inside this target

## Decision rules by week

No invented conversion benchmark is used before a baseline exists.

| Week | Continue | Revise | Stop / remain blocked |
|------|----------|--------|-----------------------|
| 1 | fresh QA、rights、human public approval が揃い、allowed claim が確定 | human change request が具体化し、修正後 review が可能 | rights blocked、または public quality を満たせない |
| 2 | 副業層 5 interviews が完了し、recent behavior に基づく repeated obstacle、actual alternative / spend、proof requirement が得られる | problem はあるが question が hypothetical answer しか生まない | recent attempt、priority、actual alternative が見つからない use case |
| 3 | readiness gate 完了後、attributable な concrete idea または qualified consultation が生まれる | target response はあるが proof / hook / CTA の一要素が理解を妨げる | proof または destination が未準備、または non-target response だけ |
| 4 | 実際の支出経験、導入時期、必要 proof、許容できる人間作業が確認できる | 課題はあるが納品範囲または説明が不明確 | 無料利用への関心だけで、有償の system delivery を検討しない |
| 5 | top objection に対する理解または proposal intent の変化が interview / consultation で確認できる | objection は残るが deliverable な追加 proof で検証可能 | objection が現行 offer で安全に解消できない |
| 6 | independent sample でも qualified signal と主要 objection pattern が再現する | signal はあるが source / proof 依存で再現しない | 再現せず、または paid scale gate が未完了。paid acquisition は開始しない |

## Supporting content

PRF-001 may be used only after approval as supporting shared-capability content:

- one-line public-domain story title -> 5:42 long-form render
- regeneration / human review process
- what the system did and what humans decided

Do not use it as the default persona proof, revenue proof, brand consistency proof, or speed comparison.

## Weekly decision

At the end of each week:

1. write actual evidence to `marketing/SNS/gtm-learning-log.md`
2. choose exactly one of `continue / revise / stop / blocked`
3. change only one of proof / hook / CTA in a revision test
4. return offer / qualification questions to Workstream 1
5. return message / destination questions to Workstream 2
