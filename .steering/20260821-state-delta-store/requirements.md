# Requirements: Delta-based run state store

## Goal

ToC の全 run state を、完全 snapshot の反復追記から append-only delta event へ移行する。
既存の state key と last-write-wins の意味は維持し、履歴監査、crash recovery、同時更新の安全性を失わずに、state read / write の計算量を現在の履歴サイズから切り離す。

## Problem statement

現行の `append_state_snapshot()` は、更新対象が数 key だけでも `state.txt` 全体を読み、全 key を含む完全 snapshot を末尾へ追記する。
長時間 run では watchdog / shard / slot / repair の進捗更新が多数発生するため、同じ key/value が何千回も複製される。

現在の Cinderella run では、約 6,914 snapshot、約 448 MB、1 snapshot 平均約 65 KB まで肥大化した。
新しい更新ごとに巨大な履歴全体を parse するため、resume の dry-run、grounding、state update のローカル処理だけで分単位の遅延が発生する。

## Success criteria

- `state.txt` は唯一の canonical state history であり、append-only を維持する。
- 各 state transaction は、変更された既存 key と transaction metadata だけを1 blockとして追記する。
- 同じ key の最後の値が current state になる既存の last-write-wins semantics を維持する。
- 新しい概念を追加する場合を除き、保存方式の移行だけを理由に state key を複製・改名しない。
- `state.current.json` は canonical log から自動生成される materialized view とし、process が直接編集しない。
- `run_status.json` と `p000_index.md` は `state.current.json` の current state から生成する derived presentation artifact とする。
- current view が削除、破損、stale の場合、`state.txt` から決定的に再構築できる。
- legacy full-snapshot block と delta block を同じ parser で順番に replay できる。
- legacy block は実際には partial block を含むため、「最後のblockだけ」ではなく全blockをglobal last-write-winsでreplayする。
- legacy run の migration は過去の `state.txt` を置換・切詰めせず、最初の delta transaction と current view を追加する。
- すべての state writer は一つの transaction API を使用し、`toc/harness.py` と frontend runner が別実装を持たない。
- read-current、merge、delta append、current-view publish は同じ run-scoped exclusive lock の下で行い、lost update を防ぐ。
- append commit 後、current-view publish 前に crash しても、次回 read で log tail を replay して自己修復する。
- retryされた同一 `event_id` は二重commitせず、既存commitを返す。
- partial / malformed tail transaction は last valid committed boundary までで停止し、黙って current state に取り込まない。
- incomplete tailの後ろへ通常eventをappendせず、専用recoveryを要求する。
- state write の通常計算量は state history 全体ではなく、current view size + delta size に比例する。
- current view が current な場合、state read は 448 MB の legacy historyを読み直さない。
- 既存 run の canonical state parser、resume token、run-root binding、nofollow / identity security contract を維持する。
- state migration 中に active create/resume/image process がある場合、in-place migration を開始しない。
- p500 resume plan は parsed state digest / file identity に加え、canonical event head の `seq/hash` に束縛する。
- 新方式の有効化後、state update latency、delta bytes、view rebuild count、replay bytes を観測可能にする。

## State ownership

- Canonical:
  - `state.txt`: append-only transaction log
- Derived and replaceable:
  - `state.current.json`: current materialized state + validated log cursor
  - `run_status.json`: UI / API status projection
  - `p000_index.md`: human-facing navigation projection
- Audit / migration artifacts:
  - `logs/state/migrations/<migration_id>.json`
  - `logs/state/recovery/<timestamp>.json`

Derived artifact は canonical state を変更する入力として使用しない。削除しても canonical log から再生成できることを必須とする。

## Compatibility requirements

- marker のない legacy `state.txt` は full-snapshot history として従来どおり読める。
- legacy reader が delta block を読んでも、key=value の last-write-wins current stateを復元できる。
- legacy state を最初に開くときだけ full replay を許可し、その結果を current view に原子的に保存する。
- current view の cursor / prefix digest が canonical log と一致しない場合は cache hit としない。
- migration marker があるのに current view schema が unsupported / corrupt の場合は fail-openで古い値を使わず、canonical replayまたは明示 failureにする。
- `state.txt` の過去履歴を compaction する処理は本変更の自動 migration に含めない。
- artifact transaction が state event commit 後に失敗しても、committed `state.txt` bytesを過去へrestore / truncateしない。

## Performance requirements

- 1〜10 key の update は、履歴が 500 MB でも full history read / rewrite を行わない。
- delta block は更新 key、timestamp、transaction envelope だけを含む。
- 10,000回の小規模更新後も file growth は delta payload の総量に概ね比例する。
- warm current read と small delta append の regression benchmark を持つ。
- state update の p95 target はローカル filesystem 上で 100 ms 未満を目標とし、CIでは絶対値だけでなく legacy方式との比率を検証する。

## Scope

- canonical state storage contract
- state transaction envelope / parser / current view schema
- run-scoped locking / atomic append / recovery
- legacy state migration
- all Python readers / writers の shared state store への統合
- `run_status.json` / `p000_index.md` projection
- resume / grounding / semantic watchdog / server create integration
- docs / templates / schema / tests / performance regression
- direct `state.txt` mutation を防ぐ repository guard

## Non-goals

- 既存 state key taxonomy の全面改名
- semantic QA や p-slot workflow の意味変更
- 現在稼働中の run へ live code migration を注入すること
- canonical history を自動削除・truncate・compactすること
- `run_status.json` または `state.current.json` を第二の正本にすること
- database / external service を state store の必須依存にすること

## Decision rules

- canonical history と current materialized view の責務を混ぜない。
- process は state delta だけを提出し、merged full state や derived file を直接保存しない。
- 新旧形式の判定は file size や topic ではなく、transaction / view schema marker で行う。
- writer concurrency は retry ではなく、同じ exclusive lock 内の read-current -> merge -> append -> publish で直列化する。
- derived projection の生成失敗は canonical transaction を巻き戻さない。stateへ recovery-needed を記録し、再生成可能にする。
- malformed committed transaction、hash-chain不一致、root identity mismatchは fail closed とする。
- performanceのために symlink / nofollow / run-root identity検証を弱めない。
- hash chainはtrusted local filesystem内のintegrity検出であり、same-user attackerに対するauthenticationとは扱わない。

## Acceptance evidence

- delta update が変更 key だけを追記する unit test
- 同じ key の複数更新が最後の値を返す replay test
- legacy full snapshot + new delta の compatibility test
- two-writer lost-update regression test
- crash between log append and view publish の recovery test
- partial tail / corrupt view / stale cursor test
- 500 MB相当の履歴を再読せず warm updateする instrumentation test
- p500 resume、grounding、semantic watchdog、frontend create の integration test
- direct writer guard と canonical docs validator
