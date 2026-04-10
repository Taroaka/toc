# Design

- `generate-assets-from-manifest.py` が request file を出力する
- `--materialize-request-files-only` で request file だけ書いて終了できる
- asset stage は `asset_generation_requests.md`
- cut image stage は `image_generation_requests.md`
- video stage は `video_generation_requests.md`
- request file には selector ごとの final prompt / references / output を残す
- video request には first_frame / last_frame も残す
