# Kindle Full-Book Output Contract

This document defines the run directory contract for full-book Kindle for Web transcription runs. It is written for the main runner and for operators who need to judge whether a run is complete, partial, or unsafe to trust.

The contract is intentionally concrete. If a future implementation cannot satisfy one of the rules below, it should mark the run `partial` or `failed` rather than silently pretending the output is clean.

## Scope

This contract applies to the full-book path that starts from an already open Kindle reader tab and produces one durable checkpoint per completed page.

It covers:

- artifact layout
- page-level quality gates
- run-level status rules
- `review_queue.md` content
- progress and session logging
- operator inspection order

It does not cover library selection or browser login.

## Canonical Run Artifacts

Every full-book run should write these artifacts inside one run directory.

| Artifact | Status | Purpose |
|---|---|---|
| `pages/0001.png` ... `pages/<n>.png` | Required | One exported reader image per accepted transcript page. These are the visual source of truth for each page checkpoint. |
| `vision/0001.txt` ... `vision/<n>.txt` | Required | The raw per-page vision transcription output. One text file per page. |
| `vision/0001.log` ... `vision/<n>.log` | Required | The per-page Codex invocation log, including failures, retries, and timeouts. |
| `transcript.txt` | Required | The assembled page-by-page transcript. This is the user-facing text output. |
| `session.md` | Required | A live run narrative with current status, progress, retries, and stop reason. |
| `run_state.json` | Required | Machine-readable checkpoint state for resume, validation, and duplicate/skipped-page detection. |
| `manifest.json` | Required | Compact summary of the run, the reader, page counts, status, and artifact pointers. |
| `review_queue.md` | Required | Human review list for pages or run events that need attention before the transcript is trusted. |

The runner may also keep stdout/stderr logs, but they are not a substitute for these artifacts.

## Required `run_state.json` Contents

`run_state.json` should be append-friendly and checkpoint-safe. At minimum it must carry:

- `status`
- `completed_pages`
- `last_completed_page_index`
- `last_completed_kindle_page`
- `reader.url`
- `reader.title`
- `reader.current_page`
- `reader.total_pages`
- `pages[]`
- `events[]`

Each `pages[]` entry should include at least:

- `page_index`
- `kindle_page_number`
- `image_path`
- `image_sha256`
- `vision_path`
- `vision_log_path`
- `vision_status`

Recommended extra fields for quality gating:

- `quality_status` with values `accepted`, `flagged`, or `failed`
- `quality_flags` as a list of short codes
- `review_queue_item` or an equivalent pointer for operators

## Run Status Model

Use these status values only:

- `running`: the run is active and checkpointing normally.
- `completed`: the runner reached the end of the book and no unresolved quality gates remain.
- `partial`: the run made useful progress, but at least one page or stop condition needs human review.
- `interrupted`: the process stopped intentionally or externally before a final completion decision.
- `failed`: the run could not continue safely or the state became unreliable.

Status rules:

- `completed` requires all completed pages to pass quality gates and `review_queue.md` to be empty.
- `partial` is the default when the run is usable but not fully trusted.
- any review item keeps the run `partial`, even if the operator believes the issue is probably benign.
- `failed` is reserved for unrecoverable conditions such as repeated export failure, reader loss that cannot be recovered, state corruption, or repeated Codex failure on the same page.
- `interrupted` is for a stop before a final quality decision, usually `Ctrl-C` or process termination.

## Page-Level Quality Gates

A page should be checkpointed only after the image, transcription, and page metadata are all available.

| Gate | Threshold | Action |
|---|---|---|
| Empty or failure text | Output is blank, whitespace-only, or exactly `[[vision transcription failed]]` | Mark the page `failed`. If the run can continue, keep the run `partial` and queue the page for review. |
| Explicit partial marker | Output starts with `[[partial vision transcription]]` | Mark the page `partial` and add it to `review_queue.md`. |
| Suspiciously short transcription | Normalized body text is under 120 Unicode characters and the page is not clearly a title page, chapter divider, copyright page, or other intentionally sparse page | Mark the page `partial`. If multiple short pages occur back-to-back, escalate the run to `partial` even if individual pages are readable. |
| Very short transcription | Normalized body text is under 40 Unicode characters | Treat this as a hard flag. The page should not be counted as clean unless the page is intentionally sparse and the operator confirms it. |
| Repeated transcription | The normalized transcription exactly matches the previous completed page, or matches an earlier completed page without an explicit duplicate-page note | Mark the page `partial` and queue it for comparison. |
| Repeated image | `image_sha256` matches the previous completed page while the Kindle page number advanced | Mark the page `partial`. This is a likely duplicate export or page-turn failure. |
| Kindle page did not advance | The reader page number does not advance after a normal page-turn attempt | Mark the run `partial` unless end-of-book has also been confirmed. |
| Page number jump | The Kindle page number jumps by more than 1 between consecutive accepted pages | Queue the page pair for review. If the jump is not explained in the session log, keep the run `partial`. |
| Vision execution failure | The Codex call times out, exits non-zero, or produces no output file | Mark the page `failed`. Keep prior checkpoints intact. |

## End-of-Book Rules

End-of-book detection should use more than one signal.

The runner may mark the run `completed` only when:

- the reader indicates the next page is unavailable or disabled, or
- a second page-turn attempt confirms the reader is already at the end, and
- the final accepted page passes the page-level gates.

If the last visible page is duplicated, the page number stops advancing, or the final page is suspiciously short without an explicit reason, the run should be `partial` rather than `completed`.

