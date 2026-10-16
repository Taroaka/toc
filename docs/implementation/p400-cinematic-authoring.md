# p400 Cinematic Authoring

作品共通の撮影方針とcutの光・焦点・身体・演技・同期音は
[Cinematic language](cinematic-language.md) を参照。新規production CLIはp410内で一度だけ
film languageを執筆し、既存のscene authorへ渡す。

2026-09-26。新規frontend/CLI制作は `cinematic_direction_v1` を使う。
p410/p420はLLMが映画として判断する工程であり、上流の機械的な整形だけではない。
原作に忠実であることは、構図・カット割り・尺を定型に固定することを意味しない。

## 執筆

共通read-only author runtimeでscene単位に執筆する。research/story/visual_valueの全文、
使用可能なasset registry、対象scene、直前sceneの完成したcut列を毎回渡す。
次sceneもstory全文に含める。個別cutを孤立して執筆させない。

初回と修復の執筆では、[何を届けたいかからシーンを考える](../story-creation.md#何を届けたいかからシーンを考える)
を文章上の思考の手がかりにする。作者が何をしたいか、観客へ何を届けたいかを先に考え、
それに役立つ場合に導入や起承転結、反応や余韻を選ぶ。全sceneに四機能を求めるものではない。
不足する説明が意図を妨げるなら入口を補い、沈黙・省略・唐突さが意図に合うなら保つ。
既存のdirection/purpose等へ必要な判断を記すだけで、各sceneへの回答票や新しい評価gateは作らない。
authorへ渡す文章は `toc/scene_entry_guidance.py`。構成を満たすかの自動判定ではない。

- p410の判断: scene全体の見せ方、観客の理解、p300の意図をどう具体化するか、前後sceneへの接続。
- p420の判断: cut数、beatの分割/統合、静止画の開始状態、動作と終了状態、構図・撮影距離・焦点・光、音と語り、切る理由、秒数。
- 全sceneが圧力・反転・解放を持つ必要はない。未解決、沈黙、状態維持も選べる。
- 原作の出来事と開示順を守り、演出判断を原作の新事実にしない。
- `story.md` / `script.md` のevent sequenceを読み、登場人物・動物・物・乗り物・衣装の外見、衣装、物のcondition/material/structureがsource上で変わるか毎scene確認する。後続画像で同一性を保つための再利用anchorが必要な可視差分だけを `state_variants[]` として作る。variantごとにparent `asset_id`、stable `variant_id`、source beat ID、変化前後の状態、drawable `generation_prompt` を執筆する。瞬間的なpose/action、時間帯や感情だけの差、再利用anchorが不要な一時的変化はasset variantにしない。
- 変化を見せる動画cutの終端を別画像で固定する必要がある場合は、同じcutの `result_frame` に状態variantと場面specificな終了画briefを結ぶ。この画像requestはp600の追加stillで、story cut、尺、語り、音を増やさない。単体のasset reference sheetを動画のlast frameに使わない。
- 連続した複数beatを一つの長回しで見せても、一beatを複数cutに分けてもよい。根拠のある視覚的役割で決める。
- 尺はsceneの目標秒数内で不均等に配分できる。1cutは現行実行範囲の1〜60秒。
- 人物なしBロールは同じcut列内のsubとして設計する。p300の案を採用/調整した理由を記録し、mainだけで必須beatを成立させる。
- 語りの人称は第三者。カメラ視点とは別に判断する。沈黙には理由を記載する。

`scene_intent` / `scene_event` の原作事実とIDは維持する。演出は別の `cinematic_direction` として
sceneとcut契約へ引き継ぐ。すべてのシーンの再配置や原作の改変はこのauthorの権限ではない。

## 成果物と失敗

`cinematic_direction.json` に全sceneの演出判断とcut列を保存する。
metadataの契約版とresearch/story/visual_valueのraw-byte SHA-256はコードが付ける。
asset registryも保存し、再投影時に現在のregistryと一致することを確認する。
出力形は `toc/p400_authoring.py::SCENE_FORMAT` が正本。

構造エラーは該当sceneの旧出力・エラー箇所とともに同じauthorへ返す。初回に加え最大2回まで修正する。
transport障害やsource変更は構造修正で隠さず失敗させる。全sceneが成功するまで旧成果物を置換しない。
新規author失敗時はp410をfailedにし、旧scaffoldや一beat一cut変換で代替しない。

CLI: `scripts/author-cinematic-direction-with-codex.py --run-dir <run>`。
frontendが実際に使うasset registryを `logs/authoring/p400/resources.json` に渡して起動する。
呼出元がrun lockを所有する。モデルは共通authorの既定値、必要なら `TOC_P400_AUTHOR_MODEL` で指定する。

## 投影と検証

新経路は旧cut builderを通さず `toc/p400_projection.py` でscript/manifestへ投影する。
生成されたカメラ、語り、沈黙、開始/終了状態、尺を固定文や均等配分で上書きしない。
画像prompt compilerと動画prompt compilerは、この具体的な演出と参照情報を実行用に変換する。

コードはscene/beat/asset参照、必須beatのcoverage、順序、cut ID、前cutの終了状態への参照、
開示許可、秒数の型・範囲・合計、source digestを確認する。
`start_state_id/end_state_id` はsceneのsource状態へ結び付ける。途中のcontinuous接続は
前cutの終了ID・`end_state_facts` を次cutの開始ID・`start_state_facts` へ正確に引き継ぐ。
世界の状態と画面に見せる範囲を分け、`visible_state_keys` で開始画に見せる状態を選ぶ。
構図・画角・焦点・first_frame_briefはcutごとに変えられ、画面外の物を毎cutへ描かせない。
省略を行う場合は `continuity.mode: ellipsis` と専用の `ellipsis_reason`、根拠ある接続理由をauthorが記す。
`event_time_position` と `progression_mode` はauthor判断を保持し、余韻を動作途中へ変換しない。
開示許可は当該/既出beatからのみ取得し、後続beatの許可を前借りしない。
後続beatの禁止境界とsourceの保持条件は、内部IDに加えて可読文でも生成側へ渡す。
既存衣装のappearance bindingもasset registryから名前付きで引き継ぐ。

衣装変更後の状態は、その後のcut/sceneでも持続する。全登場人物について人物/memberと
現在の衣装状態の対応を確認し、場所や画面上の左右が変わったことを衣装のリセットや交換の
理由にしない。色・形・袖・靴など識別に必要な特徴と、状態が変わる区間/根拠を既存の
appearance/state bindingへ記録する。主人公の服装だけを確認して脇役を省かない。
採用済み映像と古いasset/scene画像が食い違う場合は、ユーザーの現在の指定と採用状態を
解決してから参照を選ぶ。集合名の一人分の素材を複数人へ同じ衣装として複製しない。
詳細は[衣装の引き継ぎ手順](conversation-media-generation.md#衣装は人物ごとに引き継ぐ状態)を参照する。
これらは文章とIDの整合検査であり、作者の文そのものの意味や実際の映像に矛盾がないことを一般に証明するものではない。

p440/p700での語り修正・実音声の尺は既存同期を使う。authorの計画尺は `target_duration_seconds` に保持する。
画面・カメラ・動作の設計を変更する場合は、設計artifactとscript/manifestを一致させる。

保存済み設計は再開時に再利用する。未知版・stale source・参照不整合・設計欠落は失敗する。
新契約を開始する時点でstateにもmarkerを記録し、設計ファイルが失われても旧経路へ戻さない。
既存runで新契約が宣言されていない場合だけ従来経路を維持し、自動移行しない。
p400 rebuildのcandidateは、新契約なら `cinematic_direction.json` も含めて一緒に適用する。

## 観測範囲

prompt/response/provenanceと構造検証は `logs/authoring/p400/` に記録する。
構造検査を通っても、最高の映画・原作の完全な忠実さを保証したことにはならない。
実モデルの執筆と実際の映像・音声の出来は、制作結果で確認する。criticや点数による常設gateは追加しない。


script/manifestの意味に関わる契約は、保存済み演出とsourceからcanonical projectionを再生成して
照合する。人物・物・場所の参照、開始/終了状態、時間位置、原作保持条件、開示境界が途中で
書き換われば失敗する。p700で更新する語り本文や実測尺は、この固定の演出照合とは分ける。

## p420の未登録素材 — source_asset_requests_v1

既存のscene単位LLM出力に `asset_requests` を追加する。追加が不要なら空配列にする。
対象は、そのcutに必要で原作に明記された人物・物・場所だけ。全登場物の網羅登録や、
比喩・themeからの物体化、新しい物語事実の創作は行わない。LLM呼出しの工程は増やさない。

各項の内容:

- `request_id`、`kind: character|object|location`、原作上の `name`。
- `source_entity: {source: research|story, pointer}`。同じ対象を識別する原文の文字列node。
- `source_evidence: [{source, pointer, quote}]`。現在sceneの出来事/場所、またはそのsceneのbeatが参照するresearchイベント内の実在する引用。対象名を含める。
- `used_in_cuts`。この素材を使うauthor cut ID一覧。
- `existing_asset_id`。登録済み素材を再利用する場合に指定。通常は空文字。
- `distinct_from_asset_ids` / `distinct_identity_reason`。同名の既存素材と原作上で別物の場合だけ指定する。
- `source_role_id`。新しい人物素材が既存beatのparticipant IDに対応する場合だけ指定する。

cutの `character_ids` / `object_ids` / `location_id` では、追加候補を `request:<request_id>` と仮参照できる。
コードがpointer・引用一致・scene/beat範囲・使用cutを検証し、安定したasset IDと相対参照パスへ解決する。
後続beatだけを根拠とする素材を先行cutへ割り当てない。素材登録は先行開示の許可ではない。
同じ種類・canonical source pointer・原作名の組は再利用し、名前だけで別物を自動統合しない。
既存の同名候補があれば、再利用か別物かをauthorに明示させる。

不足素材の登録欄に自由な外観説明は要求しない。登録処理からp500へ渡す参照用の被写体名は
原作に根拠のあるnameに限定し、追加の金色・魔法・装飾などを自由文から流し込まない。
既存素材を再利用するときは、その既存の外観設計を保持する。

`cinematic_direction.json` には `base_resources`、拡張後の `resources`、`asset_resolutions` を保存する。
`metadata.asset_resolution_contract: source_asset_requests_v1` がある場合、読込時にもsourceから
解決を再計算する。自由に書き換えたregistryや参照パスを、そのまま信用しない。
古いdirectionでこの追加契約がないものは従来どおり読める。

解決後のIDはcut依存と画像参照へ入り、manifestのasset bibleへ登録される。
p500は実際の使用cutからinventory/planを作り、source identity・引用と使用selectorを保持して
素材作成リクエストへ渡す。既存素材の再利用にも新しく確認した使用根拠を付ける。

コードが検証するのは引用・参照・使用関係の構造的一致である。原文が物理的な対象を述べているか、
同じ対象かという意味の判断は、この既存のLLM authorが担う。列挙漏れが絶対にないという保証ではない。

## Source-grounded visual state variants

`state_variants[]` はsourceで起きる再利用価値のある視覚状態変化をasset bibleへ渡す。
作者は外見変化の有無を出来事の因果から判断し、キーワード検出へ委ねない。通常の物体の摩耗・破損・材質変化、人物の衣装/外見変化、source上の変身などが対象になり得る。variantは状態の違いだけを持つ再利用anchorで、特定sceneのcamera、背景、blockingを持ち込まない。

各variantの `generation_prompt` は変化後に見える形・素材・状態を具体化し、parent assetの同一性を保つ。`source_event_beat_ids` は現在sceneのsource event IDsでなければならない。変化後状態を通常scene/cut画像に見せるときは、そのcutの `state_variant_refs[]` でparentとvariantを選び、variant状態を使うconsumer beat IDsを同じbindingへ記録する。後続cut/sceneでは、状態作成beatより前の画像からvariantを使わない。p500はvariantをparent asset referenceから派生する通常のasset requestとして生成し、p600は選択されたactual reference pathをimage requestへ束縛する。

同じbeat内でも、sourceが変化後の状態からの開始を明記する場合は、その省略を保持する。
作者は該当する `state_variant_refs[]` に任意の `source_entry` を置き、`beat_id`、
そのbeatの `cut_transitions` にある一意の `transition_id`、その `first_frame_brief` の原文を記録する。
beatは最初のconsumer beatかつvariant作成beatで、sourceの開始画が実際に選択状態を表すことを作者が確認する。
構造検証はID・原文一致と、scene先頭の `scene_entry` または理由付き `ellipsis` を要求する。
未来beatの状態利用、根拠なしの同一beat利用、連続動作の途中での未説明な状態変更は許可しない。
原文の意味を単語検索で推測したり、省略を埋める変化過程を追加したりしない。
開始状態の順序・参照不整合は、そのcutの参照リストだけを既存p420修復へ返して再検証する。

動画の連続動作を結果状態で終える場合、p400の`result_frame.state_variant_refs[]`は必要なcharacter/object/location variantsをまとめて選ぶ。p600は同じcutのprimary scene imageを場所・camera・relative layout anchorにし、after-state variantsと場面specificなend-state briefで別のscene stillを作る。asset sheetをlast frameに流用しない。p800はこのscene stillを `last_frame` へpathとbytes hashで束縛する。結果画は同じcutの画像であり、新しいstory cutではない。構造・描画の妥当性を別の品質採点gateへ委ねない。

既存manifest cutの画面設計を後段で任意に複数shotへ分ける契約は、[Cut内ショット設計](shot-direction.md)を参照する。shot列は親cutの視覚timelineを分割するもので、story/script、source event、親cutの尺・音声・cut contractを書き換えない。人物の目的・感情、見える身体部分、動きの時間、カメラを意図に応じて選び、各shotの画像・動画requestへ投影する。

終幕を執筆するときは `docs/script-creation.md` の「終幕の焦点と観客の余韻」を確認する。最後の主要cutで中心人物・中心関係を見届けられるようにし、脇役の後始末や人物なしBロールを機械的な最終画にしない。

## 行為・反応とフレーム間の整合

全体の人物設計で役割・外見・所作を区別したうえで、各scene/shotでは
[人物と行為の個別対応](shot-direction.md#人物と行為を個別に結び付ける)を具体化する。
誰が誰に働きかけ、誰が道具を保持して使い、周囲がどう見守るかを人物/memberごとに記す。
同じ場面説明を全人物へ複製せず、行為主体を取り違え得るshotでは既存の `performance[]` を使う。
効果の発生だけで原因となる人物の動作を省略しない。性格の基調とその場の行為を区別し、
原作にない行動・感情を事実として追加しない。全員を動かす規則にはしない。

人物間の行為を設計するときは、相手がどう受け止め、どの表情・視線・応答でそれが分かるかを
既存のperformance/end-state欄へ具体化する。反応が目的の場面はその時間を確保し、
物理的な移動完了だけで終わらせない。喜び・謝意等を全場面の定型にせず、sourceの関係と
開示順を守る。開始/終了画像の組にはその意図した差だけを持たせ、衣装の細部や道具の数など
意図しない差を動画の補間へ委ねない。実行時は
[共通確認](conversation-media-generation.md#開始画像と終了画像の差を実画像で照合する)を使う。

## 音の役割をp860へ渡す

[BGM・SEの研究資料](../research/film-sound-emotion.md)と[spotting手引き](../../workflow/playbooks/sound-design/affect-and-spotting.md)を参照する。既存の`audio_intent`に、音が支える人物/出来事、何を優先して聞かせるか、必要な静けさ、語りとの分担を具体化する。音の意図はここで考え、実音源の生成と最終秒数への配置は動画確定後のp860で行う。先に作った音源へ無理に脚本を合わせる規則にはしない。sourceにない台詞/出来事や、未登録の構造fieldを追加しない。
