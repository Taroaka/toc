# Verification

- Before implementation: new staging regression suite failed at the intended execution/projection boundary (9 failed, 1 passed).
- Execution / initial author / story author / source-first projection / video compiler: 134 tests and 117 subtests passed.
- Added a cache-policy regression, source reveal schema requirement and matching repair instruction; final initial staging + story pipeline/runtime/integration-contract run: 44 passed.
- Optional references / p400 rebuild / B-roll: 27 passed.
- Pointer docs validation and scoped whitespace checks passed.
- Bounded code review completed with no outstanding findings after resolving unpeopled staging and source-reveal schema/repair issues.
- Frontend creation invokes `scripts/author-cinematic-direction-with-codex.py`, which uses the changed p420 author and projection path. No new UI option or second production reviewer is required.
- Provider generation was not run; tests exercise contracts and prompt projection with source fixtures. Generated image/video fidelity is not guaranteed.
- Existing run media were not rewritten. Unrelated user/worktree changes were preserved.
