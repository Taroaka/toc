# 検証記録（2026-10-09）

- 変更前: 新規回帰3件が想定どおり失敗（数値既定未指定、共通mastering未実装、preview_item未実装）。
- 専用＋既存ElevenLabs/lead-in: 18 passed。
- sound mix/render/script/frontend workflow: 35 passed。
- 追加のlead-in検証: 3 passed（未指定0.5秒、明示0秒・1秒を保持）。
- 最終delta: narration audio policy 3 passed（無音cutの試聴をrawで維持するケースを含む）。
- フロントTypeScript/Vite build成功。既存のbundle-size警告あり。
- live-preview.json: HTTP 200、audio/mpeg、19.043265秒、原音hash不変。既存シーン1素材を使用しTTS/API課金なし。
- 元音声/candidate hashを変更せず、試聴はassets/test/render_narration_previewへ派生保存。
- Codexによる画面クリックの試聴操作は未実施。フロントの接続はbuildと、同じ稼働HTTP endpointへの実リクエストで確認。
- 通し試聴はcut単位と全編で測定単位が異なるためgain一致を保証しない。最終mix全体へのLUFS指定ではない。
- 開発サーバーは再起動して反映。以前から承認済みのDB起動スキップを維持。DBの変更はしていない。
- ログ: .codex/run/toc-server/。フロント127.0.0.1:5173/image_gen/、バックエンド127.0.0.1:8000。
- 他の既存未コミット変更は保持。commit/pushは未実行。

## 最終再起動の補足

最終delta反映の再起動ではバックエンドHTTPチェック成功後、Codex app-serverのinitialize/thread/no-opチェックが失敗した。この再起動ではfrontend開始前にhelperが終了したため、helperの既存start_frontend/wait_http関数だけを実行してfrontendを復旧した。Codexの生成transportは最初の再起動では成功、最終再起動では失敗しており、音声試聴HTTPの正常性とは区別する。DB起動をスキップした設定は既存承認に基づく。
