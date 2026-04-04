# Design

## Evaluator

- `review-narration-text-quality.py` は既存 manifest 読み込みに加えて sibling `script.md` を読む
- scene/cut selector ごとに次を hydrate する
  - `story_phase`
  - `story_role` (`opening|middle|ending`)
  - `script_narration`
  - `script_scene_summary`
- `story_role_fit` rubric を追加し、従来の `non_visual_value` rubric を置き換える
- `story_role_fit` は phase 優先、script 不在時は全 narratable cut の位置比率で fallback する
- `anti_redundancy` は opening では緩め、中盤以降で強く見る
- canonical finding は `narration_story_role_mismatch` を追加し、`narration_adds_too_little_non_visual_value` は新規には使わない

## TTS Text

- manifest schema に `audio.narration.tts_text` を追加する
- `text` は表示・編集用の原稿、`tts_text` は読み上げ専用原稿とする
- 生成時は `tts_text` があればそれを優先し、無ければ `text`
- 自動かな変換は今回入れず、authors が `tts_text` を埋める運用にする
- templates / playbook では ElevenLabs 用 `tts_text` はひらがな主体で書くことを明記する

## Compatibility

- 既存 manifest で `tts_text` が無くても動く
- contract (`target_function` / `must_cover` / `must_avoid` / `done_when`) は継続利用する
- review report / state.txt の rubric key は `story_role_fit` へ更新する
