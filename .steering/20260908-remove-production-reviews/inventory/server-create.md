# Server / frontend create 調査

分類: **削除**=制作レビュー/証跡/合格監査、**分離**=通常処理と混在、**保持**=作成や実データの整合、**関連**=手動UIなど範囲を明示する必要がある部分。行番号は調査時点。

## 実際の停止経路

```text
frontend create
  → materialize_run
  → research作成 → _review_foundation_stage(research / p130)
  → Story Architect + Scene Author → _review_foundation_stage(story / p230)
  → scene/cut/script materialization
  → _prepare_authoring_grounding
  → _refresh_p400_review_artifacts → _require_fresh_p400_readiness
  → _run_pre_asset_semantic_fixed_point
  → _validate_pre_asset_provider_gate → asset generation
  → image_prompt semantic review → scene image generation
  → _validate_p650_run_core / _validate_frontend_create_run
```

レビュー呼出を止めるだけでは、後段が「report不存在 / passedではない / snapshotが古い / slot未完了」で停止する。生産処理とgate消費側を同時に変更する。

## scripts/toc-immersive-frontend-run.py

| アンカー | 分類 | 役割と削除時の注意 |
|---|---|---|
| `:164 DOWNSTREAM_REVIEW_STAGES` | 削除 | p400/downstreamレビュー対象と固定spec依存。 |
| `:1154 write_review_input_snapshot`, `:1242 materialize_review_loop_round` | 削除 | 5 critic prompt、aggregator prompt、snapshot、input digestを生成。パス/lock補助を他用途まで消さない。 |
| `:1593 _profile_from_reviewed_research`, `:1644 _profile_from_reviewed_story`, `:4825`以降のreviewed_story投影 | 保持・名称整理 | 名前にreviewedを含むが、研究/物語を下流へ投影する実作成処理。レビュー廃止で消すと作品が作れなくなる。 |
| `:1781–2023` duration/time-of-day contract checks | 分離 | review状態名とは別に、要求尺/型の整合を確認する処理。合格レポート監査ではない。 |
| `:2032 _run_foundation_semantic_review` | 削除 | server `_run_semantic_review`の直接入口。 |
| `:12328 _require_fresh_p400_readiness` | 分離 | `check_manifest_single`の結果、`eval.p400_readiness.status=approved`を必須とする。通常のmanifest構造確認とreview report/loop integrityを分離。 |
| `:12347 _review_status_line`, `:12353 _review_loop_critic_report` | 削除 | review/preapprovalレポート本文作成。 |
| `:12400 _authoring_review_blocking_findings` | 分離 | structural checksからcritic用findingを作る。レポート検査の循環を避ける例外まである。 |
| `:12445 _final_review_text`, `:12484 _build_semantic_review_packs` | 削除 | 最終合格文書、semantic collection/scope/prompt生成。 |
| `:12533 _refresh_p400_review_artifacts` | 削除 | scene_set/scene_detail/cut_blueprint + p400 loops。 |
| `:12543 _require_downstream_review_inputs` | 分離 | request存在チェックとgrounding.readset/レビュー入力要件が混在。 |
| `:12559 _refresh_downstream_review_artifacts` | 削除・通常validator分離 | image_prompt_story_review、judgment、asset_plan/image_prompt pack、downstream loopを生成。 |
| `:12599 _refresh_downstream_review_input_snapshots` | 削除 | レビュー入力を新requestに再結合する証跡管理。 |
| `:12668 _refresh_review_loop_artifacts` | 削除 | modeにかかわらず5 critic形式の文書とaggregateを作成。preapprovedではdeterministic_preapproval。画像段階はpendingレポートを作って後の判定を要求。 |
| `:12833 _write_orchestration` | 分離 | bucketのrequired_artifactsにreview.mdが含まれる。bucket順序/作成状況は残し、review_outputs/必須review slotを外す。 |
| `:13007 _review_foundation_stage`、`:13277` research呼出、`:13336` story呼出 | 削除 | `check_semantic_review().passed`必須。例外でp130/p230 failed、downstream blockedを追記。 |
| `:13057 materialize_run`周辺、`:13235`/`:13836` state | 分離 | `review_mode`, `review.policy.*`, `gate.*_review`, `review.*.status`, p130/p230を初期化。作成入力・artifact生成は保持。 |
| `:13778–13788` | 削除・分離 | grounding/レビュー再生成/p400 approved確認を2回実行する呼出点。1か所だけ外しても残る。 |
| `:13859 _prepare_authoring_grounding`, `:13871 prepare_grounding` | 分離 | docs/readset解決とaudit passed要求を区別。 |
| `:13928` generation branch、`:13978` image_prompt review | 削除・分離 | asset/scene media生成の途中に再レビューが挟まる。media処理は保持。 |
| `:13996 run_pre_media_semantic_pipeline` | 削除 | media無効時でも全設計レビューを実施する別入口。 |
| `:14021 validate`, CLI main `:14214`付近 | 分離 | p650/p680の通常検証とreview合格要求を外す必要あり。 |

