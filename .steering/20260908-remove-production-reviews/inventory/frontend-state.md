# Frontend / state inventory

調査時点: 2026-09-08。今回の分類は **削除**（制作レビュー agent、レビュー証跡の存在/合格/点数を要求する処理）、**分離**（通常の作成・整合検証とレビュー判定、または任意の人間承認と必須 gate が同居）、**保持**（生成物・候補・人間の選択/編集 UI・アクセス制御）である。人間の承認操作や試聴 UI を残すことと、`human_review_ok` / `listen_evidence` / approved certificate を進行条件として残すことは別判断であり、後者は削除候補を含む関連範囲として記載する。既存の `state.txt` を書き換えて過去履歴を消すことはしない。

## 対象面

`server/web/index.html:10` が `server/web/src/main.tsx` を読み込む `/image_gen` の本番 React 面である。ロケール/i18n ファイルは `server/web` 配下に存在せず、日本語 UI 文字列は `main.tsx` にインラインで置かれている。`server/web/toc-kanban.html` は `server/web/index.html` から参照されない旧静的 kanban で、Review ラベル/Story Point/Value は `:468-488, :759-819, :998-1000` にある。これは image-gen の production review 経路ではなく、今回の削除対象へ混ぜない。

## React の review mode / 進捗状態

| パス / 行 | 現状 | 分類と変更時の注意 |
|---|---|---|
| `server/web/src/main.tsx:218-222` | `FrontendReviewResponse` は `/reviews/draft` の保存結果と `progress` を受けるだけ。 | **分離**。レビュー verdict 型ではなく frontend draft response として名称を整理できる。`progress` は保持。 |
| `server/web/src/main.tsx:352-403` | `RunProgress` に `reviewPolicy`, `reviewMode`, `pendingGates`、`CreateReviewMode = standard | preapproved`、create job の `reviewMode` がある。 | `reviewPolicy/reviewMode/pendingGates` と mode 型は **削除**候補。既存 client 互換のため server が旧 `review_mode` を受けても無視して agent を起動しない契約を先に定める。 |
| `server/web/src/main.tsx:2284-2371` | `narrationReviewBusy/findings/report`、`createRunReviewMode`、`reviewSaveBusy/status` を state に保持。 | narration の auto review state は **削除**。`reviewSave*` は候補/動画設定の一時 draft 保存なので、review verdict state と分離して `draftSave*` に整理する。 |
| `server/web/src/main.tsx:990-1104` | `stageStateLabel` が `awaiting_approval/failed` を表示し、`slotLabelJa` に p130/p230/p320/p430/p540/p630/p640/p720/p820/p850/p930 の Eval/Review 名がある。`runtimeStageLabel` が semantic review failure/ready-for-review 文言を表示。 | Eval/semantic/automated review の label と runtime label は **削除**。`pending/in_progress/failed`、p550/p560/p650/p660 の request/output 待ちを保持する。p680/p750 の human handoff は表示/UI として残すか名称変更できるが、必須承認 gate として残すかは **分離・要決定**。 |
| `server/web/src/main.tsx:1110-1173` | `RunProgressPanel` が `progress.reviewMode` を「全レビュー済みモード」と表示し、stage/slot と requirement/plannedArtifacts を一覧表示。 | mode と自動 review stage の表示を外す。p-slot の pending/failed 表示自体は生成状況を理解するため保持する。`plannedArtifacts` はファイル存在の表示であり、レビュー証跡必須の意味を持たせない。 |

`server/web/src/main.tsx:4328-4342` の create payload は通常/storyboard/world-walk の全経路で `review_mode: createRunReviewMode` を送る。` :4308-4390` の reset も mode を標準へ戻す。UI の `レビューモード` select と preapproved 説明は `:5105-5124`、作成ボタンは `:5222-5235`。select と payload を削除し、旧 payload を受ける場合は server 側で値に関係なく通常の production path を通す。`tests/test_storyboard_frontend_contract.py:31-38` は現在この mode の露出/送信を必須にしているため、存在しないことと旧入力が agent 起動条件にならないことのテストへ置換する。

## 人間の画像承認と自動レビューの境界

画像 UI の候補選択は自動 review ではない。`server/web/src/main.tsx:1667-1978` の `PromptCard` は candidate を `waiting/generating/error/selected/adopted` として表示し、`selectedCandidatePath` をクリック/キー操作で変更する。` :2832-2836` の `selectedForInsert`、`:3167-3198` の `insertBulk` は選択した候補を `candidate_path + output` として `/api/image-gen/insert-bulk` へ送り、canonical `assets/...` へコピーする。この「画像を見て候補を選び、リポジトリへ挿入する」手動操作は **保持**する。ここでの選択を UI 上の採用操作として表示することは保持対象だが、別途 `human_review_ok` や approved certificate を必須にすることは **分離・削除候補**である。`isAdopted`/`adoptedKeys` と採用済み表示（`:1897-1968`、footer `:4906-4917`）は保持する。

