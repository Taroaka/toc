# 設計の参考と検証状態

確認日：2026-10-09。下記の概念を参考に独自に記述した。外部コード・実行スクリプトのコピーやインストールはしていない。

- ToC skills/youtube-studio-upload/SKILL.md：対象・入力・人間確認・保存後検証を区別したdescriptionと構成。
- https://github.com/dreammis/social-auto-upload ：サービス別アップローダー、投稿メタデータ。TikTokは例の実装で、DouyinをTikTokと混同しない。
- https://github.com/dreammis/social-auto-upload/blob/main/skills/douyin-upload/SKILL.md ：descriptionに作業と必要環境を記す設計。本スキルはsau CLI依存を採用しない。
- https://github.com/okwithit9-debug/the-posting-tool ：ログイン済みUI操作、指定日時の予約、管理一覧での結果確認。固定のCTAや即時投稿禁止は本スキルの一律ルールにはしない。
- https://github.com/LouisLin0723/social-auto-publisher ：操作準備と公開確認の分離。検知回避・sandbox回避の手法は採用しない。
- https://github.com/ShenTuZ/video-publisher-skill ：動画配信に限定したdescription、段階的読み込み、サービス別結果と再開。Ego Lite依存や即時公開の既定値は採用しない。

詳細な調査はToC marketing/SNS/computer-use-publishing-research-20261009.md と publishing-evidence-20261009/ を参照する。画像投稿例・アップロード止まりの例・動画公開例を区別する。

初期状態：TikTok / Instagram Reelsとも本人のアカウントでの実機検証は未実施。構造検証合格はライブ投稿成功を意味しない。
