# ToC Pointer Guide

`AGENTS.md` と `CLAUDE.md` は同一内容で管理する。差分を作らない。

共通ガイド本体: `docs/root-pointer-guide.md`

- Claude Code は `CLAUDE.md` を入口にしつつ、内容は `docs/root-pointer-guide.md` を参照する。
- Codex 系エージェントは `AGENTS.md` を入口にしつつ、内容は `docs/root-pointer-guide.md` を参照する。
- 詳細の追加・修正は root 側ではなく `docs/root-pointer-guide.md` に集約する。

更新後は次を実行する。

```bash
python scripts/validate-pointer-docs.py
```
