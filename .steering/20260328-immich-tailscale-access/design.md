# Design

## Decision

- Tailscale は Homebrew cask で導入する
- 接続先表示は `tailscale status --json` を優先する
- `immich-info.sh` に Tailscale IP / MagicDNS を追加する

## Why This Shape

- macOS では Tailscale の standalone / App Store いずれもあるが、この環境では Homebrew 経由が最短
- スマホの Codex からは「Tailscale が未ログイン」「ログイン済みで利用可能」をすぐ判断できる方がよい
- Immich 側の URL 表示に Tailscale 情報が含まれていれば、遠隔利用の prompt が短くなる

## Changes

### 1. Tailscale 導入補助

- `scripts/ai/tailscale-install.sh`
  - Homebrew cask install
  - アプリ起動補助

### 2. Tailscale 情報表示

- `scripts/ai/tailscale-info.sh`
  - バージョン
  - backend state
  - self の Tailscale IP
  - self の DNS name

### 3. Immich 情報への統合

- `scripts/ai/immich-info.sh`
  - Tailscale URL を追加

### 4. ドキュメント更新

- `immich_remote.md`
  - 別 Wi-Fi 前提
  - Mac / iPhone 両方での導入順
  - 使う URL の優先順位

## Verification

- `tailscale-info.sh` が未導入でも失敗理由を返す
- `rg` で `Tailscale` `MagicDNS` `100.` が入っていることを確認する
