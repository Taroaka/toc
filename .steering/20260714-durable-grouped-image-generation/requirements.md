# Requirements

## Summary

ChatGPT Pro の Codex built-in image generation (`gpt-image-2`) を使う一括画像生成を、依存関係を守るグループ単位の並列実行として扱う。ブラウザをリロードしてもジョブへ再接続でき、生成済み画像を ToC の候補画像領域へ確実に取り込む。

## User Journey

1. ユーザーは image-gen 画面で複数 scene/cut を選び、一括生成を開始する。
2. サーバーは即座に job id を返し、依存のない項目を同一グループで並列生成する。
3. 後続グループは、参照元画像が保存・取り込み済みになってから開始する。
4. ユーザーが途中でブラウザをリロードしても、同じ run の実行中ジョブと進捗が復元される。
5. 完了画像は request/item/candidate に対応する候補パスへ保存され、画面から確認・採用できる。

## Functional Requirements

1. Codex app-server の 64 KiB を超える JSONL 通知（base64 画像を含む数 MiB の通知を含む）を欠落なく読み取れる。
2. app-server の reader が停止した場合、turn timeout まで待たず、待機中 request/notification に原因を伝播する。
3. 一括生成は `_build_generation_groups` と同じ依存グラフを使用し、グループ間は直列、グループ内は上限付き並列で実行する。
4. 依存画像は、生成前に既存ファイルだけへ絞り込まず、先行グループで取り込んだ画像を後続 request に渡す。
5. POST は長時間 HTTP 接続を保持せず job id を返す。GET で job 状態と item 状態を取得できる。
6. run ごとの active/latest job を取得でき、UI はリロード後に再接続する。
7. item は少なくとも `queued`, `running`, `completed`, `failed`, `blocked` を表現し、成功時に candidate/output path を返す。
8. キュー待機と画像生成実行の timeout は別に扱う。キュー待機だけを理由に、未開始 item を generation timeout として失敗させない。
9. 同じ job/item の再実行で、既に取り込み済みの画像を不必要に重複生成しない。
10. subscription lane では OpenAI API へ暗黙フォールバックせず、Codex built-in image generation を使用する。
11. 各 run/kind/item の最初の正常な生成画像は、run 配下へ取り込む前に `output/` 外の保持領域へ原子的に保存し、以後の再生成で上書きしない。
12. 既存 candidate は不変として扱い、再生成画像は次の candidate 番号へ追記する。
13. run 内 candidate が欠落していて run 自体は存在する場合、保持領域の receipt と画像から同一 item の最初の candidate を再水和する。
14. UI と job snapshot は、検証済みの path 付き candidate を `queued` / `running` / `failed` の path なし状態で消さない。
15. request-bound lane は同一 turn の明示的な completed image item だけを受領し、並列実行中に共有 `generated_images` の最新ファイルを推測採用しない。
16. run フォルダ全体が欠落した場合、保持領域の検証済み receipt を run 一覧へ掲載し、選択時に専用 marker 付き復旧 run と候補一覧を自動再構成する。同名の既存 run は上書きしない。
17. UI は run と kind を候補状態の scope として扱い、同じ item id を持つ別 run / asset / scene の候補を混在させない。

## Success Criteria

- 3 MiB 級の image-generation notification を用いたテストが完了する。
- Cinderella の scene1 を含む先行グループが完了後、scene2/scene3 がその画像を reference として開始できる。
- ブラウザリロード後に実行中/完了ジョブが表示される。
- app-server が生成した画像が候補画像パスへ存在し、API response と UI がそれを参照する。
- 既存の単体生成、候補採用、canonical generation の契約を壊さない。
- run フォルダ全体が失われても、各 cut/scene の最初の画像と request-bound receipt が `server/data/image_first_retention/` に残る。
- 消失 run が archive-only run として一覧に戻り、選択すると最初の画像を候補として表示できる。
- 生成済み image item の通知後に turn が長く継続しても、その画像を待たずに受領・保持できる。
