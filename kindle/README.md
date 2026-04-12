# Kindle text extraction notes

このフォルダでは、`DRM-free` の電子書籍や自分で権利を持つ原稿を、ローカルで `.txt` に変換する。

## 結論

- 通常の Kindle 購入本を `全文 TXT` に書き出す Amazon 公式機能は見つからなかった。
- Amazon の一次情報で確認できたのは、`ノート/ハイライトの参照` と、`DRM-free 本に限る EPUB/PDF ダウンロード`。
- そのため、個人利用でも安全に回せる実務フローは `DRM-free の本 -> Calibre -> TXT`。
- もう一つの実験経路として、`Kindle for Web + browser computer use` は成立する。
- ただし後者は `全文 TXT をきれいに吐く変換器` というより、`画面を順に読んで要約・ノート化する reader agent` として設計した方が安定する。
- 現行の正規ルートは `./kindle/run-kindle-full-book.sh`。手動ログインと手動で本を開くところまでは人間が行い、その後は `Chrome remote debugging + CDP page-image export + per-page Codex vision transcription` でフルブックの export/transcribe/checkpoint を 1 コマンドで回す。`open-kindle-web-browser.sh` などの他スクリプトは setup/debug helper として扱う。

上の「通常の Kindle 購入本を全文 TXT に書き出す公式機能は見つからなかった」は、Amazon のヘルプと KDP の公開情報を確認した上での推定。

## 使えるケース

- 自分で書いた原稿
- パブリックドメイン本
- 出版元が DRM-free で配布している EPUB/PDF
- 2026-01-20 以降に Amazon 側で DRM-free として配布され、購入者向けに EPUB/PDF ダウンロードが有効な本

## 使えない/避けるケース

- DRM がかかった Kindle 購入本の本文抽出
- 保護を回避して本文を抜き出す方法

## ローカル変換フロー

1. Calibre を入れる

```bash
brew install --cask calibre
```

2. DRM-free の入力ファイルを用意する

- 例: `book.epub`, `book.pdf`

3. このスクリプトで TXT に変換する

```bash
./kindle/export-drm-free-book.sh "/path/to/book.epub"
```

出力先を指定したい場合:

```bash
./kindle/export-drm-free-book.sh "/path/to/book.epub" "/Users/kantaro/Downloads/toc/kindle/output/book.txt"
```

デフォルトでは `kindle/output/<入力ファイル名>.txt` に書き出す。

## Full-book export フロー

`Kindle for Web` の正規ルートはこれ。実行コマンドとして案内するのは `./kindle/run-kindle-full-book.sh` だけ。

- main entrypoint: [run-kindle-full-book.sh](/Users/kantaro/Downloads/toc/kindle/run-kindle-full-book.sh)
- Codex 用メモ: [codex-browser-use-plan.md](/Users/kantaro/Downloads/toc/kindle/codex-browser-use-plan.md)
- output contract: [full-book-output-contract.md](/Users/kantaro/Downloads/toc/kindle/full-book-output-contract.md)
- validation matrix: [full-book-validation.md](/Users/kantaro/Downloads/toc/kindle/full-book-validation.md)
- setup/debug helpers: [open-kindle-web-browser.sh](/Users/kantaro/Downloads/toc/kindle/open-kindle-web-browser.sh), [start-kindle-web-session.sh](/Users/kantaro/Downloads/toc/kindle/start-kindle-web-session.sh), [extract-kindle-web-cdp.py](/Users/kantaro/Downloads/toc/kindle/extract-kindle-web-cdp.py), [transcribe-kindle-pages-with-codex.sh](/Users/kantaro/Downloads/toc/kindle/transcribe-kindle-pages-with-codex.sh)
- 旧代替案: [browser-computer-use-plan.md](/Users/kantaro/Downloads/toc/kindle/browser-computer-use-plan.md)

OpenAI の公式 docs ベースでは、`ChatGPT サブスクで Codex を使う` 場合の本命は `Codex app` / `Codex CLI` + ローカル Chrome remote debugging だが、Kindle 側の実行はこの 1 コマンドに集約されている。