## server/image_gen_app.py

| アンカー / 関数群 | 分類 | 内容 |
|---|---|---|
| `:3420–4038` deterministic image prompt review系 | 削除・分離 | review文書の構造、score、bindings、source digest、hard gate、stale再生成。純粋なimage request validationは独立させる。 |
| `:4098 _validate_p650_run_core`、`:4164` | 分離 | research/story必須合格、downstream5stage合格、preapproved証跡を要求。manifest/schema/requests/output/provenanceは保持。 |
| `:4252 _validate_p650_run`, `:4261 _validate_materialized_p650_run`, `:4331 _validate_frontend_create_run` | 分離 | strict validatorとreview gateの混在。stop_targetとresume双方から呼ばれる。 |
| `:4386 _validate_image_prompt_semantic_review`, `:4392 _validate_semantic_reviews`, `:4405 _validate_semantic_reviews_for_media_generation` | 削除 | review不在、不合格、staleを生成阻害条件にする中心。 |
| `:5287` create command / `:27460`以降create job / `:27954`以降API | 分離 | standard/preapprovedをclient → job → CLIへ伝播。互換入力を受けるか、UIと同時撤去する。 |
| `:7030–7081` frontend review draft系 | 関連 | 人間のcandidate選択/変更依頼とファイルパス検証。手動選択機能の削除は自動レビュー廃止とは分ける。 |
| `:8259 _has_existing_narration_review`, `:8711 _append_narration_review_approved_if_ready` | 分離 | TTS/音声候補承認、p720後のready判定。候補選択とreview必須を分ける。 |
| `:9522 _run_narration_semantic_review`, `:9541` artifacts, `:9566` manifest record | 削除 | 全編5 semantic critics、最大並列3、レポートjson/md/critic一覧を保存。 |
| `:9584 _narration_review_blockers`, `:9926 _narration_final_review_is_current` | 分離 | deterministic blockersに全編semantic criticの存在/currentnessを追加。音声/タイムライン実データのチェックは保持。 |
| `:11818 _assert_video_prompt_semantic_review_is_current`, `:11831 _run_video_prompt_semantic_review_before_approval` | 削除 | video_motionレビューとsource freshness必須。承認API `:29743`から起動。 |
| `:11312 _reviewed_video_request_binding`, `:11408–11674` approval系 | 分離 | approval証跡とprovider requestの対応・改変検出が同居。後者を残す。 |
| `:14078–14148` semantic repair reconciliation | 削除・分離 | レビュー指摘修正後のmanifest/source projectionを再構築。正常作成で使うprojectionは残す。 |
| `:14520 _project_image_prompt_reviews_to_p630_p640`、`:14684` | 削除・分離 | image_prompt結果を別review-slotのcritic/aggregateへ転記。requestの凍結とは切り離す。 |
| `:16182 _validate_p680_visual_quality`, `:16272 _p560_failed_check_ids_from_eval_report` | 分離 | 生成出力の通常検証とeval報告/品質判定を区分。 |
| `:16668 _mark_image_generation_review_ready`, `:16770 _validate_image_review_ready` | 分離・関連 | p680人間review待ち/skip分岐と出力ready状態を区別。 |
| `:16810–17197` localized semantic blocked/partial-media系 | 削除・分離 | semantic失敗をscene単位のblocked candidateへ変換。provider実行失敗/通常partial retryは保持。 |
| `:17240 PRE_ASSET_SEMANTIC_STAGES`、`:17249 SEMANTIC_FIXED_POINT_MAX_REVIEWS=24` | 削除 | research/story/scene_set/scene_detail/cut_blueprint/asset_planの反復レビュー。 |
| `:17254 _load_frontend_review_runner`, `:17300 _reconcile_after_semantic_repair` | 削除・分離 | frontend runnerを動的ロードしてレビュー再生成と上流投影再同期。 |
| `:17580 _run_pre_asset_semantic_fixed_point`、`:17672 _validate_pre_asset_provider_gate` | 削除・分離 | レビューが全部current/passになるまで媒体生成前に反復。p400 readiness、preapproval証跡、dependency_sync状態でも停止する。 |
| `:17900`, `:18018` | 呼出削除 | create media経路のfixed-point再実行。 |
| `:18132`, `:18296` review-for-media wrappers | 削除 | image prompt/各stageレビュー起動と失敗分類。 |
| `:18703 SEMANTIC_REVIEW_SLOT_BY_STAGE` | 削除・slot再設計 | research p130, story p230, scene_set/detail p410, cut p420, asset p540, image p640, narration p720, video p820。 |
| `:18714–19069` preapproved系 | 削除 | 省略stage集合、mode読出、deterministic合格文書、critic shard代替文書、レビュー証跡の完全性監査。今回の要望ではこの代替経路も撤去する。 |
| `:19070 _run_semantic_review` | 削除 | pass再利用、output契約再試行、review→repair→review、blocked_transport等。 |
| `:19533–20246` review reuse/watchdog/fingerprint | 削除 | レポートcurrentness、入力変化、進捗・timeout、修復済み証跡salvage。共用runtimeを削除しない。 |
| `:20310–21814` review/repair private workspace | 削除・分離 | review/patch専用scope、immutable snapshot、source証跡、出力import。共有safe-file/lock関数は保持。 |
| `:21815 _run_semantic_review_once` | 削除 | contextless reviewer起動・出力契約検証。 |
| `:22242–25985` shard/aggregate系 | 削除 | scene_set/scene_detail/image_promptの分割レビュー、再試行、scope coverage、集約。 |
| `:25986–26463` report/selector/verdict parser | 削除 | terminal判定、failed_selectors解決、人数/entries/digestなどの監査。直前2回の不具合修正もこの撤去対象に含まれる。 |
| `:26464–27300` review/producer repair turn系 | 削除 | レポート完了待ち、patch型repair、制作側修正agentの起動。 |
| `:28425`、`:29111 api_resume_run` | 分離 | strict p650/p680判定を介して過去review合格を再要求。旧runの失敗状態を無視するだけでは不足。 |
| `:30173 api_narration_review_run`, `:30414 api_narration_review_approve` | 削除・関連 | p720 L3 review script→5 critics→full-run approval。手動音声選択とrender-readyの通常条件は維持。 |

