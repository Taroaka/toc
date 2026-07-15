# Design

## Architecture

一括生成を request/response 型の処理から、run に紐づく永続ジョブへ変更する。

```text
UI POST generate-bulk
        |
        v
  durable job record ---- GET active/status <---- UI reload
        |
        v
 dependency groups (sequential)
        |
        +-- group N items (bounded parallel)
        |       |
        |       v
        |  Codex app-server -> generated image -> candidate import
        |
        v
 next group receives imported dependency paths
```

## Transport

- `asyncio.create_subprocess_exec(..., limit=...)` に bounded な JSONL reader limit を渡す。
- 既定値は画像 base64 payload を収容できる 32 MiB とし、環境変数で安全な範囲内に調整可能にする。
- reader task の例外/EOF は client の terminal error として保持し、pending RPC futures と notification waiters を即座に起こす。
- JSON decode/parse failure も黙殺せず terminal transport error とし、reader が失われた場合の `thread/read` は新しい app-server transport から bounded recovery する。
- `close()` による正常停止は transport failure と区別する。
- image generation lane は API credential/base URL 環境変数を子プロセスへ渡さず、`account/read` が `chatgpt` / Pro を返す場合だけ開始する。

## Job State

- in-memory state に加え、run 配下の JSON snapshot を atomic replace で保存する。
- snapshot は job id, run id, kind, status, group index/count, item states, timestamps を持つ。
- 起動後に snapshot を読み、terminal job は照会可能、`running` のままプロセスを失った job は `interrupted`/`failed` として明示する。
- active/latest endpoint は run id と kind で snapshot を探す。

## First-image Retention

- 「生成画像を保持すること」と「canonical output として採用すること」を分離する。
- 同一 turn の `imageGeneration completed(savedPath)` を受けた時点で結果を返し、turn 全体の終了を待たない。
- request-bound provenance を確認した最初の正常 raster を、`server/data/image_first_retention/runs/<run>/<kind>/<item>/` へ画像 + receipt として atomic copy する。
- receipt は run id、kind、item id、candidate index、destination、SHA-256、generation job id、turn id、image item id を持つ。
- 保持領域は `output/` の外に置き、同じ run/kind/item の最初の画像を以後の処理で上書きしない。
- run 内 candidate も no-clobber import とし、既存番号があれば次の番号へ追記する。
- run が存在し candidate だけが欠けた場合、receipt に記録した同一 destination へ再水和する。別 item や別 kind へは流用しない。
- run 全体が欠けた場合、receipt の schema、run/kind/item、保存先、画像形式、SHA-256、archive directory 対応を検証したレコードだけを archive-only run として列挙する。
- archive-only run の選択時は専用 marker を持つ最小 run を作り、保持画像を candidate として復元する。marker のない同名既存 run は別 run とみなし、内容を上書きしない。
- request artifact まで失われた復旧 run は、保持 receipt から読み取り専用の最小 item payload を合成し、画像の確認と取得を可能にする。

## Execution

- request preview の全 entry から selector/output/reference の依存 DAG を組み立てる。
- canonical `_build_generation_groups` を共通利用する。
- canonical producer dependency はユーザーが追加した reference と別に保持し、reference 編集で依存辺や continuity input が消えないようにする。
- 各 group 内は既存の global limiter と bounded task concurrency を使う。
- item 開始直前に reference path を解決する。先行 item の candidate path があればそれを優先し、なければ canonical path を使う。
- 生成成功は、画像を candidate destination に copy/replace し、画像形式と bytes を検証した後にのみ `completed` とする。
- downstream dependency が失敗した場合は `blocked` とする。

## API/UI Compatibility

- `POST /api/image-gen/generate-bulk` は job を作成して返す。
- `GET /api/image-gen/generate-bulk/{job_id}` は snapshot を返す。
- `GET /api/image-gen/runs/{run_id}/generate-bulk/active` は reload 再接続用。
- UI は job を polling し、terminal 時に request list を再取得する。
- 既存の synchronous response fields は terminal snapshot 内へ保持し、表示モデルの変更を局所化する。
- disk 上の path 付き candidate は単調な事実として扱い、job snapshot と UI merge の path なし状態より優先する。
- semantic block は生成可否の状態として残すが、既に存在する正常 candidate を候補一覧から隠さない。
- UI の item/candidate merge は `(run id, kind)` が一致する場合だけ行い、scope 切替時は前 scope の item を破棄する。

## Timeout and Failure Semantics

- global slot acquisition は独立した queue timeout（または cancellation まで待機）を使う。
- app-server turn は execution timeout を使う。
- reader overflow/parse/EOF は transport error として即時失敗する。
- item ごとの error を残し、他の独立 item は継続する。

## Test Strategy

1. Transport integration: 実 subprocess から 64 KiB 超/3 MiB 級 JSONL を送信し受信を確認。
2. Transport failure: reader failure が notification waiter へ即時伝播することを確認。
3. Group scheduler: group 間順序、group 内並列、依存 candidate reference を確認。
4. API job: POST の即時 return、status/active GET、snapshot 復元を確認。
5. Import: app-server result が candidate path に存在し response へ載ることを確認。
6. Frontend: TypeScript build と reload reconnect state flow を確認。
7. Retention: 最初の画像が不変、run 削除後も archive が残る、candidate 欠落時に再水和できることを確認。
8. Monotonic merge: running/failed snapshot が path 付き candidate を消さないことを確認。
9. Request binding: 別 turn の image item と共有 `generated_images` fallback を採用しないことを確認。
10. Archive recovery: run 全消失時の一覧・synthetic item・candidate 復元、改ざん receipt の拒否、同名 run の非上書きを確認。
11. Scope isolation: run/kind 切替後に前 scope の load/job/generation response を適用しないことを TypeScript build と state guard review で確認。
