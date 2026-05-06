from __future__ import annotations

import json
import os
import subprocess
import asyncio
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSION_PATH = Path(__file__).resolve().parent / "data" / "sessions.json"

SYSTEM_PROMPT = """あなたは ToC リポジトリ専用の AI 作業エージェントです。
常に日本語で、簡潔かつ実務的に回答してください。

このリポジトリでは次を最優先で守ってください。
- ToC は spec-first repo。正本は docs/, workflow/, scripts/ にあります。
- AGENTS.md / docs/root-pointer-guide.md の指示に従って作業してください。
- ファイル探索は rg --files、内容検索は rg を優先してください。
- state.txt は置き換えず append-only を維持してください。
- hybridization は人間承認なしで進めないでください。
- run_report.md は手書きせず eval_report.json から生成してください。
"""


def _load_sessions() -> dict[str, str]:
    if not SESSION_PATH.exists():
        return {}
    try:
        data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_sessions(data: dict[str, str]) -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_session(user_id: str) -> None:
    sessions = _load_sessions()
    sessions.pop(user_id, None)
    _save_sessions(sessions)


def split_message(text: str, max_len: int = 4500) -> list[str]:
    if len(text) <= max_len:
        return [text]
    return [text[i : i + max_len] for i in range(0, len(text), max_len)]


def process_message(user_id: str, user_message: str, *, timeout_seconds: int = 240) -> str:
    sessions = _load_sessions()
    session_id = sessions.get(user_id)
    is_new = not session_id
    prompt = f"{SYSTEM_PROMPT}\n\n---\n\n[LINE userId: {user_id}]\n\n{user_message}" if is_new else user_message
    args = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--allowedTools",
        "Bash,Read,Write,Edit,Glob,Grep,LS,WebFetch,WebSearch",
        "--add-dir",
        str(PROJECT_ROOT),
    ]
    if session_id:
        args.extend(["--resume", session_id])
    result = subprocess.run(args, cwd=PROJECT_ROOT, capture_output=True, text=True, check=True, timeout=timeout_seconds)
    payload = json.loads(result.stdout)
    if payload.get("session_id"):
        sessions[user_id] = payload["session_id"]
        _save_sessions(sessions)
    return str(payload.get("result") or "応答を取得できませんでした。")


async def handle_line_webhook(body: bytes, signature: str | None) -> dict[str, Any]:
    try:
        from linebot.v3.messaging import ApiClient, Configuration, MessagingApi, ReplyMessageRequest, TextMessage
        from linebot.v3.webhook import WebhookHandler
        from linebot.v3.webhooks import MessageEvent, TextMessageContent
    except ModuleNotFoundError as exc:
        raise RuntimeError("line-bot-sdk is not installed") from exc

    channel_secret = os.environ.get("LINE_CHANNEL_SECRET")
    channel_access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    allowed_user_ids = {
        user_id.strip()
        for user_id in os.environ.get("LINE_ALLOWED_USER_IDS", "").split(",")
        if user_id.strip()
    }
    if not channel_secret or not channel_access_token:
        raise RuntimeError("LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN are required")
    if not allowed_user_ids:
        raise RuntimeError("LINE_ALLOWED_USER_IDS is required")

    handler = WebhookHandler(channel_secret)
    events: list[tuple[str, str, str]] = []

    @handler.add(MessageEvent, message=TextMessageContent)
    def _collect(event: Any) -> None:
        user_id = getattr(getattr(event, "source", None), "user_id", None)
        reply_token = getattr(event, "reply_token", None)
        text = getattr(getattr(event, "message", None), "text", "") or ""
        if user_id and reply_token and text:
            events.append((user_id, reply_token, text.strip()))

    handler.handle(body.decode("utf-8"), signature or "")
    configuration = Configuration(access_token=channel_access_token)
    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        for user_id, reply_token, text in events:
            if user_id not in allowed_user_ids:
                continue
            if text == "/reset":
                clear_session(user_id)
                chunks = ["会話をリセットしました。"]
            else:
                chunks = split_message(await asyncio.to_thread(process_message, user_id, text))
            api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=chunk) for chunk in chunks[:5]],
                )
            )
    return {"status": "ok", "events": len(events)}
