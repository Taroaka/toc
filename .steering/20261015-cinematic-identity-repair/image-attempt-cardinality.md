# Image attempt cardinality

## Requirement and evidence
A scene-image request failed with two distinct imageGeneration item IDs. Its exact native turn record shows one terminal failed item without savedPath, followed by one completed item with a saved image. The current guard counts failed no-output attempts as candidate outputs, rejecting an otherwise uniquely bound image. Other scene requests remain active and must not be restarted while healthy.

## Design and tasks
- Collapse events by stable native item ID first, retaining the latest state.
- Exclude only terminal failed/canceled attempts that have no saved output from candidate-output cardinality. Keep full transcript evidence. Completed output, failed-with-output, or unfinished additional candidates remain ambiguous and must fail closed.
- Keep request/turn/item/reference/destination provenance; never scan shared image directories or choose the latest of multiple real images.
- Add tests reproducing failed-no-output then one completed output; negative tests for two completed outputs, a failed item with a path, and another unfinished candidate. Preserve transcript/thread ID on cardinality errors for diagnostics.
- Verify related runtime/provenance tests. Do not restart the running batch; deploy and resume only after it actually stops, retaining the 20 assets and all valid scene outputs.

## Verified fix, deployment deferred until active work ends

The exact failed native turn is 01a13f25-dc93-7c21-adf6-4f8ef71e760d in thread 01a13f25-db64-7c30-8b81-4e102ba52d18. Its first image item exec-dcb39b8c-9ae0-4393-8842-fb52dd53c740 is failed with no output; the second exec-db46fde3-50b3-4b94-b9ee-d20464352598 completed with a saved path. Five new regression variants fail before the change and pass afterward. Related Codex transport/image-provenance/request-snapshot suites: 59 passed. Local review confirms events collapse by stable ID before filtering, failed-with-output and unfinished competitors remain ambiguous, multiple real images remain rejected, and full transcript/thread diagnostics survive an ambiguity error. No runtime/provenance fallback or retry budget changes. The ongoing batch must finish before restart; keep all valid assets and shot outputs on the next image_only resume.

## Batch stopped; deploy and bounded retry

The original batch finished at 21:50:35 JST: 51 scene outputs completed, 3 failed by the same no-output-attempt cardinality bug. No production Codex subprocesses remain. Exact native records for all three failures show one failed no-output attempt followed by one completed output. Before restart, all 20 asset hashes remain unchanged and hashes of all 71 canonical PNGs (20 assets + 51 scenes) were captured in preserved-images-before-cardinality-retry.json. The verified runtime patch will be loaded by the supported restart; use one frontend image_only retry and prove existing output hashes remain unchanged.

## Final outcome

After restart and frontend image_only resume 4e1250446e7742b3966ae03fde9ad73c, exactly 3 missing items were generated and 51 valid scene outputs were skipped. The last retry item completed at 21:55:48 JST. Normal frontend-create p680 validation passed; the job completed at 21:56:16. Canonical p680 is done, all 74 PNGs exist, and every one of the 71 before-retry hashes is unchanged. Automation was paused after verified completion. See completion.md and frontend-p680-complete.png.
