# Codex subscription + browser use plan

## Decision

`API は使わない` 前提なら、OpenAI 公式 docs に沿った現実的な構成はこれ。

- `Codex app` または `Codex CLI`
- `ChatGPT account` でログイン
- ローカル `Chrome remote debugging` を有効にしたブラウザ
- `Kindle for Web` をブラウザで開いて操作する
- 本文取得は `CDP direct page-image export + per-page Codex vision transcription` を使う
- 正規の実行入口は `./kindle/run-kindle-full-book.sh` だけ

## Why this route

OpenAI の docs で確認できること:

- `Every ChatGPT plan includes Codex`
- Codex は `ChatGPT account` でもサインインできる
- `MCP` で Codex に `browser` や `Figma` のような外部ツールをつなげられる
- useful MCP servers の例として `Playwright` と `Chrome Developer Tools` が明示されている

一方で `Codex web` は、docs 上では `cloud environment` でコードを読んで編集し、terminal commands を回す仕組みとして説明されている。  
このため、`Kindle for Web を GUI でページ送りする` 用途では `Codex web 単体` より `Codex app / CLI + browser MCP` が自然。

実地で分かったこととして、`Playwright MCP` の `browser_take_screenshot` は Kindle の画像レンダリングページで 120 秒タイムアウトに落ちることがある。  
そのため、現行の正規ルートは `ブラウザ起動と手動ログインは通常ブラウザ`、`本文回収は Chrome DevTools Protocol で blob 画像を直接抜き、その画像を Codex vision で読む` 方式を、`run-kindle-full-book.sh` にまとめたもの。`open-kindle-web-browser.sh` などは helper 扱いにする。

## Recommended setup

### Option A

`Codex app / CLI + local CDP helper`

- 本文キャプチャを `Playwright screenshot` に依存しない
- Kindle の `blob:` 画像を直接 PNG にできる
- `Codex` は待機と実行管理だけ担当できる
- フルブック実行と checkpoint は `run-kindle-full-book.sh` に集約される

### Option B

`Codex app / CLI + Playwright MCP`

- ブラウザ操作の補助には使える
- ただし本文キャプチャの正本にはしない

この repo では `CLI + CDP helper` を正本として扱い、`Playwright MCP` は補助か旧経路とする。実行時の正規入口は `run-kindle-full-book.sh`。

## Operator contract

- 実行前に `Chrome remote debugging` 付きブラウザが起動済みであること
- 実行前に Kindle for Web へ手動ログイン済みであること
- 実行前に対象の本が `active Kindle reader tab` で開かれていること
- Kindle reader tab は 1 つだけにすること。複数タブがあると attach 先が曖昧になる
- 公式の実行コマンドは次の 1 つだけ

```bash
./kindle/run-kindle-full-book.sh
```

再開する場合だけ `--resume` と同じ `--run-dir` を使う。

```bash
./kindle/run-kindle-full-book.sh --resume --run-dir ./kindle/runs/<timestamp>
```

このコマンドは `run_state.json` を書き、`manifest.json` と `review_queue.md` を含む `pages/`, `vision/`, `transcript.txt`, `session.md` を run ディレクトリに残す。途中停止したら同じ run ディレクトリに対して `--resume` で続ける。

## Helper scripts

`open-kindle-web-browser.sh`、`start-kindle-web-session.sh`、`extract-kindle-web-cdp.py`、`transcribe-kindle-pages-with-codex.sh` は、今は setup/debug 用の補助スクリプトとして残す。単体検証や障害切り分けでだけ使う。

## Goal for v2

- Kindle for Web を手動ログイン後に開ける
- 対象の本を `active Kindle reader tab` に手動で開いた状態から始める
- 1 コマンドで full-book export/transcribe/checkpoint を実行できる
- `run_state.json` から再開できる
- `pages/` と `vision/` にページ単位の成果物を残せる
- `transcript.txt`, `session.md`, `manifest.json`, `review_queue.md` を run ディレクトリに残せる

## Not the goal yet

- 手動ログインの自動化
- 手動で本を開く操作の自動化
- 複数 Kindle reader tab を自動で見分けること
- CAPTCHA 回避
- DRM 回避
- 長時間セッションの無停止運用

## Evidence from official docs

- Codex quickstart
  - `Every ChatGPT plan includes Codex`
  - `sign in with your ChatGPT account`
- Codex MCP
  - `Use it to give Codex access ... to let it interact with developer tools like your browser`
  - useful MCP server examples include `Playwright` and `Chrome Developer Tools`
- Codex web
  - cloud environment で background task を実行する説明が中心

## Practical conclusion

`サブスクだけで browser-use したい` なら、

- `Codex web` を単独で使う前提ではなく
- `Codex app / CLI` を `ChatGPT login` で使い
- 必要なら `browser MCP` を補助でつなぎつつ
- 本文回収と checkpoint は `Chrome CDP + local helper script` ではなく `run-kindle-full-book.sh` に寄せる

この形で進めるのが、実運用上は最も安定している。
