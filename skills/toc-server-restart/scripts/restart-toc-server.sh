#!/usr/bin/env bash
set -euo pipefail

DEFAULT_LOCAL_REPO_ROOT="/Users/kantaro/Downloads/toc"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${TOC_LOCAL_REPO_ROOT:-}" ]]; then
  REPO_ROOT="$(cd "$TOC_LOCAL_REPO_ROOT" && pwd)"
elif [[ -d "$DEFAULT_LOCAL_REPO_ROOT/server" ]]; then
  REPO_ROOT="$DEFAULT_LOCAL_REPO_ROOT"
else
  CANDIDATE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
  if [[ -d "$CANDIDATE_ROOT/server" ]]; then
    REPO_ROOT="$CANDIDATE_ROOT"
  else
    echo "[error] Cannot find ToC repo root. Set TOC_LOCAL_REPO_ROOT." >&2
    exit 1
  fi
fi

if [[ ! -f "$REPO_ROOT/server/app.py" || ! -f "$REPO_ROOT/server/web/package.json" ]]; then
  echo "[error] Invalid ToC repo root: $REPO_ROOT" >&2
  exit 1
fi

BACKEND_HOST="${TOC_SERVER_HOST:-127.0.0.1}"
BACKEND_PORT="${TOC_SERVER_PORT:-8000}"
FRONTEND_HOST="${TOC_WEB_HOST:-127.0.0.1}"
FRONTEND_PORT="${TOC_WEB_PORT:-5173}"
PYTHON_BIN="${TOC_PYTHON:-python}"
NPM_BIN="${TOC_NPM:-npm}"
TMUX_BIN="${TOC_TMUX:-}"
if [[ -z "$TMUX_BIN" ]] && command -v tmux >/dev/null 2>&1; then
  TMUX_BIN="$(command -v tmux)"
fi
TMUX_SESSION_PREFIX="${TOC_TMUX_SESSION_PREFIX:-toc-server}"
BACKEND_TMUX_SESSION="$TMUX_SESSION_PREFIX-backend"
FRONTEND_TMUX_SESSION="$TMUX_SESSION_PREFIX-frontend"

RUN_DIR="${TOC_SERVER_RUN_DIR:-$REPO_ROOT/.codex/run/toc-server}"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG="$RUN_DIR/backend.log"
FRONTEND_LOG="$RUN_DIR/frontend.log"

mkdir -p "$RUN_DIR" "$REPO_ROOT/output"

stop_tmux_session() {
  local session="$1"
  local label="$2"

  if [[ -z "$TMUX_BIN" ]]; then
    return
  fi

  if "$TMUX_BIN" has-session -t "$session" 2>/dev/null; then
    echo "[restart] stopping $label tmux session $session"
    "$TMUX_BIN" kill-session -t "$session" 2>/dev/null || true
  fi
}

stop_pid_file() {
  local pid_file="$1"
  local label="$2"
  local pid=""

  if [[ ! -f "$pid_file" ]]; then
    return
  fi

  pid="$(cat "$pid_file" 2>/dev/null || true)"
  rm -f "$pid_file"

  if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
    return
  fi

  if ! kill -0 "$pid" 2>/dev/null; then
    return
  fi

  echo "[restart] stopping $label pid $pid"
  kill "$pid" 2>/dev/null || true

  for _ in $(seq 1 30); do
    if ! kill -0 "$pid" 2>/dev/null; then
      return
    fi
    sleep 0.1
  done

  if kill -0 "$pid" 2>/dev/null; then
    echo "[restart] force stopping $label pid $pid"
    kill -9 "$pid" 2>/dev/null || true
  fi
}

stop_port() {
  local port="$1"
  local label="$2"
  local pids=""

  if ! command -v lsof >/dev/null 2>&1; then
    return
  fi

  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true)"
  if [[ -z "$pids" ]]; then
    return
  fi

  echo "[restart] stopping $label listener(s) on port $port: $pids"
  kill $pids 2>/dev/null || true
  sleep 0.5

  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true)"
  if [[ -n "$pids" ]]; then
    echo "[restart] force stopping $label listener(s) on port $port: $pids"
    kill -9 $pids 2>/dev/null || true
  fi
}

