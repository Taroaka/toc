# Design: Shared ToC skills for Claude Code and Codex

## 1) Canonical layout

### Source of truth

- 正本: `skills/<skill-name>/SKILL.md`
- 対象: ToC 独自スキル 7 個
  - `ai-idea-studio`
  - `era-explainer`
  - `folktale-researcher`
  - `improve-workflow`
  - `neta-collector`
  - `selfhelp-trend-researcher`
  - `vertical-shorts-creator`

### Compatibility path

- `codex_skills` は `skills` を指す symlink にする
- 既存ドキュメントや作業メモで `codex_skills/...` が残っていても当面は壊れない

## 2) Claude Code exposure

- `.claude/skills/` 配下には vendor スキルの実体が既にあるため、それは保持する
- ToC 独自スキルのみ `.claude/skills/<skill-name> -> ../../skills/<skill-name>` の相対 symlink を追加する
- これにより Claude Code と Codex が同じ `SKILL.md` 本文を読む

## 3) Codex install flow

- `scripts/ai/install-codex-skills.sh` の source を `skills/` に変更する
- installer は以下だけを対象にする
  - ディレクトリである
  - ディレクトリ名が `_` で始まらない
  - `SKILL.md` を持つ
- `skills/_shared/` のような補助ディレクトリは将来追加しても install 対象外になる

## 4) SKILL.md normalization

- frontmatter は shared-compatible に揃える
  - `name`: ディレクトリ名と一致
  - `description`: 英語、簡潔、`Use when:` を含む
  - `Accepts args:` は必要なスキルのみ
- 本文は大きく書き換えず、shared 運用上ズレる箇所だけ修正する
- `improve-workflow` は Codex 固有の説明を弱め、Claude Code / Codex 共通の手順スキルとして読める形にする

## 5) Verification

### Tests

- `tests/test_shared_skills.py`
  - `skills/` 配下の各 shared skill に `SKILL.md` がある
  - frontmatter の `name` がディレクトリ名と一致する
  - `codex_skills` が `skills` への symlink である
  - `.claude/skills/<skill-name>` が shared 正本への symlink である
  - installer が temp `CODEX_HOME` に shared skills だけを展開し、`_shared` のような非スキルは展開しない

### Manual / command verification

- `python scripts/validate-pointer-docs.py`
- `python -m unittest tests.test_pointer_docs tests.test_shared_skills`

## 6) Documentation

- `docs/implementation/assistant-tooling.md` を shared skills 正本の説明に更新する
- root pointer docs には詳細を書き戻さず、現状どおり正本ドキュメントへの導線だけ維持する
