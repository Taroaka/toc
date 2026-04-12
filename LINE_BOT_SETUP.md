# LINE Bot × Claude Code セットアップガイド

このガイドに従うと、任意のリポジトリにLINE経由でClaude Codeと会話できるボットを構築できる。
次のポートは **13000** を使う（このリポジトリは3000）。

---

## 前提条件

- Claude Codeインストール済み・ログイン済み（`claude --version` で確認）
- Node.js 18以上（`node --version` で確認）
- ngrokインストール済み・認証済み（`ngrok config check` で確認）
- LINEアカウント

## 運用前提メモ

- Mac本体では `sudo pmset -a sleep 0` と `sudo pmset -a disksleep 0` を実行して、AC・バッテリーともにスリープしない設定にしておく
- スリープ設定を戻す場合は `sudo pmset -a restoredefaults`
- Claude Code の TUI 入力欄が `Terminal.app` で不安定になる場合があるため、`iTerm2` の使用を推奨
- Mac再起動後は `./start.sh` を手動で再実行する必要がある
- ngrok 固定ドメインを使っている場合、再起動のたびに LINE Developers 側の Webhook URL を再設定する必要はない

---

## ステップ1: LINE Developers でチャネル作成

1. https://developers.line.biz/ にログイン
2. プロバイダー作成（初回のみ）
3. 「Messaging APIチャネル」を新規作成
4. 以下をメモしておく：
   - **チャネルシークレット**（「チャネル基本設定」タブ）
   - **チャネルアクセストークン（長期）**（「Messaging API設定」タブ最下部で「発行」）

---

## ステップ2: server/ ディレクトリを作成

リポジトリのルートに以下の4ファイルを作成する。

### server/package.json

```json
{
  "name": "line-bot",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "start": "node server.js",
    "dev": "node --watch server.js"
  },
  "dependencies": {
    "@line/bot-sdk": "^9.4.0",
    "dotenv": "^16.4.0",
    "express": "^4.21.0"
  }
}
```

### server/.env

```
LINE_CHANNEL_SECRET=ここにチャネルシークレット
LINE_CHANNEL_ACCESS_TOKEN=ここにアクセストークン
PORT=13000
```

### server/conversation-store.js

```javascript
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STORE_PATH = path.join(__dirname, 'data', 'sessions.json');

function loadStore() {
  if (!fs.existsSync(STORE_PATH)) return {};
  try {
    return JSON.parse(fs.readFileSync(STORE_PATH, 'utf-8'));
  } catch {
    return {};
  }
}

function saveStore(store) {
  fs.mkdirSync(path.dirname(STORE_PATH), { recursive: true });
  fs.writeFileSync(STORE_PATH, JSON.stringify(store, null, 2), 'utf-8');
}

export function loadSession(userId) {
  return loadStore()[userId] ?? null;
}

export function saveSession(userId, sessionId) {
  const store = loadStore();
  store[userId] = sessionId;
  saveStore(store);
}

export function clearSession(userId) {
  const store = loadStore();
  delete store[userId];
  saveStore(store);
}
```

### server/claude-agent.js

```javascript
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import { loadSession, saveSession } from './conversation-store.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '..');

// ========================================
// ★ このリポジトリ用のシステムプロンプトをここに書く
// ========================================
const SYSTEM_PROMPT = `あなたは優秀なAIエージェントです。
ユーザーとのLINE会話を通じてサポートします。
常に日本語で回答してください。`;

const ALLOWED_TOOLS = 'Bash,Read,Write,Edit,Glob,Grep,LS,WebFetch,WebSearch';

function runClaude(args, cwd) {
  return new Promise((resolve, reject) => {
    const proc = spawn('claude', args, { cwd });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', chunk => { stdout += chunk; });
    proc.stderr.on('data', chunk => { stderr += chunk; });
    proc.on('error', err => reject(new Error(`claude 起動失敗: ${err.message}`)));
    proc.on('close', code => {
      if (code !== 0) {
        reject(new Error(`claude 終了コード ${code}\nstderr: ${stderr.slice(0, 500)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(new Error(`JSON パース失敗: ${stdout.slice(0, 300)}`));
      }
    });
  });
}

export async function processMessage(userId, userMessage) {
  const sessionId = loadSession(userId);
  const isNew = !sessionId;

  const prompt = isNew
    ? `${SYSTEM_PROMPT}\n\n---\n\n[LINE userId: ${userId}]\n\n${userMessage}`
    : userMessage;

  const args = [
    '-p', prompt,
    '--output-format', 'json',
    '--allowedTools', ALLOWED_TOOLS,
    '--add-dir', PROJECT_ROOT,
  ];

  if (!isNew) args.push('--resume', sessionId);

  let result;
  try {
    result = await runClaude(args, PROJECT_ROOT);
  } catch (err) {
    if (!isNew && err.message.includes('session')) {
      console.warn(`[${userId}] セッション切れ、再試行`);
      const retryArgs = [
        '-p', `${SYSTEM_PROMPT}\n\n---\n\n[LINE userId: ${userId}]\n\n${userMessage}`,
        '--output-format', 'json',
        '--allowedTools', ALLOWED_TOOLS,
        '--add-dir', PROJECT_ROOT,
      ];
      result = await runClaude(retryArgs, PROJECT_ROOT);
    } else {
      throw err;
    }
  }

  if (result.session_id) saveSession(userId, result.session_id);
  return result.result ?? '応答を取得できませんでした。';
}
```

### server/server.js

```javascript
import express from 'express';
import { messagingApi, middleware } from '@line/bot-sdk';
import { processMessage } from './claude-agent.js';
import { clearSession } from './conversation-store.js';
import 'dotenv/config';

