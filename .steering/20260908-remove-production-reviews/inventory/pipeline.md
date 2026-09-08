# Production review removal: scripts and pipeline inventory

この inventory は `/Users/kantaro/Downloads/toc` の現在の checkout を対象にした。作業開始時に `docs/root-pointer-guide.md` を読み、生成物の workflow、grounding、state、provider provenance、render を production の範囲として追跡した。行番号は調査時点のものなので、実装で行が動いた場合は symbol 名も併記して再確認する。

対象は `scripts/` の実行入口、stage orchestration、generation、duration、render、resume、grounding、authoring helper と、それらの hidden call path である。過去の `output/`、`improve_claude_code/`、kindle/marketing、一般の code-review/security-review は対象外とした。`scripts/review-*.py`、`scripts/verify-pipeline.py`、`scripts/run-semantic-review.py`、`scripts/build-review-loop-round.py` は別 inventory の担当なので、ここでは呼び出し元と依存だけを記録した。`scripts/toc-immersive-frontend-run.py` は main の担当外だが、resume と generation が private helper 経由で再入場するため、その境界だけ記録する。

分類は次の意味で使う。

- **REMOVE**: production reviewer/critic/aggregator、semantic judgment、review score、review report の status/digest/人数/順序監査、またはそれを必須にする進行 gate。
- **SPLIT**: deterministic schema/ID/path/file/decode/duration/provenance/authoring validation と review artifact の要求が同じ関数または同じ呼び出しにある。前者を残し、後者だけを外す。
- **KEEP**: 作成 agent、authoring prompt、source/readset 解決、human selection UI、provider request/output binding、lock、path security、実ファイル検査、ffmpeg/ffprobe、run 状態の保存。`review` という既存 key 名だけでは削除対象とせず、agent report を要求するかで判定する。

## 実行経路の全体像

```text
toc-run.py / toc-scene-series.py
  -> toc.grounding.run_stage_grounding
  -> research/story/visual/script scaffold

toc-world-walk.py
  -> toc-immersive-ride.py --experience world_walk

toc-immersive-ride.py
  -> stage grounding + readset/audit materialization
  -> p400 review-loop prompt materialization (REMOVE)
  -> toc.stage_evaluation.check_manifest_single (SPLIT)
  -> p500/p600/p700/p800/p900 scaffold state

toc-immersive-ride-generate.sh / toc-immersive-ride-e2e.py
  -> generate-assets-from-manifest.py
       -> p400 readiness (REMOVE review-report dependency; KEEP structural checks)
       -> review-image-prompt-story-consistency.py (REMOVE)
       -> run-p720-narration-l3.py (REMOVE reviewer loop; SPLIT deterministic checks)
       -> run-p720-narration-semantic.py (REMOVE)
       -> image/audio/video provider generation (KEEP)
  -> sync-manifest-durations-from-audio.py (KEEP)
  -> check-audio-duration-gate.py (SPLIT)
  -> build-clip-lists.py + render-video.sh (KEEP)
  -> check-final-video-duration-gate.py (KEEP deterministic)
  -> verify-pipeline.py (excluded; its review/score/report checks are downstream)

resume-from-p500.py
  -> checkpoint/source/provenance restore (KEEP)
  -> frontend private p400 review refresh/readiness (REMOVE)
  -> prepare-stage-context.py (SPLIT grounding audit gate)
  -> frontend semantic pipeline / validate (REMOVE review dependency; KEEP structural validation)
  -> p500/p600 result materialization (KEEP)
```

## p100–p900 bucket map

The script tree has no one-file `p100.py` … `p900.py` runner. Coarse targets are implemented by `toc-immersive-ride.py` and the production shell; L2 progress is a generic helper. The frontend runner owns the canonical p100–p600 materialization path and is excluded from this subtask.

| bucket | coarse handoff / slots | script path and symbol | current review dependency | disposition |
|---|---|---|---|---|
| p100 | research → p130; p110/p120/p130 | `scripts/toc-immersive-ride.py:91-105,2160-2177`, `_main_impl`; `scripts/toc-run.py:105-106`, `main`; `scripts/toc-scene-series.py:609-610`, `main` | ride scaffold calls `materialize_review_loop_prompts(stage="research")`; `toc-run`/scene-series only call grounding | **REMOVE** research reviewer prompt/state; **KEEP** research author artifact and source grounding |
| p200 | story → p230; p210/p220/p230 | `scripts/toc-immersive-ride.py:106-108,2180-2201`; `scripts/toc-run.py:107-108`; `scripts/toc-scene-series.py:611-612` | story review loop is materialized before handoff; `build-subagent-story-review-prompt.py` is a scoring prompt | **REMOVE** reviewer/score/report requirement; **KEEP** authored story and deterministic story contract; grounding **SPLIT** because script grounding currently checks `review.story.status` |
| p300 | visual planning → p330; p310/p320/p330 | `scripts/toc-immersive-ride.py:109-112,2203-2237`; `toc-run.py:109-119` | visual value review-loop prompt/state | **REMOVE** reviewer loop; **KEEP** visual value artifact and deterministic handoff fields |
| p400 | scene set/detail p410, cut blueprint p420, script p430, readiness council p435, manifest p450 | `scripts/toc-immersive-ride.py:82-88,1712-1871,1917-1970,2309-2393`; `toc.stage_evaluation.manifest.check_manifest_single` | five critic prompts, final reports, report/loop integrity, `eval.p400_readiness` review status | **REMOVE** all critic/aggregator/review-report paths; **SPLIT** `check_manifest_single` to retain structural contract, selector, duration, grounding, and human-change checks |
| p500 | asset → p570; p510–p570 | `scripts/toc-immersive-ride.py:2411-2458`; `scripts/toc-immersive-ride-generate.sh:76-90,204-225`; `generate-assets-from-manifest.py:9440-9564` | asset review loop at p540 and p400 readiness status; asset request snapshot is also written | **REMOVE** asset semantic review requirement; **KEEP** asset inventory/plan/request files, request snapshots, asset IDs, refs, provider provenance, output existence |
| p600 | scene implementation/image → p680; p610–p680 | `scripts/toc-immersive-ride.py:2460-2496`; `generate-assets-from-manifest.py:9022-9038,9440-9564,9771-9787`; `resume-from-p500.py:1690-1739` | image consistency reviewer, image judgment review artifacts, p400 review gate, frontend semantic image review | **REMOVE** reviewer/model/report/score gate; **SPLIT** request compiler/snapshot and image file/provenance validators; human image candidate UI remains related scope |
| p700 | narration/audio → p750; p710–p750 | `scripts/toc-immersive-ride.py:2498-2519`; `run-p720-narration-l3.py:383-548,551-606`; `run-p720-narration-semantic.py:73-252,255-285`; `generate-assets-from-manifest.py:9040-9062,9789-9808` | deterministic narration reviewer, five semantic critics, p720 report/status, `gate.narration_review`; ElevenLabs generation itself is separate | **REMOVE** reviewer/critic/report/pass gate; **KEEP/SPLIT** TTS text construction, narration contract shape, audio output/decode/duration, and human candidate selection where used |
| p800 | video generation → p850; p810–p850 | `scripts/toc-immersive-ride.py:2521-2550`; `scripts/toc-immersive-ride-generate.sh:201-225`; `generate-assets-from-manifest.py:9566-9763,9810-10090` | video-generation review loop, reviewed prompt artifact/approval status, deterministic quality issues mixed into prompt binding | **REMOVE** reviewer report/approval dependency; **SPLIT** use current compiled persisted payload plus exact hashes/references/provider capability checks |
| p900 | render/QA/runtime → p930; p910–p930 | `scripts/toc-immersive-ride.py:2552-2583`; `toc-immersive-ride-generate.sh:227-267`; `check-final-video-duration-gate.py:110-178` | QA review loop/report and final human video approval are separate; final duration is deterministic | **REMOVE** QA reviewer loop/report requirement; **KEEP** render, ffprobe duration and artifact state; human final approval evidence is a related removal candidate, separate from authorization to publish |

