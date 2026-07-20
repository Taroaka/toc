# Requirements

## Goal

物語設計図が時代背景を文字列で保持し、素材画像と scene/cut 画像の生成プロンプトへ同じ値を反映できるようにする。

## Success criteria

- `story.md` の `story_metadata.time` は string とする。
- 古典・既存物語では `〇〇時代` の形式で具体的な時代を入れる。
- ユーザー創作では空文字を許容する。
- 非空の `story_metadata.time` は `video_manifest.md` と asset / scene image API prompt まで失われない。
- 空文字の場合は画像プロンプトへ空の時代指定や不自然な placeholder を追加しない。
- 時代指定は衣装、建築、生活道具、素材、技術水準の時代整合を画像モデルへ要求する。

## Scope

- story / manifest の正本テンプレートと設計ドキュメント
- frontend create flow の story -> manifest -> asset/scene prompt 経路
- image prompt compiler と関連テスト

## Out of scope

- UI に時代入力欄を追加すること
- 過去 run の一括 migration
- 個別作品の時代をこの変更内で網羅的に確定すること

