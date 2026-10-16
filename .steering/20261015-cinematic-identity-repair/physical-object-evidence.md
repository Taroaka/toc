# 2026-10-15 11:20: typed physical symbols and opening-state evidence

Scene_03 is blocked by physical_source_required: its source_entity points to research.story_materials.symbols_and_themes[1].item. That record explicitly has kind=object and is an actual prop, but the resolver bans every pointer containing symbols_and_themes, including typed physical records used elsewhere by the profile adapter. Its quoted usage event is later than opening cuts even though the prop is explicitly in scene.start_state.objects.

Permit only object requests pointing to the item field of an explicitly kind=object research record; themes/motifs/meaning fields and character requests remain rejected. If a physically grounded object has later usage evidence but is unambiguously listed in this same scene's opening objects, add the exact opening-state quote/pointer as derived corroborating evidence at rank zero. Keep all original evidence, fail on ambiguous/absent opening records, and do not use end-state or future facts for early appearance. No new story facts or title-specific rules. Keep retained repair counters and validated stages.

## Verified additional inconsistency

After the typed object fix, the saved candidate exposed previous_end_reference_missing: a later shot requested inheritance from the previous end state while end_view was intentionally omitted. Runtime now preserves the authored previous end_state in source_grounding and uses an actual end-image as an optional spatial anchor only when it exists. First-shot previous_end and unbound transformation result references still fail. No ending frame is invented.

## Verification

New typed-object tests failed before implementation; after fixes, related shot/object/repair/projection/resume/compiler suites: 180 passed, 1 known baseline test deselected, 12 subtests passed. A read-only replay of accepted scenes 1/2 plus the original scene_03 candidate now produces no projection diagnostics and retains the authored scene data and 12 consumed repair attempts. Theme/motif/meaning paths and future-only presence remain rejected. Source-opening corroboration uses one exact source-state quote, never an inferred event. Pointer docs and whitespace checks pass. Local review retained all unrelated changes.

## Same-beat intermediate variant

A normal resume exposed an additional semantic validation issue missed by the earlier projection-only dry check: scene_03 cut 4 inherits the state produced by cut 3, while both legitimately belong to the same source beat. The strict beat-rank-only >= check rejected that intermediate state. The validator now requires an earlier cut covering the transition beat, the same visible asset, an explicit continuous previous-cut link, and exact matching end/start state IDs and facts before permitting same-beat reuse. First-cut/premature use and mismatched state handoffs remain rejected. A new regression failed before the fix and now passes; the actual saved scene now passes BOTH validate_scene_direction and projection_diagnostics.

Focused p400/object/shot/repair verification after this change: 117 passed, 1 known baseline test deselected. Pointer docs and diff checks passed.

## Confirmed successful continuation

Additional asset-state-variant and shot-runtime tests: 34 passed. At 2026-10-15 11:31 JST, server restart health checks passed and Computer Use resumed the same run once. Job 16cf1c885b0e4b17b20e93662f5c66a2 is running. Scenes 1, 2 AND 3 now have accepted receipts; scene 4 authoring continues. P420 repair attempts remain 12, and all three upstream byte hashes are unchanged. UI evidence: frontend-resumed-1131.png. Monitoring remains active until normal p680 output validation completes.
