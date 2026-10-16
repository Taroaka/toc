# Verification and deployment

## Changes

- Read canonical and historical lifecycle character IDs; use explicit unique primary declarations only. All registered participants work without a protagonist label. Bind base character resources to exact research pointers and source-role IDs; keep source-index-based appearance facts.
- Diagnose cut-list references and dependent shot subject/actor/target/event references in the same bounded repair protocol. Restrict sound cut references to actual cut members. Permit null for a nullable shot target without deleting its performance record.
- Route other shot structural failures only to that cut's shot_plan; all normal validators still run.
- Reuse existing assets by explicit source binding even if a grounded alias is used. Reject another person's pointer and require explicit choice when the same source already has an asset.
- Omit nameless phantom protagonist entries from cinematic resources and asset bibles.

## Checks

- New regressions failed on the previous behavior; they now pass.
- Focused story/profile/p400/p420/shot/repair/resume tests: 152 passed, 1 deselected (before one additional normal authoring-loop regression).
- The additional normal authoring-loop regression and related shot tests: 3 passed.
- Existing test_semantic_cut_rewrite_keeps_healthy_cut_and_uses_original_validator fails identically with HEAD:toc/downstream_repair.py loaded in memory. This existing light-alternative test was excluded; no working-tree file was reverted for the comparison.
- Pointer docs validation and diff whitespace checks passed.
- Read-only validation of saved story passed. Adapter now binds CH1/CH2/CH3/CH4 to the registered people; expected scene scopes are complete.
- Upstream hashes before resume: research a644155097c1a418121cbd0b1eac1415695d25755cb0ec28c28ecf014c6b90ea; story b5c20485197b9ccd244edf5c061bde47dc56e56f6e29e62923613bdcd84789ce; visual_value 83e09bbb2b4bd8f61309e0ef8dede579af9ed7d2ef8e4612d868d6886f6247c0.

## Local review

Reviewed exact source identity handling, ambiguous/multiple/no-primary stories, nested legacy keys, nullable target patches, cut vs global scope, unchanged authored prose, locked run preservation, and unrelated edits. No independent subagent review was used, in accordance with the repository's Astra policy. All supported repairs preserve unit IDs and are followed by original validation.

## Deployment / resume

The user subsequently requested a server restart and Computer Use frontend resume, plus 30-minute monitoring. The heartbeat was created in the current thread (automation ID automation). Resume must be initiated once through the UI after the updated stack is healthy, and the selected job/status must be verified. p680 completion is not yet established here.

- Native Postgres readiness confirmed before restart; TOC_SKIP_DB_START=1 preserves that existing service.
- Restart requested by the user after passing checks; front/backend are reloaded through the bundled restart helper.

- Restart helper completed backend/frontend HTTP and Codex no-op health checks.
- 2026-10-15 09:51 JST: Computer Use clicked the existing run toolbar resume button once.
- Resume job 67ca7bce9f4647739c749d91418bc60a is running, resumeMode=authoring_subprocess.
- research/story/visual_value receipts were reused and all three byte hashes are unchanged.
- Current state: AUTHORING / cinematic_authoring, empty last_error. Current p400 resource snapshot contains named CH1/CH2/CH3/CH4 bindings.
- UI proof: frontend-resumed.png. Image generation and p680 completion remain pending and are covered by the configured heartbeat.