画像生成の request/provider failure は review failure と別物である。単体生成の payload と failed candidate は `:2929-2999`、bulk job/candidate failure は `:3001-3134`、footer の生成中/完了/失敗は `:4909-4914` にある。候補固定 slot を空白にせず status/error を残す処理は **保持**する。`server/web/src/components/LiquidGlass.tsx:5-25, :208-231` の status rim、`server/web/src/styles.css:1014-1099, :1129-1178` の candidate selected/error 表示も同様に保持する。

一方、server の gallery payload が semantic blocked item を `generationStatus=blocked` と synthetic failed candidate に変える経路は `server/image_gen_app.py:29352-29439`（`_semantic_blocked_image_item_ids` 分岐）で、generate API 側にも `:31511-31518` の `_assert_scene_candidate_items_not_semantically_blocked` がある。これは UI の候補失敗表示に見えるが、自動レビューを理由に生成を止める gate なので **削除/通常エラーへ分離**する。provider の保存/デコード/provenance/path 検証は候補選択とは独立して **保持**する。

## narration の自動 review と人間音声承認

現在は自動テキスト review と人間音声承認が同じ readiness に結合している。

- `server/web/src/main.tsx:1346-1401` の `itemNarrationAudioReady` / `narrationWorkflowPatch` は `narrationAudioReviewStatus === approved`、`narrationAudioHumanApproved`、revision/hash、音声ファイルを組み合わせる。`audio_review.status` は candidate 試聴後の人間操作状態と自動/証明書状態が同じ名前空間にあるため、**分離**する。candidate の試聴・選択 UI は保持し、`audio_review.status=approved` / `narrationAudioHumanApproved` を動画進行の必須条件として残すかは **削除候補を含む要決定**。可能なら `audioApproval` へ名称を分離し、旧 `audio_review` を読み取る互換層を残す。
- candidate 生成・preview・stale revision・silent の人間確認 UI は `:3562-3781`（text save, silent ok, narration generate, candidate approve）にあり、操作は **保持**する。`/narration-audio/approve` (`server/image_gen_app.py:30151-30169`) の approved candidate certificate を進行 gate として保持するかは **分離**し、revision/hash/file validation は保持する。
- 通し試聴 UI と `listen_evidence` は `:3883-4038`、全編の human approval POST は `:4040-4092` の `/api/image-gen/narration-review/approve`。前者の再生・編集導線は保持候補だが、`listen_evidence`、human approval status、approved certificate を必須にしている現行 gate は **削除/分離候補**である。route/field を任意操作へ変えるか削除するかは要決定。自動 review agent と同じ扱いにせず、任意の人間操作と必須 gate を切り分ける。

自動 p720 review は以下を **削除**し、full narration の human readiness から切り離す。

- state/derive: `:2488-2496` の `narrationTextReviewPassed` と `narrationReadyForVideo` の p750/p720依存、`:2514-2525` の `narrationReviewBusy` を generation busy に含める部分。
- 実行: `:3845-3881` の `runNarrationTextReview` と `/api/image-gen/narration-review/run`。
- finding/report UI: `:4851-4866` の p720 修正点 panel、footer `:4922-4929` の p720 review/status、control station `:4555-4611` および footer `:4975-5015` の p720 ボタン・`narrationTextReviewPassed` disabled 条件。
- response type `NarrationReviewRunResponse` (`:555-562`) と findings/report state (`:2327-2329`)。

削除後に動画/render readiness へ何を必須にするかは別途決める。candidate/listening/editing UI を任意操作として残す案と、human approval/listen evidence を必須 gate から外して実測 duration/path/hash と通常のファイル整合だけを要求する案を区別する。duration の deterministic check は review verdict ではないため保持する。p720 は text authoring/TTS 準備へ再定義するか、UI の自動 review slot としては表示しない。p750/p680 は人間 handoff の表示を残せるが、必須承認 gate として残すかは **分離・要決定**。

## draft 保存・video request materialization

`server/web/src/main.tsx:3301-3325` の `buildReviewItems` は score/verdict を含まず、画像候補、動画 prompt/reference、narration、render path を一つの item payload にまとめるだけである。`server/image_gen_app.py:799-830` の `FrontendReviewItem/FrontendReviewDraftRequest` と対応する。**保持し、review 命名を `buildItemPayload` 等へ整理**する。

