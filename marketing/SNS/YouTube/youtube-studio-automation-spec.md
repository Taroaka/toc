# YouTube Studio 自動投稿仕様

最終更新: 2026-04-12  
対象: `にわかのAI` の YouTube Studio 投稿運用  
目的: `YouTube Data API` を使わず、`Codex + browser/Chrome MCP` で半自動投稿するための仕様を固定する

---

## 1. この仕様の位置づけ

これは `marketing/browser-use.md` の抽象ガイドを、`にわかのAI` の YouTube 投稿に絞って具体化した仕様書。

前提:

- API 料金は使わない
- YouTube Studio の browser automation を使う
- 人間はログイン、2FA、CAPTCHA、最終確認を担当する
- Codex は upload と metadata 入力を担当する

---

## 2. 対象チャンネル

- channel name: `にわかのAI`
- handle: `@niwakanoai`
- 運用モード: `single-channel only`

この v1 では、複数チャンネル切り替えを前提にしない。
channel switcher が出た時点で、いったん停止して人間確認に切り替える。

---

## 3. 対応する自動化範囲

### 対応すること

- YouTube Studio upload URL を開く
- 動画ファイルをアップロードする
- タイトルを入力する
- 概要欄を入力する
- サムネイルをアップロードする
- audience を `Not made for kids` に設定する
- visibility を `Private` または `Scheduled/Public` に設定する
- 保存状態を確認する
- 公開後に固定コメントを投稿して pin する

### 対応しないこと

- ログイン自動化
- 2FA / CAPTCHA 回避
- bulk upload
- unattended mass posting
- 自動 external sharing
- publish 後の metadata 連続更新

---

## 4. デフォルト運用

### 基本モード

`draft-first`

意味:

- 最初は `Private` で保存
- 人間が内容とチャンネルを確認
- publish は人間確認後

### 例外

人間が明示的に `Scheduled` を指定した場合だけ、予約公開まで進めてよい。

---

## 5. 必須前提

- Chrome MCP または同等の browser MCP が接続されている
- 制御対象ブラウザで YouTube / Google にログイン済み
- 正しいチャンネルが選択済み
- サムネイルが 2MB 以下
- 投稿文面は既存の publish kit から取る

単一の source of truth:

- `marketing/SNS/YouTube/urashima-publish-kit.md`

automation 側で copy を創作しない。

---

## 6. 入力契約

必要入力:

- `video_path`
- `thumbnail_path`
- `title`
- `description`
- `pinned_comment`
- `visibility`
- optional `publish_datetime_jst`
- optional `CHANNEL_ID`

デフォルト値:

- `title`: `urashima-publish-kit.md`
- `description`: `urashima-publish-kit.md`
- `pinned_comment`: `urashima-publish-kit.md`

---

## 7. upload シーケンス

1. browser snapshot を取る
2. YouTube Studio upload URL へ移動する
3. channel identity を確認する
4. 動画ファイルをアップロードする
5. 編集可能になるまで待つ
6. title を入力する
7. description を入力する
8. thumbnail をアップロードする
9. audience を `Not made for kids` に設定する
10. visibility を設定する
11. Save を即押す
12. 保存状態を再確認する

原則:

- 入力後は save を先送りしない
- UI が不安定なら、save 済みかを先に確認する

---

## 8. post-publish シーケンス

1. 公開された動画ページを開く
2. fixed `pinned_comment` を投稿する
3. comment を pin する
4. comment の存在を確認する

---

## 9. 停止条件

次の条件では、人間確認に切り替えて停止する。

- auth prompt が出た
- channel switcher が出た
- thumbnail が reject された
- save button が disabled のまま
- publish state が明確でない
- 期待していない validation error が出た

---

## 10. 運用デフォルト

- audience: `Not made for kids`
- comments: enabled + moderation
- upload visibility: `Private`
- final publish: explicit human confirmation required
- external sharing: automation scope 外
- publish 後数分は metadata churn をしない

---

## 11. 検証観点

- draft を保存して reopen しても title/description/thumbnail が残る
- audience が `Not made for kids` のまま
- 正しいチャンネルに入っている
- 固定コメントが投稿され pin できる
- 認証や UI エラー時に停止する

---

## 12. 次に読むもの

- 運用手順 → `youtube-studio-automation-runbook.md`
- 投稿文面 → `urashima-publish-kit.md`
- policy → `channel-policy-and-ops.md`
