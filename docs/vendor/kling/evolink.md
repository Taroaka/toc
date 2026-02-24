# EvoLink で Kling v3 / O3 を使う（メモ）

このrepoでは、`video_generation.tool` が `kling_3_0` / `kling_3_0_omni` の場合でも、
`EVOLINK_API_KEY` が設定されていれば **EvoLink の Kling API** を優先して利用します。

## 必要な env

- `EVOLINK_API_KEY`
- 任意:
  - `EVOLINK_API_BASE`（default: `https://api.evolink.ai`）
  - `EVOLINK_FILES_API_BASE`（default: `https://files-api.evolink.ai`）

## モデル（override 可能）

- `EVOLINK_KLING_V3_I2V_MODEL`（default: `kling-v3-image-to-video`）
- `EVOLINK_KLING_V3_T2V_MODEL`（default: `kling-v3-text-to-video`）
- `EVOLINK_KLING_O3_I2V_MODEL`（default: `kling-v3-image-to-video`）
- `EVOLINK_KLING_O3_T2V_MODEL`（default: `kling-o3-text-to-video`）

※ モデル名はプロバイダ側で変わり得るので、invalid が出たらここを差し替える。

## 参照画像（image-to-video）

EvoLink は `image_start` / `image_end` に URL を要求します。  
このrepoは `video_generation.first_frame` のローカル画像を **EvoLink Files API にアップロード**して URL 化してから投げます。

## 追加パラメータ（elements / multi-shot 等）

このrepoは `KLING_EXTRA_JSON` / `KLING_OMNI_EXTRA_JSON` を request payload に deep-merge します。
EvoLink 側の `model_params`（例: `element_list` / `multi_shot`）をそのまま透過させる用途に使えます。