` :3327-3352` の `saveCurrentReview` は `/api/image-gen/reviews/draft` に一時保存し、`:4102-4128`/`:4130-4157` の render freeze/final render 前にも呼ばれる。これはユーザーの編集状態と path を保存する draft projection であり、自動 review agent ではない。`server/image_gen_app.py:7077-7119` の `logs/review/frontend/*_draft.json` と `review.frontend.<kind>.*` state keys は **分離**し、draft 名へ移すか、旧ファイルを読み取る互換層を残す。保存自体と path validation は保持する。

` :3354-3367` の `materializeVideoPrompts` は `/api/image-gen/video-prompts/create` に `replace_all=false`, `approve_for_generation=true` を送ってから provider call を行う。`approve_for_generation` は現在 review approval と request freeze が混在した名前だが、target request の materialization/生成許可と provider binding は **保持**し、review report/currentness を要求する意味だけ削除する。`tests/test_video_prompt_frontend_materialization.py:21-84` は「review item」ではなく target item materialization と provider call の順序を検証するテストへ改名する。

## `server/image_gen.py` の進捗・候補 projection

| パス / 行 | 現状 | 分類 |
|---|---|---|
| `server/image_gen.py:48-68` | `RUN_STAGE_STATE_KEYS` に `stage.asset_plan_review`, `stage.image_prompt_review`、`RUN_PROGRESS_BLOCKING_STATES` に `changes_requested/rejected`、terminal に `reviewed/approved` が含まれる。 | review 状態を production progress の blocker/terminal として扱う部分は **削除/分離**。通常の `failed/blocked/pending/in_progress/done/skipped` と handoff の表示データは保持候補だが、human approval を必須条件にするかは別途切り分ける。 |
| `server/image_gen.py:299-366` | state の `slot.pXXX.status` を stage に overlay し、review 用の failed/awaiting 状態も current frontier にする。 | generic slot overlay は **保持**。review verdict の優先順位・`changes_requested/rejected` の blocker 扱いは外す。古い slot key は読めても生成条件に使わない。 |
| `server/image_gen.py:400-450` | `p550/p560/p650/p660` の request file/output existence を current stage に反映し、API に `reviewPolicy`, `reviewMode`, `pendingGates` を返す。 | request file/output existence と p-slot pending は **保持**。review mode/policy/pending review gates は **削除**または段階移行中だけ deprecated empty field とする。 |
| `server/image_gen.py:564-725` | Markdown request と immutable request snapshot の prompt/output/reference/policy/hash を検証。ローカル変数 `review_item` は item 名の誤解を招くだけ。 | schema/reference/snapshot/provenance は **保持**。`review_item` は `request_item` へ名称整理。 |
| `server/image_gen.py:728-749` | display refresh は軽い Markdown projection、generation/mutation path は strict loader を使う。 | UI の read-only refresh と生成時 strict validation の分離は **保持**。 |
| `server/image_gen.py:986-1036` | candidate file を decode/size 検証して `completed` item として列挙。 | **保持**。candidate status は provider/file status であり review score ではない。 |
| `server/image_gen.py:2241-2256` | `item_to_api` は request metadata/candidates 以外の review verdict を含まない。 | **保持**。新しい progress/item contract から review mode fields だけを外す。 |

`read_run_progress` の p550/p560/p650/p660 判定（`:413-426`）は「レビューが存在するか」ではなく request/output の materialization 判定なので、レビュー削除で一緒に消さない。`tests/test_image_gen_server.py:5632-6025` は `pendingGates/reviewMode` と semantic review runtime/slot を直接期待するため、request frontier/failed slot のテストと review-free progress のテストへ分割する。

## DB / canonical state / derived projection

