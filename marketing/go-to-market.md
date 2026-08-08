# ToC Go-to-Market Operating Guide

更新日: 2026-08-08

この文書は、ToC を販売するための議論と repo 更新を 3 本の AI スレッドで並行して進める際の責務、成果物、同期方法を定義する。positioning の正本は `marketing/README.md` とし、この文書はそれを上書きしない。

## Objective

```text
あなたの想いを、映像に。
  -> 正しい顧客が自分事として理解する
  -> 実在する proof で信じる
  -> 自分の動画案を入力する
  -> 適合する相手と商談する
  -> 納品可能な条件で受注する
  -> 最初の動画と継続制作で価値を確認する
```

raw views や lead 数だけを成功にしない。persona 別に、qualified consultation、proposal、closed won / lost、delivery、first / second video まで学ぶ。

## Shared decisions

次は全 workstream に影響する shared decision であり、Workstream 1 が正本を更新した後に下流へ反映する。

- Purpose / customer-facing brand line
- category / primary personas / beachhead persona
- offer facts / delivery boundary / pricing display policy
- 公開可能な claim と必要な proof
- common CTA と persona-specific CTA
- qualified lead / disqualification の定義

下流スレッドは市場反応を evidence として返せるが、shared decision を独自に上書きしない。

## Workstream 1: Positioning and Offer

### Question

`最初に誰の、どの切実な問題を、何として、いくらで解決するのか。`

### Owns

- `marketing/README.md`
- `marketing/go-to-market.md`
- offer / positioning 用の新規 marketing 正本

`marketing/LP/` と `marketing/SNS/` は参照のみとし、変更要求は各 owner へ handoff する。

### Discuss and decide

1. 最初に本気で取りに行く beachhead persona
2. その persona が今すぐ解消したい job / obstacle
3. system delivery の納品物、導入範囲、顧客作業、保守・更新境界
4. 導入費、外部 API 費、optional service の価格仮説と表示方法
5. 最初の購入行動を consultation / diagnosis / demo / first-video package のどれにするか
6. qualification / disqualification 条件
7. objection と、それを解消する実在 proof
8. 証拠が揃うまで使わない claim

### Outputs

- beachhead decision
- offer specification
- message hierarchy
- claim-to-proof matrix
- qualification / disqualification contract
- price hypothesis and sales boundary
- Workstream 2 / 3 への approved decision handoff

### First task

`副業` と `個人ブランド` のどちらを最初の beachhead にするかを、problem urgency、支払意思、proof availability、到達可能性、納品適合性で比較して一つ選ぶ。

### Non-goals

- LP section copy や site implementation
- SNS 投稿や広告出稿
- production quality gate の変更
- 未計測の速度・収益・成果保証

## Workstream 2: Brand, Site, and Conversion

### Question

`訪問者が一瞬で自分事化し、信じ、迷わず一行の動画案を渡せる体験は何か。`

### Owns

- `marketing/LP/`

`marketing/README.md` と `marketing/SNS/` は参照のみとする。公開 site の実装 repo や `server/web/` を変更する場合は、文書設計を確定した後に別 task として扱う。

### Discuss and decide

1. common home の 0 秒 / 3 秒 / 10 秒 message
2. common brand Hero と persona-specific Hero の役割分担
3. original idea -> completed video を見せる Hero proof
4. claim と proof の対応、不足 proof の一覧
5. CTA、idea-first form、thanks / follow-up までの state flow
6. objection の順序と、説明より先に見せる証拠
7. 1 秒 / 3 秒 / 10 秒 comprehension test
8. Workstream 1 で承認済みの qualification を form state / funnel event へ投影する方法

### Outputs

- canonical copy / page section contract
- persona message consistency matrix
- proof requirement matrix
- CTA / form flow
- approved qualification を反映した event / KPI projection
- implementation acceptance checklist

### First task

共通ホームは `あなたの想いを、映像に。` を H1、persona LP は既存の persona-specific H1 を維持して brand line を signature とする役割分担を確定する。その上で、実在する一つの brief と完成動画を Hero proof に選ぶ。

### Non-goals

- category、価格、offer facts の独自変更
- SNS 運用、広告出稿
- production frontend / generation pipeline の変更
- proof のない視聴効果・速度・収益の主張
- 2 persona を一つの広告や LP へ統合すること

## Workstream 3: Proof, Acquisition, and Sales Learning

### Question

`どの persona / obstacle / proof / CTA が、関心ではなく有償需要につながるのか。`

### Owns

- `marketing/SNS/`

