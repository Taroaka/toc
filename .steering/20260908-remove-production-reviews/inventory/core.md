# Core review / evaluator inventory

Scope is the `toc/` review, evaluator, harness, grounding, semantic-pack,
repair, and mixed contract surface plus the requested review scripts.  This is
an inventory only; no production file was changed.  I read
`docs/root-pointer-guide.md` first.  The guide makes `docs/`, `workflow/`, and
`scripts/` canonical, requires grounding before stages, and currently describes
semantic review reports as production gates (root guide lines 47-67, 111-115,
184-212).

## Execution graph and ownership

* `scripts/review-research-stage.py`, `review-story-stage.py`,
  `review-script-stage.py`, `review-manifest-stage.py`, and
  `review-video-stage.py` are five thin entry points.  Each imports
  `toc.stage_review_cli.run_stage_review_cli` and supplies a stage name
  (for example `scripts/review-story-stage.py:13-20`; the other four have the
  same shape).
* `toc.stage_review_cli.run_stage_review_cli` parses `--run-dir`,
  `--profile fast|standard`, `--flow`, `--out`, and `--fail-on-findings`, calls
  `evaluate_stage`, writes the evaluator Markdown, appends evaluator state, and
  returns nonzero when `--fail-on-findings` and `result["passed"]` is false
  (`toc/stage_review_cli.py:14-67`).  This is an automatic review CLI, not a
  content-authoring helper.
* `toc.stage_evaluator` is a compatibility facade (`toc/stage_evaluator.py:1-5`)
  exporting the modular implementation.  `toc.stage_evaluation.runner` dispatches
  research/story/visual_value/script/manifest/video by flow
  (`toc/stage_evaluation/runner.py:15-40`), renders `approved` versus
  `changes_requested`, score, rubric, and PASS/FAIL checks
  (`:43-74`), and writes `eval.<stage>.status`, findings, reason keys, rubric
  scores, and `artifact.*_review` state (`:77-114`).
* `scripts/verify-pipeline.py` is the production aggregate entry point.  `main`
  parses `--flow`, `--profile`, and `--stage-target`, calls `build_report`, writes
  `eval_report.json`, appends state, writes `run_report.md`, syncs status, and
  exits 0 only when `report["overall"]["passed"]` is true
  (`scripts/verify-pipeline.py:2404-2432`).  `build_report` adds an orchestration
  stage and all stages through the normalized target, then computes the mean
  stage score and `all(stage["passed"])` (`:2237-2334`).
* `verify-pipeline.py` deliberately has two evaluator implementations.  Its
  `check_research`/`check_story` wrappers call `toc.stage_evaluation.pipeline`
  (`:515-520`); script wrappers inject `append_semantic_review_check`
  (`:525-540`); manifest wrappers call pipeline policy (`:547-552`); video
  wrappers inject semantic review and duration seams (`:1890-1914`).  The
  manifest stage additionally imports the modular `check_manifest_single` as
  `shared_check_manifest_single` (`:78-79`) and uses it in immersive
  `build_report` (`:2288-2293`).
* `scripts/run-semantic-review.py` builds a semantic pack by subprocess, starts a
  read-only Codex app-server turn, validates the report, and records pass/fail
  state (`scripts/run-semantic-review.py:297-375`).  Its default loop retries
  failed reviews through a producer-repair app-server turn, with watchdog and
  transport states (`:378-442`, `:445-601`).
* `scripts/build-review-loop-round.py` is the five-critic review-loop entry point;
  it resolves `--stage` or `--slot` and calls
  `materialize_review_loop_round` (`scripts/build-review-loop-round.py:14-45`).
  That helper snapshots source bytes, deletes stale round/final reports, writes
  five critic prompts plus an aggregator prompt, hashes them, and appends loop
  state (`toc/review_loop_runner.py:25-122`).
* The standalone deterministic reviewers are called directly by production
  generation paths: `scripts/toc-immersive-frontend-run.py:12567`,
  `scripts/generate-assets-from-manifest.py:9025`, and server routes invoke
  `review-image-prompt-story-consistency.py`; `scripts/run-p720-narration-l3.py:399`
  invokes `review-narration-text-quality.py`.  Prompt-builder
  `scripts/build-subagent-image-review-prompt.py:59` also advertises the image
  reviewer.  These callers are outside this bounded inventory's production
  implementation scope but must be rewired when the reviewers disappear.

## Automatic evaluator scores and thresholds

### Modular stage evaluator (`toc/stage_evaluation/*`)

`toc/stage_evaluation/common.py:27-63` defines weighted rubric dimensions:

* research: source_grounding .25, coverage .20, conflict_readiness .20,
  structure_readiness .15, story_material_readiness .20;
* story: selection_readiness .20, scene_density .30, grounding_boundary .20,
  affect_readiness .15, handoff_readiness .15;
* script: arc_coverage .25, scene_specificity .20, reference_grounding .20,
  anti_todo .15, production_readiness .20;
* manifest: beat_clarity .25, visual_specificity .20, continuity_readiness .20,
  narration_alignment .15, production_readiness .20;
