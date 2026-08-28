# Tasklist: Scene semantic review shift-left

## Phase 0: Baseline and fixtures

- [ ] 現在の Cinderella scene-set findings を stable regression fixture へ抽出する
- [ ] known-bad fixture と corrected fixture を作り、canonical event / reveal / role / handoff / time-location / evidence の期待結果を固定する
- [ ] 現行 pipeline の semantic attempts、producer repair rounds、wall-clock metrics を baseline として記録する

## Phase 1: Contract tests first

- [x] `scene_set_authoring_contract_v1` の valid fixture test を追加する
- [x] duplicate / missing canonical event ownership の failure test を追加する
- [x] reveal rollback / unauthorized reveal の failure test を追加する
- [x] role binding / participant / visible actor closure の failure test を追加する
- [x] handoff producer / consumer / state mismatch の failure test を追加する
- [x] location route / time transition cue の failure test を追加する
- [x] non-replaceable source ref / visual evidence の failure test を追加する
- [x] causal proof reference shell の failure test を追加する
- [x] marker-less legacy compatibility test を追加する
- [x] markerありpartial contract / unsupported versionのfail-closed testを追加する
- [x] generic proseが存在してもrequired ID reference不足ならfailするtestを追加する

## Phase 2: Canonical registry and validator

- [x] `toc/scene_acceptance_contract.py` を追加する
- [x] criterion ID / reason key / owner / required input / authoring instruction / reviewer instruction を単一 registry にする
- [x] contract schema / marker / stable digest helper を追加する
- [x] event / beat / evidence / role / character / handoff / transition / reveal ID grammarとexact reference validatorを追加する
- [x] `source_ref_v1` のartifact digest / JSON Pointer / expected ID validatorを追加する
- [x] whole-set contract validator と per-scene preflight validator を実装する
- [x] deterministic-owned reason keys と semantic-owned reason keys を分離する
- [x] registry version / canonical digest / alias /廃止規則を実装する
- [x] canonical reason keyをstage/criterion namespace化し、legacy aliasを`(stage, old_key)`で解決する
- [x] registry と reviewer prompt / template key の drift / same-version digest mismatch test を追加する
- [x] domain-separated canonical JSONと`sha256:<hex>` digest規則を実装する

## Phase 3: Docs, templates, grounding

- [x] `docs/story-creation.md` に whole-set planning -> scene authoring -> preflight -> cut authoring の順序を追加する
- [x] `docs/data-contracts.md` に marker、artifact、state、digest、escape telemetry を追加する
- [x] `docs/implementation/agent-roles-and-prompts.md` に planner / author / independent reviewer の責務を追加する
- [x] `workflow/script-template.yaml` にコメント付き authoring contract を追加する
- [x] `workflow/scene-outline-template.yaml` に contract slice ref と computed-only `authoring_preflight` を追加する
- [x] `workflow/video-manifest-template.md` に canonical ref / digest projection を追加する
- [x] `workflow/stage-grounding.yaml` の story / script / scene implementation readset を更新する
- [x] 会話履歴を持たない agent が template と docs だけで valid contract を出せる grounding test を追加する

## Phase 4: Two-pass authoring

- [x] `_build_script_and_manifest()` 内を whole-set planning / preflight / cut materialization の二段階に分離する
- [ ] scene-set contractをreview済みsourceからscene作成前に構築する唯一のauthoring rootにする
- [x] 既存 `canonical_event_coverage_matrix` をscene-set contractからの一方向compatibility projectionへ変更する
- [x] scene-set contract / matrix / scene draft のownership exact projection testを追加する
- [ ] event ownership / reveal / role / time-location / handoff を個別 scene heuristic より先に構築する
- [x] contract validation / freeze 後だけ scene draft authoring を開始する
- [x] scene generation prompt に current contract slice と criterion authoring instructions を投影する
- [x] strict `scene_draft_v1` output contractとdigest bindingを実装する
- [x] participants visibility / role / beat / evidence shapeとincoming/outgoing handoff_refs shapeを実装する
- [x] AI authorがcontract ID / ownership / source digestを変更できないgateを追加する
- [ ] `include_artifact` / keyword role inference / generic handoff を source of truth から candidate helper へ降格する
- [x] 全 scene draft の preflight pass 後だけ cut coverage / cut contract / manifest を作る二段階 flow にする
- [x] generation stagingとpublish journalを追加し、preflight前のcanonical writeを禁止する
- [x] hard-coded `agent_review.status=passed` と review summary の自己承認を、preflight / independent review status に置き換える

## Phase 5: Preflight artifacts and routing

