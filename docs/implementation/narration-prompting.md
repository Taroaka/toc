# Narration Prompt Projection

Narration prompt は story/scene/cut design の全文を連結せず、registry で用途を決めて
spoken text へ一方向に投影する。正本は `toc/narration_prompt_projection_registry.py`。

## Projection axes

各 design key は次を持つ。

- `authoring_relevance`: `required | conditional | none`
- `spoken_projection`: `derive | may_surface | must_not_surface`

`time_of_day_visual_basis`、camera metadata、image/video prompt、internal IDs、path、hash、
withheld/reveal IDs は spoken text へ直接出さない。Visible facts は原稿が重複説明にならない
範囲で読み、narration の役割は因果、内面、時間、視点、世界の rule、意味、aftertaste に置く。

registry が空の conditional value を prompt に入れないこと、required/candidate/constraint/
exclude の分類が安定していること、must-not-surface values が本文へ出ないことを ordinary
projection tests で確認する。

## Full-run authoring

cut ごとに独立作文せず、次の順で進める。

1. audience promise、narrator bible、open loop/payoff、scene attention arc、causal handoff、silence budget を決める
2. cut 境界なしの continuous full draft を書く
3. narration spans を canonical cut order へ anchor する
4. `narration`（公開用）と `tts_text`（provider用）を分ける
5. pronunciation、sentence length、pause、audio duration を普通に検証する

画面に明らかな物理行動は映像へ任せる。映像だけで伝わらない因果、内面、時間、視点、
world rule、意味を音声へ足す。非日常空間の導入で直接説明を使う場合も、後段の reveal を先出ししない。

## Projection example

```yaml
narration_projection:
  registry_version: narration_prompt_projection_registry_v1
  global:
    story_time: {authoring_relevance: conditional, spoken_projection: may_surface}
    theme: {authoring_relevance: required, spoken_projection: derive}
  scene:
    time_of_day: {authoring_relevance: conditional, spoken_projection: may_surface}
    time_of_day_visual_basis: {authoring_relevance: none, spoken_projection: must_not_surface}
  cut:
    visible_facts_in_frame: {authoring_relevance: conditional, spoken_projection: derive}
    must_not_reveal: {authoring_relevance: required, spoken_projection: must_not_surface}
    narration_should_add: {authoring_relevance: required, spoken_projection: may_surface}
    image_prompt: {authoring_relevance: none, spoken_projection: must_not_surface}
```

## References

- `docs/script-creation.md`
- `docs/implementation/video-integration.md`
- `toc/narration_prompt_projection_registry.py`

