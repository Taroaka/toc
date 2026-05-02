# ToC Pointer Guide

Codex 向けの共通ガイド本体は `docs/root-pointer-guide.md`。

- root の薄い入口として扱う。
- 詳細の追加・修正は `docs/root-pointer-guide.md` に集約する。
- `AGENTS.md` / `CLAUDE.md` の整合確認は次で行う。

## Request Intake

ガイド、プロンプト、運用ルールの見直し依頼では、作業前に Goal / Success criteria / Scope を確認する。

確認すること:

- Goal: ユーザーが達成したい最終状態
- Success criteria: 何が満たされれば完了か
- Scope: 変更対象ファイルと、変更してはいけないファイル
- Evidence: 参照すべき記事・資料・既存ルール
- Decision rule: 不足や衝突がある場合に質問すべき条件

判断ルール:

- Goal / Success criteria / Scope が読み取れる場合は、最小変更で進める
- 変更対象や変更禁止ファイルが曖昧な場合は、編集前に質問する
- ユーザーの最新指示と既存ルールが衝突する場合は、どちらを優先するか質問する
- 手順が未指定なだけなら、既存 repo ルールに従って進める

```bash
python scripts/validate-pointer-docs.py
```
