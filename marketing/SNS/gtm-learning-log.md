# ToC GTM Learning Log

更新日: 2026-08-10

この文書は、Workstream 3 の hypothesis、evidence、objection、decision、upstream handoff を匿名・集計レベルで残す正本である。

## Privacy boundary

Do not record:

- 氏名、email、電話番号、会社名など個人を直接特定する情報
- raw image / video idea や private brief
- CRM record ID、raw / hashed email、contract details
- private conversation の全文

Record only:

- audience_unit_id、persona_id、customer_attribute_id、message_version、use_case、output_mode、source、campaign、content、UTM の集計
- 匿名化・要約した obstacle / objection / lost reason
- funnel count、rate、decision
- Workstream 1 / 2 が判断に使える evidence

## Decision values

- `continue`: 同じ hypothesis を追加 sample で検証する
- `revise`: target / use case / output mode / obstacle は維持し、proof / hook / CTA の一要素だけ変える
- `stop`: evidence が否定した、または readiness gate を満たせない
- `blocked`: upstream decision、proof、LP、delivery readiness を待つ

## Experiment template

```yaml
experiment_id: EXP-YYYYMMDD-001
period: YYYY-MM-DD/YYYY-MM-DD
audience_unit_id: AU-XXX
persona_id: P-XXX
customer_attribute_id: CA-XXX
message_version: MV-XXX
persona: side_business|small_business_operator
output_mode: image_batch|video
use_case: ""
obstacle: ""
hypothesis: ""
proof_id: PRF-XXX
claim_boundary: ""
channel: youtube|shorts|x|meta|direct_interview|direct_sales
hook: ""
cta: ""
destination: ""
tracking:
  source: ""
  campaign: ""
  content: ""
  utm: ""
readiness:
  proof: ready|blocked
  offer: ready|blocked
  destination: ready|blocked
  attribution: ready|blocked
results:
  sample_or_sessions: 0
  idea_inputs: 0
  leads: 0
  qualified: 0
  consultations: 0
  proposals: 0
  closed_won: 0
  closed_lost: 0
  first_image_batch_completed: 0
  first_video_completed: 0
  next_output_started: 0
  second_video_started: 0
evidence:
  objections: []
  lost_reasons: []
  notes: ""
decision: continue|revise|stop|blocked
decision_reason: ""
handoff:
  workstream_1: ""
  workstream_2: ""
next_test: ""
```

## Current learning

### LRN-20260808-001: proof readiness audit

- persona: shared capability
- evidence: one 342.148-second final render exists for 浦島太郎
- limitation: fresh QA、human approval、rights、time / cost、creator acceptance are missing
- decision: `blocked`
- reason: no artifact currently satisfies the `publish_ready` contract
- Workstream 1 handoff: do not use speed、customer outcome、viewer impact claims from this artifact yet
- Workstream 2 handoff: common Hero proof selection is blocked until an approved brief-to-output pair exists
- Workstream 3 next test: complete `PRF-001` review request and commission persona-specific proof

### LRN-20260808-002: acquisition readiness

- persona: side_business / small_business_operator kept separate
- evidence: persona-specific LP URL and publish-ready proof are not confirmed in this workstream
- decision: `blocked`
- reason: paid traffic would create unmeasurable or mismatched demand
- next test: behavior interviews and direct sales learning may start using approved questions; public acquisition waits for destination and proof gates

### LRN-20260808-003: target architecture handoff

- upstream decision: Workstream 1 confirmed `side_business` and `small_business_operator` as the two primary targets
- classification: `personal_brand` is a small-business owner-expertise use case, not a third persona
- Workstream 3 action: proof、experiment、interview、CRM、analytics fields were projected to the confirmed target architecture
- capability action: output mode is recorded separately from target; `image_batch` does not become a third persona
- Workstream 2 handoff: update persona destination、form / event contract、and CTA to the approved small-business route
- decision: `revise`
- next test: keep results separate by target and validate the first small-business use case through interviews before narrowing the offer

### LRN-20260808-004: image-volume evidence boundary

- evidence: `PRF-001` contains 261 image files across the run
- limitation: requested、generated、reference、variant、rejected、accepted、and delivered images are not classified
- decision: `blocked`
- reason: raw filesystem count cannot support a public accepted-image or `大量生成` claim
- Workstream 1 handoff: no image-volume claim until `REQ-004` returns a defined boundary
- Workstream 2 handoff: image proof slot must show accepted items and intended destinations, not a raw file count
- next test: complete image classification and request one target-specific image-batch case

