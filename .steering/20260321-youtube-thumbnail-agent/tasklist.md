# Tasklist: YouTube サムネイル用プロンプト生成エージェント

## 1) 仕様化

- [x] `docs/implementation/agent-roles-and-prompts.md` に新役割を追加する
- [x] 入力源が `物語名` と `output/<topic>_<timestamp>/` の両対応であることを明記する

## 2) エージェント登録

- [x] `.claude/agents/youtube-thumbnail-prompt-writer.md` を追加する
- [x] 画像生成は行わず、構造化プロンプトを返す責務を明記する

## 3) 出力品質

- [x] 16:9 / 1280x720 以上 / 高可読性 / 高コントラストの制約を入れる
- [x] 装飾文字、背景、構図、avoid、final prompt を返す形式にする

## 4) 検証

- [x] 追加した定義が既存 agent ドキュメントの流儀と矛盾しないことを確認する
