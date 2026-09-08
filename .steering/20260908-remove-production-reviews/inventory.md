# 制作レビュー・合格監査の撤去対象一覧

調査対象: 現在の ToC checkout。目的は、制作中のレビューagentと、レビュー証跡・合格・点数を進行条件にする仕組みを、レビューmodeに関係なく撤去するための全体把握。

**この成果物は洗い出しと削除設計。production codeの削除、runの再実行、過去のstate変更は行っていない。**

## 結論

p230を単独で外す変更では完結しない。レビューは①レビュー実行、②合格証跡の作成、③証跡/スコア監査、④生成前gate、⑤slot/state/UI/再開判定、⑥docs/skills/agent規定に分かれている。

画面上の「5 critics + 1 aggregator」と、serverのsemantic review/repairは別実装である。frontend createにはcritic形式の文書を決定論的に作る経路もあり、表示名だけで実際のagent数や削除範囲を判断できない。

`preapproved` は完全なレビュー機構廃止ではない。semantic pack、deterministic_preapproval report、critic形式の文書、input digest、mode provenanceなどを作成/検査する経路が残る。今回の削除では「全てをpreapprovedにする」「空のpassed文書を作る」方式は採らず、読み書きと要求条件を撤去する。

## 分類

| 分類 | 意味 |
|---|---|
| 削除 | レビュー専用のagent、採点、判定、レビューを証明するレポート/監査 |
| 分離 | 通常処理とレビュー要件が混在。レビュー依存だけを外す |
| 保持 | 実作成、ファイル/型/ID参照、実際のprovider request/output対応など |
| 関連 | 手動の画像/音声選択、UI、過去run互換など、削除と同時に整える箇所 |

## 撤去する仕組み

| 系統 | 中心ファイル | 対象 |
|---|---|---|
| 作成後の5 critic + aggregator | `toc/review_loop.py`, `toc/review_loop_runner.py`, `scripts/build-review-loop-round.py` | 最大round、critic人数/独立性、aggregate/final report、round/input snapshot監査 |
| 意味レビュー | `toc/semantic_review.py`, `toc/semantic_pack*.py`, `scripts/build-semantic-review-pack.py`, `scripts/run-semantic-review.py` | collection/scope/prompt/report、criteria結果、対象網羅、digest、passed gate |
| レビュー結果に基づく修正 | `toc/semantic_review_loop.py`, `toc/semantic_repair_patch.py`, `toc/semantic_repair_reconciliation.py` | producer repair agent、review→repair→review、再レビューの依存同期 |
| server内のreview実行 | `server/image_gen_app.py` | foundation review、shard reviewer、集約、transport/output-contract retry、review専用workspace |
| create途中のレビュー | `scripts/toc-immersive-frontend-run.py` | p130/p230、p400 review生成、downstream review生成、pre-media semantic pipeline |
| 点数・合格点 | `toc/stage_evaluation/*`, `toc/stage_evaluator.py`, `scripts/review-*-stage.py`, `workflow/evaluation_criteria.md` | stage score、rubric閾値、閾値未満によるfail、review報告書の合格判定 |
| 読み込み/監査証跡 | `toc/grounding.py`, `scripts/prepare-stage-context.py`, `scripts/audit-stage-grounding.py`, `scripts/build-subagent-audit-prompt.py` | audit-agent、readset/audit passed要求。資料解決・元資料を読む処理は分離 |
| 進行を止める検証 | `scripts/verify-pipeline.py`, `toc/harness.py`, stage evaluators, server p650/p680/provider gates | review有無、必須review項目、passed/approved、人数/順序/hash、slot完了を必須とする条件 |
| ナレーション・動画 | `toc/narration_semantic_review.py`, `toc/narration_review_gate.py`, `scripts/run-p720-*`, server video_motion review | 全編5 critics、agent_review_ok、arc/semantic報告のcurrentness、video prompt合格監査 |
| mode・UI・再開 | `toc/review_mode.py`, `toc/p500_resume.py`, `toc/run_index.py`, `server/web/src/main.tsx` | standard/preapproved分岐、review待ち/failed、証跡再生成、resume阻害条件 |
| 規定・テンプレート | `docs/`, `workflow/`, `skills/`, `.codex/`, `.agents/`, `.claude/` | レビューを再要求する設計書/agent規定、必須slot、テンプレート内review section |
| テスト | `tests/`、frontend test scripts | レビュー必須を固定するテストの撤去/更新。通常の生成・型・ファイル安全性テストは残す |

## 合格点・回数の具体例

