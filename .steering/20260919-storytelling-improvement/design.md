# ToC全体の物語改善計画

状態: 計画。2026-09-19の作業ツリーを読んで作成。コードは変更していない。
要件: [requirements.md](requirements.md)。実装順・検証: [tasks.md](tasks.md)。

## 1. 方針と最初の成果

最初の実装単位は、**原作を読む上流から、物語を変えずにp450のscript/manifestを出すまで**とする。
p300だけを簡素化しても、p400が同じ定型の内容を再生成すれば改善は届かない。
p300 authoring、p400の入力・変換、対応validatorを一緒に切り替える。

その後、素材・画像・動画への投影、ナレーションと結末、生成後の比較へ広げる。
runtimeのp100〜p900順序は変えない。ここでの順序は開発・導入の順序である。

読書結果から重視するのは、具体的な行為、人物固有の認識、外的成果と内的変化の違い、
情報の提示順、意味のある細部、解釈の余白である。
それらを全sceneの追加フォームへ変換せず、必要な場面を考えるための手掛かりにする。

## 2. 現状から分かったこと

下記はソースコード・仕様の静的確認。新しいrunの生成結果や観客への効果は測定していない。
ファイルと関数名を主な位置情報とする。行番号は今回の作業ツリー時点。

| ID | 根拠 | 確認した内容 | 判断 |
| --- | --- | --- | --- |
| E1 | `toc/research_author.py:40`、`toc/story_authoring.py:434,464` | 原作からの調査、完全なresearch registry、事実/信念/観客知識の区別、曖昧な結末を許す指示が既にある | 上流を全面的に作り直さず保持する |
| E2 | `scripts/toc-immersive-frontend-run.py:12218` | frontend経路で固定配色・定型value・固定anchor・時間制限の光を持つvisual文書を直接作る | p300共通authoringへ置換する対象 |
| E3 | 同 `::_scene_value_amplification_for_profile`、`::_adaptation_intent_for_profile` | scene位置でvalueを選ぶfallbackと、尊厳/選択/証明、希望/時間圧力などの固定文がある | 作品ごとの判断をコードが代行している |
| E4 | 同 `::_scene_blueprint`、`::_apply_story_scene_to_blueprint`、`::_scene_intent_for_cut_design` | 元のpurpose/conflict/turn等を一部重ねるが、欲求・物証・制約等の定型が残る。scene番号4/7の時間制限や終端の証明もある | p300後にも意味を上書きする経路がある |
| E5 | 同 `::_build_script_and_manifest` のp410入力組立（9774付近） | E4のscene intentが実際にscene authoring recordへ入る。cut expressive contractも10735付近で生成される | 名前にscaffoldがあっても、単なる未使用例としては除外できない |
| E6 | `toc/adaptation_value_contract.py:50,387` | 相反感情、象徴的瞬間、演出5領域等を要求し、p300のamplification全文をp400と照合する | writerだけ直すとvalidatorが旧形式を要求する |
| E7 | frontend `::_build_asset_artifacts_from_manifest`（11819付近） | manifestで使われるassetから組む一方、coverageに固定の時間制限の光を記録する | 内容を生成する固定値と技術的既定値を分ける |
| E8 | `docs/script-creation.md:18,39,47` | 各sceneに変化/不可逆性を求める文と、理解の維持や反転不要を認める文が併存する | 新契約では静かな場面を排除しないよう仕様とreaderを揃える |
| E9 | `scripts/ai/toc-immersive-narration-multiagent.py::_prompt_text`（359付近）、`toc/narration_arc.py:312` | 執筆指示は未回収の問いを残さないとする一方、validatorは `intentional_unresolved` を既に許す | 新schema追加より先に指示の矛盾を修正する |
| E10 | `toc/cut_context_packet.py`、`toc/image_prompt_compiler.py:194,725` | event、reveal、前後情報を渡すpacketと、現在時点の描画状態を要求するcompilerがある | 中間データを新設する前に既存機構を使う |
| E11 | `toc/narration_prompt_projection_registry.py` | 設計情報を背景・必須・候補・開示制約・読み上げ禁止へ分類する仕組みがある | 全設計文をナレーションへ流す変更は不要 |
| E12 | `toc/video_prompt_compiler.py:440` | 主動作がない場合に、first frameありなら呼吸・重心移動を選ぶfallbackがある | 人物不在や動作指定なしのfixtureで到達条件を確認し、必要なら対象依存に直す |

E12は枝の存在を確認した段階で、すべての景観生成へ実際に流れるとまでは断定しない。
同様に、promptの指示の矛盾は確認できるが、すべての出力が誤った結末になるとは扱わない。

### すでに有用な基盤

source registry、sceneのstart/end state、reveal/preservation、creative additions、cut context packet、
drawable/current-moment compiler、narration projection、未解決loopの表現は活かす。
本の概念を受けて、別のbelief registryや心理スコアを重ねることを初手にしない。

