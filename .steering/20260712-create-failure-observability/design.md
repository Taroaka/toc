# Design

semantic media gate の transport failure 時に、既存 state から failure phase を判定し、一つの diagnostics map を生成する。

- repair status が存在する場合: `semantic_producer_repair`
- それ以外: `semantic_review`

diagnostics は state と create-job debug log の両方へ保存する。state は append-only のまま維持し、既存の supervisor result JSON は上書きせず、`orchestration.p600.supervisor.status=invalidated` と invalidation reason を追記する。

画像生成処理へ入る前の failure では `image_generation.status=not_started`、generated count 0、blocking stage と error kind を記録する。
