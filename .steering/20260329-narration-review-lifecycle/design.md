# Design

## Contract surface

- 正本: `docs/implementation/video-integration.md`
- 運用導線: `docs/how-to-run.md`
- machine-facing contract: `docs/data-contracts.md`
- テンプレート注記: `workflow/*video-manifest-template.md`
- playbook: `workflow/multiagent-immersive-narration-playbook.md`

## Review metadata

各 `audio.narration` は少なくとも次の review field を持てる。

- `agent_review_ok: true|false`
- `agent_review_reason_keys: []`
- `agent_review_reason_messages: []`
- `human_review_ok: true|false`
- `human_review_reason: ""`

配置先は `audio.narration.review` とする。

## Review scope

review 対象は renderable node 単位とする。

- scene-level narration: `sceneXX`
- cut-level narration: `sceneXX_cutYY`

`tool: "silent"` は finding なしで pass 扱いにする。

## Automated criteria

初期実装は、意味理解よりも TTS 入力事故を止める機械判定を優先する。

- 空 text
- `TODO` / `TBD` / `未記入` などのメタ marker
- `http://`, `https://`, `www.`, email, markdown link, backtick などの読み上げ事故になりやすい literal
- v2 で不向きな `[` `]` audio tag
- 数字 / 英字略語 / `%` などの未正規化表記
- 長すぎる文
- 句読点不足
- `カメラ`, `ズーム`, `パン` などの映像指示語漏れ

## Flow integration

`scripts/generate-assets-from-manifest.py` に narration review gate を追加する。

- 画像生成前の image prompt review と同様に、音声生成前に review script を自動実行する
- unresolved finding が残る場合は `--fail-on-findings` で止める
- 必要時のみ `--skip-narration-review` で回避可能にする

## Reason key set

初期 canonical key は以下とする。

- `narration_empty`
- `narration_contains_meta_marker`
- `tts_unfriendly_literal`
- `unsupported_audio_tag_for_v2`
- `needs_text_normalization`
- `sentence_too_long_for_tts`
- `missing_pause_punctuation`
- `visual_direction_leaked_into_narration`
