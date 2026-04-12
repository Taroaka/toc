# Requirements

- `image_generation_requests.md` の scene image request は、画像生成 API 実行前に自然言語エージェントが具体化する工程を持つこと
- request authoring は `script.md` の `human_review.approved_visual_beat` / `visual_beat` を最優先で参照すること
- `video_manifest.md` は request authoring の implementation source-of-truth として併読すること
- request authoring subagent は `docs/implementation/image-prompting.md` を必読とすること
- motion や first/last frame の判断が絡む request authoring subagent は `docs/video-generation.md` も必読とすること
- request authoring は scene 単位で分割でき、scene ごとに並列実行可能であること
- scene ごとの request authoring では、他 scene への stateful 言及を request 本文へ持ち込まないこと
- scene ごとの request authoring 成果物は、shared request file ではなく scene 単位 scratch file に出せること
- メインエージェントは scene rewrite を統合して `image_generation_requests.md` を更新できること
- request 本文には、参照画像に写っている人物 / 場所 / 小道具が、この場面でどう使われるかを明示すること
- request 本文の first-frame 具体化はコードの定型変換ではなく、自然言語エージェントが担当すること
- 人レビューを通した request が、そのまま生成時の prompt / references 凍結成果物として使われること
