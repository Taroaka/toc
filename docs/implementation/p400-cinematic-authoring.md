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

- p410の判断: scene全体の見せ方、観客の理解、p300の意図をどう具体化するか、前後sceneへの接続。
- p420の判断: cut数、beatの分割/統合、静止画の開始状態、動作と終了状態、構図・撮影距離・焦点・光、音と語り、切る理由、秒数。
- 全sceneが圧力・反転・解放を持つ必要はない。未解決、沈黙、状態維持も選べる。
- 原作の出来事と開示順を守り、演出判断を原作の新事実にしない。
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

終幕を執筆するときは `docs/script-creation.md` の「終幕の焦点と観客の余韻」を確認する。最後の主要cutで中心人物・中心関係を見届けられるようにし、脇役の後始末や人物なしBロールを機械的な最終画にしない。

## 音の役割をp860へ渡す

[BGM・SEの研究資料](../research/film-sound-emotion.md)と[spotting手引き](../../workflow/playbooks/sound-design/affect-and-spotting.md)を参照する。既存の`audio_intent`に、音が支える人物/出来事、何を優先して聞かせるか、必要な静けさ、語りとの分担を具体化する。音の意図はここで考え、実音源の生成と最終秒数への配置は動画確定後のp860で行う。先に作った音源へ無理に脚本を合わせる規則にはしない。sourceにない台詞/出来事や、未登録の構造fieldを追加しない。