const lineConfig = {
  channelSecret: process.env.LINE_CHANNEL_SECRET,
  channelAccessToken: process.env.LINE_CHANNEL_ACCESS_TOKEN,
};

const client = new messagingApi.MessagingApiClient(lineConfig);
const app = express();

app.post('/webhook', middleware(lineConfig), async (req, res) => {
  res.json({ status: 'ok' });
  for (const event of req.body.events ?? []) {
    await handleEvent(event).catch(err =>
      console.error(`[${event.source?.userId}] エラー:`, err)
    );
  }
});

app.get('/', (_req, res) => res.json({ status: 'running' }));

async function handleEvent(event) {
  const userId = event.source?.userId;
  if (event.type !== 'message' || event.message?.type !== 'text') return;

  const userMessage = event.message.text.trim();
  const replyToken = event.replyToken;

  if (userMessage === '/reset') {
    clearSession(userId);
    await replyToUser(replyToken, ['会話をリセットしました。']);
    return;
  }

  console.log(`[${userId}] 受信: ${userMessage.slice(0, 50)}`);
  const responseText = await processMessage(userId, userMessage);
  console.log(`[${userId}] 返信: ${responseText.length}文字`);
  await replyToUser(replyToken, splitMessage(responseText));
}

async function replyToUser(replyToken, chunks) {
  await client.replyMessage({
    replyToken,
    messages: chunks.slice(0, 5).map(text => ({ type: 'text', text })),
  });
}

function splitMessage(text, max = 4500) {
  if (text.length <= max) return [text];
  const chunks = [];
  for (let i = 0; i < text.length; i += max) chunks.push(text.slice(i, i + max));
  return chunks;
}

const PORT = parseInt(process.env.PORT ?? '3000', 10);
app.listen(PORT, () => {
  console.log(`🚀 LINE Bot 起動 (ポート: ${PORT})`);
});
```

---

## ステップ3: 依存パッケージをインストール

```bash
cd server
npm install
```

---

## ステップ4: .claude/settings.json を作成（権限設定）

リポジトリルートに `.claude/settings.json` を作成：

```json
{
  "permissions": {
    "allow": [
      "Bash(*)",
      "Read(/path/to/your/repo/**)",
      "Write(/path/to/your/repo/**)",
      "Edit(/path/to/your/repo/**)",
      "Glob(/path/to/your/repo/**)",
      "Grep(/path/to/your/repo/**)",
      "LS(/path/to/your/repo/**)",
      "WebFetch(*)",
      "WebSearch(*)"
    ],
    "deny": [
      "Read(/path/to/your/repo/server/.env)"
    ]
  }
}
```

※ `/path/to/your/repo/` を実際のパスに置き換える

---

## ステップ5: .gitignore に追記

```
server/.env
server/data/
```

---

## ステップ6: 起動スクリプトを作成

リポジトリルートに `start.sh` を作成：

```bash
#!/bin/bash
cd "$(dirname "$0")/server"

echo "🚀 サーバー起動中..."
node server.js &
SERVER_PID=$!

sleep 2

echo "🌐 ngrok起動中..."
# ★ ngrokの固定ドメインを取得して下記に入れる（dashboard.ngrok.com/domains）
ngrok http --domain=YOUR-FIXED-DOMAIN.ngrok-free.dev 13000

kill $SERVER_PID
```

```bash
chmod +x start.sh
```

---

## ステップ7: ngrok固定ドメインを取得

1. https://dashboard.ngrok.com/domains にアクセス
2. 「New Domain」で無料ドメインを発行
3. `start.sh` の `YOUR-FIXED-DOMAIN` を置き換える

---

## ステップ8: LINE DevelopersにWebhook URLを設定

1. `./start.sh` を実行
2. LINE Developers → Messaging API設定 → Webhook URL に以下を入力：
   ```
   https://YOUR-FIXED-DOMAIN.ngrok-free.dev/webhook
   ```
3. 「検証」→ `200 OK` を確認
4. 「Webhookの利用」を **オン** にする
5. 「応答メッセージ」を **オフ** にする

---

## 起動コマンド（毎回）

```bash
./start.sh
```

Macを再起動した後も自動では復帰しないため、毎回手動で起動する。

## 稼働確認

```bash
curl http://localhost:13000/
```

正常時は次が返る。

```json
{"status":"running"}
```

## 停止方法

`./start.sh` を実行しているターミナルで `Ctrl+C` を押す。

## リセットコマンド（LINEから送信）

```
/reset
```

---

## カスタマイズポイント

| ファイル | 変更箇所 |
|----------|----------|
| `server/claude-agent.js` | `SYSTEM_PROMPT` にこのリポジトリ用の指示を書く |
| `server/.env` | `PORT` を変更（このガイドでは13000） |
| `start.sh` | ngrokドメインとポート番号 |
| `.claude/settings.json` | リポジトリのパス |
