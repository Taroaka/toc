# Design

- `review-image-prompt-story-consistency.py` に `first_frame_readiness` rubric を追加する
- mid-action 動詞があり、かつ first-frame cue が無い prompt を `image_prompt_not_first_frame_ready` として検出する
- docs は「scene image = 動画の最初の1フレーム」で統一する
- request 本文の first-frame 具体化は、人レビューを踏まえた自然言語エージェントが担い、スクリプトは `script.md` の `visual_beat` と既存 prompt を request へ整形する役に留める
