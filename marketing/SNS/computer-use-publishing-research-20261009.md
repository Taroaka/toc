# Computer UseによるSNS投稿の実例とToCへの実装案

調査日：2026年10月9日

## 結論

公開された実装・運用手順は存在する。今回の要望に最も近いのはThe Posting ToolのComputer Use運用手順。ログイン済みブラウザで各サービスの予約投稿を登録し、予約一覧に実在することを確認する方式である。

本調査は公開資料・コード構成の確認まで。外部コードはインストール・実行しておらず、ToCのアカウントでの投稿成功は未検証。アカウント新規作成の自動化と投稿自動化は別で、確認した資料は既存ログイン済みアカウントを前提としている。

## 実例と根拠の強さ

| 実例 | 公開資料から確認できる範囲 | ToCへの使い方 |
|---|---|---|
| The Posting Tool | Computer Use用PLAYBOOKとPython補助実装。TikTok・Instagram・X・Threads等の予約手順、アカウント照合、予約一覧による確認を文書化。作者の対応表であり、全サービスの現在の動作保証ではない | 最も近い設計参考。クリック位置ではなく操作目的・完了条件を採用 |
| dreammis/social-auto-upload | 複数サービスのアップローダーとCLI・Skillを公開。TikTokはChrome版の例を案内し、対応表ではTikTokのCLI・Skillは未提供。DouyinはTikTokと別サービス | 入力形式とサービス別の分離を参考にする。丸ごと導入せず、必要部分を評価 |
| LouisLin0723/social-auto-publisher | PlaywrightとChrome MCPの2経路。作者はDouyin投稿成功・Reddit送信フロー確認を記載。一方TikTokはE2E未検証、Xも当該repoで未検証と明記 | UI障害・途中停止の参考。TikTok成功例として数えない。検知回避や制限回避の手法は採用しない |
| Mikefluff/skills post-publisher | ブラウザ操作手順と投稿結果の記録・content hashによる重複防止を文書化。単発・人間立ち会いのfallbackであり無人定期投稿の実証ではない | 投稿台帳、ファイル検査、結果不明時の再投稿防止を参考にする |

一次資料：
- https://github.com/okwithit9-debug/the-posting-tool
- https://github.com/okwithit9-debug/the-posting-tool/blob/main/docs/PLAYBOOK.md
- https://github.com/dreammis/social-auto-upload
- https://github.com/LouisLin0723/social-auto-publisher
- https://github.com/Mikefluff/skills/blob/main/skills/post-publisher/references/browser-fallback.md

## 公式機能との関係

TikTok公式のTools for creatorsは、Web版TikTok Studioへのアクセスと投稿のアップロード・予約・編集を案内している。機能はアプリ・Web・アカウント条件で異なる。第三者playbookのCreator/Business必須という一律の記述は、そのまま一般条件にしない。公式案内はPersonal/Business双方にcreator toolsがあると説明している。実装時は対象アカウントの実画面で予約機能を確認する。

- https://support.tiktok.com/en/using-tiktok/creating-videos/creator-tools-on-tiktok?lang=nl

Meta公式の予約投稿紹介も存在するが、今回、Instagram Reelsの最新の個別条件を本文まで確定できる公式ヘルプは取得できなかった。InstagramについてはMeta Business Suiteを実機確認の候補にし、必要なアカウント種別・連携・予約可能期間は実装時に確認する。

- Meta for Business公式動画：https://www.youtube.com/watch?v=PQjvbXyMhkM

公式Web画面に投稿機能があることは、第三者自動操作を無条件に許可する意味ではない。各サービスの現行ルール・利用権限と実画面に沿って実装する。認証・CAPTCHA・投稿制限は回避せず、必要な本人操作へ引き継ぐ。

## 既存のToCとの接続

確認したローカル資料：
- skills/youtube-studio-upload/SKILL.md
- marketing/browser-use.md
- marketing/SNS/README.md
- docs/root-pointer-guide.md

YouTube用スキルには、投稿用素材の入力、アカウント確認、Privateでの保存、保存結果確認、公開前の人間確認という構成が既にある。この設計を引き継ぎ、制作パイプラインとは分離したSNS運用スキルにする。

提案する構成（まだ未実装）：

    skills/social-video-publish/SKILL.md
    skills/social-video-publish/references/tiktok.md
    skills/social-video-publish/references/instagram.md
    marketing/SNS/accounts.json
    marketing/SNS/publishing/<run-id>/publish-plan.json
    marketing/SNS/publishing/<run-id>/receipts.jsonl

accountsには公開ハンドル・確認用URL・タイムゾーン等だけを記録し、パスワード・cookie・トークンを保存しない。実装時に既存のアカウント台帳があればそれを再利用する。

## 実行の流れ

