# Orchestration Artifacts & Logging（正本）

run を再開・診断できるように、source identity、stage inputs、outputs、state、request、
provider provenance、ordinary validation の結果を記録する。ログは production quality certificate
ではない。

## 出力構成

```text
output/<topic>_<timestamp>/
  state.txt
  state.current.json
  run_status.json
  p000_index.md
  logs/
    orchestration/
    grounding/
    validation/
    providers/
```

- `state.txt`: append-only canonical history
- `state.current.json`: state history からの derived view
- `run_status.json`: stage/slot/artifact の derived projection
- `p000_index.md`: 人間向け navigation
- `logs/orchestration/`: create input、L2 progress、supervisor result
- `logs/grounding/`: required docs、templates、inputs の source/readset
- `logs/validation/`: schema/reference/request/output の ordinary diagnostics
- `logs/providers/`: provider request/response identity と provenance

## Stage log shape

```json
{
  "job_id": "JOB_YYYY-MM-DD_0001",
  "stage": "SCENE_IMPLEMENTATION",
  "input": {
    "paths": ["script.md", "video_manifest.md"],
    "sha256": ["sha256:<hash>"]
  },
  "output": {
    "paths": ["assets/scenes/scene_01_cut_01.png"],
    "sha256": ["sha256:<hash>"]
  },
  "validation": {
    "schema": "passed",
    "references": "passed",
    "provenance": "passed"
  },
  "started_at": "ISO8601",
  "completed_at": "ISO8601",
  "duration_seconds": 0.0
}
```

Validation values describe concrete checks and may be `passed|failed|skipped` when a check is not
applicable. They do not represent a subjective score.

## Supervisor result

Each L2 bucket writes `logs/orchestration/pXXX.supervisor_result.json` with bucket, status,
completed slots, required artifact paths, state keys, ordinary output inventory, and next bucket or
blocked reason. L1 only checks these fields and file existence.

## Provider provenance

Before each provider call, log generation job ID, item ID, turn ID, prompt/source hashes, ordered
references and bytes hashes, saved path, destination, provider/model/settings. After the call, log
response item identity and output content hash. Copy output only when the complete binding matches.

## Privacy and safety

Do not write secrets, tokens, or full sensitive environment values to logs. Paths are run-relative where
possible. Compliance logs can store actor and publication decisions under their own schema.

## References

- docs/data-contracts.md
- docs/orchestration-and-ops.md

