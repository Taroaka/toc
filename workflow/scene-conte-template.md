# シーンコンテ（映画的 scene / cut 設計）テンプレ

目的:

- 1つの scene を「1カット=1枚」ではなく、劇的な時間の流れを持つ **cut 列**として設計する。
- p400 の `scene_intent` と `cut_blueprint` を、p600 の still prompt / p800 の motion prompt へ渡せる形にする。
- 英雄の旅、感情ジェットコースター、reveal 順序を、カット割りで達成しやすくする。

重要制約:

- p400 では完成 image prompt を書かない。`first_frame_brief` と `visual_beat` に留める。
- 映像内に文字は存在しない（字幕/看板/刻印/ロゴ/透かし禁止）。
- `visual_value.md` に基づく探索ブロックは、可視化必須の authored beat と distinct semantic obligation から cut 数と各尺を導き、ナレーションなしで設計してよい。固定 cut 数・固定秒数は使わない。
- 各カットの画像は毎回新規生成しなくてよい。必要なのは、同じ場所/物体/人物状態をまたぐ continuity anchor を作るか再利用するかの判断。

---

## 0) メタ情報

- topic: `<topic>`
- run: `output/<topic>_<timestamp>/`
- created_at: `<ISO8601>`
- experience: `cinematic_story|cloud_island_walk|world_walk|...`（`ride_action_boat` は legacy alias）
- source_script: `output/<topic>_<timestamp>/script.md`
- source_visual_value: `output/<topic>_<timestamp>/visual_value.md`
- story_time: `<story.time の open string。古典は時代名、ユーザー創作は空文字可>`
- rule: `scene_conte は script.md を分解した橋渡し資料。新しい物語情報を足さない`

---

## 1) Scene Contract（映画での役割）

- scene_id: `<int>`
- scene_name: `<短い名前>`
- importance: `<optional: low|medium|high|critical。欠落だけでは非blocking>`
- target_duration_seconds: `<optional: 計画用の秒数。cut floorには使わない>`
- role_in_film: `<threshold / temptation / ordeal / reveal / return / aftertaste など>`
- dramatic_question: `<この scene の間、観客が追う問い>`
- scene_spine: `<authored event の意味上の流れを1文で要約。固定 function 列は要求しない>`
- value_shift:
  - from: `<開始時の価値/感情/関係>`
  - to: `<終了時の価値/感情/関係>`
  - visible_evidence:
    - `<画面だけで変化が読める証拠>`
- causal_turn: `<次 scene を発生させる不可逆の出来事/決断/発見>`
- audience_information:
  - `<この scene で渡す情報>`
- withheld_information:
  - `<この scene ではまだ隠す情報>`
- reveal_constraints:
  - `<早出し禁止の対象>`
- emotional_beat: `<curiosity→awe→dread のような感情変化>`
- visual_thesis: `<この scene を代表する映画的な一枚絵>`
- handoff_to_next_scene: `<次へ繋ぐアンカー（視線/音/道具/方向/問い）>`
- scene_conflict_engine:
  - desire: `<この scene で主体が欲しているもの>`
  - obstacle: `<妨げる力>`
  - stakes: `<失敗すると失うもの>`
  - escalation: `<圧力の上がり方>`
  - no_return_point: `<後戻りできなくなる瞬間>`
- audience_knowledge_delta: `<観客がこの scene の前後で何を知り、何をまだ知らないか>`
- handoff_chain: `<object / sound / gaze / gesture / threat / question のID付きhandoff>`

---

## 2) 世界・連続性（文字なしで伝える）

- location: `<場所>`
- time_of_day: `<朝|昼|夕方|夜|作品固有の時間帯を表す非空文字列>`
- time_of_day_visual_basis:
  - sky_brightness: `<空と環境の明るさ>`
  - light_sources: `<自然光・人工光の種類と向き>`
  - shadows: `<影の長さ・硬さ・向き>`
  - color_temperature: `<時間帯に整合する色温度>`
- weather: `<天候。時間帯とは別に保持>`
- screen_geography: `<前景/中景/背景、入口/出口、奥行き、進行方向>`
- continuity_from_prev: `<前カット/前シーンから必ず一致させるアンカー>`
- continuity_to_next: `<次へ繋ぐアンカー>`
- character_state_start: `<scene開始時の人物状態>`
- character_state_end: `<scene終了時の人物状態>`
- forbidden_visuals:
  - `画面内テキスト`
  - `字幕`
  - `ウォーターマーク`
  - `ロゴ`
  - `アニメ/漫画/イラスト調`

---

## 3) 登場人物・舞台装置（bible参照）

- character_ids: `[...]`
- object_ids: `[...]`
- location_ids: `[...]`
- asset_notes:
  - `<この scene で同一性を固定すべき人物/物/場所>`
- staged_reveal_notes:
  - `<初出で全部見せない asset がある場合、どこまで見せるか>`

