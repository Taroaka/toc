# Undetectable.io「Instagram AI automation」調査メモ

確認日: 2026-10-09 JST

## 結論

Undetectable.io の 2026-06-16 記事は、Codex Desktop + Undetectable Browser + MCP サーバーで Instagram の単一フィード投稿を公開できた、という販売元自身の事例である。公開後のプロフィールグリッドを示す画像はあるが、外部の第三者が同じ投稿・アカウント・ログを検証した証拠ではない。記事と公式動画の範囲は画像（photo/feed post）で、Reels、TikTok、動画ファイル投稿の実演は確認できない。

ToC の実装根拠としては「Codex系エージェントで、アップロード→キャプション→公開確認までのUI状態を扱える」という参考例に限定して採用する。anti-detect/多重アカウント製品の導入や検出回避を前提にした採用は勧めない。公開ボタン前に人間確認を必須にし、投稿成功は画面の確認と投稿URL/時刻の記録で検証する。

## 主記事と視覚証拠

- 主記事: https://undetectable.io/blog/instagram-ai-automation/
  - ページ表示日: **June 16, 2026**。
  - 主張: Codex Desktop、MCP、Undetectable Browserでプロファイルを起動し、Instagramへ画像をアップロード、キャプション入力、Shareを押し、プロフィールの最新グリッドをスクリーンショットで確認したというもの。
  - 記事は「Undetectableの無料版でも利用できる」「OpenAIの有料サブスクリプションが必要」と明記する。Node.jsも必要とする。
  - 記事に埋め込まれた画像は次の通り。
    - 初回プロンプト画面（INSTAプロファイル、画面操作の逐次指示）: https://cms.undetectapp.com/assets/d0db9d9e-87a7-431d-9d0b-66044e968a4c?format=webp&quality=90
    - 最適化プロンプトの末尾（Share後にプロフィールを開き、グリッドを確認する指示）: https://cms.undetectapp.com/assets/c9a5918b-5c8b-4ecf-b0c2-01e66d08201d?format=webp&quality=90
    - Codex画面とInstagramプロフィール（241 posts / 369 followers / 128 following）。Codex側は「/create/details/に到達、caption入力、Share発火、homeへ戻った」と報告し、確認スクリーンショットを撮ると記載: https://cms.undetectapp.com/assets/b8bab324-e3ef-4640-9dd2-ea156a520077?format=webp&quality=90
    - グリッドを表示した修正版確認画像。Codex側はヘルパーの `capture_profile_grid.mjs` を編集・実行したと表示し、左側に複数の画像タイルが見える: https://cms.undetectapp.com/assets/06865c1e-63aa-4528-8d16-21a4327d683d?format=webp&quality=90

画像から読めるのは「販売元が用意したCodexとブラウザのスクリーンショット」であり、Instagram側の公開時刻、投稿URL、アカウント所有者、投稿がその後も残ったことは確認できない。profile headerの241 postsという数字も、当該テストで1件増えたことを証明しない。記事本文の「It worked! The post was published」は自己申告として扱う。

## 依存関係・経路

記事に明記された接続設定は `npx -y undetectable-local-api-mcp-ts`、ローカルAPI `http://127.0.0.1:25325`、タイムアウト `60`。Codexを再起動し、Undetectable Browserを開くよう案内している。最適化プロンプトは、プロファイル起動、返された `websocket_link` への接続、Instagramの作成ページ、ファイル選択、caption textarea、Shareボタン、プロフィールグリッド確認という流れを指定する。

現在の公開GitHub READMEも、MCPサーバーがTypeScript/Node.js製で、`npx`実行、ローカルAPI、ブラウザ操作ツール（open URL/tab、click、fill、scroll、evaluate、screenshot等）を提供すると記載する: https://github.com/undetectable-io/Undetectable-browser-MCP 。Codex CLI向けのMCP設定例もある。READMEは接続後にAIがプロフィール削除・Cookie消去・ブラウザ操作など全APIへアクセスでき、個別確認はサーバー側で行わないと警告する。人間レビューを必須にする設計上の重要な注意点である。

経路は2つに分けて理解する。

1. **Codex + MCP**: 自然言語プロンプトからMCPツールを呼ぶ。記事の最初の試行はクリック列を逐次指示し、最適化版は直接URL/DOM要素を指定する。画像43/44では、実際にCodexが確認用の `capture_profile_grid.mjs` を編集・実行しており、完全な「スクリプトなし」ではない。
2. **直接スクリプト/API**: Undetectable Local APIにNode.js等から接続し、Puppeteer/Playwright/Selenium等を使う経路。記事のNode.js要件やスクリーンショット用ヘルパーはこの境界を示す。ただし記事は実行コード、ログ、投稿URLを公開していない。

## 写真・Reels・TikTokの切り分け

