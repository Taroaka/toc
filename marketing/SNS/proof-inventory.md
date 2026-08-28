# ToC Marketing Proof Inventory

更新日: 2026-08-09

この文書は、marketing で利用を検討できる実在 proof と、その claim boundary の正本である。artifact の存在だけで公開可能とは判断しない。

## Proof state

| State | Required condition | Public use |
|-------|--------------------|------------|
| `publish_ready` | completed artifact、fresh QA、human approval、rights、claim metadata が揃う | approved claim の範囲で可 |
| `candidate` | 実 artifact はあるが public gate が未完了 | 内部 review のみ |
| `process_only` | partial asset、failure、repair process | limitation を明記した build-in-public のみ |
| `blocked` | incomplete、failed、権利または品質上利用不可 | 不可 |

## Current inventory

### PRF-001: 浦島太郎 long-form immersive render

| Field | Current evidence |
|-------|------------------|
| proof state | `candidate` |
| source run | `output/浦島太郎_20260208_1515_immersive/` |
| initial brief | topic `浦島太郎` |
| final render | `render/final/urashima_taro_full_compiled.mp4` |
| media | 342.148 sec、1280x720、24 fps、H.264、AAC stereo |
| supporting artifacts | MP4 109 files、image 261 files、audio 291 files across the run |
| visible transformation | one-line public-domain story title -> cinematic long-form render |
| current persona fit | shared system capability only |
| human approval | not recorded as public approval |
| creator acceptance | not applicable / not recorded; this is not a customer brief |
| response evidence | not found in the repository |
| speed evidence | elapsed time / active human time / comparison boundary not confirmed |
| cost evidence | external API cost not confirmed |
| rights check | public-domain source alone is insufficient; generated media / music / voice / provider terms require confirmation |

What this may prove after fresh review:

- ToC can connect a short topic to research、story、scene、image、video、voice、render artifacts
- ToC can produce a multi-scene long-form cinematic output
- human review and regeneration history can be shown as process evidence

What this does not prove:

- a side-business user can earn money
- a small-business operator can preserve business-specific knowledge and reuse a consistent production system
- a customer's original intent was preserved and accepted
- the workflow is faster or cheaper than a defined alternative
- viewers were emotionally moved or took a desired action
- 261 image files are 261 accepted, unique, customer-requested deliverables

Image evidence boundary:

- `261 files` is a filesystem count across the run, not an accepted-image count
- generated、reference、variant、rejected、selected、and delivered items are not yet classified
- requested item count、destination、acceptance rule、elapsed / active time、API cost are not confirmed
- therefore `大量生成` or a public image-volume number is not allowed from this evidence

Freshness note:

- existing `run_report.md` was generated on 2026-05-02 and reports overall `FAIL`
- final render modification time is 2026-05-03, after that report
- therefore the report is neither a fresh final-render QA pass nor evidence that the final render is publish-ready

Required before `publish_ready`:

1. human watches the full render and records public approval / requested edits
2. fresh final media QA checks playback、audio、duration、scene continuity、credits / disclosure
3. rights and provider-use boundary is confirmed
4. initial brief、human decisions、revision history、elapsed / active time、API cost are materialized
5. only claims supported by the resulting evidence are attached

### PRF-002: シンデレラ current create run

| Field | Current evidence |
|-------|------------------|
| proof state | `blocked` |
| source run | `output/シンデレラ_20260808_1934/` |
| status | `FAILED` |
| failed stage | research semantic review / repair |
| downstream media | not generated |
| public use | none |

This run may later become process evidence about failure detection and quality gates, but it is not a product proof while the repair and downstream production are incomplete.

## Publish-ready summary

As of 2026-08-08:

- publish-ready shared capability proof: `0`
- publish-ready image-batch proof: `0`
- publish-ready side-business proof: `0`
- publish-ready small-business proof: `0`
- candidate shared capability proof: `1` (`PRF-001`)
- blocked proof: `1` (`PRF-002`)

No public video URL or repository-backed viewer response dataset was located. This means only that such evidence is not bound into the repository; it does not assert that no external publication exists.

## Target proof gaps

### Side-business

Required case:

```text
own experience / knowledge / story / idea / value
  -> one-line video idea in the person's own words
  -> target audience and test hypothesis
  -> accepted first video
  -> elapsed / active human time / API cost / revision
  -> published response
  -> continue / revise / stop decision
```

Minimum proof:

- actual individual matching the persona or an explicitly labeled internal simulation
- the person's own words、first-video brief、and accepted video
- production burden evidence without income guarantee
- actual market response only after publication

### Small-business operator

Required case:

```text
business brief / use case plus selected output mode
  -> accepted primary image set or video
  -> reused rules / assets in a derivative or second output
  -> owner approval and business-fit evidence
  -> customer / candidate / audience understanding when available
```

Minimum proof:

- actual small-business use case or an explicitly labeled internal simulation
- business-owned knowledge、voice / tone / visual identity、approval rule、destination
- accepted primary output and concrete reuse / derivative evidence
- owner acceptance and what was preserved / revised

`personal_brand` is one owner-expertise use case inside this target. It is not counted as a third primary persona.

## Proof backlog

Production / human-review handoff details are in `marketing/SNS/proof-requests.md`.

| Priority | Item | Intended claim | Owner / handoff | Status |
|----------|------|----------------|-----------------|--------|
| P0 | `REQ-002` `AU-001` side-business first-video case | a person's own intent becomes an accepted video and a real test | production request from Workstream 3 | missing |
| P0 | common Hero proof | one-line idea becomes accepted video | Workstream 2 selects after approval | blocked by proof |
| P1 | `REQ-001` fresh review package for `PRF-001` | shared long-form capability | production + human review | pending |
| P1 | `REQ-004` classify `PRF-001` image files | requested / generated / accepted / rejected / variant image evidence | production + human review | pending |
| P1 | reproducible speed comparison | faster / simpler under defined boundary | Workstream 1 + production | missing |
| P1 | delivery demonstration | customer receives a usable system, not a monthly SaaS login | Workstream 1 + delivery owner | missing |
| P1 | second-video reuse evidence | continued production becomes easier / more consistent | production + customer | missing |
| P2 | `REQ-003` small-business reusable-visual case | business knowledge can become approved, reusable image / video assets | deferred until E-commerce / customization requirements are defined | deferred |

## Claim-to-proof rules

| Claim | Required proof |
|-------|----------------|
| `あなたの想いを、映像に。` | initial brief、completed output、creator acceptance、preserved / revised record |
| `人の心へ届く` | intended audience / desired change plus actual response evidence when stated as achieved |
| `もっと速く、もっと簡単に` | elapsed / active time、workflow boundary、output acceptance |
| `圧倒的に速く、簡単に` | defensible comparison with the same boundary and accepted outputs |
| `続けられる` | second / third output and reused rules / assets / learning |
| `必要な画像を、まとめて。` | requested item / destination、generated candidates、accepted unique images、rejection reason、variant、human approval |
| image-volume claim | requested / generated / accepted / rejected / variant counts under one defined boundary; raw filesystem count is insufficient |
| side-business value | reduced production burden and test iteration; never guaranteed income |
| small-business value | business brief / use case、reuse evidence、owner approval |
