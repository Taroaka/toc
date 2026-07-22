# Design

## 1. Semantic QA と media generation の分離

frontend create を次の二段に分ける。

1. `run_pre_media_semantic_pipeline`: scene/cut/asset plan と draft image prompt の review / repair。
2. `generate_media_and_freeze`: asset 生成、reference hash binding、必要なら image prompt 再 review、provider-ready freeze、scene image 生成。

`materialize-only` は 1 を実行して 2 を省略する。draft image review は deferred reference identity を許容するが、`review.image_prompt.request_freeze.status` は `reviewed_draft` とし、p650 `frozen` にはしない。

## 2. Cut still hard boundary

`first_frame_visual_plan` の positive drawable field は単一の現在状態だけを持つ。compiler は次を hard fail にする。

- `A → B → C` などの順序列
- 未解決選択
- scene / cut / motion / review meta
- 明らかな助詞結合破損
- 同じ fragment の重複

抽象概念の物体化、cut 間差分、役割不整合は semantic reviewer の必須 criterion とし、pending template を pass とみなさない。

## 3. Asset subject contract

各 asset entry に次を持つ。

```yaml
subject_contract:
  identity_scope: individual|ensemble|non_character
  subject_count: 1
  member_ids: []

appearance_contract:
  social_position: ""
  occupation_or_role: ""
  occasion_or_state: ""
  silhouette: ""
  materials: []
  condition: ""
  palette: []
  must_avoid: []

reuse_contract:
  mode: neutral_anchor|time_variant|state_variant
  time_of_day: ""
  derived_from_asset_id: ""
```

individual character は `subject_count=1`、ensemble は複数 member identity を同じ参照 sheet 内で混同せず固定する。将来 member 単位へ展開できる情報がある場合は individual asset を優先する。

`appearance_contract` は時代とは別軸で、役割・身分・用途・素材・状態を可視化する。`story_time` は歴史整合を担い、appearance は人物固有の衣装差を担う。

`reuse_contract` だけが時間 variant を有効化する。neutral anchor では scene lighting を除外し、time variant は時間帯を prompt と review trace へ exact 投影する。

## 4. Review inputs

asset-plan semantic pack は plan だけでなく compiled asset request / snapshot を読み、cardinality、appearance、reuse/time、provider prompt の整合を評価する。image-prompt semantic pack は provider-readyかdraftかを明示し、どちらでも prompt 意味品質は同じ rubric で判定する。
