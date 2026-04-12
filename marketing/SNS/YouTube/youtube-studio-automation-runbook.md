# YouTube Studio 自動投稿ランブック

最終更新: 2026-04-12  
対象: `にわかのAI`  
用途: 実際に Codex で YouTube Studio 投稿を回すときの現場手順

---

## 1. 準備

### 人間が事前にやること

- Chrome MCP または同等の browser MCP を接続する
- YouTube / Google へログインする
- 正しいチャンネル `にわかのAI` を選んでおく
- 動画ファイルとサムネイルをローカルに置く
- `urashima-publish-kit.md` を確認する

### 事前確認

- custom thumbnail が使える
- comments が有効
- `Not made for kids` を使える
- 高度機能が必要な制限に詰まっていない

---

## 2. 正しいチャンネル確認

YouTube Studio を開いたら、次を確認する。

- 表示名が `にわかのAI`
- handle が `@niwakanoai`
- アイコンや top UI が意図したチャンネルのもの

もし channel switcher が出る、または複数候補が見えるなら、自動化はそこで止める。

---

## 3. Codex への依頼開始

Codex には次を渡す。

- `video_path`
- `thumbnail_path`
- `title`
- `description`
- `pinned_comment`
- `visibility`
- optional `publish_datetime_jst`

copy の source of truth は `urashima-publish-kit.md`。

---

## 4. 標準フロー

1. snapshot を取る
2. upload URL へ移動する
3. 動画アップロード
4. metadata 入力
5. thumbnail 入力
6. audience 設定
7. visibility 設定
8. save
9. 保存状態確認
10. 必要なら公開後に固定コメント

デフォルトは `Private` 保存で止める。

---

## 5. 人間が必ずやること

- ログイン
- 2FA
- CAPTCHA
- 正しいチャンネル確認
- 最終公開判断

必要なら、人間が publish ボタンだけ押してもよい。

---

## 6. 成功条件

- draft または scheduled/public として保存された
- title が正しい
- description が正しい
- thumbnail が正しい
- audience が `Not made for kids`
- 誤チャンネルでない
- 公開後なら pinned comment が存在する

---

## 7. 失敗時の復旧

### wrong channel selected

- 自動化を停止
- 人間が正しいチャンネルへ切り替え
- 最初からやり直し

### upload stuck

- processing 状態を確認
- save 可能かを見る
- 長く進まないならアップロードをやり直す

### thumbnail over 2MB

- 人間が圧縮版を用意
- 同じ手順で再アップロード

### save not persisting

- save button の有効状態を再確認
- reopen して値が残るかを見る
- 残らない場合は UI 不安定として停止

### publish date/time mismatch

- JST 指定値を再確認
- YouTube の表示日付差に注意
- 不安なら scheduled で止めて人間確認

### comments disabled unexpectedly

- kids 判定や comment setting を確認
- 想定外なら公開前に停止して修正

---

## 8. 実務上の注意

- 一度に複数本投稿しない
- metadata を何度も更新しない
- publish 後数分でタイトルやサムネを連打しない
- external sharing は別手順で行う

---

## 9. 互換メモ

主経路は `Chrome MCP`。

Playwright など同等 browser MCP でも使えるが、その場合も要件は同じ。

- ログイン済みブラウザセッション
- upload URL へ移動可能
- file upload 可能
- comment 投稿可能

---

## 10. 次に読むもの

- automation 仕様 → `youtube-studio-automation-spec.md`
- 投稿文面 → `urashima-publish-kit.md`
- 単発投稿プレイブック → `first-upload-playbook.md`
