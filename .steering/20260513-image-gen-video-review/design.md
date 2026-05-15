# Design

## Backend

- `POST /api/image-gen/reviews/draft`
  - frontend の現在レビューを JSON として `logs/review/frontend/` に保存する。
  - prompt、selected candidate、selected references、video settings を含める。
- `POST /api/image-gen/cuts/insert`
  - `video_manifest.md` を YAML として読み、指定 anchor cut の before/after または末尾へ cut を挿入する。
  - 新 cut は `assets/scenes/<selector>/` と `assets/audio/<selector>/` 配下に default output を持つ。
  - manifest backup を作ってから保存し、既存 materializer で `image_generation_requests.md` を再作成する。
- `POST /api/image-gen/video-prompts/create`
  - video draft review を保存する。
  - `logs/review/frontend/video_prompt_design.md` に、変更 prompt / selected candidate / selected references / video settings を要約する。
  - `video_manifest.md` の `video_generation` block と `video_generation_requests.md` を更新する。
  - `replace_all=false` の場合は `video_generation_requests.md` の既存 section を維持し、対象 cut の section だけを置換または追記する。
  - これは request artifact 作成用の API として残すが、動画画面の生成ボタンからは呼ばない。
- `POST /api/image-gen/video-generate`
  - 1 cut の動画候補を実生成する。
  - `first_reference` / `last_reference` / `references` を run-relative image path として検証する。
  - Kling 3.0 / Kling Omni / Seedance の既存 provider client を直接呼ぶ。
  - `candidate_count` 分を並列生成し、`assets/test/video_gen_candidates/<cut>/candidate_NN.mp4` に保存する。
  - provider の submit / poll result は `logs/providers/video_gen/` に debug log として残す。
  - `video_generation_requests.md` と `video_manifest.md` は更新しない。
- `POST /api/image-gen/video-generate-bulk`
  - 全 cut など複数 item の実動画生成用 API。
  - cut 並列数は `concurrency`、候補並列数は各 item の `candidate_count` で制御する。
- `GET /api/image-gen/video-file`
  - `assets/` 配下の mp4 だけを安全に配信する。

## Frontend

- workspace mode を `image` / `video` に分け、画像画面と動画画面を切り替える。
- 画像画面は既存の `PromptCard` だけを表示し、画像生成・候補比較・採用・cut 追加に集中させる。
- 動画画面は scene request を読み込み、`VideoCutCard` を 1 列で表示する。各 card は `SceneVideoPanel` を 1 つだけ持つ。
- 動画画面に出す対象は `output` を持つ scene cut に限定し、共通条件などの非 cut item は除外する。
- `SceneVideoPanel` は動画プロンプト、画質、アスペクト比、秒数、tool、first/last/補助 references、動画候補生成エリアを扱う。
- `SceneVideoPanel` の動画候補生成エリアには cut ごとの実動画生成ボタンを置く。footer と topbar は全 cut 実動画生成として扱う。
- 動画候補生成エリアの既定 3 スロットは desktop/mobile とも 3 グリッドを維持し、各枠は 16:9 の大きいプレビューにする。複製数を増やした場合は横スクロールする。
- 動画タグは `preload="metadata"` で描画し、自動再生せず、動画画面以外では mount しない。
- first reference の初期値は既存生成画像を優先し、未生成の scene output を壊れたサムネイルとして出さない。
- topbar の `+` 横に「全cut動画生成」ボタンを追加する。
- footer に「一時保存」を追加する。
- scene grid の末尾に cut 追加 card を追加する。
- cut 追加 dialog は anchor cut / before-after / cut name を入力し、成功後に scene requests を reload する。
- performance 対策として、動画 UI は動画画面でのみ mount し、画像 card / 動画 card に `content-visibility` を設定する。

## Artifacts

- `output/<run>/logs/review/frontend/<timestamp>_<kind>_draft.json`
- `output/<run>/logs/review/frontend/<kind>_draft_latest.json`
- `output/<run>/logs/review/frontend/video_prompt_design.md`
- `output/<run>/assets/test/video_gen_candidates/<cut>/candidate_NN.mp4`
- `output/<run>/logs/providers/video_gen/*.json`
- `output/<run>/video_generation_requests.md`（request artifact 作成 API を明示的に呼んだ場合のみ）
- `output/<run>/video_manifest.md` backup under `logs/review/frontend/backups/`

## State

Draft save:
- `review.frontend.<kind>.draft`
- `review.frontend.<kind>.saved_at`

Video candidate generation:
- `review.frontend.video.status=draft`
- `review.frontend.video.latest`
- provider debug logs under `logs/providers/video_gen/`

Video prompt artifact creation:
- `slot.p820.status=done`
- `slot.p830.status=awaiting_approval`
- `stage.video_generation.status=awaiting_approval`
- `review.video_prompt.status=pending`
- `gate.video_prompt_review=required`

## Validation

- Python unit tests cover draft save, cut insertion, video prompt request creation, and actual provider-backed video candidate generation without request file mutation.
- TypeScript build verifies the new UI state and API payloads.
