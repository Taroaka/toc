# ADR-0005: Production を direct authoring pipeline に統一する

- Status: Accepted
- Date: 2026-09-09
- Supersedes: ADR-0003

## Context

旧 pipeline は authoring の後に production reviewer、critic、aggregator、rubric score、pass
certificate、または mandatory human approval を置いていた。standard/preapproved の mode 差で
これらを切り替える設計は、同じ source と request に複数の進行契約を作り、生成処理と入力/出力の
検証を混同していた。

## Decision

- production の canonical flow を `authoring → ordinary structural validation → generation` に統一する。
- stage author と L2 bucket owner が、schema、type、ID、source/reference、selector、request、file、
  decode、duration、stream、provenance を検証する。
- production は reviewer/critic/aggregator agent、quality/rubric score、pass threshold、review/audit
  certificate、review-only slot を作成・読取・要求しない。
- 旧 review/eval state や run artifact は履歴として読み取れるが、新規 progress や resume の条件に
  使わない。
- candidate selection、listening、editing、change request は optional user choice として保存する。
  source variant の hybridization と publication はそれぞれ明示した user action として扱う。
- state は append-only のまま維持し、L2 supervisor が canonical artifact、state、navigation index を
  single writer として更新する。
- ADR-0003 の `eval_report.json`、`run_report.md`、score/pass gate、review loop の判断は廃止する。

## Consequences

- standard/preapproved のどちらの入力でも、同じ authoring、structural validation、generation path を通る。
- 欠落参照、壊れた schema、request/hash drift、file/decode/provenance failure は通常の processing error
  として検出される。
- 品質判断を証明書や自動採点 artifact に依存しない。ユーザーの選択と公開許可は生成処理から分離して
  追跡できる。
- ADR-0003 は歴史的な背景として保持し、新規実装の根拠にはしない。