`marketing/README.md` と `marketing/LP/` は参照のみとし、positioning / offer / LP copy の変更要求は evidence とともに owner へ返す。

### Discuss and decide

1. persona 別の acquisition hypothesis
2. `1 persona / 1 obstacle / 1 proof / 1 CTA` の content package
3. diverse proof backlog と original intent / creator acceptance の記録
4. organic、直接商談、paid acquisition の開始条件
5. qualified lead / consultation / proposal / won-lost の記録方法
6. source / campaign / content を form submit 時に CRM へ一方向で引き継ぎ、受注・失注まで集計する privacy-safe attribution
7. price reaction、objection、lost reason の upstream handoff
8. 毎週の continue / revise / stop 判断

### Outputs

- 6 週間の persona-specific experiment calendar
- proof backlog and proof packages
- end-to-end funnel / CRM stage contract
- weekly learning log
- acquisition baseline by persona
- offer / LP owner へ返す objections、price response、won-lost evidence

### First task

既存の proof を persona / obstacle / initial brief / completed output / human work / revision / creator acceptance で棚卸しする。同時に、legacy mythology calendar と現行 product acquisition plan を分離し、商談・提案・受注・失注まで追える計測契約を作る。

### Non-goals

- Purpose、offer、primary persona の独自変更
- qualification / disqualification 定義の独自変更。変更案は商談 evidence とともに Workstream 1 へ返す
- LP / site 本体の編集
- offer owner の合意なしで価格を確定すること
- raw views、登録者、lead 数だけを成功とすること
- 根拠のない売上・速度・収益保証

Web analytics と CRM を結合するために raw PII、CRM record ID、hashed email、契約情報を analytics platform へ返さない。form submit 時に persona、source、campaign、content、UTM、landing path を CRM record へ一方向で保存し、CRM から外へ戻すのは集計値だけとする。

## File ownership and handoff

| Workstream | Writable canonical scope | Reads from | Hands off to |
|------------|--------------------------|------------|--------------|
| 1. Positioning / Offer | `marketing/README.md`, `marketing/go-to-market.md` | product readiness、market evidence | approved positioning / offer decisions |
| 2. Brand / Conversion | `marketing/LP/` | Workstream 1 decisions、Workstream 3 objections | destination / proof / conversion contract |
| 3. Proof / Acquisition / Sales Learning | `marketing/SNS/` | Workstream 1 decisions、Workstream 2 destination | response / consultation / won-lost evidence |

他 workstream の canonical file を変えたい場合は直接編集せず、次を owner へ渡す。

```text
Requested decision:
Evidence:
Affected persona / page / channel:
Expected benefit:
Risk if unchanged:
Files that may need projection:
```

## Sync cadence

3 スレッドは常時並列で進め、定期同期では次の5点だけを共有する。

1. 確定した decision
2. 新しく得た evidence
3. invalidated hypothesis
4. blocker / owner
5. 次に判定する一つの実験

意思決定の流れは次を守る。

```text
Positioning / offer
  -> LP / conversion projection
  -> proof / acquisition / sales execution
  -> measured response and won-lost learning
  -> positioning or conversion revision request
```

## Starter prompts for three Codex tasks

### Task 1

```text
ToC の Workstream 1: Positioning and Offer を担当してください。
最初に marketing/README.md と marketing/go-to-market.md を読み、所有範囲だけを編集してください。
副業と個人ブランドのどちらを最初の beachhead にするかを比較し、納品可能な offer、価格仮説、qualification、claim-to-proof を固めてください。
marketing/LP/ と marketing/SNS/ は直接編集せず、必要変更を owner への handoff として記述してください。
```

### Task 2

```text
ToC の Workstream 2: Brand, Site, and Conversion を担当してください。
marketing/README.md と marketing/go-to-market.md を上位正本として読み、marketing/LP/ だけを編集してください。
「あなたの想いを、映像に。」を common home の 0 秒認知から、proof、persona 選択、一行入力、Workstream 1 で承認済みの qualification の form / event 投影まで一貫させてください。
offer facts を独自に変更せず、必要な変更は Workstream 1 へ handoff してください。
```

### Task 3

```text
ToC の Workstream 3: Proof, Acquisition, and Sales Learning を担当してください。
marketing/README.md と marketing/go-to-market.md を上位正本として読み、marketing/SNS/ だけを編集してください。
persona 別 proof を棚卸しし、承認済み qualification を使って、6週間の獲得実験、qualified lead、商談、提案、受注・失注、継続制作まで追える学習ループを設計してください。
Purpose、offer、LP copy は独自に変更せず、反応データを owner への handoff として返してください。
```
