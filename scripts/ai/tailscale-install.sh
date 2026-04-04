#!/usr/bin/env bash
set -euo pipefail

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required" >&2
  exit 1
fi

brew install --cask tailscale
open -a Tailscale

echo "Tailscale installed"
echo "Next:"
echo "  1. Sign in on this Mac"
echo "  2. Install Tailscale on iPhone"
echo "  3. Sign in with the same account"
