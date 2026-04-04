# Stage Evaluator Expansion Design

## Reuse Strategy

`scripts/verify-pipeline.py` の stage check 関数を evaluator scripts から直接呼ぶ。

## New Scripts

- `scripts/review-research-stage.py`
- `scripts/review-script-stage.py`
- `scripts/review-manifest-stage.py`
- `scripts/review-video-stage.py`

各 script は:

1. run dir を受け取る
2. 対応 stage の verify helper を呼ぶ
3. markdown report を生成する
4. `state.txt` に evaluator summary を append する
5. `run_status.json` を自動更新する

## State Contract

新規 key:

- `eval.research.status`
- `eval.research.findings`
- `artifact.research_review`
- `eval.script.status`
- `eval.script.findings`
- `artifact.script_review`
- `eval.manifest.status`
- `eval.manifest.findings`
- `artifact.manifest_review`
- `eval.video.status`
- `eval.video.findings`
- `artifact.video_review_report`

`status` は `approved|changes_requested`

## Report Format

各 report は:

- stage
- score
- findings count
- failed check ids
- short detail list

## Scope

- manifest evaluator は scene/cut contract の review stage として扱う
- research/story の generator 側 multiagent 実装までは広げず、まず evaluator 実行基盤と state 反映を作る
