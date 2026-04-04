# Stage Evaluator Expansion Requirements

## Goal

research, script, scene/cut(manifest), video generation の各段階にも evaluator subagent と同等の review loop を追加する。

## Requirements

1. 各 stage に単独で実行できる evaluator CLI を持つ
2. evaluator は既存の verify 基準を流用し、重複定義を増やしすぎない
3. evaluator は `state.txt` に run 単位 summary を追記する
4. summary は最低限次を持つ
   - `eval.<stage>.status`
   - `eval.<stage>.score`
   - `eval.<stage>.findings`
   - `artifact.<stage>_review`
5. scene/cut は manifest review を evaluator stage として扱う
6. docs/how-to-run, docs/data-contracts, workflow/state-schema.txt を更新する
7. CLI テストを追加する
