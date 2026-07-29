# Requirements

## Summary

フロントの「新しいToCを作成」から storyboard 作成を選んだ場合に、通常の p680 制作工程で生成された cut 画像を使って、検証可能な storyboard render unit と動画生成 request を確実に作る。UI、API、headless regression の契約を一致させ、長時間処理や失敗時に誤った完了・失敗表示や半端な成果物を残さない。

## User Journey

1. ユーザーは新規作成ダイアログで storyboard 作成を選び、タイトル・内容・目標尺を入力する。
2. 作成ボタンを押すとダイアログは即座に閉じ、backend は storyboard 専用 create route で p680 まで実行する。
3. 各 scene の active cut 画像が順序を保って storyboard render unit にまとめられる。
4. provider の尺制限により必要な場合は、scene 内を複数 render unit に安全に分割する。
5. 完了時には manifest、storyboard PNG、video generation request、state が相互に一致する。
6. 長時間処理は backend が terminal state を返すまで監視され、固定30分で誤って失敗扱いされない。
7. 開発者は headless regression から同じ storyboard backend route を再現できる。

## Functional Requirements

1. storyboard create API は p680 のみを受け付け、scene 画像が存在しない p650 を契約上拒否する。
2. frontend は storyboard 専用 endpoint を使用し、title、source、target duration を渡す。
3. frontend の作成ダイアログは入力検証後にモードによらず即座に閉じる。
4. frontend polling は固定試行回数で実行中jobを失敗扱いせず、terminal state まで継続する。
5. scene selector と render unit request id は run 内で一意でなければならず、重複・sanitize collision を拒否する。
6. active cut は一意な cut id、存在する正常画像、provider範囲内の正の尺を持つ。
7. render unit は cut 順序を保ち、provider の最小・最大尺内へ分割される。
8. storyboard PNG は 1920x1080 の正常画像として作られ、各unitのsource cutと対応する。
9. reference-image input contract は first frame を使わず、`[unit先頭cut画像, storyboard画像]` の順で2参照を持つ。
10. video request は exact request id で一意に存在し、manifest の tool、output、duration、references、prompt、prompt hash、negative prompt hash、references digest と一致する。
11. materialization が途中で失敗した場合、今回の呼び出しで作った storyboard、manifest、video request を部分適用した状態にしない。
12. UI文言は「常に1scene=1storyboard」と誤認させず、尺に応じた分割を伝える。
13. headless regression は normal/storyboard のcreate modeを選べ、storyboard時は専用 endpoint を使い、画像生成を無効化できない契約を表す。
14. normal create route と既存 video prompt approval contract を壊さない。

## Success Criteria

- storyboard の API、materialization、validator、headless route、frontend polling の回帰テストが通る。
- duplicate/sanitize-colliding scene selector が deterministic に失敗する。
- request section の欠落、重複、prefix collision、prompt改ざん、reference改ざんを validator が検出する。
- materialization failure 後に既存 manifest/request が保持され、新規 storyboard PNG が残らない。
- frontend build/typecheck が通る。
- storyboard 関連 test suite と既存 image-gen server test suite が通る。
- headless storyboard regression の route/payload/assertion profile を外部生成なしの統合テストで確認できる。
