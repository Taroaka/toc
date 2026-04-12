# Kindle for Web + browser computer use plan

## Goal

`Kindle for Web` をブラウザで開き、`computer use` でページ送りしながら本を読む。

> Status: alternative / deprecated path
>
> このメモは `agent-browser` ベースの旧案。現行の正本は `Codex + Playwright MCP` を前提にした [codex-browser-use-plan.md](/Users/kantaro/Downloads/toc/kindle/codex-browser-use-plan.md)。

主用途は次の 3 つ。

- 章ごとの要約
- 調査用ノート作成
- 必要箇所の引用メモ整理

`全文 TXT 化` は副次用途として扱う。OCR や DOM 取得だけで本文を壊さず連結するのは不安定だから。

## Why this plan

- `Kindle for Web` ならアプリ制御なしで始められる
- `agent-browser` は AI 向けの `snapshot -> ref -> click` 操作ができる
- 人間が最初にログインし、その後のページ送りや目次移動だけ自動化すれば、最小構成で試せる

## Recommended architecture

1. Browser session bootstrap
   - `agent-browser` で `https://read.amazon.com` を開く
   - 人間がログインを完了する

2. Reading loop
   - スナップショットを取得
   - `Next page` ボタン、あるいは右側クリック/矢印キーで次ページへ進む
   - 表示領域のテキストを取得できるなら取得する
   - 取れない場合はスクリーンショットを保存し、OCR または vision 要約に回す

3. Output layer
   - `kindle/runs/<timestamp>/pages/` にページ単位の証跡
   - `kindle/runs/<timestamp>/notes.md` に章要約
   - `kindle/runs/<timestamp>/quotes.md` に必要箇所の引用メモ

## Preferred operating mode

おすすめは `reader agent` モード。

- 全ページをそのまま連結して `.txt` にするより
- 数ページごとに内容を要約し
- 章単位でノート化し
- 必要な箇所だけ抜粋する

このほうが UI 変化にも強い。

## First prototype scope

最初のプロトタイプはここまでで十分。

- `agent-browser` で `read.amazon.com` を開ける
- 人間ログイン後にスナップショットを取れる
- 右ページ送りを 1 回実行できる
- スクリーンショットを保存できる

この段階では、ログイン自動化や長時間連続走行はやらない。

## Failure modes

- Kindle UI の DOM が安定せず、`get text` が取りにくい
- ページ送りボタンの ref が毎回変わる
- 見開き、脚注、画像ページで OCR が崩れる
- セッション切れや bot 判定で止まる

対策:

- DOM 取得に固執せず `screenshot + vision summary` に落とす
- 1 冊フル自動ではなく、章単位で区切る
- ログインは人間、読書ループのみ自動化する

## Suggested commands

インストール:

```bash
npm install -g agent-browser
agent-browser install
```

起動:

```bash
./kindle/start-kindle-web-session.sh
```

手動で試す場合:

```bash
agent-browser open https://read.amazon.com
agent-browser snapshot -i
agent-browser screenshot kindle-home.png
```

## Practical next step

次にやるべきは、`read.amazon.com` にログインした状態で

- どの UI 要素でページ送りできるか
- `agent-browser get text` がどこまで効くか
- 画像ベースのページで何が落ちるか

を 1 冊ではなく 1 章でテストすること。