L2 progress is not a reviewer model: `scripts/record-l2-supervisor-progress.py:17-28,35-98,101-139` (`VALID_BUCKETS`, `append_progress`, `build_state_updates`, `main`) accepts every p100–p900 bucket and records invocation/result state. Retain this orchestration evidence, but remove any `review_outputs`/review result fields that become mandatory solely because a reviewer was run. `scripts/ai/session-bootstrap.sh:26-35` currently invokes `verify-pipeline.py --profile fast`; remove that implicit review-bearing verify call or make it a purely structural diagnostic while retaining `toc-state.py show`.

## Entry points and orchestration details

### Immersive ride scaffold and world walk

`scripts/toc-immersive-ride.py` is the largest script-side review concentrator.

- `P400_REVIEW_STAGES` and handoff tables at `:82-88` and `:229-315` encode reviewer stages, `review.*` statuses, `gate.*_review`, and p-slot notes. Remove these review-only state updates while preserving stage/slot/artifact state.
- `maybe_run_stage_grounding` at `:1364-1469` resolves docs/readsets and writes grounding/audit artifacts. It is **SPLIT**: retain source path and required-input checks; do not make `stage.*.audit.status=passed` or an audit report a production prerequisite.
- `require_fresh_p400_readiness` at `:1471-1479` calls `check_manifest_single(run_dir, "standard", "immersive")`, appends all evaluator updates, then raises unless `eval.p400_readiness.status == approved`. Replace with a structural manifest/readiness call that does not inspect critic/report state. The imported `check_manifest_single` is a hidden gate even though this script has no `review-*.py` subprocess.
- `materialize_review_loop_prompts` at `:1560-1702` builds source snapshots, five critic prompts, aggregator prompt, final-report paths, and `eval.*.loop.*` state. `merge_review_loop_updates` at `:1705-1709`, `p400_review_is_current` at `:1758-1771`, `p400_review_inputs_changed` at `:1774-1792`, `merge_current_or_materialized_p400_reviews` at `:1795-1807`, `preserved_p400_state_updates` at `:1810-1856`, and `prepare_p400_review_updates` at `:1859-1871` are review-only and should be removed or replaced by a no-review structural preparation function.
- `reset_p400_review_handoff` at `:1917-1970` deletes old eval/final reports and recreates pending loop state. Remove the report deletion/reinitialization path. Keep source receipt refresh and safe run-root cleanup.
- `_main_impl` accepts `--review-policy`, `--story-review`, `--image-review`, and `--narration-review` at `:2008-2011`, calls `resolve_review_policy` at `:2077-2082`, materializes p100–p300 loops at `:2162`, `:2184`, `:2216`, then p400 loops through `prepare_p400_review_updates` at `:2310-2313` and `:2361-2364`. Later asset/scene/narration/video/QA branches call review-loop materialization at `:2422`, `:2463-2467`, `:2499`, `:2522`, and `:2554`. Remove the mode/loop calls and keep artifact authoring, grounding, source receipt, and stage stop-slot behavior.
- World-walk source receipt handling at `:1093-1316` (`_source_asset_relpaths`, `build_world_walk_source_receipt`, `_persist_world_walk_source_receipt`) is path identity/hash provenance and must remain. `scripts/toc-world-walk.py:52-90` validates the source path and forwards to this runner; remove only review-policy flags/forwarding at `:46-49,80-87`.

`scripts/toc-run.py:16,44-45,66-163` and `scripts/toc-scene-series.py:32,75-76,539-759` are scaffolders. Their `resolve_review_policy`/`review_policy_state_entries` calls (`toc-run.py:86-103`; scene-series `:576-607`) seed review modes and `gate.*_review` state and should be removed from production handoff. `toc-scene-series.py:617-642` is a distinct human hybridization approval gate (`detect_hybridization_pending`); retain it. Its optional placeholder path at `:720-747` runs grounding, placeholder media, concat-list generation, and render; these are structural/media operations and remain.