* video: render_integrity .25, asset_completeness .20, review_readiness .15,
  audio_packaging .20, publish_readiness .20.

`common.py:66-102` turns dimensions into threshold gates.  Thresholds are
research (.60, .60, .55, .60, .60), story (.70, .85, .80, .80, .80), script
(.60, .60, .55, .70, .60), manifest (.60, .60, .60, .55, .60), and video
(.70, .60, .60, .55, .60), in the dimension order above.  `score_from_checks`
excludes only `kind="warning"` checks and returns passed/total rounded to four
decimals (`common.py:663-678`).  `make_stage` sets `passed=all(non-warning
checks)`, emits `score`, weighted `overall_rubric`, reason keys, and checks
(`common.py:681-706`).  `_append_rubric_findings` converts every rubric value
below its threshold into a failing check (`common.py:786-789`).

The pipeline policy duplicates a simpler score/gate implementation in
`toc/stage_evaluation/pipeline.py:70-86`: all checks count, `passed` is
`all(check["passed"])`, and score is passed/total.  Its research compact-pack
escape hatch requires canonical story, at least three passages, either three
sources or one source plus five passages, and a conflict or handoff
(`:41-53`); otherwise broad targets are sources >=12, events >=20, facts >=10,
and passages >=1 (`:131-191`).  Story requires 2-4 candidates, a chosen ID,
rationale, and either >=20 scenes or >=8 dense scenes (`:221-283`).  Standard
profile adds TODO/TBD checks to research/story/script/manifest; fast omits some
of those (`pipeline.py:99-102`, `:205-208`, `:286-290`, `:489-490`).

The same thresholds and score fields are present in the canonical modular
research/story evaluator (`toc/stage_evaluation/research_story.py:54-174`,
`:989-1105`).  Story also performs automatic semantic-review presence and
currentness checks when policy is required or review artifacts exist
(`research_story.py:768-793`).  These are review gates and must be removed or
made advisory; the structured file/ID/source checks can be retained separately.

### Script, manifest, and video evaluator gates

* `toc/stage_evaluation/pipeline.py:301-372` and `:375-455` require semantic
  reviews for scene_set/scene_detail/cut_blueprint at p410/p420 and onward;
  scene_detail and cut_blueprint require a generation receipt at target >=680.
  The canonical script evaluator repeats large authoring checks and writes
  `eval.script.score` (`toc/stage_evaluation/script.py:1905-2139`,
  `:2139-2304`).
* `toc/stage_evaluation/script.py:1951-1978` requires
  `scene_set_review`, `scene_detail_review`, and `cut_blueprint_review` statuses
  in `approved` (or `pending_independent_review` after a passed acceptance
  preflight); `:2080-2092` requires every scene's `agent_review.status` to be
  `passed` or `preflight_passed`.  These are automatic review evidence gates.
  The surrounding scene/event/cut checks (`:439-632`, `:657-842`,
  `:871-1124`, `:1142-1580`) are mixed: exact schema, IDs, source refs,
  reveal boundaries, event preservation, and forbidden directing fields are
  deterministic contract checks; dramatic-quality, coverage-review, film
  grammar, redundancy, handoff, and emotion judgments are semantic content
  checks.
* `toc/stage_evaluation/manifest.py:298-443` requires five round-01 critic
  reports, matching critic inventory, input snapshots/digests, aggregate
  status `passed`, critic hashes, required aggregate sections, and resolved gate
  markers.  `check_manifest_single` exposes `require_review_artifacts=True` by
  default (`:1125-1131`); immersive p400 adds `p400.review_report_integrity`
  and `p400.review_loop_integrity` when true (`:1247-1264`).  Set false in p500
  resume only skips report files; the remaining p400 evaluator still sets an
  `approved` readiness status (`:1286-1294`).
* Manifest checks mix structural output validation and review quality.  Scene and
  node presence, <=15-second cut duration, narration field, explicit character
  and object IDs, manifest phase, prompt policy, and reveal/reference contracts
  are at `manifest.py:856-1040`; scene coverage/redundancy/handoff/emotion,
  `scene_composite_review`, and `triangulation_review` are production semantic
  checks at `:680-854`.  `strict_cut_contract` activates for standard immersive
  or cinematic_story (`:894-897`).  `p400.target_duration_range` uses the
  300-1200 second target and `p400.duration_coverage` uses 80% of target
  (`:1184-1217`; duration constants are `toc/story_duration.py:12-18`).
* `toc/stage_evaluation/video.py:49-96` checks final file existence, render
  status, `review.video.status`, optional narration-list files, positive ffprobe
  duration, quality review contract and must-have artifacts, then emits
  `eval.video.score`; scene-series uses fixed fallback rubric values 1.0 or .3
  and review/audio values .8 (`:99-115`).  `pipeline.py:638-750` adds final
  target duration, duration-fit (`MINIMUM_EFFECTIVE_RATIO=.80`), narration
  list, and required `video_motion` semantic review at target >=820; scene
  series mirrors it (`:638-768`).

