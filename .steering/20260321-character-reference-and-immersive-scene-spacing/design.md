# Design: character reference の全身化と immersive scene spacing の互換移行

## 方針

### A) `character_reference` scene の役割を固定する

`character_reference` scene は、以後「人物参照の正本」として扱う。
この種の scene では、顔だけ・バストアップだけ・手元だけの画像を混ぜず、**必ず full-body** で統一する。

狙いは次の2点。

- 服装、シルエット、体格、足元まで含めて参照できること
- 後段の scene 生成で「どこまでを同一キャラとして維持すべきか」がぶれないこと

### B) readable reference identifier を導入する

`character_reference` scene には、数値の `scene_id` とは別に、人間が追跡しやすい識別子を付ける。

推奨イメージ:

- `reference_id`: `momotaro_full_body_front`
- `reference_id`: `oni_leader_full_body_side`

要件は次の通り。

- 参照対象が一目で分かる
- 向きや用途が分かる
- 既存の numeric `scene_id` と併用できる

この識別子は、manifest、asset guide、レビューコメントのどこから見ても同じものを指せることを重視する。

### C) immersive story の scene numbering を 10-step spacing に寄せる

新しい guidance では、immersive story の scene_id は **10刻み** を推奨する。

例:

- `10, 20, 30, 40...`
- 必要なら `0` を reference / prologue 用に別扱いする

この方式の目的は、後から scene を差し込みやすくし、途中の構造変更に耐えやすくすること。

### D) 互換性は維持する

重要なのは、10-step spacing を「新しい推奨」にすることであり、既存の連番や manifest 順を壊すことではない。

設計上の互換条件:

- 旧来の `scene_id: 1,2,3...` を完全禁止にしない
- 後段処理は `scene_id` の連番前提ではなく、必要に応じて manifest 順を正とする
- 既存テンプレやガイドの説明は、推奨を更新しつつ古い運用を許容する書き方にする

### E) 変更対象の中心

この変更は主に docs / workflow / playbook / agent instructions の更新で担保する。
実装ロジックがある場合でも、まずは正本の説明を更新し、そこから参照される形に整える。

## 期待する記述の粒度

- `character_reference` の full-body ルールは、曖昧語を避けて明文化する
- readable reference identifier は、命名例と使い方を併記する
- 10-step spacing は「推奨」と「例外の互換」を同じ場所で説明する
- 既存運用への影響は、禁止ではなく移行方針として書く
