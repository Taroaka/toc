# Design

## Contract surface

- 正本: `docs/implementation/image-prompting.md`
- 運用導線: `docs/how-to-run.md`
- machine-facing contract: `docs/data-contracts.md`
- テンプレート注記: `workflow/*video-manifest-template.md`
- playbook: `workflow/playbooks/image-generation/reference-consistent-batch.md`

## Prompt collection review fields

各 `sceneXX_cutYY` entry は少なくとも次を持つ前提で記述する。

- `agent_review_ok: true|false`
- `agent_review_reason_keys: []`
- `human_review_ok: true|false`
- `human_review_reason: ""` または人間判断の短文

## Semantics

- `agent_review_ok: false` は「そのままでは生成に進めない」ことを意味する
- `agent_review_reason_keys` は false の根拠を列挙し、修正対象を manifest / prompt collection に戻すための key とする
- 修正後は subagent が再 review し、reason keys を空にしたうえで `agent_review_ok: true` に戻せる
- `human_review_ok: true` は例外承認の記録であり、subagent finding 自体を消したことにはしない
- 人間が override した場合も `human_review_reason` を必須とし、なぜ許容したかを残す

## Reason key set

初期セットは docs で以下を canonical とする。

- `missing_character_ids`
- `missing_object_ids`
- `environment_only_prompt`
- `missing_story_action`
- `missing_story_relationship`
- `continuity_anchor_missing`
- `reference_missing`
- `camera_or_composition_under_specified`

必要なら将来追加してよいが、既存 key の意味は変えない。
