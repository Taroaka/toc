# 調査根拠 — 2026-10-10

本書は確認した事実と設計判断を区別する。ローカルの行番号は調査時点。作業ツリーには別作業の変更も存在する。

## ローカル実装

| 根拠 | 確認した事実 | 設計への含意 |
|---|---|---|
| `toc/p400_authoring.py:609` | character_idsの説明は「このframeに見えるID」 | 全cut参加者として再解釈すると互換性が壊れる。新しい契約を別versionで定義する |
| `toc/p400_projection.py:52`, `:91`, `:128`, `:139`, `:146`, `:184` | 同じcharsを必須役割・素材依存・開始画の被写体・開始画参照・画像compilerに渡す | 後から登場する人物まで開始画へ流れやすい。全員表示を直接要求するvalidatorだと断言はしない |
| `toc/p400_authoring.py:678` | 世界の状態と見える範囲を分ける指示は既にある | 方針追記だけでは足りず、IDと画像requestの投影を直す |
| `toc/p400_authoring.py:662`, `:663`, `:679` | beatとcutは1対1固定ではない。前後cutを考慮し、距離・角度・焦点の変更も許す | 撮影概念が皆無ではない。実行データへの受け渡しを改善する |
| `toc/cinematic_language.py:11`, `:22`, `:133` | stagingは順序付き文章、performanceはcut単位のaction/reaction/timing。人物・対象ごとの目的との型付き結合はない | 既存stagingを捨てず、必要な演技だけ個体IDと結ぶ |
| `toc/p400_authoring.py:325`, `:683`; `toc/image_prompt_compiler.py:313` | subは人物なし。手足・人影も禁止される | 足元の挿入画をsubと同義にしない。役割と可視人物を独立させる |
| `toc/image_prompt_compiler.py:270`, `:280` | IDsが渡ると人物・場所の描画記述を要求する | 足元だけの画に顔や広い背景を要求しないよう、見える部分に合わせて投影する |
| `toc/video_prompt_compiler.py:618`, `:630` | allowlistがなければ開始画像にない人物等を新しく出さない | 画面外にいる既存人物と、未来の事件・未登録の新人物の追加を区別する |
| `toc/video_prompt_compiler.py:634`, `:681`, `:1005` | Kling向けに主動作1つ・連続ショットを追記し、カメラ命令数を数え、一部を切り詰める | 演出方針とAPI制約を分離。文字列切捨てで意図を失わせない |
| `toc/cinematic_language.py:71` | film_language overrideのnullは継承解除として既に使われる | 既存nullの意味を壊さず、新契約のnullも項目別に定義する |
| `toc/p400_projection.py:122`, `:192`; `toc/p400_authoring.py:811` | 通常投影は音声原稿も出力し、再利用はpolicy・入力に依存する | 採用音声がある作品にはvisual-only経路と音声hash/尺の保護が必要 |
| `toc/video_provider_capabilities.py:65` | higgsfield経路のモデル判定は現状Seedance 2.5が対象 | 会話でKlingを利用できた事実だけで、共通バックエンドも対応済みとしない |
| `server/image_gen_app.py:9653`, `:10852` | 複数箇所から共通video compilerを呼ぶ | 一方だけのprompt修正ではなく、preview/実行/会話の共通解決処理へ入れる |

## 公開一次資料

### 映画の撮り方

[Adobe: Close-up shot](https://www.adobe.com/uk/creativecloud/video/production/cinematography/camera-shots-and-angles/close-up-shot.html) は、寄りが表情や重要な細部へ注意を向けること、手元などのinsertで行為を伝えられること、前後の編集との関係を考えることを説明する。

**本提案の判断**: 「顔の寄り→足元」は、異なる画角であることだけでなく、視聴者が読む対象を内面から行為へ移せる点が重要。毎cut違う画角にする規則にはしない。固定画や反復が意図に合う場合も残す。実際の作品についての良否はユーザーの観察を入力としており、本調査で再視聴判定したわけではない。

### 画像から動画への分担

[Runway: Image to Video Prompting Guide](https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide) は、入力画像が構図・被写体・光・スタイルを定め、テキストが動作・カメラ・時間進行を指示すると説明する。途中で現れる要素や変身は追加の可視記述が必要な例であり、全要素を毎回埋める必要はない。これはRunway向けの資料で、Klingの性能保証ではない。

**本提案の判断**: 開始画を作る前に動画内の見せる順序まで設計する。開始画に結果や全参加者を詰め、後から動画promptで消す方式にしない。文章による演技の時刻指定は制御意図であり、生成結果のフレーム精度を保証しない。

[Runway: Camera Terms, Prompts & Examples](https://help.runwayml.com/hc/en-us/articles/46749315925395-Camera-Terms-Prompts-Examples) は、画のサイズ・角度・カメラ移動を別の表現として整理している。

**本提案の判断**: framing、見せる部分、focus、camera movement、人物の移動を別項目にする。レンズの数値や複雑な3D座標は必要な場合だけ指定する。

### JSONのnull

[JSON Schema: null](https://json-schema.org/understanding-json-schema/reference/null) と [object / required](https://json-schema.org/understanding-json-schema/reference/object#required) では、nullとキーの欠落は別であり、requiredはキーの存在を指定する。

**本提案の判断**: nullableと未解決を混同しない。rootの型とID・参照・時刻は厳密にし、不要な芸術的指定だけnull/空配列を選べる。これはJSON仕様から自動的に決まるものではなく、ToC側の契約として定義する。

### HiggsfieldのKling Standard

[Higgsfield: Kling 3.0 Standard API reference](https://open.higgsfield.ai/models/kling-video/v3.0/std/image-to-video/api-reference) に、`image_url`必須、`last_image_url`任意、整数duration 3–15秒、`sound`、`multi_shots`、`multi_prompt`、`elements: array[string]`が掲載される。

**未確認**: 同ページだけではelementsの登録・識別子・参照の結び方や各入力の併用条件は確定できない。配列に素材URLを入れれば同一人物が保てるとは扱わない。multishotの編集精度も未検証。

**本提案の判断**: provider/model/input-mode別の実送信adapterが必要。最初は独立したshotを編集で接続する方式を基準とし、native multishotは別機能として検証する。料金・精度・生成成功は本調査では実測していない。
