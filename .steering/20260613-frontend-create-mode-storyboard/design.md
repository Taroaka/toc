# Frontend Create Storyboard Mode Design

## UI

`server/web/src/main.tsx` の新規作成 Dialog に小さな `Select` を追加する。選択肢は次の2つ。

- `normal`: `通常`
- `scene_storyboard`: `1scene=1ストーリーボード式`

通常は既存 endpoint と request body を維持する。storyboard mode だけ新 endpoint を呼ぶ。

## API

新 endpoint:

```text
POST /api/image-gen/runs/create/storyboard
```

request body は通常作成と同じ `title` / `source`。storyboard mode は実画像あり固定なので `generate_images=false` は公開しない。

status polling は既存 job store を使い、`GET /api/image-gen/runs/create/{job_id}` を共用する。

storyboard mode の run id は通常版と並べた時に判別できるよう、予約時の title slug に `_storyboard` を足す。

```text
通常: シンデレラ_20260615_2152
storyboard: シンデレラ_storyboard_20260615_2152
```

## Backend Flow

1. 新 endpoint で run dir と create job を予約する。
2. 既存 p680 frontend create helper を通常どおり実行する。
3. 生成済み cut 画像を scene ごとに集める。
4. 各 scene に `assets/storyboards/<scene_selector>_storyboard.png` を作る。
5. `video_manifest.md` に scene 単位の `render_units[]` を追加する。
6. `video_generation_requests.md` を render unit 単位で書く。
7. p680 通常 validation に加えて storyboard artifact / request validation を行う。

## Storyboard Image

Storyboard image は deterministic composite として作る。AI で再生成せず、Codex image generation で作られた各 cut 画像をグリッドに配置する。

出力は 16:9 の PNG。文字ラベルは入れない。cut 画像の意味と画面内容だけを storyboard reference として渡す。

## Manifest Contract

各 scene は cut を維持しつつ、次の形の render unit を持つ。

```yaml
render_units:
  - unit_id: 1
    source_cut_ids: ["1", "2", "3"]
    storyboard_image: assets/storyboards/scene10_storyboard.png
    video_generation:
      tool: kling_3_0_omni
      first_frame: assets/storyboards/scene10_storyboard.png
      input_image: assets/storyboards/scene10_storyboard.png
      references:
        - assets/storyboards/scene10_storyboard.png
      output: assets/scenes/scene10/scene10_unit1.mp4
```

`video_generation_requests.md` は render unit selector を `## scene10_unit1` のように出し、`source_cuts` を併記する。

## Risks

- ストーリーボード一覧画像を first frame として扱う provider では、動画が一覧画像をそのまま動かす可能性がある。初期実装では request prompt に「一覧画像をそのまま映さず scene 動画へ翻訳する」制約を入れ、人間レビュー対象として残す。
- p680 時点で動画生成 request を materialize するため、slot は p830 に進めず、artifact と pending review state だけを残す。
