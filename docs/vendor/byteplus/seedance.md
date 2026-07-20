# BytePlus ModelArk: Seedance（動画生成）

## 概要

ToC の `scripts/generate-assets-from-manifest.py` は、ByteDance/BytePlus の ModelArk（Ark API）経由で **Seedance** の動画生成に対応している。

- タスク作成: `POST /contents/generations/tasks`
- タスク取得: `GET /contents/generations/tasks/{id}`
- 完了後: `content.video_url` をダウンロードして `video_generation.output` に保存

## 使い方（manifest）

`video_generation.tool` に `seedance` を指定する。

```yaml
video_generation:
  tool: "seedance"
  input_image: "assets/scenes/scene01_base.png"   # first_frame として送る
  motion_prompt: "カメラはゆっくりドリーイン。髪が風で揺れる。"
  output: "assets/scenes/scene01.mp4"
```

### 参照画像（キャラ/アイテム一貫性）

この実装では **`video_generation.references[]`** を Seedance の `reference_image` として送る（`role: "reference_image"`）。画像生成用 `image_generation.references[]` を動画へ暗黙転用せず、動画reviewで選ばれたordered listだけを送る。

```yaml
render_units:
  - unit_id: "1"
    video_input_contract:
      input_mode: "reference_images"
    video_generation:
      tool: "seedance"
      references:
        - "assets/scenes/scene01_cut01.png"
        - "assets/storyboards/scene01_storyboard.png"
```

`first_frame` / `last_frame` を使うframe-boundary modeと、`references[]` を使うmultimodal-reference modeは相互排他である。reference modeではframe fieldsを空にし、reference対応I2V modelを選ぶ。開始画像をstrictなfirst frameとして固定する必要がある場合はreferencesを併用しない。

Seedance 1.0 の duration は2–12秒、reference-image-to-videoの参照画像は1–4枚である。ToCはこの上限をprovider capabilityとして、storyboard unit分割、manifest検証、materialization、approval、server/CLI実行の全箇所で共通適用する。共通の60秒上限だけでSeedance requestを承認してはならない。

現在のadapterにはseparate negative fieldがない。compilerはSeedanceの追加禁止をpositive promptの`constraints`へinlineし、`negative_prompt`は空文字としてhash・reviewする。

## 必要な環境変数（例）

- `ARK_API_KEY`（公式ドキュメント準拠）
- `ARK_API_BASE`（デフォルト: `https://ark.ap-southeast.bytepluses.com/api/v3`）
- モデル:
  - `ARK_SEEDANCE_I2V_MODEL`（I2V）
  - `ARK_SEEDANCE_T2V_MODEL`（T2V）

互換のため、`ARK_API_KEY` が未設定なら `SEADREAM_API_KEY` をフォールバックで使う。

## オプション

- 音声:
  - デフォルトは `generate_audio=false`
  - 有効化: `--ark-generate-audio`（または `ARK_EXTRA_JSON` で上書き）
- 上級者向け:
  - `--ark-extra-json` / `ARK_EXTRA_JSON` でリクエスト payload をマージして拡張パラメータを渡せる
  - `model` / `content` / `resolution` / `ratio` / `duration` などreview済みfieldの上書きは拒否する

## 実装メモ

- ローカル画像は `data:image/<fmt>;base64,...` にエンコードして送る（File API upload は使っていない）。
  - 画像サイズが大きいとリクエストが重くなるため注意。

## 公式資料

- [BytePlus ModelArk video generation API / model capability table](https://docs.byteplus.com/api/docs/ModelArk/2298881)
- [Seedance video input mode API reference](https://docs.byteplus.com/en/docs/modelark/1520757)
