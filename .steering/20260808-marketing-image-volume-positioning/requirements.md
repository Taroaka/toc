# ToC marketing image-volume positioning requirements

更新日: 2026-08-08

注記: 制作形式は、`.steering/20260809-marketing-two-production-modes/` の決定により、画像一括生成と動画制作の2つへ更新された。

## Goal

ToC の強みを動画制作だけに限定せず、必要な複数画像を設計・生成・選択・再利用できる image-batch capability と、画像から動画までを一つの制作フローへ統合できることを Workstream 1 の positioning / offer 正本へ追加する。

## Confirmed decisions

- common brand line `あなたの想いを、映像に。` は維持する
- 直後の output range は `一枚の画像から、一本の動画まで。` とする
- product category は AI 動画制作システムから AI ビジュアル制作システムへ広げる
- output mode は `image_batch`, `video`, `integrated` とする
- persona と output mode は別軸として扱う
- default public image copy は `必要な画像を、まとめて。`
- `大量生成` は requested / generated / accepted 点数、時間、human work、cost、revision、provenance、quality acceptance が揃った場合だけ公開 claim にする
- Workstream 2 / 3 の正本は直接編集せず handoff を作る

## Success criteria

1. `marketing/README.md` が画像 batch と動画制作を同格の product capability として定義する
2. `marketing/positioning-and-offer.md` が output mode、offer hypothesis、claim boundary、proof requirement を定義する
3. `marketing/go-to-market.md` が persona / output mode の二軸と下流作業を反映する
4. marketing router と root pointer が画像・動画の product scope を future task へ渡す
5. `PRF-001` の image file count を、採用枚数が未分類のまま公開 claim にしない
6. `marketing/LP/` / `marketing/SNS/` を本 task で直接編集しない

## In scope

- `marketing/README.md`
- `marketing/go-to-market.md`
- `marketing/positioning-and-offer.md`
- `.codex/skills/marketing-skills-router/SKILL.md`
- `docs/root-pointer-guide.md`
- 本 steering directory

## Out of scope

- `marketing/LP/`
- `marketing/SNS/`
- 画像・動画 generation pipeline の実装変更
- 公開 site / form の実装
- 画像枚数、速度、費用削減、売上効果の未計測 claim
- offer price の確定

## Evidence

- `docs/how-to-run.md`: image batch size、image max concurrency、variant generation、review gate
- `docs/adr/0004-image-generation-provenance-before-parallelism.md`: request-bound provenance と bounded parallel generation
- `docs/implementation/codex-built-in-image-runbook.md`: production parallelism と output ownership
- `marketing/SNS/proof-inventory.md`: PRF-001 の image file count は candidate evidence で、publish-ready ではない
