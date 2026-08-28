# Requirements: Adaptive ToC resume routing

## Goal

既存の frontend-created ToC run を常に p500 へ戻すのではなく、失敗原因と
current artifact の整合性から、最も後ろにある安全な再開境界を選んで再実行する。

## Success criteria

- scene image API / output failure で p650 契約が current の場合、p500 を再実行せず
  p650 直後の image-only resume を使う。
- asset / reference、request freeze、semantic QA、または p650 契約が stale / invalid
  の場合だけ canonical p500 checkpoint resume へ戻る。
- slot 番号や `runtime.stage` だけで再開地点を決めず、canonical validator、request
  binding、generation provenance、active lock を根拠にする。
- unknown / contradictory state では前方へ飛ばず fail closed にする。
- `state.txt` の append-only 履歴と同一 run directory を維持する。

## Scope

- `.codex/skills/toc-resume-p500/SKILL.md`
- `.codex/skills/toc-resume-p500/agents/openai.yaml`

## Non-goals

- 未実装の任意 slot resume command を新設すること。
- p560 asset generation failure を p550 から完了させる専用 worker/API を新設すること。
- server の既存 p650 image-only / p500 fallback 実装を変更すること。
- 過去 artifact や state history を削除・切詰めること。
