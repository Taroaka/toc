# Marketing browser-use guide

最終更新: 2026-04-12

`marketing/` 配下で Web UI を触る必要があるときの共通ガイド。
対象は YouTube Studio や各 SNS の管理画面、公開プロフィール、競合チャンネル調査など。

---

## 1. Decision

`API を前提にしない browser 操作` をしたいなら、基本方針はこれ。

- `Codex app` または `Codex CLI`
- `ChatGPT account` でログイン
- `MCP` でブラウザ操作ツールを接続
- 対象サービスをブラウザで開いて、`確認 / 記録 / 軽い反復操作` を支援させる

marketing では `Codex web 単体` より `Codex app / CLI + browser MCP` を優先する。
理由は、SNS 管理画面のような GUI 前提の作業と相性がよいから。

---

## 2. Recommended setup

### Option A

`Codex app + Playwright MCP`

- GUI 操作との相性がよい
- 画面観察、スクリーンショット、DOM確認がしやすい
- 日々の marketing オペで扱いやすい

### Option B

`Codex CLI + Playwright MCP`

- repo 内の運用と相性がよい
- 手順の再利用性が高い
- ドキュメント化しやすい

---

## 3. Official setup sketch

1. Codex に ChatGPT アカウントでログインする

```bash
codex login
```

2. Playwright MCP を追加する

```bash
codex mcp add playwright -- npx @playwright/mcp@latest
```

3. MCP 接続を確認する

```bash
codex mcp
```

4. 対象サービスを開いて、人間がログインする

最初は `人間がログインし、Codex はログイン後の観察と軽い操作だけを担当する` 形に寄せる。

---

## 4. Good use cases in marketing

- YouTube Studio の KPI を週次で確認して記録する
- 公開済み動画のタイトル、説明文、リンク、再生リスト設定を点検する
- コメント欄を読んで、傾向を要約する
- 競合チャンネルや類似動画の公開ページを調査して比較メモを作る
- SNS 投稿前にプロフィール、固定リンク、導線の見え方を確認する

---

## 5. Guardrails

- 大量投稿、連続クリック、無制限スクレイピングはしない
- ログイン、2FA、支払い、権限変更は人間主導で行う
- まずは `観察 -> 1回だけ試す -> 安全なら繰り返す` の順で進める
- private な画面情報は必要最小限だけ読む
- 利用規約やアカウント保護に抵触しそうな自動化は避ける

---

## 6. First prompt template

```text
Use the browser MCP to open [TARGET_URL].
Wait for me to complete login manually if needed.
After login, inspect the page structure and identify the UI elements needed for [TASK].
Do one safe trial action only.
Then save a screenshot and summarize which elements look stable enough for a repeatable workflow.
Do not perform bulk actions.
```

---

## 7. Marketing prompt examples

### YouTube Studio 週次KPI確認

```text
Use the browser MCP to open YouTube Studio.
Wait for manual login if needed.
Navigate to the analytics pages for the latest video and collect impressions, CTR, average view duration, retention, likes, comments, and saves if visible.
Do not edit any settings.
Save one screenshot per key screen and summarize the metrics in a compact table.
```

### 公開前チェック

```text
Use the browser MCP to open YouTube Studio and inspect the draft upload settings for the target video.
Check title, description, playlist, audience setting, end screen, cards, and publish schedule.
Do not publish the video.
Report missing items against the repo checklist and save screenshots of the settings pages you checked.
```

### 競合チャンネル調査

```text
Use the browser MCP to open the target public YouTube channels and videos.
Collect title patterns, thumbnail motifs, upload cadence, and visible engagement signals from the latest 10 uploads.
Do not log in unless needed.
Summarize repeated patterns and list what seems reusable for にわかのAI.
```

---

## 8. Not the goal yet

- 全SNSの完全自動運用
- 長時間の無監督ブラウザセッション
- アカウント大量操作
- bulk extraction of private dashboard data

---

## 9. Practical conclusion

`marketing で browser-use したい` ときは、

- `Codex app / CLI`
- `ChatGPT login`
- `browser MCP`

この3点を前提に、まずは `確認・要約・軽い点検` から使い始める。
投稿や設定変更の本番反映は、人間確認を挟む。
