# Requirements: Image Prompt Ops Principle

## Goal
画像生成は「うまい一文を書く」よりも、
`構造化 -> anchor を決める -> reference を固定する -> prompt collection をレビューする -> 生成する`
という運用を repo 全体の設計として明記する。

## Scope
- `docs/implementation/image-prompting.md`
- `docs/how-to-run.md`
- `workflow/playbooks/image-generation/reference-consistent-batch.md`

## Constraints
- 既存方針を壊さず、自然に統合する
- 他者の変更は戻さない
- 画像生成前に prompt collection を作る運用を正とする
- 生成品質の鍵は prompt の文才ではなく、構造・anchor・reference・レビューであることを明示する
