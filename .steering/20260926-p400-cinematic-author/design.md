# 設計

- 新しいp400 author artifact `cinematic_direction.json` に作品全体とscene単位の演出判断・cut列を保存する。
- 共通read-only Codex runtimeを利用。全research/story/visualを省略せず入力し、前sceneの完成した設計と次sceneを見ながらscene単位でauthoringする。構造不備だけを同じauthorへ上限付きで返す。
- metadataにversionと3つのsource hashをruntimeが付ける。全sceneが成功するまで旧artifactを置換しない。
- 前後cutはauthor cut IDと直前の終了状態を明記して接続する。scene境界の演出理由もauthorする。構造検査を意味の正しさの保証とは扱わない。
- 新規frontendはp300後にauthorを起動。既存scene-set preflightを通し、新しい専用projectionでscript/manifestへ変換。旧scaffoldを通してから上書きする方式にはしない。
- p400出力metadataへ設計のhashを保持。固定cut数・固定感情・均等尺・定型ナレーションを新経路で使わない。Bロールも同じauthorのcut列内で判断する。
- 既存runに設計がなければ既存経路を維持。新規author失敗はp410失敗とし、script/manifest作成前で停止する。


## レビューで追加した境界

- sceneのsource start/end状態IDへ束縛し、continuousなcut間は終了ID・構造化状態factsを次の開始へ保持（画面に見せる範囲はvisible_state_keysで別に選ぶ）。省略は明示的ellipsisと接続理由。
- revealは当該/既出beatだけが許可できる。後続beatのsource IDが存在するだけでは前倒し開示を許可しない。
- event_time_position/progression_mode、原作保持条件、読み取れる後続の禁止事実、名前付き衣装bindingを実行用promptまで保持。
- 開始済みの新契約はstate markerでも検知し、artifact消失時の旧経路へのdowngradeを拒否する。
- 既存provider capabilitiesの範囲で尺を検査。旧validatorの固定15秒上限は、新契約では共通capabilitiesに置換。
