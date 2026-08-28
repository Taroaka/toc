# ToC marketing target architecture requirements

更新日: 2026-08-08

## Goal

Workstream 1 の target architecture を、`副業に取り組む個人` と `小規模ビジネス運営者` の2つへ更新し、offer 検証と下流 handoff の正本を作る。

## Confirmed decisions

- primary target A は `side_business`: 副業に取り組む個人
- primary target B は `small_business_operator`: 小規模ビジネス運営者
- 2 target は広告、LP、CTA、analytics を分離する
- `personal_brand` は primary persona ではなく `small_business_operator` の use case とする
- Purpose `人の心を動かし、人生を豊かにする。` と brand line `あなたの想いを、映像に。` は維持する
- Workstream 1 は `marketing/README.md`, `marketing/go-to-market.md`, `marketing/positioning-and-offer.md` を所有する
- Workstream 2 / 3 の正本は直接編集せず、変更要求を handoff する

## Success criteria

1. `marketing/README.md` が新しい2 target を上位正本として定義する
2. `marketing/positioning-and-offer.md` が各 target の working definition、job、desired progress、objection、CTA、offer hypothesis、qualification を定義する
3. `marketing/go-to-market.md` の Workstream 1 starter と first task が新 target を参照する
4. root pointer と marketing router が古い primary persona を future task へ渡さない
5. Workstream 2 / 3 が所有する `marketing/LP/` / `marketing/SNS/` は本変更で直接編集しない
6. 従業員数、価格、収益効果、最初の paid beachhead を evidence なしで確定しない

## In scope

- `marketing/README.md`
- `marketing/go-to-market.md`
- `marketing/positioning-and-offer.md`
- `docs/root-pointer-guide.md`
- `.codex/skills/marketing-skills-router/SKILL.md`
- 本 steering directory

## Out of scope

- `marketing/LP/`
- `marketing/SNS/`
- 公開 site / form / production code の実装
- 広告出稿、営業連絡、決済受付
- 最終価格、契約、保証の確定
- production quality gate の変更

## Evidence and source precedence

1. ユーザーの 2026-08-08 の最新 target 指示
2. 本 requirements / design
3. `marketing/README.md`
4. `marketing/positioning-and-offer.md`
5. 下流 marketing artifact