- `toc/process_store.py:18-46` の `toc_process_runs` schema、`:52-118` の `ProcessRecord`、`:133-245` の create/update、`:248-300` の read/helper は job/run/status/current process number/stop target/pid/error/metadata の lifecycle store で、review/score 固有列はない。**保持**。呼び出し側が `metadata` に `review_mode` や review verdict を新規保存しないようにするだけで DB migration は不要。既存 metadata は削除せず無視する。直接の process-store unit test はなく、`tests/test_create_resume_duration.py` と `tests/test_image_gen_server.py:12898` の process-store patch は create/resume lifecycle として保持する。
- `toc/state_store.py:32-54` の append-only/current-view schema と `:1163-1329` の lock-held append/publish は review semantics を持たない generic state engine。**保持**。`state.txt`/`state.current.json` の integrity/current-head 検証は通常 state に必要である。`tests/test_state_store.py:768-803` の `review.scene.status` は任意 key の forged-view 検出 fixture なので、review production gate と誤認して削除しない。
- `toc/harness.py:161-237` の `_order_keys` には review/eval status/score/findings/artifact keys、`:289-311` の `pending_gates` は gate と `review.*.status` の組、`:326-361` の `run_status.json` projection は `pending_gates` と `eval_report` を公開する。state parse/nested state/artifact inventory は **保持**。新規 run の review/eval ordering、pending review gate 算出、score/eval report の production projection は **削除**または legacy read-only compatibility に分離する。古い state key は履歴として残し、進行条件として読まない。
- `toc/run_index.py:13-39` は `REVIEW_LOOP_SLOT_BY_CODE` と review role ordering、`:337-565` は p130/p230/p320/p430/p540/p630/p640/p720/p820/p850/p930 の Eval/Improve Loop slot、`:569-614` は `PENDING_GATE_TARGETS`/`_pending_gates`、`:617-733` は review status normalization/current position、`:943-1086` は `review_mode`, `next_required_human_review`, `pending_gates`, evaluator/human review columns を p000 index に出す。review-only slot/target/column/required state は **削除または human handoff/ordinary work slot へ分離**。固定 p-slot の navigation・file inventory と p680/p750 の handoff 表示、skip/pending/failed status は保持候補だが、human approval を必須 gate として残すかは **要決定**。旧 run の review artifact は `legacy/transitional` として列挙できるが、存在を必須にしない。
- `toc/grounding.py:14-26, :63-106` の approval policy preset/normalize/state entries と `:359-455` の `requires_approved_input` (`review_key`, `allowed_values`, `policy_key`, `passed`)、`:461-488` の grounding report `review_policy` は、資料解決と review approval gate を混ぜている。**分離**し、path/readset/manifest phase/type の通常検証は保持、review key の存在/値/approved requirement は削除。grounding report の review policy は legacy only にする。
- `toc/review_mode.py:17-55` は state と `logs/orchestration/create_input.json` の `preapproved` binding しか行わない review-mode helper。production caller を **削除**し、旧 create payload/state は互換上読み捨てる。`standard/preapproved` のどちらでも同一の reviewer-free path を通すことを API/CLI の受入条件にする。
- `toc/review_projection.py:1-47, :102-319` は review loop/semantic review 用の manifest projection/fingerprint policy。production review callers がなくなれば **削除**候補。通常の manifest/request snapshot hash や provider provenance と混同しない。過去 artifact の読取が必要なら migration-only reader として隔離する。

## API と UI の接続表

| route | frontend 呼出 | 処置 |
|---|---|---|
| `GET /api/image-gen/requests`, `/narration-items`, `/video-items`, `/progress` (`server/image_gen_app.py:29443-29511`) | `main.tsx:2620-2687, :2753-2774` | items/candidates/revision と human selection/listening state の表示は保持候補。`reviewMode/reviewPolicy/pendingGates` と semantic blocked synthetic candidate は除去/legacy化。human approval certificate fields を readiness gate として残すかは分離。 |
| `POST /runs/create*` (`:27946-28201`) | `main.tsx:4308-4342` | 旧 `review_mode` は受理して無視してもよい。新 UI は送らない。standard/preapproved による agent 起動差をなくす。 |
| `POST /generate`, `/generate-bulk`, `GET /candidates` (`:31511-31678, :29908-29939`) | `main.tsx:2929-3134` | 生成、bulk job、candidate recovery、decode/path/provenance は保持。semantic review blocker のみ除去。 |
| `POST /insert-bulk` (`:31912-…`) | `main.tsx:3167-3198` | 人間の候補選択→canonical 挿入操作として保持。別の review certificate を必須にする条件は追加しない/削除候補。 |
| `POST /reviews/draft` (`:29584-29604`) | `main.tsx:3327-3352`, render 前 | draft snapshot と path validation に分離。verdict/score を要求しない。 |
| `POST /video-prompts/create` (`:29834-29841`) | `main.tsx:3354-3367, :3443-3445, :3532-3534` | request materialization と provider binding は保持。`approve_for_generation` は request-ready の意味へ整理し review report を要求しない。 |
| narration draft/text/generate/silent/audio approve (`:29942-30169`) | `main.tsx:3562-3781` | authoring/revision/candidate と試聴・選択 UI は保持候補。audio approved state を後段の必須 certificate として残すかは分離。 |
| `POST /narration-review/run` (`:30172-…`) | `main.tsx:3845-3881` | **削除**。L3/semantic text review 起動、findings/report 保存を除く。 |
| `POST /narration-review/approve` (`:30413-30427`) | `main.tsx:4040-4092` | route 名は review でも full-run human listen/approval。自動 p720 条件から分離する。full-run approval/listen evidence を任意操作として残すか、必須 gate/certificate とともに削除するかは **要決定**。 |
| render freeze/final (`:30480-30504`) | `main.tsx:4102-4157` | duration/path/audio/video の通常検証と render は保持。review draft 保存は draft projection として分離。 |
| `POST /chat/turn` (`:32097-…`) | `main.tsx:4392-4428, :5584-5598` | `approvals` は app-server の interactive tool approval で、production content review ではない。**保持**。 |

