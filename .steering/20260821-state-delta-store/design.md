# Design: Delta-based run state store

## Decision

`state.txt` を append-only canonical transaction log として維持し、完全 snapshot block の反復追記を廃止する。
current state は `state.current.json` に materialize するが、この file は cache / view であり正本ではない。

```text
process update dict
       |
       v
StateStore.update(updates)
       |
       | exclusive .state.txt.append.lock
       v
load validated state.current.json
  or replay canonical state.txt once
       |
       v
append changed keys as one delta transaction
       |
       v
fsync canonical log
       |
       v
atomic publish state.current.json
       |
       +------> run_status.json
       +------> p000_index.md
```

## Canonical API

新規 `toc/state_store.py` を state I/O の唯一の高水準入口にする。

```python
class RunStateStore:
    def read_current(self) -> dict[str, str]: ...
    def update(self, updates: Mapping[str, str]) -> StateCommit: ...
    def rebuild_current_view(self) -> StateView: ...
    def inspect_integrity(self) -> StateIntegrityReport: ...
```

既存の次の関数は shared store への薄い compatibility wrapper にする。

- `toc.harness.parse_state_file`
- `toc.harness.append_state_snapshot`
- `scripts/toc-immersive-frontend-run.py::append_state_snapshot`

frontend runner は独自の read / merge / block construction を持たない。

## Delta transaction format

既存 parser と互換な `key=value` block を維持する。envelope は comment metadata と delimiter を使い、state key namespaceを汚染しない。

```text
# toc.state.delta.v1 {"committed_at":"<iso8601>","event_hash":"sha256:<hex>","event_id":"<uuid>","event_type":"state.updated","occurred_at":"<iso8601>","prev_hash":"sha256:<hex>","request_hash":"sha256:<hex>","seq":6915,"state_hash":"sha256:<hex>"}
timestamp=2026-08-21T00:00:00+09:00
review.semantic.scene_set.status=reviewing
slot.p410.status=in_progress
---
```

規則:

- payload は caller が変更した key と自動 `timestamp` だけを含む。
- 空 update は timestamp-only eventを暗黙作成せず、必要な heartbeat API だけが明示 eventを作る。
- key ordering は deterministic とする。
- newline は既存契約どおり1行へcleanする。
- event ID、sequence、previous commit、payload digest、適用後current state digestをdomain-separated canonical bytesへ束縛する。
- caller retryは同じevent IDを再利用し、既存commit済みeventならidempotent successとして扱う。
- `request_hash` はevent typeとcallerのcleaned update mapへ束縛し、同じevent IDで異なるrequestが来た場合はconflicting retryとして拒否する。
- metadata JSONはsorted compact canonical encoding、line endingはLF、delimiterはexact `---\n` とし、非canonical framingは拒否する。
- 普通のappend前にincomplete tailがあれば停止し、専用recovery以外は後ろへeventを連結しない。
- delimiterまで揃いcommit digestが一致するblockだけを committed とする。
- legacy blockはenvelopeなしでも有効なsnapshot/deltaとしてlast-write-wins replayする。

## Materialized current view

`state.current.json` schema:

```json
{
  "schema_version": "toc.state.current.v1",
  "generated_at": "...",
  "run_root_identity": [16777231, 103036579],
  "log_identity": [16777231, 103036580, 448128458, 1787270400000000000, 1787270400000000000],
  "log_cursor": {
    "committed_bytes": 448128458,
    "sequence": 6915,
    "event_hash": "sha256:..."
  },
  "events": [
    {
      "event_id": "...",
      "sequence": 6915,
      "event_hash": "sha256:...",
      "event_type": "state.updated",
      "request_hash": "sha256:...",
      "changed_keys": ["slot.p410.status"],
      "encoded_bytes": 512
    }
  ],
  "state": {
    "status": "P410",
    "slot.p410.status": "in_progress"
  },
  "state_sha256": "sha256:..."
}
```

`events` は末尾frameのbounded検証と表示に使うderived indexであり、canonical historyではない。明示event IDのidempotent/conflicting retry判定はindexを信頼せず、常にcanonical logをstream scanしてexact判定する。通常の自動採番updateはscanしない。current view は canonical log append成功後、同じ lock の中で temporary regular fileへ書き、fsync後にatomic publishする。
reader はschema、root identity、log inode/size/mtime/ctime、cursor、末尾commitと直前commitのhash chain、末尾metadataに記録された適用後state digestを検証する。current viewがlog末尾より後ろ、未知schema、symlink、digest不一致の場合は使用しない。

## Read algorithm

1. run rootをdescriptor-relative / nofollowでbindする。
2. shared append lockを取得する。
3. `state.current.json` を検証する。
4. view cursorとcanonical log committed boundaryを照合し、末尾eventの`state_hash`とview本文digestが一致すればstateを返す。
5. viewが後れていればvalid tail transactionだけreplayする。
6. viewがないlegacy runはcanonical logを一度full replayする。
7. repaired current viewをatomic publishする。

通常readでcanonical 448 MBをhashし直さない。cursor validationはlog identity、size、last committed frame metadataなど固定量の検査を使う。full prefix digest再計算はintegrity audit / migration時だけ行う。

## Update algorithm and locking

1. `.state.txt.append.lock` のexclusive lockを取得する。
2. lock内でvalidated current stateを取得する。
3. caller updatesをclean / validateする。
4. current valueと同じupdateは原則deltaから除外する。
5. sequence / previous commitへ束縛したdeltaを構築する。
6. descriptor-relative `O_APPEND|O_NOFOLLOW` で全bytesを書き、`fsync`する。
7. merged current viewをatomic publishし、directoryをfsyncする。
8. lockを解放する。
9. `run_status.json` / `p000_index.md` をcurrent stateから再生成し、`source_seq/source_hash/projection_schema`へ束縛する。

