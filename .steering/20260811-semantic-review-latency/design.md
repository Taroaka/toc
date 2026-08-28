# Semantic Review Latency Design

## Observed Bottleneck

代表 run の最初の `scene_set` review は約 15 分 24 秒を要した。15 scene、約 2.7 MB の collection を単一 reviewer turn に渡し、同じ event 情報を `semantic_contract`、`normalized_semantic_contract`、`scene_event` に重複格納していた。reviewer が正しい digest を引用符付きで返した際、canonical parser が引用符を除去しないため currentness mismatch と誤判定し、全量 retry も発生した。

同じ run artifact を一時コピーして compact projection を再構築した計測では、collection は 2,722,531 bytes から 1,079,731 bytes へ縮小した（60.3% reduction、旧サイズの 39.7%）。15 scene は既定 concurrency 6 なら最大 3 wave で審査する。実 provider の wall time は次回 run で別途計測する。

## Design

### 1. Scalar normalization

report の単一 scalar は、field occurrence 数を先に厳密検証した上で、外側の backtick / single quote / double quote を正規化する。正規化後も digest regex と scope の完全一致を要求する。

### 2. Stage-specific scene projection

`scene_set` は scene-level の設計審査に必要な情報だけを投影する。

- retain: identity/selectors、summary、phase/importance、time and location review fields、dramatic question、value shift、causal turn、done-when、participants/roles、ordered event evidence、reveal/withhold、coverage、handoff、terminal resolution
- omit: downstream `scene_generation` prompt payload、cut summaries、film coverage detail、large character-state timeline
- deduplicate: event sequence は一つの canonical compact fieldだけに置き、semantic contract と normalized contract の双方へ複製しない

`scene_detail` / `cut_blueprint` の既存 projection は downstream-specific 判定のため維持する。

### 3. Compact sequence context

collection から全 scene の ordered compact index を作る。各 row は scene id、previous/next、location route、participants/role coverage、time of day、dramatic question、value shift、causal turn、event/reveal ids、handoff、terminal resolution に限定する。

各 shard の collection は対象 scene entry と compact sequence context のみを持つ。reviewer は対象 scene 自体に加え、全体順序に対する因果、reveal、location/daypart、handoff の整合性を判定する。

### 4. Bounded per-scene review

既存 `scene_detail` shard runner を stage-aware に一般化し、`scene_set` からも利用する。

- default concurrency: 6
- `TOC_SCENE_SET_REVIEW_CONCURRENCY` で override
- transport retry: failed shard only
- aggregate: deterministic exact coverage and combined verdict
- semantic failure は repair loop へ渡し、transport failure と混同しない

追加の model aggregate turn は設けない。全 shard が同じ compact sequence context を読むことで全体契約を確認し、aggregate 自体は coverage と shard verdict の機械的結合に限定する。これは単一巨大 turn を再導入せず、待ち時間を bounded shard の最長 wave に近づけるためである。

### 5. Earlier-stage behavior

research / story を含む既存の canonical passed-report reuse を維持する。全 stage 共通の digest 正規化により、引用表現の差だけで起きる output-contract retry を除去する。品質判定を弱める stage skip や timeout 短縮は行わない。

## Safety Invariants

- source artifact digests と canonical input digest は変更前と同じ fail-closed currentness contract で検証する。
- canonical collection の heading は scope entry と exactly once で一致し、各 section は非空の JSON object かつ `payload.id == heading` を満たす。missing / duplicate / unexpected / malformed / id mismatch は provider を呼ぶ前に fail-close する。
- collection section は scope と同順で、JSON fence は1個だけ、fence 外は空白だけ、JSON object 内の duplicate key は禁止する。collection 自体を読めない場合も failed aggregate と coverage-invalid state を残し、provider は起動しない。
- duplicate report fields、invalid digest、missing entry、unexpected entry、duplicate shard assignment は pass にしない。
- shard turn は invocation 固有の bound report または final transcript だけを取り込み、古い canonical report の digest を書き換えて再利用しない。
- canonical collection SHA-256、generation id、canonical input digest、scope binding、entry projection SHA-256 を各 shard scope に束縛し、provider 前後と aggregate 公開前後で世代一致を再確認する。同一 stage の pack / shard / aggregate publication は run 内の cross-process lock で直列化する。
- active run artifact は編集しない。
- state.txt は append-only helper 経由で更新する。
