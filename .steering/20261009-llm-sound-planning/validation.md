# 検証結果

2026-10-09。

- 変更前の新規テスト9件の失敗を確認後に実装。
- Domain/API/mixの一括確認: 57 passed。後続のreadset追加・2SE/2BGM実音声試験・stage-groundingを含む最終subset: 57 passed, 6 subtests passed。
- フロント: SoundDesignPanel 5 tests passed。TypeScript/Vite build成功（既存bundle-size警告のみ）。
- 実FFmpeg: 同じcutに異なる周波数のSEを2本重ね、BGM2本を区間ごとに切り替え、各周波数成分の存在/不在を確認。
- 隔離ブラウザー: 動画承認後に空cue、LLMテスト応答からSE2件+BGM2件、手動SE追加、削除、再読込後4件の保持を確認。削除分はarchived_cuesに1件保存。画像はsound-planning-ui.png。
- ブラウザーのLLM応答はmock。共通read-only author transportは単体テストで接続/出力復号を検証。実モデルによる音響案の内容品質と有料音声生成は今回未検証。
- source/revisionの競合、不正selector/尺、LLM失敗、音声生成中のcue削除で既存plan/音源を保持することを確認。
- 既存採用cue/mix/native audio保持。新案は未採用で追記し、完了したとは扱わない。旧sound_design_v1のfixtureに基づく採用・生成・render回帰を維持。
- 実サーバーへ反映。backend/frontend health成功、Codex app-server initialize/thread/no-opチェック成功。OpenAPIでdesign/cue-create/cue-deleteを確認。
- DB起動スキップは既存の承認済み設定を維持。実作品の音声/動画/SE/BGMを生成・変更していない。
- 対象diff check、pointer docs validation成功。commit/pushはこの作業では実行していない。
- 新規テスト追加時の自動承認レビューで上書き懸念が出たが、未存在を確認しexclusive creationで解消。既存テストを削除していない。