`scripts/toc-immersive-ride-e2e.py:233-436` builds a legacy manifest from an existing script and calls `generate-assets-from-manifest.py` at `:396-436`; it does not call a reviewer directly, but inherits the generator’s p400/image/narration gates. Its API credentials, scene manifest construction, provider invocation, concat list, and render at `:443-471` remain. Update only the inherited generator path/flags after the review branches are removed.

`scripts/toc-create-run-headless.py` is a regression helper for the backend create route. `_check_cut_contract_v2` at `:52-155` and `_check_storyboard_v1` at `:224-387` are structural contract, identity, duration, prompt leakage, reference ordering, image decode, and request-binding checks; retain them. `_write_report` at `:409-445` writes a contained regression diagnostic, not a production reviewer report, so retain. `REVIEW_MODES`/`review_mode` validation and payload echo at `:31-32,448-568,612-618` are review-mode plumbing; remove the standard/preapproved behavior distinction once both routes run without reviewers, while keeping create job/run/path identity checks.

### Generation, narration, video, and render

`scripts/generate-assets-from-manifest.py` contains both request compilation and review enforcement.

- Review-related CLI switches at `:8621-8646` (`--ignore-duration-fit-gate`, `--ignore-p400-readiness-gate`, `--skip-image-prompt-review`, `--skip-narration-review`, `--image-prompt-review-fix-character-ids`) exist to control reviewer gates. Remove the switches and their branching; do not silently replace them with a global preapproved mode.
- Manifest identity and phase checks at `:8934-9019` are structural and remain, but the p400 call/status block at `:8971-8981` must stop requiring review-report-backed `eval.p400_readiness.status`. The duration state check at `:8982-8991` must stop requiring `review.duration_fit.status=changes_requested` to be resolved by a subagent; retain direct runtime validation where the product still needs a duration floor.
- Direct reviewer subprocesses at `:9022-9038` (`review-image-prompt-story-consistency.py`) and `:9040-9062` (`run-p720-narration-l3.py`, `run-p720-narration-semantic.py`) are **REMOVE**. These are the production image/narration reviewer model/report paths.
- Structural request and input validation at `:9173-9218` (`validate_human_change_requests`, `validate_scene_character_ids`, `validate_scene_object_ids`, `validate_scene_reference_variant_ids`, `validate_object_reference_scenes`, `validate_scene_narration`) remains. Human change request expansion is provenance/edit data, not reviewer scoring.
- Image request construction, preview, and request snapshot at `:9440-9564` (`_write_request_preview_md`, `_write_image_request_snapshot`) remains as authoring/provenance materialization. `review_status` fields emitted at `:9518-9546` should not be read as a production gate.
- Video request materialization at `:9566-9763` keeps compiled payloads, references, negative prompts, exclusion output, and request revision. `_validated_video_prompts_from_review_artifact` at `:7941-8024` is **SPLIT/REMOVE gate**: retain exact current payload/hash/section binding, remove the requirement that the section is “reviewed” and that state contains `status=approved`. `_require_exact_persisted_video_payload` at `:8272-8292` is a structural persisted-payload equality check and remains. `_assert_video_prompt_quality_allows_provider_execution` at `:8320-8330` can remain only for deterministic compiler blocking issues; do not use reviewer-generated score/report fields as its input.
- `_write_image_request_snapshot` at `:8333-8397`, `_write_generation_exclusion_report_md` at `:8426-8453`, and provider loops at `:9771-10092` remain for request/output provenance, deleted-item exclusion, concurrency, image/audio/video generation, and provider transport. The word `reviewed_*` in local variable names does not by itself indicate a reviewer model; the payload approval/status lookup does.

The shell pipeline `scripts/toc-immersive-ride-generate.sh` has these gates:

- `:45-62` initializes state and enforces hybridization human approval; retain the latter.
- `:80-90` runs p500 asset generation; it inherits generator p400/reviewer checks and must run after those checks are split.
- Revision-aware narration binding at `:118-168` calls `server.image_gen_app._require_narration_ready_for_video`; this is p750 human candidate/audio timeline approval plus hash binding, not a reviewer-model report. Retain if human audio selection remains a product requirement.
- Legacy narration generation and duration sync at `:176-199` runs `generate-assets`, `sync-manifest-durations-from-audio.py`, and `check-audio-duration-gate.py`. The shell currently blocks when duration gate requests scene/narration review prompts and prints their paths; remove the reviewer handoff but keep direct duration/file checks.
- Video request generation and freeze at `:204-225` retains provider request construction, asset guides, last-frame binding, and revision-aware freeze. `freeze-approved-render-inputs.py` calls `_require_narration_ready_for_video` at `:220-223`; retain as explicit human p750 binding if desired, but do not confuse it with a production reviewer agent.
- Render and final duration at `:227-255` (`render-video.sh`, `check-final-video-duration-gate.py`) remain deterministic media operations. The final state currently sets `review.video.status=pending` at `:257-262`; this is a human final-review handoff and may remain only if publishing still requires human approval.
- `verify-pipeline.py` at `:264-267` is excluded and is a major downstream hidden gate. It currently imports semantic review and stage evaluators and must be handled by its owner; the shell call itself is a production stop point.

`scripts/check-audio-duration-gate.py:162-305` is mixed. `_resolve_target_seconds`, `_ffprobe_duration_seconds`, `measure_manifest_runtime`, and `audit_duration` (`:63-87,90-135,201-243`) are deterministic runtime measurement and can remain. `build_duration_*_review_prompt`/`write_review_prompt` calls at `:264-277`, prompt paths in state at `:279-304`, and `slot.p740 failed → p750 blocked` as a request for agent review are **REMOVE**. Decide separately whether an under-target runtime should remain a direct deterministic error; it must not ask for or require a scene/narration reviewer report.

`scripts/check-final-video-duration-gate.py:110-178` is fully deterministic ffprobe + shared duration contract. Keep `_manifest_target_seconds` (`:73-107`), `audit_duration` (`:124-143`), and p920/p930 updates. The `review.final.duration_fit.*` key prefix is legacy naming, not a reviewer report; it should not be used as evidence of a model review.

