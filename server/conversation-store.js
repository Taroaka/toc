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
