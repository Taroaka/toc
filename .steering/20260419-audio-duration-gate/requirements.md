# Requirements

## Goal

音声生成後に実尺を確認し、目標尺に足りない run をそのまま人レビューへ流さず、
scene 設計と narration 設計の見直し review を差し込めるようにする。

## Required behavior

1. TTS 実行後、manifest の実尺を source of truth として判定する。
2. `cinematic_story` は既定で 300 秒以上を目標尺とする。
3. 実尺が目標未満なら、画像/動画生成へ進まず停止する。
4. 停止時には次を自動生成する。
   - scene 設計見直し用 subagent prompt artifact
   - narration 拡張見直し用 subagent prompt artifact
5. 停止時には state と p-slot に未達状態を残す。
6. 目標尺を満たした run だけが次の human review へ進める。
7. この workflow は全 story の固定 p-slot 契約に反映される。

## Non-goals

- repo から Codex subagent を強制 spawn すること
- subagent review の結果を自動で story/script/manifest に反映すること

