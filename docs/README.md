# Docs Index

この `docs/` 配下は、本リポジトリの「恒久仕様」を置く場所です。

## まず読む（入口）
- 実行方法: `docs/how-to-run.md`
- 全体アーキテクチャ: `docs/system-architecture.md`
- 未決定事項: `docs/open-decisions.md`
- 生成（プロバイダ/不足分の調査）: `docs/video-production-research.md`

## 生成パイプライン（設計仕様）
- 情報収集: `docs/information-gathering.md`
- 物語生成: `docs/story-creation.md`
- 台本生成: `docs/script-creation.md`
- 動画生成: `docs/video-generation.md`
- オーケストレーション/QA/運用: `docs/orchestration-and-ops.md`

## 実装仕様（昇華: .steering → docs）

- LangGraph topology: `docs/implementation/langgraph-topology.md`
- Agent roles & prompts: `docs/implementation/agent-roles-and-prompts.md`
- Asset bibles（object / setpiece）: `docs/implementation/asset-bibles.md`
- Image prompting（Nano Banana 2 / Gemini 3.1 Flash Image / cross-model）: `docs/implementation/image-prompting.md`
- Assistant tooling（Claude/Codex）: `docs/implementation/assistant-tooling.md`
- Entrypoint (/toc-run): `docs/implementation/entrypoint.md`
- Entrypoint (/toc-scene-series): `docs/implementation/scene-series-entrypoint.md`
- Entrypoint (/toc-immersive-ride): `docs/implementation/immersive-ride-entrypoint.md`
- Scene loop: `docs/implementation/scene-loop.md`
- Video integration: `docs/implementation/video-integration.md`
- Orchestration logging: `docs/implementation/orchestration-logging.md`
- QA harness: `docs/implementation/qa-harness.md`

## データ/運用
- データライフサイクル: `docs/data-lifecycle.md`
- データ契約（state/成果物テンプレ）: `docs/data-contracts.md`
- ADR: `docs/adr/`
- パイプライン方式選択（自然言語）: `workflow/playbooks/README.md`
- セキュリティ/コンプライアンス: `docs/security-compliance.md`
- CI/CD: `docs/ci-cd.md`
- DB設計: `docs/DATABASE_DESIGN.md`

## 変更履歴（作業単位）
作業ごとの要求・設計・タスクリストは `.steering/` 配下に残します。
