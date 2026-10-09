# SNSアカウントと投稿スキル

更新日：2026年10月9日。本人がユーザー名を変更せず運用すると決定。

## Instagram と TikTok

作品配信用のアカウント。希望するチャンネル表示名は「英雄の旅」。YouTubeの既存名やToC製品広報の名称を自動で変更する決定ではない。

| サービス | ユーザー名 | プロフィールURL | 確認状態 |
|---|---|---|---|
| Instagram | `eiyu_no_tabi` | https://www.instagram.com/eiyu_no_tabi/ | 登録済み。本人のログイン画面でハンドルと表示名「英雄の旅」を確認 |
| TikTok | `eiyu_no_tabi` | https://www.tiktok.com/@eiyu_no_tabi | 登録済み。本人報告とプロフィール編集画面でハンドルを確認。表示名は画面上 `eiyu_no_tabi`。希望名「英雄の旅」への保存は未完了 |

`heros_journey` は両サービスの変更画面で使用不可。変更は保存せず、本人が現在の `eiyu_no_tabi` を維持すると決定した。`heros_journey_jp` は未採用。

## 使用するスキル

- **TikTok・Instagram Reels：`$toc-social-publish`**
- 正本：[SKILL.md](../../skills/toc-social-publish/SKILL.md)
- プロジェクト検出用：`.agents/skills/toc-social-publish`（正本へのリンク）
- 対象：完成動画のアップロード、投稿準備、公開、予約、結果確認・再開、明示的な初回アカウント設定。
- 呼び出し例：「`$toc-social-publish` で、この動画をInstagramとTikTokの `eiyu_no_tabi` 向けに投稿準備して」
- 動画制作だけ、投稿事例の調査だけ、目標登録だけは対象外。
- YouTubeのみの投稿は既存の `$youtube-studio-upload` を使う。

このアカウント表は投稿先の識別用。公開操作の許可を兼ねない。実行時はログイン中のハンドルと照合し、本人が動画・投稿文・公開範囲・日時を確認した計画に従う。

## 現在の進捗

- アカウント登録：両方完了。
- スキル作成：完了。形式・参照・登録リンクは検証済み。
- TikTok表示名、両サービスのアイコン・自己紹介等の最終設定：未完了または未確認。
- 動画の投稿・予約、自動投稿の実機検証：未実施。

パスワード、認証コード、Cookie、ログイン用メールアドレス等はこの公開プロフィール台帳に保存しない。
