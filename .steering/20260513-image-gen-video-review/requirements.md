# Requirements

## Summary

`server/image_gen_app` に、scene image review から実動画生成へ進むための UI と backend video generation API を追加する。

## Requirements

1. 画像生成画面と動画生成準備画面を分離し、ユーザーが画面を切り替えられる。
2. 画像画面では従来どおり画像生成・候補比較・採用・cut 追加を扱い、動画作成操作は行わない。
3. 動画画面では scene cut だけを表示し、cut ごとに 1 カード、カード内に 1 つの動画並列生成エリアを出す。
   - cut ごとのボタンは `video_generation_requests.md` を更新せず、その cut の実動画生成 API を呼ぶ。
   - 全 cut ボタンも `video_generation_requests.md` を作成/更新せず、全 cut の実動画生成 API を呼ぶ。
   - cut ごとの動画エリアは、指定した複製数に応じて候補 mp4 を並列生成できる。
4. 動画エリアでは、少なくとも次を編集できる。
   - 動画プロンプト
   - 画質
   - アスペクト比
   - first frame reference
   - last frame reference
   - 補助 reference
5. `+` の隣に「全cut動画生成」ボタンを出す。
6. 全 cut 動画生成ボタンは確認モーダルを出し、承認後に frontend review を一時保存してから実動画生成を開始する。
7. 下部に「一時保存」ボタンを出し、現在の prompt / selected candidate / selected references / video settings を `output/<run>/logs/review/frontend/` に保存する。
8. scene image cut 側の末尾に cut 追加ボタンを出す。
9. cut 追加では、既存 cut のどこへ挿入するかと cut 名を指定できる。
10. cut 追加後は manifest と `image_generation_requests.md` に反映し、対応する output 内フォルダを作る。
11. 新規作成や差し替え画像など、動画生成前の frontend review 内容を draft JSON に残す。
12. 新規 run 作成の backend 進捗は、現状どおり Codex app-server による画像生成完了まででよい。
13. 動画画面の追加でフロントを重くしないよう、画像カードへ動画 UI を同居させず、カード単位の遅延描画を維持する。
14. 動画並列生成エリアは既定 3 グリッドを維持し、複製数を増やした場合は横スクロールできる 16:9 の大きいプレビュー枠で表示する。
15. 実動画生成は Kling 3.0 / Kling Omni / Seedance を既存 provider 経由で呼び、候補動画を `assets/test/video_gen_candidates/<cut>/candidate_NN.mp4` に保存する。

## Non-goals

- 生成した動画候補を最終 `video_generation.output` へ採用する操作は今回の必須範囲に含めない。
- LINE bot 側の route は変更しない。