## 3. 改善領域と優先順位

| 優先 | 改善領域 | 主な効果 | 主な工程 |
| --- | --- | --- | --- |
| 最優先 | 定型の内容生成の除去とsourceの引き継ぎ | 原作が下流で別の筋に変わることを防ぐ | p300・p400 |
| 高 | 事実・信念・観客の理解の保持 | 人物を単純な感情ラベルにせず、自己説明のずれを残す | p100・p200・p400 |
| 高 | 未解決・語りの知識境界・結末 | 意図的な曖昧さを説明や教訓で閉じない | p400・p700 |
| 中 | 細部・比喩・外観と状態・動作 | 原作にない物を作らず、重要な行為を読み取れる画へ | p500・p600・p800 |
| 中 | 編集後の意味を比較する開発検証 | 単体cutは正しくても連結で意味が変わる問題を把握 | p900・開発時検証 |

共通の成功条件は、データが揃うだけでなく、どの情報を守り、何を表現として選んだか説明できること。

## 4. 領域ごとの設計

### A. p100/p200：本文と人物理解を保つ

既存のfull registryと `AUDIENCE_MEANING_INSTRUCTION` を土台にする。
人物の自己説明、観察できる行為、他者の評価が異なる場合、既存の本文・grounding_note・
source refs・creative additionsへ記録する。全人物に傷や隠れた欲求を要求しない。

作者への追加の手掛かりは、読書結果のうち次の差分に絞る。

- 当人の対処法が役に立ってきた面と、別の関係で払う代償を同時に保持する。
- 否定された信念が、本人の自己像と本当に結びついているかを読む。
- 外的な成果と、内面・関係の変化を一つの勝敗ラベルへ圧縮しない。
- 自己説明のずれを、意図的な嘘と自動的に解釈しない。
- 所属集団や語り手の見方を、世界全体の事実として一般化しない。

新作ではこれらを発想の手掛かりとして使える。adaptationでは原作の不明点を心理創作で埋めない。
scene順の因果説明も、原作にない原因を発明しない。既存の因果接続指示については、
実際のsourceで支持できる接続と、作者の配置理由の混同がないかfixtureで確認する。

### B. p300：必要な見せ方だけを執筆する

[2026-09-17のp300設計](../20260917-p300-source-first-planning/design.md) を本計画に取り込む。
`visual_value.md`、p310/p330を維持し、新規は同設計の `source_first_v2` を使う案とする。
メタデータ/入力binding、全sceneのIDと空を許すnotes、任意の全編方針、任意のcontinuityを中心にする。

authorはresearch/story本文とユーザー方針を直接読む。コードはID・形・digestを扱い、
尊厳・解放・配色・時間制限などを定型文で作らない。
演出の選択が不要ならnotesを空にできるが、scene未出力やauthor失敗をコードが空で埋めてはならない。

比喩は何を想像/理解させるかから考え、名詞をそのままobject候補へ変換しない。
カメラ視点も語りの人称だけで決めない。ユーザーが選んだ体験形式の視点制約は保持する。

### C. p400：具体的な出来事を基準にcutへ落とす

`_scene_blueprint` の定型文を先に作って一部だけ上書きする経路を、新規v2では使わない。
authorのscene/event/start/end/revealとp300のnotesからscene intentとcutを執筆する。
上流にない作者判断が必要なら、p400のauthorが具体的に行う。Pythonが未知の心理や事件を補わない。

必須にするのは、scene/source対応、担当event/beat、必要な状態・役割・開示順・handoff等の
整合性に必要な情報である。dramatic question、相反感情、不可逆なturn、圧力、象徴的瞬間を
全sceneで非空にする要件は見直す。空でもよい項目と、欠けるとsourceを失う項目を分ける。

start/endの構造は維持しつつ、状態が維持されるsceneも表せるようにする。
物理的状態、人物の認識、観客に開示する情報を同じ「変化」の一欄へ畳み込まない。
これは三種類の新しい必須カードを作るという意味ではなく、既存の状態と知識の表現を使う。

`cut_expressive_contract` のために全cutへ呼吸・重心移動・圧力・沈黙を追加しない。
具体的な行為とcutの役割は既存viewer/event/motion欄へ記し、同じ内容の二重執筆を減らす。
schemaの任意化はwriter/reader/validator/template/source ledgerを同じ変更単位で扱う。

### D. p500/p600/p800：意味を失わず媒体へ変換する

assetはstory/scriptの具体的な対象と使用箇所から作る。
p300とp500にある固定の「時間制限を示す象徴的な光」は新規経路から除く。
同じ物であるための特徴と、濡れる・開く・持ち主が移る等の状態差分を区別する。

