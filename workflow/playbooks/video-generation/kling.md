# Kling 3.0 Prompt Guide

このドキュメントは、ToC で `kling_3_0` / `kling_3_0_omni` を使うときの**動画用 prompt の正本**です。  
汎用原則は `docs/video-generation.md` を参照し、Kling 固有の書き方は本書を優先します。

## 適用範囲

- `video_generation.tool: "kling_3_0"`
- `video_generation.tool: "kling_3_0_omni"`
- `video_manifest.md` の
  - `scenes[].video_generation.prompt`
  - `scenes[].video_generation.motion_prompt`
  - Kling 向けの negative / continuity 制約

## ToC での位置づけ

- `docs/video-generation.md`
  - 動画生成全般の原則
- 本書
  - Kling 3.0 向けの prompt 設計
- `docs/vendor/kling/`
  - API / integration / billing の補助情報

## 参照ルール

- 汎用動画ガイドだけで済ませない
- `video_generation.tool` が Kling 系なら、prompt を書く agent は `docs/video-generation.md` に加えて**必ず本書を参照**する
- `seedance` など Kling 以外では、本書を既定参照先にしない

## Tanaka 記事から正式採用した運用ルール

この章は、[tanaka 記事](https://note.com/noz_tanaka/n/n553795d4619a) から ToC の Kling 運用ルールとして**正式採用**したものを固定化する。

- **start frame と cut 1 を同期させる**
  - `first_frame` と最初の shot の意図・構図・被写体状態を一致させる
- **cut ごとに prompt を分ける**
  - 1 本の長文 prompt に全展開を詰め込まない
- **selection loop を前提にする**
  - 単発確定ではなく、複数生成して良い cut を採る
- **shot card を先に切る**
  - `タイトル / サブジェクト / カメラ / アクション / ボイス` を先に決める
- **API 運用では 1シーン3秒程度を基本単位にする**
  - 長い 1 scene を無理に抱え込まず、短い shot の列として組む

## 記事群から正式採用した recurring prompt 術

- **reference 起点で始める**
  - pure text から始めるより、reference image / element / subject を先に決める
- **不変条件を毎回 lock する**
  - 顔、髪、服、持ち物、役割、環境 anchor を毎 shot で繰り返し固定する
- **カメラは安定寄り**
  - motion 自体が主題でない限り、カメラを暴れさせない
- **見た目と motion を分離する**
  - appearance は reference / subject 側
  - motion は motion control / video reference / action prompt 側で扱う
- **lip sync は読みを崩してでも制御する**
  - 音声品質を優先し、難読漢字はかな表記へ寄せる
- **speech-heavy では読みをかなに寄せる**
  - lip sync や音声生成は、自然な漢字表記より読みの安定を優先する

## Kling 向け基本方針

### 1. 1クリップ1意図に絞る

- 1クリップの中心動作は 1 つにする
- 「人物が振り向く + 爆発 + 群衆が走る + カメラが急上昇」のような多目的 prompt は避ける
- API 運用では **1シーン3秒程度** を基本単位にし、主動作は `1つの感情変化` か `1つの空間アクション` に寄せる

### 2. 被写体固定と動き指定を分離する

- prompt 本文では「誰が / どこで / どう見えるか」を固定する
- `motion_prompt` では「何が / どう動くか」を別で書く
- 同じ情報を両方に重複させすぎない
- speech-heavy な shot では、読みの難しい固有名詞や漢字表現をそのまま音声へ渡さず、かな表記を別で管理する

### 3. 強い continuity anchor を先に置く

- 同一人物の顔、服、髪型
- 同一の小道具、乗り物、舞台装置
- 進行方向、視点、カメラ高さ
- 光源方向、時間帯、天候
- 役割や人物関係

Kling は絵作りの雰囲気は拾いやすい一方、anchor が弱いと shot 間で漂流しやすい。  
scene/cut をまたぐ要素は、毎回同じ語で固定する。

### 4. カメラは「見える変化」に合わせる

- カメラ指示は 1 つか 2 つまで
- 被写体の感情変化が主役なら、複雑なカメラ演出を足しすぎない
- 空間体験が主役なら、被写体の細かな演技を詰め込みすぎない

## 推奨 prompt 構造

### shot card の基本要素

Kling では、`prompt` と `motion_prompt` だけでなく、shot ごとの設計メモとして次の 5 要素を持つ。

- `タイトル`
- `サブジェクト`
- `カメラ`
- `アクション`
- `ボイス`

`video_manifest.md` に field を増やせない場合でも、少なくとも設計段階ではこの 5 要素で分解してから
`video_generation.prompt` と `video_generation.motion_prompt` に落とし込む。

対応関係:

- `タイトル`
  - shot の狙いを一行で要約する
- `サブジェクト`
  - `video_generation.prompt` の被写体 / 場所 / 見た目へ入る
- `カメラ`
  - `video_generation.motion_prompt` のカメラ動作へ入る
- `アクション`
  - `video_generation.motion_prompt` の主動作へ入る
- `ボイス`
  - セリフ、環境音、BGM、読みの注意点として別管理し、必要なら `notes` や音声設計へ渡す

### shot card の必須化

ToC では、Kling 系 scene を書くときは、少なくとも設計段階では shot card を省略しない。

- `タイトル` がない shot は、狙いが曖昧な可能性が高い
- `サブジェクト` が弱い shot は、見た目 anchor が不足しやすい
- `カメラ` がない shot は、motion_prompt が抽象化しやすい
- `アクション` が多すぎる shot は、3秒単位の設計を崩しやすい
- `ボイス` が未整理の shot は、後段の narration / lip sync / ambient 設計で破綻しやすい

### `video_generation.prompt` / `motion_prompt`

`video_generation.prompt`:

```text
[被写体 / 主題]
[場所 / 時間 / 天候]
[画作り / 質感 / 光]
[固定したい見た目]
[このショットで見せたい状態]
```

`video_generation.motion_prompt`:

```text
[主動作]
[カメラ動作]
[速度 / リズム]
[連続性制約]
```

### shot card から prompt へ落とす例

```text
タイトル:
雨上がりの決意

サブジェクト:
短い黒髪で紺の外套を着た若い侍。雨上がりの石畳の路地。夜明け前の青灰色の空気。左頬の細い傷。同じ刀の鞘。

カメラ:
胸の高さから緩やかに寄る。回転なし。

アクション:
侍が息を整えた後、ゆっくり振り向く。

ボイス:
無言。雨音のみ。BGMなし。
```

```text
video_generation.prompt:
実写、シネマティック。短い黒髪で紺の外套を着た若い侍が、雨上がりの石畳の路地に立つ。夜明け前の青灰色の空気、濡れた地面の反射、左頬の細い傷、同じ刀の鞘、静かな緊張感。

video_generation.motion_prompt:
侍が息を整えた後、ゆっくり振り向く。カメラは胸の高さから滑らかに寄る。回転なし。顔、傷、衣装、鞘の位置を維持し、背景の路地の奥行きと雨上がりの反射を保つ。
```

## 書き方の実務ルール

### `video_generation.prompt`

入れる:

- 主役被写体
- 場所と時間帯
- 実写感、質感、照明
- 顔や衣装などの固定条件
- 持ち物、役割、環境 anchor
- その瞬間の感情または状態

入れすぎない:

- 長い因果説明
- 1クリップ内での過剰な展開
- 編集指示（カット、フェード、モンタージュ）

良い方向:

- 「濡れた石畳の路地、夜明け前、冷たい青灰色の空気」
- 「同じ紺の外套、短い黒髪、頬の傷、金の装飾が入った鞘」

避ける方向:

- 「すごく映画的で美しくて感動的」
- 「最初はAして、そのあとBして、最後にCとDが起きる」

### `video_generation.motion_prompt`

入れる:

- 被写体の主動作
- カメラ 1 種類
- 動きの速度
- 何を維持したいか
- 3秒前後の shot で完結する変化

例:

- `主人公がゆっくり振り向く。カメラは肩越しの高さを維持したまま緩やかに寄る。顔立ちと衣装を崩さず、背景の路地の奥行きを保つ。`
- `ボートが前進する。カメラは一人称の高さで安定し、水平線を保つ。揺れは微小、進行方向はぶらさない。`

避ける:

- カメラの連続切替
- 急激な回転
- 被写体、背景、光源が同時に大きく変わる指定

## Selection Loop

Kling は「一発で決める」より、「複数候補から良い cut を選ぶ」方が安定する。

- 同一 shot を複数回生成する
- 比較観点を先に決める
  - 顔の一貫性
  - 構図の安定
  - 主動作の自然さ
  - 光や空間の continuity
  - ボイス / 音の破綻有無
- 修正は無限に継ぎ足さず、必要なら
  - shot を切り直す
  - start frame を更新する
  - shot card を再定義する

「prompt をさらに長くする」より、「shot の責務を切り直す」方を優先する。

## Text-to-Video と Image-to-Video の違い

### Text-to-Video

向いているケース:

- 導入の establishing shot
- 単発の情景カット
- 参照画像がまだない探索段階

コツ:

- 空間、光、主動作を短くまとめる
- 同一キャラ再現が必要なら、参照なし T2V を多用しない

### Image-to-Video

向いているケース:

- キャラクター一貫性が必要
- object bible / scene anchor がある
- 前後フレーム continuity を優先したい

コツ:

- 静止画で構図と見た目を確定してから motion を足す
- `motion_prompt` は「その静止画をどう動かすか」に限定する
- 参照元にない要素を突然増やしすぎない

### reference-first の原則

Kling 系では、pure text だけで同一人物や同一舞台を維持しようとしない。

- 人物:
  - reference image
  - subject / element
  - character bible
- 小道具 / 建物:
  - object reference
  - recurring environment anchor
- motion:
  - video reference
  - motion control

appearance と motion を別レイヤで扱う方が安定する。

## Voice / Lip Sync

speech-heavy な shot では、映像 prompt と同じくらい読みの管理が重要。

- 音声品質を優先する
- 難読漢字、固有名詞、崩れやすい読みはかな表記へ寄せる
- quoted line が必要な workflow では、セリフ文字列を別管理する
- 「見た目の自然さ」と「読み上げの正確さ」が衝突する場合、lip sync では後者を優先する

## Negative / 禁止事項の扱い

Kling では禁止事項の書きすぎも不安定要因になるため、**本当に事故りやすいものだけ**を書く。

優先度が高い禁止:

- 画面内テキスト、ロゴ、透かし
- 顔崩れ、指崩れ、不自然な四肢
- 急なカメラ回転、視点ジャンプ
- フェード、暗転、別ショット化

例:

```text
画面内テキストなし。ロゴなし。顔と衣装の一貫性を維持。不自然な手指や余分な四肢なし。急回転、フェード、ショット切替なし。
```

## ToC 向けテンプレート

### Character-centric shot

```text
video_generation.prompt:
実写、シネマティック。短い黒髪で紺の外套を着た若い侍が、雨上がりの石畳の路地に立つ。夜明け前の青灰色の空気、濡れた地面の反射、左頬の細い傷、同じ刀の鞘、静かな緊張感。

video_generation.motion_prompt:
侍が息を整えた後、ゆっくり振り向く。カメラは胸の高さから滑らかに寄る。顔、傷、衣装、鞘の位置を維持し、背景の路地の奥行きと雨上がりの反射を保つ。
```

### Environment-centric shot

```text
video_generation.prompt:
実写、シネマティック。雲海の上に浮かぶ回廊状の庭園、朝の柔らかな逆光、白い石柱、金箔の反射、水面の薄い霧、静かな神域の空気。

video_generation.motion_prompt:
カメラは一人称の高さで前進する。水平線と中央の導線を維持し、速度は一定、揺れは最小。光の向きと空間の連続性を崩さない。
```

## 悪い例と改善

### 悪い例

```text
主人公が走って振り向いて泣いて敵が現れて爆発してカメラが急上昇して最後に街全体が見える。映画みたいで超かっこいい。
```

問題:

- 主動作が多すぎる
- 被写体固定情報がない
- カメラ変化が多すぎる
- 感情語が抽象的

### 改善例

```text
video_generation.prompt:
実写、シネマティック。煤けた地下通路を走る若い女性、濡れた黒いコート、額に張りつく前髪、非常灯だけが赤く明滅する。逃走直後の緊張で息が荒い。

video_generation.motion_prompt:
女性が走りを緩め、背後を振り向く。カメラは背中側から一定距離で追い、最後に肩越しで横顔を捉える。顔とコートを崩さず、通路の赤い非常灯を保つ。
```

## Agent 向け運用

- `Director` は下流で Kling を使う想定が明示されている場合、story の scene 設計で `1 clip = 1 intention` を崩さない
- `Scriptwriter` / `Immersive Scriptwriter` は `video_generation.tool` が Kling 系なら、本書に沿って `タイトル / サブジェクト / カメラ / アクション / ボイス` を先に整理し、その後 `prompt` と `motion_prompt` に分離する
- `docs/video-generation.md` と本書が衝突する場合、Kling prompt の書き方については本書を優先し、全体運用原則は `docs/video-generation.md` を優先する

---------
