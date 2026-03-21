# シーンコンテ（文字＋画像コンテのハイブリッド）テンプレ

目的:
- 1つのシーンを「1カット=1枚」ではなく、**3〜5カット**でストーリー性を持って見せる
- 各カットの入力画像（`sceneX_Y.png`）を作り、その隣接カット同士で **8秒程度のI2V** を複数作って、合算して「1シーン」にする
- 英雄の旅、感情ジェットコースターの設計を、カット割りで達成しやすくする

重要制約:
- 映像内に文字は存在しない（字幕/看板/刻印/ロゴ/透かし禁止）
- `visual_value.md` に基づく探索ブロックは、**4-6カット / 各4秒前後 / ナレーションなし** で設計してよい
- Ryugu 系の探索ブロックでは、乙姫の登場を最後まで遅らせ、門・回廊・玉座の間の入口で止める
- 各カットの画像は毎回新規生成しなくてよい。必要なのは、同じ場所/物体/人物状態をまたぐ continuity anchor を作るか再利用するかの判断

---

## 0) メタ情報

- topic: `<topic>`
- run: `output/<topic>_<timestamp>/`
- created_at: `<ISO8601>`
- experience: `cinematic_story|cloud_island_walk|...`（`ride_action_boat` は legacy alias）
- source_script: `output/<topic>_<timestamp>/script.md`
- rule: `scene_conte は script.md を分解した橋渡し資料。新しい物語情報を足さない`

## 1) シーン設計（映画での役割）

- scene_id: `<int>`
- scene_name: `<短い名前>`
- role_in_film: `<このシーンは映画のどの役割? 例: threshold / temptation / ordeal / return>`
- hero_journey_beat: `<英雄の旅のフェーズ>`
- emotional_beat: `<観客の感情をどう動かす? 例: curiosity→awe→dread>`
- conflict_or_question: `<このシーンが投げる問い / 緊張>`
- payoff: `<次のシーンで回収する伏線 or 今ここで回収するもの>`

## 2) 世界・連続性（文字なしで伝える）

- location: `<場所>`
- time_weather: `<時間帯/天候>`
- continuity_from_prev: `<前カット/前シーンから必ず一致させるアンカー>`
- continuity_to_next: `<次へ繋ぐアンカー（進行方向/照明/色/構図）>`
- forbidden_visuals:
  - `on-screen text`
  - `subtitle text`
  - `watermark`
  - `logo`

## 3) 登場人物・舞台装置（bible参照）

- character_ids: `[...]`
- object_ids: `[...]`
- notes: `<このシーンで“見せたいディテール”を、bibleで固定する>`

---

## 4) カット割り（3〜5カット）

このシーンの「時間の流れ」を、**カット列**として設計する。

各カットは以下の情報を埋める（画像コンテの要点を優先）:

推奨ルール:
- 1カット = 1ナレーション
- メインカット（最低1つ）: 5–15 秒（ナレーション実秒）
- サブカット（任意 / 複数可）: 3–15 秒（ナレーション実秒）
- 15秒以下でも、scene と narration を書き終えた時点で分割の要否を都度判断する
- `visual_value.md` に基づく視覚報酬カットは例外で、4秒固定 / ナレーションなしを許可する
- その場合、Ryugu 探索ブロックのように「見せ場を先に積む」構成を優先し、登場人物の初出は最後の cut に寄せる

### Cut `<scene_id>_1`

- cut_purpose: `<このカットで観客に与える情報>`
- narration_text: `<このカットのナレーション（メイン=5–15秒 / サブ=3–15秒）>`
- shot_type: `<WS/MS/CU/POV/etc>`
- composition: `<前景/中景/背景 + 画面アンカー + 視線誘導>`
- camera: `<高さ/レンズ感/手ブレ/移動（前進/パン/ドリー）>`
- action: `<何が起きる>`
- key_prop_or_setpiece: `<このカットの主役アイテム/舞台装置>`
- lighting_color: `<キーライト/色温度/陰影>`
- vfx_practicality: `<practical effectsとして成立する表現>`
- duration_hint_seconds: `<推定(例:8)>`
- output_image: `assets/scenes/scene<scene_id>_1.png`
- output_clip: `assets/scenes/scene<scene_id>_1_to_2.mp4`
- avoid: `<手崩れ/余計な人物/文字/破綻>`

### Cut `<scene_id>_2`

(同様)

### Cut `<scene_id>_3`

(同様)

### Optional Cut `<scene_id>_4` / `<scene_id>_5`

(必要に応じて)

---

## 5) `video_manifest.md` への落とし込み（チェック）

- `scenes[].cuts[]` として、各cutを `image_generation` に落とし込んだ（新規生成が不要な cut は既存 anchor の再利用でよい）
- 各cutに `character_ids: []` と `object_ids: []` が明示されている
- cut画像の `output` は `assets/scenes/scene<scene_id>_<cut>.png` に揃っている
- 各I2V clip の `first_frame/last_frame/output` が隣接cut同士になっている