### Aggregate `verify-pipeline.py` stages

`check_asset` (`scripts/verify-pipeline.py:1264-1587`) activates checks by slot:
inventory >=520, plan >=530, request/manifest metadata >=550, outputs and
provenance >=560, and visual stats >=560.  It requires every planned asset
review status to be `approved` at target >=540 (`:1417-1438`), requires
asset-plan semantic review, and requires strict request-bound provenance at
target >=560 (`:1462-1484`).  Request metadata includes tool, lane,
reference-count, output, **review status**, prompt policy and API-prompt fence
(`:1503-1545`).

`check_image` (`:1590-1844`) requires request tool/lane consistency, grounding,
declared outputs, localized partial-media receipt, non-blocked output files,
strict request snapshot/provenance, and image visual-quality inspection
(`:1658-1832`).  It then requires `image_prompt` semantic review at target >=640
and a generation receipt at >=680 (`:1833-1842`).  `check_narration`
(`:1847-1887`) requires `narration_text_review.md`, outputs, duration-fit status
`passed|skipped`, and mandatory narration semantic review; all are scored into
`eval.narration.score`.  Video wrappers require `video_motion` semantic review
at target >=820 (`:1900-1914`).

The aggregate orchestration gate requires each p100-p900 bucket's invocation,
returned state, supervisor result JSON, completed slots, required artifacts, and
state keys to agree (`scripts/verify-pipeline.py:1917-2153`).  It emits
`eval.orchestration.score`; this is operational evidence rather than content
authoring and should be separated from any remaining file/state integrity
checks.

### Standalone image-prompt reviewer

`scripts/review-image-prompt-story-consistency.py` has six weighted dimensions
at `:286-302`: story_alignment .25, subject_specificity .20, prompt_craft .15,
continuity_readiness .15, first_frame_readiness .15, production_readiness .10;
all six thresholds are .60 except prompt_craft .65.  Prompt craft also requires
>=220 non-space characters and >=4 of subject/blocking/setting/light/camera/
material categories (`:304-313`, `:1367-1385`).  `_score_prompt_entry` combines
the dimensions into `overall_score` (`:1437-1581`), then `review_entries` adds
findings whenever a dimension is below threshold (`:2054-2129`).

The reviewer has a hard/soft finding split (`:348-388`).  Structural candidates
that are suitable for extraction into a deterministic validator include missing
required blocks, nonvisual/internal metadata, first-frame metadata, motion
brief leakage, missing/unknown character/object IDs, prompt self-containment,
and reveal-constraint violations (`:598-667`, `:696-875`, `:1813-1887`,
`:1929-2052`).  Subject/story alignment, prompt craft, continuity quality,
first-frame quality, target focus, and production-readiness scores are semantic
review behavior and should be removed from the production gate.  `main` reads
manifest/story/script, may autofix IDs, writes review metadata into
`image_generation.review`, writes `image_prompt_story_review.md`, state scores,
and exits nonzero for unresolved findings (`:2392-2463`, `:2465-2494`,
`:2522-2648`).

### Standalone narration-text reviewer

`scripts/review-narration-text-quality.py:151-165` defines thresholds
`tts_readiness=.70`, `story_role_fit=.55`, `anti_redundancy=.45`,
`pacing_fit=.50`, `spoken_japanese=.60` and weights `.30/.30/.15/.15/.10`.
Scores are heuristic: TTS score subtracts .45 for meta markers, .35 for URLs,
emails, Markdown/backticks, and .20 for text normalization
(`:527-536`); pacing bins are <=4.8 chars/sec=1.0, <=6.0=.80, <=7.0=.55,
otherwise .25, with .20 penalties for long sentences/no punctuation
(`:630-650`).  The reviewer adds semantic role, redundancy, pacing, and spoken
Japanese findings under these thresholds (`:702-789`), writes per-node review
metadata and scores (`:800-930`), renders PASS/WARN/FAIL and averages into
`eval.narration.*` (`:937-1006`), and returns 1 only for
`--fail-on-findings` with unresolved entries (`:1021-1063`).  Retain speech/file
hygiene as a possible deterministic media validator; remove the automatic
review score, `agent_review_ok`, human override, and unresolved-entry gate.

## Review policy, grounding, and evidence gates

### Grounding policy

`toc/grounding.py:12-107` defines strict defaults (`story/image/narration` all
`required`) and a `drafts` preset making them `optional`; state writes both
`review.policy.*` and `gate.*_review`.  `resolve_stage_grounding` checks required
files plus `requires_approved_input` entries by looking up a review key and
allowing only configured values, conditioned on policy (`:359-414`).  The
workflow currently binds these checks as follows:

* `workflow/stage-grounding.yaml:67-75`: script requires `story.md` with
  `review.story.status=approved` when `review.policy.story=required`;
* `:86-93`: narration requires `eval.p400_readiness.status=approved` and a
  production manifest;
* `:108-111`: asset requires p400 readiness approved;
* `:146-149`: scene implementation requires p400 readiness approved;
* `:167-181`: video generation requires image and narration statuses approved
  under required policies, plus `:187-192` p400 readiness approved and
  duration-fit passed.