- 実行前に `Chrome remote debugging` 付きのブラウザが起動済みであること
- 実行前に Kindle for Web へ手動ログイン済みであること
- 実行前に対象の本が `active Kindle reader tab` で開かれていること
- Kindle reader tab は 1 つだけにすること。複数タブがあると attach 先が曖昧になる
- `run-kindle-full-book.sh` を実行する
- 必要なら `--resume` で `run_state.json` から再開する
- 出力は `kindle/runs/<timestamp>/` にまとまる
- 生成物は `pages/`, `vision/`, `transcript.txt`, `session.md`, `run_state.json`, `manifest.json`, `review_queue.md`
- 5 ページ固定ではなく、reader が終端に達するまで進める

`chatgpt.com/codex` は Codex cloud の入口ではあるが、docs 上は主に `repo を cloud container で処理する coding agent` として説明されている。そのため、Kindle のような GUI サイト操作は `Codex app / CLI + local Chrome CDP` を優先する。

### v2 の固定仕様

- ログインは手動
- 対象の本を開く操作も手動
- 実行前に対象の本が `active Kindle reader tab` で開いている必要がある
- Kindle reader tab を複数開いた状態では attach が曖昧になり得る
- 本文取得は `CDP page-image export + per-page Codex vision transcription` を正本にする
- `run-kindle-full-book.sh` が export/transcribe/checkpoint をまとめて実行する
- OCR は補助または fallback としてのみ使う
- 出力は `kindle/runs/<timestamp>/` に置く
- 生成物は `transcript.txt`, `session.md`, `run_state.json`, `manifest.json`, `review_queue.md`, `pages/0001.png` 〜 `pages/<n>.png`, `vision/<n>.txt`

### 実行コマンド

公式の実行コマンドはこれだけ。

```bash
./kindle/run-kindle-full-book.sh
```

再開したい場合だけ `--resume` を付ける。

```bash
./kindle/run-kindle-full-book.sh --resume --run-dir ./kindle/runs/<timestamp>
```

### Setup/debug helpers

- 個別にブラウザ起動したい時だけ `open-kindle-web-browser.sh` を使う
- run ディレクトリを手で作ってデバッグしたい時だけ `start-kindle-web-session.sh` を使う
- 個別 export / 個別 transcription を調べたい時だけ `extract-kindle-web-cdp.py` と `transcribe-kindle-pages-with-codex.sh` を使う

このフローでは、ユーザーが Kindle for Web に手動ログインし、対象の本を `active Kindle reader tab` で手動オープンしたあとに `run-kindle-full-book.sh` を 1 回実行する。Script は `run_state.json` に checkpoint を書き、`manifest.json` と `review_queue.md` を含む run ディレクトリ成果物を更新しながら進み、途中停止時は同じ run ディレクトリに対して `--resume` で続行できる。

## 公式情報メモ

- Amazon は `Send to Kindle` / USB 経由で `PDF, DOC, DOCX, TXT, RTF, HTM, HTML, PNG, GIF, JPG, JPEG, BMP, EPUB` を Kindle に送れるとしている。
- Kindle for Web / Kindle 端末では Notebook からノート・ハイライトを確認できる。
- Amazon KDP の公開ヘルプでは、`2026-01-20` 以降、`DRM-free` と確認された本は購入者が `Manage Your Content and Devices` から `EPUB/PDF` をダウンロードできるとしている。

## 参考

- Amazon: Connect, Browse, and Transfer Files on E-Reader
  - https://digprjsurvey.amazon.co.uk/csad/help/node/TCUBEdEkbIhK07ysFu
- Amazon: View Your Notebook in Kindle for Web
  - https://digprjsurvey.amazon.co.uk/csad/help/node/TS3oZMNGd9T0s62hVd
- Amazon KDP: Digital Rights Management
  - https://kdp.amazon.com/en_US/help/topic/GDDXGH9VR22ACM8U
- Calibre CLI
  - https://manual.calibre-ebook.com/generated/en/cli-index.html
- Calibre `ebook-convert`
  - https://manual.calibre-ebook.com/generated/en/ebook-convert.html