## When To Mark `partial`

Mark the run `partial` when any of these happen:

- at least one page is `partial` or `failed`, but the run still produced usable output
- duplicate-page, skipped-page, or repeated-image detection fires
- the run hits a safety cap such as `--max-pages`
- the run ends at the book boundary but at least one page is unresolved
- the operator would need to inspect `review_queue.md` before trusting the transcript

Do not hide these cases behind `completed`.

## When To Mark `failed`

Mark the run `failed` when the runner cannot keep producing trustworthy checkpoints, for example:

- the active reader tab is lost and cannot be reattached
- the page export path fails repeatedly for the same page
- Codex transcription fails repeatedly for the same page
- `run_state.json` cannot be written or reloaded
- the run state and on-disk artifacts disagree in a way that makes resume unsafe

`failed` should mean the run should be resumed only after the operator has fixed the environment or created a new run directory.

## `review_queue.md` Contract

`review_queue.md` is the human triage file. It should contain one entry per issue, sorted by `page_index`.

Each entry should capture:

- `page_index`
- `kindle_page_number`
- `severity` (`info`, `warn`, `blocker`)
- `reason`
- `evidence`
- `suggested_action`
- `artifact_links`

Expected item shape:

```md
## Page 0012 | Kindle page 27 | warn

- reason: suspiciously short transcription
- evidence: normalized text length 54; previous page length 1487
- suggested_action: compare screenshot against `vision/0012.txt`; retry if text is truncated
- artifact_links:
  - `pages/0012.png`
  - `vision/0012.txt`
  - `vision/0012.log`
```

Current intended behavior:

- `artifact_links` should point to repo-relative paths inside the same run directory.
- one issue may reference the same page more than once if the reasons are materially different, but the default is one item per page.
- if `review_queue.md` has any item at all, the run remains `partial`.

Put these kinds of items in the queue:

- partial or failed page transcriptions
- suspiciously short pages
- repeated transcriptions
- repeated images
- skipped-page suspicion
- end-of-book ambiguity
- resume mismatch
- missing page image or vision log
- any page that a human should compare against the screenshot before trusting

Do not put routine accepted pages into `review_queue.md`. It is a triage file, not a transcript index.

## `manifest.json` Contract

`manifest.json` should be the compact machine-readable summary of the run. It is the fastest way for automation to answer: “What happened, where is the output, and is it safe?”

It should be explicit, but small. Treat it as a summary index, not as a second copy of `run_state.json`.

It should summarize:

- run identity: `run_dir` and a stable run id or basename
- timestamps that the runner already knows, such as `created_at` and `updated_at`
- reader title and URL
- total pages exported
- completed pages
- final status
- count of partial and failed pages
- count of review items
- pointers to `transcript.txt`, `session.md`, `run_state.json`, and `review_queue.md`

Realistic producer guidance:

- do not require fields that the runner does not already track durably
- prefer copying summary values from `run_state.json` instead of recomputing them
- avoid per-page detail here; that belongs in `run_state.json`

If the implementation adds more metadata, keep this file small and stable.

## `transcript.txt` Contract

`transcript.txt` should remain strictly page ordered.

Rules:

- one section per accepted page
- sequential page headers with no gaps in accepted pages
- no hidden edits to earlier pages after they have been checkpointed
- if a page is partial or failed, the transcript must preserve the sentinel text so the issue is visible in the assembled output

The transcript is user-facing. It should not be used to hide page quality problems.

## `session.md` Contract

`session.md` is the live operator narrative. It should let someone understand the run without opening every page artifact.

It should include:

- run directory
- target reader URL
- current status
- resume mode
- current and last completed page numbers
- reader title and total pages when known
- recent events, newest last

Required event types:

- start
- connect
- export start / export ok / export failed
- vision start / vision ok / vision partial / vision failed
- checkpoint saved
- page turn ok / page turn failed
- duplicate detected
- safety cap reached
- end-of-book confirmed
- run marked partial / completed / failed / interrupted

Logging cadence:

- emit a progress line to stdout for every page phase transition
- append a session event after each page checkpoint
- flush the live state after every accepted page and after every failure

## Progress Logging Expectations

The runner should make it obvious where it is in the book.

Progress output should include:

- transcript page index
- Kindle page number
- current status of export, vision, and page turn
- whether the page was accepted, partial, failed, or queued for review
- checkpoint counts so an operator can compare progress against `run_state.json`

Good example shape:

```text
[page 12/384] export ok, vision partial, checkpoint saved, review queued
```

The exact wording can vary, but the meaning should not.

## What Operators Should Inspect

When a run is not obviously clean, inspect in this order:

1. `session.md` for the stop reason and recent page events.
2. `run_state.json` for the final status, page count, and tail of `pages[]`.
3. `review_queue.md` for pages that need human judgement.
4. `transcript.txt` for page order, duplicate tails, and sentinel text.
5. The last few `pages/*.png` images and the matching `vision/*.log` files for any queued page.

If the run is `partial`, the operator should verify whether the issue is local to one page or systemic before reusing the run directory.

## Acceptance Summary

A full-book run is safe to hand off only when all of these are true:

- `run_state.json.status` is `completed`
- `review_queue.md` is empty
- `transcript.txt` page order matches `run_state.json.pages[]`
- `session.md` ends with a clear completion reason
- the final page is not an accidental duplicate

If any of those checks fail, the run should be treated as `partial` until a human clears it.