`scripts/sync-manifest-durations-from-audio.py:234-424` probes actual audio and updates per-cut/per-scene duration and timestamps. Keep `_ffprobe_duration_seconds`, `update_one_duration`, and manifest total measurement. It has no reviewer model call. `scripts/render-video.sh:72-174` is ffmpeg-only and fully KEEP. `scripts/build-clip-lists.py:80-145,282-334` enforces render-unit coverage/order and writes concat/narration lists; fully KEEP.

`scripts/generate-elevenlabs-tts.py:63-184`, `scripts/generate-kling-video.py:55-217`, `scripts/generate-veo-video.py:32-161`, `scripts/generate-gemini-image.py:60-147`, `scripts/generate-seadream-image.py:60-130`, and `scripts/generate-placeholder-assets.py:294-341` are provider/file generators with credential, request, output, or ffmpeg conversion logic. None requires a reviewer report; KEEP. `scripts/import-codex-generated-image.py:20-111` is file selection/copy provenance and KEEP. `scripts/make-vertical-short.py:87-106,149-275` requires human `review.video.status=approved` and optional hybridization approval before recutting; list the mandatory review.video.status certificate as a related removal candidate; preserve the recut operation and any separately authorized publish action. It does not invoke a reviewer agent.

### Narration p720 helpers

`scripts/run-p720-narration-l3.py` is a production review loop despite being deterministic internally:

- `materialize_review_loop_round` at `:393` creates critic prompt/report state.
- It executes excluded `scripts/review-narration-text-quality.py` at `:397-408` and parses `unresolved_entries`/finding reports at `:426-431`.
- It synthesizes five critic reports and aggregate/final report at `:439-500`, then requires `narration_semantic_review_is_current` at `:501-512`.
- It writes p720/review/gate status and blocks p730 when semantic currentness is absent at `:513-547`; `--fail-on-findings` returns nonzero at `:569-606`.

Remove the reviewer loop, reports, semantic-currentness requirement, and fail-on-findings behavior. If p720 remains as a stage name, retain only deterministic narration schema/contract checks (`validate_audio_story_contract` at `:24-25,433-435`) and audio/TTS readiness; do not materialize critic artifacts.

`scripts/run-p720-narration-semantic.py` is wholly reviewer infrastructure: it imports `run_narration_semantic_critics` at `:24-28`, records five-critic running state at `:93-105`, executes the critic calls at `:108-115`, validates the aggregate and writes semantic report artifacts at `:147-177`, derives pass from semantic + deterministic review at `:178-218`, and exposes `--fail-on-findings` at `:255-285`. Remove from production invocation (generator call is `generate-assets-from-manifest.py:9053-9062`). Hashing the narration text for request invalidation can be retained in a non-review binding helper if needed.

`scripts/ai/toc-immersive-narration-multiagent.py:497-665` prepares full-run and per-scene narration authoring scratch. Its `authoring_status` lock handling (`:200-224,452-475`) and projection registry instructions are authoring behavior, not reviewer model calls; KEEP. `scripts/ai/merge-immersive-narration.py:128-177,259-328,434-447,450-623,626-857` validates structured audio-story authoring, preserves human-locked cuts, merges into `script.md`, and runs `sync-narration-from-script.py`; KEEP authoring/projection checks. The required `authoring_status`/`authoring_provenance` fields at `:144-176` are an authoring contract; do not replace them with reviewer approval. Any later code that treats `human_review.status` as a model-review pass should be split.

`scripts/sync-narration-from-script.py:76-91,168-238,481-553,901-1068` is the script→manifest projection and human change-request synchronizer. Keep preferred human fields, TTS materialization, narration revision, span refs, render-unit defaults, locks, and atomic rollback. The branch at `:1016-1067` invalidates final audio hashes and writes `review.narration.status=pending` / `gate.narration_review=required` after any change; this is a hidden re-review gate and should be split so stale audio/request provenance is invalidated without requiring a reviewer report. It may still require explicit human candidate approval when that feature is intentionally retained.

### Authoring and legacy multi-agent helpers

`scripts/author-story-with-codex.py:51-199,202-237` is a real authoring path: it reads structured research, runs architect/scene-author turns through `run_structured_story_turn`, writes prompt/output/provenance caches, calls `author_story_from_research`, and publishes only after deterministic story validation. KEEP. The imported author pipeline (`toc/story_author_pipeline.py:1361-1609`) uses author roles and scene-local deterministic repair turns; this is content authoring, not a production reviewer/critic, so KEEP. Its `validate_story_document` result is a schema/ID/lifecycle contract, not a score gate.

`scripts/build-immersive-script-from-manifest.py:149-244,247-277` deterministically projects manifest visual/narration into canonical `script.md`; KEEP. `scripts/ai/dispatch-toc-scene-series.py:16-39,42-131` dispatches research/story author tasks to scratch files; KEEP. `scripts/ai/toc-scene-series-multiagent.py:45-165` prepares scratch, queue, and single-writer phases; KEEP. `scripts/ai/merge-scene-series-scratch.py:20-66` merges scratch author notes; KEEP.

`scripts/ai/toc-immersive-cuts-multiagent.py:102-117,176-339` and `scripts/ai/merge-immersive-cuts.py:151-251,686-813` are explicitly legacy fixed-cut scaffolding. They reject canonical/provider/review fields in legacy scratch and require explicit legacy opt-in; that is schema isolation, not a reviewer pass. KEEP unless the legacy workflow is intentionally removed. The merge writes the next generation command at `merge-immersive-cuts.py:797-813`, which enters the shell pipeline described above.

`scripts/ai/multiagent.sh:70-125` is a generic tmux/improve launcher and does not itself run production reviewers; KEEP. `scripts/select-stage-playbooks.py:18-61` selects optional playbooks and writes a selection report; it is not a semantic review report, so KEEP. `scripts/build-run-index.py:16-24`, `scripts/validate-slot-contract.py:29-103`, and `scripts/validate-pointer-docs.py:15-74` are structural index/contract/pointer checks; KEEP.

## Grounding and hidden approval gates

The script wrappers call `toc.grounding` rather than implementing grounding themselves.