The resolver materializes report/readset/audit artifacts and appends grounding
state (`toc/grounding.py:766-810`); `prepare_stage_context` rejects unless
report ready, readset exists, and audit passes (`:812-843`).  Keep required doc,
template, input-file, root-binding, and readset integrity checks.  Remove the
review-policy/approved-input branch and review-derived state keys, or split it
so a stage cannot accidentally retain an approval evidence gate.

`grounding_validation` returns report/readset/audit existence, current-contract
audit, state statuses, and selected playbooks (`grounding.py:666-765`).
`toc/stage_evaluation/common._append_grounding_checks` turns those into failing
rubric checks for report, ready state, readset, audit, and `audit_passed`
(`common.py:709-772`); this is a mixed consumer.  Preserve path/schema/current
contract validation if grounding remains, but stop counting it as a content
review score or requiring audit `passed` as an automatic evaluator verdict.

### Harness and navigation state

`toc/harness.py:161-231` orders gate/review/eval/artifact keys for the run index;
`:266-312` computes artifact existence and `pending_gates` from required gate
values plus review statuses.  `sync_run_status` embeds `pending_gates` and the
entire eval report (`:326-375`), while `append_state_snapshot` appends state and
rebuilds `p000_index.md`/`run_status.json` (`:377-409`).  Preserve append-only
state, path safety, and projections; remove the pending-review interpretation
and review/eval score fields or make them historical/advisory.

`toc/run_index.py` hard-codes review stage ownership and navigation.  StageSpec
fields `evaluator`/`human_review` and stage tables name review artifacts
(`run_index.py:42-80`, `:89-332`); `SLOT_CONTRACTS` defines review slots p130,
p230, p320, p430, p435, p540, p630, p640, p720, p820, p850, and p930
(`:337-565`).  `PENDING_GATE_TARGETS`, `_pending_gates`, and
`_summarize_slot_status` map gate/review statuses to navigation
(`:569-697`).  `classify_run_file` maps review/eval/semantic/duration artifacts
to those slots (`:769-860`), and `build_run_index_markdown` emits review mode,
next human review, pending gates, review-loop state, and scores
(`:943-985`).  Retain ordinary canonical/request/output file classification and
slot numbering; remove review slots/labels and pending-review navigation.

### Review mode

`toc/review_mode.py:17-55` returns true only when both state values are
`preapproved` and immutable `logs/orchestration/create_input.json` has schema
`toc.create_input.v1` and `review_mode=preapproved`.  It is imported by the
canonical script/manifest evaluator and used to waive coverage/agent-review
checks (`stage_evaluation/script.py:15`, `:1910-1937`; `manifest.py:27`,
`:229-265`), as well as production callers.  Once standard and preapproved
both follow the same no-review path, this mode binding and its waiver branch can
be deleted; keep create-input provenance if it remains useful to request
identity.

## Review-loop and semantic-review machinery

### Five-critic evaluator-improvement loops

`toc/review_loop.py:29-31` sets `MAX_REVIEW_LOOP_ROUNDS=5`,
`REVIEW_LOOP_CRITIC_COUNT=5`, and snapshot schema `review_input_snapshot_v1`.
`REVIEW_LOOP_SPECS` defines final reports and source artifacts for research,
story, visual_value, script, production_readiness, scene_set, scene_detail,
scene_intent, cut_blueprint, narration, asset, hard/judgment scene
implementation, motion/video, video review, and QA (`:251-366`).  Slot mapping is
at `:369-382`; rounds/critic numbers are bounded to 1-5
(`:385-395`).

`build_review_input_snapshot` requires every source artifact, records exact
source SHA/size/policy, optional grounding readset SHA, and for scene stages the
criterion-registry version/digest; it computes the review input digest
(`review_loop.py:485-557`).  `review_input_snapshot_issues` rejects missing or
stale sources/readsets/prompts, policy mismatch, digest mismatch, and prompt
inventory mismatch (`:582-726`).  `_contained_review_source` rejects absolute,
traversal, escaped, missing, or non-file paths (`:445-458`).

`render_critic_prompt` requires independent reports with critic ID, input digest,
`status: passed|changes_requested`, and blocking findings containing
evidence/root cause/downstream impact/fix direction/acceptance condition
(`review_loop.py:875-940`).  `render_aggregator_prompt` requires all five
critic reports and the same digest, while its stage guidance makes scene-count,
scene-detail, cut-blueprint, reveal, handoff, and triangulation markers blocking
(`:943-1090`).  `review_critic_report_issues` accepts only the two statuses and
derives aggregate `passed` only if all five are passed (`:1098-1134`);
`render_aggregated_review` refuses fewer than five reports or a pass with any
critic requesting changes (`:1137-1159`).  `loop_state_updates` also refuses a
passed loop at round 0 and writes `eval.<stage>.loop.*` status/current/max/report
keys (`:846-872`).  Remove this entire critic/evidence/digest/round machinery;
it is the core production review agent mechanism.

### Contextless semantic reviews and repair loop

