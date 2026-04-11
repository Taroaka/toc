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
  console.log(`LINE Bot 起動 (ポート: ${PORT})`);
});
