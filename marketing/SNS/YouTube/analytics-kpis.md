# ToC marketing analytics and KPIs

更新日: 2026-08-09

## 1. Measurement principle

Views and clicks are diagnostic metrics. The main question is whether the right individual moves from interest to a real image / video idea, qualified consultation, paid decision, successful delivery, and continued creation.

Keep `side_business` and `small_business_operator` results separate at every step. `personal_brand` is recorded as a small-business use case, not a primary persona.

### Audience identity contract

`marketing/SNS/audience-unit-registry.md` is the source of truth for acquisition identity. Every non-shared event and CRM state records:

- `audience_unit_id`
- `persona_id`
- `customer_attribute_id`
- `message_version`

Current acquisition uses only `AU-001`. Existing ID meanings are immutable; future audiences receive new IDs. The legacy `persona` dimension may remain for readability and compatibility, but it is not the cross-system join key.

## 2. Web / product analytics events

| Stage | Event | Required dimensions |
|-------|-------|---------------------|
| acquisition | `view_landing_page` | persona, source, campaign, content |
| intent | `select_persona` | selected_persona, original_landing_persona |
| idea | `start_idea_input` | persona, landing_path |
| idea | `complete_idea_input` | persona, idea_length_bucket, requested_output_mode, use_case |
| proof | `view_example` | persona, output_mode, example_type, source_proof_id |
| consideration | `view_how_it_works` | persona, source |
| lead | `start_lead_form` | persona, source |
| lead | `generate_lead` | persona, source, reply_preference |
| activation | `start_first_video` | persona, acquisition_source |
| activation | `complete_first_video` | persona, format, duration_bucket |
| activation | `start_first_image_batch` | persona, acquisition_source, use_case, requested_item_bucket |
| activation | `complete_first_image_batch` | persona, use_case, requested_item_bucket, accepted_item_bucket |
| retention | `express_second_video_intent` | persona, first_video_type |
| retention | `express_next_output_intent` | persona, use_case, first_output_mode, next_output_mode |

Do not send raw email, name, or image / video idea to analytics platforms.

商談、提案、受注、失注理由、金額のように個人や契約へ紐づく状態は CRM またはアクセス制御された営業記録で管理し、web analytics へ raw PII や契約情報を送らない。

Attribution は form submit 時に audience_unit_id、persona_id、customer_attribute_id、message_version、persona、use_case、output_mode、source、campaign、content、UTM、landing path を CRM record へ一方向で保存してつなぐ。CRM record ID、raw / hashed email、その他の hashed identifier、契約情報を analytics platform へ返さない。CRM から外部の分析面へ戻すのは audience unit / use_case / output_mode / source / campaign / content 単位の集計値だけとする。

### CRM / delivery states

| Stage | State | Required dimensions |
|-------|-------|---------------------|
| sales | `lead_qualified` | persona, use_case, output_mode, source, qualification_reason |
| sales | `lead_disqualified` | persona, use_case, output_mode, source, disqualification_reason |
| sales | `consultation_booked` | persona, use_case, output_mode, source |
| sales | `consultation_completed` | persona, use_case, output_mode, source, outcome |
| sales | `proposal_sent` | persona, use_case, output_mode, source, offer_version |
| sales | `closed_won` | persona, use_case, output_mode, source, offer_version |
| sales | `closed_lost` | persona, use_case, output_mode, source, lost_reason |
| delivery | `delivery_started` | persona, use_case, output_mode, offer_version |
| delivery | `delivery_completed` | persona, use_case, output_mode, offer_version |

Qualification source of truth:

- criteria は Workstream 1 が管理する `marketing/positioning-and-offer.md` の `Initial qualification hypothesis` を使う
- Workstream 3 は approved criteria に基づく status と reason を記録し、独自に条件を追加・変更しない
- evidence が定義変更を示唆する場合は、匿名集計、objection、won-lost reason とともに Workstream 1 へ返す
- 単なる資料請求、raw click、動画視聴だけを qualified としない

## 3. Primary KPIs

### Acquisition quality

- persona LP -> idea input start rate
- idea input completion rate
- lead completion rate
- qualified lead rate
- cost per qualified lead when ads begin

### Product activation

- lead -> first-output start rate by output mode
- first-image-batch / first-video completion rate
- time to first accepted image set or completed video
- human working time per accepted output
- revision count

### Sales

- qualified consultation count by persona / source
- consultation show rate
- proposal rate
- closed-won rate
- decision time
- closed-lost reason distribution

### Revenue and delivery economics

- contracted amount and received amount
- acquisition cost when measurable
- delivery cost and external API cost
- gross margin by offer version
- delivery completion rate

### Continuation

- next-output intent by output mode
- second image batch / video start and completion
- repeatable business-video use and series continuation for small-business users
- repeated test cycles for side-business users

## 4. YouTube diagnostics

- impressions and CTR by persona promise
- first 30-second retention
- completed-result-first vs process-first retention
- description / pinned-link CTR
- LP idea-input rate by source video
- qualified lead rate by content pillar

Do not select a content strategy only because it generated raw views. Prefer content that produces the intended persona、use case、output mode、completed ideas、qualified consultations、proposal / won-lost learning、and accepted first-output starts.

## 5. Claim metrics

To support `圧倒的に速く、簡単に`, maintain a reproducible evidence table:

| Field | Meaning |
|-------|---------|
| baseline_method | comparison workflow and operator skill |
| baseline_elapsed_time | start to finished output |
| toc_elapsed_time | same boundary under ToC |
| toc_human_working_time | active human time |
| external_wait_time | generation / provider waiting |
| output_format | duration, aspect ratio, resolution |
| image_counts | requested, generated, accepted, rejected, variant under the same boundary |
| revision_count | revisions before accepted output |
| acceptance_rule | who accepted and by what criteria |

If comparison boundaries differ, do not publish a percentage reduction.

## 6. Initial baselines

Do not invent target conversion rates before traffic and offer are stable. Collect the first meaningful sample by persona, document the baseline, then set improvement targets.

Initial operating questions:

- which persona reaches idea input more often?
- which obstacle predicts qualified use?
- which proof type causes first-output starts by output mode?
- where does each persona abandon the funnel?
- does the first accepted output create demand for another image batch or video?
- which persona, obstacle, proof, and source produce qualified consultations?
- why do qualified leads accept, delay, or reject a proposal?
- can the promised offer be delivered at a sustainable cost and quality?
