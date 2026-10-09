# 投稿計画と結果記録

ToCでは marketing/SNS/publishing/<job-id>/ にplan.json、receipts.jsonl、必要な確認画像を置く。既存の同目的台帳があれば再利用する。認証情報は含めない。生成パイプラインのstate.txtへ配信結果を混ぜない。

## 計画

最終送信前に、少なくとも以下を記録する。

- job_id、source_run（分かる場合）、video_path、video_sha256
- サービス別のplatform、account_handle、caption、hashtags、cover_path/hash
- mode（prepare/publish/schedule）、visibility、scheduled_at（UTCオフセット付き）とtimezone
- AI生成表示等の申告とその根拠
- 本人が確認した内容のplan_sha256、確認日時・会話参照（記録できる範囲）

公開設定が重要な未確定値のままなら送信しない。hashは動画だけでなく、本文・アカウント・公開範囲・日時・表紙・申告を含む確定計画から計算する。承認済みhashと現在のhashが違えば公開前に再確認する。

## 結果

receipts.jsonlには変更ごとに追記する。

- timestamp、job_id、platform、account_handle、video_sha256、plan_sha256
- state：prepared / draft_saved / submitting / submitted / scheduled / published / blocked / unknown
- post_id、permalink、scheduled_at、evidence_path（得られたものだけ）
- observed_status、next_action

submittingは送信前の記録。submittedは受理や審査待ちを確認した状態。scheduledは予約日時が管理一覧で確認できた状態。publishedは本人の対象動画の公開状態を確認した状態。draft_savedには下書きの再表示確認が必要。

## 重複を防ぐ判断

再開時は必ず同一ジョブの記録を読む。
- 同一計画がscheduled/publishedなら新規投稿をスキップする。予約を即時投稿として再作成しない。
- submitting/submitted/unknownなら、画面で既存の結果を照合してから次を決める。
- 同じ動画・同じアカウントの別計画がある場合、意図した再投稿か確認する。日時や文章の変更だけで新規投稿を推定しない。
- アカウント内で別ジョブがsubmitting/unknown等なら、先に解決する。同じ画面に複数の操作担当を並列実行しない。
- 一覧に見当たらないだけでは失敗確定としない。処理・審査・下書き等も確認し、不明な場合はunknownを維持する。

元ファイルやplanを再実行で無言で上書きしない。ユーザーが変更した計画は別revisionとして残す。
