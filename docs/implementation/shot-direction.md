# Cut内ショット設計

`shot_direction_v1` は、既存のmanifest cutの画面設計を、必要な場合だけ複数の個別shotへ分ける契約です。story/script、source event、親cutの意味・尺・音声・cut contractは変えません。sceneや物語cutを追加する機能でもありません。

静止画への投影では、人物の姿勢は人物subjectの `view` だけから、小道具の状態はobject subjectの
`view` から作り、両者を一つの人物状態へ混ぜません。子shotの画像compilerが失敗した場合も
cut番号・shot番号・開始画/終了画の位置を保持して診断します。内部の前cut参照などで描画不能な
説明は、そのsubjectの `view` または画面の `description` だけを限定修復し、正常な人物や別shotを
書き換えません。修復後も同じcompilerと通常の参照・構造検証を通します。
`shot_plan` がある親cutの説明は連続性を持つ要約であり、独立した静止画として余分にcompileしません。
実行対象の各shotの開始画・終了画をそれぞれcompileして検証します。subjectの `view` が前cut参照などの
描画不能な継続情報だけの場合は、同じ画面にauthor済みの具体的な `description` を現在状態として投影でき、
汎用proseの補完や新しい人物・物・出来事の推測はしません。
`state_source: previous_end` は直前shotのauthor済み `end_state` を継承します。`end_view` は任意のままとし、
終了画像が存在するときだけ空間参照も引き継ぎます。終了画像を省略したことだけで新たな画像生成を
強制せず、継承した終了状態は画像planの `source_grounding.previous_shot_end_state` に保存します。
先頭shotは同じcut内の前shotを持たないため `previous_end` を指定できません。変身等の結果参照の
必須条件や、画像として生成する実際の開始画・終了画の検証は省略しません。

## 考える順序

まず「このcutで何を届けるか」を決めます。人物の行為が関わるなら、必要に応じて人物の目的や感情を考えます。次に、顔・手・足・背中・道具・環境など何が見えると意図が伝わるか、その見え方、動きと時間、カメラを選び、最後に構造化した `shot_plan` へ記録します。

これは選択肢であり、毎sceneに同じ構成や感情表現を課しません。画面外の顔や身体を見せる必要はなく、顔が映らないshotに表情を要求しません。静止・反復・人物なしの画も意図に合えば使えます。終了画は任意で、動きの説明だけで意図が成立するshotにend frameを追加しません。quality criticや得点による常設gateもありません。

## データと時間

### 人物と行為を個別に結び付ける

複数人物のやり取りでは、行為主体、対象、道具の保持者、周囲の反応を分けて設計します。
`initial_view.subjects[].view` は各人物の外見・位置・姿勢・手元の説明です。同じ全景説明を
全員へ複製して人物別設計の代わりにしません。人物/memberのIDをそのshotの実画像の外見と対応させます。

主体を取り違え得るshotでは、既存の `performance[]` に `actor_id`、必要な `target_id`、
観察できる `behavior` を個別に書きます。「人物Aが行う」と主動作だけに書いて終わらず、
周囲の人物が何を見て、手や身体をどこに保つかも演出上必要な範囲で決めます。
待機や視線だけの反応も演技であり、全員を動かす、一律に手を組ませる等の定型にはしません。
画角外の人物に見える演技を要求したり、その演技のために全景へ戻したりもしません。

現行schemaの `member_id` は行為者側の指定です。`target_id` が集合人物を指す場合は、
対象メンバーの識別名と外見を `behavior` に明記し、その対応が実送信文にも残ることを確認します。
存在しない対象メンバー用fieldや未登録の人物IDを補いません。

道具の保持者と使用者を一致させ、受け渡しがある場合だけ移動の順序を記述します。
同種の物が複数ある場合は個体と保持場所・身体との対応を分け、既に着用/保持している物は
次の動作でも残る状態を `motion` / `end_state` に記録します。位置はshot内の識別補助であり、
画角が変わっても人物や物のIDを入れ替えません。効果や状態変化は原因となる人物の動作の後に配置します。

これらは作者の設計指針です。全shotへのperformance、顔、全身、終了画像の必須化や、
語句だけで内容を合否判定するgateは追加しません。モデル出力の主体・保持物は生成後にも確認します。

静かな会話や余韻を保つために、全員へ一律に「自然な呼吸」を追加しません。必要な瞬き・視線・
口元の変化と、維持する体形・胴衣・襟元の輪郭を分けます。息切れ等の呼吸自体が物語上必要な
場合は、対象人物・強さ・見える部位を限定して指定します。人物を完全に静止させる規則ではなく、
身体や衣服の周期的な膨張収縮を自然な演技として容認しない指針です。生成後は途中の形状も確認します。

正本は親cutの `shot_plan` です。`intent` はcut全体の狙い、`shots[]` は順に実行するshotです。各shotは `shot_id`、cut内の `start_seconds` / `duration_seconds`、狙い、`initial_view`、`motion`、`camera`、任意の `performance` / `events` / `end_view`、`end_state` を持ちます。細部は `toc/shot_direction.py::SHOT_PLAN_FORMAT` と `normalize_shot_plan()` が正本です。

