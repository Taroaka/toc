# Tasklist: Delta-based run state store

## Phase 0: Safety and baseline

- [x] 現在の Cinderella resume process が終了するまで shared runtime code / canonical docsを変更しない
- [x] current dirty worktreeの対象差分を分類し、state refactorが既存修正を上書きしないことを確認する
- [x] 448 MB Cinderella stateのsnapshot count、read/update/resume時間をbaseline artifactへ記録する
- [x] state writer / reader / direct file access / run_status consumer mapを作る

## Phase 1: Contract tests first

- [x] legacy full snapshot replay testを追加する
- [x] legacy partial blockを含むglobal last-write-wins replay testを追加する
- [x] delta-only last-write-wins replay testを追加する
- [x] legacy snapshot + delta mixed replay testを追加する
- [x] delta blockがchanged keysだけを含むtestを追加する
- [x] same-value updateを省略するtestを追加する
- [x] malformed / partial tailをcurrent stateに取り込まないtestを追加する
- [x] commit digest / previous commit / sequence mismatch testを追加する
- [x] duplicate event ID retryのidempotency testを追加する
- [x] missing / corrupt / stale / ahead current view testを追加する
- [x] two-writer no-lost-update testを追加する
- [x] append commit後・view publish前crash recovery testを追加する
- [x] symlink / root identity / inode replacement security regression testを追加する
- [x] direct state writer guard testを追加する

## Phase 2: Shared state store

- [x] `toc/state_store.py` を追加する
- [x] delta envelope parser / serializer / digest helperを実装する
- [x] legacy + delta streaming replayを実装する
- [x] `state.current.json` schema / validator / atomic publisherを実装する
- [x] exclusive transaction lock内のread-current / merge / append / publishを実装する
- [ ] partial tail recovery reportを実装する
- [ ] structured performance instrumentationを実装する

## Phase 3: Reader consolidation

- [x] `toc.harness.parse_state_file` をshared store wrapperにする
- [x] frontend runnerのactive-root state readerをshared storeへ置換する
- [x] server / resume / grounding / verifier / index builder readersを置換する
- [x] `run_status.json` をcurrent read sourceとして使う箇所がないことを確認する
- [x] run index / server image / headless / shell helperのduplicate readerをshared storeへ統合する
- [x] legacy fallbackがfull replay後にcurrent viewを作ることを確認する

## Phase 4: Writer consolidation

- [x] `toc.harness.append_state_snapshot` をdelta update wrapperにする
- [x] frontend runnerの独自full snapshot builderを削除する
- [x] p500 resume / immersive rideの独自full snapshot writerを削除する
- [x] legacy AI merge / multiagent direct writerをshared APIへ統合する
- [x] watchdog / shard / repair / slot / approval writersをshared APIへ統合する
- [x] state update中のderived projection生成をcanonical commitから分離する
- [x] direct `append_run_file_text(..., "state.txt")` 呼出しをlow-level store内だけに限定する
- [x] empty heartbeat / same-value updateの増殖を抑制する

## Phase 5: Migration and recovery tooling

- [ ] inactive legacy run用migration dry-run / exact-token / apply commandを追加する
- [ ] active create/resume/image leaseを拒否するtestを追加する
- [ ] migration planにrun identity / state digest / view digestを束縛する
- [x] p500 resume plan tokenをevent head seq/hashへ束縛する
- [x] migrationがlegacy state bytesを変更しないtestを追加する
- [ ] view rebuild / integrity audit commandを追加する
- [x] optional physical compactionは別proposalに分離する

## Phase 6: Canonical docs and schemas

- [x] `docs/data-contracts.md` のcanonical/derived state契約をdelta方式へ更新する
- [x] `docs/system-architecture.md` のstate store / recovery / ownershipを更新する
- [x] `docs/root-pointer-guide.md` のState節へ`state.current.json`を追加する
- [x] `docs/orchestration-and-ops.md` のconcurrency / recovery運用を更新する
- [x] `workflow/state-schema.txt` にstorage metadataとkey policyを追加する
- [x] `docs/implementation/assistant-tooling.md` にwriter API制約を追加する
- [x] AGENTS / CLAUDE pointer自体に詳細を重複させない

## Phase 7: Integration and performance

- [x] grounding preflight integration testを追加する
- [x] semantic watchdog高頻度update integration testを追加する
- [ ] frontend create p680 integration testを追加する
- [x] p500 resume dry-run/apply integration testを追加する
- [x] approval / index / run_status regeneration testを追加する
- [x] stale projection writerが新しいrun_status/indexを上書きしないtestを追加する
- [x] state commit後のartifact failureがcanonical eventをrestore/truncateしないtestを追加する
- [ ] 10,000 delta update growth benchmarkを追加する
- [ ] 500 MB legacy + warm current view read benchmarkを追加する
- [ ] update p95 / bytes-read regression thresholdを固定する

## Phase 8: Verification and rollout

- [x] targeted unit testsを実行する
- [x] state / resume / grounding / semantic integration testsを実行する
- [ ] Python lint / type / full relevant test suiteを実行する
- [x] pointer docs / slot / schema validatorsを実行する
- [x] security reviewを実行する
- [x] code-review subagentのCritical / High / Medium findingsを解消する
- [ ] inactive fixture runでmigration / rollback drillを実行する
- [ ] new frontend runでdelta defaultを確認する
- [ ] current Cinderellaはactive process終了後、別checkpointと明示確認を経てmigrationする
