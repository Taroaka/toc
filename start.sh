#!/bin/bash
cd "$(dirname "$0")"

echo "サーバー起動中..."
python -m uvicorn server.app:app --host 127.0.0.1 --port "${PORT:-13000}" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

sleep 2

if [ "${ENABLE_NGROK:-0}" = "1" ]; then
  if [ -z "${TOC_SERVER_TOKEN:-}" ]; then
    echo "ENABLE_NGROK=1 では TOC_SERVER_TOKEN が必須です。" >&2
    kill "$SERVER_PID"
    exit 1
  fi
  echo "ngrok起動中... /image_gen と /api は token 保護されています。"
  ngrok http --domain=spectator-gothic-shady.ngrok-free.dev "${PORT:-13000}"
else
  echo "ローカル起動: http://127.0.0.1:${PORT:-13000}/image_gen"
  wait "$SERVER_PID"
fi
