# Cut内ショット設計

`shot_direction_v1` は、既存のmanifest cutの画面設計を、必要な場合だけ複数の個別shotへ分ける契約です。story/script、source event、親cutの意味・尺・音声・cut contractは変えません。sceneや物語cutを追加する機能でもありません。

## 考える順序

まず「このcutで何を届けるか」を決めます。人物の行為が関わるなら、必要に応じて人物の目的や感情を考えます。次に、顔・手・足・背中・道具・環境など何が見えると意図が伝わるか、その見え方、動きと時間、カメラを選び、最後に構造化した `shot_plan` へ記録します。

これは選択肢であり、毎sceneに同じ構成や感情表現を課しません。画面外の顔や身体を見せる必要はなく、顔が映らないshotに表情を要求しません。静止・反復・人物なしの画も意図に合えば使えます。終了画は任意で、動きの説明だけで意図が成立するshotにend frameを追加しません。quality criticや得点による常設gateもありません。

## データと時間

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

開始画、動作、カメラは別に記します。人物の移動は `motion` / `events`、カメラの動きは `camera.movement` が持ちます。原作にない事件・台詞を追加しません。画面外の参加者は世界の状態として保持し、心理や演技の解釈は原作の事実と区別します。後段で参照同一性を安全に解決できない構成はfail closedにします。

## 適用範囲と保持

shot設計を適用するときは、scene/cut一覧で対象の親cutを選び、そのcutのshot列だけを更新します。親cutのaudio、source/cut contract、story、script、`cinematic_direction.json` と他のcutは保持します。既存の画像・動画candidateのbytesは消さず、設計変更で古くなったvisual request bindingを無効化して、選択されたshotのrequestを再materializeします。設計を保存したことだけで画像・動画を生成済みとは扱いません。

関連コードは `server/cut_direction_api.py` と `scripts/edit-cut-direction.py`、scene/cut表示は `server/web/src/CutDirectionPanel.tsx` です。API routeは `server/image_gen_app.py` から登録されます。コード上の入口と生成contractの説明であり、有料providerへのend-to-end実行確認を意味しません。

設計が変わると出力ファイル名にplan hashを付けて分離し、shot selector自体は安定させます。保存のみで以前の採用メディアを上書きしません。

全sceneの動画生成前準備については[動画生成前の全scene準備](video-preparation.md)を参照してください。