---

## 4) Authored Beat Inventory（scene 内部の劇的流れ）

次の行は候補例であり、必須 ladder ではない。実際には `scene_event.event_sequence[]` の一意な `beat_id` と任意の非空 `beat_function` を順序どおり列挙する。1 beat だけの scene や独自 function も許容する。

| beat | 目的 | 画面で見える証拠 | cut候補 |
|---|---|---|---|
| setup | 場所・人物状態・問いを立てる | `<visual evidence>` | `<cut id>` |
| pressure | 障害/誘惑/危険を強める | `<visual evidence>` | `<cut id>` |
| threshold | 引き返せない一歩の直前 | `<visual evidence>` | `<cut id>` |
| turn | 発見/決断/反転 | `<visual evidence>` | `<cut id>` |
| payoff_or_handoff | 結果/余韻/次への入口 | `<visual evidence>` | `<cut id>` |

---

## 5) カット割り

推奨ルール:

- 1カット = 1意図。
- cutは映像編集単位。narration spanは複数cutをまたいでよく、または明示的な silent cut。
- cut 数は distinct semantic obligation ID 数と、可視化必須の authored event beat ID 数から逆算する。importance や target duration だけでは増やさない。
- 1 authored beat に 1 つの十分な可視責務しかない scene は、1 cut でもよい。
- 各 cut の秒数は provider capability と scene の意味上の必要尺に合わせる。尺不足は narration / silence、既存 cut の duration、scene 構成または target 調整で解決する。
- spectacle / transformation / emotional reversal / proof reveal は、独立した authored beat または可視責務がある段階だけを複数 cut に分ける。

### Cut `<scene_id>_1`

- cut_role: `main|sub|transition|reaction|visual_payoff`
- cut_function: `<authored beat に整合する任意の非空 function。setup|pressure|threshold|turn|payoff|reaction|handoff は候補例>`
- target_beat: `<このカットで観客に与える1つの情報/感情>`
- screen_question: `<このカットの間、観客が画面から読む問い>`
- visual_beat: `<画として何が見えるか>`
- first_frame_brief: `<動画が動き出す直前に見えている初期状態。prompt本文には制作メタを書かない>`
- motion_brief: `<p800 motion prompt 専用。p600 image prompt authoring では参照しない>`
- narrative_position: `opening|middle|ending`
- voice_function: `information|emotion|causality|time|viewpoint|world_rule|contrast|meaning|aftertaste|silence`
- visual_distance_policy: `stay_close|contextual|meaning_first|silent`
- pronunciation_targets: []
- narration_role: `setup|fact|emotion|contrast|aftertaste|silent`
- narration_text: `<このカットのナレーション。silent の場合は空文字>`
- shot_type: `<WS/MS/CU/POV/etc>`
- composition: `<前景/中景/背景 + 画面アンカー + 視線誘導>`
- camera: `<高さ/レンズ感/手ブレ/移動>`
- action_threshold: `<まだ完了していない行為の入口>`
- key_prop_or_setpiece: `<このカットの主役アイテム/舞台装置>`
- lighting_color: `<キーライト/色温度/陰影>`
- vfx_practicality: `<practical effectsとして成立する表現>`
- duration_hint_seconds: `<推定秒>`
- still_image_plan: `generate_still|reuse_anchor|no_dedicated_still`
- output_image: `assets/scenes/scene<scene_id>_cut<cut_id>_base.png`
- output_clip: `assets/scenes/scene<scene_id>_cut<cut_id>_video.mp4`
- must_show:
  - `<必ず見せるもの>`
- must_avoid:
  - `<手崩れ/余計な人物/文字/reveal早出し/破綻>`
- done_when:
  - `<reviewer が完了判断できる条件>`

### Cut `<scene_id>_2`

（同様）

### Cut `<scene_id>_3`

（同様）

### Optional Cut `<scene_id>_4` / `<scene_id>_5+`

（必要に応じて）

---

## 6) `video_manifest.md` への落とし込み（チェック）

- [ ] `scenes[].scene_intent` に dramatic_question / value_shift / causal_turn / visual_thesis がある。
- [ ] `scenes[].cuts[]` として、各 cut を正本 `cut_contract` に落とし込み、必要なら旧 reader 用 `scene_contract` alias を用意した。
- [ ] 各 cut に `cut_function` と `first_frame_brief` と `motion_brief` がある。
- [ ] 各 cut に `character_ids: []` / `object_ids: []` / `location_ids: []` が明示されている。
- [ ] `image_generation.prompt` は p600 で作り、6 block を必ず持つ。
- [ ] cut画像の `output` は `assets/scenes/scene<scene_id>_cut<cut_id>_base.png` に揃っている。
- [ ] 各 I2V clip の input / output / duration / motion_prompt が cut contract と一致している。
- [ ] narration が visual beat を説明しすぎず、映像で読める情報を重複しすぎていない。
