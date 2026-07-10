# Drawable image prompt runtime design

## 1. Single compiler boundary

新しい pure module を scene/cut prompt の唯一の compiler とする。入力は normalized な `first_frame_visual_plan`、cut の asset IDs、解決済み bible/reference、style/negative constraints。出力は次の二つ。

- `DrawablePromptIR`: 選択した drawable fragment と、空・motion-only・metadata・非可視情報として除外した source path/reason。
- `ImageApiPromptPayloadV2`: 自然文 prompt、policy/compiler version、prompt hash、source digest、included/excluded fragment trace。

prompt renderer は固定 block を全部出すのではなく、存在する fragment group だけを安定順で自然文化する。必須なのは画像全体の style/format、現在の画面内容、最小の禁止事項だけ。人物・object・location・blocking・lighting・reference continuity は条件付きである。

## 2. Separation of responsibilities

- `scene_event` / `cut_contract`: story truth、因果、reveal、review の正本。
- `first_frame_visual_plan`: cut 開始時に静止画として見える内容の normalized projection。
- `drawable_prompt_ir`: provider に描かせる候補を採否した compiler trace。API へは送らない。
- `api_prompt_payload.prompt`: provider が描く自然文だけ。
- request snapshot: 実行に必要な exact prompt/reference/destination/provenance contract。
- request Markdown: snapshot の human-readable projection。debug は別 fence、`api_prompt` fence は exact prompt の表示。

## 3. Snapshot and edit semantics

`image_generation_request_snapshot.json` を request Markdown と同じ run に atomic write する。snapshot は request revision と source digest を持つ。production loader は snapshot を読み、schema、item uniqueness、prompt hash、reference hash、destination containment を検証する。

人間が prompt を更新する route は、manifest/payload を更新後に request Markdown と snapshot を再 materialize する。Markdown だけの編集で snapshot と不一致になった場合は stale request として実行を拒否する。fence parser は named `api_prompt` の closing fence を越えて置換しない。

## 4. Provenance and output reuse

各 item について以下を exact tuple として記録する。

`generation_job_id, request_revision, item_id, turn_id, image_generation_item_id, prompt_sha256, reference_sha256s, saved_path, destination, output_sha256, compiler_version`

送信前に snapshot の hash を再計算する。受理後は request-bound item が exactly one であること、saved path がその item に属することを確認して atomic copy する。既存 output は provenance tuple と output content hash が一致する場合だけ reuse する。

## 5. Concurrency and resume

- per-run lease: run directory 内の lock file を `flock(LOCK_EX|LOCK_NB)` し、create/resume 全体で保持する。
- global image semaphore: runtime lock directoryに N 個の slot lock を作り、各 provider turn の直前から provenance/copy 完了まで一つ保持する。
- serial fallback:専用 global lock を追加し、process 境界でも並列化しない。
- resume: item 状態を `pending|running|succeeded|failed|stale` として journal 化し、一致する `succeeded` item は保持、不一致/未完了だけを再投入する。

process crash では OS が flock を解放する。artifact の `running` は次の resume で provenance/output を検査して `succeeded` または `stale` へ回収する。

## 6. Gates and semantic review

- prompt completeness は IR の採用 fragment と cut の宣言依存を比較する。全 cut に同じ固定 block を要求しない。
- leak gate は API prompt のみを検査し、debug/trace は別 artifact で許可する。
- request gate は snapshot/Markdown/payload prompt hash の一致を検証する。
- semantic pack は per-scene image prompt shard を持ち、review orchestrator は expected entry count > 0 と reviewed count 一致を必須にする。
- `agent_review_ok` の欠損を true とみなさない。

## 7. Migration order

1. compiler + conditional gates + tests
2. frontend/materializer integration and legacy prompt decoupling
3. snapshot + safe editor + send-time provenance
4. output reuse/resume + leases/semaphore
5. semantic shards/docs/templates/frontless verification

旧 v1 artifact は compatibility loader が読めるが、新規 production 実行で snapshot がない場合は明示フラグなしに silent fallback しない。
