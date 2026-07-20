# Design

## Contract

- historical era: `story_metadata.time: string` -> `script_metadata.time` -> `video_metadata.time`
- contract marker: `story_metadata.scene_time_of_day_contract: required_v1` -> `script_metadata.scene_time_of_day_contract` -> `video_metadata.scene_time_of_day_contract`
- scene daypart: `story.script.scenes[].time_of_day: string` -> `script.scenes[].time_of_day` -> `video_manifest.scenes[].time_of_day`
- derived visual basis: `story.script.scenes[].time_of_day_visual_basis` -> `script.scenes[]` -> `video_manifest.scenes[]`。光源・空/窓外の明るさ・影・色温度を必ず含み、`time_of_day`から導くreview evidenceとする
- `time_of_day`は非空のopen stringとする。代表値は`朝|昼|夕方|夜`だが、`夜明け前|真夜中|夕方から夜|時間帯なし（抽象空間）`なども許容する。空文字や`不明`をprovider promptのplaceholderにしない。
- keyは各sceneに置く。空文字は旧artifact読込時の後方互換に限って受け入れ、新規authoringではreview/verifyで修正する。

## Data flow

1. story authoringがsceneごとの出来事・場所・時間順序から`time_of_day`を確定する。
2. reviewed storyからscript sceneへ同じ値を一方向projectionする。
3. script sceneからmanifest sceneへ同じ値を一方向projectionする。
4. 同sceneの各cutはscene `time_of_day`をcompiler inputとして受け取る。
5. `drawable_prompt_ir.dependencies.time_of_day`と`time_of_day` fragmentを非空時だけ作り、provider promptへ時間帯と光の整合制約を追加する。
6. compiler source digestはscene time-of-dayを含み、値変更時にrequest revisionを変える。
7. deterministic reviewerはmanifest scene値、IR dependency、required group、provider fragmentの一致を検証する。
8. semantic reviewerは歴史的時代と時間帯を別軸で評価し、cut-local light sourceとの矛盾を修正対象にする。
9. 複数場所sceneは順序付き`location_sequence`を保持し、scene reviewは全経路、cut compilerは担当event beatの一場所だけを見る。

## Prompt behavior

- `story_time`: 衣装、髪型、建築、生活道具、素材、技術水準を拘束する。
- `scene_time_of_day`: 空の明るさ、自然光・人工光、影の方向・長さ、色温度を拘束する。
- `scene_material_pack.light_source`: cutに実際に見える具体光源を記述する。
- compilerは3者を順に提示するが、抽象的な制作metadataやscene IDはproviderへ送らない。

## Compatibility

- explicit markerがない既存artifactはscene fieldの欠落・空文字を`""`として読み、placeholderは出さない。歴史的`time` keyだけでは新契約を有効化しない。
- shared location / character / object assetは複数sceneで再利用できるため、scene time-of-dayを自動付加しない。
- scene内で時間帯が変わる場合はscene分割を優先する。単一sceneとして扱う場合は遷移を表す文字列を使う。