1. 制作済み動画と投稿文を読み、対象サービスに合う長さ・縦横比・容量か確認する。適合しない場合は勝手に切らず、既存のvertical-shorts-creator等による別の制作工程へ戻す。
2. 投稿先、アカウント、動画、本文、表紙、必要なAI生成表示、公開範囲、日時を投稿計画にまとめる。
3. 人間が投稿計画を確認する。確認済み計画の範囲内は繰り返し承認を求めず進め、内容・アカウント・日時が変わった場合に確認し直す。
4. 環境が提供するComputer Useでログイン済みブラウザを操作する。現在の画面と公開されたAPIを確認し、外部Playwrightを無断で別経路として起動しない。
5. 動画添付、入力、プレビュー確認を行い、指定され承認済みの公開方法で投稿または予約する。予約機能がなければ勝手に即時公開へ変更しない。
6. 予約一覧または投稿一覧で、アカウント・対象動画・日時を照合する。処理待ちを完了と扱わない。
7. 予約IDや投稿URL、時刻、画面証拠を記録する。予約登録済みと公開確認済みを別状態にする。

重複防止の単位は「サービス＋アカウント＋動画ハッシュ＋投稿計画ID」。送信後に結果不明となった場合はunknownとして、一覧確認が済むまで再送信しない。失敗回数を制限し、失敗状態と次の本人操作を記録する。

## スキルと定期実行の分担

SKILL.mdは操作手順であり、それだけでは定期的に起動しない。まずComputer Useで承認済み動画をサービス側の予約機能へ登録する。これなら投稿時刻ごとのブラウザ操作を減らせる。

自動で次の動画も投入する段階では、別途起動スケジュール・投稿計画の承認状態・ブラウザの利用可能性・失敗通知を設計する。新規チャネル作成は初回設定として分離し、名前・プロフィール・アカウントの本人確認を行う。

## 最初の実装範囲の提案

最初はTikTok 1アカウント・動画1本で、本人が確認した計画から予約登録と結果確認を通す。成功後、Instagramを追加する。これは実装順の提案であり、投稿先はまだ本人未決定。

完了条件：
- 指定した本人のアカウントに、承認済みの動画と文面が保存・予約されている。
- 予約日時とタイムゾーンを確認できる。
- 同じ計画を再実行しても重複投稿しない。
- ログイン切れ・予約機能なし・アップロード失敗・投稿後結果不明の各場合で、誤公開や再送をしない。
- 初回の実機確認を記録するまで「本番動作確認済み」と表現しない。

今回の成果物は調査と実装設計案。スキル追加・チャネル新規作成・ログイン・投稿・予約は未実施。


## 追加確認 直近の実動とCodex利用の証拠

2026年10月9日、GitHub APIのmainコミット・PR・Issueと公開ドキュメントを再確認。更新日、導入対応、開発へのCodex使用、Codexでの実投稿成功は別の証拠として評価する。

| 候補 | mainの最新コミット日 | 直近の実動の根拠 | Codexについて確認できたこと |
|---|---|---|---|
| The Posting Tool | 2026-09-27、3df88e6621 | 9月30日更新のダッシュボードPRあり。ただし日付付きの本番投稿成功記録は確認できず | Computer Use・Codexを想定した記述はあるが、Codexで成功した公開ログは確認できず |
| dreammis/social-auto-upload | 2026-09-02、0012d2c355 | PR #293の10月6日コメントにWeChat Channelsの実投稿成功と所有者確認の報告。mainに未マージの#292・#293修正を適用した環境 | 公式docs/agent-bootstrap.mdにCodex向け手順。PR #290はcodex表記があるが、実ログイン・投稿未実施と明記。#293のブランチ名codex/だけでは実行エージェントの証明にならない |
| LouisLin0723/social-auto-publisher | 2026-06-04、737dc9f814 | READMEにDouyin成功の作者報告。TikTokはE2E未検証、Xも当該repoで未検証。10月の動作確認は発見できず | コミットにClaudeの共同著者表記。Codexでの動作確認は発見できず |

結論：直近の実投稿証拠とCodex向け導入整備を別々に持つのはsocial-auto-upload。ただし「Codex Computer UseでTikTok/Instagramの投稿が最近成功した」という両条件を満たす公開実績は、この3候補からは確認できなかった。The Posting Toolを最も近いとした前の結論は設計の近さであり、実動保証の順位ではない。

social-auto-uploadには10月2日のIssue #291で、小紅書の実投稿が誤った転載表示になった報告もある。投稿処理が通ることと、メタデータまで正しく投稿されることを分けて確認する必要がある。TikTokのCLI・Skill未提供とInstagramがREADME対応表にない点も、ToCの対象選びに重要。

