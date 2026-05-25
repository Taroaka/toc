# ToC Pointer Guide

## North Star

- ToC は spec-first repo。正本は `docs/`, `workflow/`, `scripts/` に置く。
- 価値の中心は生成物の質にある。ハーネスは動画の中身ではなく、運用・評価・承認・回帰検証を強化するために使う。
- semantic QA は全 stage の不変条件。実装者は artifact 作成時点で上流の意味・役割・因果・参照対象に合う状態にし、レビュワーは存在/形式だけでなく「意味のある成果物になっているか」を確認する。
- 日常運用は Codex 主軸。Claude Code は backup / accelerator として扱う。
- 回答は必要なことを端的に書く。長い説明は正本ドキュメントへ寄せる。

## Repo Scope

- 動画生成
  - 本 repo は、調査・物語・台本・画像/動画/音声生成・最終レンダリングまでの動画生成フローを扱う。
  - 正本: `docs/video-generation.md`
- マーケティング（SNS 限定）
  - 本 repo で扱う marketing は、SNS 内の配信設計、投稿運用、反応分析、改善ループに限定する。
  - 広義の marketing（広告運用、LP、CRM、オフライン施策）は対象外とする。
  - 正本: `docs/orchestration-and-ops.md`

## Entrypoints

- `/toc-run`
- `/toc-scene-series`
- `/toc-immersive-ride`
- 実行方法の正本: `docs/how-to-run.md`

## Server Roles

`server/` はローカル FastAPI server の同居レイヤーで、役割は次の2つに分ける。

- LINE: `/line/webhook` と互換 `/webhook` を受ける LINE bot 用。route は `server/line_app.py`、実処理は `server/line_bot.py` に置く。
- Image generation app: `/image_gen`, `/api/image-gen/*`, `/api/chat/turn` を受ける画像生成 Web App 用。route は `server/image_gen_app.py`、md parser / candidate / zip / repo insert などのドメイン処理は `server/image_gen.py` に置く。

`server/app.py` は shared entrypoint として扱い、共通 middleware、static mount、router 組み立てだけに寄せる。LINE 側と image generation app 側の責務を混ぜない。
`/image_gen` と `/api/*` は `TOC_SERVER_TOKEN` 必須で fail closed にする。ローカル検証で明示的に外す場合だけ `TOC_SERVER_AUTH_DISABLED=1` を使う。

フロントから物語を1から作る Image generation app の create flow は、server 都合の最短 scaffold として実装しない。人間承認だけを frontend handoff にし、それ以外の grounding、deterministic verifier、review-loop prompt/report/aggregate materialization、story/image prompt consistency review、asset/scene request materialization、asset/scene image generation、p650/p680 validation は通常経路を通す。`server/image_gen_app.py` はこの orchestration を呼び出す入口に留め、品質 gate や artifact 契約を迂回する独自ショートカットを持たない。

server 経由の生成でも semantic QA を短絡しない。scene/cut 設計、asset 計画、画像 prompt、生成画像、動画 motion、音声、最終 render は、それぞれ上流 artifact の意味契約を満たす必要がある。構造チェックは関数 verifier で通し、意味判定は contextless semantic review agent の report を verifier が読む。server はファイル数や schema 成功だけで run を成功扱いにせず、意味レビュー用 artifact と検証可能な参照関係を残す。canonical artifact は `logs/review/semantic/<stage>.collection.md`, `.scope.json`, `.prompt.md`, `.report.md` と `review.semantic.<stage>.*` state keys で、frontend create の p680 経路では少なくとも `scene_set`, `scene_detail`, `cut_blueprint`, `asset_plan`, `asset_output`, `image_prompt`, `scene_image` を通す。semantic QA が通らない場合は、その stage の production-side agent に改善点を渡して修正し、同じ contextless reviewer が再レビューする repair loop を使う。修正中は次の process slot へ進めず、`review.semantic.<stage>.loop.status=repairing` と `review.semantic.<stage>.repair.status=in_progress` で semantic QA 修正中であることを state に残す。

## Read Next

- 用語集: `docs/data-contracts.md` の "Core Terms / Glossary"
- 調査: `docs/information-gathering.md`
- 感情設計: `docs/affect-design.md`
- 物語化: `docs/story-creation.md`
- 台本: `docs/script-creation.md`
- 動画生成: `docs/video-generation.md`
- Web UI / brand design: `server/web/docs/brand-design/README.md`
- marketing/SNS: `marketing/README.md`
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
- `workflow/stage-grounding.yaml`
- `workflow/state-schema.txt`
- `workflow/evaluation_criteria.md`
- `workflow/evals/golden-topics.yaml`

## State

