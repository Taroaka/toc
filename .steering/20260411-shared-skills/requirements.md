# Requirements: Shared ToC skills for Claude Code and Codex

## Background

ToC 独自スキルは `codex_skills/` に集まっている一方で、Claude Code 側の `.claude/skills/` とは別系統になっている。
このままだと ToC 独自スキルの本文を二重管理しやすく、Claude Code / Codex で導線も分かれる。

一方で `improve_claude_code/skills/` は vendor として upstream 追従したいので、ToC 独自スキルと混ぜて単一管理しない。

## Goals

### G1: ToC 独自スキルの正本を 1 箇所に集約する

- ToC 独自スキルの canonical path を `skills/<skill-name>/SKILL.md` にする
- `codex_skills/` は互換 alias として残し、既存参照を急に壊さない

### G2: Claude Code / Codex の両方から同じ実体を参照できるようにする

- Claude Code 側では `.claude/skills/<skill-name>` から `../../skills/<skill-name>` を相対 symlink で参照する
- Codex 側では `scripts/ai/install-codex-skills.sh` が `skills/` を source として `~/.codex/skills/` に配布する

### G3: shared-compatible な SKILL frontmatter に揃える

- `name` はディレクトリ名と一致させる
- `description` は英語で簡潔に書き、`Use when:` を含める
- Claude Code 固有の `allowed-tools` は ToC shared 正本には含めない

### G4: 正本ドキュメントと検証を更新する

- `docs/implementation/assistant-tooling.md` に shared skills 構成を反映する
- shared skills の存在、frontmatter、Claude symlink、Codex installer をテストで検証する

## Non-goals

- `improve_claude_code/skills/` を shared skills ツリーへ移すこと
- vendor スキル本文の再設計や upstream 同期方式の変更
- Claude 固有 overlay の導入（必要になった時点で別設計にする）

## Constraints

- `AGENTS.md` / `CLAUDE.md` の pointer doc 方針は崩さない
- 既存の vendor スキルは `.claude/skills/` 配下で引き続きそのまま利用できる状態を保つ
- shared skills は macOS / Linux の symlink 前提で扱う

## Success criteria

- A1: ToC 独自スキルの本文正本が `skills/` にのみ存在し、`codex_skills` は alias 扱いになる
- A2: `.claude/skills/<skill-name>` が shared 正本を指し、Claude Code から参照できる
- A3: `scripts/ai/install-codex-skills.sh` を temp `CODEX_HOME` で実行すると `skills/` の shared skills だけが `~/.codex/skills` 相当に展開される
- A4: `python scripts/validate-pointer-docs.py` と shared skills テストが通る