wait_http() {
  local url="$1"
  local label="$2"
  local log_file="$3"

  for _ in $(seq 1 80); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "[ok] $url"
      return 0
    fi
    sleep 0.25
  done

  echo "[error] $label did not become healthy: $url" >&2
  echo "[error] recent $label log: $log_file" >&2
  tail -80 "$log_file" >&2 || true
  return 1
}

start_backend() {
  : >"$BACKEND_LOG"

  if [[ -n "$TMUX_BIN" ]]; then
    "$TMUX_BIN" new-session -d -s "$BACKEND_TMUX_SESSION" -c "$REPO_ROOT" \
      "TOC_SERVER_AUTH_DISABLED=1 TOC_OUTPUT_ROOT=\"$REPO_ROOT/output\" exec \"$PYTHON_BIN\" -m uvicorn server.app:app --host \"$BACKEND_HOST\" --port \"$BACKEND_PORT\" >>\"$BACKEND_LOG\" 2>&1"
    "$TMUX_BIN" display-message -p -t "$BACKEND_TMUX_SESSION" "#{pane_pid}" >"$BACKEND_PID_FILE" 2>/dev/null || true
    return
  fi

  (
    cd "$REPO_ROOT"
    TOC_SERVER_AUTH_DISABLED=1 \
    TOC_OUTPUT_ROOT="$REPO_ROOT/output" \
    nohup "$PYTHON_BIN" -m uvicorn server.app:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
      >"$BACKEND_LOG" 2>&1 &
    pid=$!
    echo "$pid" >"$BACKEND_PID_FILE"
    disown "$pid" 2>/dev/null || true
  )
}

start_frontend() {
  : >"$FRONTEND_LOG"

  if [[ -n "$TMUX_BIN" ]]; then
    "$TMUX_BIN" new-session -d -s "$FRONTEND_TMUX_SESSION" -c "$REPO_ROOT/server/web" \
      "VITE_API_PROXY_TARGET=\"http://$BACKEND_HOST:$BACKEND_PORT\" exec \"$NPM_BIN\" run dev -- --host \"$FRONTEND_HOST\" --port \"$FRONTEND_PORT\" >>\"$FRONTEND_LOG\" 2>&1"
    "$TMUX_BIN" display-message -p -t "$FRONTEND_TMUX_SESSION" "#{pane_pid}" >"$FRONTEND_PID_FILE" 2>/dev/null || true
    return
  fi

  (
    cd "$REPO_ROOT/server/web"
    VITE_API_PROXY_TARGET="http://$BACKEND_HOST:$BACKEND_PORT" \
    nohup "$NPM_BIN" run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" \
      >"$FRONTEND_LOG" 2>&1 &
    pid=$!
    echo "$pid" >"$FRONTEND_PID_FILE"
    disown "$pid" 2>/dev/null || true
  )
}

stop_tmux_session "$FRONTEND_TMUX_SESSION" "frontend"
stop_tmux_session "$BACKEND_TMUX_SESSION" "backend"
stop_pid_file "$FRONTEND_PID_FILE" "frontend"
stop_pid_file "$BACKEND_PID_FILE" "backend"
stop_port "$FRONTEND_PORT" "frontend"
stop_port "$BACKEND_PORT" "backend"

echo "[start] repo root: $REPO_ROOT"
echo "[start] output root: $REPO_ROOT/output"
echo "[start] logs: $RUN_DIR"
if [[ -n "$TMUX_BIN" ]]; then
  echo "[start] tmux: $TMUX_BIN"
fi

start_backend

wait_http "http://$BACKEND_HOST:$BACKEND_PORT/api/image-gen/runs" "backend" "$BACKEND_LOG"

start_frontend

wait_http "http://$FRONTEND_HOST:$FRONTEND_PORT" "frontend" "$FRONTEND_LOG"

echo "[ready] backend:  http://$BACKEND_HOST:$BACKEND_PORT/api/image-gen/runs"
echo "[ready] frontend: http://$FRONTEND_HOST:$FRONTEND_PORT"