step 9の失敗はcanonical commitを無効化しない。次のsyncまたは明示repairで派生物を再生成する。
古いprojection writerが新しいprojectionを上書きしないよう、publish前にsource headを再検証する。

read-currentとmergeをlock外へ分離しない。これにより二つのwriterが同じold stateを読み、片方のkeyを失うlost-updateを防ぐ。

## Crash recovery

| Crash point | Canonical result | Recovery |
|---|---|---|
| delta append前 | unchanged | retry可能 |
| delta途中 | incomplete tail | last valid delimiter/commitまで採用し、recovery artifactを残す |
| delta fsync後 / view前 | committed log ahead | next readがtail replayしてview修復 |
| view temp write中 | committed log + old view | tempを無視してtail replay |
| view publish後 / projection前 | canonical + current valid | run_status/indexを再生成 |

partial tailを自動truncateしない。canonical append-onlyを維持し、次のvalid recovery transactionで状況を記録する。物理修復が必要な場合はcheckpoint付き専用commandとする。

artifactとstateをまたぐtransactionでは、artifact publish前の失敗だけartifact bytesをrestoreできる。state event commit後はcanonical logをrestore / truncateせず、compensating state eventとrecovery journalで収束させる。

## Legacy migration

active run leaseがないことを確認して次を行う。

1. legacy `state.txt` をdescriptor-relativeにfull replayする。
2. last-write-wins current stateとlegacy log fingerprintを計算する。
3. `state.current.json` candidateをstagingへ作る。
4. migration plan artifactへrun identity、state digest、view bytes、plan tokenを保存する。
5. apply時に同じlockとtokenでcurrent viewをpublishする。
6. 最初のdelta eventへstorage markerを追加する。

過去のfull snapshot blocksは書換えない。したがってrollbackはcurrent viewを削除してlegacy replayへ戻せる。

new runは最初からdelta v1で開始する。legacy runはcurrent viewが作られた後だけwarm pathへ入る。

p500 resumeのprepare/apply tokenは、legacy file fingerprintとparsed map digestだけでなく、current event head `seq/hash` を含む。apply時にheadが変わっていればfail closedとし、pseudo rollbackはdownstream keyをneutralizeする一つのnamed eventとしてcommitする。

## Derived projections

- `state.current.json`: minimal state materialized view
- `run_status.json`: current state、nested projection、artifact inventory、pending gates
- `p000_index.md`: human navigation

`run_status.json` と index は state transaction lock の正本commit範囲から外し、再生成可能にする。
process / server routeがこれらのderived artifactへstate mutationを書き戻すことを禁止する。

## State key policy

- 同じ概念は同じ既存keyを更新する。
- storage migrationのために `*.current` / `*.latest` のduplicate business keyを追加しない。
- 新規keyはstorage metadataまたは本当に新しいdomain conceptに限定する。
- deprecated keyはreader aliasで受け、writerはcanonical keyだけを書く。
- key registry / state schema validatorでunknown typo keyを検出する。

## Direct-write guard

repository testで、許可されたlow-level module以外の次を禁止する。

- `state.txt` への `write_text`, `open(..., "a")`, `append_run_file_text`
- full merged mappingからblockを組み立てる独自実装
- `run_status.json` / `state.current.json` を入力正本としてmutationする処理

移行対象には少なくともcentral harness、frontend runner、p500 resume、immersive ride、legacy AI merge/multiagent scripts、run index、server image progress readerを含める。全writer統合前にdelta defaultを有効化しない。

## Lock hierarchy

lock orderを一つに固定する。

```text
create_resume / run_artifacts lease（必要なworkflowだけ）
  -> state transaction lock
     -> state log descriptor
     -> current-view publication
  -> derived projection publication
```

state storeから外側のworkflow lockを取得しない。外側lockを必要とするcallerが先に取得する。shared readはstate transaction lockと競合するが、canonical authored artifactのidentity検証lockへ逆順で入らない。

## Rollout

1. parser / current-view / recovery testsを追加する。
2. shared storeをlegacy read + snapshot writer互換modeで導入する。
3. readersを`read_current()`へ統合する。
4. writerをdelta transactionへ切り替える。
5. new runをdelta defaultにする。
6. inactive legacy fixtureでmigrationを検証する。
7. frontend create / p500 resume / semantic watchdogのgolden runを通す。
8. current Cinderellaは現在のprocess終了後にだけmigration対象として判定する。

## Performance instrumentation

state commitごとにcanonical state keyではなくstructured app logへ次を記録する。

- `state_store.read_source=view|tail_replay|full_replay`
- `state_store.log_bytes_read`
- `state_store.delta_bytes_written`
- `state_store.view_bytes_written`
- `state_store.duration_ms`
- `state_store.recovery_count`

instrumentation自体でstate eventを追加し、再帰的にstateを肥大化させない。

## Trust model

event hash chainとcurrent-view digestは、accidental corruption、partial write、stale projection、実装driftを検出するintegrity機構であり、same-user attackerに対する署名ではない。run directoryと実行userのfilesystem権限をtrust boundaryとする。承認や外部security boundaryへstateを使う場合は、repo外のHMAC/signature keyまたは外部authorityを別途導入する。unkeyed SHA-256をauthenticationと説明しない。

delta defaultを有効にする前に、全production readerをverified parser/shared storeへ切り替える。legacy parserがmarker commentを無視してpayloadだけ適用する期間は、delta writerをproductionで起動しない。
