---
name: ai-idea-studio
description: |
  Generate original story, world, or concept ideas that can be turned into a ToC production skeleton with scene mapping and visual invariants.
  Use when: the user asks for original video ideas, new story concepts, AI-generated premises, or fresh concepts that should avoid existing franchise-specific elements.
---

# AI Idea Studio（ネタ収集その3）

## Overview

オリジナルの世界観/物語/コンセプトを “制作可能なネタ” に変換する。
重要なのは「それっぽい設定」ではなく、**映像化できる見せ場（setpieces）と、破綻しないルール**。

## When to Use

- 「AIが考えた◯◯みたいなネタを出したい」
- 既存IPに寄せず、オリジナルの短編/シリーズの種が欲しい

## Clarify

- フォーマット: 物語 / 解説 / 没入型ライド（POV）/ scene-series（Q&A短編）など
- 尺: 60秒 / 10分 / 20分
- トーン: 怖い/爽やか/哲学/コメディ
- NG: グロ、露骨な性、特定作品の固有名詞・固有設定

## Output（slate: 10 ideas）

各案に必ず入れる:

- title + one_liner
- core question（何を問う話か）
- world rule（世界の不変ルール 2〜4）
- setpieces（映像の見せ場 3つ）
- protagonist / opponent（最低限）
- why it works（視聴維持の仕掛け: open loop / tension / reveal）
- originality guard（似せないための禁則: 固有名詞/定番演出を避ける）

## Pick one → Deep dive

### 1) Story-first skeleton

- canonical synopsis（1行 + 5〜10行）
- beat_sheet（10〜20）
- characters（goal / stakes / setting）

### 2) Scene mapping（最低20）

scene_id 1..20 を埋め、各sceneを1〜2行で定義する（後段で増やせる）。

### 3) Production notes（ToC接続）

- aspect_ratio（横/縦）
- visual invariants（POV/スタイル/禁止事項）
- risky points（破綻しやすい点、曖昧さ）

## Guidelines

- 既存作品の “固有表現” を輸入しない（名詞、固有の設定、決め台詞、象徴アイテム）
- 既存ジャンルの型は使ってよいが、必ず「固有のルール/固有の見せ場」で差別化する
