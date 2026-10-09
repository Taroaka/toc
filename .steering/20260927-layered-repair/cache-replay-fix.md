# 再開時の補正キャッシュと予算

## 実際の原因

12:11の再開では保存済みSC02 field patchの再利用に対してfeedback予約が先に実行され、
LLMを呼ばないまま11→12回へ達した。SC05へ進む前の予約で停止した。

## 修正

- runnerがcache-only lookupを公開する。missでは外部APIも論理call ordinalの更新も行わない。
- pipelineは一致するcached patchを再検証し、適用可能なら予算予約なしで再利用。
- miss/不正cacheだけ通常の予算予約→provider呼び出しへ進む。全体validatorは引き続き実行。
- cache identityはprompt/schema/model/payload hashを維持。base digest/path/value制限も再確認。
- ユーザーが許可した追加1回分を、今回の誤課金分だけ退避して復元する。実際のprovider試行履歴は削除しない。

## 確認

実runは読取りのみでSC02/SC05/SC06のcached patchを再検証・メモリ上に適用できた。
その後に残る検証エラーはSC08の /event_sequence/4/participants/2 のunknown IDだけ。

## 検証結果

- キャッシュ上限到達済みでの再利用、miss時の1回予約、stale-base拒否の回帰テスト成功。
- CLI cache-only missではprovider/ordinalとも変更なし。semantic-invalid hitもcommitせず、同じordinalで通常生成する。
- CLI/repair/pipeline共有予算群32 tests passed、追加のinvalid-hit ordinalを含むfocused10 tests passed。
- 実runのコピーで、SC02/05/06をキャッシュ再利用し、fake providerをSC08だけ1回呼んでstory.md作成・通常story検証合格を確認（実run変更なし）。
- 今回の誤消費を履歴退避して11/12に復元。ユーザーの追加1回分を返却し、run再開は行っていない。