### LRN-20260809-005: first beachhead owner decision

- owner decision: 最初の販売・獲得対象を `side_business` とする
- product-fit rationale: 現行 ToC の物語・コンテンツ制作能力を活かしやすく、最初の発信と反応検証へ直接つなげられる
- deferred target: `small_business_operator`
- deferral hypothesis: 小規模ビジネスへ売るには、物語中心の表現から Eコマース寄りの表現、商品・導線との接続、事業別カスタマイズを追加する必要がある
- decision: `continue`
- Workstream 1 handoff: beachhead、offer、価格、納品境界の正本を副業優先へ更新する
- Workstream 2 handoff: 共通サイトから副業向け導線を主導線にし、小規模ビジネス向け導線は後続市場として保持する
- Workstream 3 action: Week 2-6 の面談、proof、organic acquisition、直接商談を副業層へ集中する
- next test: 副業層 5 interviews で、最初に売る用途、出力形式、直近の支出、必要 proof を絞る

### LRN-20260809-006: customer-language definition

- owner decision: 最初の顧客を、本人の言葉では `自分の想いを動画にしたい人` と表現する
- meaning of 想い: 自分の経験、知識、物語、企画、伝えたい価値観
- public entrance: `あなたの想いを、映像に。`
- internal fit: 副業として発信・反応検証をしたい、具体的なテーマがある、制作負荷で完成または公開できていない
- primary output: `video`
- decision: `continue`
- Workstream 1 handoff: side-business target definition and first-offer hypothesisへ反映する
- Workstream 2 handoff: Hero の直後で説明を増やしすぎず、本人の言葉と完成動画の対比で自分事化させる
- next test: 面談で `想い` のどの種類が直近の制作行動と有償検討へ結びついているか確認する

### LRN-20260809-007: additive audience architecture

- owner decision: 一つの販売・獲得単位を `1 persona x 1 customer attribute` とする
- active unit: `AU-001` = `P-001 自分の想いを動画にしたい人` x `CA-001 副業として発信・反応検証に取り組む個人`
- architecture decision: 新しい対象は既存定義の全入れ替えではなく、新しい ID と registry row の追記で増やす
- history rule: 実験済み ID の意味を変更・再利用・削除しない
- decision: `continue`
- Workstream 1 handoff: target / persona architecture へ stable ID と append-only rule を反映する
- Workstream 2 handoff: LP / form / event で `audience_unit_id`、`persona_id`、`customer_attribute_id`、`message_version` を保持する
- Workstream 3 action: calendar、interview、proof、CRM、analytics は `AU-001` を参照して開始する

## Active experiment

### EXP-20260810-001: first five-customer interviews

```yaml
experiment_id: EXP-20260810-001
period: 2026-08-10/2026-08-16
audience_unit_id: AU-001
persona_id: P-001
customer_attribute_id: CA-001
message_version: MV-001
persona: side_business
output_mode: video
use_case: first_personally_meaningful_video
obstacle: "具体的な想いはあるが、制作負荷で完成・公開できない"
hypothesis: "最近の制作行動を持つ5人から、共通する停止点と有償検討に必要な証拠が見つかる"
proof_id: none
claim_boundary: "面談では商品成果を主張せず、最近の行動だけを聞く"
channel: direct_interview
hook: "自分の想いを動画にしようとして、途中で止まった経験"
cta: "25〜30分の行動面談に参加する"
destination: direct_scheduling_outside_repository
tracking:
  source: direct_recruitment
  campaign: first_customer_interviews_20260810
  content: warm_or_community_or_social
  utm: none
readiness:
  proof: ready
  offer: blocked
  destination: ready
  attribution: ready
status: ready_to_recruit
decision: continue
decision_reason: "Proofや広告を待たずに、匿名・非販売の行動面談を開始できる"
next_test: "5人の面談を完了し、続行・修正・中止または保留を判定する"
```

## Weekly review template

```text
Week:
Decisions confirmed:
New evidence:
Invalidated hypothesis:
Top objections by target / use case / output mode:
Funnel counts by target / use case / output mode / source:
Continue / revise / stop:
Blocker / owner:
Workstream 1 handoff:
Workstream 2 handoff:
Next experiment:
```
