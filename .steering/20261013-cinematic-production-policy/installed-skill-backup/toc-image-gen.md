---
name: toc-image-gen
description: >
  スレッドからToC作品の素材画像・状態variant・cutの開始画像や終了画像を、画像生成APIまたは組み込み画像生成で作成・再生成・編集するよう依頼されたときに使う。「素材を作って」「この画像を直して」「変身後の参照画像も生成して」などの実画像生成が対象。最新の物語状態、採用素材と実際に渡す参照を確認する。画像の説明・批評、prompt設計だけ、動画生成だけでは起動しない。
---

# ToC 画像生成

ToCルートを特定し、`docs/implementation/conversation-media-generation.md` を読む。
素材(p500)と場面画像(p600)を区別し、対象に応じて次のstage readsetを読む。

- 素材: `python scripts/prepare-stage-context.py --stage asset --run-dir <run_dir> --flow <flow>`
- 場面: `python scripts/prepare-stage-context.py --stage scene_implementation --run-dir <run_dir> --flow <flow>`
- 正本: `docs/implementation/asset-bibles.md`、`docs/implementation/image-prompting.md`、
  `workflow/video-manifest-template.md`。

## 生成前

1. 素材は `asset_inventory.md` / `asset_plan.md` / `asset_generation_requests.md`、
   場面は `video_manifest.md` / `image_generation_requests.md` と採用候補を読む。
   未生成、採用済みの再利用、今回の修正対象を分ける。
   キャラ画像の前には `docs/implementation/cast-design.md` と全キャストの設計を読む。
   対象一人だけで決めず、役割・関係・性格の根拠・所作・顔・髪・体格・衣装を全体で比較し、
   意図した共通点と見分ける特徴を定義する。集合人物はmemberごとに分ける。
   `cinematic_direction.json` の `cast_design` から個別assetの実promptへ、描画可能な特徴が
   引き継がれているかを確認する。既存合格素材を一律に作り直さない。
2. 物語の今の状態、登場人数、衣装・道具・空間・光、未開示の出来事を確認する。
   変化前と変化後を区別し、必要な状態素材の欠落を埋めてから依存する場面を作る。
   動作途中の姿勢と、再利用する外観のvariantを混同しない。
   衣装は変更後の全場面へ引き継ぐ状態として、主人公だけでなく各人物を個別に照合する。
   共通手順の「衣装は人物ごとに引き継ぐ状態」を読み、人物ID/memberと衣装状態、
   適用区間、採用参照を対応させる。集合名の素材が一人分なら全員分として複製しない。
   既存の場面画像が人物別の色・形・袖・靴に合わなければ、存在済みでも修正対象にする。
3. 使用する参照画像を実際に開き、役割を決める。
   同一人物の顔、衣装の状態、物の形、背景、開始画像の構図など、何を各参照から保持するかを指定する。
   背景に小さく写る対象しかない場合は、その事実と利用する範囲を記録する。
4. 終了画像は同じcutの補助画像として扱う。生成済み開始画像と変化後の状態素材を参照し、
   変化前だけの描画指定を残さない。補助画像を余分な動画cutやナレーション尺に加えない。
   共通手順の「開始画像と終了画像の差を実画像で照合する」に従い、入力する既存の組を
   事前確認し、生成した終了画像も開始画像と並べて比較する。袖・襟・レースの形や
   付着位置など、意図しない細部の差は修正してから動画用に渡す。
   行為後の反応を見せる目的なら、終了画像の表情・視線・手元にも反映する。
   喜び等を全場面へ一律に追加せず、各画像にはその時点の状態だけを描く。
5. promptは一つの静止した状態として描く。動画で行う動作列を詰め込まない。
   人物・物・比率/サイズ・参照の順序と、実ツールへ渡す画像を照合する。
6. 対象manifest cutに `shot_plan` がある場合はリポジトリの `docs/implementation/shot-direction.md`を読み、各child shotの `initial_view` に対応する開始stillを扱う。親cutの参加者全員や、映らない顔/身体を各stillへ戻さない。`end_view` は設計で選ばれたshotだけに作り、表情は顔が見えて必要な場合だけ描く。

## 実行と保存

- 既存のp500/p600 request・依存順序・通常の構造検証を使う。親素材→状態variant、
  開始画像→終了画像という依存を守り、未完成の参照を並列送信しない。
- Codex組み込み画像生成は、利用可能な `imagegen` スキルの現行手順に従う。
  ローカルの編集対象/参照を先に表示し、実ツールの参照引数へ渡す。
  参照ファイルを読む代わりに、会話に画像が出たことだけを根拠にしない。
  明示指定された別providerはその対応schema/既存経路を確認し、勝手に変更しない。
- 保存先、request ID/生成応答、参照hash、出力hashを結び付ける。
  組み込みツールがrun外へ保存した場合は生成物をrunの指定先へコピーする。採用元は保持する。
- decode、寸法、数・外観・状態を確認し、結果がどのrequestの候補かを記録する。
  ユーザーの採用があれば正式参照へ反映する。画像生成だけの依頼で動画APIを呼ばない。
