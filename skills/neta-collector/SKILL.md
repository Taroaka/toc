---
name: neta-collector
description: |
  Route ToC idea collection across folklore, self-help figures, original AI concepts, and era explainers, then produce either a slate or a deep dive.
  Use when: the user asks for video topic ideas, wants more candidate concepts, has not chosen a genre yet, or needs the right ToC idea-generation path selected quickly.
---

# Neta Collector（ネタ収集: 入口/ルータ）

## Overview

「ネタ収集」を複数カテゴリで回せるようにするための入口スキル。
最初に “どのネタ種別（その1〜その4）か” と “ゴール（候補出し or 1本深掘り）” を確定し、該当スキルの手順で出力する。

## Categories（ネタ種別）

1) 各国の物語（民話/神話/伝承） → `folktale-researcher`  
2) 世界で話題の自己啓発系人物（億万長者/ポッドキャスト等） → `selfhelp-trend-researcher`  
3) AIが考えたオリジナル◯◯（世界観/物語/コンセプト） → `ai-idea-studio`  
4) 時代解説（例: 縄文時代） → `era-explainer`  

## When to Use

- 「次の動画テーマのネタが欲しい（でもジャンルが決まってない/複数案欲しい）」
- 「世界の物語・話題の人物・AI発案・時代解説のどれかで、制作向けに候補を出してほしい」

## Instructions

### 0) Clarify（まず確定する）

未指定なら仮定して進め、仮定は明示する。

- ネタ種別: 1〜4
- 出力モード:
  - `slate`: 候補を8〜12個（短い推し理由付き）
  - `deep_dive`: 1個選んで ToC に落とす（骨格/scene割当/検証TODO）
- 制約: 対象年齢、怖さ、宗教/民族配慮、実写/アニメ、尺（例: 10〜20分 / 60秒ショート）

### 1) Dispatch（該当スキルで処理）

- 1) → `folktale-researcher`
- 2) → `selfhelp-trend-researcher`
- 3) → `ai-idea-studio`
- 4) → `era-explainer`

### 2) Output（共通フォーマット）

#### slate（候補出し）

- constraints（前提/NG/尺）
- candidates（8〜12）
  - title
  - one_liner
  - why_now / why_it_works（制作向け）
  - sensitivity/rights/verification（注意点）
- top_picks（1〜3）+ 理由
- next_questions（選ぶために聞きたいこと）

#### deep_dive（1本深掘り）

- まず Story-first（骨）を固める
- “未検証” を明示し、検証TODOと当たるべき典拠候補を列挙する
- 可能なら `workflow/research-template.yaml` 互換の YAML を出す

## Guidelines

- 断定しない（特に固有名詞・年代・資産/収入・論争点）
- 近代の再話/翻案や特定コンテンツの文章をなぞらない（骨格を自分の言葉で）
- センシティブ領域（宗教/民族/植民地主義/医療/投資）は注意点を先に出す
