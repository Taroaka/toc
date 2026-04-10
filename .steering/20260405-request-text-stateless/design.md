# Design

## Scope

- `scripts/generate-assets-from-manifest.py` の request preview materialization のみを対象にする。
- provider に実送信する prompt source はこの変更では直接書き換えない。

## Approach

- request preview 用に prompt text を整形する helper を追加する。
- helper は以下を行う。
  - `以後のscene`, `後続scene` を含む continuity 文を stateless な文に言い換える
  - `この cut` のような運用メタ語を `この画像` / `この場面` に置き換える
  - `参照画像と完全一致` を、参照画像がある場合は「参照画像に写っている要素をこの cut で維持する」に変える
  - 参照画像がない場合は、参照画像を前提にした wording を外し、要素そのものを維持する表現にする
  - character reference asset では `参照画像` を `基準画像` に寄せる
  - story topic がある場合、人物基準画像と story scene request には `物語「<topic>」` の文脈を加える

## Verification

- request preview 用 helper の unit test を追加する
- current run の request files を再 materialize して弱い phrasing が消えることを確認する
