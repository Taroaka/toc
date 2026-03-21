# Script Method: Visual Value Midroll Pass

## Use when

- 物語本筋だけでは映像の見せ場が弱い
- 竜宮城や玉手箱のように、読者は知っているが細部を見たことがない要素がある
- 動画生成AIの強みを使って、中盤に強い視覚報酬を置きたい

## Goal

`visual_value.md` を使って、動画の 20% - 80% に
**4-6カット・各4秒・ナレーションなし** の価値パートを挿入する。
Ryugu 系の題材では、乙姫をすぐ出さずに「宮殿の内部探索」を先に見せ、最後の cut で入口/門前に止めて次のドラマへ渡す。

## Workflow

1. `story.md` から中盤の余地を確認する
2. `visual_value.md` から、最も価値が高い part を1つ選ぶ
3. その part を `script.md` では visual-first の silent sequence として落とす
4. `scene_conte.md` / `video_manifest.md` では、各カットを 4 秒 fixed cut として分解する
5. narration は `audio.narration.tool: "silent"` と `text: ""` を使い、説明を入れない

## Quality gate

- 価値パートが 20% - 80% に入っている
- 4-6カットでまとまっている
- 各カットが 4 秒で、ナレーションなし
- 文字説明に頼らず、形・光・動き・機構で価値が伝わる
- 後続の本筋へ自然に接続している

## Canonical example

- 浦島太郎:
  - `ryugu_palace` を `object_bible` で固定
  - 中盤に「竜宮城の中身をPOVで探索する」6カットを置く
  - 各 cut は約4秒、実写の見せ物として gate / corridor / atrium / spectacle を段階的に見せる
  - 最後は乙姫の登場直前の門前で止め、次のドラマへ接続する
