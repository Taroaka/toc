# Remote Work

スマホから ToC の Codex / Claude Code セッションを監視、指示、軽微編集できる状態を作るための実行 TODO。

## Claude Code Remote Control（ネイティブ機能）

Claude Code v2.1.51 以降に組み込まれた公式リモート接続機能。
ポート開放不要・外部ツール不要で、`claude.ai/code` またはスマホの Claude アプリから直接接続できる。

### 前提

- `claude auth login` 済み（claude.ai アカウント認証が必要。API キー不可）
- Claude Pro / Max / Team / Enterprise サブスクリプション

### 起動方法

**サーバーモード**（ローカル対話なし・バックグラウンド向き）:

```bash
scripts/ai/claude-remote-control.sh
# または直接:
claude remote-control --name "ToC"
```

**Interactive + リモート同時モード**（ローカルでも操作しながらスマホからも繋ぐ）:

```bash
scripts/ai/claude-remote-control.sh --interactive
# または直接:
claude --rc "ToC"
```

**既存セッション内からオンにする**:

```
/remote-control
```

### 接続方法

1. ブラウザ: `claude.ai/code` を開き、セッション一覧から「ToC」を選ぶ
2. スマホ: Claude モバイルアプリ → Sessions → 「ToC」

### 特徴

- ポート開放・トンネル不要（アウトバウンド HTTPS のみ）
- ファイルシステム・MCP サーバー・ツールはすべてローカルのまま
- 複数デバイスから同時接続、リアルタイム同期
- ネットワーク切断後の自動再接続

### CommandMate との役割分担

| 機能 | Claude Code Remote Control | CommandMate |
|------|---------------------------|-------------|
| Claude Code セッション操作 | ◎ ネイティブ | △ 間接的 |
| Codex セッション操作 | ✗ | ◎ |
| ファイル編集（Markdown 等）| △ | ◎ |
| セットアップコスト | 低（認証のみ） | 中（初期設定あり） |
| トンネル設定 | 不要 | Pinggy が必要（外出先） |

## Current Status

- `commandmate` 導入済み
- `~/.commandmate/.env` 作成済み
- `scripts/ai/commandmate.sh` から安定起動できる
- main server は `3101` で起動確認済み
- ToC worktree は `toc-main` として認識済み
- LAN IP は `192.168.11.14`
- `~/.commandmate/certs/localhost+2.pem` を生成済み
- HTTPS 信頼化は `sudo` が必要なので未完了
- `scripts/ai/commandmate-start-pinggy.sh` で外出先用トンネルを起動できる

## Goal

- PC で走らせた Codex セッションをスマホのブラウザから確認できる
- 必要に応じて追加プロンプトを送れる
- Markdown ベースの指示メモをスマホから修正できる
- ToC の通常運用を壊さず、外出先でも最小限の介入ができる

## Scope

- 対象は `CommandMate + Codex CLI + ToC workspace`
- まずは監視と追加指示を優先する
- 本格的なコード編集や大きいレビューは PC に戻す前提で考える

## Prerequisites

- [x] `tmux` が入っている
- [x] `git` が入っている
- [ ] `node -v` が `v20` 以上
- [x] `codex` が PC 側で通常利用できる
- [x] ToC の作業ディレクトリが固定されている
- [x] `scripts/ai/session-bootstrap.sh` を普段の開始ルーチンとして使える
- [x] `commandmate` を導入済み

現状メモ:

- この環境のデフォルト `node` は `v18.20.7`
- Homebrew 側には `v24.4.1` が入っている
- `commandmate` は Homebrew 側で導入済み
- ToC では `scripts/ai/commandmate.sh` 経由で起動する
- 起動補助は `scripts/ai/commandmate-start-lan-http.sh`
- HTTPS 起動補助は `scripts/ai/commandmate-start-lan-https.sh`
- 接続情報確認は `scripts/ai/commandmate-info.sh`
- 外出先用は `scripts/ai/commandmate-start-pinggy.sh`
- 外出先用情報確認は `scripts/ai/commandmate-pinggy-info.sh`
- 外出先用停止は `scripts/ai/commandmate-stop-pinggy.sh`

確認コマンド:

```bash
tmux -V
git --version
node -v
codex --version
scripts/ai/commandmate.sh --version
scripts/ai/commandmate-info.sh
```

## Phase 1: PC 側の基盤準備

- [x] `commandmate` を導入する
- [x] `commandmate init` を実行する
- [x] `CM_ROOT_DIR` を ToC root に合わせる
- [x] `CM_PORT` は `3101` に寄せる
- [x] `CM_DB_PATH` はデフォルト運用で始める

実施済み:

- `commandmate` インストール済み
- `~/.commandmate/.env` 初期化済み
- `CM_ROOT_DIR=/Users/kantaro/Downloads/toc`
- `CM_PORT=3101`
- `CM_BIND=0.0.0.0`
- `CM_DB_PATH=/Users/kantaro/.commandmate/data/cm.db`
- `LAN_IP=192.168.11.14`

コマンド:

```bash
scripts/ai/commandmate.sh init
```

`CM_ROOT_DIR` の候補:

```bash
/Users/kantaro/Downloads
```

ToC 単体で閉じるなら次でもよい:

```bash
/Users/kantaro/Downloads/toc
```

ToC を先に動かす段階では、この値をそのまま使う:

```bash
/Users/kantaro/Downloads/toc
```

## Phase 2: ToC ワークスペース登録

- [x] `commandmate start` で UI を開く
- [x] ToC リポジトリを認識させる
- [ ] 必要なら worktree 用の親ディレクトリも同じ root 配下に置く
- [ ] スマホで見たい Markdown を決める

登録候補:

- [ ] `/Users/kantaro/Downloads/toc`
- [ ] 将来の worktree 置き場

