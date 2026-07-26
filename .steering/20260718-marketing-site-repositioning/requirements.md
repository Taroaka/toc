# ToC marketing site repositioning requirements

更新日: 2026-07-18

## Goal

ToC のマーケティング正本を、民話・神話チャンネル中心の訴求から、個人が動画を圧倒的に速く、簡単に制作し、副業または個人ブランド構築へつなげる動画制作システムの訴求へ再設計する。

## Background

現行資料は、テスト題材として制作していた民話・神話を ToC 自体の主要価値と混同している。また、公開サイトを Notion と Google フォームで仮設する前提や、marketing の対象を SNS のみに限定する記述が残っている。

ユーザーが今回確定した方向性は次のとおり。

- ToC を使う意義は、動画制作を圧倒的に速く、簡単にすること
- 第一対象は個人
- 直接訴求する主要ペルソナは `副業を始めたい人` と `個人ブランドを構築したい人`
- 2 ペルソナは同一コピーへ丸めず、別の欲求・障壁・CTA で扱う
- 感情・直感に先に届く設計は、神話の感情ではなく、訪問者本人の可能性、解放感、自己効力感、期待へ向ける
- 民話・神話は ToC の商品テーマではなく、制作能力を示すテスト事例の一つ
- 既存 ToC 制作フロントとは別に、独立した公開マーケティングサイトを作る
- 提供物は ToC 動画作成システム一式の納品
- 納品後の ToC 月額料金は 0 円。外部 API 料金は別途、使用量に応じて発生

## Success criteria

1. `marketing/README.md` が新しい positioning と 2 ペルソナを正本として定義している
2. 公開サイト / LP が独自サイトとサイト内フォームを前提にしている
3. Hero、価値階層、感情遷移、ペルソナ分岐、CTA が具体化されている
4. SNS / YouTube は、ToC の能力と利用後の未来を伝える獲得チャネルとして定義されている
5. 民話・神話の個別資料が product positioning の正本として参照されない
6. repo pointer と marketing router が LP / public site を含む新しい scope を指す
7. 通常の research / story / image / video production rules と marketing rules の境界は維持する
8. LP 部門が、動画の情報価値、offer facts、訴求順序、proof、法務、accessibility、performance、検証を定義する
9. section 別の LP prototype と縦長 composite を `marketing/test/` に保存する

## In scope

- `marketing/README.md`
- `marketing/LP/`
- `marketing/SNS/README.md`
- `marketing/SNS/YouTube/strategy.md`
- `marketing/SNS/YouTube/monetization.md`
- `marketing/SNS/YouTube/analytics-kpis.md`
- `docs/root-pointer-guide.md`
- `docs/implementation/assistant-tooling.md`
- `.codex/skills/marketing-skills-router/SKILL.md`
- 本 steering directory

## Out of scope

- 公開サイトのコード実装
- ドメイン取得、ホスティング契約、広告出稿
- ToC 制作フロント `server/web/` の変更
- 動画生成 pipeline、story、script、image、narration、render の仕様変更
- 浦島太郎の公開作業そのもの
- 料金の最終決定

## Evidence and source precedence

1. ユーザーの 2026-07-18 の最新指示
2. この requirements / design
3. `marketing/README.md`
4. channel / campaign 固有資料

浦島太郎や民話・神話に限定されたファイルは campaign artifact とし、ToC 全体の positioning を上書きしない。
