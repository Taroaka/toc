# Design

## Contract shape

`script.md.evaluation_contract.reveal_constraints`

```yaml
evaluation_contract:
  reveal_constraints:
    - subject_type: "character"
      subject_id: "otohime"
      rule: "must_not_appear_before"
      selector: "scene05_cut01"
      rationale: "乙姫の初出は scene04 では温存する"
```

## Notes

- selector は `sceneXX_cutYY` を基本にする
- `must_not_appear_before` を最初の canonical rule にする
- narrative design 上の理由を `rationale` に残す

