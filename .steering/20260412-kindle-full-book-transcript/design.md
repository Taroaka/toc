# Design

- Python を正本実装とし、次の 3 層に分ける
  - `kindle_web_cdp.py`: Kindle reader tab への接続、reader state 読み取り、ページ画像 export、ページ送り
  - `run-kindle-full-book.py`: full-book orchestration, checkpoint/resume, per-page transcription
  - `run-kindle-full-book.sh`: ユーザー入口の薄い wrapper
- 既存 `extract-kindle-web-cdp.py` は CLI として残しつつ、内部ロジックは `kindle_web_cdp.py` を使う形へ寄せる
- full-book runner の基本 loop は次
  1. run ディレクトリ準備
  2. reader tab 接続
  3. 現在ページを export
  4. `codex exec --image` で単ページ転写
  5. `pages/`, `vision/`, `transcript.txt`, `run_state.json`, `session.md` を更新
  6. 次ページへ進む
  7. 停止条件に当たるまで繰り返す
- checkpoint state は `run_state.json` とし、少なくとも次を持つ
  - run metadata
  - overall status
  - reader URL/title
  - completed page count
  - per-page records (`page_index`, `kindle_page_number`, `image_path`, `vision_path`, `status`, `timestamps`)
- v2 の resume は「reader が次に読むべき位置、または直前ページにある」契約を最低限とする
- per-page transcription は既存の batch shell script を流用せず、runner から `codex exec --image` を直接呼ぶ
- session summary は append 型で更新し、停止時点の reader state と最後に完了したページを追跡できるようにする
- 既存の 5 ページ exporter/transcriber は debug/smoke 用として残す
- task 4, 5, 8 はこの state contract の上に追加しやすいよう、state 更新ロジックと runner loop を分離する