`toc/semantic_review.py:25-60` defines canonical collection/scope/prompt/report
paths and nine semantic stages: research, story, scene_set, scene_detail,
cut_blueprint, asset_plan, image_prompt, narration, and video_motion.  Foundation
stages also require fixed criterion IDs (`:60-80`).  The module's secure writer
`safe_semantic_write_text` is a large no-follow atomic publication and rollback
implementation (`:468-1441`) used for semantic packs/repairs and tested by
`test_semantic_write_security.py`.

`semantic_review_relpaths`, `semantic_state_updates`, and
`SemanticReviewStatus.passed` make report status and `status=passed` the gate
(`semantic_review.py:1444-1490`).  Reports must contain exactly one status,
reviewed_entries, blocked_entries, failed_selectors, and (unless legacy) input
digest (`:1507-1522`).  `_semantic_review_artifact_currentness_issues` verifies
safe in-run paths, source artifact SHA/policy, collection/prompt/report SHA,
scope binding SHA, request revision, and canonical input digest
(`:1621-1872`).  Shard currentness additionally requires terminal passed/failed
status and exact reviewed-entry coverage (`:1876-1954`); canonical shard
generation IDs, collection/input/scope hashes, per-entry projection hashes, and
exactly-once assignment are checked at `:1956-2235`.  `_check_review_artifacts`
requires all four artifacts, nonzero entries, `status=passed`, exact entry
coverage, empty blocked/failed lists on pass, and foundation criteria evidence
(`:2373-2438`).  `check_semantic_review` and the legacy image judgment fallback
are the public gate wrappers (`:2441-2484`); `review_status_to_state` writes
review paths/status (`:2487-2493`).  Retain any independent safe file/path
validator only if a non-review artifact needs it; remove report status/evidence
and digest currentness gates with the semantic reviewer.

`toc/semantic_review_loop.py:25-36` sets semantic max attempts (2 generally,
3 for scene_set), review/repair timeout 1800 seconds, scene/detail and scene/set
concurrency 6, transport retries 3, and repair snapshot attempts 3.  It maps
each semantic stage to producer slot/owner/artifacts/focus (`:39-94`), writes
repair/loop states (`:368-407`), captures consistent review snapshots and hashes
(`:433-739`), and writes a committed producer-repair prompt/report pair whose
prompt explicitly says not to advance the slot and that the next reviewer must
say `status: passed` (`:888-1162`).  This module is review/repair-only and is
REMOVE; any generic snapshot/path code required elsewhere must be extracted.

`scripts/run-semantic-review.py` uses those limits, writes watchdog states and
transport failures, calls `build-semantic-review-pack.py`, invokes a Codex
app-server critic, requires a completed report, and on failure invokes producer
repair before retry (`:182-294`, `:297-375`, `:378-442`, `:474-601`).  Its CLI
offers `--no-repair-loop` but still runs one semantic reviewer (`:604-624`);
delete the entry point and all callers, not merely the repair flag.

### Semantic pack builders

`toc/semantic_pack.py:12-22` dispatches all nine semantic stages to specialized
collectors and has a conservative fallback collector (`:318-360`).  The
specialized collectors are all reviewer input materializers:

* `semantic_pack_foundation.py:81-105` records unresolved research references,
  event allocation, and unassigned events; `:121-245` records declared
  time/location route status; `:248-329` emits research/story review entries.
* `semantic_pack_scene.py:41-103` collects scene/cut entries;
  `_validated_scene_acceptance_context` performs acceptance contract, draft,
  preflight, generation, and digest currentness checks and raises on any failure
  (`:135-236`); cut entries retain derived event/context/neighbor diagnostics
  (`:481-598`).
* `semantic_pack_asset.py:23-78` carries category rubrics; `collect_entries`
  merges inventory/plan/request/manifest/usage and adds `review_rubric`,
  `review_status`, wrong-category usage, and fix targets
  (`:81-175`, `:310-363`, `:588-638`).
* `semantic_pack_image.py:231-457` collects prompt, scene-image, and composite
  entries; its `semantic_contract_missing`, output/provenance, reference-role,
  temporal, and coverage fields are reviewer inputs, not generation output.
* `semantic_pack_narration.py:13-18` names quality-review artifacts; entries
  carry semantic contract, audio output, silence, visual-redundancy, and quality
  review fields (`:71-171`, `:235-319`).
* `semantic_pack_video.py:34-216` collects motion/clip/render entries;
  provider prompt recompile and materialized reference SHA checks are at
  `:342-473` and `:542-590`; render-order/sample/contact-sheet artifacts are at
  `:697-906`.

`scripts/build-semantic-review-pack.py` is the materializer called by
`run-semantic-review.py` (`:297-311`).  It renders collection and report
  templates, computes source/collection/prompt/scope/input digests, and emits
  per-scene image shards with exact selector coverage (`:69-174`,
  `:214-390`).  `entry_diagnostics` turns missing contracts, blocking provider
  quality issues, unresolved refs, unassigned events, invalid dayparts/routes
  into `failed_selectors` (`:393-558`).  Remove with the semantic reviewer; a
  small source/reference collector may survive only if needed by a new
  deterministic validator.