| 実装 | 現在の条件 | 撤去対象 |
|---|---|---|
| `toc/stage_evaluation/common.py:66` | storyのscene_densityは0.85、grounding/affect/handoffは0.80など | rubric閾値を下回ると失敗する採点gate |
| `scripts/review-image-prompt-story-consistency.py:286` | prompt_craft 0.65、他の主要項目0.60 | promptの品質採点と合格条件 |
| `scripts/review-narration-text-quality.py:151` | TTS 0.70、story_role_fit 0.55、anti_redundancy 0.45など | 自動採点、agent_review_ok、未解決指摘による停止 |
| `toc/review_loop.py:29` | 最大5round、各round5 critics | critic/aggregate文書と人数・round監査 |
| `toc/semantic_review_loop.py:25` | 通常2attempt、scene_set 3attempt | 意味review→repair→reviewの別反復系 |
| `server/image_gen_app.py:17249` | pre-asset fixed point 最大24review | 上流のレビューが全てcurrent/passになるまで繰り返す処理 |

全rubricの重み・閾値・score計算式・durationとの区別は [core.md](inventory/core.md) に収録。実測尺やprovider制限の数値は品質スコアとは分ける。

## 詳細調査

各レポートは具体的な関数・行番号・caller・削除時の依存を記載する。

1. [server/createと実呼出経路](inventory/server-create.md)
2. [採点・レビュー本体・verifier](inventory/core.md)
3. [CLI・ナレーション・動画・再開](inventory/pipeline.md)
4. [画面・状態・mode・関連テスト](inventory/frontend-state.md)
5. [正本・workflow・skills・agent規定](inventory/contracts.md)

## 画面・既存runの扱い

- 新規作成UIのreview mode選択と送信値を撤去。旧clientの `review_mode` は互換読取しても、実行分岐には使用しない。
- `p230 failed`などレビュー専用slotを旧runのcurrent blockerとして扱う条件を外す。通常の生成失敗は引き続き表示する。
- 画像候補の選択、音声試聴、編集内容のdraft保存は、名前にreviewが含まれていても制作操作として分離できる。一方、その操作の「承認証跡が必須」というgateは別の撤去候補。
- `toc/process_store.py` と `toc/state_store.py` はreview専用DBではない。job管理、append-only履歴、lock/current state整合は残す。既存metadata/stateのreviewキーを消すための一括DB変更は不要。
- レビュー以外の原因で失敗したrunまで合格/成功へ書き換えない。再開時は現存する制作物と通常の実行前提から判断する。

## 削除順序

1. 撤去後のstage順序と通常処理完了条件を定義する。review slotを `passed` に偽装して残さない。
2. server/create/CLIのreviewer/critic/aggregator/repair呼出を外す。
3. 同時に、verifier・provider前gate・p650/p680・narration/video・resumeの「reviewがある/合格した」検査を外す。
4. review-onlyレポート、snapshot、collector、scorer、aggregate、修正workspace、mode代替証跡の作成を撤去する。
5. state/slot/API/UIを新しい完了条件へ更新する。旧runの履歴は残し、旧review失敗を進行条件に使わない。
6. docs/workflow/templates/skills/agent instructionsを同期する。repo外にinstall済みのToC skillコピーも残存指示を確認する。
7. review必須性だけを固定するテストを更新/撤去し、レビュー証跡無しで一連の作成と再開が動くテストへ置き換える。
8. review呼出・read/write・passed依存が残っていないか、静的検索と通常実行入口の両方で確認する。

## 削除と混同しないもの

- Story Architect / Scene Author / script / image / TTS / videoの作成処理。
- JSON/YAMLの読み込み、必須のデータ型、IDの参照先、ファイルdecodeなど、処理自体が成立するための条件。
- 画像/video requestのprompt/reference/outputが同一リクエストに属すること、lock/パス/権限。`review.image_prompt.request_freeze.*`のような名前でも実request結合を担う部分は分離する。
- ユーザーが候補を選ぶUIと、その選択結果を保存する処理。必須承認gateと画像/音声候補選択は同一ではない。
- `reviewed_story`などの名称を持つだけの物語投影関数。実際は下流生成に必要なことがある。
- 汎用のソフトウェア開発向けcode-review/security-reviewの仕組み。今回の制作レビュー廃止とは対象が異なる。

## 調査範囲と網羅性

- 現在のcheckoutの `server`, `toc`, `scripts`, `docs`, `workflow`, `config`, `skills`, `tests`, `.agents`, `.codex`, `.claude`, `.github`, README/入口文書を検索した。
- [検索インデックス](search-index.md) / [JSON](search-index.json)には435ファイルの広いキーワード一致を保存した。これは削除対象435件という意味ではなく、無関係な同名語や開発用スキルも含む候補である。
- [server symbol index](server-symbols.json)には主要3ファイルの227定義と同ファイル内callerを収録。削除/保持の意味分類は詳細レポートを優先する。
- `output/`の既存生成物、`.claude/worktrees/`の別checkout、`marketing/`, `kindle/`, `improve_claude_code/`は削除候補から除外。過去の証跡ファイルを消して問題解決したことにはしない。
- repo外のinstall済みToC skillは別コピーが存在するため、正本だけの変更では古いreview規定が残る。詳細はcontracts.md。
- 動的実行でしか現れない外部サービス内部までは対象に含めない。ここで「全体」は上記checkoutとToC skill設定の静的依存調査範囲を指す。
