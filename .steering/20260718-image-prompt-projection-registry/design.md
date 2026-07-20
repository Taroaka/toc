# Design

## Two-layer guide

画像 prompt の虎の巻を次の2層へ分ける。

1. 不変原則: 単一瞬間、描画可能性、未確定選択の解消、future motion の除外、reference binding、cut差分、制作meta除外。
2. key projection registry: 正本キーごとの relevance、target group、変換責務、deterministic/semantic review 観点。

任意のfrontend inputは上流stageで共通設計キーへ正規化し、image prompt stageは登録済みキーだけを読む。

## Registry contract

`toc/image_prompt_projection_registry.py` を正本とし、各 rule は少なくとも次を持つ。

- `group`
- `source_keys`
- `relevance: required|conditional|none`
- `activation_dependency`
- `transform`
- `deterministic_checks`
- `semantic_checks`

`none` rule は provider groupを作らず、除外理由を持つ。初期登録では `motion_contract.motion_brief` をvideo-onlyとして宣言する。

## Review flow

1. compiler は registry の drawable group order を使って IR を構築する。
2. reviewer は manifest-local expected values と image dependencies から active rule を解決する。
3. active group は dependency、raw `required_groups`、exactly one non-empty fragment、provider prompt inclusionを確認する。
4. exact value binding rule は、source value、dependency、fragment text、provider promptの同値traceを確認する。
5. semantic pack は active/inactive rules と `include|omit|add|replace` の判断観点をcontextless reviewerへ渡す。

## Extension rule

新しい設計キーを追加する場合、prompt relevance を必ず分類する。

- `required|conditional`: registry rule、transform、deterministic check、semantic check、正常/異常テストを追加する。
- `none`: 除外理由を登録する。

compiler groupを追加したのにregistryへ登録しない変更は、coverage testでfailする。
