# Design

## Contract

- `script.md` に以下を追加する。

```yaml
script_metadata:
  elevenlabs:
    provider: "elevenlabs"
    model_id: "eleven_v3"
    voice_name: "Shohei - Warm, Clear and Husky"
    voice_id: "8FuuqoKHuM48hIEwni5e"
    prompt_contract_version: "v3_tagged_context_v1"
    default_stability_profile: "creative"
    text_policy: "natural_japanese_plus_audio_tags"
```

- cut 単位で以下を持てる。

```yaml
elevenlabs_prompt:
  spoken_context: ""
  voice_tags: []
  spoken_body: ""
  stability_profile: ""
tts_text: ""
```

- `tts_text` は final string であり、authoring 用の source block は `elevenlabs_prompt` に置く。

## Materialization

- helper を `toc/` に置き、次を共通化する。
  - `voice_tags` 正規化
  - `stability_profile` 正規化
  - `elevenlabs_prompt -> tts_text` materialization
  - legacy `tts_text` only cut の fallback

- materialization の順序は固定:
  - `spoken_context`
  - concatenated `voice_tags` with brackets
  - `spoken_body`

## Compatibility

- 既存 cut が `tts_text` しか持たない場合:
  - helper 上は `spoken_body=<tts_text>` の prompt として扱う
- sync の優先順位は維持:
  - `approved_tts_text`
  - `tts_text`
  - materialized `elevenlabs_prompt`
  - narration fallback

## Authoring

- template / script builder / prompt docs は `elevenlabs_prompt` と `tts_text` を両方出す
- reviewer 向け docs では「`elevenlabs_prompt` を直したら `tts_text` も同じ変更で更新する」を明記する
- runtime 側の v2 review key はこの slice では変更しない

### Voice Tag Profile

- voice tag は物語位置で使い分ける。
- 導入 / 通常 narration は `gentle` を基本軸にする。
  - 例: `gentle + curious`
  - 例: `gentle + grateful`
  - 例: `gentle + beckoning`
- 締め / 教訓 / bitter aftertaste の narration は `low + measured` を基本軸にする。
  - 採用例: `[low][measured] 知らない世界には、強い引力があります。`
  - 狙い: 低め、落ち着き、押し出しを抑えた輪郭、説教臭さのない重さ
  - `gentle` は不要なら外す。締めの格を出す cut では、柔らかさよりも低さと測った読みを優先する
- `alpha` は常用 baseline にしない。
  - 使う場合は、輪郭や押し出しを少し足したい cut に限定する
  - Shohei + ElevenLabs v3 では尺や間が伸びる場合があるため、短く締めたい cut では避ける
- 追加 tag は 1 個までを基本にする。
  - 深い余韻: `reflective`
  - 重い結論: `grave`
  - 静かな終止: `quiet`
  - 不穏な気配: `ominous`
- `spoken_context` は原則空にする。
  - 文脈文は読み上げられて尺が伸びるため、再現性と音声品質を優先する cut では使わない
  - 必要な演技は `voice_tags` に集約する
- `spoken_body` は ElevenLabs v3 では漢字かな交じりの自然な日本語を許可する。
  - ひらがな正規化で読みが間延びする場合、自然表記を優先する
  - 例: `知らない世界には、強い引力があります。`
- `stability_profile` は別軸で扱う。
  - `voice_tags` は演技の質感
  - `stability_profile` は読みの揺れ幅 / 安定度
  - `low + measured` でも `natural|creative|robust` の選択は別に行う

### Reproducible Voice Baseline

- provider: ElevenLabs
- model: `eleven_v3`
- voice: `Shohei - Warm, Clear and Husky`
- voice_id: `8FuuqoKHuM48hIEwni5e`
- ending / lesson example:

```yaml
elevenlabs_prompt:
  spoken_context: ""
  voice_tags: ["low", "measured"]
  spoken_body: "知らない世界には、強い引力があります。"
  stability_profile: "natural"
tts_text: "[low][measured] 知らない世界には、強い引力があります。"
```
