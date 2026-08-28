# Semantic Review Latency Requirements

## Goal

生成品質と semantic QA の fail-closed 契約を維持したまま、frontend create の審査待ち時間、特に複数 scene をまとめて読む `scene_set` 審査時間を短縮する。

現在進行中の run は変更・停止・再開せず、この変更は次回以降に生成する run へ適用する。

## Success Criteria

1. 正しい `semantic_review_input_digest` が引用符付きで返っても currentness 判定に通り、同一内容の無駄な再審査を起こさない。
2. digest の欠落、重複、不正形式、不一致は従来どおり拒否する。
3. `scene_set` を scene 単位の bounded concurrency review とし、既定で最大 6 scene を並列審査する。
4. 各 scene shard は対象 scene の意味契約と、順序・因果・reveal・location・daypart・handoff を判定できる compact な全体文脈を持つ。
5. shard aggregate は expected entry を過不足・重複なく照合し、1件でも semantic failure または transport failure があれば canonical report を pass にしない。
6. transport retry は失敗 shard だけを対象にし、完了済み shard を同一 attempt 内で再実行しない。
7. `scene_set` collection は同じ `scene_event` を複数キーへ重複格納せず、scene-detail / image-generation 専用情報を含めない。
8. scene necessity、value shift、causal turn、event order、character/location/time continuity、reveal order、handoff など既存の semantic 判定項目を削除しない。
9. research / story を含む全 stage で current passed report の再利用と正規化済み digest 判定を維持し、format 差だけを理由に再実行しない。
10. representative fixture で compact `scene_set` collection が旧 projection より明確に小さいことを deterministic test で保証する。

## Scope

- semantic report scalar normalization
- scene semantic pack projection
- `scene_set` per-scene sharding / concurrency / transport retry / aggregate
- related configuration, state diagnostics, tests, and canonical documentation

## Out of Scope

- 現在進行中のシンデレラ run の操作
- semantic 判定基準の緩和または gate の省略
- reviewer model や provider の変更
- image / video provider generation の並列数変更
- story 本文や既存 run artifact の書き換え