## Mixed validators and contracts to split

### Scene acceptance contract

`toc/scene_acceptance_contract.py:25-46` defines contract/draft/criterion
versions and SHA256 digest domains.  The criterion registry marks canonical
event ownership/order, reveal monotonicity, role visibility, handoff, time/
location transition, source grounding, and causal-proof references as
`owner=deterministic`; `causal_proof_visual_quality` is
`owner=independent_semantic` and `story_specificity` is `owner=authoring_semantic`
(`:52-173`).  The latter two semantic/reviewer criteria are REMOVE candidates;
the deterministic reference/ID/evidence criteria are RETAIN candidates.

`ValidationResult` exposes `.passed`, reason keys, blocking keys, findings, and
`status` (`:189-306`).  Contract validation checks generation ID, registry
version/digest, unique scenes, exact canonical events/evidence/reveal/handoff/
transition IDs, reveal-state order, owner beats, and cross-scene state
continuity (`:739-1023`).  Draft validation checks schema, generation/contract/
slice digests, exact beat order and reference closure, participant roles/
evidence, and handoffs (`:1260-1530`).  Whole-set preflight requires exactly
one draft per scene, reruns draft checks, checks producer/consumer handoff
equality, and emits contract/registry/source/draft/preflight digests
(`:1555-1648`).  Keep these as deterministic authoring/schema/ID/provenance
checks if the scene-authoring path still needs them, but stop treating their
`.passed` output as an automatic semantic reviewer verdict.

`semantic_pack_scene._validated_scene_acceptance_context` currently requires
preflight `status=passed`, current contract/draft/source digests, and no
blocking findings (`semantic_pack_scene.py:150-221`); it is a review-pack
dependency and should be moved to a direct authoring/materialization contract
check if retained.  `scene_acceptance_currentness_issues` checks script marker,
contract/preflight, manifest projection, and all digests
(`semantic_pack_scene.py:239-289`), and is consumed by stage evaluators and
manifest checks (`stage_evaluation/script.py:1923-1949`,
`stage_evaluation/manifest.py:730-768`).

### Image request snapshot and provenance (retain core)

`toc/image_request_snapshot.py` is primarily a deterministic output/provenance
contract, despite its docstring saying Markdown request files are review
projections (`:1-6`).  It freezes unique item IDs/destinations, prompt and
source SHA, compiler/policy versions, references and deferred producers
(`:216-450`); `write_request_snapshot_atomic` validates and durably publishes
it (`:1395-1428`); `load_request_snapshot` and `validate_request_snapshot`
enforce schema, normalized in-run paths, item/request/revision digests,
reference hashes and deferred-producer rules (`:1515-1662`).
`match_output_provenance` requires successful app-server `request_bound_v2`,
authoritative provenance, one generation item, exact request/item/prompt/
compiler/source/destination/reference/output hashes (`:1710-1824`).  Keep these
schema/file/ID/reference/provenance checks for media safety and reproducibility.
The `Review-time snapshots may defer...` wording and any call path that exists
only to bind semantic-review evidence (`:1431-1512`) are SPLIT candidates.

### Partial-media localization (remove review dependency, preserve media checks)

`toc/partial_media.py:39-50` defines semantic stages image_prompt/scene_detail,
projection and generation-receipt paths.  Selector normalization and
localization map failed/blocked semantic selectors to exact image item IDs and
reject duplicates, out-of-scope selectors, zero matches, and all-items-blocked
(`:71-452`).  `_semantic_bundle`/`_captured_scope_report_issues` require
semantic report status, reviewed-entry coverage, failed/blocked lists, source
digests, scope binding, and input digest (`:650-1010`); stable request snapshots
and receipts are captured around `:1243-1365`, and
`derive_partial_media_projection` materializes a digest-bound blocked/surviving
projection and synthetic failed candidates (`:1368-1635`).  The verifier in
`verify-pipeline.py` repeats exact receipt truth-set checks
(`:131-464`).  This entire path exists to continue image generation after a
semantic reviewer failure and is REMOVE with semantic review.  Retain generic
request snapshot/output existence/provenance validation in the image output
validator.

### Narration review gate, revision, and duration

`toc/narration_review_gate.py:66-123` requires every revision-aware narration
node to have `agent_review_ok=true` or a human override with a non-empty reason,
rejects bad semantic/delivery/arc statuses, and for a revision-aware run
requires full-run `arc_review.status=passed` plus matching
`narration_text_set_hash` (`:71-119`).  This is a direct review-evidence gate
and should be removed/split.  Keep active-node ordering and selector normalization
(`:48-64`) if needed by media generation.

