# Design

- `p620` は scene image request の human review 帯とする
- `p620` に入ったら、対象範囲を scene 単位で分割し、scene ごとに request authoring subagent を割り当てられる
- 各 subagent は少なくとも次を読む
  - `script.md`
  - `video_manifest.md`
  - 現在の `image_generation_requests.md`
  - `docs/implementation/image-prompting.md`
- motion や first/last frame の判断が絡む scene では、各 subagent は `docs/video-generation.md` も読む
- 各 subagent は shared request file を直接編集せず、scene 単位の scratch rewrite を出す
- メインエージェントが scene rewrite を統合して `image_generation_requests.md` を更新する
- request authoring の semantic source priority は次
  1. `script.md` の `human_review.approved_visual_beat`
  2. `script.md` の `visual_beat`
  3. `video_manifest.md` の scene/cut contract と既存 prompt
- request authoring の出力規則は次
  - stateful な前後 scene 言及を書かない
  - `cut` のような運用メタ語を prompt 本文に入れない
  - 参照画像の何を維持し、何をこの場面で変えるかを書く
  - `references` が空なら `[参照画像の使い方]` 節を本文に入れない
  - request metadata には実 path を残すが、本文には `assets/...png` のような path を直接書かない
  - 本文では `人物参照画像1`, `場所参照画像1`, `小道具参照画像1` のような役割付きラベルを使う
  - 複数参照がある場合も metadata の並び順で番号を固定し、人レビュー時に path とラベルを対応づけられるようにする
  - scene image は動画の最初の1フレームとして具体化する
- request generator のコードは request の骨格整形と metadata materialize を担う
- request の意味具体化は自然言語エージェントが担い、必読ドキュメントのルールに従う
- 人レビュー通過後の `image_generation_requests.md` が、そのまま provider 実行前の凍結成果物になる
