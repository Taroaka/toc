# Tasklist: Shared ToC skills for Claude Code and Codex

- [x] `skills/` を ToC 独自スキルの canonical path として作る
- [x] `codex_skills` を `skills` への互換 symlink に切り替える
- [x] `.claude/skills/` に ToC 独自スキルの相対 symlink を追加する
- [x] shared skills の `SKILL.md` frontmatter を正規化する
- [x] `scripts/ai/install-codex-skills.sh` を `skills/` source に更新する
- [x] `docs/implementation/assistant-tooling.md` を shared skills 構成に更新する
- [x] shared skills 用テストを追加する
- [ ] 検証:
  - [x] `python scripts/validate-pointer-docs.py`
  - [x] `python -m unittest discover -s tests -p 'test_pointer_docs.py'`
  - [x] `python -m unittest discover -s tests -p 'test_shared_skills.py'`
