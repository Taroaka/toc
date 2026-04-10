# ToC Pointer Guide

## North Star

- ToC は spec-first repo。正本は `docs/`, `workflow/`, `scripts/` に置く。
- 価値の中心は生成物の質にある。ハーネスは動画の中身ではなく、運用・評価・承認・回帰検証を強化するために使う。
- 日常運用は Codex 主軸。Claude Code は backup / accelerator として扱う。
- 回答は必要なことを端的に書く。長い説明は正本ドキュメントへ寄せる。

## Entrypoints

- `/toc-run`
- `/toc-scene-series`
- `/toc-immersive-ride`
- 実行方法の正本: `docs/how-to-run.md`

## Read Next

- 調査: `docs/information-gathering.md`
- 物語化: `docs/story-creation.md`
- 台本: `docs/script-creation.md`
- 動画生成: `docs/video-generation.md`
- 運用/QA: `docs/orchestration-and-ops.md`
- エージェント運用: `docs/implementation/assistant-tooling.md`
- 役割定義: `docs/implementation/agent-roles-and-prompts.md`
- 状態/成果物契約: `docs/data-contracts.md`
- ADR: `docs/adr/`

## Templates / Contracts

- `workflow/research-template.yaml`
- `workflow/research-template.production.yaml`
- `workflow/story-template.yaml`
- `workflow/video-manifest-template.md`
- `workflow/state-schema.txt`
- `workflow/evaluation_criteria.md`
- `workflow/evals/golden-topics.yaml`

## State

- canonical state: `output/<topic>_<timestamp>/state.txt`
- derived state: `output/<topic>_<timestamp>/run_status.json`
- eval outputs: `output/<topic>_<timestamp>/eval_report.json`, `output/<topic>_<timestamp>/run_report.md`

## Required Workflow

- 非自明な変更は `.steering/YYYYMMDD-<title>/requirements.md -> design.md -> tasklist.md`
- 実装は最小変更で進める
- 変更後は verify を回す

```bash
python scripts/verify-pipeline.py --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive --profile fast|standard
```

日常の開始ルーチン:

```bash
scripts/ai/session-bootstrap.sh
```

## Hard Rules

- `state.txt` を置き換えない。append-only を維持する。
- hybridization は人間承認必須。自動承認しない。
- `run_report.md` は手書きしない。`eval_report.json` から生成する。
- root guide に長い説明を戻さない。詳細は正本へ移す。
- `AGENTS.md` / `CLAUDE.md` を更新したら次を通す。

```bash
python scripts/validate-pointer-docs.py
```

## Search / Tools

- ファイル一覧は `rg --files` または `fd`
- 内容検索は `rg`
- `tree`, `find`, `grep -r`, `ls -R` は使わない

## Related Runtime Layer

- `improve_claude_code/` は ToC 本体とは別の運用レイヤー
- 詳細は `docs/implementation/assistant-tooling.md`