- `scripts/prepare-stage-context.py:18-39` calls `prepare_stage_context`; its description says “resolve, audit” and returns a readset. `scripts/resolve-stage-grounding.py:17-30` calls `run_stage_grounding` and exits nonzero unless status is `ready`. `scripts/audit-stage-grounding.py:24-54` loads reports/readsets, writes an audit, updates `stage.*.audit.*`, and exits nonzero unless audit is `passed`.
- `toc/grounding.py:359-488` resolves required docs/templates/inputs and also evaluates `requires_approved_input`, required state, manifest phase, and review policy. Required source existence, path containment, manifest phase, and readset order are **KEEP**. `approved_input_checks` at `:371-405` and required state keys that are review/eval statuses are **SPLIT/REMOVE** when they only require reviewer approval.
- `toc/grounding.py:561-584` creates readsets; `:587-657` builds the audit from contract versions, readset coverage, and file existence; `:666-763` recomputes currentness; `:766-809` writes audit state and retries; `:812-855` refuses to return context unless `report_ready`, `readset_exists`, and `audit_passed` are all true. Retain deterministic doc/input resolution and safe readset contents, but remove the “audit passed” evidence gate and the optional grounding audit subagent from production progression. Audit can remain an explicit diagnostic.
- `scripts/build-subagent-audit-prompt.py:41-85,88-111` builds a contextless grounding audit prompt and asks for `audit-stage-grounding.py` plus `status: passed`. This is an audit-only subagent rather than a content reviewer; under the requested boundary it should be **SPLIT**: keep a deterministic readset/path diagnostic if needed, remove agent invocation and the passed-report prerequisite.
- `workflow/stage-grounding.yaml:67-75` requires `review.story.status=approved` for script grounding when policy is required; `:86-93` requires `eval.p400_readiness.status=approved` for narration; `:108-111` does the same for asset; `:146-149` for scene implementation; `:167-190` requires image/narration review approval, p400 approval, and duration-fit pass for video generation. These are hidden gates reached via grounding and must be removed or replaced with structural prerequisites.
- `toc/review_mode.py:17-54` validates a bound `preapproved` create input. Removing reviewers means standard/preapproved must converge; retain create-input identity/source/hash checks if useful, but remove mode-specific “synthetic approved review artifact” behavior.

`scripts/migrate-audio-first-slot-contract.py:67-181` remaps old slots and grounding filenames. Keep manifest-phase migration, slot remap, state append, and optional grounding refresh. Its `STATE_PREFIX_REMAP` at `:48-56` and grounding refresh at `:127-135` copy review/subagent keys; do not make migrated review keys a new production gate.

## Resume, rebuild, and p500/p680 callers

`scripts/resume-from-p500.py` has a safe data-recovery core and a review-bearing continuation layer.

- `_resolve_resume_mode_contract` at `:664-803` validates experience/source/create mode and binds `review_mode` from authenticated state/create input. Keep source/run/create-input identity and exact hash checks; remove standard/preapproved branches whose only effect is reviewer skipping or synthetic approval.
- `_resume_state_updates` at `:1436-1535` writes p500/p600 supervisor state but also sets `runtime.stage=image_prompt_semantic_review_pending`, `review.policy.*`, `gate.*`, `review.*=approved/pending`, and p630/p640/p680 semantic-review notes. Keep slot/artifact progress and supervisor state; remove reviewer status/approval requirements.
- `_write_resume_orchestration` at `:1538-1631` materializes p500/p600 supervisor result files and progress. Keep L2 orchestration and required-artifact bookkeeping; drop review-only result fields if they become mandatory.
- `materialize_from_p500` at `:1634-1750` safely restores world-walk references, recompiles image prompt payloads, writes asset artifacts, and materializes requests. Calls to frontend `_refresh_p400_review_artifacts` / `_require_fresh_p400_readiness` at `:1730-1739` are hidden reviewer gates and must be removed/split. Keep `_archive_p400_review_evidence` only if historical copies are explicitly desired; it currently copies old reviewer reports/eval/semantic files (`:1753-1820`) and should not be required to continue.
- `_prepare_stage_context` / `_prepare_resume_grounding` at `:1823-1854` reenter `prepare-stage-context.py`; retain grounding resolution but remove audit-passed dependency. `_mark_resume_dependency_sync_complete` at `:1857-1882` writes `review.semantic.*.dependency_sync`; remove review naming/status if no longer used, while preserving dependency synchronization state.
- `_finalize_resume_orchestration` at `:1902-1952` validates p500/p600 supervisor result JSON, terminal slots, and progress memo. Keep as L2 structural orchestration. `_continue_run` at `:1955-2077` calls frontend `run_pre_media_semantic_pipeline` at `:2014-2021`, `generate_images` at `:2022-2043`, and `frontend.validate` at `:2044-2053`; remove semantic reviewer invocation/pass requirement while retaining provider, file, identity, and request validation.
- CLI dry-run/apply token, lock, checkpoint, source, and world-walk checks at `:2079-2330` are recovery/security behavior and remain. `--materialize-only` help at `:2107-2111` currently promises semantic materialization; rename/redefine after semantic reviewer removal.

`scripts/rebuild-from-p400.py:43-101,108-169` only reads bounded candidate bytes and performs checkpointed prepare/apply/recover through `toc.p400_rebuild`; no reviewer call is present. KEEP. Its candidate path/symlink/size/identity controls are structural.

The frontend-owned p650/p680 path is reached indirectly from resume and generator. Current script-side callers that must be removed or changed are:

- `resume-from-p500.py:1731-1739` → frontend p400 refresh/readiness.
- `resume-from-p500.py:2016-2020` → frontend pre-media semantic pipeline.
- `resume-from-p500.py:2023-2043` → frontend image generation and p680/p650 handoff; keep media generation, split any semantic pass parameter.
- `resume-from-p500.py:2045-2053` → frontend validation; preserve deterministic validation only.
- `generate-assets-from-manifest.py:9022-9062` → excluded image/narration reviewer scripts.

