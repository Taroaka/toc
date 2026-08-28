# ATTEMPTS

| Time | Attempt | Evidence | Result | Next Adjustment |
| --- | --- | --- | --- | --- |
| 2026-08-26 | Initial diagnosis from Cinderella retries | `run_status.json`, semantic repair report, P400 critic reports | Repair changes canonical scenes but leaves stale cut/reference/timeline projections before P400 refresh | Add failing tests at the repair reconciliation boundary |
| 2026-08-26 | Added focused reconciliation tests before implementation | `PYTHONPATH=.. python -m unittest test_semantic_repair_reconciliation` | RED: `toc.semantic_repair_reconciliation` did not exist | Implement pure deterministic reconciler |
| 2026-08-26 | Implemented event/cut projection, variant ancestry replacement, fail-closed unknown references, and pre-P400 integration | 4 new tests plus existing safe-order test | GREEN: 5 tests | Validate against real Cinderella artifacts |
| 2026-08-26 | Ran reconciler in memory against Cinderella | `source_event_preservation=0`, `timeline_states_complete=0` | Partial: found initial replacement was document-global and would corrupt valid later transformed scenes | Add scene-local regression test |
| 2026-08-26 | Made appearance replacement scene-local | focused test reproduced global replacement before fix | GREEN: scene40 uses base appearance while scene50 retains transformed appearance | Run broader reconciliation regression tests |
| 2026-08-26 | Focused compile and regression pass | `py_compile`; 6 focused/integration tests | PASS | Independent code review and broader semantic/P400 suites |
| 2026-08-26 | Coverage report attempt | `python -m coverage ...` | Blocked: coverage module is not installed | Do not add dependency without approval |
