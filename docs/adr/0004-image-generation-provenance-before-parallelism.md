# ADR-0004: Image generation は request-bound provenance を正規ルートにする

- Status: Accepted
- Date: 2026-06-20

## Context

p500/p600 の Codex built-in image generation は、`server/codex_app_server.py` の shared runtime boundary を通して実行している。
生成結果は app-server transcript の `savedPath` から取得するのが本来の正本だが、現実には `turn/completed` より先に `$CODEX_HOME/generated_images` へ画像が保存されることがある。
このため旧実装は `generated_images` 配下の「cutoff より新しい未 claim 画像」を early fallback として拾っていた。

この fallback は単一 item 実行では実用的だが、複数 image turn を並列実行すると、A の waiter が B の生成画像を先に claim し、別 cut の画像を A の output に保存する可能性がある。
`_claimed_generated_images` は同じ画像の二重利用を防ぐだけで、画像が正しい request に属することまでは証明しない。

## Decision

- `generated_images` の時刻順 fallback を image generation の正本にしない。
- 正本は request ごとの provenance record とする。
  - `generation_job_id`
  - `item_id`
  - `kind`
  - `turn_id`
  - `prompt_sha256`
  - `reference_sha256s`
  - `savedPath`
  - `destination`
  - `source`
- destination へ copy してよいのは、provenance が request と一致した画像だけにする。
- app-server transcript から `turn_id -> savedPath` を確定できる場合は、それを primary path とする。
- `generated_images` fallback は明示的に `TOC_IMAGE_GEN_PROVENANCE_POLICY=serial_fallback` を指定した legacy / recovery mode、または debug 用 non-authoritative signal に制限する。
- image generation の正規ルートは request-bound provenance v2 とし、bounded worker pool で並列化する。
- 並列化後の初期値は bounded worker pool とし、scene cut 生成では 4-6 workers を上限候補にする。

## Implementation Direction

1. `ImageGenerationResult` と app-server image debug log に `generation_job_id`, `turn_id`, `prompt_sha256`, `reference_sha256s`, `destination` を保存する。
2. `client.generate_image()` は `savedPath` が transcript / app-server response から取れる場合、それを primary provenance として返す。
3. early fallback は `serial_fallback` mode 以外では `source=generated_images_early_fallback` を authoritative success にしない。
4. `_has_completed_app_server_image_provenance()` は `item_id + destination` だけでなく `generation_job_id/prompt_sha256/reference_sha256s` も検査できるようにする。
5. `TOC_IMAGE_GEN_PARALLELISM` は env で設定可能にし、正規 route の既定値は 6 とする。`TOC_IMAGE_GEN_PROVENANCE_POLICY=serial_fallback` の場合だけ実効値を 1 に clamp する。
6. `request_generation_batch` / `request_generation_group` logs に `parallelismRequested`, `parallelismEffective`, `provenancePolicy` を残す。
7. p500/p600 validator は generated image provenance mismatch を semantic QA ではなく deterministic output failure として報告する。

## Consequences

- 直列実行は、fallback の取り違えを避けるための legacy / recovery safety policy としてだけ残る。
- 正規方針は request-bound provenance を正本にした bounded parallel image generation である。
- scene/cut 数が増えても、画像生成時間を linear に伸ばし続ける設計から脱却できる。
- provenance が確定できない runtime では速さより正しさを優先し、legacy recovery として直列化する。