The excluded frontend file has its own direct semantic calls at `scripts/toc-immersive-frontend-run.py:2037-2040,12423-12567,13027-13030,13978-14018`; another agent owns those removals. This inventory records them because p650/p680/resume cannot be review-free while these callers remain.

## Review-only helper scripts and report artifacts

These scripts are in the current `scripts/` tree and should be removed from production invocation or converted to optional diagnostics:

| path | exact entry points | why it is review-only |
|---|---|---|
| `scripts/build-subagent-story-review-prompt.py:27-85,95-115` | `build_subagent_story_review_prompt`, `main` | instructs a judgment subagent to score candidates and emit `approved|changes_requested`, `overall_score`, and candidate scores |
| `scripts/build-subagent-image-review-prompt.py:34-102,105-126` | `build_subagent_image_review_prompt`, `main` | asks a contextless image quality/reveal reviewer to run review script and return hard blockers/status |
| `scripts/build-subagent-duration-scene-review-prompt.py:21-48` | `main` | writes scene-duration subagent prompt and state path |
| `scripts/build-subagent-duration-narration-review-prompt.py:21-48` | `main` | writes narration-duration subagent prompt and state path |
| `scripts/build-image-prompt-judgment-review.py:106-155,158-302,311-380` | `collect_review_entries`, `render_review_collection`, `build_judgment_prompt`, `main` | materializes judgment collection/scope/prompt/report, agent/human flags, and `overall_score`; remove the review pack, or split plain request collection from judgment metadata |
| `scripts/export-image-prompt-collection.py:28-85,88-148,151-163` | `ExistingReviewState`, `load_existing_review_states`, `render_collection`, `main` | carries `agent_review_ok`, reason keys/messages, and human-review state into a review collection; retain only a plain prompt collection if still useful |
| `scripts/build-semantic-review-pack.py:69-70,101-174,214-390,393-516,694-907,943-1033,1072-1095` | `render_scope_json`, `image_prompt_scene_shard_plan`, `materialize_image_prompt_scene_shards`, `entry_diagnostics`, `render_report_template`, `render_prompt`, `build_pack`, `main` | writes semantic collection/scope/prompt/report, shard review instructions, failed selectors, semantic status, and reviewer criteria. Keep deterministic entry collection, exact-once shard/path/hash diagnostics only if promoted to a normal structural validator; remove prompt/report/state/pass artifacts |
| `scripts/run-p720-narration-l3.py` | see p720 section | deterministic review + critic report loop and semantic currentness |
| `scripts/run-p720-narration-semantic.py` | see p720 section | five contextless semantic critics and aggregate pass |
| excluded `scripts/review-*.py` | wrappers call `toc.stage_review_cli` or quality reviewers | another agent owns removal; callers are listed above |
| excluded `scripts/run-semantic-review.py` | semantic reviewer/repair orchestration | another agent owns removal; server/frontend invoke it indirectly |
| excluded `scripts/build-review-loop-round.py` | `materialize_review_loop_round` wrapper | another agent owns removal; ride has an in-file equivalent |
| `scripts/review-pr.sh` | `main`-style shell copy of PR review template | generic software development review, outside production story/video scope; leave untouched |

`toc/review_loop.py:242-366,846-939,943-1134` and `toc/review_loop_runner.py:25-122` are the shared implementation behind the script helpers. `REVIEW_LOOP_SPECS` names the production reviewer stages and final reports (`research_review.md`, `story_review.md`, `visual_value_review.md`, `script_review.md`, `production_readiness_review.md`, scene/cut reports, `narration_text_review.md`, `asset_review.md`, `manifest_review.md`, image/video reports, and `run_report.md`). Remove these stage specs/runner use from production, while retaining ordinary run reports generated from actual runtime state if they are no longer reviewer outputs. `loop_state_updates` at `toc/review_loop.py:846-872`, critic/aggregator prompt builders at `:875-1090`, and critic report validator at `:1093-1134` are report/status/digest infrastructure and are REMOVE.

## Structural/provenance checks to preserve or split

The following checks are often labeled “review” but protect execution correctness and should survive in a no-review pipeline:

- YAML/JSON parsing, exact field shapes, scene/cut IDs, event ownership, handoff references, reveal constraints, request selector uniqueness, and no-TODO authoring contracts (`toc/story_authoring.py`, `toc/stage_evaluation/manifest.py`, generator validators).
- Grounding required doc/template/input existence and path containment, plus readset contents/order. Remove only the agent/audit-passed prerequisite.
- Human change request IDs and target selectors (`generate-assets-from-manifest.py:9177-9182`, `sync-narration-from-script.py:901-1032`).
- Image/video request snapshots, request revision, compiler/prompt SHA-256, reference path/content SHA-256, provider binding, output destination, model/backend/options, and current file bytes (`generate-assets-from-manifest.py:7941-8024,8272-8397`; shared image request snapshot tests).
- Image/video/audio file existence, decode, ffprobe duration, render-unit coverage/order, and final render output (`build-clip-lists.py`, `render-video.sh`, duration gates).
- Run-root pinning, symlink/hardlink/FIFO rejection, locks, atomic writes, checkpoint tokens, world-walk source identity and reference restore (`toc-immersive-ride.py:348-1007`, `resume-from-p500.py:69-342,1005-1433`, `rebuild-from-p400.py:43-101`).
- Author model calls and deterministic author validation (`author-story-with-codex.py`, `toc/story_author_pipeline.py`); an author repair turn is not a reviewer report and should not be removed solely because its role is named `repair`.
- Human hybridization approval and human image/audio/video selection UI remain separate product decisions. A reviewer-agent gate can be removed without deleting candidate management or an explicit human publish approval.

The main mixed function is `toc.stage_evaluation.manifest.check_manifest_single` (`toc/stage_evaluation/manifest.py:1125-1294`): retain file/phase, grounding, duration, selector, adaptation contract, cut-contract, reveal, human-change, and structural scene checks (`:1135-1245,1266-1285`); remove `_review_report_issues` (`:308-334`), `_review_loop_integrity_issues` (`:337-443`), the `require_review_artifacts` branch (`:1247-1265`), automatic rubric/score publication (`:1286-1288`), and any `eval.p400_readiness` result that is derived solely from removed review checks (`:1289-1293`). The same split applies to any caller passing `require_review_artifacts=True`.