- 主記事は一貫して「image」「ready images」「image file」「input[type=file]」を扱い、単一画像のInstagramフィード投稿である。
- 最終画像はプロフィールのグリッドに画像タイルが並ぶだけで、Reelsの動画アイコン、動画アップロード、音源、カバー、トリミング等は見えない。
- TikTokの投稿手順、Reels投稿手順、動画ファイルの成功例は主記事・公式動画・確認した公式ブログ記事では見つからなかった。
- したがって、ToCの「動画公開例」としては未検証。画像投稿のUI状態遷移を動画向けUIへ一般化できる、という設計上の示唆に留める。

## 同じ販売元の新しい一次情報

- 公式YouTubeチャンネル: https://www.youtube.com/@anti-detect
  - English動画「Complete Instagram Automation with ChatGPT and Undetectable Browser | Guide」: https://www.youtube.com/watch?v=Gv5-Ltz63gE
  - 公開日を動画埋め込みメタデータで確認: **2026-06-22 13:05:57 -07:00**。確認時の再生数は183。
  - 自動字幕は、Undetectable Browser→Codex Desktop→MCP接続、まずテスト、最適化プロンプト、実行中のスクリーンショット、最後に「post has been published on the Instagram page」と述べる。記事内容の再演であり、第三者検証ではない。説明文も「right photo」を選ぶ例で、動画/Reelsではない。
  - 同じ動画のロシア語版: https://www.youtube.com/watch?v=ITrtma-4sGA（同日、確認時259再生）。字幕もInstagramの投稿公開を述べる。
  - チャンネルの新しい順一覧（確認時）は、このInstagram動画が最新の関連長尺動画で、後続のInstagram/Reels/TikTok公開実演は見当たらない。2026-06-02のShort「Demonstration of automation with ChatGPT」は記事より前で、Instagram投稿の証拠ではない。
- 2026-07-01の公式ブログ「Free AI automation」はLM Studio + MCPの後続記事: https://undetectable.io/blog/free-ai-automation/ 。Instagram投稿を「例」として言及するが、実際に掲載されたテスト画像はLM StudioからUndetectableプロファイルを作成した画面で、Instagram投稿成功の画像ではない。後続記事もReels/TikTokの実演ではない。
- 公式更新一覧の最新表示は 2026-09-15 の Undetectable 2.51.0（Chromium 153）: https://undetectable.io/blog/category/updates/ 。これはブラウザ更新であり、Instagram/TikTok動画公開の検証報告ではない。主記事の2026-06-16テスト環境と同一バージョンとは確認できない。

## 費用・現時点の差分

- 主記事の明示: Undetectable無料版でも可能、ただしOpenAIサブスクリプション必須。Node.jsとMCPパッケージも必要。
- 現行料金ページ（確認日）: https://undetectable.io/pricing/ 。Free（最大5 cloud profiles、1 user session、10 browser configurations等）、Base $34/月、Professional $69/月を表示する。料金ページの表ではFreeのLocal API欄が明確に埋まっていないため、記事の「無料版でMCP自動化可能」が現行プランにもそのまま適用されるとは断定しない。料金・機能は導入前に再確認が必要。
- 公式LM Studio記事はローカルモデルならAPIトークン費用をゼロにできると宣伝するが、LM Studio、モデル、ハードウェア、Undetectableのプラン条件は別途必要で、Instagram公開成功の証拠ではない。

## ToCに再利用できる安全な一般UIフロー

販売元のanti-detect固有手順をテンプレート化せず、通常の承認済みセッションで次の状態機械だけを再利用する。

1. 人間が対象アカウント、公開先、素材、キャプション、公開日時を確認する。
2. 承認済みのブラウザセッションで対象プラットフォームの作成画面を開く。
3. 素材を選択し、アップロード完了とプレビューを目視確認する。動画の場合はトリミング・カバー・音源・字幕など、サービス固有の項目を追加確認する。
4. キャプション、タグ、公開範囲、アクセシビリティ項目を入力し、対象アカウント名とプレビューを再確認する。
5. **公開ボタンの直前で停止し、人間が最終承認する。**
6. 公開後、成功トースト/遷移先/投稿ページを確認し、投稿URL、時刻、表示されたメディアを保存する。失敗時は再送せず、状態を人間に返す。

## 採用判断

販売元の主張としての「Codexで画像投稿を完了」は、記事画像と公式動画の2系統で整合する。一方、証拠はすべて販売元の自己申告・自己制作スクリーンショットで、独立検証なし。動画投稿、Reels、TikTok、継続運用、料金の現行適用も未検証である。ToCでは、画像投稿のUI状態と人間確認の設計例として参照し、まず小さな可逆テストを行う。anti-detect、アカウント多重化、検出回避を前提にした運用テンプレートとしては採用しない。
