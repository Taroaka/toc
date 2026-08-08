# ToC marketing analytics and KPIs

更新日: 2026-08-08

## 1. Measurement principle

Views and clicks are diagnostic metrics. The main question is whether the right individual moves from interest to a real video idea, starts a first video, and wants to continue.

Keep side-business and personal-brand results separate at every step.

## 2. Web / product analytics events

| Stage | Event | Required dimensions |
|-------|-------|---------------------|
| acquisition | `view_landing_page` | persona, source, campaign, content |
| intent | `select_persona` | selected_persona, original_landing_persona |
| idea | `start_idea_input` | persona, landing_path |
| idea | `complete_idea_input` | persona, idea_length_bucket |
| proof | `view_example` | persona, example_type, source_video_id |
| consideration | `view_how_it_works` | persona, source |
| lead | `start_lead_form` | persona, source |
| lead | `generate_lead` | persona, source, reply_preference |
| activation | `start_first_video` | persona, acquisition_source |
| activation | `complete_first_video` | persona, format, duration_bucket |
| retention | `express_second_video_intent` | persona, first_video_type |

Do not send raw email, name, or video idea to analytics platforms.

商談、提案、受注、失注理由、金額のように個人や契約へ紐づく状態は CRM またはアクセス制御された営業記録で管理し、web analytics へ raw PII や契約情報を送らない。

Attribution は form submit 時に persona、source、campaign、content、UTM、landing path を CRM record へ一方向で保存してつなぐ。CRM record ID、raw / hashed email、その他の hashed identifier、契約情報を analytics platform へ返さない。CRM から外部の分析面へ戻すのは persona / source / campaign / content 単位の集計値だけとする。

### CRM / delivery states

| Stage | State | Required dimensions |
|-------|-------|---------------------|
| sales | `lead_qualified` | persona, source, qualification_reason |
| sales | `lead_disqualified` | persona, source, disqualification_reason |
| sales | `consultation_booked` | persona, source |
| sales | `consultation_completed` | persona, source, outcome |
| sales | `proposal_sent` | persona, source, offer_version |
| sales | `closed_won` | persona, source, offer_version |
| sales | `closed_lost` | persona, source, lost_reason |
| delivery | `delivery_started` | persona, offer_version |
| delivery | `delivery_completed` | persona, offer_version |

Initial qualified lead definition:

- primary persona のどちらかに該当する
- 具体的な動画テーマまたは継続発信の目的がある
- ToC が解消できる制作障壁がある
- 導入時期と有償導入を検討する意思を follow-up で確認できる

この定義は persona 別の商談 evidence で更新する。単なる資料請求、raw click、動画視聴だけを qualified としない。

## 3. Primary KPIs

### Acquisition quality

- persona LP -> idea input start rate
- idea input completion rate
- lead completion rate
- qualified lead rate
- cost per qualified lead when ads begin

### Product activation

- lead -> first-video start rate
- first-video completion rate
- time to first completed video
- human working time per completed video
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

- second-video intent
- second-video start / completion
- series continuation for personal-brand users
- repeated test cycles for side-business users

## 4. YouTube diagnostics

- impressions and CTR by persona promise
- first 30-second retention
- completed-result-first vs process-first retention
- description / pinned-link CTR
- LP idea-input rate by source video
- qualified lead rate by content pillar

Do not select a content strategy only because it generated raw views. Prefer content that produces the intended persona, completed ideas, qualified leads, and first-video starts.

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
| revision_count | revisions before accepted output |
| acceptance_rule | who accepted and by what criteria |

If comparison boundaries differ, do not publish a percentage reduction.

## 6. Initial baselines

Do not invent target conversion rates before traffic and offer are stable. Collect the first meaningful sample by persona, document the baseline, then set improvement targets.

Initial operating questions:

- which persona reaches idea input more often?
- which obstacle predicts qualified use?
- which proof type causes first-video starts?
- where does each persona abandon the funnel?
- does the first completed video create demand for a second?
- which persona, obstacle, proof, and source produce qualified consultations?
- why do qualified leads accept, delay, or reject a proposal?
- can the promised offer be delivered at a sustainable cost and quality?