## 関連テストの更新範囲

- `server/web/src/createRunPolling.ts:1-23` と `createRunPolling.test.ts:15-78` は create job の running/terminal polling のみ。paused message の「承認待ち」は人間 handoff なら保持、auto review mode の意味にしない。
- `tests/test_storyboard_frontend_contract.py:31-38` は mode select/送信/表示を要求するため review-free contract へ置換。
- `tests/test_video_prompt_frontend_materialization.py:21-84` は `buildReviewItems`/`approve_for_generation` の命名を整理するが、target-only materialization、provider call 前の順序、dirty field/candidate保持は保持。
- `tests/test_narration_frontend_workflow.py:156-329`（p720 findings、semantic currentness、supersession）は **削除**。`:467-1010` の output traversal、candidate generation、revision/hash、tamper、試聴・選択 UI は保持候補だが、human approval certificate を必須にする assertions は **分離/削除候補**。`:1018-1083` の semantic blocker/agent override は削除し、`:1116-1341` の timeline/duration/path 整合は保持。`:1435` 以降の二段 approval テストは、任意の human operation と必須 readiness gate を分けて再編する。
- `tests/test_frontend_duration_gate.py:49-149` の 80% duration/file coverage は deterministic gate として保持するが、`review.duration_fit.status`/p750 auto review assertion は review-free の期待へ変更する。p750 human approval を必須にする assertions は **分離/削除候補**。
- `tests/test_image_gen_server.py:5632-6025` の progress suite は `pendingGates/reviewMode` と semantic runtime/slot 期待を除去し、p550/p560/p650/p660 request frontier と generic failed/in-progress frontier を保持。`:8697-9054` candidate listing/retention/insertion は保持。`:10875-11723` と `:16618-16720` の semantic blocked item rejection/synthetic failed candidate は通常 provider generation/error semantics へ書き換える。frontend draft `:19374-19420`、narration candidate/approval `:21065-21253` 以降は path/revision/file integrity を保持し、review report/gate/certificate assertions は分離または削除候補。
- `tests/test_run_index.py:17-62, :172-199` と `tests/test_toc_state_script.py:111-167` は pending review gate、Eval Loop、`Review: approved`、review-specific CLI を要求している。review-only assertions は削除し、slot skip/pending/failed、run index/state projection、明示的 human image handoff のテストへ置換。
- `tests/test_state_store.py:768-803` は generic state integrity fixture として保持。`tests/test_review_projection.py` 全体（`:1-688`）は review-only fingerprint/currentness contract のため production から切り離し、必要なら migration-only test に移す。
- `tests/test_toc_immersive_frontend_run.py:1256-1375, :1485-1785, :2359-2440` は frontend create の review policy/mode、review phase、preapproved semantic pass を固定している。create/materialization ordering と lock/path/manifest/output 検証は保持し、review agent/mode/証跡要求のみ削除。

## 互換性の要点

1. `state.txt`、`state.current.json`、既存 `p000_index.md`、過去 `review.*`/`eval.*`/`review.frontend.*`/`audio.review` は履歴・legacy data として残し、production の進行条件では読まない。
2. 旧 client が `review_mode=standard|preapproved` を送っても、どちらも同じ reviewer-free production path を通す。暗黙に preapproved の疑似合格を materialize する fallback は作らない。
3. 壊れた YAML/JSON、参照先不存在、request snapshot drift、画像/音声 decode 失敗、provider output/provenance 不一致、path/lock violation は通常の deterministic error として検出し、review 不在を理由に止めない。
4. `selectedCandidatePath`、候補 status/error、`insert-bulk`、narration candidate の試聴/編集/選択、通し試聴 UI は自動 review agent と独立した制作操作として扱う。これらを任意操作として残すか、`human_review_ok` / `listen_evidence` / approved certificate を readiness gate として残すかは分けて決める。後者は削除候補に含む。
