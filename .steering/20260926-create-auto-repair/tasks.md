# 実装状況

- [x] typed診断、compilerの所有工程、subprocessエラー伝達。
- [x] 前回候補と検証エラーを含む補正context、永続履歴、共有上限、再開時の消費維持。
- [x] p220構成案・シーン・修正出力の補正と、尺/時間帯の引き渡し検証からの復帰。
- [x] p330映像設計の補正。
- [x] p420局所・全体補正、投影/画像compilerからの復帰、完了シーン再利用。
- [x] 型付きのrequest materialization失敗をauthorへ返し、同じrunの派生成果物を再構築。
- [x] 画像item単位の再生成、デコード確認、終端画像検証からの復帰。
- [x] フロント進捗に補正工程・対象・回数・理由を表示。
- [x] 作成job→補正→画像生成→通常p680検証→completedのオフライン統合テスト。
- [x] 取消、非収束、再開予算、provider/path/既存工程の回帰テスト。
- [x] 実装ドキュメントを追加。

## 設計からの具体化

履歴は別々のJSONLとカウンターではなく、イベントと予約を一緒にatomic更新するledger.jsonを採用。既存run leaseに加えてroot-bound lockで保護する。
補正roundの予算を共有し、scene set roundに含まれるmodel呼び出しを別の費用上限と誤認しない。
追加の尺・時間帯検証は同じauthor_stageの引き渡しループへ統合。既存authorの保存結果を失敗候補として記録し、失敗時は元の正本へ復旧する。
独立した自動再起動schedulerは追加せず、中断後は既存resume経路で履歴を継承する。

## 運用

本番run・外部画像生成は未実行。生成プロセスがないことを確認してAPI・フロントを再起動済み。Dockerデーモンへ接続できないためDB起動はスキップし、既存DBは変更していない。API/フロントのhealthとCodex initialize/thread/no-opを確認。
