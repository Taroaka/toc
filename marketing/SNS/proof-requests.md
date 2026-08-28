# ToC Marketing Proof Requests

更新日: 2026-08-08

この文書は、Workstream 3 から production / human review へ渡す proof request である。動画生成 pipeline や quality gate を変更せず、marketing claim に必要な evidence を指定する。

## Common evidence package

Every proof request returns:

- `proof_id`
- initial brief / source material boundary
- selected output mode: `image_batch|video`
- intended audience / desired understanding or action
- completed media path and format
- creator / human acceptance and requested revisions
- ToC-owned stages / human-owned decisions
- elapsed production time / active human time / external waiting time
- external API cost or `not_available` with reason
- revision count and material before / after evidence
- rights / consent / provider-use confirmation
- public disclosure requirements
- fresh media QA result
- approved claim list and prohibited claim list

For an `image_batch` proof, also return:

- requested item count and intended destination per item
- generated candidate count
- accepted unique image count
- rejected count and rejection reason
- reference / variant / derivative classification
- visual identity / continuity acceptance rule

If any field is missing, the inventory keeps the item as `candidate` and names the missing gate.

## REQ-001: PRF-001 public-readiness review

### Input

- run: `output/浦島太郎_20260208_1515_immersive/`
- final media: `render/final/urashima_taro_full_compiled.mp4`

### Purpose

Determine whether PRF-001 can be used as shared system-capability proof.

### Required review

1. watch the complete 342.148-second render
2. check playback、audio、scene order、continuity、visible defects、credits / disclosure
3. resolve the freshness mismatch between the 2026-05-02 run report and 2026-05-03 final render
4. record human `approved_for_public_marketing` or exact change requests
5. confirm rights / provider terms for generated video、image、music、voice
6. materialize time、cost、revision、human-decision metadata where available

### Allowed claim if approved

- a one-line public-domain story topic became a multi-scene long-form cinematic render
- ToC connected multiple production stages into a completed artifact

### Not requested / prohibited

- side-business income proof
- small-business outcome or reuse proof
- speed comparison without baseline
- viewer impact without response evidence

## REQ-002: Side-business first-video case

### Purpose

Prove that a matching individual can move from a personally meaningful idea to an accepted first video and a real test without losing the intent they wanted to express.

Audience binding: `AU-001` / `P-001` / `CA-001` / `MV-001`.

### Required input

- one persona-matching individual, or an explicitly labeled internal simulation
- the person's own experience、knowledge、story、idea、or value they want to express
- one-line video idea in the person's own words
- selected output mode: `video`
- target audience and test hypothesis
- current alternative and largest production obstacle
- consent and public-use boundary when a real participant is involved

### Required output

- accepted first video
- idea -> output comparison
- elapsed / active human / external wait / API cost / revisions
- human decisions and what ToC handled
- publication / response plan
- actual response only after publication

### Allowed claim boundary

- the person's original intent was preserved in an accepted first video
- production burden and time to a testable first video
- ability to run a market test

Never claim guaranteed revenue、views、or continuation.

## REQ-003: Small-business reusable-visual case

### Purpose

Prove that a small business can turn business-specific knowledge into an accepted image set or video and reuse its rules or assets without losing owner control. `personal_brand` may be selected as an owner-expertise use case, but is not a separate primary persona.

### Required input

- one concrete business use case: product / service explanation、customer education、recruiting、company story、or owner expertise
- business-owned knowledge / source material
- intended customer、candidate、or audience and desired understanding
- selected output mode: `image_batch|video`
- voice、tone、visual identity、approval rule、reuse goal
- consent and public-use boundary

### Required output

- one accepted primary image set or video
- at least one derivative / second output or concrete reuse of approved rules / assets
- brief -> output comparison and reuse record
- owner acceptance and what was preserved / revised
- elapsed / active human / API cost / revisions per output or reuse step

### Allowed claim boundary

- business-specific knowledge became an owner-approved image or video asset
- owner control and human approval were preserved
- defined rules / assets were reused in a derivative or second output

Never claim automatic leads、sales、authority、brand growth、or audience trust without response evidence.

## REQ-004: PRF-001 image classification

### Purpose

Determine what the 261 image files in `PRF-001` actually represent and whether any subset can support image-batch capability proof.

### Required classification

- requested / planned item and intended scene or destination
- generated candidate
- reference or intermediate asset
- variant / derivative relationship
- rejected item and reason
- selected / accepted unique image
- image used in the final render

### Required boundary

- classification method and file scope
- requested、generated、accepted、rejected、variant counts
- acceptance rule and human reviewer
- elapsed / active human time、API cost、revision count where available
- rights / provider-use status

Until completed, allow only the factual internal statement `261 image files exist across the run`. Do not publish a production-volume or accepted-output claim.

## Handoff format

```yaml
request_id: REQ-XXX
owner: "production or human reviewer"
status: pending|in_progress|blocked|completed
proof_id: PRF-XXX
audience_unit_id: AU-XXX
persona_id: P-XXX
customer_attribute_id: CA-XXX
message_version: MV-XXX
target: side_business|small_business_operator|shared
use_case: ""
output_mode: image_batch|video
input_paths: []
output_paths: []
evidence_package_path: ""
image_counts:
  requested: null
  generated: null
  accepted: null
  rejected: null
  variant: null
human_approval: pending|changes_requested|approved_for_public_marketing
rights_status: pending|confirmed|blocked
claim_status: pending|approved|restricted
missing_gates: []
notes: ""
```
