# ToC marketing purpose and sales parallelism requirements

更新日: 2026-08-08

## Goal

ToC を本気で販売するため、既存の機能訴求より上位にある Purpose と、訪問者が一瞬で自分事として理解できる customer-facing brand line を marketing 正本へ追加する。同時に、複数の AI スレッドが marketing repo を並行して扱っても判断と編集が衝突しない 3 workstream の運用契約を定義する。

## Confirmed decisions

- Purpose は `人の心を動かし、人生を豊かにする。`
- customer-facing brand line は `あなたの想いを、映像に。`
- `世界に増やす` は企業側の願望を主語にするため、短い顧客向けコピーには使わない
- brand line は 0 秒で直感的に理解させ、詳細は 3 秒 / 10 秒の下位コピーで補う
- `右脳設計` は外部向けの脳科学的主張ではなく、説明より先に visitor の変化を理解させる内部設計原則として扱う
- 既存の functional promise、emotional promise、2 persona、offer facts、proof policy は維持する
- 今後の議論と repo 編集は 3 workstream へ分ける

## Success criteria

1. `marketing/README.md` が Purpose、customer-facing brand line、既存の functional / emotional promise の階層を正本として定義している
2. LP 正本が `0 秒 -> 3 秒 -> 10 秒` の message disclosure と `あなたの想いを、映像に。` を反映している
3. SNS 正本が brand line を投稿の visitor-facing entry として継承している
4. `marketing/go-to-market.md` が 3 workstream の目的、所有ファイル、決めること、成果物、依存関係、非対象、同期方法を定義している
5. 各 workstream は同じ canonical file を同時編集しない
6. 収益保証、未計測の速度主張、偽の希少性を追加しない
7. marketing の変更が通常の ToC production quality gate を上書きしない

## In scope

- `marketing/README.md`
- `marketing/go-to-market.md`
- `marketing/LP/README.md`
- `marketing/LP/personas.md`
- `marketing/LP/lp-strategy.md`
- `marketing/LP/toc-marketing-site.md`
- `marketing/SNS/README.md`
- `marketing/SNS/YouTube/analytics-kpis.md`
- `marketing/SNS/YouTube/strategy.md`
- `marketing/SNS/YouTube/monetization.md`
- 本 steering directory

## Out of scope

- 公開サイトのコード実装
- `server/web/` の変更
- 料金、パッケージ、導入条件の最終決定
- 広告出稿、営業連絡、外部サービスへの書き込み
- 通常の research / story / script / image / video production 仕様
- 既存 campaign artifact の一括修正

## Evidence and source precedence

1. ユーザーの 2026-08-08 の最新指示
2. 本 requirements / design
3. `marketing/README.md`
4. `marketing/LP/` / `marketing/SNS/` の部門正本
5. channel / campaign 固有 artifact