- [x] run-local authoring contract / per-scene preflight / aggregate preflight artifact を materialize する
- [x] append-only state keys を追加する
- [x] generation ID、contract / registry / source / preflight digestをstateへ追加し、source変更時のinvalidationを実装する
- [x] deterministic preflight failure で cut / request materialization を停止する
- [ ] preflight failure時にcanonical script / manifest / requestがpublishされないtestを追加する
- [ ] planner-level failure と scene-level failure を別 routing にする
- [ ] targeted local repair は failed scene と adjacent handoff だけを対象にする
- [ ] targeted repairを1 scene最大1回・scene-set全体最大3回に制限する
- [ ] repair時にnew generationを作りwhole-set preflightとsemantic invalidationを再実行する
- [ ] source meaning / event ownership change を human approval へ送る
- [ ] all-scene mandatory extra critic turn を追加しないことを integration test で固定する

## Phase 6: Independent reviewer binding

- [ ] `toc/semantic_pack_image.py` のdownstream cut / image projectionをcontract / preflight digest currentnessへ束縛する
- [x] `toc/semantic_pack_scene.py` の scene-set / scene-detail pack を frozen contract slice / digest / registry version に束縛する
- [x] role / reveal / handoff を reviewer pack 作成時に別 heuristic で再推論しない
- [x] `toc/review_loop.py` の criterion ID / reason key を registry projection にする
- [x] `server/image_gen_app.py` の scene-set prompt reason keys を registry projection にする
- [x] reviewer scope を contract digest に束縛する
- [x] reviewer scopeをgeneration / source / preflight / registry digestへ束縛し、mismatchをprovider前に拒否する
- [x] deterministic-owned final finding を `shift_left_escape` として記録する
- [x] escape を pass に変換せず、block と defect telemetry の両方を維持する
- [x] deterministic-owned findingをsemantic producer repairへ送らずauthoring defect routingへ戻す
- [ ] scene_detail / cut_blueprintがpreflight-owned criterionをproviderで重複審査しないtestを追加する

## Phase 7: Current Cinderella migration

- [x] `p400_rebuild_plan_v1` のrun identity / state digest / source digest / replace / invalidate / reuse policy / plan-token schema testを追加する
- [x] prepare段階でcandidateをstagingにbuildし、contract/script/manifest/preflight/registry/implementation digestをplan tokenへ束縛する
- [x] applyがcandidateを再生成せずprepare済みbytesだけをpublishするtestを追加する
- [x] research / story / visual_value を preserve し、script / manifest / p400 review / p500+ を checkpoint する専用 entrypoint を実装する
- [x] same create/resume lock、single-use plan token、commit journal、crash recovery、rollbackを実装する
- [x] staged p400 validation完了前にactive runを変更しないtestを追加する
- [x] apply途中失敗時に旧p400を復元しappend-only rollback stateを残すtestを追加する
- [x] 旧p500 selector / request / asset / imageがactive pathへ残らないtestを追加する
- [x] queued/running bulk jobを拒否し、p410+ slot / runtime.resume.p500 / artifact / orchestration stateをappend-onlyでinvalidateする
- [x] p000_index.md / run_status.jsonをnew stateから再生成する
- [x] selector / manifest変更時のp500+ reuseをv1で禁止する
- [ ] `resume-from-p500.py` の責務を変更しない regression test を追加する
- [ ] current Cinderella で dry-run を確認し、user approval 後だけ apply する
- [ ] rebuilt p400 が new contract / preflight / independent scene-set review を通ってから p500 へ進むことを確認する

## Phase 8: Verification and rollout

- [ ] known-bad Cinderella fixture が provider call 前に期待 reason key で fail することを確認する
- [x] corrected fixture が preflight pass 後に cut materialization へ進むことを確認する
- [x] marker-less legacy fixture を確認する
- [x] markerありpartial / unsupported version fixtureを確認する
- [x] contract freeze後のsource / script / registry変更でdigest mismatchになることを確認する
- [ ] provider call数、repair round数、prompt slice size、preflight p95の上限を確認する
- [ ] semantic aggregate attemptとshard provider turnを別metricとして検証する
- [x] targeted unit / integration / frontend create tests を実行する（新規target、既存first-frame除外、Cinderella provider prompt回帰がpass）
- [x] pointer docs / stage grounding / slot contract validators を実行する
- [ ] baseline と比較して semantic attempts / repair rounds / total time を報告する
- [x] code-review subagent を実行し、Critical / High / Medium findings を解消する
- [ ] golden run 合格後に新規 frontend create の marker を default にする（実装上はdefault、golden run未実施）
