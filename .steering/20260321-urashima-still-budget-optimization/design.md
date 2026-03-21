# Design: Urashima still budget optimization

## Decision Rule

For this run, a dedicated still stays only if the cut is serving as one of the following:

1. A reusable location anchor with visual identity that spans later cuts.
2. A hero-object lock frame, especially for `tamatebako`.
3. A character-state lock frame that cannot be inferred cleanly from adjacent motion.

All other cuts should be demoted as follows:

- `reuse_anchor`: when the cut stays in the same physical space/state and can inherit continuity from a nearby anchor.
- `no_dedicated_still`: when the cut is primarily a transition beat, a mood beat, or a motion bridge between two stronger anchors.

## Planned Demotions

- Transition into the portal / palace / return path should rely more heavily on motion chains than new stills.
- Ryugu exploratory cuts should keep enough anchors to sell spatial variety, but not assign a dedicated still to every connective beat.
- Late-village and post-transformation beats should collapse around a smaller number of tableau anchors.

## Verification

- Update the run manifest only.
- Re-run `python scripts/verify-pipeline.py --run-dir output/浦島太郎_20260208_1515_immersive --flow immersive --profile fast`.
- Use the refreshed `run_report.md` / `eval_report.json` only as derived outputs; do not hand-edit them.