スマホから編集対象にしやすい Markdown 候補:

- [ ] `remote_work.md`
- [ ] `movie_todo.md`
- [ ] run ごとの `video_manifest.md`

## Phase 3: 安全な公開方法を決める

### 同一 Wi-Fi だけで使う場合

- [x] まずは LAN 内だけで試す
- [x] 認証付きで起動する
- [ ] 可能なら HTTPS 化する

起動候補:

```bash
scripts/ai/commandmate-start-lan-http.sh
```

同一 Wi-Fi でも HTTPS 化する場合:

```bash
brew install mkcert
CAROOT="$HOME/.commandmate/mkcert" mkcert localhost 127.0.0.1 192.168.11.14
scripts/ai/commandmate-start-lan-https.sh
```

補足:

- 証明書生成は完了済み
- macOS trust store への登録は `sudo` が必要なので未完了
- `scripts/ai/commandmate-start-lan-https.sh` で HTTPS 起動自体は確認済み
- ただしこの版の `commandmate ls` など CLI API 呼び出しは HTTPS 常駐時に扱いづらいため、普段の常駐は HTTP に戻している

### 外出先から使う場合

- [x] 認証なし公開はしない
- [x] `commandmate start --auth --daemon` で起動する
- [x] トークンを安全な場所に保管する
- [x] HTTPS トンネルを張る

起動:

```bash
scripts/ai/commandmate-start-pinggy.sh
```

トンネル候補:

```bash
scripts/ai/commandmate-pinggy-info.sh
```

または:

```bash
scripts/ai/commandmate-stop-pinggy.sh
```

補足:

- Pinggy free tunnel は未認証だと 60 分制限
- `~/.commandmate/pinggy-urls.txt` に公開 URL を保存する
- トンネル側は HTTPS なので、外出先では Pinggy の `https://...` URL を使う
- automation から叩く場合は相対 path ではなく絶対 path を使う

## Phase 4: スマホ接続

- [ ] PC 側でログイン URL とトークンを入力して QR を出す
- [ ] スマホで QR を読む
- [x] ToC ワークスペースを開けることを確認する
- [ ] セッション一覧、ファイル一覧、履歴が見えることを確認する

最低限の動作確認:

- [ ] ファイル一覧が見える
- [ ] `remote_work.md` を開ける
- [x] 既存 Codex セッションを監視できる
- [x] 追加プロンプトを 1 件送れる

今回の実績:

- 同一 Wi-Fi 上のスマホから `http://192.168.11.14:3101/login` で接続できた
- 認証トークン入力でログインできた
- `toc-main` の Codex セッションを開けた
- 新規セッションへプロンプト送信が通った

## Phase 5: ToC 向け運用ルーチン

### PC で開始するとき

- [ ] ToC root で開始する
- [ ] 必要なら bootstrap を走らせる
- [ ] 長作業は worktree を切って隔離する
- [ ] スマホから確認しやすいように、作業指示を Markdown に残してから走らせる

開始ルーチン:

```bash
cd /Users/kantaro/Downloads/toc
scripts/ai/session-bootstrap.sh
```

### 週末だけ常時稼働する場合

- [x] `pmset` 恒久変更ではなく `caffeinate` で止める方式にする
- [ ] 金曜夜か土曜朝に keep-awake を開始する
- [ ] 日曜夜に keep-awake を停止する

開始:

```bash
cd /Users/kantaro/Downloads/toc
scripts/ai/weekend-keepawake-start.sh
```

状態確認:

```bash
cd /Users/kantaro/Downloads/toc
scripts/ai/weekend-keepawake-status.sh
```

停止:

```bash
cd /Users/kantaro/Downloads/toc
scripts/ai/weekend-keepawake-stop.sh
```

補足:

- `caffeinate -dimsu` を使うので、終了すれば通常の省電力設定に戻る
- 再起動後は自動復帰しない
- 週末運用では電源接続を前提にする
- 画面消灯は別で起きうるが、スリープは抑止できる

worktree を使う場合の考え方:

- [ ] 本線ブランチを汚さない
- [ ] スマホでは「どの worktree がどの作業か」を識別できる命名にする
- [ ] 長時間タスクごとに独立セッションを持つ

## Phase 6: スマホから実際にやること

- [ ] 進捗監視
- [ ] エラー確認
- [ ] 次の一手の短文プロンプト送信
- [ ] Markdown の TODO 更新
- [ ] manifest や run 出力の目視確認

スマホ向きの作業:

- [ ] 「続きを進めて」
- [ ] 「失敗原因だけ調べて」
- [ ] 「`movie_todo.md` を見て次の 1 件だけ進めて」
- [ ] 「生成結果を要約して」

PC に戻した方がよい作業:

- [ ] 大きい diff review
- [ ] 競合解消
- [ ] 複数ファイルの構造変更
- [ ] 秘匿情報を触る設定変更

## Security Rules

- [ ] 認証なしで外部公開しない
- [ ] トークンを平文で雑に共有しない
- [ ] 公開 URL は使い終わったら閉じる
- [ ] 不要な daemon を放置しない
- [ ] スマホから触る workspace は必要最小限にする

## Definition of Done

- [ ] スマホから ToC の Codex セッションを開ける
- [ ] 追加プロンプトを送って応答が返る
- [ ] Markdown を 1 ファイル編集できる
- [ ] LAN 利用か外部公開か、使う方式が決まっている
- [ ] 自分用の運用ルーチンがこのファイルに追記されている

## Next Steps

- [ ] 実機で `Phase 1` から順に消化する
- [x] 最初は LAN 内接続だけで成立させる
- [ ] 安定したら外部公開を追加する
- [x] ToC 用の `commandmate` 起動スクリプトを別途作る
