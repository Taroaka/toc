# Design

## Contract

- canonical field: `story_metadata.time: string`
- 値の例: `平安時代`, `江戸時代`, `ヴィクトリア時代`
- ユーザー創作: `""` を許容
- `time` は時刻・時間帯ではなく、作品世界の歴史的時代背景を表す。

## Data flow

1. story authoring が `story_metadata.time` を決める。
2. reviewed story から runtime profile へ `story_time` として取り込む。
3. `video_manifest.md` の `video_metadata.time` へ転記する。
4. asset prompt は非空時に時代背景ブロックを追加する。
5. scene/cut の `image_api_prompt_v2` compiler は `story_time` を dependency として digest / IR に含め、非空時だけ provider prompt に時代背景を描画制約として追加する。

## Compatibility

- field が無い既存 story / manifest は空文字として扱う。
- 空文字の場合、既存 prompt 出力を変えない。
- 時代情報は review/debug metadata ではなく provider-facing prompt 本文へ入れる。

