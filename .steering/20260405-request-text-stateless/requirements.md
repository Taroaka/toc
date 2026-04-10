# Request Text Stateless

## Goal

generation request の本文は、stateful な継続前提ではなく、参照画像とこの cut の関係をその場で読める文面にする。

## Requirements

- request 本文で `後続scene` や `以後のscene` のような stateful continuity phrasing を使わない。
- request 本文で continuity を書く場合は、参照画像があるときだけ「参照画像の人物 / 場所 / 小道具がこの cut でどう使われるか」を書く。
- request 本文で `cut` のような運用メタ語を使わない。
- 参照画像がない request 本文では、「参照画像と完全一致」のような表現を避ける。
- 物語に実在する人物 / 場所 / 場面を扱う request では、必要に応じて `物語「<topic>」` の文脈を明示する。
- 既存の manifest prompt source は保ち、request preview 側で人レビュー向けの phrasing に整形できる。