画像では既存compilerのcurrent moment/temporal boundaryを使い、未来の結果を一枚に混ぜない。
重要な細部を全ての装飾と同じ強さで扱わず、何を読み取らせる画かをauthorが選ぶ。
抽象語の禁止リストを増やすだけで解決したことにはしない。

動画では明示した動作と反応の順序を保つ。
主動作なしのfallbackは対象に合うものかを確認し、人物不在に呼吸等を追加しない。
意味のある動作が必要なcutで動作が未記述なら、無関係な微動で成功扱いせずownerの入力不備として扱う。
静止を意図したcutと、未完成のcutの区別には既存のmode/contractを優先する。

### E. p700：話すべき情報を選び、結末を守る

既存projection registryとnarrator bibleを再利用する。
「未回収の問いを残さない」を、生成側が勝手に作った未回収の約束を残さないことと、
原作が意図した未解決を保持することに分ける。
`intentional_unresolved` は既存表現を使い、新しい同義enumを作らない。

`audience_information` 等がrequired contentへ入る現状を踏まえ、
人物の推測や自己説明を、客観的な語りとして断定する経路を確認する。
技術的なprojectionの存在は保ちながら、authorが読む背景と発話できる事実の用途を守る。

映像が担う情報を毎回実況しない。一方、画像では伝わらない背景や時間を語りが担うことも許す。
「一度の選択」を「それ以来ずっと」の変容へ広げない。`human_locked` テキストは引き続き保持する。

### F. p900：連結による意味の違いを開発時に確認する

既存のrender、duration、decode、provenanceチェックはそのまま維持する。
新しい常設の意味判定agentや点数gateは作らない。

開発時の少数の比較例で、反応cutの接続先、時系列、受け渡し、最後の画と語りを確認する。
原作の情報がどこで変わったかを、source→script→prompt→出力の順に追えるようにする。
技術検査だけでは感動や理解を保証しないため、観察結果と作者の狙いを分けて報告する。

## 5. 以前のp300計画から広げる点

| 以前の範囲 | 本計画で追加する内容 |
| --- | --- |
| p300と最低限のconsumer互換 | p400独自の定型blueprint、scene番号による意味付与も対象 |
| notes空を許す | 後段のscene/cut authoringとvalidatorも空を埋め直さない |
| 上流を読む | 本文、人物の見方、観客知識が実際のauthor入力へ届くことを検証 |
| p700への引き継ぎ | 未解決loopとpromptの矛盾、語りによる心理・結末の断定を扱う |
| asset候補 | p500のcoverage生成、p600/800の時点・対象に合った投影まで確認 |

旧計画を別実装として重複遂行しない。要件・最小p300構造・互換方針を再利用し、実装の進行は本計画に集約する。

## 6. 情報と版の境界

原作を保存する仕組みと、新しい著作権資料を全文取得する作業は分離する。
既存のresearch/story/run資料と、利用できる出典を用いる。
書籍ノート全体を毎stageのpromptに流し込まず、必要な判断指針を正本stage docsへ短く反映する。
読書資料は根拠の追跡先として残し、作品固有の事実の出典に混ぜない。

新規runは対応するv2 writer/reader/validatorを一式で使う。
既存v1は旧契約を維持し、markerなしlegacyも勝手にv2認定しない。
未知版・v1/v2混在・source digest不一致は普通の構造エラーにする。
`adaptation_value_contract` を消して原作保護の検査全体を迂回しない。

新規writerの失敗を旧定型fallbackで救済しない。技術的な既定値と、物語内容の捏造を区別する。
既存runを再設計する場合は別の明示的操作とし、p400 rebuildが現在visual_valueを保存する境界にも注意する。

## 7. 実装時に確定する限定事項

- p400で非空を要求している全フィールドのreader/validator一覧。最初の実装で列挙し、局所的に版を分ける。
- 削除候補のfallbackが、新規・legacy・world-walkのどの経路から到達するか。定義名だけで死んだコードと判断しない。
- 主観の帰属が既存のsource/context表現で足りるか。足りなければ必要な情報に限定して追加する。
- 比較に使う実run。既存成果物を読み取り、選んだ入力を固定して使う。無断で再生成・上書きしない。

この限定事項があるため、全工程の品質改善が既に実証されたとは報告しない。

## 8. 読書資料との対応

- [追加読解](../../docs/reading/the-science-of-storytelling/reread-findings.md): 特に信念の重要度、成果と代償、自己説明、二層、集団、視点。
- [20論点](../../docs/reading/the-science-of-storytelling/concepts.md): 概念の区別と適用上の注意。
- [6つの架空例](../../docs/reading/the-science-of-storytelling/worked-examples.md): 回帰fixtureの発想元。productionの定型文にはしない。
- [読解範囲](../../docs/reading/the-science-of-storytelling/coverage.md): 未確認と原研究未検証の境界。
