# ToC Pointer Guide

`AGENTS.md` と `CLAUDE.md` は同一内容で管理する。差分を作らない。
以下は編集しないこと

共通ガイド本体: `docs/root-pointer-guide.md`

Astra 使用時はサブエージェントを使わないこと。使う場合は、事前にユーザーの明示的な許可を取ること。

- Claude Code は `CLAUDE.md` を入口にしつつ、内容は `docs/root-pointer-guide.md` を参照する。
- Codex 系エージェントは `AGENTS.md` を入口にしつつ、内容は `docs/root-pointer-guide.md` を参照する。
- リポジトリ全体に適用する詳細は `docs/root-pointer-guide.md` に集約する。
- 特定ディレクトリを編集するときは、その配下の `AGENTS.md` / `CLAUDE.md` を確認する。局所的な方針はそのディレクトリ内で管理する。

更新後は次を実行する。
```bash
python scripts/validate-pointer-docs.py
```
