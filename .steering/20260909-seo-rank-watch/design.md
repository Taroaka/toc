# 設計

- 共通スキル正本を `skills/seo-rank-watch/SKILL.md`、運用手順を `marketing/SEO/rank-watch.md` に置く。
- 既存のマーケティング router と README に入口を追加する。Claude Code は既存方式の symlink で共通スキルを読む。
- 指定された `fetch_gsc_ranks.mjs` は現状存在しない。提供済みの場合だけ使うコマンド例として保持し、GSC 連携ツールによる同等の取得を定義する。存在しないスクリプトを実行可能とは扱わない。
- GSC と WebSearch の測定元・期間を分離し、28日平均と7日平均を直接比較しない。データ不足時は判定を保留する。
