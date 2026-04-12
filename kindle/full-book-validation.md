# Kindle Full-Book Runner Validation Matrix

This document is the operator runbook for validating `kindle/run-kindle-full-book.sh` and `kindle/run-kindle-full-book.py`.
It is written against the current full-book runner behavior, including `manifest.json`, `review_queue.md`, retry handling, quality flags, and end-of-book confirmation logic.

## Required Artifacts

Every validation run should leave a consistent artifact bundle:

- `transcript.txt`: one block per completed transcript page.
- `session.md`: run summary plus recent event trail.
- `run_state.json`: canonical page records, `quality_status`, `quality_flags`, and `review_items`.
- `manifest.json`: top-level summary, counts, status, and artifact paths.
- `review_queue.md`: operator queue for pages that need inspection.
- `pages/`: exported page images.
- `vision/`: one `.txt` result and one `.log` per completed page.

Treat `manifest.json` and `review_queue.md` as first-class outputs. A run is not fully validated if they are missing or inconsistent with `run_state.json`.

## Status Expectations

Use the runner's actual stop behavior when judging results:

- `completed`: run reached the end and produced no review items.
- `partial`: run hit a safety cap, or reached the end with review items, or stopped in a recoverable but incomplete state.
- `interrupted`: operator stopped the run.
- `failed`: run aborted unexpectedly before reaching a clean stop.

## Validation Matrix

| Scenario | Setup | Run | Expected artifacts | Pass criteria | Fail criteria | What to inspect |
|---|---|---|---|---|---|---|
| Smoke: 5-page happy path | Open a stable Kindle reader tab on a readable book. Use a fresh run directory. | `./kindle/run-kindle-full-book.sh --run-dir <run-dir> --max-pages 5` | Full bundle including `manifest.json` and `review_queue.md` | Run stops at the safety cap after 5 completed pages. `run_state.json.completed_pages` is `5`. `manifest.json.completed_pages` is `5`. `status` is `partial` because the cap is intentional, not because the run is broken. | Missing bundle files, fewer than 5 completed page records, or `failed` status on a clean smoke run. | `run_state.json.pages[*]`, `manifest.json.completed_pages`, `manifest.json.review_items`, `review_queue.md`, `session.md` stop reason. |
| Medium-length run: 30 pages | Use a longer book with enough pages to exercise repeated export, vision, and page-turn loops. Use a fresh run directory. | `./kindle/run-kindle-full-book.sh --run-dir <run-dir> --max-pages 30` | Same full bundle, with 30 exported pages and 30 vision outputs | Run stops at the safety cap with 30 completed pages. Page sequence stays stable across the run. Any review items that appear are visible in both `run_state.json` and `review_queue.md`. | Silent page duplication, silent page skips, manifest counts that do not match state, or missing review output when a gate fires. | `run_state.json.completed_pages`, `pages[*].kindle_page_number`, `pages[*].image_sha256`, `pages[*].quality_flags`, `manifest.json.review_items`, `review_queue.md` sections. |
| Full-book end-to-end | Open the book at the first unread page and let the runner go to the end without a cap. | `./kindle/run-kindle-full-book.sh --run-dir <run-dir>` | Full bundle for the whole book | Runner reaches the end without manual intervention after launch. Final status is `completed` if there are no review items, or `partial` if the book finished but review gates fired. `manifest.json` and `review_queue.md` reflect the same outcome. | Runner loops on the last page, overshoots the end, or reports a clean finish while review files disagree. | Final `session.md` events, tail of `transcript.txt`, tail of `run_state.json.pages[]`, `manifest.json.status`, `manifest.json.review_items`, `review_queue.md`. |
| Failure drill: interrupted run and resume | Start a normal run, stop it after several completed pages, then reopen the same book on the last completed or next unread page. | First run: start normally and stop with `Ctrl-C`. Resume: `./kindle/run-kindle-full-book.sh --resume --run-dir <same-run-dir>` | Same bundle reused across both launches | First run ends as `interrupted`. Resume run preserves existing pages and continues from the right place without rewriting completed pages. Final bundle remains internally consistent. | Resume starts over, overwrites completed pages, or fails alignment without telling the operator which page is expected. | `run_state.json.resume_mode`, `last_completed_page_index`, `last_completed_kindle_page`, `session.md` interruption and resume events, `manifest.json.completed_pages` before and after resume. |
| Failure drill: transient vision failure and retry | Use a controlled setup where one `codex exec --image` call is slow or flaky, but the environment recovers. | Run the normal command and watch one page through retry behavior. | Prior completed pages remain intact. If retry succeeds, the current page gets normal outputs. If retry exhausts, the run stops without corrupting prior outputs. | Retry events appear in `session.md`, and prior checkpoints remain durable. A successful retry yields a normal page record. An exhausted retry leaves the run in `failed` without pretending the page succeeded. | Silent retry loops, overwritten prior pages, or a failed Codex call recorded as a completed page. | `session.md` retry events, latest `vision/*.log`, `run_state.json.completed_pages`, and whether the page record exists only after a real transcription result. |
| Gate path: short-transcription handling | Include at least one sparse page such as a chapter title page, section divider, or otherwise short but readable page. | Run enough pages to include the sparse page. | Standard page outputs plus a review entry for the flagged page | The page is kept in `transcript.txt` as a completed page. The matching page record shows `quality_status: flagged` with `short_transcription` for a merely short page, or `quality_status: failed` with `very_short_transcription` for an extremely short page. `review_queue.md` records the same reason with `warn` or `blocker` severity to match. | Sparse output is silently accepted with no gate, or the runner collapses `short_transcription` and `very_short_transcription` into the wrong severity. | `run_state.json.pages[*].quality_status`, `quality_flags`, `review_queue.md` reasons `short_transcription` and `very_short_transcription`, `manifest.json.review_items`, and the page text in `transcript.txt`. |
| Gate path: repeated-image or duplicate-page suspicion | In a controlled drill, force the reader to stay on the same page for two captures, or use a resume scenario that intentionally reopens on the same already-captured page. | Run until the duplicate-like condition is recorded. | Standard bundle plus review output for the affected page | The affected page record is retained but flagged. `quality_flags` should include `repeated_image_sha256` and may also include `duplicate_kindle_page_number`. `review_queue.md` contains the page with evidence pointing to the repeated image or page number. | Same-page capture is silently accepted as normal progress, or the evidence only appears in one file and not the others. | Adjacent page records in `run_state.json`, `image_sha256`, `kindle_page_number`, `quality_flags`, `review_queue.md`, and the corresponding two screenshots in `pages/`. |
| Gate path: skipped-page suspicion | In a controlled drill, force the reader to advance an extra page between captures, or validate a real run where Kindle jumped forward unexpectedly. | Run until the page-gap condition is recorded. | Standard bundle plus review output for the affected page | The run records the page and flags it instead of hiding the jump. `quality_flags` includes `kindle_page_gap`. `review_queue.md` adds a warn-level item telling the operator to compare this page against the previous page. | The page-number jump is not surfaced, or the runner invents missing pages instead of flagging the suspicion. | Adjacent `kindle_page_number` values in `run_state.json.pages[]`, the relevant `quality_flags`, the matching `review_queue.md` entry, and surrounding transcript blocks. |
| Gate path: end-of-book ambiguity on page-turn failure | Use the final page or near-final page, then induce a page-turn failure. Run both a strong-signal case and a weak-signal case if possible. | Run normally until page turn fails near the end. | Standard bundle plus either a confirmed-end event or a `page_turn_failed` review item | Strong-signal case: the runner stops with a `session.md` event like `Confirmed end-of-book after page-turn failure with signals: ...` and does not add a blocker `page_turn_failed` review item. Weak-signal case: the runner stops `partial`, adds a blocker `page_turn_failed` item, and tells the operator to reopen on the next unread page. | A single weak signal is treated as confirmed end-of-book, or a strong multi-signal end state is downgraded to an ordinary page-turn failure. | `session.md` end-of-book event, triggered signal names, `manifest.json.status`, presence or absence of `page_turn_failed` in `review_queue.md`, and the final two page records in `run_state.json`. |