The excluded verifier is another hidden path: `scripts/verify-pipeline.py:51-79` imports `check_semantic_review`, `check_image_prompt_judgment`, `score_from_checks`, and the shared manifest evaluator; `append_semantic_review_check` at `:470-512` turns semantic report pass/localized failure into a rubric check. `build_report` at `:2237-2334` runs stage checks and computes `overall.score`/`overall.passed`; `render_run_report` at `:2337-2401` exposes the score and review gates. These are owned by the verifier agent, but every shell/session/bootstrap caller must stop treating this report as a production prerequisite. In the imported stage code, `toc/stage_evaluation/research_story.py:768-792` requires current story semantic artifacts when review policy/artifacts are present, and `:900-908` publishes story rubric score; `toc/stage_evaluation/video.py:49-96` checks `review.video.status`, `quality_check.review_contract`, and publishes `eval.video.score`. Keep file/narration/duration/provenance checks after removing these review/status/score branches.

Server-owned subprocess callers of script review infrastructure, for coordination with the server inventory, are `server/image_gen_app.py:4004-4018,14023-14045` (image prompt reviewer), `:16208-16228,16442-16461,17728-17747` (verify-pipeline), `:18885-18908,21873-21896,23025-23048,24029-24052` (build semantic review pack), and `:30178-30192` (p720 narration runner). The script inventory does not modify these locations, but removing only the script-side checks will leave these direct launches in the create/resume runtime.

## Tests directly affected

The test suite has many tests whose assertions encode the old reviewer contract. The names below are the exact current symbols and the expected treatment. Structural/provenance tests are listed so implementation does not over-delete them.

### Remove or rewrite because they assert reviewer prompts, reports, scores, or approval gates

- `tests/test_toc_immersive_ride_scaffold.py:1005-1147` (`test_scaffold_p410_materializes_only_scene_reviews`, `test_scaffold_p420_materializes_cut_review_but_not_script_review`, `test_scaffold_p435_materializes_production_readiness_after_script_review`, `test_scaffold_p430_materializes_script_review_without_production_readiness`); `:1149-1199` (`test_scaffold_p410_rewind_invalidates_later_p400_reviews_and_approval`); `:1255-1305` (`test_approved_p435_continues_to_p500_without_rewriting_p400_evidence`, `test_approved_p435_continues_to_p610_with_production_bound_p400_evidence`); `:1455-1488` (`test_scaffold_p500_requires_p400_readiness_gate`). These assert prompt files and `eval.*`/approval state.
- `tests/test_build_subagent_story_review_prompt.py:21-65` (`TestBuildSubagentStoryReviewPrompt` and its two tests), `tests/test_build_subagent_image_review_prompt.py:22-76` (`TestBuildSubagentImageReviewPrompt` and its two tests), `tests/test_build_subagent_duration_review_prompts.py:29-122` (`TestBuildSubagentDurationReviewPrompts`), and `tests/test_build_image_prompt_judgment_review.py:23-144` (`TestBuildImagePromptJudgmentReview`). They assert reviewer prompts, report paths, agent flags, and scores.
- `tests/test_p720_l3_narration_runner.py:186-386` (`TestP720L3NarrationRunner` all tests) and `tests/test_p720_narration_semantic_runner.py:139-359` (all six tests) assert five critics, semantic currentness, reports, and fail-on-findings. Remove or replace with deterministic narration shape/audio tests.
- `tests/test_narration_review_gate.py:56-81` (all shared deterministic review gate tests) and `tests/test_narration_semantic_review.py:171-829` (critic profiles, private app-server critic calls, aggregate/currentness, and report tests) encode the p720 reviewer contract. Preserve only non-review text/projection helpers if tests are split.
- `tests/test_review_loop.py:78-696` (`TestReviewLoop`), `tests/test_review_loop_contract.py:120-148`, and `tests/test_semantic_review.py:498-1651` are review-loop/semantic report currentness, digest, critic count, repair, and score contracts. Remove the production-gate portions; retain only tests explicitly repurposed for deterministic structural selectors/provenance.
- `tests/test_build_subagent_audit_prompt.py:21-114` (`TestBuildSubagentAuditPrompt`) must be rewritten to test deterministic readset/path diagnostics without requiring an audit subagent or `audit.status=passed`.
- `tests/test_audio_duration_gate.py:142-199` (`test_gate_ignores_spoofed_metadata_and_fails_at_79_9_percent`, `test_gate_passes_at_80_percent_and_has_no_upper_bound`, `test_incomplete_measurement_fails_even_when_metadata_claims_long_runtime`) currently require duration review prompt files and `slot.p740/p750` review states. Keep duration measurement assertions, remove prompt/report/agent expectations, and decide the direct runtime failure contract.
- `tests/test_stage_grounding.py:164-215` (`test_script_grounding_requires_approved_story`, optional/preapproved variants), `:248-385` (audit CLI/currentness tests), and `:428-449` (serialized readset currently tied to audit) encode approval/audit gates. Rewrite around required input/readset existence and optional diagnostics.
- `tests/test_stage_evaluator_scripts.py:2125-2168` (`test_story_required_semantic_review_is_missing_or_stale_fail_closed`), `:2470-2690` (script evaluator approval tests), `:3195-3216` (`test_manifest_evaluator_gates_p400_duration_and_review_integrity`), `:4084-4104` (p400 readiness/preapproved coverage), and `:4335-4355` (`test_downstream_grounding_requires_p400_readiness_approval`) encode removed review/pass dependencies. Keep adjacent structural scene/event/duration/contract tests.
- `tests/test_semantic_pack_scene.py:606-644`, `tests/test_semantic_pack_video.py:208-264,403-446,842-1023`, `tests/test_semantic_pack_image.py:405-545`, `tests/test_semantic_pack_foundation.py:283-358`, and `tests/test_semantic_review_workspace_security.py:479-1631` assert reviewer guidance, report/critic packs, semantic reviewer workspace, and producer repair. Remove review-agent expectations; retain safe source/path/hash tests if the pack is split into a structural diagnostic.
- `tests/test_image_prompt_repair_freeze.py:359-416,622-830,859-1068,1276-1698` has reviewer/report-bound repair tests mixed with request freeze/provenance. Remove reviewer-gate assertions; keep exact manifest/request hash, lock, output provenance, and transactional rollback tests.
- `tests/test_toc_state_script.py:21-167` (`test_ensure_append_approve_show`) asserts image/video review labels and approval commands; split human approval assertions from removed reviewer status presentation. `:231-268` (`test_sync_embeds_eval_report`) should retain only if `eval_report.json` remains an ordinary runtime diagnostic, not a required score/report.
- `tests/test_sync_narration_from_script.py:144-204` (`test_sync_prefers_human_review_fields`) may remain as human edit precedence, while tests or assertions for reopening `gate.narration_review` after sync must be rewritten. `:489-623` and `:727-1047` are projection/change-request/render-unit structural tests and should remain.
- `tests/test_p500_resume.py:2734-2948` (`test_materialize_refreshes_p400_grounding_before_snapshot_freeze`), `:2949-3144` (`test_materialize_recompiles_repaired_image_prompt_before_first_p400_gate`), `:4140-4180` (`test_archives_p400_review_evidence_before_refresh`) assert review snapshot/archival gates and must be removed or rewritten. `tests/test_create_resume_duration.py:1029-1081` and `:1083-1164` cover mode re-resolution; retain identity/security but remove reviewer-mode behavior.
- `tests/test_toc_immersive_frontend_run.py:318-360,1172-1808,1909-2404` (frontend-owned) asserts semantic review pipeline, p400 review materialization, preapproved synthetic reports, and reviewer failures. Another agent owns implementation, but these tests must be coordinated with this script inventory.
- `tests/test_narration_frontend_workflow.py:156-330,1018-1068,1435-1466` and `tests/test_frontend_duration_gate.py:49-152` are frontend-owned reviewer/duration gate tests; preserve candidate/file/timeline checks and remove reviewer report/pass requirements.
- `tests/test_verify_pipeline.py:2125-2168,3195-3419` and related semantic/review sections are excluded verifier tests; another agent must remove score/report/orchestration reviewer assertions while retaining structural/provenance cases.

