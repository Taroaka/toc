# Requirements

## Goal

物語全体の歴史的時代とは別に、各 scene が朝・昼・夕方・夜などの時間帯を文字列で保持し、scene/cut画像の生成プロンプトへ同じ値を反映できるようにする。

## Success criteria

- 新規の`story.md`、`script.md`、`video_manifest.md`の各sceneは、非空の`time_of_day: string`を持つ。自然な時間帯がない抽象世界でも`時間帯なし（抽象空間）`のように、照明設計へ使える意図を明示する。
- 新規contractは各metadataの`scene_time_of_day_contract: required_v1`で明示し、歴史的時代の`time` keyを契約判定に流用しない。
- 値は `朝`、`昼`、`夕方`、`夜`に限定せず、`夜明け前`、`真夜中`、`夕方から夜`など物語に必要な表現を許容する。
- `story_metadata.time` / `video_metadata.time` は歴史的時代、scene `time_of_day` は一日の時間帯として混同しない。
- 非空のscene `time_of_day`は、同sceneの全cutのprovider-facing image prompt、dependency、digestへ失われずに届く。
- markerのない旧artifactの欠落・空文字は互換読込時に`""`として扱い、時間帯placeholderをpromptへ追加しない。markerのある新規authoringではreview/verifyの修正対象にする。
- 時間帯は空の明るさ、自然光・人工光、影、色温度へ反映し、既存のcut-local `light_source`と矛盾させない。
- stale・欠落・別sceneの時間帯を持つcompiled promptはreviewで検出する。

## Scope

- story / script / manifestの正本templatesとdata contract
- frontend create flowのscene設計とstory -> script -> manifest projection
- scene image prompt compiler / materializer / server-side recompile
- deterministic / semantic image prompt reviewと回帰テスト

## Out of scope

- 共有asset promptへscene固有の時間帯を無条件に焼き込むこと
- 過去runの一括migration
- UIへの時間帯入力欄追加
- 1つのscene内でcutごとに別時間帯へ変わる設計。必要ならsceneを分けるか、`夕方から夜`のようなscene値で表現する
