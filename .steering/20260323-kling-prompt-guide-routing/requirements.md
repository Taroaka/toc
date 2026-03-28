# Requirements

## Context

- `docs/video-generation.md` は動画生成全般の正本だが、Kling 3.0 向けの prompt 運用知見は汎用ルールと混ざっている
- `workflow/playbooks/video-generation/kling.md` は例の寄せ集めで、ToC 内の agent が参照すべき設計ガイドとしては使いづらい
- 物語生成から下流へ渡す prompt 設計で、Kling 利用時の参照先が明確ではない

## Problem

- Kling 3.0 を使う run で、agent が汎用ガイドだけを見て prompt を組み立てると、motion / continuity / negative constraints の粒度が不足しやすい
- provider 固有ガイドの参照条件が曖昧で、story/script 系 agent の実装と docs の間で運用差が出る

## Goals

- Kling 3.0 向けの動画生成プロンプト術を、再利用しやすい markdown の正本として整理する
- Kling 系 tool を使う場合だけ、動画 prompt を書く agent がその専用ガイドを優先参照する設計を明文化する
- 汎用の `docs/video-generation.md` は残し、provider 固有の差分だけを切り出す

## Non-Goals

- Kling API 実装や provider routing の変更
- 他 provider（Seedance, Veo など）の prompt ガイド追加
- 既存 run artifact の再生成

## Acceptance Criteria

1. `workflow/playbooks/video-generation/kling.md` が、Kling 3.0 / Kling 3.0 Omni 向け prompt guide として読める構成になる
2. `docs/story-creation.md` または `docs/script-creation.md` に、Kling 利用時は汎用動画ガイドに加えて専用ガイドを参照する方針が明記される
3. `docs/implementation/agent-roles-and-prompts.md` と少なくとも 1 つの実エージェント定義で、Kling 利用時の参照先分岐が明記される
