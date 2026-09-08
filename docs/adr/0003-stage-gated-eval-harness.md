# ADR-0003: Stage Gated Eval Harness を標準化する（履歴）

- Status: Superseded by ADR-0005
- Date: 2026-03-09

## Context

ToC の価値はコード量より生成物の質に強く依存する。
既存フローには「創造→選択」の思想があるが、品質判定の多くは運用ルールに留まっていた。

## Decision

- `research -> story -> script -> manifest -> video` を共通 stage として扱う
- 各 stage に deterministic check と rubric check を置く
- 共通入口は `scripts/verify-pipeline.py` とする
- 出力は `eval_report.json` と `run_report.md`
- state には最低限の eval score と selection metadata を追記する
- hybridization は自動承認しない。人間承認を必須にする

## Consequences

- 生成フローを人間レビューだけに依存せず反復できる
- regression topic を用いた dry-run / smoke render を CI へ載せやすくなる
- `run_report.md` は手書きではなく、eval 結果から生成する標準成果物になる
