# Validation

- 失敗する回帰テストを追加してから実装。
- 広い関連テスト: 388 passed / 60 subtests（サーバー、authoring、compiler経路を含む）。
- 最終の予約/ロック/再開処理更新後: 80 passed（production repair、frontend create-job→p680、p400、story、visual、server生成境界）。
- 別のcompiler/B-roll/story-duration/checkpoint群: 86 passed / 25 subtests。
- frontend: Vitest 7 passed、TypeScript/Vite build成功。bundle-size warningのみ。
- pointer docs、diff whitespace、変更Pythonファイルの構文確認成功。
- 画像テストfixtureをmagic bytesだけのデータからデコード可能なPNGへ更新。
- 既存の不正参照拒否テストは、同等の新しいrooted-pathエラー文言も受け付けるよう更新。HTTP 400とprovider未呼び出しの期待は維持。
- 生成jobへのエラー注入から、正常な上流を保持して補正し、1画像だけ再生成して最終p680とjob completedまで到達することを確認。
- 稼働中生成なしを確認後、既存restart helperでAPI/フロントを反映。Docker非接続のためDB起動をスキップ。API/フロントhealthおよびCodex no-op turn成功。
- 本番runの再開、外部画像APIによる生成は未実行。