`toc/narration_revision.py:157-170` invalidates semantic/arc/delivery review
fields on text/TTS changes.  Revision hashes, compare-and-swap edits, TTS
candidate snapshots, stale completion protection, and output hashes are normal
authoring/media lifecycle (`:41-155`, `:220-395`).  Explicit human audio
candidate approval still gates `current_audio_is_human_approved`
(`:398-473`), and `narration_audio_set_hash` hashes the ordered approved
playback set (`:476-495`).  The latter human listen/approval evidence is a
SPLIT/removal candidate under the user's broad review-evidence request; do not
silently classify it as an automatic semantic review.  `script_narration.py`
resolves approved text before explicit TTS and otherwise materializes clean
ElevenLabs text (`:52-107`); remove the `human_review.approved_*` fallback if
human review fields are removed.  `narration_continuity.py` preserves full-run
span text and adjacent TTS context hashes (`:89-200`) but reads approved text
fallbacks (`:39-48`) and resets audio approvals when context changes
(`:203-248`): keep hash/continuity, split approval-field dependencies.

`toc/story_duration.py:12-18` defines target 300-1200s, effective runtime floor
80%, narration floor 70%, and max 40s/scene.  `measure_manifest_runtime` is a
deterministic audio/video timeline measurement (`:120-266`); `audit_duration`
returns `passed` only when actual >= 80% target (`:301-328`).  Keep measurement
and output validation.  `toc/duration_fit_review.py:11-116` only writes
contextless scene/narration expansion prompts and asks for
`status:passed|changes_requested`; remove it as an automatic review agent.
`scripts/check-audio-duration-gate.py` is mixed: measurement/state and the 80%
gate are at `:201-263`, while prompt generation and p740/p750
`changes_requested|blocked` review flow are at `:264-305`; split accordingly.

### Prompt compilers and reveal/media safety

`toc/image_prompt_compiler.py:81-135` and `toc/video_prompt_compiler.py:128-180`,
`:280-805` are normal deterministic prompt compilers.  They enforce drawable
fragments, frame/reference modes, reveal allowlists, provider request binding,
prompt SHA, and no unresolved alternatives/abstract placeholders
(`image_prompt_compiler.py:641-727`; `video_prompt_compiler.py:902-910`,
`:1146-1228`).  Keep provider/media safety.  Remove or stop emitting
`review_metadata`, `review_only_dependencies`, and `projection_review_contract`
fields if they are consumed solely by reviewers (`image_prompt_compiler.py:90-135`,
`video_prompt_compiler.py:366-406`, `:735-805`).

`toc/image_prompt_projection_registry.py:82-113`, `:118-324` maps source keys
to drawable groups and explicit excluded/review-only rules.  Registry shape
validation is at `:375-398`; `build_projection_review_contract` and
`projection_trace_issues` enforce source->dependency->fragment->prompt exactness
(`:400-624`).  Keep compiler group order, source IDs, path/metadata stripping,
and time/reveal safety; split out/remove review-only rule metadata and semantic
trace findings.

`toc/video_prompt_projection_registry.py:31-441` similarly marks rules as
provider `derive|may_surface|must_not_surface` and review visibility
`projection|review_only|none`; `video_projection_registry_issues` checks registry
shape (`:470-509`) and `build_video_prompt_projection` returns active/excluded/
review-only sources (`:512-732`).  Keep provider projection and metadata
stripping; remove review-only source lists and semantic-check labels if no
reviewer consumes them.

`toc/reveal_constraints.py:81-180` parses allowed `must_not_appear_before`
constraints and returns concrete violations from declared IDs/aliases/text.  This
is a story reveal invariant and can remain as a deterministic content-safety
check; only remove duplicate reviewer reporting.

`toc/cut_context_packet.py:34-118` compiles an immutable derived cut packet and
`diagnose_cut_context_packet` returns warning-only missing role/proof/boundary/
neighbor diagnostics (`:219-309`).  Keep packet compilation for downstream
authoring, but do not route warning diagnostics through a semantic review gate.

## Production repair/rebuild consumers

`toc/semantic_repair_patch.py:21-150` defines patch schema, max 64 operations,
stage roots, and protected identity/evidence/digest/status keys.  Header checks
require exact stage, `semantic_review_input_digest`, nonempty operations, and
<=64 operations (`:441-484`); application is restricted to failed selectors,
`script.md`, existing exact paths, expected-old compare-and-swap, compatible
types, and unchanged protected projection, then calls reconciliation
(`:540-695`).  This is REMOVE as semantic-review repair infrastructure.  Its
path/identity protections are only useful if a replacement authoring patch API
is intentionally retained.

`toc/semantic_repair_reconciliation.py:1-100` is explicitly “after semantic
producer repair.”  It normalizes/reprojects event, source, reveal, first-frame,
motion, narration, asset and handoff contracts (`:162-901`), syncs script into
manifest and validates exact scene/cut shape/IDs (`:1012-1181`), then mutates
documents through `reconcile_semantic_repair_documents` (`:1493-1596`).  Remove
the repair-specific projection; extract `_validate_scene_and_cut_shape` if an
independent schema/ID check is still required.

