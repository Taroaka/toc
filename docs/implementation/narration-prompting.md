# Narration Prompt Projection

Narration prompt は story/scene/cut design の全文を連結せず、registry で用途を決めて
spoken text へ一方向に投影する。正本は `toc/narration_prompt_projection_registry.py`。

## Projection axes

各 design key は次を持つ。

- `authoring_relevance`: `required | conditional | none`
- `spoken_projection`: `derive | may_surface | must_not_surface`

`time_of_day_visual_basis`、camera metadata、image/video prompt、internal IDs、path、hash、
withheld/reveal IDs は spoken text へ直接出さない。Visible facts は原稿が重複説明にならない
範囲で読み、narration の役割は因果、内面、時間、視点、世界の rule、意味、aftertaste に置く。

registry が空の conditional value を prompt に入れないこと、required/candidate/constraint/
exclude の分類が安定していること、must-not-surface values が本文へ出ないことを ordinary
projection tests で確認する。

## Full-run authoring

cut ごとに独立作文せず、次の順で進める。

1. audience promise、narrator bible、open loop/payoff、scene attention arc、causal handoff、silence budget を決める
2. cut 境界なしの continuous full draft を書く
3. narration spans を canonical cut order へ anchor する
4. `narration`（公開用）と `tts_text`（provider用）を分ける
5. pronunciation、sentence length、pause、audio duration を普通に検証する

画面に明らかな物理行動は映像へ任せる。映像だけで伝わらない因果、内面、時間、視点、
world rule、意味を音声へ足す。非日常空間の導入で直接説明を使う場合も、後段の reveal を先出ししない。

## 音声だけで理解できる説明の具体性

- 初めて聞く人が、前後の音声だけで行為・条件・因果を理解できる具体性を優先する。必要な「誰が、誰に、何を、どこから／どこへ、いつまでに、なぜ」を省略しない。全項目を毎文に詰め込む必要はない。
- 「退出する」「戻る」「約束する」には理解に必要な場所・対象・相手・約束の内容を添える。「その前」「元通り」などは、指す期限や変化前後が音声から一意に分からなければ具体語に置き換える。
- 映像との重複回避を、行為の対象・場所・期限・因果を削る理由にしない。視覚的な細部の実況は避けつつ、物語を知っている視聴者の補完を前提にしない。
- 警告・条件・約束は、何が起きる条件なのか、そのため誰が何をするのかを短い複数の文でつなぐ。細かく書くとは理解に必要な情報を補うことであり、装飾や同じ説明を増やすことではない。
- 補足はsourceで裏付けられ、その時点で開示可能な事実に限る。原作にない動機・帰宅条件・例外を創作せず、意図的な未開示や曖昧さを説明で消さない。
- 尺が足りない場合は意味に必要な語を削らず、文の分割、既存のcutをまたぐspan、音声実測後の尺調整で扱う。reveal境界、silent、human_lockedの契約は維持する。
- TTSへ渡す前に、映像や設計資料を見ず通し原稿を読み、行為の対象・場所・指示語・条件と結果が追えるかを執筆者自身が確認する。不明点は原稿段階で補い、tts_textへの変換でも落とさない。別の必須レビュー工程や品質スコアは追加しない。

## 標準の語り口・音声タグ・単語の修正

ユーザーが別の演出を指定しない限り、日本語の第三者ナレーションは「です・ます調」で統一する。
落ち着いた温かい声と、ゆっくりした自然な間を基本にし、感情を演じすぎない。
事実・人物関係・開示順を変えず、直接の台詞や引用まで機械的に敬体へ変換しない。

- 執筆時に音声ありcutの語り方を決め、`tts_text` に実際に送るボイスタグを入れる。
  基本例は `[Warm, calm narration, slow measured delivery]`。
  意味の区切りには必要な場合だけ `[short pause]` を置く。毎文に付けず、笑い・ため息・息継ぎを人間らしさのためだけに追加しない。
- 表示用の `narration` / `audio.narration.text` にタグや読み仮名を混ぜない。
  `tts_text` はタグ・読み指定込みの最終送信文字列とする。`elevenlabs_prompt.voice_tags` を使う場合も実際のTTS本文と整合させ、音声にしない制作指示を `spoken_context` として読み上げない。
