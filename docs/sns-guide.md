# SNS Marketing Guide

## North Star

- SNS 作業は spec-first。正本は `docs/sns/`, `sns/` に置く。
- 各フォルダの `CLAUDE.md` は参照ポインタ専用。長い説明はここ（`docs/sns-guide.md`）か各正本ドキュメントへ移す。
- 目的はSNSチャンネルの成長と視聴者エンゲージメントの向上。

## Entrypoints

- `/sns` — SNSマーケティング作業の起点コマンド
- 実行方法の正本: このファイル（`docs/sns-guide.md`）

## フォルダ構成

| フォルダ | 役割 | 正本ドキュメント |
|---------|------|----------------|
| `sns/research/` | プラットフォーム調査・トレンド収集 | `docs/sns/research.md` |
| `sns/content/` | コンテンツ企画・キャプション・ハッシュタグ | `docs/sns/content.md` |
| `sns/analytics/` | 投稿実績・インサイト分析 | `docs/sns/analytics.md` |

## 作業フロー

```
research（トレンド調査） → content（コンテンツ設計） → analytics（効果測定）
```

## Read Next

- 調査: `docs/sns/research.md`
- コンテンツ設計: `docs/sns/content.md`
- 分析: `docs/sns/analytics.md`

## Hard Rules

- 各フォルダの `CLAUDE.md` は短く保つ。詳細は正本ドキュメントへ。
- SNS投稿は承認フロー必須。自動公開しない。
- `CLAUDE.md` を更新したら次を通す。

```bash
python scripts/validate-pointer-docs.py
```
