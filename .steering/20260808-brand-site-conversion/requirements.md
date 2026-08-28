# ToC brand site conversion requirements

更新日: 2026-08-09

## Goal

スレッド2として、共通サイトの `あなたの想いを、映像に。` を、訪問者が説明を読む前に理解できる最上部の体験へ具体化する。直後に `一枚の画像から、一本の動画まで。` を置き、最初の販売対象である副業向け動画の実在する依頼内容と完成物を示し、一行入力フォームまで意味を切らさない。

## Confirmed inputs

- Purpose: `人の心を動かし、人生を豊かにする。`
- customer-facing brand line: `あなたの想いを、映像に。`
- common home は brand line を H1 にする
- 3秒の制作範囲は `一枚の画像から、一本の動画まで。`
- 主な顧客層は副業に取り組む個人と小規模ビジネス運営者
- 最初の販売対象は `副業に取り組む個人 × 動画制作`
- 個人ブランドは小規模ビジネスの利用例
- persona-specific LP は persona 固有 H1 / CTA を維持する
- `0 秒` は内部設計概念であり、外部向けの脳科学的主張にしない
- common CTA、qualification / disqualification、offer facts は Workstream 1 の shared decision であり、Workstream 2 は独自に確定しない

## Success criteria

1. 最上部が `0秒: ブランドの言葉`, `3秒: 画像から動画までの制作範囲`, `10秒: 実例の対応 / 実現方法 / 次の行動` の優先順を持つ
2. Hero は一つの `Direct Proof Pair` に限定され、装飾的な AI glow、句点 interaction、工程カード列へ依存しない
3. Hero proof は副業向けの同じ事例の actual initial brief と accepted completed video を使う
4. 副業向け動画の実例が無い場合、架空の完成物を本番の根拠とせず最上部の公開を止める
5. desktop / mobile / reduced motion / no autoplay / low-bandwidth fallback を定義する
6. 共通サイトと顧客層別ページの入力順を分け、入力した案、顧客層、制作形式を保持する
7. CTA の変更案は Workstream 1 へ handoff し、承認前に canonical CTA を上書きしない
8. implementation が検証できる acceptance checklist を残す

## In scope

- `marketing/LP/README.md`
- `marketing/LP/lp-strategy.md`
- `marketing/LP/toc-marketing-site.md`
- `marketing/LP/lead-form-schema.md`
- `marketing/LP/workstream-handoffs.md`
- 本 steering directory

## Out of scope

- `marketing/README.md` / `marketing/go-to-market.md` の変更
- `marketing/SNS/` の変更
- public site のコード実装
- `server/web/` の変更
- new proof video の制作
- common CTA、価格、offer、qualification の最終決定
- production quality gate の変更