## authoring 自体との境界

`toc/story_author_pipeline.py:1361 author_story_from_research`の `architect` と `scene_author` は作成agentなので保持候補。`:1474`以降の `role="repair"` はレビューcriticではなく構造/参照検証に基づく修復で、現在の既定 `max_repair_rounds=0`。独立レビューと同じ扱いで丸ごと消すと作成データの型・参照検証まで消える。任意のモデル修復経路を廃止するなら別に明記して削除し、`validate_story_document`のどの項目を通常validatorとして残すかを分ける。

## 関連テスト

- `tests/test_image_gen_server.py`: semantic review/repair/preapproved、image generation gate、narration/video approval。
- `tests/test_toc_immersive_frontend_run.py`: review artifact生成、p400 readiness、review mode、semantic呼出。
- `tests/test_semantic_review_workspace_security.py`: review-only workspace/selector。共用パス隔離テストと分ける。
- `tests/test_semantic_repair_reconciliation.py`, `tests/test_semantic_repair_patch.py`, `tests/test_semantic_write_security.py`: review修復/証跡。
- `tests/test_scene_set_semantic_sharding.py`, `tests/test_image_prompt_semantic_sharding.py`: critic shard/集約。
- `tests/test_narration_frontend_workflow.py`, `tests/test_narration_review_gate.py`, `tests/test_narration_semantic_review.py`: 音声作成とreview条件が混在。
- `tests/test_story_author_pipeline.py`, `tests/test_story_authoring.py`: 保持すべきauthoring/参照テストもある。

## 補助インデックス

`../server-symbols.json`にserver/create/story-authoring内のreview/semantic/eval/approval/grounding/readiness/gate名の227 symbols、定義行、同ファイル内caller行を収録。名称検索候補であり227全部が削除対象ではない。上記の分離判断を優先する。
