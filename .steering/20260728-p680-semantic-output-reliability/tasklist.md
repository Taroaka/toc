# Task list

- [x] Add red tests for complete JSON verdict normalization.
- [x] Add red integration test proving JSON verdicts do not trigger producer
      repair.
- [x] Add red tests proving missing/malformed final verdicts are classified as
      transport/output-contract failures in monolithic and shard paths.
- [x] Implement strict JSON normalization and shared output-contract detection.
- [x] Add semantic-repair dependency reconciliation and a pre-asset fixed-point
      review/provider gate.
- [x] Audit p650/p680 request freeze, generation, and terminal-state validation.
- [x] Split P400/downstream review materialization and bind P400 reviews to the
      final post-request manifest revision.
- [x] Make frontend resume use the canonical p500 dry-run/exact-token/apply
      workflow and reject same-run concurrency.
- [x] Add fine-slot rerun invalidation so stale P400 approval/review snapshots
      cannot survive a rewind.
- [x] Harden resume locks, image deletion, subprocess cancellation, and
      dry-run/apply fingerprints against symlink and TOCTOU races.
- [x] Require terminal p680 verification and request-bound immutable asset/image
      provenance.
- [ ] Add shared pre-p800 review projection and transactional storyboard p680
      finalization.
- [ ] Preserve the exact create source through canonical p500 resume.
- [ ] Preserve the `world_walk` source-reference contract in fresh and resumed
      asset requests.
- [ ] Route asset/reference repair through canonical p500 and fail closed for
      malformed image-only repair plans.
- [ ] Continue unaffected image generation for completely localized semantic
      failures while exposing blocked items as failed candidates.
- [x] Invalidate downstream approval/provenance when a candidate is inserted.
- [ ] Run focused and related test suites.
- [ ] Run mandatory code review and resolve findings.
- [ ] Restart the backend/frontend safely and verify health.
- [ ] Dry-run and apply the canonical p500 resume plan for the existing
      Cinderella run, then verify p680 artifacts and generated images.
