---
name: toc-server-restart
description: "Use when: asked to restart or verify this ToC repository's `/server` frontend/backend or image generation app. Restarts the local FastAPI backend and Vite frontend for `/image_gen` with auth disabled, the canonical local `output/` directory, and health checks on 127.0.0.1:8000 and 127.0.0.1:5173."
---

# ToC Server Restart

## Overview

Restart the local ToC image generation web stack:

- backend: `server.app:app` on `127.0.0.1:8000`
- frontend: Vite app in `server/web` on `127.0.0.1:5173`
- backend auth: always disabled for local verification with `TOC_SERVER_AUTH_DISABLED=1`
- story/run directory source: the canonical local repo output at `/Users/kantaro/Downloads/toc/output`

## When to Use

Use this skill when the user asks to:

- restart the ToC server frontend/backend
- restart or check `/server`
- open or verify the `/image_gen` app
- ensure `http://127.0.0.1:8000/api/image-gen/runs` and `http://127.0.0.1:5173` return 200

## Instructions

1. Run the restart helper:

```bash
bash /Users/kantaro/Downloads/toc/skills/toc-server-restart/scripts/restart-toc-server.sh
```

2. Treat `/Users/kantaro/Downloads/toc` as the canonical local repo root unless the user explicitly asks for another root.
   This is intentional: when the current shell is inside a worktree, the backend must still use the local `output/` directory for story/run folders.

3. Confirm both health checks:

```bash
curl -fsS http://127.0.0.1:8000/api/image-gen/runs >/dev/null
curl -fsS http://127.0.0.1:5173 >/dev/null
```

4. If a health check fails, inspect logs:

```bash
tail -80 /Users/kantaro/Downloads/toc/.codex/run/toc-server/backend.log
tail -80 /Users/kantaro/Downloads/toc/.codex/run/toc-server/frontend.log
```

## Command Details

The helper starts both processes in detached `tmux` sessions when `tmux` is available:

- `toc-server-backend`
- `toc-server-frontend`

If `tmux` is not available, it falls back to `nohup`.

The backend command is:

```bash
TOC_SERVER_AUTH_DISABLED=1 python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
```

The frontend command is:

```bash
cd /Users/kantaro/Downloads/toc/server/web
VITE_API_PROXY_TARGET=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1 --port 5173
```

## Guidelines

- Do not start the backend from `.claude/worktrees/*` when the user expects local story/run directories.
- Do not require `TOC_SERVER_TOKEN` for local server verification; use `TOC_SERVER_AUTH_DISABLED=1`.
- Keep ports stable unless the user asks otherwise: backend `8000`, frontend `5173`.
- If another process owns either port, the helper stops it before starting the local stack.
- Report the two URLs and the log directory after restart.

## Examples

User: "server front/back restart"

Action:

```bash
bash /Users/kantaro/Downloads/toc/skills/toc-server-restart/scripts/restart-toc-server.sh
```

Expected output includes:

```text
[ok] http://127.0.0.1:8000/api/image-gen/runs
[ok] http://127.0.0.1:5173
```
