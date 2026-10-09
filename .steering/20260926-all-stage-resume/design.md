# Design

Add durable per-stage receipts around canonical authoring. Bind receipts to exact create input, upstream bytes, and output bytes; re-run current validators even when reusing. An explicit existing-run CLI uses the normal authoring pipeline through p450, then the existing p500 continuation. The API routes incomplete authoring to this worker under its retained execution lease.

Later media operations retain their exact validated request and per-item results in an operation journal. Resuming replays the requested operation with current-input verification and skips valid completed items. Unknown external provider outcomes are not claimed successful. Generation does not imply user selection/approval. Existing normal create remains p680-scoped; media resume only replays an already-requested operation.

Tests use fake authors/providers and temporary runs, never production generation.