## Operator Checklist

Before each run:

1. Confirm Chrome is already running with remote debugging.
2. Confirm the target book is open in the active Kindle reader tab.
3. Confirm the run directory is new, or is an intentional `--resume` target.
4. Decide whether the run is a smoke, medium, full-book, or gate/failure drill before launch.

During the run:

1. Watch `session.md` for page-by-page progress and retry events.
2. Watch `run_state.json.completed_pages` for steady growth.
3. Watch `review_queue.md` after each checkpoint if you are deliberately triggering a gate.
4. Watch `vision/*.log` when a page is slow, partial, or suspiciously short.

After the run:

1. Compare `run_state.json.completed_pages` with the number of `=== Page N ===` blocks in `transcript.txt`.
2. Compare `manifest.json.completed_pages`, `partial_pages`, `failed_pages`, and `review_items` against `run_state.json`.
3. Confirm `review_queue.md` either says `No review items.` or has one section per flagged page.
4. Confirm `session.md` ends with the same stop reason implied by `manifest.json.status`.

## Output Inspection Rules

Use these rules to decide whether a run is actually acceptable:

- `transcript.txt` should have sequential transcript page headers with no missing completed blocks.
- `run_state.json.pages[]` should contain one record per completed page, with `page_index`, `kindle_page_number`, `image_sha256`, `vision_path`, `vision_log_path`, `vision_status`, `quality_status`, and `quality_flags`.
- `run_state.json.review_items` should explain every page that needs inspection.
- `manifest.json.review_items` should equal the number of review items in `run_state.json`.
- `review_queue.md` should reflect the same flagged pages and reasons the state file reports.
- A flagged page should remain in the transcript unless the run failed before that page was checkpointed.
- Duplicate-like signals should show up as `repeated_image_sha256` and often `duplicate_kindle_page_number`.
- Skip suspicion should show up as `kindle_page_gap`.
- Short readable pages should show up as `short_transcription` with a flagged quality status, while extremely short pages should show up as `very_short_transcription` with blocker severity.
- Confirmed end-of-book on page-turn failure should be visible in `session.md` with the triggered signals.

## Coverage Standard

Treat validation as complete only when all of these have been exercised at least once:

- One 5-page smoke run.
- One 30-page medium run.
- One full-book run to the end.
- One interrupted run that resumes cleanly.
- One transient vision retry drill.
- One short-transcription gate case.
- One repeated-image or duplicate-page gate case.
- One skipped-page gate case.
- One end-of-book ambiguity drill covering confirmed-end or ambiguous-stop behavior.