### Keep as structural, provenance, media, lock, or authoring coverage

- `tests/test_toc_immersive_ride_scaffold.py:218-381,433-757,802-953,1201-1233,1307-1420,1490-1540`: stage-target normalization, source receipt/path security, world-walk source binding, safe rewind, authoring placeholders, and handoff slot shape. Update expected review fields only where necessary.
- `tests/test_toc_run_scaffold.py:8-9` (`TestTocRunScaffold.test_scaffold_creates_expected_files`) and `tests/test_toc_scene_series_scaffold.py:7-8` (`TestTocSceneSeriesScaffold.test_scaffold_creates_root_and_scene_grounding_artifacts`): retain scaffold and grounding file checks; remove review-state expectations if present.
- `tests/test_final_video_duration_gate.py:52-150` (`FinalVideoDurationGateTests`) and the deterministic portions of `tests/test_audio_duration_gate.py:95-140`: retain ffprobe/80% threshold/target fallback and shell order checks.
- `tests/test_generate_assets_narration_guard.py:19-116`: revision-aware cut detection, render-target order, and shared-reference structural guards; retain.
- `tests/test_build_clip_lists.py:15-374`: render-unit inventory, deleted-cut exclusion, exact coverage/order, and duplicate assignment; retain.
- `tests/test_image_request_snapshot.py:55-1334` and `tests/test_verify_pipeline_image_provenance.py:30-90`: request/reference/output provenance and atomic safety; retain.
- `tests/test_codex_app_server_transport.py:23-675`, `tests/test_runtime_locks.py:21-603`, and `tests/test_run_root_binding.py:37-1729`: transport, locks, root identity, atomic file/state IO, and race safety; retain.
- `tests/test_story_authoring.py:201-229`, `tests/test_story_author_pipeline.py:120-380`, `tests/test_story_author_runtime.py:17-161`, `tests/test_story_author_integration_contract.py:9-19`, and `tests/test_story_lifecycle_downstream_projection.py:287-359`: author model envelope, deterministic validation, repair-locality, and downstream projection; retain.
- `tests/test_immersive_cuts_multiagent.py:141-939` and `tests/test_immersive_narration_multiagent.py:22-1205`: legacy scratch schema/path safety and authoring merge behavior; retain, except any assertions that require a reviewer pass.
- `tests/test_sync_manifest_durations_from_audio.py:1-` (all duration sync tests), `tests/test_freeze_approved_render_inputs.py` (render freeze contract), `tests/test_tts_text.py`, `tests/test_elevenlabs_request_payloads.py`, and provider tests: retain request/media behavior and separate human approval semantics.

## First implementation pass implied by this inventory

The removal must be done from both sides of each gate. Deleting only reviewer scripts leaves callers blocked on missing reports; deleting only caller checks leaves prompt/report generation and state artifacts active. The minimal dependency cuts are:

1. Remove review-policy arguments/state from script scaffold wrappers and make standard/preapproved converge.
2. Remove `toc-immersive-ride.py` review-loop materialization and change p400 readiness to structural-only.
3. Split `toc.stage_evaluation.manifest.check_manifest_single` and grounding so `review_report_integrity`, `review_loop_integrity`, review scores, and `audit_passed` are not prerequisites.
4. Remove generator subprocess calls to image/narration reviewers and replace video “reviewed artifact + approved state” with current compiled request/payload/provenance validation.
5. Remove p720 critic/semantic runners and duration prompt handoff; retain deterministic narration/audio/runtime checks.
6. Remove resume calls that refresh or require p400 semantic evidence and pre-media semantic review; preserve checkpoint/source/request/file/lock safety.
7. Update only tests whose names above encode reviewer existence/pass/score/report; keep structural, provenance, media, authoring, and human-selection tests.
