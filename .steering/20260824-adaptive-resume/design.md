# Design: Adaptive ToC resume routing

## Decision

`toc-resume-p500` を legacy 名のまま adaptive resume router として扱う。再開地点は
checkpoint 同士や「最大の done slot」を比べず、失敗した operation から依存関係を
上流へ辿って最初に見つかる、正式な continuation worker を持つ検証済み境界を使う。

```text
inspect failed operation + acquire run lease
                    |
                    v
scene provider/output + strict current p650
+ current-request-bound scene-only plan?
        | yes                    | no
        v                        v
p650 image-only resume    p400 foundation current?
                                | yes       | no/unknown
                                v           v
                         canonical p500    block and repair upstream
```

## Routing rules

- `p650 image-only`: current p650 validator passes and the regeneration plan contains only
  current-request-bound scene outputs. Preserve assets and unaffected scene images.
- `p500 checkpoint`: no verified p650 route applies and downstream design/request
  materialization is stale, while the p400 foundation remains valid. Use the existing
  dry-run/exact-token/apply entrypoint.
- `blocked`: active mutation, unsafe or unbound target, malformed plan, contradictory state,
  or invalid p400 foundation. Do not infer a resume point from progress labels.

The Image generation app resume API remains the preferred automatic router for p650 versus p500
because it repeats the classification after the run lease is acquired. Direct p500 CLI use is
reserved for an explicit canonical p500 reset or diagnostics. p550 is not advertised as a
repairable boundary until a dedicated worker owns request-bound retry, p560/p570 validation,
state transitions, handoff, and lease revalidation as one contract.
