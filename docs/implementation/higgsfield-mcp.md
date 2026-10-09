# Higgsfield MCP 接続準備（任意・初期状態は無効）

確認日: 2026-10-05。目的は ToC のエージェントから公式 MCP を後で追加できるようにすること。
この変更では OAuth、CLI/skill のインストール、有料生成、永続アクセス追加を行わない。

## 接続仕様と確認の限界

| 項目 | 確認結果 |
| --- | --- |
| 公式性 | [Higgsfield MCP](https://higgsfield.ai/mcp) が公開するサービス。第三者 wrapper は使わない |
| URL | `https://mcp.higgsfield.ai/mcp` |
| 接続設定 | Codex の remote URL / Streamable HTTP 設定を使用。認証後の initialize / transport negotiation は未検証 |
| 認証 | OAuth Bearer、HTTP Authorization header。REST の key ID / secret 認証とは別 |
| 認証メタデータ | [Protected resource metadata](https://mcp.higgsfield.ai/.well-known/oauth-protected-resource/mcp) |
| advertised scopes | `openid email offline_access` |
| advertised authorization servers | `https://clerk.higgsfield.ai`（authorization code + PKCE）、`https://fnf-device-auth.higgsfield.ai`（device code）。クライアント能力に応じて選択される |
| 公開応答 | 資格情報なし GET は HTTP 401 と Bearer challenge を返すことを確認。これは接続成功ではない |

公式ページは画像・動画生成、参照画像、各種プリセットを案内する。ただし、公開マーケティング上の
ワークフロー名を MCP tool 名として扱わない。OAuth を行っていないため `tools/list`、入力 schema、
利用可能モデル、生成・取得・キャンセル操作の実際の対応範囲は未確認。ツール名やモデル ID を
ToC に予約登録しない。

公式サイトの **Other → Codex (CLI)** は現在、公式 CLI と companion skills を案内する。
[公式 skills リポジトリ](https://github.com/higgsfield-ai/skills) の Codex plugin も CLI ベース。
これは remote MCP 設定とは異なる導入経路であり、この準備では導入しない。

## 設定例とユーザー側の手順

[Codex 設定例](../examples/higgsfield.codex.toml) は自動読込されない場所にあり、
`enabled = false`。API キーもトークンも含めない。OAuth 接続に架空の API-key header を追加しない。

1. [公式接続案内](https://higgsfield.ai/mcp) と下記の料金・契約を再確認する。
2. ユーザー設定・project 設定・既存 plugin に同じ endpoint が登録済みか確認する。
   既存登録があればそれを使い、`higgsfield` を重複定義しない。
3. 接続を開始すると決めた時点で、例のセクションだけを ToC の `.codex/config.toml` に統合する。
   ファイル全体を上書きしない。`enabled = false` のまま内容を確認できる。
4. ユーザーが接続を許可した後に限り `enabled = true` とし、信頼済み ToC ディレクトリから
   `codex mcp login higgsfield` を実行して、本人がブラウザ認証を完了する。
   例を置いただけではログインもツール利用もできない。Codex 側の OAuth 互換性はここで確認する。
5. 初回は initialize と `tools/list` だけを確認し、生成をしない。必要なツールと schema を記録し、
   費用・出力先・利用モデルを合意してから有料呼び出しを許可する。
6. 無効化は `enabled = false`。接続の撤回は `codex mcp logout higgsfield` と
   Higgsfield アカウント側の連携解除を確認する。設定削除だけを token revoke と見なさない。

認証情報はクライアントの credential store で管理し、repo、`.env.example`、ログ、成果物に貼らない。
公式 REST API を別途実装する場合に限り、`HF_API_KEY_ID` / `HF_API_KEY_SECRET` を環境変数として
管理する（この例に設定しない）。

## 料金・契約

[API Billing and retention](https://docs.higgsfield.ai/docs/concepts/billing-and-retention) は、成功した
生成をモデル・パラメータ別のクレジットで課金し、認証済み estimate の結果を金額の正本とする。
failed / nsfw と処理開始前のキャンセルは返金対象、出力保持は少なくとも7日、クレジット期限は
追加から1年と案内する。[API pricing](https://open.higgsfield.ai/pricing) も再確認する。
これらは **REST API 文書の条件**。MCP に同一単価や同一残高が適用されるか、Web の Unlimited
枠を使えるか、必要プランは、今回の未ログイン調査では確定できない。MCP 利用開始前にアカウント
画面または公式サポートで確認し、Web 定額プランだけで無料生成できると仮定しない。

[利用規約](https://higgsfield.ai/terms-of-use-agreement)（2026-07-26 更新）の §1.5、§11 は
API/MCP の制限と developer access、§11.12–13 はエージェント経由の操作・費用と第三者
クライアントの責任を扱う。§4.4 の入力・出力の利用条件、§9–10 の課金・契約更新条件も
利用前に本人が確認する。この準備は規約同意や契約締結を代行しない。

## ToC の provider 境界

この MCP はエージェントの任意ツール。既存の `toc/providers/`、
`toc/video_provider_capabilities.py`、manifest の selector、モデル default は変更しない。
現在の `scripts/generate-assets-from-manifest.py` は外部画像 provider を無効化し、
画像を `codex_builtin_image` に正規化する。MCP 登録だけで ToC の自動生成が
Higgsfield に切り替わることはない。同名の Kling / Seedance でも既存 provider の認証・契約を
Higgsfield に流用しない。

将来自動化する場合は別タスクで provider adapter と schema を設計し、
[video integration](video-integration.md) と [image prompting](image-prompting.md) の
request snapshot、prompt/reference hash、request/response identity、出力検証・provenance に
接続する。生成済みファイルを無検証で既存の成功状態に置き換えない。

## 今回の検証

- TOML 構文と Codex の設定デシリアライズをオフラインで確認（無効状態・URL・transport）。
- pointer docs 検証と差分の空白検査。実行コードの変更はないため生成回帰テストは対象外。
- 公開 endpoint の未認証 401 と OAuth metadata を確認。cookie/token は証跡に保存しない。
- 認証後の接続・ツール列挙・課金・生成は未検証。これらを完了済みと報告しない。

REST API の認証仕様: [Authentication](https://docs.higgsfield.ai/docs/authentication)。
REST の endpoint / 非同期 request lifecycle は [API Docs](https://docs.higgsfield.ai/docs) を参照。