`toc/p500_resume.py` preserves canonical p400 files but classifies and moves all
downstream semantic/eval/review files and resets review/eval state prefixes
(`:43-182`, `:996-1030`, `:1320-1371`).  `_p400_readiness` calls the manifest
evaluator with `require_review_artifacts=False`, then still requires
`eval.p400_readiness.status=approved` (`:966-993`).  Keep safe direct-child run
validation, symlink/path checks, checkpoint/rollback and downstream media
cleanup; split out this p400 review-status dependency.

`toc/p400_rebuild.py:76-141` explicitly replaces semantic reports and
invalidates `review.semantic.*`; candidate validation requires contract,
draft, preflight and acceptance projection digests/statuses
(`:517-656`).  Transactional checkpointing and source/path/identity safety can
remain, but semantic report paths/status checks should be removed or replaced
by direct deterministic acceptance checks.

## Tests and expected fallout

The direct reviewer/evaluator suites are:

* `tests/test_review_loop.py`, `test_review_loop_contract.py`,
  `test_review_projection.py`, `test_stage_evaluator_parity.py`,
  `test_stage_evaluator_scripts.py`, `test_review_story_stage.py`;
* `tests/test_verify_pipeline.py` and
  `test_verify_pipeline_image_provenance.py`;
* `tests/test_semantic_review.py`, `test_semantic_review_workspace_security.py`,
  `test_semantic_write_security.py`, `test_run_semantic_review_script.py`,
  `test_image_prompt_semantic_sharding.py`, `test_build_image_prompt_judgment_review.py`;
* `tests/test_image_prompt_story_review.py`,
  `test_image_prompt_repair_freeze.py`, `test_build_subagent_image_review_prompt.py`;
* `tests/test_narration_text_review.py`, `test_narration_review_gate.py`,
  `test_narration_semantic_review.py`, `test_p720_narration_semantic_runner.py`,
  `test_p720_l3_narration_runner.py`;
* `tests/test_scene_acceptance_contract.py`,
  `test_scene_acceptance_frontend_integration.py`,
  `test_scene_acceptance_shift_left_runtime.py`,
  `test_semantic_repair_patch.py`, `test_semantic_repair_reconciliation.py`;
* `tests/test_stage_grounding.py`, `test_build_subagent_audit_prompt.py`,
  `test_build_subagent_duration_review_prompts.py`, `test_audio_duration_gate.py`,
  `test_final_video_duration_gate.py`, `test_frontend_duration_gate.py`;
* `tests/test_image_request_snapshot.py`, `test_run_root_binding.py`,
  `test_state_store.py`, `test_run_index.py`, and `test_p500_resume.py` cover
  mixed/provenance/state/rollback behavior and need retained portions isolated.

Additional integration suites that assert the same gates/callers include
`tests/test_image_gen_server.py`, `test_toc_immersive_frontend_run.py`,
`test_immersive_narration_multiagent.py`, `test_migrate_audio_first_slot_contract.py`,
`test_sync_narration_from_script.py`, and `test_story_neutral_production_code.py`.

The review-only tests assert exact report status, reviewer IDs, evidence,
source/digest currentness, five-critic counts, shard coverage, repair retries,
transport/no-progress behavior, `agent_review_ok`, human overrides, rubric
scores, and `eval.*` state.  Delete or rewrite those assertions when removing
the review path.  Keep tests for YAML/schema parsing, exact IDs and references,
run-root/symlink safety, request snapshot/provenance, media decode/existence,
duration measurement, TTS revision CAS, reveal constraints, and transactional
rollback.

## Classification summary

* **REMOVE:** `review_loop.py`, `review_loop_runner.py`,
  `semantic_review.py` review-status/currentness layer and safe writer if no
  other caller remains, `semantic_review_loop.py`, `semantic_repair_patch.py`,
  semantic-repair-only parts of `semantic_repair_reconciliation.py`, all
  semantic pack collectors/dispatcher, `scripts/run-semantic-review.py`,
  `scripts/build-review-loop-round.py`, five stage-review wrappers/CLI,
  standalone image/narration reviewer score-and-status layers, duration prompt
  builders, partial-media semantic-failure projection, and reviewer-only
  navigation/report materialization.
* **SPLIT:** `verify-pipeline.py`, modular/pipeline stage evaluators,
  `grounding.py`/`workflow/stage-grounding.yaml` approved-input policy,
  `harness.py` pending-gate projection, `run_index.py`, `review_mode.py`,
  `scene_acceptance_contract.py`, `narration_review_gate.py`, narration
  revision/continuity approval fields, image/video prompt projection registries,
  p400/p500 rebuild/resume, and compiler/reviewer metadata.  Preserve
  schema/file/ID/source/reveal/reference/request/provenance/media checks while
  deleting automatic reviewer status, evidence, digest, rubric, and score gates.
* **KEEP (ordinary production):** rich story authoring and deterministic story
  document validation (`story_authoring.py`, `story_author_pipeline.py`), prompt
  compilation and provider capability checks, reveal constraints, TTS text
  materialization, request snapshots/output provenance, safe run-root/state
  transactions, media existence/decode and duration measurement.  Human
  selection/listening/edit fields are intentionally listed as SPLIT because the
  user's request includes broad review evidence removal; their final product
  policy needs an explicit replacement decision.