- 最初のshotは0秒から始まり、隙間・重なりなく連続し、尺の合計は親cutの尺と一致します。現在のcontractでは最大60 shot、各shotは15秒以下です。
- `initial_view.subjects` はそのshotの開始画面に見せる人物・物だけを列挙します。asset IDは登録済みIDを使います。`visible_parts` は自由記述で、全身や全員の表示を前提にしません。場所は親cutから引き継ぎます。
- `performance[]` は人物の目的・感情・相手・契機と、作者が選ぶ観察可能な行為を必要なときだけ記録します。`basis` は `source_action`、`user_direction`、`directorial_interpretation` を区別します。解釈を原作の心理事実へ昇格させません。
- `events[]` は入退場、カメラによる発見、焦点移動、変身など画面上の契機を記します。後から現れる人物の同一性を開始/終了参照で表せない場合は、そのshotを採用せず、同一性を参照できる開始画を持つshotへ分けます。
- 感情、相手、焦点移動、終了構図など、不要な任意値は `null` または空配列にできます。`null` は未解決のIDや時刻を表しません。

shotのtimeline尺とproviderへ送る整数の生成尺は別です。親区間は `parent_duration_seconds()` で合成用render尺→採用後のvideo尺→元のcut予定尺の順に解決し、採用音声に合わせた更新を優先します。現在のKling経路では各shotのtimelineを最大15秒にし、providerには `max(3, ceil(timeline duration))` の整数秒を要求します（3〜15秒）。fractional timelineも扱えます。provider出力がtimelineより長い場合、親cutへ配置するときはshotのtimeline尺だけを使い、余分な部分をtrimします。provider出力の尺へ親cutやナレーションを延長しません。別provider/modeを選ぶ場合は現行adapter設定の尺上限を確認します。

## 画像・動画への投影

`toc/shot_projection.py::project_cut_shots()` は各shotを通常のscene stillとvideo requestへ投影します。画像promptは既存のimage compiler、動画promptは既存のvideo compiler/runtimeを通します。ネイティブproviderのmultishot機能は使わず、shotごとに別々の生成requestを作ります。shot-level動画のnative audioはoffで、音声は親cutに残します。

開始画像には各shotの `initial_view` だけを描きます。後続の結果状態を開始画へ混ぜません。`state_source: result` は、その人物・物について原作に結び付いた変化が既に起きた時点に限り、実際に渡す状態variantと照合します。`state_source: previous_end` は直前shotの終了画を参照し、nullではその時点までの状態を継承します。直前の終了画があれば次の開始画の空間参照にも使い、必要な画角変更は別に指定できます。`end_view` を選んだ場合は開始画を空間anchorにした補助stillを作ります。これは同じ親cut内の画像で、追加の物語cut・語り・音声尺ではありません。

`end_view.state_source: result` は、親cutに変化後画像も状態variant参照もない通常動作の結果画にも使えます。
この場合は元の同一性参照を保持し、作者が記述した終了時の位置・姿勢・構図を描きます。
移動・受け渡し・保持などの結果画を作るためだけに `transform` や新しいvariantを追加しません。
親cutに変化後画像または状態参照がある場合は、対応する変化が成立するまで結果参照を使えません。
`initial_view` に未来の結果を使うことや、実際の `transform` に必要な出典・終了画・variant束縛を省くことは引き続き拒否します。

viewの全体説明が前cutへの相対参照を含みprovider用の描画文として使えない場合も、
同じviewの全被写体に具体的な `subjects[].view` があれば、その状態・見える部位・framing・compositionを
現在画として投影します。正本のshot記述は変更しません。別shotや終了状態から開始画を補完せず、
一人・一物でも具体状態が欠ける場合は通常の描画検証で停止します。
同じviewの文が具体描写と制作上の参照に分かれている場合は、具体描写の完全な文だけを保持できます。
内部scene/cut IDは数字直結・underscore・hyphenを含めproviderへ渡しません。
次cut/sceneの説明を現在画として取り出すことや、一文の途中だけを意味を推測して書き換えることはしません。

開始画、動作、カメラは別に記します。人物の移動は `motion` / `events`、カメラの動きは `camera.movement` が持ちます。原作にない事件・台詞を追加しません。画面外の参加者は世界の状態として保持し、心理や演技の解釈は原作の事実と区別します。後段で参照同一性を安全に解決できない構成はfail closedにします。

## 適用範囲と保持

shot設計を適用するときは、scene/cut一覧で対象の親cutを選び、そのcutのshot列だけを更新します。親cutのaudio、source/cut contract、story、script、`cinematic_direction.json` と他のcutは保持します。既存の画像・動画candidateのbytesは消さず、設計変更で古くなったvisual request bindingを無効化して、選択されたshotのrequestを再materializeします。設計を保存したことだけで画像・動画を生成済みとは扱いません。

関連コードは `server/cut_direction_api.py` と `scripts/edit-cut-direction.py`、scene/cut表示は `server/web/src/CutDirectionPanel.tsx` です。API routeは `server/image_gen_app.py` から登録されます。コード上の入口と生成contractの説明であり、有料providerへのend-to-end実行確認を意味しません。

設計が変わると出力ファイル名にplan hashを付けて分離し、shot selector自体は安定させます。保存のみで以前の採用メディアを上書きしません。

全sceneの動画生成前準備については[動画生成前の全scene準備](video-preparation.md)を参照してください。

複数shotの動画request payloadをmanifestへ保存するときは、source cutだけでなく
`shot_id`と完全一致するshot selectorで保存先を解決する。親cutのvideo_generationや
他shotを上書きせず、不明・重複shotやrender unitとの混同は保存前に拒否する。

shot_planを持つ親cutのresult_frameは、子shotへ状態差分を渡す設計情報として保持する。
実行画像の集合は子shotの開始画像と、その子shotが明示した終了画像だけで構成し、
親の非実行result_frameをp650のsnapshotやp680の生成対象へ追加しない。
