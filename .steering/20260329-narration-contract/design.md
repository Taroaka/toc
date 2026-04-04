# Design

## Contract placement

`audio.narration.contract` に配置する。

```yaml
audio:
  narration:
    contract:
      target_function: "time|causality|inner_state|viewpoint|rule|meaning"
      must_cover: []
      must_avoid: []
      done_when: []
```

## Semantics

- `target_function`
  - この cut の narration が何を担うか
- `must_cover`
  - 触れるべき概念や要素
- `must_avoid`
  - 直接言わない方がよい語や、映像説明の禁止語
- `done_when`
  - evaluator と generator が共有する完了条件の短文

## Evaluation

review script は次を追加判定する。

- `narration_contract_missing`
- `narration_contract_must_cover_unmet`
- `narration_contract_must_avoid_violated`
- `narration_contract_target_function_unmet`

`must_cover` / `must_avoid` は完全一致だけでなく semantic anchor で判定する。

- exact phrase
- 語形ゆれ
- narrative concept の同義表現
- phrase token の十分な重なり

これにより、`must_cover: ["理由"]` に対して narration が `そのため` や `だから` を使っていても通せる。
