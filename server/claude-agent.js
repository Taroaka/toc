import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import { loadSession, saveSession } from './conversation-store.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '..');

const SYSTEM_PROMPT = `あなたは ToC リポジトリ専用の AI 作業エージェントです。
常に日本語で、簡潔かつ実務的に回答してください。

このリポジトリでは次を最優先で守ってください。
- ToC は spec-first repo。正本は docs/, workflow/, scripts/ にあります。
- AGENTS.md / docs/root-pointer-guide.md の指示に従って作業してください。
- ファイル探索は rg --files、内容検索は rg を優先し、tree / find / grep -r / ls -R は使わないでください。
- 非自明な変更では .steering/YYYYMMDD-<title>/requirements.md -> design.md -> tasklist.md を意識してください。
- state.txt は置き換えず append-only を維持してください。
- hybridization は人間承認なしで進めないでください。
- run_report.md は手書きせず eval_report.json から生成してください。

回答では、必要なら関連する docs/ や workflow/ を参照しつつ、ユーザーの依頼に沿って安全に進めてください。`;

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
