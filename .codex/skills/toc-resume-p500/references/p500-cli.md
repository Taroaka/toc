# Manual p500 Resume

Use only for the canonical p500 route, explicit reset, or materialization diagnostics. The resume API already performs plan/apply when it starts its own p500 worker; do not duplicate that work.

## Dry run

For manual p500 diagnostics/execution, with no API-started job already active, run:

```bash
python scripts/resume-from-p500.py \
  --run-dir "output/<topic>_<timestamp>" \
  --checkpoint-id "<unique-checkpoint-id>"
```

The command must pass the fresh p400 structural checks before it produces a plan.
The continuation path rematerializes p400 request artifacts and passes the
structural integrity checks before any p500 request/provider work.
Inspect the JSON and confirm:

- `preserved_files` includes `research.md`, `story.md`, `visual_value.md`,
  `script.md`, and `video_manifest.md`
- `downstream_files` contains only p500+ requests, reports, generated media, and
  derived outputs
- `checkpoint_dir` is inside the same run under `logs/resume/p500/`
- record the returned `checkpoint_id` and `plan_token`; apply must use both
  exact values

Stop on any upstream canonical file in `downstream_files`. Fix the classifier
before applying; never work around it with manual deletion.

## Apply the intended mode

Reset only:

```bash
python scripts/resume-from-p500.py \
  --run-dir "output/<topic>_<timestamp>" \
  --checkpoint-id "<dry-run checkpoint_id>" \
  --plan-token "<dry-run plan_token>" \
  --apply
```

Run materialization diagnostics without media generation:

```bash
python scripts/resume-from-p500.py \
  --run-dir "output/<topic>_<timestamp>" \
  --checkpoint-id "<dry-run checkpoint_id>" \
  --plan-token "<dry-run plan_token>" \
  --apply \
  --continue-to p650 \
  --materialize-only
```

Normal frontend image retry:

```bash
python scripts/resume-from-p500.py \
  --run-dir "output/<topic>_<timestamp>" \
  --checkpoint-id "<dry-run checkpoint_id>" \
  --plan-token "<dry-run plan_token>" \
  --apply \
  --continue-to p680
```

The CLI holds the same `create_resume.lock` used by frontend create/resume and
single/bulk image generation. It also rejects persisted bulk jobs that are
still `queued` or `running`. If another process owns the run, report the
conflict and wait; do not remove lock files.

After execution, verify checkpoint.json, quarantined files, preserved upstream hashes, and the worker status. For normal media retry, also verify strict p680 completion. For a diagnostic materialization run, report only that diagnostic result.
