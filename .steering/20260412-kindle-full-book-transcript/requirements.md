# Requirements

- `/kindle` は `CDP direct page-image export + per-page Codex vision` を正規ルートとして維持すること
- v2 の完成条件は、手動ログインと手動で本を開いたあと、1回の指示で 1 冊分の `transcript.txt` を生成できること
- 長時間実行の途中で停止しても、完了済みページを失わずに再開できること
- full-book 実行中は、1 ページごとに画像 export と vision transcription を完了させてから次ページへ進むこと
- ページ画像、vision raw output、transcript、session summary、checkpoint state を run ディレクトリに保存すること
- extractor は 5 ページ固定の一括実行だけでなく、`connect`, `read state`, `export one page`, `turn page` として再利用できること
- full-book runner は、既存の成功済み 5 ページ経路を壊さずに追加されること
- v2 では少なくとも「現在アクティブな Kindle reader tab から続ける」resume 契約を持つこと
- v3 の `library page から本を自動で開く` は分離し、v2 の blocking path に含めないこと
- ドキュメントは、v2 の正式入口と補助スクリプトの役割分担を明確に示すこと
