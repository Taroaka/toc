# /sns

SNSマーケティング作業の起点コマンド。

## 使い方

```
/sns research "TikTokトレンド調査"
/sns content "桃太郎動画のキャプション作成"
/sns analytics "2026年4月の月次レポート"
```

## フェーズ別の作業場所

| フェーズ | 作業フォルダ | 正本ドキュメント |
|---------|------------|----------------|
| research | `sns/research/` | `docs/sns/research.md` |
| content | `sns/content/` | `docs/sns/content.md` |
| analytics | `sns/analytics/` | `docs/sns/analytics.md` |

## 方針

- 各フォルダの `CLAUDE.md` を読んでから作業を開始する
- 投稿テキストや素材は `sns/<フェーズ>/<YYYYMMDD>-<topic>.md` に保存する
- SNS投稿は必ず人間が確認・承認してから行う（自動公開しない）

## 参照

- メインガイド: `docs/sns-guide.md`
- ToC動画生成との連携: `docs/video-generation.md`
