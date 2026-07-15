# Duration-aware story pipeline requirements

## Goal

フロントから指定した 5〜20 分の目標尺を、research から scene / cut / narration / manifest / audio duration gate まで一貫して引き継ぎ、目標尺に必要な物語量を作る。research と story は実際の semantic review に合格するまで cut へ進めない。

## User-approved decisions

- フロントは 5 / 10 / 15 / 20 分プリセットと 300〜1200 秒のカスタム値を受け付ける。
- 既定値は 300 秒とし、既存クライアントとの互換性を保つ。
- 動画尺は `target_duration_seconds * 0.8` 以上で合格する。
- 上限超過は失敗にしない。79.9% は失敗、80% と 150% は合格とする。
- 生成計画は目標尺そのものを狙い、最低設計量は次の式で算出する。
  - scene: `ceil(target_duration_seconds / 40)`
  - cut: `ceil(target_duration_seconds / 12)`
  - narration: `ceil(target_duration_seconds * 0.70)` 秒
- 実音声、意図的無音、render unit、完成動画を、それぞれの段階で実測または明示値から検証する。
- CLI と frontend backend は同じ duration contract を使用する。
- 外部課金を伴う画像・動画・TTS生成は検証で実行しない。
- 現在の未コミット変更は現行ベースとして保持する。

## User journeys

1. ユーザーがフロントで 15 分を選ぶと、API、run state、research、story、script、manifest が同じ 900 秒を保持する。
2. 20 分を選ぶと、8 scene / 45 cut / 固定 300 秒 script のままではなく、最低 30 scene / 100 cut / 840 秒 narration を狙う計画になる。
3. research または story が物語の骨格を満たさない場合、review が合格を偽装せず cut materialization 前に停止する。
4. p740 では一部の音声が存在するだけでは完了せず、全 cut の実効 audio timeline が目標尺の 80% 以上かを判定する。
5. 目標 300 秒に対して 239.7 秒は失敗、240 秒と 450 秒は合格する。

## Semantic review contract

research review は最低限、次を監査可能な criteria として評価する。

- canonical synopsis 相当の story baseline がある。
- ordered beat sheet / chronology がある。
- 主要人物と役割がある。
- central conflict と resolution がある。
- 後続 scene に使う情報が配分されている。

story review は最低限、次を評価する。

- research baseline と主要 beat が scene に割り当てられている。
- scene の時系列、因果、人物、対立、解決が破綻していない。
- duration plan が要求する scene / narration / cut budget を後続で満たせる。
- review artifact に criteria ごとの結果、根拠、status が残る。

review transport failure、review artifact 欠落、明示的 fail は合格扱いにしない。

## Duration contract

| target | minimum scenes | minimum cuts | narration target | minimum effective duration |
| ---: | ---: | ---: | ---: | ---: |
| 300s | 8 | 25 | 210s | 240s |
| 600s | 15 | 50 | 420s | 480s |
| 900s | 23 | 75 | 630s | 720s |
| 1200s | 30 | 100 | 840s | 960s |

- 音声段階では、narration cut は実測 audio 秒、intentional-silence cut は明示 duration を用いて non-overlapping cut timeline を合計する。
- render unit timeline と final video duration は別レイヤーとして測り、audio timeline と足し合わせて二重計上しない。
- その段階で存在する必須レイヤーは、それぞれ `0.8 * target` 以上でなければならない。
- duration の上限は設けない。

## Non-goals

- faithful / inspired-by / user-supplied のモード分離。
- タイトル曖昧性、版、翻訳、対象章の強制解決。
- 一次資料、権利状態、URL、passage / event / story ref の真正性検証。
- 古典としての史実・典拠・版への忠実性保証。
- p680 から p900 へのワンクリック自動継続。
- 画像・動画生成品質そのものの変更。

## Done when

1. Frontend の新規作成 UI と create API が `target_duration_seconds` を 300〜1200 秒で受け付け、未指定時は 300 秒になることを frontend build と backend request tests が証明する。
2. `tests/test_story_duration_contract.py` が上表、境界値 299 / 300 / 1200 / 1201、79.9% / 80% / 150% を検証して合格する。
3. frontend create route で作った新規 run の state / research / story / script / manifest に同一 target が保存され、20 分 fixture が最低 30 scene / 100 cut / 840 narration seconds の budget を持つ。
4. research / story の unconditional auto-pass がなくなり、focused tests で fail または review transport failure 時に cut materialization が開始されない。
5. CLI と frontend が同じ duration audit 実装を呼び、audio timeline に実音声と intentional silence を一度だけ数えることを unit / integration tests が証明する。
6. p740 は全 cut の audio readiness と 80% gate の合格時だけ完了し、video endpoint は未合格 run を拒否する。
7. final video が存在する場合は ffprobe 実尺に同じ 80% / no-upper-bound contract を適用するテストが合格する。
8. `python scripts/toc-create-run-headless.py --title "シンデレラ" --source "シンデレラ" --target-duration-seconds 300 --no-images --assert-profile cut_contract_v2` が frontend と同じ backend create route を通って完了し、生成 artifact と regression report が新 contract を満たす。
9. focused Python tests、関連 regression tests、frontend build、`python scripts/validate-pointer-docs.py` が合格し、既存の未コミット変更を消していない。

