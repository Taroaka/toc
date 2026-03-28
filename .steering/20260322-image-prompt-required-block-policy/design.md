# Design

## Contract

- 正本に required block を明記する: `docs/implementation/image-prompting.md`
- run guide に review criterion を追記する: `docs/how-to-run.md`
- machine-facing contract に欠落時の false semantics を追記する: `docs/data-contracts.md`
- playbook と manifest template に required block 前提の注記を入れる

## Review semantics

- subagent review は 6 block の存在確認を必須 criterion に含める
- block が 1 つでも欠けていれば `agent_review_ok: false`
- canonical false reason key は `missing_required_prompt_block`
- 必要なら補助説明で欠けた block 名を列挙してよい
- fix は prompt collection / source manifest で block を補完し、再 review 後に `agent_review_ok: true` に戻す