- human-facing run navigation: `output/<topic>_<timestamp>/p000_index.md`
- canonical state: `output/<topic>_<timestamp>/state.txt`
- derived state: `output/<topic>_<timestamp>/run_status.json`
- grounding audit: `output/<topic>_<timestamp>/logs/grounding/<stage>.json`
- grounding readset: `output/<topic>_<timestamp>/logs/grounding/<stage>.readset.json`
- grounding audit result: `output/<topic>_<timestamp>/logs/grounding/<stage>.audit.json`
- subagent audit prompt: `output/<topic>_<timestamp>/logs/grounding/<stage>.subagent_prompt.md`
- story review subagent prompt: `output/<topic>_<timestamp>/logs/review/story.subagent_prompt.md`
- image judgment subagent prompt: `output/<topic>_<timestamp>/logs/review/image_prompt.subagent_prompt.md`
- semantic review pack: `output/<topic>_<timestamp>/logs/review/semantic/<stage>.collection.md`
- semantic review scope: `output/<topic>_<timestamp>/logs/review/semantic/<stage>.scope.json`
- semantic review prompt: `output/<topic>_<timestamp>/logs/review/semantic/<stage>.prompt.md`
- semantic review report: `output/<topic>_<timestamp>/logs/review/semantic/<stage>.report.md`
- L2 supervisor progress memo: `output/<topic>_<timestamp>/logs/orchestration/l2_supervisor_progress.md`
- p-bucket supervisor result: `output/<topic>_<timestamp>/logs/orchestration/pXXX.supervisor_result.json`
- eval outputs: `output/<topic>_<timestamp>/eval_report.json`, `output/<topic>_<timestamp>/run_report.md`
- fixed slot workflow: `p100`-`p900` plus fine-grained slots (`p110`, `p120`, ... `p930`) are global across all stories
- per-run differences are recorded with `slot.<code>.status`, `slot.<code>.requirement`, `slot.<code>.skip_reason`, `slot.<code>.note`
- `video_manifest.md` lifecycle: `manifest_phase: skeleton|production`

## Required Workflow

- 非自明な変更は `.steering/YYYYMMDD-<title>/requirements.md -> design.md -> tasklist.md`
- 実装は最小変更で進める
- 変更後は verify を回す
- stage 開始前に grounding preflight を通す
  - manual/chat では `python scripts/prepare-stage-context.py --stage <stage> --run-dir <run_dir> [--flow <flow>]` を標準入口として使う
  - 返ってきた JSON の `readset_path` を起点に、`global_docs -> stage_docs -> templates -> inputs` の順で読む
- `scripts/resolve-stage-grounding.py` と `scripts/audit-stage-grounding.py` は `prepare-stage-context.py` の下位処理として扱う
  - `python scripts/resolve-stage-grounding.py --stage research|story|script|narration|asset|scene_implementation|video_generation|render|qa --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive`
  - `stage.<name>.grounding.status=ready` を確認できない限り、当該 stage を開始しない
  - stage 完了扱いに進めてよいのは grounding が `ready` のときだけ
  - `python scripts/audit-stage-grounding.py --stage research|story|script|narration|asset|scene_implementation|video_generation|render|qa --run-dir output/<topic>_<timestamp>` を続けて実行し、`stage.<name>.audit.status=passed` を確認する
  - slot を skip / optional として残したいときは `python scripts/toc-state.py set-slot --run-dir output/<topic>_<timestamp> --slot p640 --status skipped --requirement optional --skip-reason "<reason>"` を使う
  - fixed `p-slot` contract を触ったら `python scripts/validate-slot-contract.py` を実行する

```bash
python scripts/verify-pipeline.py --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive --profile fast|standard
```

日常の開始ルーチン:

```bash
scripts/ai/session-bootstrap.sh
```

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

全体設計 / 正本ドキュメントへ汎用ルールを追加するとき:

- 人物名・地名・道具名・scene 固有イベントは、原則として直接入れない
- 作品固有の判断は抽象カテゴリへ置き換える（例: 固有人物 -> 後続 scene で reveal する人物、固有場所 -> 非日常エリア、固有道具 -> 禁忌の対象物）
- 作品別の具体判断は run artifact（`script.md`, `video_manifest.md`, `human_change_requests[]` など）へ残す

## Agent Stage Design Docs

各エージェントステップは **作業開始前** に対応する設計書を読み、grounding preflight を通す。全 stage 共通で `docs/system-architecture.md` を読み、その上で stage ごとの設計書へ入る。install 可能な stage skill は `skills/toc-<stage>/SKILL.md` を正本とする。

変更内容:
- production order を asset/image-first に切り替えた
- canonical stage は `research`, `story`, `script`, `asset`, `scene_implementation`, `narration`, `video_generation`, `render`, `qa`

修正理由:
- asset と scene image を先に確定し、実際の visual に合わせて narration と video を仕上げるため

旧仕様との差分:
- 旧 canonical stage は `image_prompt` 中心だったが、公開上は `scene_implementation` に寄せた

