#!/usr/bin/env bash
# Claude Code Remote Control 起動スクリプト
# スマホ / ブラウザ (claude.ai/code) から ToC セッションを操作できるようにする
#
# 使い方:
#   scripts/ai/claude-remote-control.sh            # サーバーモード（ローカル対話なし）
#   scripts/ai/claude-remote-control.sh --interactive  # ローカル対話 + リモート接続両立
#
# 接続先: claude.ai/code または Claude モバイルアプリ
# 前提: claude auth login 済み（inference-only トークンは不可）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOC_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SESSION_NAME="ToC"

cd "${TOC_ROOT}"

# スコープ確認（inference-only だと Remote Control 不可）
check_scope() {
  local creds="${HOME}/.claude/.credentials.json"
  if [[ -f "${creds}" ]]; then
    local scopes
    scopes=$(python3 -c "
import json, sys
d = json.load(open('${creds}'))
sc = d.get('claudeAiOauth', {}).get('scopes', [])
print(' '.join(sc))
" 2>/dev/null || echo "")
    if [[ "${scopes}" == "user:inference" ]] && [[ "${scopes}" != *"user:profile"* ]]; then
      echo "[ERROR] 現在の認証トークンは inference-only スコープのみです。"
      echo "        Remote Control にはフルスコープのログインが必要です。"
      echo ""
      echo "  新しいターミナルで次を実行してください:"
      echo "    claude auth login"
      echo ""
      echo "  または Claude Code セッション内では:"
      echo "    /login"
      exit 1
    fi
  fi
}

# 実行テストで詳細なエラーを確認
check_remote_control() {
  local output
  if ! output=$(claude remote-control --help 2>&1); then
    if echo "${output}" | grep -q "full-scope login token"; then
      echo "[ERROR] Remote Control にはフルスコープのログインが必要です。"
      echo ""
      echo "  新しいターミナルで次を実行してください:"
      echo "    claude auth login"
      echo ""
      echo "  ※ CLAUDE_CODE_OAUTH_TOKEN や setup-token では Remote Control は使えません。"
      exit 1
    fi
  fi
}

check_scope
check_remote_control

if [[ "${1:-}" == "--interactive" ]]; then
  echo "[INFO] Interactive + Remote Control モードで起動します"
  echo "[INFO] 接続先: claude.ai/code または Claude モバイルアプリ"
  echo "[INFO] セッション名: ${SESSION_NAME}"
  echo ""
  exec claude --rc "${SESSION_NAME}"
else
  echo "[INFO] Remote Control サーバーモードで起動します（ローカル対話なし）"
  echo "[INFO] 接続先: claude.ai/code または Claude モバイルアプリ"
  echo "[INFO] セッション名: ${SESSION_NAME}"
  echo ""
  exec claude remote-control --name "${SESSION_NAME}"
fi
