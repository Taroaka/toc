#!/bin/bash
cd "$(dirname "$0")/server"

echo "サーバー起動中..."
node server.js &
SERVER_PID=$!

sleep 2

echo "ngrok起動中..."
ngrok http --domain=spectator-gothic-shady.ngrok-free.dev 13000

kill $SERVER_PID