| ステージ | 正本ドキュメント | Playbooks |
|---------|----------------|-----------|
| research | `docs/information-gathering.md` | `workflow/playbooks/research/` |
| story | `docs/story-creation.md` `docs/affect-design.md` | `workflow/playbooks/scene/` |
| script | `docs/script-creation.md` | `workflow/playbooks/script/` |
| narration | `docs/implementation/video-integration.md` | `workflow/playbooks/script/` |
| asset | `docs/implementation/asset-bibles.md` | `workflow/playbooks/image-generation/` |
| scene_implementation | `docs/implementation/image-prompting.md` `docs/implementation/asset-bibles.md` | `workflow/playbooks/image-generation/` |
| video_generation | `docs/video-generation.md` | `workflow/playbooks/video-generation/` |
| render | `docs/implementation/video-integration.md` | `workflow/playbooks/video-generation/` |
| qa | `docs/orchestration-and-ops.md` | `workflow/playbooks/video-generation/` |

grounding preflight の正本:

- 契約: `workflow/stage-grounding.yaml`
- resolver: `scripts/resolve-stage-grounding.py`
- audit: `scripts/audit-stage-grounding.py`
- 証跡: `output/<topic>_<timestamp>/logs/grounding/<stage>.json`
- readset: `output/<topic>_<timestamp>/logs/grounding/<stage>.readset.json`
- audit result: `output/<topic>_<timestamp>/logs/grounding/<stage>.audit.json`

## Chat Stage Protocol

ユーザーがこのチャットで `進めて` と言った場合も、slash command と同じ preflight を適用する。

1. 対象 stage と run dir を確定する
2. まず `python scripts/prepare-stage-context.py --stage <stage> --run-dir <run_dir> [--flow <flow>]` を実行する
3. 返ってきた `readset_path` の `global_docs -> stage_docs -> templates -> inputs` の順に読む
4. `stage.<name>.grounding.status=ready` かつ `stage.<name>.audit.status=passed` のときだけ成果物を更新する
5. subagent を呼ぶ場合も、担当 L2 P-Bucket Supervisor が `readset_path` を確定してから、必要 artifact path / 目的 / 出力先だけを渡す。親会話の未記録文脈を前提にしない
6. L1 Run Orchestrator は L2 P-Bucket Supervisor を起動したことを `logs/orchestration/l2_supervisor_progress.md` に記録する。L3 task/review agents はこの進捗メモには記録しない
7. `state.txt` / `p000_index.md` / canonical artifact の最終更新、slot 更新、承認判断は担当 bucket の L2 supervisor が行う。L1 Run Orchestrator は bucket 完了後に `logs/orchestration/pXXX.supervisor_result.json`、required artifact existence、terminal slot state だけを検証する
8. 必要なら `python scripts/build-subagent-audit-prompt.py --stage <stage> --run-dir <run_dir> [--flow <flow>]` を実行し、その出力をそのまま contextless subagent に渡す
   - prompt artifact は `logs/grounding/<stage>.subagent_prompt.md` に保存され、`state.txt` には `stage.<name>.subagent.prompt=...` が追記される
9. image prompt の意味評価を独立 subagent に切り出すときは `python scripts/build-subagent-image-review-prompt.py --run-dir <run_dir> [--flow <flow>]` を実行する
   - prompt artifact は `logs/review/image_prompt.subagent_prompt.md` に保存され、`state.txt` には `review.image_prompt.subagent.prompt=...` が追記される
9. audio-only 生成後に尺が target 未満だった場合は、次を使って duration review 用 prompt artifact を生成する
   - `python scripts/build-subagent-duration-scene-review-prompt.py --run-dir <run_dir> --min-seconds <target> --actual-seconds <actual> [--flow <flow>]`
   - `python scripts/build-subagent-duration-narration-review-prompt.py --run-dir <run_dir> --min-seconds <target> --actual-seconds <actual> [--flow <flow>]`
   - prompt artifact は `logs/review/duration_scene.subagent_prompt.md` と `logs/review/duration_narration.subagent_prompt.md` に保存される
10. 標準運用では prompt builder を直接叩く前に `python scripts/check-audio-duration-gate.py --manifest <run_dir>/video_manifest.md --run-dir <run_dir>` を使い、実尺 gate と prompt 生成を一度に行う

multi-agent が使える環境では、コンテキストを fork しない audit 専用 subagent に `scripts/audit-stage-grounding.py` を実行させてよい。ただし story / script / manifest などの content artifact は編集させず、hard gate は state / report artifact と verifier に置く。run 全体の通常運用では L1 Run Orchestrator が L2 P-Bucket Supervisor を bucket ごとに起動し、L2 が必要な L3 task/review agents を配下で起動する。

## Hard Rules

- `state.txt` を置き換えない。append-only を維持する。
- hybridization は人間承認必須。自動承認しない。
- `run_report.md` は手書きしない。`eval_report.json` から生成する。
- marketing 関連の参照先は `marketing/SNS/` に限定する。通常の story / script / image / video generation と混ぜない。
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
