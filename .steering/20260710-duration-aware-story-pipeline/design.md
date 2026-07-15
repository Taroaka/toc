# Duration-aware story pipeline design

## Architecture

目標尺を request-local な単一 contract として扱う。frontend、backend request model、frontend runner、artifact writers、stage evaluators、audio/final-video gates が独自の既定値や式を持たないよう、Python 側に純粋な duration contract / audit module を置く。

```text
Frontend duration selector
  -> POST /api/image-gen/runs/create target_duration_seconds
  -> backend create command
  -> frontend runner duration plan
  -> research -> semantic review gate
  -> story -> semantic review gate
  -> scene/cut/script/manifest budgets
  -> p740 shared audio audit
  -> render/final-video shared audit
```

## Shared duration contract

共通 module は最低限、次を提供する。

- target の parse / default / 300〜1200 validation
- `minimum_effective_seconds = target * 0.8`
- `minimum_scene_count = ceil(target / 40)`
- `minimum_cut_count = ceil(target / 12)`
- `minimum_narration_seconds = ceil(target * 0.70)`
- measured seconds に対する lower-bound-only 判定
- manifest cut timeline の audit result
- render timeline / final media duration の audit result

audit result は `target_seconds`、`minimum_seconds`、`actual_seconds`、`ratio`、`status`、`measurement_layer`、`evidence` を持つ。layer 間の秒数は加算しない。

## Propagation

- React state に target duration を追加し、通常作成と storyboard 作成の両 request に含める。
- backend request model の `target_duration_seconds` は default 300 と整数 300〜1200 validation を持つ。
- create job command は runner に target を明示的に渡す。
- state と各 authoring artifact の metadata に同じ target を書く。
- 後段は metadata の値を読み、独自の固定 300 秒を生成しない。

## Planning

既存の 8 scene variant は 5 分の最低量としてのみ利用できる。長尺では target-derived scene plan まで拡張し、同じ scene のコピーで数合わせしない。cut count は scene target と既存 cut criticality contract の双方を満たす大きい方を採用する。

narration は pre-TTS では推定読み上げ秒、post-TTS では実 audio 秒を source of truth とする。文字数だけを最終尺として扱わない。

## Semantic gates

既存 semantic review transport / rubric / artifact conventions を再利用し、research と story を正式な frontend authoring stage に追加する。固定 JSON の `passed` materialization を禁止する。

- production: Codex app-server review result と deterministic structural preflight の両方を必要とする。
- tests: app-server result は mock し、passed / failed / transport error を網羅する。
- failed review は既存 repair loop が扱える場合だけ repair へ進み、最終 pass がなければ cut を作らない。
- 外部 source fidelity は rubric に含めない。

## Audio and media audit

audio timeline は cut ごとに一つの effective duration を選ぶ。

1. narration cut: 対応する音声ファイルの実測値。
2. intentional silence cut: `intentional: true`、`confirmed_by_human: true`、non-empty `kind` / `reason` を持つ場合だけ manifest の明示 duration。
3. narration が必要なのに音声がない cut: not-ready / fail。

video timeline は scene に render units があれば unit 合計で source cut video duration を置換し、なければ cut 合計を使う。audio / video は並列 layer なので加算せず、pre-render actual は完全な両 timeline の `min(audio, video)` とする。final video はさらに別 audit layer とし、完成 media を直接測る。p740 completion、CLI gate、frontend video readiness は同じ lower-bound-only audit status を参照する。

## Compatibility

- request field 未指定は 300 秒。
- 既存 run は書き換えない。
- historical artifact parser は target 欠落時に既存 fallback を読める。
- API endpoint 名と polling contract は維持する。
- 画像生成、動画生成、cut_contract の既存 gate は弱めない。
- p680 から p900 までの one-click 自動継続は追加しない。

## Likely files

- `server/web/src/main.tsx`
- `server/image_gen_app.py`
- `scripts/toc-immersive-frontend-run.py`
- `scripts/toc-create-run-headless.py`
- `scripts/check-audio-duration-gate.py`
- `scripts/sync-manifest-durations-from-audio.py`
- `toc/stage_evaluator.py`
- new shared duration module under `toc/`
- focused tests under `tests/`
- `workflow/state-schema.txt` and duration-related docs/templates when contract changes require it

## Risk controls

- 汚れた worktree の変更を revert / reformat しない。
- target layer の秒数を足して見かけ上 pass させない。
- 既存の `duration_seconds` metadata だけを無条件に信用せず、音声がある場合は実測する。
- AI review unavailable を passed にしない。
- long-form の数合わせで同一 scene / narration を機械的に複製しない。
- paid image/video/TTS calls を verification に含めない。