出典：
- 最新コミット：https://github.com/okwithit9-debug/the-posting-tool/commit/3df88e66219e67bb6e01932093399dabd4f0e785
- ダッシュボードPR：https://github.com/okwithit9-debug/the-posting-tool/pull/1
- 最新コミット：https://github.com/dreammis/social-auto-upload/commit/0012d2c355f88f683cc38dde2a2db209e14091bc
- 実投稿報告と修正条件：https://github.com/dreammis/social-auto-upload/pull/293
- Codex表記の開発PR、実投稿未実施：https://github.com/dreammis/social-auto-upload/pull/290
- Codex向け公式導入文書：https://github.com/dreammis/social-auto-upload/blob/main/docs/agent-bootstrap.md
- メタデータ不具合報告：https://github.com/dreammis/social-auto-upload/issues/291
- 最新コミット：https://github.com/LouisLin0723/social-auto-publisher/commit/737dc9f814e67a4f98ab65cb314a19609b1d82aa

実投稿報告は第三者の自己報告であり、こちらで再現した結果ではない。ToCでは、候補を導入済み・動作確認済みと扱う前に、対象SNSと本人のアカウントで承認済み動画1本の予約・公開確認を行う。


## YouTubeと体験記事へ拡大した追加調査

2026年10月9日に本人が、TikTok・Instagramを優先し、GitHubに限らずYouTubeのマーケティング系動画・体験記事も採用判断の資料としてよいと指定。以下は紹介資料の候補で、製品や有料教材の購入・導入決定ではない。

| 資料 | 日付 | 確認できた範囲 | 未確認事項 |
|---|---|---|---|
| AI収益化ラボ「自動で働くCodexにInstagram投稿を100本作ってと指示した結果」 | 2026-07-27公開（YouTube検索結果のメタデータ） | 説明欄にChrome/MCP連携で投稿作業を自動化と記載。10:31が該当章。ブラウザで動画ページの存在とチャンネルを確認 | 字幕取得は不可。映像全体や投稿完了画面は未確認。漫画フィード投稿で、Reels動画の成功とは区別 |
| Undetectable公式「Full Instagram Automation with ChatGPT」 | 2026-06-16公開 | Codexの新規チャットでInstagram画像投稿を試し、公開に成功したと本文に実施者が明記。最適化後の再実行も報告 | 専用ブラウザ＋MCP。Codex標準Computer UseやReels動画の10月時点の成功ではない |
| MI Studio「InstagramとTikTokへの毎日の投稿を、手放す」 | 2026-09-05公開、ブラウザ表示の更新日2026-10-03 | 両SNS・本人のChrome・Claude Code/Codex向け教材と題名に明記。検索結果には9月の実行とTikTok管理一覧確認の説明がある | ブラウザとWeb取得で本文が表示されず、当該説明は検索結果由来。実行者がCodexかClaudeか、画像の内容、価格、配布コード、投稿成功は未確認。条件一致を断定せず要確認候補 |
| トレBotG「Codexを活用し、動画生成＋Insta投稿を自動化」 | 2026-05-19公開 | CodexでReels動画生成からInstagram MCPによる投稿まで試したという体験記事とプロンプトを確認 | 投稿MCPの製品名・実装方式・投稿URLが不明。Computer Use方式だと断定できない |

リンク：
- YouTube（10:31〜）：https://www.youtube.com/watch?v=IqZrWAVbLrY&t=631s
- Undetectable：https://undetectable.io/blog/instagram-ai-automation/
- MI Studio：https://brain-market.com/u/mistudio/a/b2UzM0YjMgoTZsNWa0JXY
- トレBotG：https://coconala.com/blogs/2954967/747982

参考：Claire Vo本人のサイトにも、CodexでTikTok Studioの投稿画面まで動画をアップロードし、公開はせずに止めた実践記録がある。投稿準備の証拠であり公開成功とは扱わない。https://clairevo.com/

結論の更新：CodexでInstagram投稿を実行した体験報告はある。「事例なし」と一般化しない。ただし今回の優先条件であるTikTok/Instagram動画、直近の実行、Codex Computer Useの3点を同時に裏付けた資料として採用確定できるものはまだ確認できていない。無料資料としてはYouTubeの該当章とUndetectableの体験記を参照候補とし、MI Studioの教材は本文・実演・使用エージェントを確認するまで購入推薦しない。収益化・大量投稿の宣伝を技術的な成功証拠にしない。


## サブエージェント4件の個別調査

10月9日、本人依頼で4件を分担調査。YouTubeのCodex実画面、Undetectable公式動画、MI Studioの購入境界、Claire Voの直接記事を追加確認。[統合結果](publishing-evidence-20261009/README.md)と各個別報告を参照。画像投稿の実行例と動画アップロード例はあるが、TikTok・Instagram Reels両方の直近のCodex公開成功例は未確認。採用は未確定。
