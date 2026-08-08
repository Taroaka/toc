# ToC marketing purpose and sales parallelism design

更新日: 2026-08-08

## Message hierarchy

```text
Purpose
  人の心を動かし、人生を豊かにする。

0-second customer-facing brand line
  あなたの想いを、映像に。

3-second outcome
  visitor の知識・物語・世界観が、相手へ届く一本になる

10-second mechanism
  企画、台本、映像、音声、編集を一つの制作フローへつなぐ

Functional promise
  動画制作を、もっと速く、もっと簡単に。

Emotional promise
  作りたいと思った瞬間を、完成まで止めない。
```

`圧倒的` は比較可能な実測がある場合だけ公開する。

## Copy roles

- Purpose は ToC が価値判断をするときの最上位基準
- customer-facing brand line は common site / brand surface の最初の入口
- 3-second outcome は visitor の未来を具体化する
- 10-second mechanism は ToC が何をつなぐシステムかを説明する
- persona LP の Hero は各 persona 固有の欲求と障壁を優先し、common brand line を無理に主見出しへ固定しない

## Three-workstream model

### Workstream 1: Positioning and Offer

- owns: `marketing/README.md`, `marketing/go-to-market.md`
- decides: category、Purpose、brand line、offer boundary、persona priority、価格表示原則、販売可能条件
- hands off: approved message / offer decision を Workstream 2 と 3 へ渡す
- does not own: LP section copy、channel post、広告管理画面、production code

### Workstream 2: Brand and Conversion

- owns: `marketing/LP/`
- decides: common site / persona LP の情報設計、Hero、proof 配置、CTA、lead form、承認済み qualification の conversion event への投影
- inputs: Workstream 1 の approved positioning / offer facts、Workstream 3 の objections / response data
- does not own: category / pricing policy の独自変更、SNS 配信、production frontend

### Workstream 3: Proof, Acquisition, and Sales Learning

- owns: `marketing/SNS/`
- decides: proof package、content pillar、channel plan、campaign hypothesis、distribution、analytics、学習の記録
- inputs: Workstream 1 の approved positioning、Workstream 2 の destination / event contract
- does not own: LP canonical copy、offer facts の独自変更、収益保証

## Coordination contract

1. 各スレッドは担当 workstream の canonical files だけを編集する
2. 他 workstream の正本を変えたい場合は、変更要求を文章で handoff し、所有スレッドが反映する
3. category、Purpose、brand line、persona、offer facts、primary CTA を shared decision とする
4. shared decision の変更は Workstream 1 で確定し、Workstream 2 / 3 が下流へ反映する
5. Workstream 3 の市場反応は evidence として Workstream 1 / 2 へ戻すが、自動で positioning を上書きしない
6. 3スレッドの共通レビューでは、直近の意思決定、検証結果、blocker、次の実験だけを同期する
7. qualification / disqualification の定義は Workstream 1 が所有し、Workstream 2 は form / event へ投影し、Workstream 3 は商談 evidence を返す
8. acquisition attribution は source metadata を CRM へ一方向で保存し、CRM identifier / PII / 契約情報を web analytics へ返さない

## Decision cadence

```text
Positioning / offer decision
  -> LP / conversion projection
  -> proof / acquisition execution
  -> measured response and sales objections
  -> positioning or conversion revision
```

3 workstream は並列に進めるが、この意思決定方向は逆転させない。
