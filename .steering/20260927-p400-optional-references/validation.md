# 検証

- p400 / downstream layered repair / p420 assets / visual value / frontend auto repair: 111 passed。
- 独立レビュー指摘の「空にできないID配列へnullしか提示できないスキーマ」はprovider呼び出し前に拒否する。予算非消費の回帰テストあり。
- 保存済みSC02 candidateをメモリ上で再検証。resolved registry適用後に残る8件は任意reveal許可配列の不正要素のみ。これらを限定削除するとdirection validatorは成功。正常なasset参照は維持。
- 次のcompilerエラー drawable_prompt_current_moment_missing はfirst_frame_briefだけの意味補正へ戻せることを確認。
- 本番runのartifact/state/予算は変更していない。実際のLLM補正・画像生成完了を意味しない。
- サーバー反映の事前確認で本番cinematic authorの実行を検出したため、稼働中プロセスを中断する再起動は行わない。

## 失敗表示・再開の統合確認

- 関連API回帰（run failure progress / all stage resume / lock conflict / create resume duration）: 46 passed。
- フロント: 13 tests passed、TypeScript / Vite build成功。既存のbundleサイズ警告あり。
- 独立レビュー指摘の再開直後旧失敗・過去完了job上書き・失敗slot優先・工程別理由・再開busy所有権・stage marker対応を実施。エラー文のredactionも空白・JSON・Authorization形式を検証済み。
- 本番生成プロセスの生存を再確認したため、backendの新コードを読み込む再起動は保留。Vite開発サーバーのフロント変更は通常の更新対象。

- UI担当最終検証: test_image_gen_server.py 全315件成功、失敗表示14件成功、フロント13件とbuild成功。最後に区切り空白/JSON形式のredaction回帰3例を追加対応。

- 最終追加回帰: failure tests 16 passed、既存progress tests 12 passed。明示failure stage優先・resume task完了後baseline削除を確認。

- 最終統合API回帰: 50 passed。
