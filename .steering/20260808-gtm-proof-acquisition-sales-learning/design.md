# ToC proof, acquisition, and sales learning design

更新日: 2026-08-09

## Operating loop

```text
proof inventory
  -> claim / target / output-mode fit
  -> target / use-case / output-mode hypothesis
  -> organic content or direct conversation
  -> idea / qualified consultation / proposal / won-lost
  -> continue / revise / stop
  -> evidence handoff to Workstream 1 / 2
```

## Proof states

| State | Meaning | Public use |
|-------|---------|------------|
| `publish_ready` | artifact、fresh QA、human approval、rights、claim metadata が揃う | approved claim の範囲で可 |
| `candidate` | 実 artifact はあるが public gate が一つ以上未完了 | 内部 review のみ |
| `process_only` | partial asset / failure / repair が build-in-public evidence になる | context と limitation を明記した場合のみ |
| `blocked` | artifact が未完成、failed、または権利・品質上利用不可 | 不可 |

## Claim boundary

- `想いを映像に`: initial brief と completed output の対応、creator acceptance が必要
- `人の心へ届く`: intended audience / desired change と実際の response evidence が必要
- `速く、簡単に`: elapsed time、active human time、comparison boundary が必要
- `続けられる`: second / third video と reused brief / assets / series rules が必要
- `system capability`: completed artifact、工程、human decisions、fresh QA が必要

## Experiment contract

1 experiment は `1 audience unit / 1 use case / 1 output mode / 1 obstacle / 1 proof / 1 CTA` とする。1 audience unit は `1 persona x 1 customer attribute` であり、`audience_unit_id` を join key とする。

Required fields:

- week / audience_unit_id / persona_id / customer_attribute_id / message_version / use case / output mode / obstacle / hypothesis
- proof asset / claim boundary / hook
- channel / CTA destination / UTM
- readiness gate / primary metric / decision rule
- result / objection / continue-revise-stop

`image_batch` proof additionally records requested、generated、accepted、rejected、reference、variant、destination、and human acceptance under one boundary.

Audience definitions are append-only. A new persona or customer attribute creates a new registry row and IDs; it never rewrites a unit already used by an experiment.

## CRM boundary

- raw PII、raw image / video idea、CRM identifier、hashed email、contract details を marketing repo または web analytics に置かない
- form submit 時の source / campaign / content / UTM / landing path は CRM へ一方向で保存する
- repo の learning log には persona / use_case / output_mode / source / campaign / content 単位の集計と匿名化した objection だけを残す
- qualification は Workstream 1 の approved definition を使い、変更案は evidence とともに handoff する

## Parallel dependency

- Workstream 1 から受け取る: beachhead、offer version、qualification、price hypothesis、claim approval
- Workstream 2 から受け取る: persona LP URL、CTA label、form / event contract、approved Hero proof slot
- production から受け取る: completed media、QA、human approval、rights、time / cost / revision metadata
- Workstream 3 から返す: objections、price response、lost reasons、proof response、persona conversion evidence