- p400の初期原稿でも敬体・平易な言葉を使い、`audio_intent` に語り方と必要なタグを明示する。
  p700で最終スクリプトを書く際にタグをTTS本文へ反映する。無音cutにはタグも本文も追加しない。
- フロントの「音声用の文面（読み方・タグ）」で全文を確認でき、「語り方・間のタグ」はそのTTS本文から表示する。
  未適用のメタデータから表示しない。タグ編集後は原稿を保存し、新しい改訂から音声生成する。
- 文語・専門語・関係語は、聞いた瞬間に対象と意味が分かる表現へ言い換える。
  親族関係を説明する今回の標準例は `継母 → 新しい母`、`義姉 → 義理の姉`。
  一度採用した言い換えは、その作品のナレーション全箇所に統一する。原資料の引用や人物ID、映像用の設計資料を検索置換しない。
- 言い換えと読み修正は区別する。意味を分かりやすくする修正は表示本文にも反映し、
  `2人の義理の姉 → ふたりの義理のあね` のような発音指定はTTS本文だけに入れる。
  同じ表記で読みが変わる語は文脈ごとに修正し、読み替え辞書で一律置換しない。
- 修正履歴には元の語・採用表現・読み・対象範囲を残す。runの `narration_style.json` があれば執筆前に読む。
  読み替え辞書は繰り返す同じ読みの語に使い、かなで解決しない場合だけv4の発音辞書やIPAを検討する。
- ユーザーが承認した声・語り口を引き継ぐ。文面や読みを変えた音声は再生成前の状態として扱い、
  既存の試聴音声を新稿の完成音声へ自動昇格させない。尺は生成音声で実測する。

## 人物の呼び名と読みの修正

ユーザーが人物を固有名で呼ぶよう指定した場合は、その人物を指す箇所だけを文脈で特定して変更する。
親族自身の子供、一般の女性全体など別の対象を指す語は置き換えない。
正体を知らない人物の発言へ名前を補って知識や開示順を変えない。必要なら「女性」などの自然な語に言い換える。
「真夜中」の表示はそのままに、誤読を修正する音声用表記は「マヨナカ」とする。
修正はrunの `narration_style.json` に記録し、過去に承認した読み指定とボイスタグを保持する。

## Projection example

```yaml
narration_projection:
  registry_version: narration_prompt_projection_registry_v1
  global:
    story_time: {authoring_relevance: conditional, spoken_projection: may_surface}
    theme: {authoring_relevance: required, spoken_projection: derive}
  scene:
    time_of_day: {authoring_relevance: conditional, spoken_projection: may_surface}
    time_of_day_visual_basis: {authoring_relevance: none, spoken_projection: must_not_surface}
  cut:
    visible_facts_in_frame: {authoring_relevance: conditional, spoken_projection: derive}
    must_not_reveal: {authoring_relevance: required, spoken_projection: must_not_surface}
    narration_should_add: {authoring_relevance: required, spoken_projection: may_surface}
    image_prompt: {authoring_relevance: none, spoken_projection: must_not_surface}
```

## References

- `docs/script-creation.md`
- `docs/implementation/video-integration.md`
- `toc/narration_prompt_projection_registry.py`



## API設定と音声加工の再現性

日本語ナレーションの未指定時の既定はJun、`eleven_v4`、`language_code=ja`、`mp3_44100_128`。
v4の未指定voice settingsは `stability=0.5`、`similarity_boost=0.75` とし、
provider境界の `normalize_elevenlabs_voice_settings` が補完する。明示された値と話者は維持する。
script metadataの既定stability profileは `natural`。既存作品の設定を一律に上書きしない。

ですます調、平易な単語、落ち着いた語り、`[Warm, calm narration, slow measured delivery]` と
必要箇所の `[short pause]` はauthoring時に正規の `tts_text` へ保存する。
フロント生成は保存済みの本文・タグとそのrevisionを使う。生成直前にタグや読みを無断追加して
原稿と送信文を違えることはしない。前後文脈も既存のTTS continuity契約で送信する。

音の大きさとcutの0.5秒はproviderの速度/音量パラメータではない。
[ナレーション音量・試聴・合成の共通処理](video-integration.md#ナレーション音量試聴合成の共通処理)に従い、
原音を保存してから派生試聴・合成用trackに適用する。Codexスレッドの確認版も同じ共通処理を使う。
